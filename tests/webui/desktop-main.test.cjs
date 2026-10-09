const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");
const { PassThrough } = require("node:stream");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const mainPath = path.join(root, "desktop", "main.cjs");
const source = fs.readFileSync(mainPath, "utf8");
const cookieName = "scopes-tool.webui.theme";
const readyUrl = "http://127.0.0.1:49321";
const flush = () => new Promise((resolve) => setImmediate(resolve));

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function desktop(options = {}) {
  const windows = [];
  const errors = [];
  const warnings = [];
  const writes = [];
  const launches = [];
  const order = [];
  const children = [];
  const cookies = new EventEmitter();
  let saved = options.preference;
  cookies.get = async (filter) => {
    assert.deepEqual({ ...filter }, { url: "http://127.0.0.1/", name: cookieName });
    if (options.cookieError) throw new Error("Cookie access failed");
    if (options.cookieRead) return options.cookieRead.promise;
    return saved === undefined ? [] : [{ value: saved }];
  };
  const app = new EventEmitter();
  app.isPackaged = options.packaged || false;
  app.whenReady = () => options.appReady || Promise.resolve();
  app.quit = () => {
    const event = { prevented: false, preventDefault() { this.prevented = true; } };
    app.emit("before-quit", event);
    if (!event.prevented) order.push("app.quit");
    return event;
  };
  const nativeTheme = { themeSource: "system" };
  class BrowserWindow extends EventEmitter {
    constructor(config) {
      super();
      this.options = config;
      this.webContents = new EventEmitter();
      this.webContents.setWindowOpenHandler = (handler) => { this.popup = handler; };
      this.destroyed = false;
      this.shown = false;
      windows.push(this);
      order.push("window.create");
    }
    loadURL(url) {
      this.url = url;
      return options.load ? options.load.promise : Promise.resolve();
    }
    isDestroyed() { return this.destroyed; }
    show() { this.shown = true; order.push("window.show"); }
    close() {
      const event = { prevented: false, preventDefault() { this.prevented = true; } };
      this.emit("close", event);
      if (!event.prevented) {
        this.destroyed = true;
        this.emit("closed");
        app.emit("window-all-closed");
      }
      return event;
    }
  }
  function spawn(command, args, config) {
    launches.push({ command, args: [...args], config });
    if (options.spawnThrows) throw new Error("Spawn failed");
    const child = new EventEmitter();
    child.exitCode = null;
    child.signalCode = null;
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.stdin = new EventEmitter();
    child.stdin.write = (text, callback) => {
      writes.push(text);
      order.push("shutdown.write");
      if (options.writeThrows) throw new Error("Pipe closed");
      queueMicrotask(() => {
        const error = options.writeError ? new Error("Pipe closed") : null;
        callback(error);
        if (error) child.stdin.emit("error", error);
      });
    };
    child.kill = () => assert.fail("Desktop must not kill the Host");
    children.push(child);
    return child;
  }
  const electron = {
    app, BrowserWindow, nativeTheme,
    dialog: {
      showErrorBox: (title, message) => errors.push({ title, message }),
      showMessageBox: (...args) => { warnings.push(args.at(-1)); return Promise.resolve(); },
    },
    screen: { getPrimaryDisplay: () => ({ workAreaSize: options.workArea || { width: 2560, height: 1440 } }) },
    session: options.sessionError ? {} : { defaultSession: { cookies } },
  };
  const context = vm.createContext({
    __dirname: options.dirname || path.dirname(mainPath), URL, Set,
    process: { stderr: new PassThrough(), execPath: options.execPath },
    require(name) {
      if (name === "electron") return electron;
      if (name === "node:child_process") return { spawn };
      if (name === "node:fs") return { existsSync: (file) => {
        if (options.packaged) assert.equal(file, path.join(path.dirname(options.execPath), "scopes-tool-webui-host.exe"));
        return options.missing !== path.basename(file);
      } };
      return require(name);
    },
  });
  vm.runInContext(source, context, { filename: mainPath });
  await flush();
  return {
    app, nativeTheme, windows, errors, warnings, writes, launches, order, children,
    event(payload) { children[0].stdout.write(JSON.stringify(payload) + "\n"); },
    line(text) { children[0].stdout.write(text); },
    theme(value, name = cookieName) { saved = value; cookies.emit("changed", {}, { name }); },
    exit(code = 0, signal = null) {
      children[0].exitCode = code;
      children[0].signalCode = signal;
      order.push("host.close");
      children[0].emit("close", code, signal);
    },
  };
}

