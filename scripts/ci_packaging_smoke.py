"""Check actual Windows onedir outputs without connecting to instruments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


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


def _run(*command: str) -> str:
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True,
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


def _smoke_commands(directory: Path) -> None:
    cli = str(directory / "scopes-tool.exe")
    _run(cli, "--help")
    result = json.loads(_run(cli, "identify", "--simulate", "--json"))
    if result.get("ok") is not True:
        raise AssertionError(f"Packaged simulator identify did not succeed: {result!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("bundle", "desktop"), required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("real Windows packaging smoke requires Windows")

    bundle = ROOT / "dist" / "scopes-tool"
    _check_bundle_contents(bundle)
    target = bundle
    if args.mode == "desktop":
        target = ROOT / "dist" / "desktop" / "win-unpacked"
        _check_bundle_contents(target)
        _require_file(target, "Scopes Tool.exe")
        _require_file(target, "resources/app.asar")
    _smoke_commands(target)
    print(f"Windows {args.mode} packaging smoke passed (no hardware)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
