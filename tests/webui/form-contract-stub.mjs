import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

class FakeNode {
  constructor(tag) {
    this.tagName = (tag || "").toUpperCase();
    this.children = [];
    this.hidden = false;
    this.textContent = "";
    this.className = "";
    this.disabled = false;
    this.value = "";
  }
  append(...nodes) {
    for (const n of nodes) {
      if (n && typeof n.remove === "function") {
        const oldRemove = n.remove;
        n.remove = () => {
          if (this.children) this.children = this.children.filter((c) => c !== n);
          return oldRemove.call(n);
        };
      }
      this.children.push(n);
    }
  }
  replaceChildren(...nodes) { this.children = [...nodes]; }
  addEventListener() {}
  setAttribute() {}
  remove() { if (this.children) this.children = this.children.filter((c) => c !== this); }
  querySelector(sel) {
    // Minimal: only support [data-field="name"] selectors needed by harness.
    if (sel === '[data-field="x"]') {
      const find = (list) => {
        for (const c of list || []) {
          if (c.dataset && c.dataset.field === "x") return c;
          if (c.children) {
            const found = find(c.children);
            if (found) return found;
          }
        }
        return null;
      };
      return find(this.children) || null;
    }
    return null;
  }
  querySelectorAll(sel) {
    const collect = (list, out) => {
      for (const c of list || []) {
        if (c.dataset && c.dataset.field) out.push(c);
        if (c.children) collect(c.children, out);
      }
    };
    const out = [];
    collect(this.children, out);
    if (sel === '[data-field="x"]') return out.filter((c) => c.dataset && c.dataset.field === "x");
    if (sel === '[data-field="y"]') return out.filter((c) => c.dataset && c.dataset.field === "y");
    if (sel === '[data-field]') return out;
    // Unknown selectors (e.g. preset/multi controls absent from this harness)
    // must not match data-field inputs; production setDisabled() would
    // otherwise write disabled state onto unrelated fields.
    return [];
  }
  get closest() { return () => null; }
  get validity() { return { badInput: false }; }
  setCustomValidity() {}
  reportValidity() {}
  checkValidity() { return true; }
  get dataset() { if (!this._dataset) this._dataset = {}; return this._dataset; }
  set dataset(v) { this._dataset = v; }
}

globalThis.document = { createElement: (tag) => new FakeNode(tag) };
globalThis.queueMicrotask = (fn) => fn();
globalThis.translate = (key) => String(key || "");
globalThis.hasTranslation = () => false;
globalThis.translateEnum = (v) => String(v || "");

const rawPath = path.join(process.cwd(), "src/scopes_tool_webui/static/command-form.js");
let source = fs.readFileSync(rawPath, "utf8");
source = source.split("\n").filter((l) => !l.trim().startsWith("import ")).join("\n");
source = source.replace(/^export /gm, "");
source += "\nfunction applyNumericFieldConstraints(input, field) { if (field.minimum !== undefined) input.min = String(field.minimum); if (field.maximum !== undefined) input.max = String(field.maximum); }\n";
const formModuleWrapper = new Function(source + "; return typeof CommandForm !== 'undefined' ? CommandForm : undefined;");
const CommandForm = formModuleWrapper();
globalThis.CommandForm = CommandForm;

// C1: disabled field renders disabled=true + capabilityDisabled=true.
const stubCatalog = (fieldsArray) => ({
  fieldsFor: () => fieldsArray || [],
  optionsFor: () => [],
});

const c1 = new FakeNode("div");
const form1 = new CommandForm(c1, stubCatalog([{ name: "x", type: "integer", disabled: true, required: false }]));
const disabledDef = { name: "x", type: "integer", disabled: true, required: false };
const w1 = form1.field(disabledDef);
const inp1 = w1.children ? w1.children.find((ch) => ch.tagName === "INPUT") : null;
assert.strictEqual(inp1 && inp1.disabled, true, "C1: disabled=true");
assert.strictEqual(inp1 && inp1.dataset && inp1.dataset.capabilityDisabled, "true", "C1: capabilityDisabled marker");

// C2: values skips capability-disabled field (value="123" set manually).
const c2 = new FakeNode("div");
const form2 = new CommandForm(c2, stubCatalog([{ name: "x", type: "integer", disabled: true, required: false }]));
form2.render({ id: "test" });
const disabledInp = new FakeNode("input");
disabledInp.dataset = { field: "x", type: "integer", capabilityDisabled: "true" };
disabledInp.value = "123";
disabledInp.disabled = true;
c2.append(disabledInp);
const vResult = form2.values();
assert.strictEqual(vResult && vResult.x === undefined, true, "C2: capability-disabled omitted from values");

// C3: setDisabled(true)->false preserves capability-disabled, restores normal.
// Both fields come from the real production render; no manual marking, so a
// missing marker or a missing element fails instead of silently passing.
const c3 = new FakeNode("div");
const form3 = new CommandForm(c3, stubCatalog([
  { name: "x", type: "integer", disabled: true, required: false },
  { name: "y", type: "integer", disabled: false, required: false },
]));
form3.render({ id: "test" });
const capInputs = c3.querySelectorAll('[data-field="x"]');
const stdInputs = c3.querySelectorAll('[data-field="y"]');
assert.ok(capInputs.length === 1, "C3: rendered capability-disabled input exists");
assert.ok(stdInputs.length === 1, "C3: rendered normal input exists");
const capInp = capInputs[0];
const stdInp = stdInputs[0];
assert.strictEqual(capInp.disabled, true, "C3: capability-disabled renders disabled");
assert.strictEqual(stdInp.disabled, false, "C3: normal renders enabled");
form3.setDisabled(true);
assert.strictEqual(capInp.disabled, true, "C3a: busy keeps capability-disabled");
assert.strictEqual(stdInp.disabled, true, "C3a: busy disables normal");
form3.setDisabled(false);
assert.strictEqual(capInp.disabled, true, "C3b: capability-disabled preserved after false");
assert.strictEqual(stdInp.disabled, false, "C3b: normal restored after false");

// C4: enabled integer "0" preserved as numeric 0.
const c4 = new FakeNode("div");
const form4 = new CommandForm(c4, stubCatalog([{ name: "y", type: "integer", disabled: false, required: false }]));
form4.render({ id: "test" });
// Find the rendered input for y and set value to "0".
const yInputs = form4.container.querySelectorAll ? form4.container.querySelectorAll('[data-field="y"]') : [];
const normalInp = yInputs.length ? yInputs[0] : null;
if (normalInp) normalInp.value = "0";
const vNormal = form4.values();
assert.strictEqual(vNormal && vNormal.y, 0, "C4: 0 preserved");

console.log(JSON.stringify({ ok: true }));
