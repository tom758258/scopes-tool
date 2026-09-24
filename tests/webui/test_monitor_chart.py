from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


CHART_SOURCE = Path(__file__).resolve().parents[2] / "src" / "scopes_tool_webui" / "static" / "monitor-chart.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_monitor_projection_and_exact_retained_lookup() -> None:
    script = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const source = fs.readFileSync(process.argv[1], "utf8");
        const { projectMonitorChunks, lookupMonitorSample } = await import(
          `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`
        );
        const values = Array.from({ length: 250000 }, (_, index) => Math.sin(index / 20));
        values[100003] = -12;
        values[100004] = 15;
        const large = [{
          capture_index: 1, global_start_index: 0,
          time_s: Array.from({ length: values.length }, (_, index) => index * 1e-8),
          channels: { CH1: { values, unit: "V" } },
        }];
        const projected = projectMonitorChunks(large, 800);
        const points = projected.channels.get("CH1").flat();
        assert.ok(points.length <= 800 * 4);
        assert.ok(points.some(([index, value]) => index === 100003 && value === -12));
        assert.ok(points.some(([index, value]) => index === 100004 && value === 15));
        assert.equal(points[0][0], 0);
        assert.equal(points.at(-1)[0], 249999);

        const chunks = [
          { capture_index: 145, global_start_index: 145000, time_s: [0, 1e-8],
            channels: { CH1: { values: [1, 2], unit: "V" } } },
          { capture_index: 146, global_start_index: 145002, time_s: [0, 3.82e-6],
            channels: {
              CH1: { values: [0.5, 0.124], unit: "V" },
              CH2: { values: [0.2, -0.031], unit: "V" },
            } },
        ];
        const segments = projectMonitorChunks(chunks, 800).channels.get("CH1");
        assert.equal(segments.length, 2);
        assert.deepEqual(segments.map((segment) => segment.map(([index]) => index)),
          [[145000, 145001], [145002, 145003]]);
        assert.deepEqual(lookupMonitorSample(chunks, 145003), {
          captureIndex: 146, globalIndex: 145003, localIndex: 1, time: 3.82e-6,
          channels: {
            CH1: { value: 0.124, unit: "V" },
            CH2: { value: -0.031, unit: "V" },
          },
        });
        chunks.shift();
        assert.equal(lookupMonitorSample(chunks, 145001), null);
        assert.equal(projectMonitorChunks(chunks, 800).minX, 145002);
    '''
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script), str(CHART_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_stationary_hover_resolves_current_raw_sample_after_redraw() -> None:
    script = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const source = fs.readFileSync(process.argv[1], "utf8");
        const { MonitorChart } = await import(
          `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`
        );
        const listeners = {};
        const context = {
          setTransform() {}, clearRect() {}, beginPath() {},
          moveTo() {}, lineTo() {}, stroke() {},
        };
        const canvas = {
          width: 0, height: 0,
          addEventListener(name, handler) { listeners[name] = handler; },
          removeEventListener(name) { delete listeners[name]; },
          getContext() { return context; },
          getBoundingClientRect() { return { left: 0, width: 100, height: 100 }; },
        };
        const crosshair = { hidden: true, style: {} };
        const tooltip = { hidden: true, style: {}, offsetWidth: 30, textContent: "" };
        let chunks = [{ capture_index: 1, global_start_index: 0, time_s: [0, 1],
          channels: { CH1: { values: [1, 2], unit: "V" } } }];
        const chart = new MonitorChart(canvas, crosshair, tooltip, () => chunks,
          (key, args) => `${key}: ${args.value}`);
        chart.draw();
        listeners.mousemove({ clientX: 92 });
        assert.equal(crosshair.hidden, false);
        assert.equal(tooltip.hidden, false);
        assert.ok(tooltip.textContent.includes("CH1: 2 V"));

        chunks = [{ capture_index: 2, global_start_index: 0, time_s: [0, 1],
          channels: { CH1: { values: [3, 4], unit: "V" } } }];
        chart.draw();
        assert.equal(crosshair.hidden, false);
        assert.equal(tooltip.hidden, false);
        assert.ok(tooltip.textContent.includes("CH1: 4 V"));
        assert.ok(tooltip.textContent.includes("workflow.monitor.hoverCapture: 2"));
        assert.equal(tooltip.textContent.includes("CH1: 2 V"), false);
        chart.dispose();
    '''
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script), str(CHART_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
