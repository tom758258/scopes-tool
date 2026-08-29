from __future__ import annotations

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
        '"command.channel-summary": "通道設定摘要"',
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
            if(sel==='[data-visible-if-hidden="true"]') return null;
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
            const isMultiFor = sel==="[data-multi-for]";
            const mField = sel.match(/^\[data-field="([^"]+)"\]$/);
            const walk=(node)=>{
              if(!node) return;
              if(isDataField && node.dataset && "field" in node.dataset){
                if(sel==="[data-field]") out.push(node);
                else if(mField && node.dataset.field===mField[1]) out.push(node);
              }
              if(isVisibleIf && node.dataset && "visibleIf" in node.dataset) out.push(node);
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
          "enum.channel1":"通道 1","enum.channel2":"通道 2","enum.channel3":"通道 3","enum.channel4":"通道 4",
          "enum.enable":"啟用","enum.disable":"停用","enum.true":"是","enum.false":"否",
          "form.selectValue":"請選擇值","form.leaveUnchanged":"保持不變","field.channel":"通道","field.enabled":"啟用","field.bus":"匯流排","field.channel-scale.value":"每格數值","field.channel-offset.value":"偏移值","field.channel-range.value":"範圍值"
        };
        globalThis.hasTranslation = k=> k in translations;
        globalThis.translate = k=> translations[k]||k;

        const catalog = {
          fieldsFor: (cmd)=> cmd.fields,
          optionsFor: (f)=> f.options||[],
        };

        let source = fs.readFileSync(path.join(process.cwd(),"src/scopes_tool_webui/static/command-form.js"),"utf8");
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

        // B. generic integer without channel label renders numeric
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

        console.log("all channel control frontend checks passed");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
