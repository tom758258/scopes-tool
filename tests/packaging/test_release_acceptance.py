"""Release layout and isolated PowerShell orchestration contracts; no builds or hardware."""

import hashlib
import io
import json
import os
from pathlib import Path
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
@pytest.mark.parametrize("fault", ["version", "outside"])
def test_release_build_rejects_unsafe_inputs_before_building(tmp_path, fault):
    repo = _repository(tmp_path)
    python = repo / ".venv/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    if fault == "version":
        (repo / "desktop/package.json").write_text('{"version":"9.9.9"}')
        result = _run_script(repo, "build_release.ps1")
        assert "must match" in result.stderr
    else:
        result = _run_script(repo, "build_release.ps1", "-ReleaseRoot", tmp_path / "outside")
        assert "must stay under" in result.stderr
        assert not (tmp_path / "outside").exists()
    assert result.returncode != 0
    assert not (repo / "release").exists()
    assert not (repo / "dist").exists()


@WINDOWS
def test_release_build_uses_existing_builds_and_preserves_existing_output(tmp_path):
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
    result = _run_script(repo, "build_release.ps1")
    assert result.returncode == 0, result.stdout + result.stderr
    artifacts = repo / "release/0.1.0"
    assert len(list(artifacts.iterdir())) == 4
    for line in (artifacts / "checksums.txt").read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((artifacts / name).read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(artifacts / "scopes-tool-0.1.0-windows-x64.zip") as archive:
        assert {name.split("/")[0] for name in archive.namelist()} == {"scopes-tool-0.1.0"}
        assert all(f"scopes-tool-0.1.0/{name}" in archive.namelist()
                   for name in (*SMOKE["BUNDLE_EXECUTABLES"], "Scopes Tool.exe"))
    original = {path.name: path.read_bytes() for path in artifacts.iterdir()}
    rerun = _run_script(repo, "build_release.ps1")
    assert rerun.returncode != 0
    assert original == {path.name: path.read_bytes() for path in artifacts.iterdir()}
    assert not list((repo / ".tmp_tests").glob("release-build-*"))
