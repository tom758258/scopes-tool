from __future__ import annotations

from pathlib import Path

from scopes_tool_webui.commands import command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_acquisition_wait_workflow_has_help_metadata() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}
    fields = {field["name"]: field for field in catalog["single-wait"]["fields"]}

    assert fields["trigger_timeout_seconds"]["help_key"] == "single-wait.trigger_timeout_seconds"
    assert fields["force_trigger_on_timeout"]["help_key"] == "single-wait.force_trigger_on_timeout"
    assert fields["trigger_poll_interval_ms"]["help_key"] == "single-wait.trigger_poll_interval_ms"
    assert "advanced" not in fields["trigger_poll_interval_ms"]


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