async function ready(options) {
  const harness = await desktop(options);
  harness.event({ event: "ready", url: readyUrl });
  await flush();
  return harness;
}

test("Desktop metadata and lock match the Python distribution and source entry point", () => {
  const metadata = JSON.parse(fs.readFileSync(path.join(root, "desktop/package.json")));
  const lock = JSON.parse(fs.readFileSync(path.join(root, "desktop/package-lock.json")));
  const version = fs.readFileSync(path.join(root, "pyproject.toml"), "utf8").match(/^version = "([^"]+)"/m)[1];
  assert.equal(metadata.name, "scopes-tool-desktop");
  assert.equal(metadata.productName, "Scopes Tool");
  assert.equal(metadata.version, version);
  assert.equal(metadata.main, "main.cjs");
  assert.equal(metadata.scripts.start, "electron .");
  assert.equal(metadata.scripts.check, "node --check main.cjs");
  assert.equal(metadata.scripts["dist:win"], "electron-builder --dir --win --x64");
  assert.deepEqual(metadata.build.files, ["main.cjs", "assets/scopes-icon.ico"]);
  assert.equal(metadata.build.win.icon, "assets/scopes-icon.ico");
  assert.equal(lock.name, metadata.name);
  assert.equal(lock.version, version);
  assert.equal(lock.packages[""].version, version);
  assert.deepEqual(lock.packages[""].devDependencies, metadata.devDependencies);
  assert.equal(lock.packages["node_modules/electron"].version, metadata.devDependencies.electron);
});

test("Host uses the repository venv, module, hidden process and separate pipes", async () => {
  const h = await desktop();
  assert.equal(h.launches.length, 1);
  assert.equal(h.launches[0].command, path.join(root, ".venv/Scripts/python.exe"));
  assert.deepEqual(h.launches[0].args, ["-m", "scopes_tool_webui._desktop_host"]);
  assert.equal(h.launches[0].config.cwd, root);
  assert.equal(h.launches[0].config.windowsHide, true);
  assert.deepEqual([...h.launches[0].config.stdio], ["pipe", "pipe", "pipe"]);
  assert.equal(h.windows.length, 0);
  h.children[0].stderr.write(JSON.stringify({ event: "ready", url: readyUrl }) + "\n");
  await flush();
  assert.equal(h.windows.length, 0);
});

test("Packaged Host uses the executable directory without repository files", async () => {
  const directory = path.join(root, ".tmp_tests", "outside-source");
  const h = await ready({
    packaged: true,
    execPath: path.join(directory, "Scopes Tool.exe"),
    dirname: path.join(directory, "resources", "app.asar"),
  });
  assert.equal(h.launches[0].command, path.join(directory, "scopes-tool-webui-host.exe"));
  assert.deepEqual(h.launches[0].args, []);
  assert.equal(h.launches[0].config.cwd, undefined);
  assert.equal(h.windows[0].shown, true);
  assert.equal(h.windows[0].options.icon, path.join(directory, "resources/app.asar/assets/scopes-icon.ico"));
  h.windows[0].close();
  assert.deepEqual(h.writes, ['{"command":"shutdown"}\n']);
  h.exit();
  assert.equal(h.errors.length, 0);
  assert.ok(h.order.includes("app.quit"));
});

test("Missing packaged Host reports its path and exits before spawning", async () => {
  const execPath = path.join(root, ".tmp_tests", "Scopes Tool.exe");
  const h = await desktop({ packaged: true, execPath, missing: "scopes-tool-webui-host.exe" });
  assert.equal(h.launches.length, 0);
  assert.equal(h.windows.length, 0);
  assert.equal(h.errors.length, 1);
  assert.ok(h.errors[0].message.includes(path.dirname(execPath)));
  assert.match(h.errors[0].message, /Desktop backend executable not found/);
  assert.ok(h.order.includes("app.quit"));
});

test("Only one complete JSONL ready creates a window using the supplied URL", async () => {
  const h = await desktop();
  h.line('not JSON\nnull\n[]\n{"event":"unknown"}\n');
  h.line('{"event":"ready","url":"http://127.0.0.1:51234');
  await flush();
  assert.equal(h.windows.length, 0);
  h.line('"}\r\n');
  h.event({ event: "ready", url: "http://127.0.0.1:51235" });
  await flush();
  assert.equal(h.windows.length, 1);
  assert.equal(h.windows[0].url, "http://127.0.0.1:51234/");
});

