from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = REPO_ROOT / "src" / "scopes_tool_core"


def test_core_source_does_not_print_directly():
    offenders = []
    for path in CORE_SRC.glob("*.py"):
        if "print(" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)

    assert offenders == []


def test_operations_do_not_depend_on_cli_process_state():
    text = (CORE_SRC / "operations.py").read_text(encoding="utf-8")

    assert "argparse" not in text
    assert "sys.argv" not in text
