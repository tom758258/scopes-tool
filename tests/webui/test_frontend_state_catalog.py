from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

from scopes_tool_webui.command_catalog import command_catalog

from tests.webui._frontend_state_test_support import (
    STATIC_ROOT,
    read_static,
    extract_function_declaration,
)

COMMAND_CATALOG_HARNESS = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.listeners = {};
            this.dataset = {};
            this.attributes = {};
            const classSet = new Set();
            this.classList = {
              add: (...names) => { for (const name of names) classSet.add(name); },
              contains: (name) => classSet.has(name),
            };
            this.hidden = false;
            this.disabled = false;
            this.title = "";
            this.value = "";
            this.type = "";
            this.textContent = "";
            this.className = "";
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name, event = {}) { for (const handler of this.listeners[name] || []) handler(event); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
          setAttribute(name, value) { this.attributes[name] = String(value); }
          closest(selector) {
            const match = selector.match(/data-([a-z-]+)\]$/);
            if (!match) return null;
            const property = match[1].replace(/-([a-z])/g, (_all, char) => char.toUpperCase());
            return this.dataset[property] !== undefined ? this : null;
          }
        }

        const translations = {
          "group.edge": "Edge",
          "group.common": "Common",
          "group.runt": "Runt",
          "group.basic": "Basic",
          "group.uart": "UART",
          "commands.noMatches": "No matching commands.",
        };
        globalThis.testTranslate = (key) => translations[key] ?? key;
        globalThis.testHasTranslation = (key) => key in translations;
        globalThis.testCommandSupported = () => true;
        globalThis.testCommandSupportReason = () => "";
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };

        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          "const commandSupported = (...args) => globalThis.testCommandSupported(...args);",
          "const commandSupportReason = (...args) => globalThis.testCommandSupportReason(...args);",
          "const fieldsForModel = globalThis.testFieldsForModel;",
          fs.readFileSync(process.argv[1], "utf8")
            .replace('import { hasTranslation, translate } from "/static/i18n.js";', "")
            .replace(/import \{[^}]*\} from "\/static\/command-support\.js";/, ""),
        ].join("\n").replace(/^export class /gm, "class ")
          + "\nglobalThis.catalogApi = { CommandCatalog };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const commands = [
          { id: "trigger-edge", category: "Trigger", label: "Edge trigger", modes: ["live"], group: "edge" },
          { id: "trigger-edge-source", category: "Trigger", label: "Edge trigger source", modes: ["live"], group: "edge" },
          { id: "trigger-sweep", category: "Trigger", label: "Trigger sweep", modes: ["live"], group: "common" },
          { id: "trigger-runt", category: "Trigger", label: "Runt trigger", modes: ["live"], group: "runt" },
          { id: "search-state", category: "Search", label: "Search state", modes: ["live"], group: "basic" },
          { id: "serial-search-uart", category: "Search", label: "UART serial search", modes: ["live"], group: "uart" },
          { id: "serial-mode", category: "Serial", label: "Serial mode", modes: ["live"], group: "uart" },
          { id: "acquisition", category: "Acquisition", label: "Acquisition", modes: ["live"] },
        ];
        const buildCatalog = () => {
          const elements = {
            filter: new FakeNode("input"),
            categories: new FakeNode(),
            list: new FakeNode(),
          };
          const selections = [];
          const catalog = new globalThis.catalogApi.CommandCatalog(
            commands,
            elements,
            (selected) => selections.push(selected?.id || ""),
          );
          return { elements, selections, catalog };
        };
        const sections = (list) => list.children.filter((node) => node.className === "command-group");
        const sectionFor = (list, group) =>
          sections(list).find((node) => node.children[0].dataset.commandGroup === group);
        const flatButtons = (list) => list.children.filter((node) => node.className === "command-button");
        const clickGroupHeader = (list, section) =>
          list.dispatch("click", { target: section.children[0] });
