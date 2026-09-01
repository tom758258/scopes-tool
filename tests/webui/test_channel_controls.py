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

        console.log("all channel control frontend checks passed");
        '''
    ).replace("__MEASURE_FIELDS__", json.dumps(measure_fields)).replace(
        "__MEASURE_WINDOW_FIELDS__", json.dumps(measure_window_fields)
    ).replace(
        "__REFERENCE_SLOT__", json.dumps(reference_slot)
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
def test_capture_multi_enum_channel_options_use_channel_translation() -> None:
    capture_fields = next(
        entry["fields"] for entry in command_catalog() if entry["id"] == "capture"
    )
    capture_channels = next(field for field in capture_fields if field["name"] == "channels")
    assert capture_channels["option_label"] == "channel"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

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
            const isMultiFor = sel==="[data-multi-for]";
            const mField = sel.match(/^\[data-field="([^"]+)"\]$/);
            const walk=(node)=>{
              if(!node) return;
              if(isDataField && node.dataset && "field" in node.dataset){
                if(sel==="[data-field]") out.push(node);
                else if(mField && node.dataset.field===mField[1]) out.push(node);
              }
              if(isMultiFor && node.dataset && "multiFor" in node.dataset) out.push(node);
              for(const c of node.children||[]) walk(c);
              for(const o of node.options||[]) {
                if(isDataField && o.dataset && "field" in o.dataset) {
                  if(sel==="[data-field]") out.push(o);
                  else if(mField && o.dataset.field===mField[1]) out.push(o);
                }
              }
            };
            for(const w of this.children) walk(w);
            return out;
          }
        }
        function makeContainer(){
          const c=new FakeEl("div");
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
          "enum.channel1":"Channel 1","enum.channel2":"Channel 2","enum.channel3":"Channel 3","enum.channel4":"Channel 4",
          "field.capture.channels":"Channels",
        };
        globalThis.hasTranslation = k=> k in translations;
        globalThis.translate = (k, values={})=>{
          let text = translations[k] || k;
          for(const [name,value] of Object.entries(values)) text=text.replaceAll(`{{${name}}}`, String(value));
          return text;
        };

        const catalog = {
          fieldsFor: (cmd)=> cmd.fields,
          optionsFor: (f)=> f.options||[],
        };

        const captureFields = __CAPTURE_FIELDS__;

        let source = [
          fs.readFileSync(path.join(process.cwd(),"src/scopes_tool_webui/static/numeric-input.js"),"utf8"),
          fs.readFileSync(path.join(process.cwd(),"src/scopes_tool_webui/static/command-form.js"),"utf8"),
        ].join("\n");
        source = source.replace(/^import[^\n]*\r?\n/gm,"").replace(/^export /gm,"");
        source += "\nglobalThis.CommandForm=CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const CommandForm = globalThis.CommandForm;

        const cont = makeContainer();
        const form = new CommandForm(cont, catalog);
        const cmd = { id:"capture", fields:captureFields, presentation:{ kind:"command", action:"capture" } };
        form.render(cmd);
        const sel = cont.querySelector('[data-field="channels"]');
        assert.ok(sel, "channels should be SELECT");
        assert.equal(sel.tagName, "SELECT");
        assert.equal(sel.multiple, true);
        // options should be Channel N, not bare numbers
        assert.equal(sel.options[0].textContent, "Channel 1");
        assert.equal(sel.options[1].textContent, "Channel 2");
        assert.equal(sel.options[2].textContent, "Channel 3");
        assert.equal(sel.options[3].textContent, "Channel 4");
        assert.equal(sel.options[0].value, "1");

        // multi-choice checkboxes should also use channel labels
        const boxes = cont.querySelectorAll("[data-multi-for]");
        const boxLabels = boxes.map(b=> b.parentElement.children[1].textContent);
        assert.deepEqual(boxLabels, ["Channel 1","Channel 2","Channel 3","Channel 4"]);

        console.log("capture multi-enum channel translation passed");
        '''
    ).replace("__CAPTURE_FIELDS__", json.dumps(capture_fields))
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
