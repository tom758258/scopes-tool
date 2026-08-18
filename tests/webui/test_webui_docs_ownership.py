from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_ROOT = REPO_ROOT / "docs" / "webui"


def read_doc(*parts: str) -> str:
    return DOC_ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_webui_docs_are_root_level():
    assert (DOC_ROOT / "README.md").exists()
    assert (DOC_ROOT / "web-ui-change-rules.md").exists()
    assert (REPO_ROOT / "CHANGELOG.md").exists()
    assert (REPO_ROOT / "AGENTS.md").exists()
    assert (REPO_ROOT / "README.md").exists()
    assert (REPO_ROOT / "docs" / "architecture" / "monorepo-layout.md").exists()
    assert (REPO_ROOT / "docs" / "contracts" / "scopes-worker-contract.md").exists()


def test_webui_readme_names_public_package_identity():
    text = read_doc("README.md")

    assert "scopes_tool_webui" in text
    assert "web-ui-change-rules.md" in text


def test_root_readme_discovers_webui_and_agent_docs():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "AGENTS.md" in text
    assert "docs/webui/README.md" in text
    assert "docs/webui/web-ui-change-rules.md" in text
