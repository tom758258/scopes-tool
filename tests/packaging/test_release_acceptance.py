"""Release layout and isolated PowerShell orchestration contracts; no builds or hardware."""

import hashlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
SMOKE = runpy.run_path(str(ROOT / "scripts/ci_packaging_smoke.py"))
WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell required")


def test_application_and_lockfile_versions_agree():
    version = re.search(r'^version = "([^"]+)"',
                        (ROOT / "pyproject.toml").read_text(), re.MULTILINE)[1]
    core = (ROOT / "src/scopes_tool_core/__init__.py").read_text(encoding="utf-8")
    assert re.search(r'^__version__ = "([^"]+)"', core, re.MULTILINE)[1] == version
    assert json.loads((ROOT / "desktop/package.json").read_text())["version"] == version
    lock = json.loads((ROOT / "desktop/package-lock.json").read_text())
    assert lock["version"] == lock["packages"][""]["version"] == version
    uv_lock = (ROOT / "uv.lock").read_text()
    assert re.search(r'name = "scopes-tool"\nversion = "([^"]+)"', uv_lock)[1] == version


@pytest.mark.parametrize("fault", [
    None, "version", "manifest-schema", "manifest-schema-float", "worker-schema",
    "worker-schema-float", "policy", "feature-missing", "feature-version", "feature-bool",
])
def test_packaged_cli_smoke_checks_common_v3_manifest(monkeypatch, tmp_path, fault):
    manifest = {
        "tool_version": "1.0.0", "schema_version": 2,
        "worker_protocol": {"schema_versions": [3], "compatibility_policy": "v3-only"},
        "features": {"common.async_jobs": {"contract_version": 1}},
    }
    if fault == "version":
        manifest["tool_version"] = "0.1.0"
    elif fault in ("manifest-schema", "manifest-schema-float"):
        manifest["schema_version"] = 3 if fault == "manifest-schema" else 2.0
    elif fault in ("worker-schema", "worker-schema-float"):
        manifest["worker_protocol"]["schema_versions"] = [2 if fault == "worker-schema" else 3.0]
    elif fault == "policy":
        manifest["worker_protocol"]["compatibility_policy"] = "v2-only"
    elif fault == "feature-missing":
        manifest["features"] = {}
    elif fault in ("feature-version", "feature-bool"):
        manifest["features"]["common.async_jobs"]["contract_version"] = (
            2 if fault == "feature-version" else True
        )
    commands = []

    def run(*command, env=None):
        commands.append(command)
        assert command[0] == "packaged/scopes-tool.exe"
        if command[1:] == ("manifest", "--json"):
            return json.dumps(manifest)
        if command[1] == "user-guide":
            filename = "cli.zh-TW.html" if "zh-TW" in command else "cli.html"
            return (tmp_path / filename).as_uri()
        return '{"ok": true}'

    smoke = SMOKE["_smoke_cli"]
    monkeypatch.setitem(smoke.__globals__, "_run", run)
    if fault:
        with pytest.raises(AssertionError, match="Packaged Manifest"):
            smoke("packaged/scopes-tool.exe", tmp_path, "1.0.0")
    else:
        smoke("packaged/scopes-tool.exe", tmp_path, "1.0.0")
        assert commands[-1][1:] == ("identify", "--simulate", "--json")
    assert ("packaged/scopes-tool.exe", "manifest", "--json") in commands


def _bundle(directory):
    for name in (*SMOKE["BUNDLE_EXECUTABLES"], "Scopes Tool.exe", "resources/app.asar",
                 "_internal/python312.dll", "_internal/scopes_tool_webui/static/index.html",
                 "_internal/scopes_tool-0.1.0.dist-info/METADATA"):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    (directory / "_internal/scopes_tool-0.1.0.dist-info/METADATA").write_text(
        "Metadata-Version: 2.1\nName: scopes-tool\nVersion: 0.1.0\n", encoding="utf-8",
    )
    for owner in ("scopes_tool_cli/help", "scopes_tool_webui/static/help"):
        for source in (ROOT / "src" / owner).iterdir():
            if source.is_file():
                target = directory / "_internal" / owner / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)


