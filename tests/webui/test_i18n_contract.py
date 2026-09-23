from __future__ import annotations

import re
from pathlib import Path

from scopes_tool_webui.commands import command_catalog


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
    # Segmented-capture workspace result fields that must have real
    # translations rather than snake_case-derived fallbacks.
    "output_dir",
    "manifest_path",
    "scpi_log_path",
    "vertical_unit",
    "requested_segments",
    "configured_segments",
    "acquired_segments",
    "exported_segments",
    "initial_mode",
    "final_mode",
    "polling",
    "command",
    "runtime_behavior",
    "error",
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
    "ascii",
    "hex",
    "entered",
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


def test_capture_result_and_prerequisite_labels_are_localized() -> None:
    english = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    chinese = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")

    for key in (
        "results.summary.captureCompleted",
        "results.summary.capturePoints",
        "results.summary.outputFileCount",
        "results.summary.waveformReadTimedOut",
        "results.field.requested_points",
        "results.field.actual_points",
        "results.field.captures",
        "results.field.preamble",
        "results.field.byte_order",
        "results.field.unsigned",
        "capture.existingWaveformRequired",
    ):
        assert f'"{key}"' in english
        assert f'"{key}"' in chinese

    assert "usable waveform data" in english
    assert "可用的波形資料" in chinese


def test_catalog_navigation_entries_are_localized() -> None:
    english = locale_keys("locale_en.js")
    chinese = locale_keys("locale_zh_tw.js")
    missing: list[str] = []

    for command in command_catalog():
        command_key = f"command.{command['id']}"
        if command_key not in english:
            missing.append(f"EN {command_key}")
        if command_key not in chinese:
            missing.append(f"zh-TW {command_key}")

        category_key = f"category.{command['category']}"
        if category_key not in english:
            missing.append(f"EN {category_key}")
        if category_key not in chinese:
            missing.append(f"zh-TW {category_key}")

        group = command.get("group")
        if group:
            group_key = f"group.{group}"
            if group_key not in english:
                missing.append(f"EN {group_key}")
            if group_key not in chinese:
                missing.append(f"zh-TW {group_key}")

    assert not missing, "Unlocalized navigation entries: " + ", ".join(sorted(set(missing)))


def test_catalog_token_options_have_localized_labels() -> None:
    """Lower-case internal enum tokens must never leak into a user-facing selector."""
    english = locale_keys("locale_en.js")
    chinese = locale_keys("locale_zh_tw.js")
    missing: list[str] = []

    def check_fields(scope: str, fields: object) -> None:
        if not isinstance(fields, (list, tuple)):
            return
        for field in fields:
            if not isinstance(field, dict):
                continue
            option_label = field.get("option_label")
            for option in field.get("options") or ():
                if not isinstance(option, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", option):
                    continue
                candidates = [f"enum.{option}"]
                if option_label:
                    candidates = [
                        f"enum.{option_label}.{option}",
                        f"enum.{option_label}",
                        *candidates,
                    ]
                if not any(key in english for key in candidates):
                    missing.append(f"EN {scope}.{field.get('name')}: {option}")
                if not any(key in chinese for key in candidates):
                    missing.append(f"zh-TW {scope}.{field.get('name')}: {option}")

    for command in command_catalog():
        check_fields(command["id"], command.get("fields"))
        sequence = command.get("sequence")
        if isinstance(sequence, dict):
            for action, fields in (sequence.get("parameters") or {}).items():
                check_fields(f"{command['id']}.{action}", fields)

    assert not missing, "Unlocalized lower-case option tokens: " + ", ".join(missing)


def test_english_enum_labels_do_not_start_with_lowercase_text() -> None:
    source = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    failures = [
        f"{key}={value!r}"
        for key, value in re.findall(r'"(enum\.[^"]+)"\s*:\s*"([^"]+)"', source)
        if value and value[0].isascii() and value[0].islower()
    ]
    assert not failures, "English enum labels start lower-case: " + ", ".join(failures)


def test_navigation_labels_use_english_title_case() -> None:
    source = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    stop_words = {"and", "or", "for", "to", "of", "in", "the", "a", "an", "from", "with", "per"}
    failures: list[str] = []

    for match in re.finditer(
        r'"((?:command|group)\.[^"]+)"\s*:\s*"([^"]+)"',
        source,
    ):
        key, value = match.groups()
        words = value.split()
        for index, token in enumerate(words):
            if index > 0 and token.lower() in stop_words:
                continue
            for part in token.strip("()[]{}.,:/").split("-"):
                if not part or not part[0].isalpha() or part.isupper():
                    continue
                if part[0].islower():
                    failures.append(f"{key}={value!r}")
                    break

    assert not failures, "Navigation labels are not title-cased: " + ", ".join(sorted(set(failures)))


def test_math_ui_uses_uppercase_math_terminology() -> None:
    for locale_name in ("locale_en.js", "locale_zh_tw.js"):
        source = (STATIC_ROOT / locale_name).read_text(encoding="utf-8")
        offending = [
            line.strip()
            for line in source.splitlines()
            if re.search(r"\bMath\b", line)
            and '"system.option.ADVMATH"' not in line
        ]
        assert not offending, f"{locale_name} still contains mixed-case Math: {offending}"
