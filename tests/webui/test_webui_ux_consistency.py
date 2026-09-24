from __future__ import annotations

from pathlib import Path

from scopes_tool_webui.commands import command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_acquisition_wait_workflow_is_advanced_and_documented() -> None:
    editor = read_static("acquisition-editor.js")
    catalog = {entry["id"]: entry for entry in command_catalog()}
    fields = {field["name"]: field for field in catalog["single-wait"]["fields"]}

    assert "this.buildAdvancedSection()" in editor
    assert 'summary.textContent = translate("form.advanced")' in editor
    assert 'translate("acquisition.editor.controlHelp")' in editor
    assert fields["trigger_timeout_seconds"]["help_key"] == "single-wait.trigger_timeout_seconds"
    assert fields["force_trigger_on_timeout"]["help_key"] == "single-wait.force_trigger_on_timeout"
    assert fields["trigger_poll_interval_ms"]["help_key"] == "single-wait.trigger_poll_interval_ms"
    assert "advanced" not in fields["trigger_poll_interval_ms"]


def test_multiple_measurements_reuses_workflow_channel_and_item_help_below_choices() -> None:
    editor = read_static("measurement-editor.js")

    assert '"help.workflow.measurement.channels"' in editor
    assert '"help.workflow.measurement.items"' in editor
    assert "section.append(choices);\n    if (note) section.append(note);" in editor


def test_all_serial_search_views_explain_status_and_mode() -> None:
    editor = read_static("search-editor.js")

    assert 'this.labeledOutput("command.search-state", "state", "search.editor.stateHelp")' in editor
    assert 'this.labeledOutput("command.search-mode", "mode", "search.editor.modeHelp")' in editor
    assert "labeledOutput(labelKey, name, helpKey = null)" in editor


def test_segmented_memory_has_help_for_unread_realtime_and_segmented_states() -> None:
    editor = read_static("segmented-editor.js")

    assert '"segmented.editor.stateUnreadHelp"' in editor
    assert '"segmented.editor.stateRealtimeHelp"' in editor
    assert "this.stateHelp.hidden = !memoryView;" in editor


def test_workflow_boolean_options_are_full_rows_and_measure_until_is_half_width() -> None:
    editor = read_static("workflow-editor.js")
    styles = read_static("styles.css")

    assert editor.count("workflow-editor-full-row") >= 4
    assert editor.count('className += " workflow-editor-half-field"') == 2
    assert ".workflow-editor-full-row { grid-column: 1 / -1; }" in styles
    assert ".workflow-editor-half-field { width: calc(50% - 5px); }" in styles
    assert ".workflow-editor-half-field,\n  .sequence-editor-loop { width: 100%; max-width: none; }" in styles


def test_sequence_toolbar_is_documented_and_loop_count_is_half_width() -> None:
    editor = read_static("sequence-editor.js")
    styles = read_static("styles.css")

    assert 'translate("sequence.editor.toolbarHelp")' in editor
    assert ".sequence-editor-loop { width: calc(50% - 4px); max-width: none; }" in styles


def test_new_user_facing_copy_is_localized_in_both_languages() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    keys = (
        "acquisition.editor.controlHelp",
        "help.single-wait.trigger_timeout_seconds",
        "help.single-wait.trigger_poll_interval_ms",
        "search.editor.stateHelp",
        "search.editor.modeHelp",
        "segmented.editor.stateUnreadHelp",
        "segmented.editor.stateRealtimeHelp",
        "sequence.editor.toolbarHelp",
    )
    for key in keys:
        assert f'"{key}"' in english
        assert f'"{key}"' in chinese
