"""Focused no-hardware coverage for appearance and supported-device display."""

import re
import shutil
import subprocess
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scopes_tool_webui.app import app
from scopes_tool_webui.commands import model_catalog
from scopes_tool_webui import supported_devices


STATIC = Path(__file__).resolve().parents[2] / "src/scopes_tool_webui/static"


def run_node(script: str) -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required")
    setup = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import vm from "node:vm";
        const root = process.argv[1];
        const read = (name) => fs.readFileSync(`${root}/${name}`, "utf8");
        const url = (source) => `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`;
        class Node {
          constructor() { this.dataset = {}; this.attributes = {}; this.listeners = {}; this.children = []; }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          removeEventListener(name, handler) { this.listeners[name] = this.listeners[name].filter((item) => item !== handler); }
          emit(name, event = {}) { this.listeners[name]?.forEach((handler) => handler(event)); }
          dispatchEvent(event) { this.emit(event.type, event); }
          setAttribute(name, value) { this.attributes[name] = value; }
          focus() { this.focused = true; }
          append(child) { this.children.push(child); }
          replaceChildren() { this.children = []; }
        }
        globalThis.localStorage = { getItem() { return "en"; }, setItem() {} };
        globalThis.CustomEvent = class { constructor(type) { this.type = type; } };
        const doc = new Node();
        doc.documentElement = new Node();
        doc.querySelectorAll = () => [];
        doc.querySelector = () => null;
        doc.createElement = () => new Node();
        globalThis.document = doc;
        let i18nSource = read("i18n.js");
        for (const file of ["locale_en.js", "locale_zh_tw.js"]) {
          i18nSource = i18nSource.replace(`/static/${file}`, url(read(file)));
        }
        const i18nUrl = url(i18nSource);
        const { setLocale, translate } = await import(i18nUrl);
        const load = (name) => import(url(read(name).replace("/static/i18n.js", i18nUrl)));
    '''
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(setup + script), str(STATIC)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_theme_cycle_cookie_system_changes_and_localization() -> None:
    run_node(r'''
        const { initializeThemeUi, readSavedThemePreference } = await load("theme_ui.js");
        const button = new Node(), label = new Node(), mediaQuery = new Node();
        mediaQuery.matches = true;
        doc.cookie = "unrelated=value";
        const ui = initializeThemeUi({button, label, documentElement: doc.documentElement, cookieDocument: doc, mediaQuery});
        assert.equal(ui.getPreference(), "system");
        assert.equal(doc.documentElement.dataset.theme, "dark");
        assert.equal(label.textContent, "System");
        mediaQuery.matches = false; mediaQuery.emit("change");
        assert.equal(doc.documentElement.dataset.theme, "light");
        for (const [preference, effective, destination] of [["light", "light", "Dark"], ["dark", "dark", "System"], ["system", "light", "Light"]]) {
          button.emit("click");
          assert.equal(ui.getPreference(), preference);
          assert.equal(doc.documentElement.dataset.theme, effective);
          assert.equal(readSavedThemePreference(doc), preference);
          assert.ok(doc.cookie.includes("Max-Age=31536000; Path=/; SameSite=Lax"));
          assert.equal(button.attributes.title, `Switch theme to ${destination}`);
          assert.equal(button.attributes["aria-label"], button.attributes.title);
          if (preference !== "system") {
            mediaQuery.matches = !mediaQuery.matches; mediaQuery.emit("change");
            assert.equal(doc.documentElement.dataset.theme, effective);
          }
        }
        setLocale("zh-TW"); ui.refresh();
        assert.equal(label.textContent, "系統");
        assert.equal(button.attributes.title, "切換為淺色主題");
        assert.equal(button.attributes["aria-label"], "切換為淺色主題");
        doc.cookie = "scopes-tool.webui.theme=dark";
        const restored = initializeThemeUi({button: new Node(), label: new Node(), documentElement: doc.documentElement, cookieDocument: doc, mediaQuery});
        assert.equal(restored.getPreference(), "dark");
        assert.equal(doc.documentElement.dataset.theme, "dark");
        doc.cookie = "scopes-tool.webui.theme=invalid";
        assert.equal(readSavedThemePreference(doc), null);
    ''')


def test_bootstrap_applies_theme_before_css_and_help_is_disabled() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.index("<script>") < html.index('<link rel="stylesheet"')
    help_tag = re.search(r'<button\b[^>]*id="help-button"[^>]*>', html).group()
    assert "disabled" in help_tag and "href" not in help_tag and "onclick" not in help_tag
    assert 'id="webui-version"' in html
    assert 'data-i18n="page.unofficial_tool"' in html
    run_node(r'''
        const bootstrap = read("index.html").match(/<script>([\s\S]*?)<\/script>/)[1];
        for (const [cookie, systemDark, expected] of [["", true, "dark"], ["", false, "light"], ["scopes-tool.webui.theme=light", true, "light"], ["scopes-tool.webui.theme=dark", false, "dark"], ["scopes-tool.webui.theme=invalid", true, "dark"]]) {
          const document = {cookie, documentElement: {dataset: {}}};
          vm.runInNewContext(bootstrap, {document, matchMedia: () => ({matches: systemDark})});
          assert.equal(document.documentElement.dataset.theme, expected);
        }
    ''')


def test_supported_devices_api_is_display_only() -> None:
    client = TestClient(app)
    models_before = client.get("/api/models").json()
    response = client.get("/api/supported-devices")
    assert response.status_code == 200
    assert response.json() == [
        {"vendor": "Keysight", "model": model, "connections": connections}
        for model, connections in [
            ("DSOX2004A", ["USB"]), ("DSOX3024A", ["USB"]),
            ("DSOX4024A", ["USB", "TCPIP"]), ("DSOX4034A", ["USB"]),
        ]
    ]
    assert client.get("/api/models").json() == models_before == model_catalog()
    for module in ("command_catalog.py", "command_validation.py", "jobs.py"):
        assert "supported_devices" not in (STATIC.parent / module).read_text(encoding="utf-8")
    assert client.get("/static/theme_ui.js").headers["Cache-Control"] == "no-store"
    assert client.get("/static/supported-devices.js").headers["Cache-Control"] == "no-store"


def test_supported_projection_uses_core_identity_and_omits_unapproved_models(monkeypatch) -> None:
    model = next(model for model in supported_devices.PHYSICAL_MODEL_REGISTRY if model.model_id == "keysight-dsox2004a")
    monkeypatch.setattr(supported_devices, "PHYSICAL_MODEL_REGISTRY", (replace(model, canonical_model="Core model"),))
    monkeypatch.setattr(supported_devices, "DISPLAY_CONNECTIONS", {model.model_id: ("USB",), "unknown": ("TCPIP",)})
    assert supported_devices.supported_devices_payload() == [{"vendor": "Keysight", "model": "Core model", "connections": ["USB"]}]
    monkeypatch.setattr(supported_devices, "DISPLAY_CONNECTIONS", {model.model_id: ()})
    assert supported_devices.supported_devices_payload() == []


def test_supported_panel_open_close_escape_outside_click_and_retry() -> None:
    run_node(r'''
        const { initializeSupportedDevices } = await load("supported-devices.js");
        const button = new Node(), panel = new Node(), body = new Node(), status = new Node(), settings = new Node();
        button.ownerDocument = doc; panel.hidden = true;
        let requests = 0, opened = 0, fail = true;
        globalThis.fetch = async (path) => {
          assert.equal(path, "/api/supported-devices"); requests++;
          return {ok: !fail, json: async () => [{vendor: "Keysight", model: "DSOX4024A", connections: ["USB", "TCPIP"]}]};
        };
        initializeSupportedDevices({button, panel, body, status, settings, onOpen: () => opened++});
        const event = {stopPropagation() { this.stopped = true; }};
        button.emit("click", event);
        assert.equal(panel.hidden, false); assert.equal(button.attributes["aria-expanded"], "true");
        assert.equal(event.stopped, true); assert.equal(opened, 1);
        await new Promise(setImmediate);
        assert.equal(status.textContent, translate("supported_devices.error"));
        setLocale("zh-TW");
        assert.equal(status.textContent, translate("supported_devices.error"));
        doc.emit("keydown", {key: "Escape"});
        assert.equal(panel.hidden, true); assert.equal(button.attributes["aria-expanded"], "false");
        assert.equal(button.focused, true);
        fail = false; button.emit("click", event); await new Promise(setImmediate);
        assert.deepEqual(body.children[0].children.map((cell) => cell.textContent), ["Keysight", "DSOX4024A", "USB, TCPIP"]);
        assert.equal(status.hidden, true);
        const inside = {stopPropagation() { this.stopped = true; }};
        panel.emit("click", inside); assert.equal(inside.stopped, true); assert.equal(panel.hidden, false);
        doc.emit("click"); assert.equal(panel.hidden, true);
        button.emit("click", event); settings.emit("click"); assert.equal(panel.hidden, true);
        assert.equal(requests, 2);
    ''')


def test_chart_repaints_theme_without_changing_samples_and_disposes_listener() -> None:
    run_node(r'''
        const { MonitorChart } = await load("monitor-chart.js");
        const canvas = new Node(); canvas.ownerDocument = doc;
        const colors = [];
        const context = {setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() { colors.push(this.strokeStyle); }};
        canvas.getContext = () => context;
        canvas.getBoundingClientRect = () => ({width: 100, height: 100});
        const frames = []; globalThis.requestAnimationFrame = (callback) => {frames.push(callback); return frames.length;};
        const chunks = [{capture_index: 1, global_start_index: 0, time_s: [0, 1], channels: {CH1: {values: [1, 2]}}}];
        const before = JSON.stringify(chunks);
        doc.documentElement.dataset.theme = "light";
        const chart = new MonitorChart(canvas, new Node(), new Node(), () => chunks, translate);
        frames.shift()(); assert.equal(colors.at(-1), "#1769aa");
        doc.documentElement.dataset.theme = "dark"; doc.emit("themechange");
        frames.shift()(); assert.equal(colors.at(-1), "#8bbcf5");
        assert.equal(JSON.stringify(chunks), before);
        chart.dispose(); assert.equal(doc.listeners.themechange.length, 0);
    ''')
