from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_serial_decode_workspace_latest_result() -> None:
    """
    Regression test: serial-decode (presentation_only) workspace must show
    #identity-workspace-result after a successful underlying command read.

    Mirrors the pattern of test_channel_scale_range_workspace_latest_result()
    in test_channel_controls.py.
    """
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import vm from "node:vm";

        const read = (name) => fs.readFileSync(`src/scopes_tool_webui/static/${name}`, "utf8");
        const app = read("app.js");

        // Extract the two helper functions needed from app.js (same slice technique
        // as test_channel_scale_range_workspace_latest_result).
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

        // ── Serial Decode workspace selected ──────────────────────────────────
        let selected = { id: "serial-decode", presentation_only: true };
        let context = { mode: "live", resource: "scope-a", model_id: null };
        let model = "model-a";

        const sandbox = {
          elements,
          document: { createElement: node },
          catalog: { selected: () => selected },
          state: { workspaceResults: new Map() },
          currentModelId: () => model,
          translate: (key) => key,
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
          Object.assign(sandbox, { hasTranslation: () => false }),
        );

        const displayed = () => JSON.stringify(elements.identityWorkspaceContent.children);

        const capture = (command, result) => {
          const job = {
            command,
            status: "completed",
            result: { result: { ...result } },
          };
          sandbox.captureWorkspaceResult(job, sandbox.currentWorkspaceContext(command));
          return job;
        };

        // ── 1. serial-decode selected → identityWorkspace must NOT be hidden ─
        sandbox.renderWorkspace();
        assert.equal(
          elements.identityWorkspace.hidden,
          false,
          "serial-decode: identityWorkspace must not be hidden",
        );
        // Before any capture, shows the empty placeholder.
        assert.ok(
          displayed().includes("workspace.resultEmpty"),
          "serial-decode: before capture, should show resultEmpty",
        );

        // ── 2. Capture serial-mode (completed) → result content rendered ──────
        capture("serial-mode", { mode: "uart" });
        assert.ok(
          !displayed().includes("workspace.resultEmpty"),
          "serial-decode: after serial-mode capture, resultEmpty should be gone",
        );

        // ── 3. Subsequent failure does NOT erase the previous success ─────────
        const failJob = { command: "serial-mode", status: "failed" };
        sandbox.captureWorkspaceResult(failJob, sandbox.currentWorkspaceContext("serial-mode"));
        // The last *successful* result (serial-mode completed) must still show.
        assert.ok(
          !displayed().includes("workspace.resultEmpty"),
          "serial-decode: failure must not erase previous success",
        );

        // ── 4. Capture serial-uart (completed) → rendered as latest ───────────
        capture("serial-uart", { baud_rate: 9600, data_bits: 8, parity: "none" });
        assert.ok(
          !displayed().includes("workspace.resultEmpty"),
          "serial-decode: after serial-uart capture, result should be visible",
        );

        // ── 5. Context isolation: different resource → resultEmpty ────────────
        const submittedContext = sandbox.currentWorkspaceContext("serial-uart");
        context = { mode: "live", resource: "scope-b", model_id: null };
        // Capture with the OLD submitted context — should not pollute new context.
        sandbox.captureWorkspaceResult(
          { command: "serial-uart", status: "completed", result: { baud_rate: 115200 } },
          submittedContext,
        );
        assert.ok(
          displayed().includes("workspace.resultEmpty"),
          "serial-decode: different resource must not show stale result",
        );
        // Restore context.
        context = { mode: "live", resource: "scope-a", model_id: null };

        // ══════════════════════════════════════════════════════════════════════
        // serial-trigger routing coverage
        // ══════════════════════════════════════════════════════════════════════
        selected = { id: "serial-trigger", presentation_only: true };
        sandbox.state.workspaceResults.clear();
        sandbox.renderWorkspace();
        assert.equal(
          elements.identityWorkspace.hidden,
          false,
          "serial-trigger: identityWorkspace must not be hidden",
        );
        capture("serial-mode", { mode: "i2c" });
        assert.ok(
          !displayed().includes("workspace.resultEmpty"),
          "serial-trigger: after serial-mode capture, result should be visible",
        );

        // ══════════════════════════════════════════════════════════════════════
        // serial-lister routing coverage
        // ══════════════════════════════════════════════════════════════════════
        selected = { id: "serial-lister", presentation_only: true };
        sandbox.state.workspaceResults.clear();
        sandbox.renderWorkspace();
        assert.equal(
          elements.identityWorkspace.hidden,
          false,
          "serial-lister: identityWorkspace must not be hidden",
        );
        capture("serial-lister-query", { source: "bus1" });
        assert.ok(
          !displayed().includes("workspace.resultEmpty"),
          "serial-lister: after serial-lister-query capture, result should be visible",
        );

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
