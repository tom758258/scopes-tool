from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_webui import command_catalog as catalog_module
from scopes_tool_webui.commands import COMMANDS, command_catalog
from scopes_tool_webui.command_catalog import _ANALOG_CHANNEL_FIELDS, _model_command_presentation


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def test_analog_channel_base_fields_are_select_capable() -> None:
    channel_ids = [
        "channel-display",
        "channel-scale",
        "channel-label",
        "channel-offset",
        "channel-coupling",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
    ]
    by_id = {entry["id"]: entry for entry in COMMANDS}
    for cid in channel_ids:
        field = next(f for f in by_id[cid]["fields"] if f["name"] == "channel")
        assert field.get("options") == (1, 2, 3, 4), cid
        assert field.get("option_label") == "channel", cid
        base_entry = next(e for e in command_catalog() if e["id"] == cid)
        base_field = next(f for f in base_entry["fields"] if f["name"] == "channel")
        assert base_field.get("options") == [1, 2, 3, 4], cid
        assert base_field.get("option_label") == "channel", cid


def test_analog_channel_model_projection_tracks_capabilities() -> None:
    catalog = {e["id"]: e for e in command_catalog()}
    for model_id in ("keysight-dsox2004a", "keysight-dsox4024a"):
        for cid in ("channel-scale", "trigger-edge", "trigger-delay"):
            presentation = catalog[cid]["presentation"]["models"][model_id]
            for name in _ANALOG_CHANNEL_FIELDS:
                if name in presentation["fields"]:
                    expected = 4
                    assert presentation["fields"][name]["maximum"] == expected
                    assert presentation["fields"][name]["options"] == list(range(1, expected + 1))

    fake = ScopeCapabilities(
        series="2000X",
        analog_channels=2,
        default_waveform_points=1000,
        safe_max_waveform_points=10000,
        supports_word_format=True,
        supports_raw_points_mode=False,
        supports_measurements=True,
        supports_delay_measurement=False,
        supports_screenshot=True,
        supports_segmented_memory=True,
        supports_serial_decode=True,
        serial_bus_count=1,
        serial_modes=frozenset({"can"}),
        math_function_count=1,
        supports_math_goft=False,
        reference_waveforms=2,
        supports_channel_label=True,
        channel_label_max_length=10,
        supports_display_label=True,
        supports_annotation=True,
        annotation_slots=1,
        supports_50_ohm_impedance=False,
        supports_search_basic=True,
        search_modes=frozenset({"serial1"}),
    )
    original = catalog_module.capabilities_for_model_id
    try:
        catalog_module.capabilities_for_model_id = lambda _mid: fake  # type: ignore[assignment]
        entry = next(e for e in catalog_module.COMMANDS if e["id"] == "channel-scale")
        pres = _model_command_presentation(entry, "fake-2ch")
        assert pres["fields"]["channel"]["options"] == (1, 2)
        assert pres["fields"]["channel"]["maximum"] == 2

        trigger = next(e for e in catalog_module.COMMANDS if e["id"] == "trigger-runt")
        pres2 = _model_command_presentation(trigger, "fake-2ch")
        assert pres2["fields"]["channel"]["options"] == (1, 2)
        assert pres2["fields"]["channel"]["maximum"] == 2
    finally:
        catalog_module.capabilities_for_model_id = original  # type: ignore[assignment]


def test_channel_catalog_retains_validation_and_locale_contracts() -> None:
    catalog = {e["id"]: e for e in command_catalog()}
    for cid, fname in (
        ("channel-scale", "volts_per_division"),
        ("channel-probe", "ratio"),
        ("channel-range", "volts"),
    ):
        field = next(f for f in catalog[cid]["fields"] if f["name"] == fname)
        assert field.get("exclusive_minimum") == 0
        assert "minimum" not in field
    skew = next(f for f in catalog["channel-probe-skew"]["fields"] if f["name"] == "seconds")
    assert skew["minimum"] == -100e-9
    assert skew["maximum"] == 100e-9

    expected_help = {
        "channel-scale": ("volts_per_division", "channel-scale.volts_per_division"),
        "channel-label": ("text", "channel-label.text"),
        "channel-offset": ("volts", "channel-offset.volts"),
        "channel-coupling": ("coupling", "channel-coupling.coupling"),
        "channel-probe": ("ratio", "channel-probe.ratio"),
        "channel-bandwidth-limit": ("enabled", "channel-bandwidth-limit.enabled"),
        "channel-impedance": ("impedance", "channel-impedance.impedance"),
        "channel-invert": ("enabled", "channel-invert.enabled"),
        "channel-range": ("volts", "channel-range.volts"),
        "channel-units": ("units", "channel-units.units"),
        "channel-vernier": ("enabled", "channel-vernier.enabled"),
        "channel-probe-skew": ("seconds", "channel-probe-skew.seconds"),
    }
    for cid, (fname, hk) in expected_help.items():
        field = next(f for f in catalog[cid]["fields"] if f["name"] == fname)
        assert field.get("help_key") == hk

    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    for key in (
        '"command.channel-scale": "垂直刻度"',
        '"command.channel-summary": "讀取通道資訊"',
        '"command.channel-offset": "垂直偏移"',
        '"command.channel-coupling": "輸入耦合"',
        '"command.channel-probe": "探棒衰減比"',
        '"command.channel-bandwidth-limit": "頻寬限制"',
        '"command.channel-impedance": "輸入阻抗"',
        '"command.channel-invert": "波形反相"',
        '"command.channel-range": "垂直範圍"',
        '"command.channel-vernier": "刻度微調"',
        '"command.channel-probe-skew": "探棒時間校正"',
    ):
        assert key in zh

    # label_key for volts fields must be present and generic field stays volts
    assert next(f for f in catalog["channel-offset"]["fields"] if f["name"] == "volts").get("label_key") == "channel-offset.value"
    assert next(f for f in catalog["channel-range"]["fields"] if f["name"] == "volts").get("label_key") == "channel-range.value"
    assert '"field.channel-offset.value": "偏移值"' in zh
    assert '"field.channel-range.value": "範圍值"' in zh
    assert '"field.volts_per_division": "每格數值"' in zh


def test_channel_summary_result_locale_keys_exist() -> None:
    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    en = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    for key in (
        "results.field.display",
        "results.field.label",
        "results.field.scale",
        "results.field.range",
        "results.field.offset",
        "results.field.coupling",
        "results.field.impedance",
        "results.field.invert",
        "results.field.bandwidth_limit",
        "results.field.units",
        "results.field.vernier",
        "results.field.probe_ratio",
        "results.field.probe_skew",
    ):
        assert f'"{key}":' in zh
        assert f'"{key}":' in en
    assert '"description.channel-summary":' in zh
    assert '"description.channel-summary":' in en
    assert '"results.channelSummary.field.scale": "垂直刻度"' in zh
    assert '"results.channelSummary.field.scale": "Vertical scale"' in en
    # Polluting generic labels must remain generic
    assert '"results.field.scale": "刻度"' in zh
    assert '"results.field.range": "範圍"' in zh
    assert '"results.field.offset": "偏移"' in zh
    assert '"results.field.coupling": "耦合"' in zh


