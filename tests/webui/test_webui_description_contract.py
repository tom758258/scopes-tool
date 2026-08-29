from __future__ import annotations

import re
from pathlib import Path

from scopes_tool_webui.commands import command_catalog

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def _locale_description_ids(text: str) -> set[str]:
    return set(re.findall(r'"description\.([^"]+)":', text))


def _locale_help_keys(text: str) -> set[str]:
    return set(re.findall(r'"help\.([^"]+)":', text))


def test_generic_commands_have_dedicated_descriptions() -> None:
    catalog = command_catalog()
    generic_ids = {entry["id"] for entry in catalog if not entry.get("editor")}
    en_text = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    zh_text = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    en_ids = _locale_description_ids(en_text)
    zh_ids = _locale_description_ids(zh_text)
    missing_en = sorted(generic_ids - en_ids)
    missing_zh = sorted(generic_ids - zh_ids)
    assert not missing_en, f"EN missing description.<id>: {missing_en}"
    assert not missing_zh, f"zh-TW missing description.<id>: {missing_zh}"


def test_generic_boolean_fields_have_help_key() -> None:
    catalog = command_catalog()
    missing: list[str] = []
    for entry in catalog:
        if entry.get("editor"):
            continue
        for field in entry.get("fields", []):
            if field.get("type") == "boolean" and not field.get("help_key"):
                missing.append(f"{entry['id']}.{field['name']}")
    assert not missing, f"generic boolean fields missing help_key: {missing}"


def test_channel_target_fields_have_help_key() -> None:
    catalog = command_catalog()
    missing: list[str] = []
    for entry in catalog:
        if entry.get("category") != "Channel":
            continue
        if entry.get("editor"):
            continue
        for field in entry.get("fields", []):
            if field.get("name") == "channel" and not field.get("help_key"):
                missing.append(entry["id"])
    assert not missing, f"Channel target fields missing help_key: {missing}"
    # also verify locale keys exist
    en_text = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    zh_text = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    assert '"help.channel.target":' in en_text
    assert '"help.channel.target":' in zh_text
