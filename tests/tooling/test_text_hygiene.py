from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_text_hygiene.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_text_hygiene", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_inspect_text_file_accepts_valid_utf8_lf_crlf_and_empty(tmp_path: Path) -> None:
    cases = (
        ("lf.py", "value = 'ok'\n".encode()),
        ("crlf.py", "value = 'ok'\r\n".encode()),
        ("traditional.md", "正常繁體中文，全形標點。 café · → ✓\n".encode()),
        ("empty.txt", b""),
    )
    for name, content in cases:
        path = tmp_path / name
        _write_bytes(path, content)
        assert CHECKER.inspect_text_file(path, Path(name)) == []


def test_inspect_text_file_rejects_trailing_whitespace_for_lf_and_crlf(tmp_path: Path) -> None:
    path = tmp_path / "trailing.txt"
    _write_bytes(path, b"clean\r\nspace \r\ntab\t\n")

    assert CHECKER.inspect_text_file(path, Path("trailing.txt")) == [
        "trailing.txt:2: trailing whitespace",
        "trailing.txt:3: trailing whitespace",
    ]


def test_inspect_text_file_rejects_missing_final_newline(tmp_path: Path) -> None:
    path = tmp_path / "missing.py"
    _write_bytes(path, b"first\nsecond")

    assert CHECKER.inspect_text_file(path, Path("missing.py")) == [
        "missing.py:2: final newline is required"
    ]


def test_inspect_text_file_rejects_bom_nul_and_invalid_utf8(tmp_path: Path) -> None:
    bom_path = tmp_path / "bom.py"
    nul_path = tmp_path / "contains_nul.py"
    invalid_path = tmp_path / "invalid.py"
    _write_bytes(bom_path, bytes((0xEF, 0xBB, 0xBF)) + b"value = 'ok'\n")
    _write_bytes(nul_path, b"value\0\n")
    _write_bytes(invalid_path, b"value = '\xff'\n")

    assert CHECKER.inspect_text_file(bom_path, Path("bom.py")) == [
        "bom.py:1: UTF-8 BOM is not allowed"
    ]
    assert CHECKER.inspect_text_file(nul_path, Path("contains_nul.py")) == [
        "contains_nul.py:byte 5: NUL byte is not allowed"
    ]
    assert CHECKER.inspect_text_file(invalid_path, Path("invalid.py")) == [
        "invalid.py:byte 9: invalid UTF-8"
    ]


def test_inspect_text_file_rejects_replacement_character_and_mojibake(tmp_path: Path) -> None:
    replacement_path = tmp_path / "replacement.py"
    mojibake_path = tmp_path / "mojibake.py"
    _write_bytes(replacement_path, "value = '\ufffd'\n".encode())
    mojibake = b"caf\xc3\xa9".decode("latin-1")
    _write_bytes(mojibake_path, f"value = {mojibake!r}\n".encode())

    assert CHECKER.inspect_text_file(replacement_path, Path("replacement.py")) == [
        "replacement.py:1: U+FFFD replacement character is not allowed"
    ]
    assert CHECKER.inspect_text_file(mojibake_path, Path("mojibake.py")) == [
        "mojibake.py:1: likely UTF-8 mojibake is not allowed"
    ]


def test_selected_text_paths_includes_source_and_excludes_binary_or_generated_paths() -> None:
    paths = (
        Path(".gitignore"),
        Path("Local/private.md"),
        Path("assets/logo.png"),
        Path("build/generated.py"),
        Path("scripts/check_text_hygiene.py"),
        Path("src/scopes_tool_webui/static/index.html"),
        Path("tests/tooling/test_text_hygiene.py"),
        Path("tests/webui/.gitkeep"),
    )

    assert CHECKER.selected_text_paths(paths) == (
        Path(".gitignore"),
        Path("scripts/check_text_hygiene.py"),
        Path("src/scopes_tool_webui/static/index.html"),
        Path("tests/tooling/test_text_hygiene.py"),
    )


def test_tracked_files_ignores_untracked_text(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    _write_bytes(repo / "tracked.py", b"tracked = True\n")
    _write_bytes(repo / "untracked.py", b"untracked = True   \n")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)

    assert CHECKER.tracked_files(repo) == (Path("tracked.py"),)


def test_repository_tracked_text_is_clean() -> None:
    assert CHECKER.collect_findings(REPO_ROOT, CHECKER.tracked_files(REPO_ROOT)) == []
