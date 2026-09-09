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