def _release(tmp_path, *, extra_internal=False):
    artifacts = tmp_path / "release"
    artifacts.mkdir()
    metadata = b"Metadata-Version: 2.1\nName: scopes-tool\nVersion: 0.1.0\n"
    with zipfile.ZipFile(artifacts / "scopes_tool-0.1.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr("scopes_tool-0.1.0.dist-info/METADATA", metadata)
    with tarfile.open(artifacts / "scopes_tool-0.1.0.tar.gz", "w:gz") as sdist:
        member = tarfile.TarInfo("scopes_tool-0.1.0/PKG-INFO")
        member.size = len(metadata)
        sdist.addfile(member, io.BytesIO(metadata))
    bundle = tmp_path / "scopes-tool-0.1.0"
    _bundle(bundle)
    if extra_internal:
        (bundle / "resources/backend/_internal").mkdir(parents=True)
    with zipfile.ZipFile(artifacts / "scopes-tool-0.1.0-windows-x64.zip", "w") as archive:
        for path in bundle.rglob("*"):
            archive.write(path, path.relative_to(tmp_path))
    _checksums(artifacts)
    return artifacts


def _checksums(artifacts):
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
             for path in sorted(artifacts.iterdir()) if path.name != "checksums.txt"]
    (artifacts / "checksums.txt").write_text("".join(lines), encoding="utf-8")


def test_release_layout_checks_distributions_and_unified_desktop(tmp_path):
    artifacts = _release(tmp_path)
    extracted = SMOKE["_check_release"](artifacts, "0.1.0", tmp_path / "extracted")
    assert extracted.name == "scopes-tool-0.1.0"
    assert len(list(extracted.rglob("_internal"))) == 1


@pytest.mark.parametrize("fault, message", [
    ("checksum", "SHA-256 mismatch"), ("duplicate-checksum", "duplicate checksum"),
    ("extra-file", "exactly ZIP"), ("duplicate-backend", "one shared _internal"),
    ("zip-root", "single versioned"), ("zip-traversal", "single versioned"),
    ("version", "Distribution metadata"), ("extra-exe", "four application"),
])
def test_release_layout_rejects_invalid_artifacts(tmp_path, fault, message):
    artifacts = _release(tmp_path, extra_internal=fault == "duplicate-backend")
    if fault == "checksum":
        with (artifacts / "scopes_tool-0.1.0.tar.gz").open("ab") as stream:
            stream.write(b"corrupt")
    elif fault == "duplicate-checksum":
        checksums = artifacts / "checksums.txt"
        checksums.write_text(checksums.read_text() * 2, encoding="utf-8")
    elif fault == "extra-file":
        (artifacts / "extra.exe").write_bytes(b"fixture")
    elif fault in ("zip-root", "zip-traversal"):
        with zipfile.ZipFile(artifacts / "scopes-tool-0.1.0-windows-x64.zip", "a") as archive:
            archive.writestr("other/file" if fault == "zip-root" else "scopes-tool-0.1.0/../escape", b"x")
        _checksums(artifacts)
    elif fault == "version":
        with zipfile.ZipFile(artifacts / "scopes_tool-0.1.0-py3-none-any.whl", "w") as wheel:
            wheel.writestr("scopes_tool-0.1.0.dist-info/METADATA", "Name: scopes-tool\nVersion: 9.9.9\n")
        _checksums(artifacts)
    elif fault == "extra-exe":
        with zipfile.ZipFile(artifacts / "scopes-tool-0.1.0-windows-x64.zip", "a") as archive:
            archive.writestr("scopes-tool-0.1.0/extra.exe", b"fixture")
        _checksums(artifacts)
    with pytest.raises(AssertionError, match=message):
        SMOKE["_check_release"](artifacts, "0.1.0", tmp_path / "extracted")


