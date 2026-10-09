from __future__ import annotations

import re
import shutil
import subprocess
import textwrap

import pytest

from tests.webui._frontend_state_test_support import (
    STATIC_ROOT,
    read_static,
)


RESULT_FAKE_DOM_HARNESS = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag) { this.tagName = tag; this.children = []; this.className = ""; this.textContent = ""; }
          append(...nodes) { this.children.push(...nodes); }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_system_result_summaries_localize_options_and_unknown_operation_bits() -> None:
    results_path = STATIC_ROOT / "results.js"
    chinese = read_static("locale_zh_tw.js")
    english = read_static("locale_en.js")
    assert '"system.option.MEMUP": "記憶體升級",' in chinese
    assert '"system.option.WAVEGEN": "波形產生器",' in chinese
    assert '"system.option.AERO": "MIL-1553/ARINC 429 串列",' in chinese
    assert '"system.option.USF": "USB 2.0 低速／全速",' in chinese
    assert '"system.option.AERO": "MIL-1553/ARINC 429 Serial",' in english
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const translations = {
          "system.option.MEMUP": "記憶體升級",
          "system.option.WAVEGEN": "波形產生器",
          "system.option.MSO": "混合訊號示波器",
          "system.option.BW20": "頻寬",
          "system.option.PLUS": "增強功能",
          "system.option.AERO": "MIL-1553/ARINC 429 串列",
          "system.option.USF": "USB 2.0 低速／全速",
          "system.option.D3000PWRA": "電源供應器測試軟體",
          "enum.invalid DVM sentinel": "DVM 讀值無效",
        };
        const source = [
          `const translations = ${JSON.stringify(translations)};`,
          "const hasTranslation = (key) => key in translations;",
          "const translate = (key) => translations[key] ?? key;",
          fs.readFileSync(process.argv[1], "utf8").replace(/^import[^\n]*\r?\n/gm, ""),
          "globalThis.resultsApi = { formatSystemOptionsSummary, formatSystemOperationStatusSummary, formatWorkspaceValue };",
        ].join("\n");
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { formatSystemOptionsSummary, formatSystemOperationStatusSummary, formatWorkspaceValue } = globalThis.resultsApi;

        assert.equal(
          formatSystemOptionsSummary({ options: [0, "MEMUP", "WAVEGEN", "FPGAX"] }),
          "記憶體升級 — MEMUP; 波形產生器 — WAVEGEN; FPGAX",
        );
        assert.equal(
          formatSystemOptionsSummary({
            options: ["MSO", "BW20", "PLUS", "AERO", "USF", "D3000PWRA", "FPGAX"],
          }),
          "混合訊號示波器 — MSO; 頻寬 — BW20; 增強功能 — PLUS; "
          + "MIL-1553/ARINC 429 串列 — AERO; USB 2.0 低速／全速 — USF; "
          + "電源供應器測試軟體 — D3000PWRA; FPGAX",
        );
        assert.equal(formatSystemOperationStatusSummary({ set_bits: [12] }), "Bit 12");
        assert.equal(formatSystemOperationStatusSummary({ set_bits: [12] }).includes("system.operationStatus.bit.12"), false);
        assert.equal(
          formatWorkspaceValue("reason", "invalid DVM sentinel"),
          "DVM 讀值無效",
        );
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(results_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_cursor_mode_structured_result_uses_friendly_labels() -> None:
    results_path = STATIC_ROOT / "results.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const translations = {
          "enum.cursor-mode.MAN": "Manual",
          "enum.cursor-mode.MANual": "Manual",
          "enum.cursor-mode.MANUAL": "Manual",
          "enum.cursor-mode.OFF": "Off",
        };
        const source = [
          `const translations = ${JSON.stringify(translations)};`,
          "const hasTranslation = (key) => key in translations;",
          "const translate = (key) => translations[key] ?? key;",
          fs.readFileSync(process.argv[1], "utf8").replace(/^import[^\n]*\r?\n/gm, ""),
          "globalThis.resultsApi = { formatWorkspaceValue };",
        ].join("\n");
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { formatWorkspaceValue } = globalThis.resultsApi;

        assert.equal(formatWorkspaceValue("mode", "MAN", "cursor"), "Manual");
        assert.equal(formatWorkspaceValue("mode", "MANual", "cursor"), "Manual");
        assert.equal(formatWorkspaceValue("mode", "MANUAL", "cursor"), "Manual");
        assert.equal(formatWorkspaceValue("mode", "OFF", "cursor"), "Off");
        assert.equal(formatWorkspaceValue("mode", "TRACK", "cursor"), "TRACK");
        assert.equal(formatWorkspaceValue("mode", "MAN", null), "MAN");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(results_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_mode_structured_result_prefers_scoped_labels() -> None:
    results_path = STATIC_ROOT / "results.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const translations = {
          "enum.trigger-mode.delay": "邊緣後邊緣",
          "enum.delay": "延遲",
          "enum.trigger-mode.pattern": "碼型",
          "enum.pattern": "模式",
        };
        const source = [
          `const translations = ${JSON.stringify(translations)};`,
          "const hasTranslation = (key) => key in translations;",
          "const translate = (key) => translations[key] ?? key;",
          fs.readFileSync(process.argv[1], "utf8").replace(/^import[^\n]*\r?\n/gm, ""),
          "globalThis.resultsApi = { formatWorkspaceValue };",
        ].join("\n");
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { formatWorkspaceValue } = globalThis.resultsApi;

        assert.equal(formatWorkspaceValue("mode", "delay", "trigger"), "邊緣後邊緣");
        assert.equal(formatWorkspaceValue("mode", "pattern", "trigger"), "碼型");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(results_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_serial_result_uses_scoped_labels() -> None:
    source = read_static("results.js")
    commands_block = source.split("const SEARCH_RESULT_COMMANDS", 1)[1].split("]);", 1)[0]
    for command_id in (
        "search-state",
        "search-mode",
        "search-count",
        "search-event",
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    ):
        assert f'"{command_id}"' in commands_block, command_id
    assert "SEARCH_RESULT_COMMANDS.has(job.command)" in source

    results_path = STATIC_ROOT / "results.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const translations = {
          "results.field.search_enabled": "搜尋狀態",
          "results.field.search_mode": "搜尋模式",
          "results.field.selected": "已選取",
          "status.enabled": "已啟用",
          "status.disabled": "已停用",
          "status.yes": "是",
          "status.no": "否",
          "enum.search-mode.serial1": "串列 1",
          "enum.serial-search-can-mode.data": "資料",
          "enum.serial-search-can-id-mode.standard": "標準",
        };
        const source = [
          `const translations = ${JSON.stringify(translations)};`,
          "const hasTranslation = (key) => key in translations;",
          "const translate = (key) => translations[key] ?? key;",
          fs.readFileSync(process.argv[1], "utf8").replace(/^import[^\n]*\r?\n/gm, ""),
          "globalThis.resultsApi = { formatWorkspaceValue, resultFieldLabel };",
        ].join("\n");
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { formatWorkspaceValue, resultFieldLabel } = globalThis.resultsApi;

        assert.equal(resultFieldLabel("search_enabled", "serial-search-can"), "搜尋狀態");
        assert.equal(resultFieldLabel("selected", "serial-search-can"), "已選取");
        assert.equal(formatWorkspaceValue("search_enabled", false, "serial-search-can"), "已停用");
        assert.equal(formatWorkspaceValue("selected", false, "serial-search-can"), "否");
        assert.equal(formatWorkspaceValue("mode", "data", "serial-search-can"), "資料");
        assert.equal(formatWorkspaceValue("id_mode", "standard", "serial-search-can"), "標準");
        assert.equal(formatWorkspaceValue("search_mode", "serial1", "serial-search-can"), "串列 1");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(results_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_wgen_aggregate_result_uses_wgen_labels() -> None:
    results_path = STATIC_ROOT / "results.js"
    script = textwrap.dedent(
        RESULT_FAKE_DOM_HARNESS
        + r'''
        const translationsEN = {
          "results.field.function": "Math function",
          "wgen.state.output": "WGEN output",
          "wgen.state.function": "WGEN function",
          "wgen.state.frequency": "WGEN frequency",
          "wgen.state.amplitude": "WGEN amplitude",
          "wgen.state.offset": "WGEN offset",
          "wgen.state.load": "WGEN load",
          "enum.wgen-function.sine": "Sine",
          "enum.wgen-load.fifty": "50 Ω",
          "status.disabled": "Disabled",
        };
        const translationsZH = {
          "wgen.state.output": "輸出",
          "wgen.state.function": "波形",
          "wgen.state.load": "負載",
          "enum.wgen-function.sine": "正弦波",
          "enum.wgen-load.fifty": "50 Ω",
          "status.disabled": "已停用",
        };
        const source = [
          `const translationsEN = ${JSON.stringify(translationsEN)};`,
          `const translationsZH = ${JSON.stringify(translationsZH)};`,
          "let active = translationsEN;",
          "const hasTranslation = (key) => key in active;",
          "const translate = (key) => active[key] ?? key;",
          "const formatEngineering = globalThis.formatEngineering;",
          fs.readFileSync(process.argv[1], "utf8").replace(/^import[^\n]*\r?\n/gm, ""),
          "globalThis.resultsApi = { renderWorkspaceResult, setActive: (map) => { active = map; } };",
        ].join("\n");
        const liveData = fs.readFileSync(process.argv[2], "utf8").replace(/^export /gm, "")
          + "\nglobalThis.formatEngineering = formatEngineering;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(liveData)}`);
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { renderWorkspaceResult, setActive } = globalThis.resultsApi;
        const rowsOf = (container) => Object.fromEntries(
          container.children.map((row) => [row.children[1].textContent, row.children[0].textContent]),
        );

        const container = new FakeNode("div");
        renderWorkspaceResult(container, {
          command: "wgen-query",
          status: "completed",
          result: {
            result: {
              wgen: {
                enabled: false,
                function: "sine",
                function_scpi: "SINusoid",
                function_raw: "SIN",
                frequency_hz: 1000,
                amplitude_volts: 0.5,
                offset_volts: 0,
                load: "fifty",
                load_scpi: "ONEMeg",
                load_raw: "FIFT",
              },
            },
          },
        }, { mode: "simulate" });
        const rows = rowsOf(container);
        assert.equal(rows["WGEN function"], "Sine");
        assert.equal(rows["WGEN load"], "50 Ω");
        assert.equal(rows["WGEN output"], "Disabled");
        assert.equal(rows["WGEN frequency"], "1.00 kHz");
        assert.equal(rows["WGEN amplitude"], "500 mVpp");
        assert.equal(rows["WGEN offset"], "0.00 V");
        assert.ok(!Object.keys(rows).some((label) => label.includes("Math")));
        assert.ok(!Object.keys(rows).some((label) => /scpi|raw/i.test(label)));

        // Setter results share the WGEN presentation context.
        const setterContainer = new FakeNode("div");
        renderWorkspaceResult(setterContainer, {
          command: "wgen-function",
          status: "completed",
          result: {
            result: {
              function: { function: "sine", function_scpi: "SIN", function_raw: "SIN" },
            },
          },
        }, { mode: "simulate" });
        const setterRows = rowsOf(setterContainer);
        assert.equal(setterRows["WGEN function"], "Sine");
        assert.ok(!Object.keys(setterRows).some((label) => /scpi|raw/i.test(label)));

        // Traditional Chinese labels resolve through the same context.
        setActive(translationsZH);
        const zhContainer = new FakeNode("div");
        renderWorkspaceResult(zhContainer, {
          command: "wgen-query",
          status: "completed",
          result: {
            result: {
              wgen: { enabled: false, function: "sine", load: "fifty" },
            },
          },
        }, { mode: "simulate" });
        const zhRows = rowsOf(zhContainer);
        assert.equal(zhRows["波形"], "正弦波");
        assert.equal(zhRows["輸出"], "已停用");
        assert.equal(zhRows["負載"], "50 Ω");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(results_path), str(STATIC_ROOT / "live-data.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_demo_workspace_result_uses_demo_presentation() -> None:
    results_path = STATIC_ROOT / "results.js"
    script = textwrap.dedent(
        RESULT_FAKE_DOM_HARNESS
        + r'''
        const translations = {
          "results.field.function": "Math function",
          "demo.state.output": "DEMO output",
          "demo.state.function": "DEMO function",
          "demo.state.phase": "DEMO phase",
          "enum.demo-function.sine": "Sine",
          "status.disabled": "Disabled",
        };
        const source = [
          `const translations = ${JSON.stringify(translations)};`,
          "const hasTranslation = (key) => key in translations;",
          "const translate = (key) => translations[key] ?? key;",
          "const formatEngineering = globalThis.formatEngineering;",
          fs.readFileSync(process.argv[1], "utf8").replace(/^import[^\n]*\r?\n/gm, ""),
          "globalThis.resultsApi = { renderWorkspaceResult };",
        ].join("\n");
        const liveData = fs.readFileSync(process.argv[2], "utf8").replace(/^export /gm, "")
          + "\nglobalThis.formatEngineering = formatEngineering;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(liveData)}`);
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { renderWorkspaceResult } = globalThis.resultsApi;
        const rowsOf = (container) => Object.fromEntries(
          container.children.map((row) => [row.children[1].textContent, row.children[0].textContent]),
        );

        const container = new FakeNode("div");
        renderWorkspaceResult(container, {
          command: "demo-query",
          status: "completed",
          result: {
            result: {
              demo: {
                enabled: false,
                output_raw: "0",
                function: "sine",
                function_scpi: "SIN",
                function_raw: "SIN",
                phase_degrees: 90,
                phase_raw: "90",
              },
            },
          },
        }, { mode: "simulate" });
        const rows = rowsOf(container);
        assert.equal(rows["DEMO function"], "Sine");
        assert.equal(rows["DEMO output"], "Disabled");
        assert.equal(rows["DEMO phase"], "90");
        assert.ok(!Object.keys(rows).some((label) => label.includes("Math")));
        assert.ok(!Object.keys(rows).some((label) => /scpi|raw/i.test(label)));

        // Setter results share the DEMO presentation context.
        const setterContainer = new FakeNode("div");
        renderWorkspaceResult(setterContainer, {
          command: "demo-function",
          status: "completed",
          result: {
            result: {
              function: { function: "sine", function_scpi: "SIN", function_raw: "SIN" },
            },
          },
        }, { mode: "simulate" });
        const setterRows = rowsOf(setterContainer);
        assert.equal(setterRows["DEMO function"], "Sine");
        assert.ok(!Object.keys(setterRows).some((label) => /scpi|raw/i.test(label)));
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(results_path), str(STATIC_ROOT / "live-data.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

def test_summary_uses_only_scopes_supported_states() -> None:
    english = read_static("locale_en.js")

    assert '"device.summary.live": "{{mode}} / VISA resource: {{resource}} / {{detection}}"' in english
    assert '"device.detection.notScanned": "Detection status: not scanned"' in english
    assert '"device.detection.scanFailed": "Detection status: scan failed: {{error}}"' in english
    assert '"device.summary.planning": "{{mode}} / Planning model: {{model}} / Real VISA resource: not used"' in english
    assert "Expected Model guard" not in english
    assert "Connection scope" not in english

def test_command_help_and_common_result_labels_are_localized() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    for key in (
        "description.action.apply",
        "description.timebase-scale",
        "description.timebase-reference",
        "form.greaterThan",
        "help.pairs",
        "help.timebase.seconds_per_division",
        "help.timebase.position_seconds",
        "help.timebase.reference",
        "results.field.seconds_per_division",
        "results.field.planned_scpi",
    ):
        assert f'"{key}":' in english
        assert f'"{key}":' in chinese

def test_fft_result_field_localization() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    def locale_value(source: str, key: str) -> str:
        match = re.search(
            rf'"{re.escape(key)}":\s*"((?:[^"\\]|\\.)*)"',
            source,
        )
        if not match:
            raise AssertionError(f"locale key not found: {key}")
        return match.group(1)

    for key in (
        "results.field.operation_canonical",
        "results.field.start_hz",
        "results.field.stop_hz",
        "results.field.gate",
        "results.field.phase_reference",
        "results.field.detection_type",
        "results.field.detection_points",
        "results.field.bin_size_hz",
        "results.field.sample_rate_hz",
        "results.field.resolution_bandwidth_hz",
    ):
        assert f'"{key}":' in english, key
        assert f'"{key}":' in chinese, key

    # Semantic assertions: canonical operation must contain FFT and differ from generic operation
    en_op_canonical = locale_value(english, "results.field.operation_canonical")
    zh_op_canonical = locale_value(chinese, "results.field.operation_canonical")
    assert "FFT" in en_op_canonical, f"EN operation_canonical missing FFT: {en_op_canonical}"
    assert "FFT" in zh_op_canonical, f"ZH operation_canonical missing FFT: {zh_op_canonical}"

    en_op_generic = locale_value(english, "results.field.operation")
    zh_op_generic = locale_value(chinese, "results.field.operation")
    assert en_op_canonical != en_op_generic, "operation_canonical must differ from generic operation"
    assert zh_op_canonical != zh_op_generic, "operation_canonical must differ from generic operation"

    # Frequency-domain labels must retain Hz
    for key in (
        "results.field.start_hz",
        "results.field.stop_hz",
        "results.field.bin_size_hz",
        "results.field.sample_rate_hz",
        "results.field.resolution_bandwidth_hz",
    ):
        en_label = locale_value(english, key)
        zh_label = locale_value(chinese, key)
        assert "Hz" in en_label, f"EN {key} missing Hz: {en_label}"
        assert "Hz" in zh_label, f"ZH {key} missing Hz: {zh_label}"

    # Gate should contain FFT when available (optional but preferred)
    en_gate = locale_value(english, "results.field.gate")
    zh_gate = locale_value(chinese, "results.field.gate")
    assert "FFT" in en_gate, f"EN gate missing FFT: {en_gate}"
    assert "FFT" in zh_gate, f"ZH gate missing FFT: {zh_gate}"

def test_advanced_math_form_and_result_localization() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    for key in (
        "command.math-transform",
        "command.math-filter",
        "command.math-visualization",
        "description.math-transform",
        "description.math-filter",
        "description.math-visualization",
        "field.input_offset",
        "field.gain",
        "field.linear_offset",
        "field.cutoff_hz",
        "field.average_count",
        "field.smooth_points",
        "field.measurement_slot",
        "help.advanced-math.source",
        "help.math-visualization.measurement_slot",
        "results.field.input_offset",
        "results.field.cutoff_hz",
        "results.field.measurement_slot",
    ):
        assert f'"{key}":' in english, key
        assert f'"{key}":' in chinese, key
