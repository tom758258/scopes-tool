"""Validate tracked repository text files for basic hygiene."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re
import subprocess
import sys


TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".css",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".lock",
        ".md",
        ".ps1",
        ".py",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
SPECIAL_TEXT_FILENAMES = frozenset(
    {
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        "AGENTS.md",
        "CHANGELOG.md",
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "uv.lock",
    }
)
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".tmp_pytest",
        ".tmp_tests",
        ".venv",
        "Local",
        "artifacts",
        "build",
        "captures",
        "coverage",
        "dist",
        "htmlcov",
        "reports",
    }
)
REPLACEMENT_CHARACTER = chr(0xFFFD)
UTF8_BOM = bytes((0xEF, 0xBB, 0xBF))
MOJIBAKE_PATTERNS = (
    re.compile(rf"{chr(0x00C2)}[\u0080-\u00BF\u00A0-\u00FF]"),
    re.compile(rf"{chr(0x00C3)}[\u0080-\u00BF\u00A0-\u00FF]"),
    re.compile(rf"{chr(0x00E2)}{chr(0x20AC)}"),
    re.compile(rf"{chr(0x00F0)}{chr(0x0178)}"),
)


def tracked_files(repo_root: Path) -> tuple[Path, ...]:
    """Return repository-relative tracked paths in stable order."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "git ls-files failed")

    return tuple(
        sorted(
            (Path(item) for item in result.stdout.decode("utf-8").split("\0") if item),
            key=lambda path: path.as_posix(),
        )
    )


def is_checked_text_path(relative_path: Path) -> bool:
    """Return whether a tracked path belongs to the text-check scope."""
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return False
    if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative_path.parts):
        return False
    if relative_path.name in SPECIAL_TEXT_FILENAMES:
        return True
    return relative_path.suffix.lower() in TEXT_SUFFIXES


def selected_text_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    """Filter candidate paths to the stable text-check scope."""
    return tuple(
        sorted(
            (path for path in paths if is_checked_text_path(path)),
            key=lambda path: path.as_posix(),
        )
    )


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_body(line: str) -> str:
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith(("\n", "\r")):
        return line[:-1]
    return line


def inspect_text_file(path: Path, relative_path: Path) -> list[str]:
    """Return text-hygiene findings for one selected file."""
    data = path.read_bytes()
    display_path = relative_path.as_posix()
    findings: list[str] = []

    if data.startswith(UTF8_BOM):
        findings.append(f"{display_path}:1: UTF-8 BOM is not allowed")

    nul_offset = data.find(b"\0")
    if nul_offset >= 0:
        findings.append(f"{display_path}:byte {nul_offset}: NUL byte is not allowed")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        findings.append(f"{display_path}:byte {error.start}: invalid UTF-8")
        return findings

    if data and not data.endswith(b"\n"):
        findings.append(
            f"{display_path}:{text.count(chr(10)) + 1}: final newline is required"
        )

    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        if _line_body(line).endswith((" ", "\t")):
            findings.append(f"{display_path}:{line_number}: trailing whitespace")

    replacement_offset = text.find(REPLACEMENT_CHARACTER)
    if replacement_offset >= 0:
        findings.append(
            f"{display_path}:{_line_number(text, replacement_offset)}: "
            "U+FFFD replacement character is not allowed"
        )

    for pattern in MOJIBAKE_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            findings.append(
                f"{display_path}:{_line_number(text, match.start())}: "
                "likely UTF-8 mojibake is not allowed"
            )
            break

    return findings


def collect_findings(repo_root: Path, paths: Iterable[Path]) -> list[str]:
    """Inspect selected repository-relative paths in deterministic order."""
    findings: list[str] = []
    for relative_path in selected_text_paths(paths):
        findings.extend(inspect_text_file(repo_root / relative_path, relative_path))
    return findings


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        findings = collect_findings(repo_root, tracked_files(repo_root))
    except (OSError, RuntimeError) as error:
        print(f"text hygiene check failed: {error}", file=sys.stderr)
        return 1

    if findings:
        print("Tracked text hygiene failures:", file=sys.stderr)
        print(*findings, sep="\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