def _run_script(repo, name, *arguments):
    environment = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(repo / "scripts" / name), *map(str, arguments)],
        cwd=repo, env=environment, capture_output=True, text=True, timeout=60,
    )


def _repository(tmp_path):
    repo = tmp_path / "repository with spaces"
    (repo / "scripts").mkdir(parents=True)
    (repo / "desktop").mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "scopes-tool"\nversion = "0.1.0"\n')
    (repo / "desktop/package.json").write_text('{"version":"0.1.0"}')
    for name in ("build_release.ps1", "release-acceptance.ps1", "_validation_helpers.ps1"):
        shutil.copyfile(ROOT / "scripts" / name, repo / "scripts" / name)
    return repo


@WINDOWS
@pytest.mark.parametrize("fault", ["dirty", "version", "command", "head", "success"])
def test_acceptance_records_gates_failures_and_unexecuted_steps(tmp_path, fault):
    repo = _repository(tmp_path)
    # Replace only subprocess execution in this isolated fixture. Never build or install.
    stub = r'''
function Invoke-CapturedCommand {
    param($Name, $FilePath, $Arguments, $StdOutPath, $StdErrPath, $WorkingDirectory)
    $text = ""
    if ($Name -in @("git-head", "final-head")) { $text = "fixture-commit" }
    if ($env:RELEASE_TEST_FAULT -eq "dirty" -and $Name -eq "git-clean") { $text = " M README.md" }
    if ($env:RELEASE_TEST_FAULT -eq "head" -and $Name -eq "final-head") { $text = "different-commit" }
    $code = if ($env:RELEASE_TEST_FAULT -eq "command" -and $Name -eq "build") { 7 } else { 0 }
    Write-Utf8NoBomText -LiteralPath $StdOutPath -Text $text
    return @{ name=$Name; command=$FilePath; arguments=$Arguments; exit_code=$code;
        duration_ms=1; success=($code -eq 0); stdout=$StdOutPath; stderr=""; stdout_text=$text }
}
'''
    with (repo / "scripts/_validation_helpers.ps1").open("a", encoding="utf-8") as stream:
        stream.write(stub)
    if fault == "version":
        (repo / "desktop/package.json").write_text('{"version":"9.9.9"}')
    env = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
    env["RELEASE_TEST_FAULT"] = fault
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(repo / "scripts/release-acceptance.ps1")],
        cwd=repo, env=env, capture_output=True, text=True, timeout=60,
    )
    reports = list((repo / ".tmp_tests").rglob("report.json"))
    assert len(reports) == 1, result.stdout + result.stderr
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["hardware_touched"] is False
    assert report["source_commit"] == "fixture-commit"
    assert all(step["duration_ms"] >= 0 for step in report["steps"])
    if fault == "success":
        assert result.returncode == 0, result.stdout + result.stderr
        assert report["ok"] is True
        assert all(step["result"] == "PASS" for step in report["steps"])
        build = next(command for command in report["commands"] if command["name"] == "build")
        assert Path(build["arguments"][-1]).is_relative_to(repo / ".tmp_tests")
    else:
        assert result.returncode == 1, result.stdout + result.stderr
        failed = [step for step in report["steps"] if step["result"] == "FAIL"]
        assert len(failed) == 1
        expected_step = {"dirty": "git-source", "version": "versions", "command": "build-release", "head": "source-unchanged"}[fault]
        assert failed[0]["name"] == expected_step
        assert failed[0]["error"]
        assert failed[0]["exit_code"] == (7 if fault == "command" else 1)
        if fault != "head":
            assert any(step["result"] == "NOT RUN" for step in report["steps"])


@WINDOWS
def test_acceptance_rejects_output_escape_before_creating_directory(tmp_path):
    repo = _repository(tmp_path)
    outside = tmp_path / "outside"
    result = _run_script(repo, "release-acceptance.ps1", "-OutputRoot", outside)
    assert result.returncode != 0
    assert not outside.exists()
    assert "must stay under" in result.stderr


