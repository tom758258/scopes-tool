"""Check actual Windows onedir outputs without connecting to instruments."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_EXECUTABLES = (
    "scopes-tool.exe",
    "scopes-tool-webui-launcher.exe",
    "scopes-tool-webui-host.exe",
)


def _require_file(root: Path, relative: str) -> None:
    path = root / relative
    if not path.is_file():
        raise AssertionError(f"Missing packaged file: {path}")


def _run(*command: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=90, check=False,
    )
    if result.returncode:
        raise AssertionError(
            f"Packaged command failed ({result.returncode}): {command!r}\n"
            f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-2000:]}"
        )
    return result.stdout


def _check_bundle_contents(directory: Path) -> None:
    if not directory.is_dir():
        raise AssertionError(f"Missing Windows onedir output: {directory}")
    for filename in BUNDLE_EXECUTABLES:
        _require_file(directory, filename)
    internal = directory / "_internal"
    if not internal.is_dir():
        raise AssertionError(f"Missing shared _internal: {internal}")
    if len([path for path in directory.rglob("_internal") if path.is_dir()]) != 1:
        raise AssertionError("Windows output must have exactly one shared _internal")
    if (directory / "resources" / "backend").exists():
        raise AssertionError("Unexpected duplicate Python backend")
    libraries = list(directory.rglob("python*.dll"))
    if not libraries or any(path.parent != internal for path in libraries):
        raise AssertionError("Python runtime libraries must exist only in the shared _internal")
    if any("portable" in path.name.lower() for path in directory.rglob("*.exe")):
        raise AssertionError("Unexpected portable executable")
    _require_file(directory, "_internal/scopes_tool_webui/static/index.html")
    for owner, guide in (("scopes_tool_cli/help", "cli"),
                         ("scopes_tool_webui/static/help", "webui")):
        for filename in (f"{guide}.html", f"{guide}.zh-TW.html", "supported-models.html",
                         "supported-models.zh-TW.html", "help.css"):
            relative = f"_internal/{owner}/{filename}"
            _require_file(directory, relative)
            if (directory / relative).read_bytes() != (ROOT / "src" / owner / filename).read_bytes():
                raise AssertionError(f"Packaged Help differs from runtime source: {relative}")
    if len(list(internal.glob("scopes_tool-*.dist-info/METADATA"))) != 1:
        raise AssertionError("Missing or duplicate scopes-tool distribution metadata")


def _smoke_cli(cli: str, help_root: Path) -> None:
    _run(cli, "--help")
    # Echo the browser URI from a child process instead of opening a GUI.
    browser = f'"{Path(sys.executable).as_posix()}" -c "print(__import__(\'sys\').argv[1])" %s'
    browser_env = {**os.environ, "BROWSER": browser}
    for options, filename in (((), "cli.html"), (("--lang", "zh-TW"), "cli.zh-TW.html")):
        uri = _run(cli, "user-guide", *options, env=browser_env).strip()
        expected = (help_root / filename).as_uri()
        if uri != expected:
            raise AssertionError(f"Packaged User Guide URI differs: {uri!r} != {expected!r}")
    result = json.loads(_run(cli, "identify", "--simulate", "--json"))
    if result.get("ok") is not True:
        raise AssertionError(f"Packaged simulator identify did not succeed: {result!r}")


def _check_desktop(directory: Path) -> None:
    _check_bundle_contents(directory)
    _require_file(directory, "Scopes Tool.exe")
    _require_file(directory, "resources/app.asar")
    if {path.name for path in directory.glob("*.exe")} != {*BUNDLE_EXECUTABLES, "Scopes Tool.exe"}:
        raise AssertionError("Desktop root must contain exactly the four application executables")


def _check_distributions(directory: Path, version: str) -> None:
    def check_metadata(data: bytes) -> None:
        metadata = BytesParser().parsebytes(data)
        if metadata["Name"] != "scopes-tool" or metadata["Version"] != version:
            raise AssertionError("Distribution metadata does not match scopes-tool and release version")

    with zipfile.ZipFile(directory / f"scopes_tool-{version}-py3-none-any.whl") as wheel:
        metadata = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
        if metadata != [f"scopes_tool-{version}.dist-info/METADATA"]:
            raise AssertionError("Unexpected wheel metadata layout")
        check_metadata(wheel.read(metadata[0]))
    with tarfile.open(directory / f"scopes_tool-{version}.tar.gz") as sdist:
        root = f"scopes_tool-{version}"
        if {name.split("/")[0] for name in sdist.getnames()} != {root}:
            raise AssertionError("Unexpected sdist root")
        package_info = sdist.extractfile(f"{root}/PKG-INFO")
        if package_info is None:
            raise AssertionError("Missing sdist metadata")
        check_metadata(package_info.read())


def _check_release(directory: Path, version: str, extract_dir: Path) -> Path:
    names = {
        f"scopes-tool-{version}-windows-x64.zip",
        f"scopes_tool-{version}-py3-none-any.whl",
        f"scopes_tool-{version}.tar.gz",
    }
    if {path.name for path in directory.iterdir()} != names | {"checksums.txt"}:
        raise AssertionError("Release must contain exactly ZIP, wheel, sdist, and checksums.txt")
    if any(not path.is_file() or not path.stat().st_size for path in directory.iterdir()):
        raise AssertionError("Release artifacts must be non-empty files")
    entries = {}
    for line in (directory / "checksums.txt").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)
        if not match or match[2] in entries:
            raise AssertionError("Malformed or duplicate checksum entry")
        entries[match[2]] = match[1].lower()
    if set(entries) != names:
        raise AssertionError("Checksum entries must cover exactly the three distributables")
    for name, expected in entries.items():
        digest = hashlib.sha256()
        with (directory / name).open("rb") as artifact:
            for block in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise AssertionError(f"SHA-256 mismatch: {name}")
    _check_distributions(directory, version)
    extract_dir = extract_dir.resolve()
    extract_dir.relative_to((ROOT / ".tmp_tests").resolve())
    # A new directory prevents stale files from satisfying layout checks.
    extract_dir.mkdir(parents=True, exist_ok=False)
    root = f"scopes-tool-{version}"
    with zipfile.ZipFile(directory / f"{root}-windows-x64.zip") as archive:
        for member in archive.infolist():
            parts = member.filename.replace("\\", "/").split("/")
            if parts[0] != root or any(part in ("..", ".") or ":" in part for part in parts):
                raise AssertionError("Windows ZIP must contain a single versioned application root")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise AssertionError("Windows ZIP cannot contain symbolic links")
        archive.extractall(extract_dir)
    target = extract_dir / root
    _check_desktop(target)
    metadata_path = next((target / "_internal").glob("scopes_tool-*.dist-info/METADATA"))
    metadata = BytesParser().parsebytes(metadata_path.read_bytes())
    if metadata["Name"] != "scopes-tool" or metadata["Version"] != version:
        raise AssertionError("Desktop distribution metadata does not match release version")
    return target


def _smoke_installed(python: Path, version: str) -> None:
    # Isolated imports must resolve inside the new environment, never src/.
    code = """
