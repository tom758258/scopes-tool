from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"

_KEY_PATTERN = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:')


def locale_keys(name: str) -> set[str]:
    return set(_KEY_PATTERN.findall((STATIC_ROOT / name).read_text(encoding="utf-8")))


def test_locale_key_parity() -> None:
    en_keys = locale_keys("locale_en.js")
    zh_keys = locale_keys("locale_zh_tw.js")
    assert en_keys == zh_keys, (
        "missing_in_zh: " + str(sorted(en_keys - zh_keys))
        + " missing_in_en: " + str(sorted(zh_keys - en_keys))
    )


# Fields that reach the generic result renderer (results.js resultFieldLabel /
# formatWorkspaceValue object branch) through structured command results such
# as check-error entries, system status payloads, DVM state, and OPC results.
# Each must have a real translation so the UI never shows a snake_case-derived
# English fallback label under zh-TW.
RESULT_FIELDS = (
    "state",
    "set_bits",
    "complete",
    "displayed",
    "options",
    "drain",
    "max_reads",
    "entries",
    "code",
    "message",
    "valid",
    "reason",
    "auto_range_enabled",
    "is_error",
    "unit",
    # Trigger / generic workspace readback fields that must have real
    # translations rather than snake_case-derived fallbacks.
    "probe_attenuation",
    "bandwidth_limit_enabled",
    "level_volts",
    "greater_than_seconds",
    "less_than_seconds",
    "range_min_seconds",
    "range_max_seconds",
    "low_level_volts",
    "high_level_volts",
    "digital",
    "arm_source",
    "arm_source_kind",
    "arm_digital",
    "trigger_source",
    "trigger_source_kind",
    "trigger_digital",
    "clock_source_kind",
    "clock_digital",
    "data_source",
    "data_source_kind",
    "data_digital",
    "tv_mode",
    "format",
    # Additional workspace fields that must have real translations.
    "file",
    "filename",
    "filenames",
)


def test_smoke_help_documents_measurement_prerequisites() -> None:
    en = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    # Extract the exact value for diagnostics.smokeHelp from each locale.
    en_match = re.search(r'"diagnostics\.smokeHelp"\s*:\s*"(.*?)(?<!\\)"', en)
    zh_match = re.search(r'"diagnostics\.smokeHelp"\s*:\s*"(.*?)(?<!\\)"', zh)
    assert en_match is not None, "missing diagnostics.smokeHelp in locale_en.js"
    assert zh_match is not None, "missing diagnostics.smokeHelp in locale_zh_tw.js"
    en_text = en_match.group(1)
    zh_text = zh_match.group(1)
    # Core prerequisites that must appear in the Smoke help value in both locales.
    for keyword in ("CH1", "VPP/VRMS", "Autoscale", "Single", "Force Trigger"):
        assert keyword in en_text, f"missing '{keyword}' in en smokeHelp"
        assert keyword in zh_text, f"missing '{keyword}' in zh smokeHelp"


def test_result_field_labels_localized() -> None:
    english = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    chinese = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    for field in RESULT_FIELDS:
        assert f'"results.field.{field}":' in english or f'"field.{field}":' in english, field
        assert f'"results.field.{field}":' in chinese or f'"field.{field}":' in chinese, field


def _locale_value(source: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"(.*?)(?<!\\)"', source)
    assert match is not None, f"missing {key}"
    return match.group(1)


def test_tool_neutral_user_facing_copy() -> None:
    english = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    chinese = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")

    assert "WebUI" not in _locale_value(english, "page.title")
    assert "WebUI" not in _locale_value(chinese, "page.title")
    assert _locale_value(english, "live_data.webui_state") == "Tool State"
    assert _locale_value(chinese, "live_data.webui_state") == "工具狀態"

    english_pc_help = _locale_value(english, "pcOutput.helper")
    chinese_pc_help = _locale_value(chinese, "pcOutput.helper")
    assert "WebUI" not in english_pc_help
    assert "WebUI" not in chinese_pc_help
    assert "this tool" in english_pc_help
    assert "本工具" in chinese_pc_help

    assert "WebUI" not in _locale_value(english, "save-export.editor.baseFilenameHelp")
    assert "WebUI" not in _locale_value(chinese, "save-export.editor.baseFilenameHelp")
    assert "WebUI" not in _locale_value(english, "help.measurement-statistics.display-enabled")
    assert "WebUI" not in _locale_value(chinese, "help.measurement-statistics.display-enabled")

    english_storage = _locale_value(english, "save-export.editor.storageNote")
    chinese_storage = _locale_value(chinese, "save-export.editor.storageNote")
    assert "WebUI" not in english_storage
    assert "WebUI" not in chinese_storage
    assert "local" in english_storage
    assert "本機" in chinese_storage

    assert '<title data-i18n="page.title">Scopes Tool</title>' in html
    assert '<span data-i18n="live_data.webui_state">Tool State</span>' in html
    assert '<p class="compact-note" data-i18n="pcOutput.helper">This is the only PC-side output location setting in this tool.' in html


TRIGGER_RESULT_ENUMS = (
    "glitch",
    "runt",
    "transition",
    "delay",
    "setup-hold",
    "edge-burst",
    "tv",
    "pattern",
    "or",
    "edge",
    "channel",
    "digital",
)


def test_trigger_result_enum_labels_localized() -> None:
    english = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    chinese = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    # Presence-only regression: these enum values must not fall back to raw
    # lower-case in the workspace result renderer.
    for value in TRIGGER_RESULT_ENUMS:
        en_key = f'"enum.{value}":'
        zh_key = f'"enum.{value}":'
        assert en_key in english, f"missing enum.{value} in en"
        assert zh_key in chinese, f"missing enum.{value} in zh"