test("Invalid ready URLs fail without a window and request graceful cleanup", async (t) => {
  for (const url of [null, 123, "invalid", "https://127.0.0.1:49321", "http://localhost:49321", "http://example.com:49321", "http://[::1]:49321", "http://127.0.0.1", "http://127.0.0.1:0", "http://127.0.0.1:65536", "file:///tmp/index.html", "http://user:secret@127.0.0.1:49321"]) {
    await t.test(String(url), async () => {
      const h = await desktop();
      h.event({ event: "ready", url });
      await flush();
      assert.equal(h.windows.length, 0);
      assert.equal(h.errors.length, 1);
      assert.match(h.errors[0].message, /invalid local URL/);
      assert.deepEqual(h.writes, ['{"command":"shutdown"}\n']);
      assert.ok(!h.order.includes("app.quit"));
    });
  }
});

test("Window uses Scopes title, icon and sandbox settings within the work area", async () => {
  const h = await ready({ workArea: { width: 1366, height: 768 } });
  const config = h.windows[0].options;
  assert.equal(config.title, "Scopes Tool");
  assert.equal(config.icon, path.join(root, "desktop/assets/scopes-icon.ico"));
  assert.ok(fs.existsSync(config.icon));
  assert.equal(config.width, 1366);
  assert.equal(config.height, 768);
  assert.equal(config.show, false);
  assert.deepEqual({ ...config.webPreferences }, {
    nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true,
  });
  const large = await ready();
  assert.equal(large.windows[0].options.width, 1920);
  assert.equal(large.windows[0].options.height, 1080);
});

test("Window is shown only after page load and initial native theme synchronization", async () => {
  const load = deferred();
  const cookieRead = deferred();
  const h = await ready({ load, cookieRead });
  assert.equal(h.windows[0].shown, false);
  load.resolve();
  await flush();
  assert.equal(h.windows[0].shown, false);
  cookieRead.resolve([{ value: "dark" }]);
  await flush();
  assert.equal(h.nativeTheme.themeSource, "dark");
  assert.equal(h.windows[0].shown, true);
});

test("Navigation and redirects stay on the ready origin; every popup is denied", async () => {
  const h = await ready();
  const window = h.windows[0];
  for (const eventName of ["will-navigate", "will-redirect"]) {
    for (const [url, allowed] of [
      [readyUrl + "/static/index.html", true],
      ["http://127.0.0.1:49322/", false],
      ["https://127.0.0.1:49321/", false],
      ["http://example.com/", false],
      ["file:///tmp/index.html", false],
      ["javascript:alert(1)", false],
      ["invalid", false],
    ]) {
      let prevented = false;
      window.webContents.emit(eventName, { preventDefault() { prevented = true; } }, url);
      assert.equal(prevented, !allowed, `${eventName}: ${url}`);
    }
  }
  for (const url of [readyUrl, readyUrl + "/help/", "https://example.com/"]) {
    assert.equal(window.popup({ url }).action, "deny");
  }
});

test("Saved system, light, dark, missing and invalid cookies initialize native theme", async (t) => {
  for (const preference of ["system", "light", "dark", undefined, "invalid"]) {
    await t.test(String(preference), async () => {
      const h = await ready({ preference });
      assert.equal(h.nativeTheme.themeSource, ["light", "dark"].includes(preference) ? preference : "system");
      assert.equal(h.windows[0].shown, true);
    });
  }
});

test("Theme cookie changes synchronize native theme and ignore unrelated cookies", async () => {
  const h = await ready();
  for (const preference of ["light", "dark", "system"]) {
    h.theme(preference);
    await flush();
    assert.equal(h.nativeTheme.themeSource, preference);
  }
  h.theme("dark", "unrelated.theme");
  await flush();
  assert.equal(h.nativeTheme.themeSource, "system");
  h.theme("invalid");
  await flush();
  assert.equal(h.nativeTheme.themeSource, "system");
});

test("Cookie or session failures fall back to system without blocking startup", async () => {
  for (const options of [{ cookieError: true }, { sessionError: true }]) {
    const h = await ready(options);
    assert.equal(h.nativeTheme.themeSource, "system");
    assert.equal(h.windows[0].shown, true);
    assert.equal(h.errors.length, 0);
  }
});

test("Window close and app quit send one shutdown and wait for Host close", async () => {
  const h = await ready();
  assert.equal(h.windows[0].close().prevented, true);
  assert.equal(h.windows[0].close().prevented, true);
  assert.equal(h.app.quit().prevented, true);
  assert.deepEqual(h.writes, ['{"command":"shutdown"}\n']);
  assert.ok(!h.order.includes("app.quit"));
  assert.equal(h.windows[0].destroyed, false);
  await flush();
  h.exit();
  assert.equal(h.errors.length, 0);
  assert.deepEqual(h.order.slice(-3), ["shutdown.write", "host.close", "app.quit"]);
});