import importlib, importlib.metadata, json, pathlib, sys
assert importlib.metadata.version('scopes-tool') == sys.argv[1]
for name in ('scopes_tool_core', 'scopes_tool_cli', 'scopes_tool_webui'):
    pathlib.Path(importlib.import_module(name).__file__).resolve().relative_to(pathlib.Path(sys.prefix).resolve())
from importlib.resources import files
for package, relative, guide in (('scopes_tool_cli', 'help', 'cli'), ('scopes_tool_webui', 'static/help', 'webui')):
    root = files(package).joinpath(relative)
    for name in (guide + '.html', guide + '.zh-TW.html', 'supported-models.html', 'supported-models.zh-TW.html', 'help.css'):
        assert root.joinpath(name).is_file(), name
print(json.dumps(str(files('scopes_tool_cli').joinpath('help'))))
"""
    help_root = Path(json.loads(_run(str(python), "-I", "-c", code, version)))
    _smoke_cli(str(python.parent / "scopes-tool.exe"), help_root)
    _run(str(python.parent / "scopes-tool-webui.exe"), "--help")
    _require_file(python.parent, "scopes-tool-webui-launcher.exe")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mode", choices=("bundle", "desktop"))
    mode.add_argument("--release-dir", type=Path)
    mode.add_argument("--installed-python", type=Path)
    parser.add_argument("--expected-version")
    parser.add_argument("--extract-dir", type=Path)
    parser.add_argument("--layout-only", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("real Windows packaging smoke requires Windows")

    if args.release_dir or args.installed_python:
        if not args.expected_version:
            parser.error("--expected-version is required for release and installed checks")
        if args.installed_python:
            _smoke_installed(args.installed_python.resolve(), args.expected_version)
        else:
            if not args.extract_dir:
                parser.error("--extract-dir under .tmp_tests is required for release checks")
            target = _check_release(args.release_dir, args.expected_version, args.extract_dir)
            if not args.layout_only:
                _smoke_cli(str(target / "scopes-tool.exe"), target / "_internal/scopes_tool_cli/help")
        print("Release packaging smoke passed (no hardware)")
        return 0

    bundle = ROOT / "dist" / "scopes-tool"
    _check_bundle_contents(bundle)
    target = bundle
    if args.mode == "desktop":
        target = ROOT / "dist" / "desktop" / "win-unpacked"
        _check_desktop(target)
    if not args.layout_only:
        _smoke_cli(str(target / "scopes-tool.exe"), target / "_internal/scopes_tool_cli/help")
    print(f"Windows {args.mode} packaging smoke passed (no hardware)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