def test_channel_label_composes_shared_visibility_without_replacing_display_command() -> None:
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="channel-label-visibility"' in html
    assert 'new LabelVisibility(elements.channelLabelVisibility, catalog,' in app
    assert 'channelLabelVisibility?.render(selected?.id === "channel-label")' in app
    commands = {entry["id"]: entry for entry in command_catalog()}
    assert commands["display-label"]["category"] == "Display"
    assert "channel-label-display" not in commands


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_generic_command_form_integer_options_render_as_select_and_serialize_integer() -> None:
    measure_fields = next(
        entry["fields"] for entry in command_catalog() if entry["id"] == "measure"
    )
    measure_window_fields = next(
        entry["fields"] for entry in command_catalog() if entry["id"] == "measure-window"
    )
    reference_save = next(
        entry for entry in command_catalog() if entry["id"] == "reference-save"
    )
    reference_slot = next(
        field for field in reference_save["fields"] if field["name"] == "slot"
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        // Dependency-free minimal DOM stub
        class FakeEl {
          constructor(tag){
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.style = {};
            this.className = "";
            this.textContent = "";
            this.hidden = false;
            this.disabled = false;
            this.checked = false;
            this.type = "";
            this.multiple = false;
            this.required = false;
            this.validity = {};
            this._value = "";
            this.options = [];
            this.selectedOptions = [];
            this.parentElement = null;
            const classes = new Set();
            this.classList = {
              add: (...names) => names.forEach((name) => classes.add(name)),
              contains: (name) => classes.has(name),
            };
          }
          get value(){ return this._value; }
          set value(v){
            this._value = String(v);
            // emulate SELECT value selects matching option
            if(this.tagName==="SELECT"){
              for(const o of this.options) o.selected = (o.value===this._value);
              this.selectedOptions = this.options.filter(o=>o.selected);
            }
          }
          append(...nodes){
            for(const n of nodes){
              this.children.push(n);
              n.parentElement = this;
              if(n.tagName==="OPTION"){
                this.options.push(n);
                if(n.selected) this.selectedOptions.push(n);
              }
            }
          }
          replaceChildren(...nodes){
            this.children = [];
            this.options = [];
            this.selectedOptions = [];
            if(nodes.length) this.append(...nodes);
          }
          setAttribute(k,v){ this.attributes[k]=String(v); }
          getAttribute(k){ return this.attributes[k]; }
          addEventListener(){}
          dispatchEvent(){ return true; }
          closest(sel){
            if(sel==='[data-visible-if-hidden="true"]'){
              let node = this;
              while(node){
                if(node.dataset?.visibleIfHidden === "true") return node;
                node = node.parentElement;
              }
            }
            return null;
          }
          setCustomValidity(){}
          checkValidity(){ return true; }
          reportValidity(){}
          querySelector(sel){ return this.querySelectorAll(sel)[0]||null; }
          querySelectorAll(sel){
            const out=[];
            const isDataField = sel==="[data-field]" || sel.startsWith('[data-field="');
            const isVisibleIf = sel==="[data-visible-if]";
            const isHelpByValue = sel==="[data-help-by-value]";
            const isMultiFor = sel==="[data-multi-for]";
            const mField = sel.match(/^\[data-field="([^"]+)"\]$/);
            const walk=(node)=>{
              if(!node) return;
              if(isDataField && node.dataset && "field" in node.dataset){
                if(sel==="[data-field]") out.push(node);
                else if(mField && node.dataset.field===mField[1]) out.push(node);
              }
              if(isVisibleIf && node.dataset && "visibleIf" in node.dataset) out.push(node);
              if(isHelpByValue && node.dataset && "helpByValue" in node.dataset) out.push(node);
              if(isMultiFor && node.dataset && "multiFor" in node.dataset) out.push(node);
              if(sel==="span" && node.tagName==="SPAN") out.push(node);
              for(const c of node.children||[]) walk(c);
              // also walk select options that may be queried directly
              for(const o of node.options||[]) {
                if(isDataField && o.dataset && "field" in o.dataset) {
                  if(sel==="[data-field]") out.push(o);
                  else if(mField && o.dataset.field===mField[1]) out.push(o);
                }
              }
            };
            for(const w of this.children) walk(w);
            // direct children that are inputs with data-field
            for(const w of this.children){
              for(const c of w.children||[]){
                if(c.dataset && "field" in c.dataset){
                  if(sel==="[data-field]") {
                    if(!out.includes(c)) out.push(c);
                  } else if(mField && c.dataset.field===mField[1]){
                    if(!out.includes(c)) out.push(c);
                  }
                }
              }
            }
            // also consider this element itself if it matches (for container queries)
            return out;
          }
        }
        function makeContainer(){
          const c=new FakeEl("div");
          // Make container behave like FakeEl but with document-like query
          return c;
        }
        globalThis.document = { createElement(tag){ return new FakeEl(tag); } };
        globalThis.Option = function(text, value){
          const o=new FakeEl("option");
          o.textContent=text; o.value=String(value); o.selected=false; return o;
        };
        globalThis.Event = class Event { constructor(t){ this.type=t; } };
        globalThis.HTMLElement = FakeEl;

        const translations = {
          "enum.measure.slope.positive":"上升","enum.measure.slope.negative":"下降",
          "enum.measure-window.window.main":"主要視窗","enum.measure-window.window.zoom":"縮放視窗","enum.measure-window.window.auto":"自動","enum.measure-window.window.gate":"游標區間",
          "enum.channel1":"通道 1","enum.channel2":"通道 2","enum.channel3":"通道 3","enum.channel4":"通道 4",
          "enum.enable":"啟用","enum.disable":"停用","enum.true":"是","enum.false":"否",
          "form.selectValue":"請選擇值","form.leaveUnchanged":"保持不變","field.channel":"通道","field.enabled":"啟用","field.bus":"匯流排","field.channel-scale.value":"每格數值","field.channel-offset.value":"偏移值","field.channel-range.value":"範圍值",
          "help.measure-window.window":"選擇量測範圍","help.measure-window.window.main":"在主要視窗量測"
        };
        translations["enum.reference-waveform"] = "Reference waveform {{value}}";
        globalThis.hasTranslation = k=> k in translations;
        globalThis.translate = (k, values = {})=> {
          let text = translations[k] || k;
          for (const [name, value] of Object.entries(values)) {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
          return text;
        };

        const catalog = {
          fieldsFor: (cmd)=> cmd.fields,
          optionsFor: (f)=> f.options||[],
        };
        const measureFields = __MEASURE_FIELDS__;
        const measureWindowFields = __MEASURE_WINDOW_FIELDS__;
        const referenceSlot = __REFERENCE_SLOT__;

        let source = [
          fs.readFileSync(path.join(process.cwd(),"src/scopes_tool_webui/static/numeric-input.js"),"utf8"),
          fs.readFileSync(path.join(process.cwd(),"src/scopes_tool_webui/static/command-form.js"),"utf8"),
        ].join("\n");
        source = source.replace(/^import[^\n]*\r?\n/gm,"").replace(/^export /gm,"");
        source += "\nglobalThis.CommandForm=CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const CommandForm = globalThis.CommandForm;

        // Shared visibility uses the existing form and actual readback, including set results.
        {
          const visibilitySource = fs.readFileSync(
            path.join(process.cwd(), "src/scopes_tool_webui/static/label-visibility.js"), "utf8",
          ).replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "")
            + "\nglobalThis.LabelVisibility = LabelVisibility;";
          await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(visibilitySource)}`);
          const command = __DISPLAY_LABEL__;
          const calls = [];
          let contextKey = "simulate|model";
          let returnedState = false;
          let status = "completed";
          let finish;
          const hooks = {
            contextKey: () => contextKey,
            isAvailable: () => true,
            isExecutionBusy: () => false,
            executeCommand: async (id, parameters, options) => {
              calls.push({ id, parameters, intent: options.intent });
              if (finish === null) await new Promise((resolve) => { finish = resolve; });
              return { status, result: { result: { state: returnedState } } };
            },
          };
          const control = new globalThis.LabelVisibility(makeContainer(), {
            ...catalog, commands: [command], supported: () => true,
          }, hooks);
          control.render(true);
          assert.equal(calls.length, 0);
          assert.equal(control.container.children[1].textContent, "labels.shared");
          const buttons = control.container.children.filter((node) => node.tagName === "BUTTON");
          assert.equal(buttons.length, 1);
          assert.equal(buttons[0].textContent, "actions.apply");
          assert.equal(control.applyButton, buttons[0]);
          const input = control.container.querySelector('[data-field="enabled"]');
          assert.equal(input.value, "");
          await control.run(false);
          assert.equal(input.value, "false");
          input.value = "true";
          input.dataset.dirty = "true";
          await control.run(false);
          assert.equal(input.value, "true");
          await control.run(true);
          assert.deepEqual(calls.at(-1), {
            id: "display-label", parameters: { action: "set", enabled: true }, intent: "apply",
          });
          assert.equal(input.value, "false", "set readback wins over requested value");
          assert.equal(input.dataset.dirty, undefined);
          returnedState = true;
          await control.run(false);
          assert.equal(input.value, "true");
          status = "failed";
          await control.run(false);
          assert.equal(input.value, "true");
          assert.equal(control.status.textContent, "labels.readFailed");
          status = "completed";
          finish = null;
          const pending = control.run(false);
          assert.equal(control.applyButton.disabled, true);
          control.render(true);
          contextKey = "simulate|other-model";
          finish();
          await pending;
          assert.equal(control.container.querySelector('[data-field="enabled"]').value, "");
          control.render(false);
          assert.equal(control.container.hidden, true);
          assert.equal(await control.run(false), null);
        }

        // A. channel integer+options with channel label -> SELECT and values() integer
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const field = { name:"channel", type:"integer", options:[1,2,3,4], option_label:"channel", default:1 };
          const cmd = { id:"channel-scale", fields:[field], presentation:{ kind:"setting", action_field:"action", query_value:"query", apply_value:"set", query_fields:[] } };
          form.render(cmd);
          const sel = cont.querySelector('[data-field="channel"]');
          assert.ok(sel, "channel should be SELECT");
          assert.equal(sel.tagName, "SELECT");
          assert.equal(sel.options.length, 4);
          assert.equal(sel.options[0].textContent, "通道 1");
          assert.equal(sel.options[1].value, "2");
          sel.value = "2";
          const vals = form.values();
          assert.deepEqual(vals, { channel: 2 });
          assert.equal(typeof vals.channel, "number");
        }

        // B. projected reference waveform options render as a SELECT
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const cmd = { id:"reference-save", fields:[referenceSlot], presentation:{ kind:"command", action:"save" } };
          form.render(cmd);
          const sel = cont.querySelector('[data-field="slot"]');
          assert.equal(sel.tagName, "SELECT");
          assert.equal(sel.options.length, 3);
          assert.equal(sel.options[1].value, "1");
          assert.equal(sel.options[2].value, "2");
          assert.equal(sel.options[1].textContent, "Reference waveform 1");
          assert.equal(sel.options[2].textContent, "Reference waveform 2");
          sel.value = "2";
          assert.deepEqual(form.values(), { slot: 2 });
        }

        // C. generic integer without channel label uses numeric option text
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const field = { name:"bus", type:"integer", options:[1,2], default:1 };
          const cmd = { id:"generic", fields:[field], presentation:{ kind:"command", action:"run" } };
          form.render(cmd);
          const sel = cont.querySelector('[data-field="bus"]');
          assert.equal(sel.options[0].textContent, "1");
          assert.equal(sel.options[1].textContent, "2");
        }

        // C. boolean wording
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const enabledField = { name:"enabled", type:"boolean" };
          const otherField = { name:"display", type:"boolean" };
          const cmd = { id:"test", fields:[enabledField, otherField], presentation:{ kind:"command", action:"run" } };
          form.render(cmd);
          const enabledSel = cont.querySelector('[data-field="enabled"]');
          const displaySel = cont.querySelector('[data-field="display"]');
          assert.equal(enabledSel.options[1].textContent, "啟用");
          assert.equal(enabledSel.options[2].textContent, "停用");
          assert.equal(displaySel.options[1].textContent, "是");
          assert.equal(displaySel.options[2].textContent, "否");
        }

        // D. label_key
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const field = { name:"volts", type:"number", label_key:"channel-range.value" };
          const wrapper = form.field(field);
          assert.equal(wrapper.querySelector("span").textContent, "範圍值");
        }

        // E. invalid draft is ignored, keeps rendered default and no dirty
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const field = { name:"channel", type:"integer", options:[1,2], option_label:"channel", default:1 };
          const cmd = { id:"channel-scale", fields:[field], presentation:{ kind:"setting", action_field:"action", query_value:"query", apply_value:"set", query_fields:[] } };
          form.render(cmd, { draft: [{ name:"channel", value:"4", dirty:true }] });
          const sel = cont.querySelector('[data-field="channel"]');
          assert.equal(sel.value, "1");
          assert.equal(sel.dataset.dirty, undefined);
          const vals = form.values();
          assert.deepEqual(vals, { channel: 1 });
        }
        // E2. valid draft is restored
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const field = { name:"channel", type:"integer", options:[1,2], option_label:"channel", default:1 };
          const cmd = { id:"channel-scale", fields:[field], presentation:{ kind:"setting", action_field:"action", query_value:"query", apply_value:"set", query_fields:[] } };
          form.render(cmd, { draft: [{ name:"channel", value:"2", dirty:true }] });
          const sel = cont.querySelector('[data-field="channel"]');
          assert.equal(sel.value, "2");
          assert.equal(sel.dataset.dirty, "true");
          const vals = form.values();
          assert.deepEqual(vals, { channel: 2 });
        }

        // F. vpp keeps only the common fields and excludes hidden values
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const cmd = { id:"measure", fields:measureFields, presentation:{ kind:"command", action:"run" } };
          form.render(cmd);
          const hiddenNames = ["reference_channel", "time_s", "level", "slope", "occurrence"];
          for(const name of hiddenNames){
            assert.equal(cont.querySelector(`[data-field="${name}"]`).parentElement.hidden, true, name);
          }
          assert.deepEqual(form.values(), { item:"vpp", channel:1 });
        }

        // G. phase shows a required reference channel without leave-unchanged wording
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const cmd = { id:"measure", fields:measureFields, presentation:{ kind:"command", action:"run" } };
          form.render(cmd);
          cont.querySelector('[data-field="item"]').value = "phase";
          form.refreshVisibility();
          const reference = cont.querySelector('[data-field="reference_channel"]');
          assert.equal(reference.parentElement.hidden, false);
          assert.equal(reference.required, true);
          assert.equal(reference.options[0].textContent, translations["form.selectValue"]);
          assert.ok(reference.options.every((option)=> option.textContent !== translations["form.leaveUnchanged"]));
        }

        // H. time_at_value uses required level and measurement-specific defaults/labels
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const cmd = { id:"measure", fields:measureFields, presentation:{ kind:"command", action:"run" } };
          form.render(cmd);
          cont.querySelector('[data-field="item"]').value = "time_at_value";
          form.refreshVisibility();
          const level = cont.querySelector('[data-field="level"]');
          const slope = cont.querySelector('[data-field="slope"]');
          const occurrence = cont.querySelector('[data-field="occurrence"]');
          assert.equal(level.parentElement.hidden, false);
          assert.equal(level.required, true);
          assert.equal(slope.value, "positive");
          assert.equal(slope.options[0].textContent, "上升");
          assert.equal(slope.options[1].textContent, "下降");
          assert.equal(occurrence.value, "1");
          assert.equal(cont.querySelector('[data-field="time_s"]').parentElement.hidden, true);
          level.value = "0.5";
          assert.deepEqual(form.values(), {
            item:"time_at_value", channel:1, level:0.5, slope:"positive", occurrence:1,
          });
        }

        // I. help_by_value adds selected guidance after the base help
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const cmd = {
            id:"measure-window",
            fields:measureWindowFields,
            presentation:{ kind:"setting", action_field:"action", query_value:"query", apply_value:"set", query_fields:[] },
          };
          form.render(cmd);
          const help = cont.querySelector("[data-help-by-value]");
          const window = cont.querySelector('[data-field="window"]');
          assert.equal(help.textContent, "選擇量測範圍");
          window.value = "main";
          form.refreshVisibility();
          assert.equal(help.textContent, "選擇量測範圍\n在主要視窗量測");
        }

        // J. capture multi-enum channel options use channel translation
        {
          const cont = makeContainer();
          const form = new CommandForm(cont, catalog);
          const field = { name:"channels", type:"multi-enum", options:[1,2,3,4], default:[1], serialize:"csv", required:true, option_label:"channel" };
          const cmd = { id:"capture", fields:[field], presentation:{ kind:"command", action:"capture" } };
          form.render(cmd);
          const sel = cont.querySelector('[data-field="channels"]');
          assert.ok(sel, "channels should be SELECT");
          assert.equal(sel.tagName, "SELECT");
          assert.equal(sel.multiple, true);
          assert.equal(sel.options[0].textContent, "通道 1");
          assert.equal(sel.options[0].value, "1");
          const boxes = cont.querySelectorAll("[data-multi-for]");
          const boxLabels = boxes.map(b=> b.parentElement.children[1].textContent);
          assert.deepEqual(boxLabels, ["通道 1","通道 2","通道 3","通道 4"]);
        }

        console.log("all channel control frontend checks passed");
        '''
    ).replace("__MEASURE_FIELDS__", json.dumps(measure_fields)).replace(
        "__MEASURE_WINDOW_FIELDS__", json.dumps(measure_window_fields)
    ).replace(
        "__REFERENCE_SLOT__", json.dumps(reference_slot)
    ).replace(
        "__DISPLAY_LABEL__", json.dumps(next(
            entry for entry in command_catalog() if entry["id"] == "display-label"
        ))
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout


EXPECTED_CHANNEL_GROUPS = {
    "channel-display": "channel-basic",
    "channel-scale": "channel-basic",
    "channel-summary": "channel-basic",
    "channel-label": "channel-basic",
    "channel-offset": "channel-basic",
    "channel-range": "channel-basic",
    "channel-coupling": "channel-advanced",
    "channel-probe": "channel-advanced",
    "channel-bandwidth-limit": "channel-advanced",
    "channel-impedance": "channel-advanced",
    "channel-invert": "channel-advanced",
    "channel-units": "channel-advanced",
    "channel-vernier": "channel-advanced",
    "channel-probe-skew": "channel-advanced",
}

EXPECTED_CHANNEL_BASIC_ORDER = [
    "channel-display",
    "channel-scale",
    "channel-summary",
    "channel-label",
    "channel-offset",
    "channel-range",
]


def test_channel_commands_keep_groups_order_and_presentation_labels() -> None:
    channel_commands = [entry for entry in COMMANDS if entry["category"] == "Channel"]
    assert len(channel_commands) == len(EXPECTED_CHANNEL_GROUPS)
    assert {entry["id"] for entry in channel_commands} == set(EXPECTED_CHANNEL_GROUPS)

    for entry in channel_commands:
        assert entry.get("group") == EXPECTED_CHANNEL_GROUPS[entry["id"]], entry["id"]

    basic_commands = [entry["id"] for entry in channel_commands if entry.get("group") == "channel-basic"]
    assert len(basic_commands) == 6
    assert basic_commands == EXPECTED_CHANNEL_BASIC_ORDER

    advanced_commands = [entry["id"] for entry in channel_commands if entry.get("group") == "channel-advanced"]
    assert len(advanced_commands) == 8
    assert set(advanced_commands) == set(EXPECTED_CHANNEL_GROUPS) - set(EXPECTED_CHANNEL_BASIC_ORDER)

    summary_entry = next(entry for entry in channel_commands if entry["id"] == "channel-summary")
    assert summary_entry["label"] == "Read Channel Information"

    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    en = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")

    assert '"command.channel-summary": "讀取通道資訊"' in zh
    assert '"command.channel-summary": "Read Channel Information"' in en
    assert '"group.channel-basic": "基本功能"' in zh
    assert '"group.channel-advanced": "進階功能"' in zh
    assert '"group.channel-basic": "Basic"' in en
    assert '"group.channel-advanced": "Advanced"' in en

    # Search and shared basic group remains intact
    assert '"group.basic": "基本"' in zh
    assert '"group.basic": "Basic"' in en


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_channel_display_editor_checkbox_and_readback_behavior() -> None:
    catalog_json = json.dumps(command_catalog())
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeEl {
          constructor(tag) {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.className = "";
            this.textContent = "";
            this.hidden = false;
            this.disabled = false;
            this.checked = false;
            this.type = "";
            this.value = "";
          }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(event, handler) { this[`on_${event}`] = handler; }
          remove() {}
        }

        globalThis.document = { createElement: (tag) => new FakeEl(tag) };
        globalThis.queueMicrotask = (fn) => fn();
        globalThis.hasTranslation = () => false;
        globalThis.translate = (key) => key;

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/channel-display-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class ChannelDisplayEditor", "class ChannelDisplayEditor")
          + "\nglobalThis.ChannelDisplayEditor = ChannelDisplayEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const command = __CATALOG__.find((entry) => entry.id === "channel-display");
        let currentContext = "simulate|model";

        function makeEditor(options, handler, headerActions = null) {
          const calls = [];
          const catalog = {
            commands: [{
              ...command,
              fields: command.fields.map((field) =>
                field.name === "channel" ? { ...field, options } : field
              ),
            }],
            fieldsFor: (definition) => definition.fields || [],
            optionsFor: (field) => field.options || [],
          };
          const hooks = {
            contextKey: () => currentContext,
            selectedCommand: () => ({ id: "channel-display", editor: "channel-display" }),
            isAvailable: () => true,
            isExecutionBusy: () => false,
            isCommandAvailable: () => true,
            ...(headerActions ? { headerActions } : {}),
            async executeCommand(id, parameters, requestOptions) {
              calls.push({ id, parameters, options: requestOptions });
              return handler({ id, parameters, setContext: (value) => { currentContext = value; } });
            },
          };
          return {
            editor: new globalThis.ChannelDisplayEditor(new FakeEl("div"), catalog, hooks),
            calls,
          };
        }

        // A. Run snapshots the checkbox state and dispatches all projected channels in order.
        currentContext = "simulate|model";
        const completeRun = makeEditor([1, 2, 3, 4], ({ parameters }) => ({
          status: "completed",
          result: { result: { enabled: parameters.enabled } },
        }));
        const completeBoxes = completeRun.editor.entries.map((entry) => entry.box);
        completeBoxes[0].checked = true;
        completeBoxes[1].checked = false;
        completeBoxes[2].checked = true;
        completeBoxes[3].checked = false;
        await completeRun.editor.run();
        assert.deepEqual(completeRun.calls, [
          { id: "channel-display", parameters: { action: "set", channel: 1, enabled: true }, options: { intent: "apply" } },
          { id: "channel-display", parameters: { action: "set", channel: 2, enabled: false }, options: { intent: "apply" } },
          { id: "channel-display", parameters: { action: "set", channel: 3, enabled: true }, options: { intent: "apply" } },
          { id: "channel-display", parameters: { action: "set", channel: 4, enabled: false }, options: { intent: "apply" } },
        ]);
        assert.equal(completeRun.editor.status.textContent, "");

        // B. A completed set with a mismatching readback stops immediately.
        currentContext = "simulate|model";
        const mismatchRun = makeEditor([1, 2, 3, 4], ({ parameters }) => ({
          status: "completed",
          result: { enabled: parameters.channel === 1 ? false : parameters.enabled },
        }));
        await mismatchRun.editor.run();
        assert.equal(mismatchRun.calls.length, 1);
        assert.equal(mismatchRun.calls[0].parameters.channel, 1);
        assert.equal(mismatchRun.editor.status.textContent, "channel-display.editor.runIncomplete");

        // A lifecycle failure also stops before the next channel.
        currentContext = "simulate|model";
        const failedRun = makeEditor([1, 2, 3, 4], () => ({ status: "failed" }));
        await failedRun.editor.run();
        assert.equal(failedRun.calls.length, 1);
        assert.equal(failedRun.editor.status.textContent, "channel-display.editor.runIncomplete");

        // 1. Same context present() should preserve existing status.
        failedRun.editor.present();
        assert.equal(
          failedRun.editor.status.textContent,
          "channel-display.editor.runIncomplete",
        );

        // 2. Presentation context change should clear previous status.
        currentContext = "simulate|other-model";
        failedRun.editor.present();
        assert.equal(failedRun.editor.status.textContent, "");

        // C. A context change after the first command prevents the second dispatch or stale status.
        currentContext = "simulate|model";
        const staleStatus = "current-context-status";
        const staleRun = makeEditor([1, 2, 3, 4], ({ setContext }) => {
          setContext("simulate|other-model");
          return { status: "failed" };
        });
        staleRun.editor.status.textContent = staleStatus;
        await staleRun.editor.run();
        assert.equal(staleRun.calls.length, 1);
        assert.equal(staleRun.calls[0].parameters.channel, 1);
        assert.equal(staleRun.editor.status.textContent, staleStatus);

        // D. A complete aggregate readback updates all checkboxes atomically.
        currentContext = "simulate|model";
        const completeRead = makeEditor([1, 2, 3, 4], ({ id }) => id === "channel-summary"
          ? {
              status: "completed",
              result: { result: { channels: [
                { channel: 1, display: true },
                { channel: 2, display: false },
                { channel: 3, display: true },
                { channel: 4, display: false },
              ] } },
            }
          : { status: "completed" });
        for (const [index, entry] of completeRead.editor.entries.entries()) {
          entry.box.checked = index % 2 === 1;
        }
        await completeRead.editor.read();
        assert.deepEqual(completeRead.editor.entries.map((entry) => entry.box.checked), [true, false, true, false]);
        assert.equal(completeRead.editor.status.textContent, "");

        // Invalid aggregate readback leaves every checkbox unchanged.
        currentContext = "simulate|model";
        const invalidRead = makeEditor([1, 2, 3, 4], ({ id }) => id === "channel-summary"
          ? {
              status: "completed",
              result: { channels: [
                { channel: 1, display: true },
                { channel: 2, display: null },
                { channel: 3, display: false },
                { channel: 4, display: true },
              ] },
            }
          : { status: "completed" });
        const invalidBefore = [false, true, false, true];
        invalidRead.editor.entries.forEach((entry, index) => { entry.box.checked = invalidBefore[index]; });
        await invalidRead.editor.read();
        assert.deepEqual(invalidRead.editor.entries.map((entry) => entry.box.checked), invalidBefore);
        assert.equal(invalidRead.editor.status.textContent, "channel-display.editor.readFailed");

        // E. Channel options are projected from the catalog.
        currentContext = "simulate|model";
        const projected = makeEditor([1, 2], () => ({ status: "completed" }));
        assert.deepEqual(projected.editor.channels, [1, 2]);
        assert.equal(projected.editor.entries.length, 2);

        // F. With headerActions, refresh/run move to the header and the body uses a section.
        currentContext = "simulate|model";
        const headerActions = new FakeEl("div");
        const headedRun = makeEditor([1, 2, 3, 4], ({ parameters }) => ({
          status: "completed",
          result: { result: { enabled: parameters.enabled } },
        }), headerActions);
        assert.ok(headerActions.children.includes(headedRun.editor.refreshButton));
        assert.ok(headerActions.children.includes(headedRun.editor.runButton));
        assert.equal(headedRun.editor.container.children.includes(headedRun.editor.refreshButton), false);
        assert.equal(headedRun.editor.container.children.includes(headedRun.editor.runButton), false);
        assert.ok(headedRun.editor.runButton.className.split(" ").includes("primary"));
        assert.equal(headedRun.editor.section.tagName, "DIV");
        assert.equal(headedRun.editor.section.className, "workflow-editor-section");
        assert.equal(headedRun.editor.heading.textContent, "channel-display.editor.displayedChannels");
        assert.equal(headedRun.editor.helper.textContent, "channel-display.editor.displayHelper");
        assert.deepEqual(
          headedRun.editor.section.children.map((node) => node.tagName),
          ["STRONG", "DIV", "SMALL"],
        );
        assert.equal(headedRun.editor.section.children[1], headedRun.editor.choicesHost);
        await headedRun.editor.run();
        assert.equal(headedRun.calls.length, 4);

        // Fallback without headerActions keeps both buttons in the body.
        assert.ok(completeRun.editor.container.children.includes(completeRun.editor.refreshButton));
        assert.ok(completeRun.editor.container.children.includes(completeRun.editor.runButton));
        assert.ok(completeRun.editor.runButton.className.split(" ").includes("primary"));

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)
    completed = subprocess.run(
        ["node", "--input-type=module"],
        cwd=REPO_ROOT,
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
    assert json.loads(completed.stdout) == {"ok": True}


def test_channel_scale_range_composite_workspace() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}
    assert "channel-scale-range" in catalog
    composite = catalog["channel-scale-range"]
    assert composite["category"] == "Channel"
    assert composite["group"] == "channel-basic"
    assert composite["editor"] == "channel-scale-range"
    assert composite["presentation_only"] is True
    assert composite["modes"] == ["live", "simulate"]
    assert composite["fields"] == []

    # Underlying commands are hidden in command browser
    assert catalog["channel-scale"]["browser_hidden"] is True
    assert catalog["channel-range"]["browser_hidden"] is True

    # Underlying commands still retain their proper fields and requirements
    scale_fields = {field["name"]: field for field in catalog["channel-scale"]["fields"]}
    assert "volts_per_division" in scale_fields
    assert scale_fields["volts_per_division"]["exclusive_minimum"] == 0

    range_fields = {field["name"]: field for field in catalog["channel-range"]["fields"]}
    assert "volts" in range_fields
    assert range_fields["volts"]["exclusive_minimum"] == 0

    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    en = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    assert '"command.channel-scale-range": "垂直刻度 / 範圍"' in zh
    assert '"command.channel-scale-range": "Vertical Scale / Range"' in en
    assert '"channel-scale-range.editor.title": "垂直刻度 / 範圍"' in zh
    assert '"channel-scale-range.editor.title": "Vertical Scale / Range"' in en
    assert "Range = Scale × 8" in zh
    assert "Range = Scale × 8" in en
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    availability = app.split("function updateAvailability()", 1)[1].split(
        "function isExecutionBusy()", 1
    )[0]
    assert "channelScaleRangeEditor?.applyBusyState();" in availability

    # Preset layout and value-field width contracts live in styles.css
    css = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    assert ".channel-scale-range-presets" in css
    assert ".channel-scale-range-value" in css
    assert "max-width: 50%" in css
    desktop_presets = css.split(".channel-scale-range-presets {", 1)[1].split("}", 1)[0]
    assert "repeat(5, minmax(0, 1fr))" in desktop_presets
    narrow = css.split("@media (max-width: 700px)", 1)[1]
    narrow_presets = narrow.split(".channel-scale-range-presets {", 1)[1].split("}", 1)[0]
    assert "repeat(2, minmax(0, 1fr))" in narrow_presets
    assert ".channel-scale-range-mode button.selected" in css
    header_actions = app.split("function syncWorkspaceHeaderActions(editorKind)", 1)[1].split(
        "function syncEditorPresentation(editorKind)", 1
    )[0]
    assert 'channelScaleRangeEditor.readButton.hidden = editorKind !== "channel-scale-range";' in header_actions
    assert 'channelScaleRangeEditor.applyButton.hidden = editorKind !== "channel-scale-range";' in header_actions

    # Shared quick-fill help key exists in both locales
    assert '"channel-scale-range.editor.quickFillHelp":' not in zh
    assert '"channel-scale-range.editor.quickFillHelp":' not in en
    for key in (
        "channel-scale-range.editor.modeScale",
        "channel-scale-range.editor.modeRange",
        "channel-scale-range.editor.scaleDescription",
        "channel-scale-range.editor.rangeDescription",
        "channel-scale-range.editor.readFirstHelp",
    ):
        assert f'"{key}":' in zh, key
        assert f'"{key}":' in en, key


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_channel_scale_range_editor_command_dispatch_and_readback(tmp_path: Path) -> None:
    catalog_json = json.dumps(command_catalog())
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeNode {
          constructor(tag) {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.className = "";
            this.textContent = "";
            this.disabled = false;
            this.hidden = false;
            this.style = {};
            this.value = "";
            this.type = "";
            this.min = "";
            this.step = "";
            const classSet = () => new Set(this.className.split(" ").filter(Boolean));
            const writeBack = (set) => { this.className = [...set].join(" "); };
            this.classList = {
              add: (...names) => { const s = classSet(); names.forEach((n) => s.add(n)); writeBack(s); },
              remove: (...names) => { const s = classSet(); names.forEach((n) => s.delete(n)); writeBack(s); },
              toggle: (name, force) => {
                const s = classSet();
                const want = force === undefined ? !s.has(name) : Boolean(force);
                if (want) s.add(name); else s.delete(name);
                writeBack(s);
                return want;
              },
              contains: (name) => classSet().has(name),
            };
          }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(event, handler) { this[`on_${event}`] = handler; }
          setAttribute(k, v) { this.attributes[k] = String(v); }
          getAttribute(k) { return this.attributes[k]; }
          remove() {}
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };
        globalThis.translate = (key) => key;
        globalThis.hasTranslation = (_key) => false;

        let liveDataSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/live-data.js"),
          "utf8",
        );
        liveDataSource = liveDataSource.replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "")
          + "\nglobalThis.formatEngineering = formatEngineering;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(liveDataSource)}`);

        const calls = [];
        let executionBusy = false;
        let currentContext = "simulate||keysight-dsox4024a";
        let mockUnits = "volt";
        let failUnits = false;
        const headerActions = new FakeNode("div");
        const hooks = {
          contextKey: () => currentContext,
          selectedCommand: () => ({ id: "channel-scale-range", editor: "channel-scale-range" }),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          headerActions,
          async executeCommand(id, parameters, options) {
            calls.push([id, parameters, options]);
            if (id === "channel-scale") {
              if (parameters.action === "query") {
                return { status: "completed", result: { volts_per_division: 0.2 } };
              }
              if (parameters.action === "set") {
                return { status: "completed", result: { volts_per_division: parameters.volts_per_division } };
              }
            }
            if (id === "channel-range") {
              if (parameters.action === "query") {
                return { status: "completed", result: { volts: 1.6 } };
              }
              if (parameters.action === "set") {
                return { status: "completed", result: { volts: parameters.volts } };
              }
            }
            if (id === "channel-units") {
              if (failUnits) return { status: "failed" };
              return { status: "completed", result: { units: mockUnits } };
            }
            return { status: "completed" };
          },
        };

        const catalog = {
          commands: __CATALOG__,
          fieldsFor: (command) => command.fields || [],
          optionsFor: (field) => field.options || [],
        };

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/channel-scale-range-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class ChannelScaleRangeEditor", "class ChannelScaleRangeEditor")
          + "\nglobalThis.ChannelScaleRangeEditor = ChannelScaleRangeEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const editor = new globalThis.ChannelScaleRangeEditor(new FakeNode("div"), catalog, hooks);
        editor.present();

        const drain = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        // Verify channel dropdown was populated from catalog
        assert.equal(editor.channels.length, 4);
        assert.deepEqual(editor.channels, [1, 2, 3, 4]);

        // Select shared channel 3
        editor.channelSelect.value = "3";

        // 0. Default mode is Scale; only the Scale section is visible.
        assert.equal(editor.mode, "scale");
        assert.equal(editor.scaleSection.hidden, false);
        assert.equal(editor.rangeSection.hidden, true);
        assert.equal(editor.modeButtons.scale.classList.contains("selected"), true);
        assert.equal(editor.modeButtons.range.classList.contains("selected"), false);
        assert.ok(headerActions.children.includes(editor.readButton));
        assert.ok(headerActions.children.includes(editor.applyButton));
        assert.deepEqual(
          editor.scalePresetButtons.map((button) => button.textContent),
          ["0.001", "0.002", "0.005", "0.01", "0.02", "0.05", "0.1", "0.2", "0.5", "1"],
        );
        for (const button of [...editor.scalePresetButtons, ...editor.rangePresetButtons]) {
          assert.equal(button.disabled, true);
        }

        // 1. Header Read in Scale mode queries scale then units and enables Scale presets.
        editor.readButton.on_click();
        await drain();
        assert.deepEqual(calls[0], [
          "channel-scale",
          { action: "query", channel: 3 },
          { intent: "readback" },
        ]);
        assert.deepEqual(calls[1], [
          "channel-units",
          { action: "query", channel: 3 },
          { intent: "readback" },
        ]);
        assert.equal(editor.scaleInput.value, "0.2");
        assert.deepEqual(
          editor.scalePresetButtons.map((button) => button.textContent),
          [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1].map(
            (value) => globalThis.formatEngineering(value, "V"),
          ),
        );
        assert.equal(editor.scalePresetButtons[0].textContent, globalThis.formatEngineering(0.001, "V"));
        for (const button of editor.scalePresetButtons) assert.equal(button.disabled, false);
        // Range was not read: its presets stay disabled even though units are known.
        for (const button of editor.rangePresetButtons) assert.equal(button.disabled, true);

        // 2. Switching modes needs no dispatch and keeps per-mode read state.
        const callsBeforeSwitch = calls.length;
        editor.modeButtons.range.on_click();
        assert.equal(editor.mode, "range");
        assert.equal(editor.scaleSection.hidden, true);
        assert.equal(editor.rangeSection.hidden, false);
        assert.equal(editor.modeButtons.scale.classList.contains("selected"), false);
        assert.equal(editor.modeButtons.range.classList.contains("selected"), true);
        assert.equal(calls.length, callsBeforeSwitch);
        for (const button of editor.rangePresetButtons) assert.equal(button.disabled, true);

        // 3. Header Read in Range mode enables Range presets; Scale stays enabled.
        editor.readButton.on_click();
        await drain();
        assert.deepEqual(calls[calls.length - 2], [
          "channel-range",
          { action: "query", channel: 3 },
          { intent: "readback" },
        ]);
        assert.deepEqual(calls[calls.length - 1][0], "channel-units");
        assert.equal(editor.rangeInput.value, "1.6");
        for (const button of editor.rangePresetButtons) assert.equal(button.disabled, false);
        for (const button of editor.scalePresetButtons) assert.equal(button.disabled, false);
        // Preset click fills without dispatch and leaves the other field alone.
        editor.rangeInput.value = "sentinel";
        const rangeButton = editor.rangePresetButtons.find(
          (candidate) => candidate.textContent === globalThis.formatEngineering(4, "V"),
        );
        assert.ok(rangeButton);
        rangeButton.on_click();
        assert.equal(editor.rangeInput.value, "4");
        assert.equal(editor.scaleInput.value, "0.2");

        // 4. Header Apply dispatches set for the current mode with readback fill.
        editor.modeButtons.scale.on_click();
        editor.scaleInput.value = "0.5";
        const callsBeforeApply = calls.length;
        editor.applyButton.on_click();
        await drain();
        assert.equal(calls.length, callsBeforeApply + 1);
        assert.deepEqual(calls[calls.length - 1], [
          "channel-scale",
          { action: "set", channel: 3, volts_per_division: 0.5 },
          { intent: "apply" },
        ]);
        assert.equal(editor.scaleInput.value, "0.5");
        // Apply does not unlock anything new and keeps presets enabled.
        for (const button of editor.scalePresetButtons) assert.equal(button.disabled, false);

        // 5. Invalid numeric values are rejected without dispatch.
        editor.scaleInput.value = "-1";
        editor.applyButton.on_click();
        await drain();
        assert.equal(calls.length, callsBeforeApply + 1);
        editor.scaleInput.value = "abc";
        editor.applyButton.on_click();
        await drain();
        assert.equal(calls.length, callsBeforeApply + 1);

        // 6. AMP units render mA / A labels after a fresh read.
        mockUnits = "amp";
        currentContext = "simulate|RESOURCE-B|keysight-dsox4024a";
        editor.present();
        editor.channelSelect.value = "3";
        editor.readButton.on_click();
        await drain();
        assert.equal(editor.scalePresetButtons[0].textContent, globalThis.formatEngineering(0.001, "A"));
        assert.equal(editor.scalePresetButtons[9].textContent, globalThis.formatEngineering(1, "A"));
        mockUnits = "volt";

        // 7. A failed value read keeps presets disabled and leaves inputs alone.
        hooks.executeCommand = async (id, parameters, options) => {
          calls.push([id, parameters, options]);
          if (id === "channel-scale") return { status: "failed" };
          if (id === "channel-units") return { status: "completed", result: { units: "volt" } };
          return { status: "completed" };
        };
        editor.scaleInput.value = "sentinel";
        editor.readButton.on_click();
        await drain();
        for (const button of editor.scalePresetButtons) assert.equal(button.disabled, true);
        assert.equal(editor.scaleInput.value, "sentinel");

        // 8. A failed units query fills the value but never unlocks quick-fill.
        hooks.executeCommand = async (id, parameters, options) => {
          calls.push([id, parameters, options]);
          if (id === "channel-scale") return { status: "completed", result: { volts_per_division: 0.2 } };
          if (id === "channel-units") return { status: "failed" };
          return { status: "completed" };
        };
        editor.readButton.on_click();
        await drain();
        assert.equal(editor.scaleInput.value, "0.2");
        for (const button of editor.scalePresetButtons) assert.equal(button.disabled, true);
        editor.modeButtons.range.on_click();
        for (const button of editor.rangePresetButtons) assert.equal(button.disabled, true);

        // Restore the default mock for the remaining steps.
        hooks.executeCommand = async (id, parameters, options) => {
          calls.push([id, parameters, options]);
          if (id === "channel-scale") {
            if (parameters.action === "query") {
              return { status: "completed", result: { volts_per_division: 0.2 } };
            }
            if (parameters.action === "set") {
              return { status: "completed", result: { volts_per_division: parameters.volts_per_division } };
            }
          }
          if (id === "channel-range") {
            if (parameters.action === "query") {
              return { status: "completed", result: { volts: 1.6 } };
            }
            if (parameters.action === "set") {
              return { status: "completed", result: { volts: parameters.volts } };
            }
          }
          if (id === "channel-units") {
            return { status: "completed", result: { units: mockUnits } };
          }
          return { status: "completed" };
        };

        // 9. Channel changes clear values, units, and per-mode read state.
        editor.modeButtons.scale.on_click();
        editor.readButton.on_click();
        await drain();
        for (const button of editor.scalePresetButtons) assert.equal(button.disabled, false);
        editor.scaleInput.value = "0.5";
        editor.rangeInput.value = "4";
        editor.channelSelect.value = "2";
        editor.channelSelect.on_change();
        assert.equal(editor.scaleInput.value, "");
        assert.equal(editor.rangeInput.value, "");
        for (const button of [...editor.scalePresetButtons, ...editor.rangePresetButtons]) {
          assert.equal(button.disabled, true);
        }

        // 10. A new context clears values and keeps the editor structure compact.
        editor.channelSelect.value = "3";
        editor.readButton.on_click();
        await drain();
        for (const button of editor.scalePresetButtons) assert.equal(button.disabled, false);
        editor.scaleInput.value = "0.5";
        editor.rangeInput.value = "4";
        currentContext = "simulate|RESOURCE-C|keysight-dsox4024a";
        editor.present();
        assert.equal(editor.scaleInput.value, "");
        assert.equal(editor.rangeInput.value, "");
        assert.equal(editor.container.children.length, 4);
        for (const button of [...editor.scalePresetButtons, ...editor.rangePresetButtons]) {
          assert.equal(button.disabled, true);
        }

        // 11. Stale result protection: if contextKey changes before read completes, do not update input.
        let slowReadResolve;
        hooks.executeCommand = async (id, parameters, options) => {
          calls.push([id, parameters, options]);
          return new Promise((resolve) => { slowReadResolve = resolve; });
        };
        const readPromise = editor.readButton.on_click();
        // Context changed while read was pending
        currentContext = "live|USB0::0x0957::0x17A6::MY50000001::INSTR|keysight-dsox4024a";
        slowReadResolve({ status: "completed", result: { volts_per_division: 99 } });
        await readPromise;
        // scaleInput should NOT be overwritten with 99
        assert.notEqual(editor.scaleInput.value, "99");

        // Drain the step-11 read continuation so busy clears before the remaining checks.
        await drain();

        // 12. Busy state disables presets alongside the existing controls.
        editor.busy = true;
        editor.applyBusyState();
        for (const button of [...editor.scalePresetButtons, ...editor.rangePresetButtons]) {
          assert.equal(button.disabled, true);
        }
        editor.busy = false;
        editor.applyBusyState();

        // 13. Help combines the mode description with the read-first note.
        assert.equal(editor.scaleHelp.tagName, "SMALL");
        assert.equal(editor.scaleHelp.className, "field-help");
        assert.equal(
          editor.scaleHelp.textContent,
          "channel-scale-range.editor.scaleDescription\nchannel-scale-range.editor.readFirstHelp",
        );
        assert.equal(editor.rangeHelp.tagName, "SMALL");
        assert.equal(editor.rangeHelp.className, "field-help");
        assert.equal(
          editor.rangeHelp.textContent,
          "channel-scale-range.editor.rangeDescription\nchannel-scale-range.editor.readFirstHelp",
        );
        globalThis.translate = (key) => `T:${key}`;
        editor.rerender();
        assert.equal(
          editor.scaleHelp.textContent,
          "T:channel-scale-range.editor.scaleDescription\nT:channel-scale-range.editor.readFirstHelp",
        );
        assert.equal(
          editor.rangeHelp.textContent,
          "T:channel-scale-range.editor.rangeDescription\nT:channel-scale-range.editor.readFirstHelp",
        );

        // 14. Without headerActions the Read / Apply pair falls back to the body.
        const fallbackEditor = new globalThis.ChannelScaleRangeEditor(new FakeNode("div"), catalog, {
          contextKey: () => currentContext,
          selectedCommand: () => ({ id: "channel-scale-range", editor: "channel-scale-range" }),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          executeCommand: async () => ({ status: "completed" }),
        });
        assert.ok(fallbackEditor.container.children.includes(fallbackEditor.readButton));
        assert.ok(fallbackEditor.container.children.includes(fallbackEditor.applyButton));

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)

    harness_path = tmp_path / "scale-range-editor-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
    assert json.loads(completed.stdout) == {"ok": True}