@WINDOWS
@pytest.mark.parametrize("fault", [
    "version", "outside", ".", ".git", ".GIT/unused/../releases", ".venv", ".VeNv/releases",
])
def test_release_build_rejects_unsafe_inputs_before_building(tmp_path, fault):
    repo = _repository(tmp_path)
    python = repo / ".venv/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    if fault == "version":
        (repo / "desktop/package.json").write_text('{"version":"9.9.9"}')
    (repo / ".git").mkdir()
    (repo / ".git/keep.txt").write_bytes(b"preserve git data")
    (repo / ".venv/keep.txt").write_bytes(b"preserve environment data")
    original = {path.relative_to(repo): path.read_bytes() if path.is_file() else None
                for path in repo.rglob("*")}
    if fault == "version":
        result = _run_script(repo, "build_release.ps1")
        assert "must match" in result.stderr
    elif fault == "outside":
        result = _run_script(repo, "build_release.ps1", "-ReleaseRoot", tmp_path / "outside")
        assert "must stay under" in result.stderr
        assert not (tmp_path / "outside").exists()
    else:
        result = _run_script(repo, "build_release.ps1", "-ReleaseRoot", fault)
        assert "ReleaseRoot cannot be" in result.stderr
    assert result.returncode != 0
    assert original == {path.relative_to(repo): path.read_bytes() if path.is_file() else None
                        for path in repo.rglob("*")}
    assert not (repo / "release").exists()
    assert not (repo / "dist").exists()


@WINDOWS
@pytest.mark.parametrize("release_root", [None, ".tmp_tests/releases", ".github/releases",
                                          "artifacts/releases"])
def test_release_build_uses_existing_builds_and_preserves_existing_output(tmp_path, release_root):
    repo = _repository(tmp_path)
    # A minimal Python module and Desktop producer stand in for the heavyweight builds.
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(repo / ".venv")], check=True)
    (repo / "build.py").write_text('''
from pathlib import Path
import sys
output = Path(sys.argv[sys.argv.index('--outdir') + 1])
for name in ('scopes_tool-0.1.0-py3-none-any.whl', 'scopes_tool-0.1.0.tar.gz'):
    (output / name).write_bytes(b'fixture')
''', encoding="utf-8")
    source = repo / "fixture-desktop"
    _bundle(source)
    (repo / "scripts/build_desktop.ps1").write_text('''
$root = Split-Path $PSScriptRoot -Parent
$destination = Join-Path $root "dist\\desktop\\win-unpacked"
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root "fixture-desktop") -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse
}
''', encoding="utf-8")
    (repo / "scripts/ci_packaging_smoke.py").write_text("# Layout checked separately with real inspector.\n")
    arguments = ("-ReleaseRoot", release_root) if release_root else ()
    result = _run_script(repo, "build_release.ps1", *arguments)
    assert result.returncode == 0, result.stdout + result.stderr
    artifacts = repo / (release_root or "release") / "0.1.0"
    assert len(list(artifacts.iterdir())) == 4
    for line in (artifacts / "checksums.txt").read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((artifacts / name).read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(artifacts / "scopes-tool-0.1.0-windows-x64.zip") as archive:
        assert {name.split("/")[0] for name in archive.namelist()} == {"scopes-tool-0.1.0"}
        assert all(f"scopes-tool-0.1.0/{name}" in archive.namelist()
                   for name in (*SMOKE["BUNDLE_EXECUTABLES"], "Scopes Tool.exe"))
    original = {path.name: path.read_bytes() for path in artifacts.iterdir()}
    rerun = _run_script(repo, "build_release.ps1", *arguments)
    assert rerun.returncode != 0
    assert original == {path.name: path.read_bytes() for path in artifacts.iterdir()}
    assert not list((repo / ".tmp_tests").glob("release-build-*"))
