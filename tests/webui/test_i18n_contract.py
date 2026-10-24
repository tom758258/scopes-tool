from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scopes_tool_webui.command_catalog import command_catalog


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


@pytest.mark.frontend_node
def test_locale_initialization_and_switching_with_unavailable_browser_storage() -> None:
    script = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const root = process.argv[1];
        const url = (source) => `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`;
        let source = fs.readFileSync(`${root}/i18n.js`, "utf8");
        for (const name of ["locale_en.js", "locale_zh_tw.js"]) {
          source = source.replace(`/static/${name}`, url(fs.readFileSync(`${root}/${name}`, "utf8")));
        }
        const blocked = () => { throw new Error("browser access denied"); };
        const blockedLanguages = Object.defineProperty({ language: "zh-TW" }, "languages", { get: blocked });
        const blockedNavigator = Object.defineProperties({}, {
          languages: { get: blocked }, language: { get: blocked },
        });
        const cases = [
          ["en", { languages: ["zh-TW"] }, "en"],
          ["zh-TW", { languages: ["en-US"] }, "zh-TW"],
          ...[null, "", "fr", "EN", "zh-tw", "zh_TW", " zh-TW ", "toString", "__proto__"].map(
            (saved) => [saved, { languages: ["zh-TW"] }, "zh-TW"]
          ),
          ...["zh-TW", " ZH_tw ", "zh-TW-x-test", "zh-Hant", "ZH_hAnT-HK"].map(
            (language) => [null, { languages: [language], language: "en" }, "zh-TW"]
          ),
          ...["zh", "zh-CN", "zh-Hans-TW", "zh-twfoo", "zh-hantfoo", "en-US", "fr"].map(
            (language) => [null, { languages: [language, "zh-TW"], language: "zh-TW" }, "en"]
          ),
          [null, { languages: [null, " ", "zh-Hant"], language: "en" }, "zh-TW"],
          [null, { languages: [], language: "zh_TW" }, "zh-TW"],
          [null, { languages: [null, " "], language: "zh-Hant-TW" }, "zh-TW"],
          [null, { languages: "zh-TW", language: "en" }, "en"],
          [null, {}, "en"],
          [null, null, "en"],
          [null, blockedLanguages, "zh-TW"],
          [null, blockedNavigator, "en"],
          [null, { language: "zh-TW" }, "zh-TW", "read"],
          [null, { language: "zh-TW" }, "zh-TW", "write"],
          [null, { language: "zh-TW" }, "zh-TW", "getter"],
          [null, { language: "zh-TW" }, "zh-TW", "missing"],
          [null, null, "en", "navigatorGetter"],
        ];
        globalThis.fetch = blocked;
        globalThis.window = { location: { reload: blocked } };
        for (const [index, [saved, navigatorLike, expected, failure]] of cases.entries()) {
          const writes = [];
          const storage = {
            getItem(key) {
              assert.equal(key, "scopes-tool-webui-locale");
              if (failure === "read") blocked();
              return saved;
            },
            setItem(key, value) {
              if (failure === "write") blocked();
              writes.push([key, value]);
            },
          };
          Object.defineProperty(globalThis, "localStorage", {
            configurable: true,
            get: failure === "getter" ? blocked : () => failure === "missing" ? undefined : storage,
          });
          Object.defineProperty(globalThis, "navigator", {
            configurable: true,
            get: failure === "navigatorGetter" ? blocked : () => navigatorLike,
          });
          const label = { dataset: { i18n: "actions.refresh" } };
          const input = { dataset: { i18nPlaceholder: "actions.refresh" }, value: "unsaved input" };
          const button = { dataset: { i18nTitle: "actions.refresh", i18nAriaLabel: "actions.refresh" },
            setAttribute(name, value) { this[name] = value; } };
          const title = { dataset: { i18n: "page.title" } };
          const doc = new EventTarget();
          doc.documentElement = {};
          doc.querySelectorAll = (selector) => ({
            "[data-i18n]": [label, title], "[data-i18n-placeholder]": [input],
            "[data-i18n-title]": [button], "[data-i18n-aria-label]": [button],
          })[selector];
          doc.querySelector = () => title;
          globalThis.document = doc;
          const events = [];
          doc.addEventListener("localechange", (event) => events.push(event.detail));
          const i18n = await import(`${url(source)}#${index}`);
          assert.equal(i18n.locale(), expected);
          i18n.initializeI18n();
          assert.deepEqual(writes, [], "initial detection must not save a preference");
          const switched = expected === "en" ? "zh-TW" : "en";
          for (const [step, language] of [expected, switched, expected].entries()) {
            if (step > 0) i18n.setLocale(language);
            assert.equal(i18n.locale(), language);
            assert.equal(doc.documentElement.lang, language);
            assert.equal(label.textContent, i18n.translate("actions.refresh"));
            assert.equal(input.placeholder, label.textContent);
            assert.equal(button.title, label.textContent);
            assert.equal(button["aria-label"], label.textContent);
            assert.equal(doc.title, i18n.translate("page.title"));
            assert.equal(input.value, "unsaved input");
          }
          assert.deepEqual(events, [expected, switched, expected]);
          assert.deepEqual(writes, ["write", "getter", "missing"].includes(failure) ? [] : [
            ["scopes-tool-webui-locale", switched], ["scopes-tool-webui-locale", expected],
          ]);
        }
    '''
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(STATIC_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


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
    for token in ("Tool", "State"):
        assert token in _locale_value(english, "live_data.webui_state")
    for token in ("工具", "狀態"):
        assert token in _locale_value(chinese, "live_data.webui_state")

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
    assert 'data-i18n="live_data.webui_state"' in html
    assert 'data-i18n="pcOutput.helper"' in html


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

    def check_options(scope: str, field: dict, options: object) -> None:
        option_label = field.get("option_label")
        for option in options or ():
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

    def check_fields(scope: str, fields: object) -> None:
        if not isinstance(fields, (list, tuple)):
            return
        for field in fields:
            if not isinstance(field, dict):
                continue
            check_options(scope, field, field.get("options"))
            for mode, options in (field.get("mode_options") or {}).items():
                check_options(f"{scope}[{mode}]", field, options)

    for command in command_catalog():
        check_fields(command["id"], command.get("fields"))

        fields_by_name = {
            field["name"]: field
            for field in command.get("fields") or ()
            if isinstance(field, dict) and field.get("name")
        }
        presentation = command.get("presentation") or {}
        action_field = presentation.get("action_field")
        if action_field and presentation.get("action_choices"):
            field = fields_by_name.get(action_field, {"name": action_field})
            check_options(command["id"], field, presentation["action_choices"])

        for model_id, model in (presentation.get("models") or {}).items():
            for field_name, override in (model.get("fields") or {}).items():
                if not isinstance(override, dict) or "options" not in override:
                    continue
                field = dict(fields_by_name.get(field_name, {"name": field_name}))
                field.update({key: value for key, value in override.items() if key == "option_label"})
                check_options(f"{command['id']}[{model_id}]", field, override.get("options"))

        sequence = command.get("sequence")
        if isinstance(sequence, dict):
            for action, fields in (sequence.get("parameters") or {}).items():
                check_fields(f"{command['id']}.{action}", fields)

    assert not missing, "Unlocalized lower-case option tokens: " + ", ".join(missing)

def test_reported_workflow_and_math_tokens_have_user_facing_labels() -> None:
    english_source = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    chinese_source = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")

    for token in (
        "peak-to-peak",
        "abs-max",
        "decibel",
        "rectangular",
        "hanning",
        "flattop",
        "bharris",
        "bartlett",
        "composite",
        "math1",
        "math2",
        "math3",
    ):
        en_value = _locale_value(english_source, f"enum.{token}")
        zh_value = _locale_value(chinese_source, f"enum.{token}")
        assert en_value != token, token
        assert zh_value != token, token
        assert not en_value[0].islower(), f"enum.{token}={en_value!r}"



def test_math_user_facing_copy_uses_consistent_math_casing() -> None:
    failures: list[str] = []
    value_pattern = re.compile(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
    for filename in ("locale_en.js", "locale_zh_tw.js"):
        source = (STATIC_ROOT / filename).read_text(encoding="utf-8")
        for key, value in value_pattern.findall(source):
            if key == "system.option.ADVMATH":
                continue
            if re.search(r"\b(?:Math|math)\b", value):
                failures.append(f"{filename}:{key}={value!r}")
    assert not failures, "Inconsistent MATH casing: " + ", ".join(failures)

def test_english_enum_labels_do_not_start_with_lowercase_text() -> None:
    source = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    failures = [
        f"{key}={value!r}"
        for key, value in re.findall(r'"(enum\.[^"]+)"\s*:\s*"([^"]+)"', source)
        if value and value[0].isascii() and value[0].islower()
    ]
    assert not failures, "English enum labels start lower-case: " + ", ".join(failures)