test("App quit before ready requests cleanup without creating a window", async () => {
  const h = await desktop();
  assert.equal(h.app.quit().prevented, true);
  assert.equal(h.windows.length, 0);
  assert.deepEqual(h.writes, ['{"command":"shutdown"}\n']);
  h.exit();
  assert.equal(h.errors.length, 0);
});

test("Incomplete cleanup warns, stays open and permits another formal shutdown", async () => {
  const h = await ready();
  h.windows[0].close();
  h.event({ event: "shutdown_incomplete", message: "Cleanup timed out" });
  assert.equal(h.warnings.length, 1);
  assert.equal(h.warnings[0].type, "warning");
  assert.equal(h.warnings[0].detail, "Cleanup timed out");
  assert.ok(!h.order.includes("app.quit"));
  assert.equal(h.windows[0].destroyed, false);
  h.windows[0].close();
  assert.equal(h.writes.length, 2);
  h.exit();
  assert.equal(h.errors.length, 0);
});

test("Exit after incomplete cleanup is reported as unexpected, even with code zero", async () => {
  const h = await ready();
  h.windows[0].close();
  h.event({ event: "shutdown_incomplete" });
  h.exit();
  assert.match(h.errors[0].message, /unexpectedly/);
});

test("Shutdown write callback and stream errors warn once and allow a retry", async () => {
  const options = { writeError: true };
  const h = await ready(options);
  h.windows[0].close();
  await flush();
  assert.equal(h.warnings.length, 1);
  assert.match(h.warnings[0].detail, /Could not request graceful shutdown: Pipe closed/);
  assert.ok(!h.order.includes("app.quit"));
  options.writeError = false;
  h.windows[0].close();
  assert.equal(h.writes.length, 2);
  h.exit();
  assert.equal(h.errors.length, 0);
});

test("Synchronous shutdown write failures warn and keep Desktop running", async () => {
  const h = await ready({ writeThrows: true });
  h.windows[0].close();
  assert.equal(h.warnings.length, 1);
  assert.ok(!h.order.includes("app.quit"));
});

test("Missing Python or Host source reports a startup error without a window", async () => {
  for (const missing of ["python.exe", "_desktop_host.py"]) {
    const h = await desktop({ missing });
    assert.equal(h.launches.length, 0);
    assert.equal(h.windows.length, 0);
    assert.equal(h.errors.length, 1);
    assert.equal(h.errors[0].title, "Scopes Tool");
    assert.ok(h.order.includes("app.quit"));
  }
});

test("Spawn failures show one error and quit without a window", async () => {
  const h = await desktop();
  h.children[0].emit("error", new Error("Access denied"));
  h.exit(-1);
  assert.equal(h.errors.length, 1);
  assert.match(h.errors[0].message, /Could not start.*Access denied/);
  assert.equal(h.windows.length, 0);
  const synchronous = await desktop({ spawnThrows: true });
  assert.equal(synchronous.errors.length, 1);
  assert.ok(synchronous.order.includes("app.quit"));
});

test("Host startup error event is displayed and process exit ends Desktop", async () => {
  const h = await desktop();
  h.event({ event: "error", message: "Missing dependency" });
  assert.match(h.errors[0].message, /Missing dependency/);
  assert.equal(h.windows.length, 0);
  h.exit(1);
  assert.equal(h.errors.length, 1);
  assert.ok(h.order.includes("app.quit"));
});

test("Unexpected Host exit or signal displays an error and ends Desktop", async () => {
  for (const [code, signal] of [[0, null], [1, null], [null, "SIGTERM"]]) {
    const h = await ready();
    h.exit(code, signal);
    assert.equal(h.errors.length, 1);
    assert.match(h.errors[0].message, /exited unexpectedly/);
    assert.ok(h.order.includes("app.quit"));
  }
});

test("Nonzero exit during requested shutdown is not considered successful", async () => {
  const h = await ready();
  h.windows[0].close();
  h.exit(1);
  assert.match(h.errors[0].message, /unexpectedly/);
});

test("Page load failure keeps the window hidden and requests graceful cleanup", async () => {
  const load = deferred();
  const h = await ready({ load });
  load.reject(new Error("Load failed"));
  await flush();
  assert.equal(h.windows[0].shown, false);
  assert.match(h.errors[0].message, /Could not load.*Load failed/);
  assert.deepEqual(h.writes, ['{"command":"shutdown"}\n']);
  assert.ok(!h.order.includes("app.quit"));
  h.exit();
});
