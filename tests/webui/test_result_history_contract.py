from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_JS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "results.js"


def test_result_panel_preserves_powers_style_bounded_job_history() -> None:
    source = RESULTS_JS.read_text(encoding="utf-8")

    assert "const RESULT_HISTORY_LIMIT = 20;" in source
    assert "let resultHistory = [];" in source
    assert "resultHistory.findIndex(" in source
    assert 'entry.job.job_id === job.job_id' in source
    assert "resultHistory.splice(existingIndex, 1);" in source
    assert 'resultHistory.unshift({ kind: "job", job });' in source
    assert "resultHistory = resultHistory.slice(0, RESULT_HISTORY_LIMIT);" in source
    assert "resultHistory.forEach((entry) =>" in source
    assert "commandLabel(entry.job.command)" in source
    assert "translateJobStatus(statusValue)" in source


def test_result_clear_resets_history_and_detail() -> None:
    source = RESULTS_JS.read_text(encoding="utf-8")

    render_empty = source.split("export function renderEmpty", 1)[1].split("\n}", 1)[0]
    assert "resultHistory = [];" in render_empty
    assert "summaryContainer.replaceChildren(emptyMessage());" in render_empty
    assert "detailContainer.replaceChildren(emptyMessage());" in render_empty
