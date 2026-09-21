from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for frontend behavior checks",
)
def test_serial_decode_workspace_latest_result() -> None:
    """
    Regression test: Serial workspaces (Decode, Trigger, Lister) must show
    #identity-workspace-result for their underlying commands and render
    scoped enum labels instead of raw tokens.
    """
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import vm from "node:vm";

        const read = (name) => fs.readFileSync(`src/scopes_tool_webui/static/${name}`, "utf8");
        const app = read("app.js");

        const functions = [
          app.slice(app.indexOf("function renderWorkspace()"), app.indexOf("async function updateHealth()")),
          app.slice(app.indexOf("function currentWorkspaceContext("), app.indexOf("function isCurrentEditorJob(")),
        ].join("\n");

        const node = () => ({
          children: [], hidden: false,
          replaceChildren() { this.children = []; },
          append(...children) { this.children.push(...children); },
        });

        const elements = { identityWorkspace: node(), identityWorkspaceContent: node() };

        let selected = { id: "serial-decode", presentation_only: true };
        let context = { mode: "live", resource: "scope-a", model_id: null };
        let model = "model-a";

        const enTranslations = vm.runInNewContext(
          read("locale_en.js").replace("export const en =", "const en =") + "\nen;"
        );
        const zhTranslations = vm.runInNewContext(
          read("locale_zh_tw.js").replace("export const zhTW =", "const zhTW =") + "\nzhTW;"
        );

        let activeTranslations = enTranslations;

        const sandbox = {
          elements,
          document: { createElement: node },
          catalog: { selected: () => selected },
          state: { workspaceResults: new Map() },
          currentModelId: () => model,
          translate: (key) => activeTranslations[key] || key,
          hasTranslation: (key) => key in activeTranslations,
          get context() { return context; },
        };
        vm.createContext(sandbox);
        vm.runInContext(
          read("execution-context.js")
            .replace(/^import[^\n]*\r?\n/gm, "")
            .replaceAll("export function ", "function ")
          + read("results.js")
            .replace(/^import[^\n]*\r?\n/gm, "")
            .replaceAll("export function ", "function ")
          + functions,
          sandbox,
        );

        const displayed = () => JSON.stringify(elements.identityWorkspaceContent.children);

        const capture = (command, result) => {
          const job = {
            command,
            status: "completed",
            result: { result },
          };
          sandbox.captureWorkspaceResult(job, sandbox.currentWorkspaceContext(command));
          return job;
        };

        // Serial Decode
        selected = { id: "serial-decode", presentation_only: true };
        sandbox.renderWorkspace();
        assert.equal(elements.identityWorkspace.hidden, false, "serial-decode must not be hidden");
        assert.ok(
          displayed().includes(activeTranslations["workspace.resultEmpty"]),
          "initially empty",
        );

        // Capture production-like nested serial-uart result
        capture("serial-uart", {
          uart: {
            bus: 1,
            mode: "uart",
            rx_source: "channel1",
            tx_source: "channel1",
            baud_rate: 9600,
            data_bits: 8,
            parity: "none",
            polarity: "high",
            bit_order: "msb-first",
          },
        });

        assert.ok(displayed().includes("9600"), "baud rate 9600 rendered");
        assert.ok(displayed().includes("MSB First"), "bit_order translated to MSB First");
        assert.ok(displayed().includes("None"), "parity translated to None");
        assert.ok(displayed().includes("High"), "polarity translated to High");
        assert.ok(!displayed().includes('"msb-first"'), "raw token msb-first not displayed");

        // Serial Trigger
        selected = { id: "serial-trigger", presentation_only: true };
        sandbox.state.workspaceResults.clear();
        sandbox.renderWorkspace();
        assert.equal(elements.identityWorkspace.hidden, false, "serial-trigger must not be hidden");

        // Capture production-like nested serial-trigger-uart result
        capture("serial-trigger-uart", {
          trigger: {
            protocol: "uart",
            bus: 1,
            mode: "uart",
            type: "rx-data",
            data: 65,
            qualifier: "equal",
          },
        });

        assert.ok(displayed().includes("RX Data"), "type translated to RX Data");
        assert.ok(displayed().includes("Equal"), "qualifier translated to Equal in EN");
        assert.ok(!displayed().includes('"rx-data"'), "raw token rx-data not displayed");

        // Test Traditional Chinese qualifier translation
        activeTranslations = zhTranslations;
        sandbox.renderWorkspace();
        assert.ok(displayed().includes("相等"), "qualifier translated to 相等 in zh-TW");
        activeTranslations = enTranslations;

        // Serial Lister: all four underlying commands must update the latest result
        selected = { id: "serial-lister", presentation_only: true };
        sandbox.state.workspaceResults.clear();
        sandbox.renderWorkspace();
        assert.equal(elements.identityWorkspace.hidden, false, "serial-lister must not be hidden");

        // A. Read Lister settings (serial-lister-query)
        capture("serial-lister-query", {
          lister: {
            display: "bus1",
            reference: "trigger",
          },
        });
        assert.ok(displayed().includes("Bus 1"), "lister display translated to Bus 1");
        assert.ok(displayed().includes("Trigger"), "lister reference translated to Trigger");
        assert.ok(!displayed().includes('"bus1"'), "raw token bus1 not displayed");

        // B. Apply Display (serial-lister-display)
        capture("serial-lister-display", {
          display: {
            display: "bus2",
          },
        });
        assert.ok(displayed().includes("Bus 2"), "lister display updated to Bus 2");

        // C. Apply Reference (serial-lister-reference)
        capture("serial-lister-reference", {
          reference: {
            reference: "previous",
          },
        });
        assert.ok(displayed().includes("Previous Row"), "lister reference updated to Previous Row");

        // D. Export CSV (serial-lister-export)
        capture("serial-lister-export", {
          output: "lister_capture.csv",
        });
        assert.ok(displayed().includes("lister_capture.csv"), "export result includes filename");

        console.log(JSON.stringify({ ok: true }));
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    import json
    assert json.loads(completed.stdout) == {"ok": True}