'''

def test_hidden_commands_use_model_projection_before_refresh() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog(include_hidden=True)}
    model = "tektronix-tbs2074"
    assert catalog["live-data-snapshot"]["presentation"]["models"][model]["supported"] is True
    assert catalog["system-information-snapshot"]["presentation"]["models"][model]["supported"] is True
    for command in ("doctor", "smoke"):
        assert catalog[command]["presentation"]["models"][model]["supported"] is True
    app_source = read_static("app.js")
    assert "getCommands(true)" in app_source
    assert "catalog.supported(definition)" in extract_function_declaration(app_source, "function commandAvailable(command)")
    assert '!commandAvailable("live-data-snapshot")' in extract_function_declaration(app_source, "async function refreshLiveDataSnapshot()")

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_command_support_consumes_backend_model_projection() -> None:
    support_path = STATIC_ROOT / "command-support.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        const source = "const translate = (key, values) => `${key}:${values?.model || ''}`;\n"
          + fs.readFileSync(process.argv[1], "utf8").replace(/^import[^\n]*\r?\n/gm, "");
        const support = await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const command = {
          fields: [
            { name: "channel", type: "integer", maximum: 4 },
            { name: "impedance", type: "enum", options: ["one_meg", "fifty"] },
          ],
          presentation: { models: { two_channel: {
            supported: false,
            fields: {
              channel: { maximum: 2 },
              impedance: { options: ["one_meg"] },
            },
          } } },
        };
        assert.equal(support.commandSupported(command, "two_channel"), false);
        assert.match(support.commandSupportReason(command, "two_channel", "Two Channel"), /Two Channel/);
        assert.deepEqual(support.fieldsForModel(command, "two_channel"), [
          { name: "channel", type: "integer", maximum: 2 },
          { name: "impedance", type: "enum", options: ["one_meg"] },
        ]);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(support_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

def test_command_editor_and_result_presentation_contract() -> None:
    app_source = read_static("app.js")
    form_source = read_static("command-form.js")
    results_source = read_static("results.js")

    assert 'input.type = "hidden";' in form_source
    assert 'field.help_key ? `help.${field.help_key}` : `help.${field.name}`' in form_source
    assert 'field.label_key ? `field.${field.label_key}`' in form_source
    assert 'translate("enum.enable")' in form_source
    assert 'translate("enum.disable")' in form_source
    assert 'translate("enum.true")' in form_source
    assert 'translate("enum.false")' in form_source
    assert 'new Option(translate("status.enabled")' not in form_source
    assert "commandForm.queryValues()" in app_source
    assert 'intent: "readback"' in app_source
    assert 'if (options.intent === "apply") commandForm.clearDirty();' in app_source
    assert 'const draft = changed && rerender && commandForm ? commandForm.draft() : null;' in app_source
    assert 'if (changed && rerender && commandForm) syncCommandSelection(draft);' in app_source
    assert 'if (lockEditor) commandForm.setDisabled(true);' in app_source
    assert 'commandForm.setDisabled(false);' in app_source
    assert "}, () => syncCommandSelection());" in app_source
    assert "renderWorkspaceResult" in results_source
    assert 'job.command === "identify"' in results_source
    assert "appendWorkspaceFields(container, fields);" in results_source
    assert "JSON.stringify(job.result, null, 2)" in results_source

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_command_catalog_renders_collapsible_groups_with_flat_fallback() -> None:
    catalog_path = STATIC_ROOT / "command-catalog.js"
    script = textwrap.dedent(COMMAND_CATALOG_HARNESS) + textwrap.dedent(
        r'''
        {
          const { elements, catalog } = buildCatalog();
          catalog.render();

          const groups = sections(elements.list).map((node) => node.children[0].dataset.commandGroup);
          assert.deepEqual(groups, ["edge", "common", "runt"]);
          const expectedLabels = { edge: "Edge", common: "Common", runt: "Runt" };
          for (const section of sections(elements.list)) {
            const toggle = section.children[0];
            assert.equal(toggle.tagName, "BUTTON");
            assert.equal(toggle.type, "button");
            assert.equal(toggle.attributes["aria-expanded"], "true");
            assert.equal(toggle.children[0].textContent, "▾");
            assert.equal(toggle.children[1].textContent, expectedLabels[toggle.dataset.commandGroup]);
            assert.equal(section.children[1].hidden, false);
          }
          assert.deepEqual(
            sectionFor(elements.list, "edge").children[1].children.map((node) => node.dataset.command),
            ["trigger-edge", "trigger-edge-source"],
          );

          catalog.select("acquisition");
          assert.equal(flatButtons(elements.list).length, 1);
          assert.equal(sections(elements.list).length, 0);
          assert.equal(flatButtons(elements.list)[0].dataset.command, "acquisition");

          globalThis.testCommandSupported = () => false;
          globalThis.testCommandSupportReason = () => "Unavailable for Model X";
          catalog.updateModel("model-x", "Model X");
          catalog.select("trigger-edge");
          const edgeItems = sectionFor(elements.list, "edge").children[1].children;
          assert.equal(edgeItems[0].disabled, true);
          assert.equal(edgeItems[0].title, "Unavailable for Model X");
          assert.equal(edgeItems[0].children[1].tagName, "SMALL");
          globalThis.testCommandSupported = () => true;
          globalThis.testCommandSupportReason = () => "";
          catalog.updateModel(null);

          let commonSection = sectionFor(elements.list, "common");
          clickGroupHeader(elements.list, commonSection);
          commonSection = sectionFor(elements.list, "common");
          assert.equal(commonSection.children[0].attributes["aria-expanded"], "false");
          assert.equal(commonSection.children[0].children[0].textContent, "▸");
          assert.equal(commonSection.children[1].hidden, true);
          assert.equal(catalog.selectedId, "trigger-edge");
          clickGroupHeader(elements.list, commonSection);
          assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "true");

          catalog.select("search-state");
          clickGroupHeader(elements.list, sectionFor(elements.list, "uart"));
          assert.equal(sectionFor(elements.list, "uart").children[0].attributes["aria-expanded"], "false");
          catalog.select("serial-mode");
          assert.equal(sectionFor(elements.list, "uart").children[0].attributes["aria-expanded"], "true");
          catalog.select("search-state");
          assert.equal(sectionFor(elements.list, "uart").children[0].attributes["aria-expanded"], "false");

          catalog.select("trigger-edge");
          clickGroupHeader(elements.list, sectionFor(elements.list, "runt"));
          assert.equal(sectionFor(elements.list, "runt").children[1].hidden, true);
          catalog.select("trigger-runt");
          const runtSection = sectionFor(elements.list, "runt");
          assert.equal(runtSection.children[0].attributes["aria-expanded"], "true");
          assert.equal(runtSection.children[1].hidden, false);
          const runtButton = runtSection.children[1].children[0];
          assert.equal(runtButton.dataset.command, "trigger-runt");
          assert.equal(runtButton.attributes["aria-pressed"], "true");
          assert.equal(runtButton.classList.contains("active"), true);
        }

        {
          const { elements, selections, catalog } = buildCatalog();
          catalog.render();
          const baselineSelections = selections.length;
          clickGroupHeader(elements.list, sectionFor(elements.list, "common"));
          assert.equal(selections.length, baselineSelections);
          assert.equal(catalog.selectedId, "trigger-edge");
        }
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(catalog_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_command_catalog_filter_keeps_matching_groups_visible() -> None:
    catalog_path = STATIC_ROOT / "command-catalog.js"
    script = textwrap.dedent(COMMAND_CATALOG_HARNESS) + textwrap.dedent(
        r'''
        const { elements, catalog } = buildCatalog();
        catalog.render();
        assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "true");

        elements.filter.value = "sweep";
        elements.filter.dispatch("input");
        const visibleGroups = sections(elements.list).map((node) => node.children[0].dataset.commandGroup);
        assert.deepEqual(visibleGroups, ["common"]);
        const forcedSection = sectionFor(elements.list, "common");
        assert.equal(forcedSection.children[0].attributes["aria-expanded"], "true");
        assert.equal(forcedSection.children[1].hidden, false);
        assert.deepEqual(
          forcedSection.children[1].children.map((node) => node.dataset.command),
          ["trigger-sweep"],
        );

        clickGroupHeader(elements.list, sectionFor(elements.list, "common"));
        const clickedSection = sectionFor(elements.list, "common");
        assert.equal(clickedSection.children[0].attributes["aria-expanded"], "true");
        assert.equal(clickedSection.children[1].hidden, false);
        assert.equal(catalog.collapsedGroups.size, 0);

        elements.filter.value = "";
        elements.filter.dispatch("input");
        assert.deepEqual(
          sections(elements.list).map((node) => node.children[0].dataset.commandGroup),
          ["edge", "common", "runt"],
        );
        assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "true");
        assert.equal(sectionFor(elements.list, "common").children[1].hidden, false);

        clickGroupHeader(elements.list, sectionFor(elements.list, "common"));
        assert.equal(sectionFor(elements.list, "common").children[1].hidden, true);

        elements.filter.value = "sweep";
        elements.filter.dispatch("input");
        assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "true");
        assert.equal(sectionFor(elements.list, "common").children[1].hidden, false);

        elements.filter.value = "";
        elements.filter.dispatch("input");
        assert.deepEqual(
          sections(elements.list).map((node) => node.children[0].dataset.commandGroup),
          ["edge", "common", "runt"],
        );
        assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "false");
        assert.equal(sectionFor(elements.list, "common").children[1].hidden, true);

        elements.filter.value = "runt";
        elements.filter.dispatch("input");
        catalog.select("trigger-runt");
        assert.equal(sectionFor(elements.list, "runt").children[0].attributes["aria-expanded"], "true");
        assert.equal(catalog.collapsedGroups.size, 1);

        elements.filter.value = "";
        elements.filter.dispatch("input");
        assert.equal(sectionFor(elements.list, "runt").children[0].attributes["aria-expanded"], "true");
        assert.equal(sectionFor(elements.list, "runt").children[1].hidden, false);
        assert.equal(catalog.selectedId, "trigger-runt");

        elements.filter.value = "zzz-no-match";
        elements.filter.dispatch("input");
        assert.equal(elements.list.children.length, 1);
        assert.equal(elements.list.children[0].className, "muted command-list-empty");
        assert.equal(elements.list.children[0].textContent, "No matching commands.");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(catalog_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
