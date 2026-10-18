[繁體中文](README.zh-TW.md)

# Scopes Tool

Scopes Tool is vendor-neutral oscilloscope tooling for the registered Keysight
InfiniiVision and Tektronix models in [Supported Models](docs/core/supported-models.md).
It provides one installable Python distribution, `scopes-tool`, with independent
`scopes_tool_core`, `scopes_tool_cli`, and `scopes_tool_webui` import packages.
The CLI, Worker, browser WebUI, and Electron Desktop use the same Core behavior.

Live identity comes from the instrument's actual `*IDN?` response. Unknown,
unregistered, or mismatched vendors, models, profiles, or drivers fail closed;
a planning model does not override detected identity.

**VISA backend:** System VISA is the default and requires a separately installed
IVI runtime, such as Keysight IO Libraries or NI-VISA. Scopes Tool does not bundle
these runtimes or fall back to `@py`. Python installations and Windows packages
include PyVISA, `pyvisa-py`, `psutil`, and `zeroconf`. The latter two support
TCPIP/VXI-11 interface discovery and HiSLIP mDNS discovery; discovery depends on
the instrument and network.

Product Live support is limited to the exact model, transport, and backend
combinations in [Supported Models](docs/core/supported-models.md). PyVISA-py (`@py`)
Product operation is open only for DSOX4024A, DSOX4034A, and TBS2074 over TCPIP/LAN.
USB through `@py` is not Product-open; its separate PyUSB, libusb, and driver
requirements are not bundled. Bluetooth (`@bt`) and explicit custom backends are
not Product-open. Connection diagnostics do not imply Product authorization.
Simulation and supported dry-run operations do not open real instrument sessions.

## Features

- Operate through the CLI, Common v2 Worker, localhost-only browser WebUI, or
  Electron Desktop.
- Use registered Keysight DSOX2004A, DSOX3024A, DSOX4024A, DSOX4034A and Tektronix
  TBS2074, TDS2024B, TBS1052B models within their documented support scope.
- Configure acquisition, analog channels, timebase, and display settings; capture
  waveforms and screenshots; query measurements and statistics.
- Use model-dependent DVM, Math, FFT, WGEN, Reference, Trigger, Search, Serial,
  and segmented-memory operations.
- Run finite measurement, logging, periodic and triggered capture workflows,
  capture-until, capture-monitor, and Generic Sequence v1.
- Use hardware-free simulation and Core-planned dry-run where supported, with
  JSON, JSONL, CSV, and host-side capture artifacts for automation.
- Switch the WebUI/Desktop language between English and Traditional Chinese and
  choose System, Light, or Dark appearance; open bundled offline Help.
- Use the Windows onedir CLI, Launcher, and private Host with one shared Python
  runtime directory, alongside Electron Desktop with its own Electron/Chromium runtime.

Availability depends on the model, capability profile, and installed instrument
options. See [Supported Models](docs/core/supported-models.md) and the
[CLI README](docs/cli/README.md) for command and workflow limits.
Generic Sequence composes supported Core operations; it is not an arbitrary SCPI
macro facility.

## Project Structure

The root `pyproject.toml` defines the single distribution and Python version;
`desktop/package.json` must carry the same application version. In build examples,
`<version>` means `[project].version`.

```text
src/
  scopes_tool_core/
  scopes_tool_cli/
  scopes_tool_webui/
desktop/
examples/
tests/
  core/
  cli/
  packaging/
  webui/
  tooling/
docs/
  core/
  cli/
  webui/
  contracts/
  architecture/
  help/
scripts/
```

## Install

Python source development requires Python `>=3.10`. In PowerShell, enter the
repository root and prepare the environment:

```powershell
cd path\to\scopes-tool
py -m pip install --user uv
uv venv .venv
uv sync --all-extras --locked --link-mode=copy
```

To select a particular compatible interpreter, use `uv venv .venv --python 3.12`
when creating the environment. The committed `uv.lock` defines development and
CI dependencies. For only the browser WebUI dependencies, use
`uv sync --extra webui --link-mode=copy` instead of the all-extras sync.

Installation creates `scopes-tool`, `scopes-tool-webui`, and
`scopes-tool-webui-launcher` console commands. If an existing synchronized
Windows environment has missing or outdated wrappers, repair just the project:

```powershell
uv sync --all-extras --link-mode=copy --reinstall-package scopes-tool
```

For a prebuilt Windows x64 ZIP, extract the entire application directory and
keep its files together. Start `Scopes Tool.exe` for Desktop or
`scopes-tool-webui-launcher.exe` for the browser UI. The onedir package includes
Python, Electron, and Python dependencies; it does not require a separate Python
or Node.js installation. Live System VISA still needs an external VISA runtime.

## Quick Start

Run a safe CLI simulator smoke without hardware:

```powershell
.\.venv\Scripts\scopes-tool.exe identify --simulate --json
```

Start the local browser WebUI:

```powershell
.\.venv\Scripts\scopes-tool-webui-launcher.exe
```

The WebUI is localhost-only. The direct server defaults to `127.0.0.1:8025`.
Without an explicit port, the Launcher tries up to 100 ports for port-in-use or
permission-denied conflicts before offering manual port selection. The direct
server is also available as `.\.venv\Scripts\scopes-tool-webui.exe`.

For source-mode Electron Desktop, install Node.js 22.12 or newer and npm, prepare
the Python environment above, then run:

```powershell
Set-Location .\desktop
npm ci
npm start
```

Desktop presents the existing WebUI and waits for Host cleanup before exiting.
Use the language and appearance controls for English/Traditional Chinese and
System/Light/Dark themes. See the [WebUI README](docs/webui/README.md) for device,
resource, job, and artifact behavior.

Real hardware access is explicit: one-shot live commands require `--resource`
or `SCOPES_TOOL_RESOURCE`; live Workers require both `--live` and `--resource`.
Do not infer a VISA resource from these simulator examples.

## Built-in Help

Open the bundled offline CLI User Guide:

```powershell
.\.venv\Scripts\scopes-tool.exe user-guide
.\.venv\Scripts\scopes-tool.exe user-guide --lang zh-TW
```

The WebUI/Desktop **Help** button opens its offline User Guide in the selected
language. Guides include the supported-model reference and require no internet
connection. See [Help Maintenance](docs/help/README.md) before building packages.

## Build

Build the wheel and sdist with the development environment:

```powershell
.\.venv\Scripts\python.exe -m build
```

Windows packaging requires Windows x64 Python in `.venv`, PyInstaller, working
Tkinter/Tcl/Tk, and, for Desktop, Node.js 22.12 or newer with npm. Build either the
Python bundle or the complete Electron directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_bundle.ps1
# Alternatively, build Desktop (includes the Python bundle build):
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_desktop.ps1
```

The bundle is `dist\scopes-tool\`; the complete Desktop is
`dist\desktop\win-unpacked\`:

```text
Scopes Tool.exe
scopes-tool.exe
scopes-tool-webui-launcher.exe
scopes-tool-webui-host.exe
_internal\
resources\
... Electron runtime files
```

The three Python executables share a single root `_internal` directory. The
Electron Desktop resides in the same application directory, has its own
Electron/Chromium runtime, and uses the shared Python backend through the private
Desktop Host. The private Host is not a public CLI entry point. Builds replace
their existing bundle/Desktop output directories. Check the packaged CLI without
hardware using
`.\dist\scopes-tool\scopes-tool.exe identify --simulate --json`.

Build the versioned release artifacts:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

```text
release/<version>/
  scopes-tool-<version>-windows-x64.zip
  scopes_tool-<version>-py3-none-any.whl
  scopes_tool-<version>.tar.gz
  checksums.txt
```

The script reads the project version, requires the Electron version to match,
builds Python distributions and Desktop once, and wraps the merged Desktop in a
single `scopes-tool-<version>/` ZIP root. SHA-256 checksums cover the three
distributables. An existing version directory is rejected; use a fresh
`-ReleaseRoot` inside the repository for another build. The script does not
publish artifacts.

From a clean, fully committed HEAD, run the no-hardware acceptance gate:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\release-acceptance.ps1
```

Acceptance checks tools, lock consistency and application versions, invokes the
release build once, verifies artifact names, metadata, checksums and extracted
Desktop layout, installs wheel and sdist into separate clean environments,
checks imports, CLI help, simulation and bilingual offline Help, runs the existing
no-hardware CLI preflight, and verifies unchanged HEAD and source worktree.
It writes step results, failures, exit codes, timings, and captured command output
to a unique run under `.tmp_tests/release_acceptance/`. A custom `-OutputRoot`
must remain under repository `.tmp_tests`. Build intermediates use the existing
`build/` and `dist/` locations. Acceptance never discovers or opens live resources
and does not commit, tag, or publish.

The manual **Build Windows** Actions workflow offers Bundle/Desktop ZIPs as
30-day Actions artifacts. Conditional packaging CI builds Desktop or the release
layout once per job and runs packaged CLI smoke; it does not validate GUI
interaction or real instruments. Full acceptance remains a manual release gate.

## Test

Run focused checks from the repository root, with intentional artifacts in
`.tmp_tests/`:

```powershell
New-Item -ItemType Directory -Force .tmp_tests | Out-Null
.\.venv\Scripts\python.exe -m pytest tests\packaging -q --basetemp .tmp_tests\packaging
.\.venv\Scripts\python.exe -m ruff check src tests
```

Select the relevant Core, CLI, WebUI, or tooling tests for other changes. See
[Testing Guidelines](docs/testing-guidelines.md) for CI responsibilities and
hardware-free validation. Mock, simulator, and packaging tests do not establish
real-instrument support; live validation requires explicit opt-in and a
user-supplied VISA resource.

## Documentation

- CLI User Guide: [English](docs/cli/USER_GUIDE.md) / [繁體中文](docs/cli/USER_GUIDE.zh-TW.md)
- WebUI/Desktop User Guide: [English](docs/webui/USER_GUIDE.md) / [繁體中文](docs/webui/USER_GUIDE.zh-TW.md)
- Core README: [English](docs/core/README.md) / [繁體中文](docs/core/README.zh-TW.md)
- CLI README: [English](docs/cli/README.md) / [繁體中文](docs/cli/README.zh-TW.md)
- WebUI README: [English](docs/webui/README.md) / [繁體中文](docs/webui/README.zh-TW.md)
- Supported Models: [English](docs/core/supported-models.md) / [繁體中文](docs/core/supported-models.zh-TW.md)
- [Core Integration](docs/core/integration.md) and [CLI Integration](docs/cli/cli-integration.md)
- [Public Contracts](docs/contracts/), including [CLI JSONL](docs/contracts/scopes-cli-jsonl-contract.md),
  [Worker](docs/contracts/scopes-worker-contract.md), and [Workflow orchestration](docs/contracts/scopes-orchestrator-workflows.md)
- [Repository Layout](docs/architecture/monorepo-layout.md),
  [WebUI Change Rules](docs/webui/web-ui-change-rules.md), and [Help Maintenance](docs/help/README.md)

## Contributing

Read [Agent Instructions](AGENTS.md) and [Testing Guidelines](docs/testing-guidelines.md)
before changing behavior. Keep Core independent of CLI/WebUI, preserve public
contracts, and use simulator or fake-instrument checks by default. Changes to
instrument operations and live support require the applicable safety review and
explicitly authorized validation. Keep temporary validation artifacts out of
tracked public documentation.

## License and Disclaimer

This project is licensed under the MIT License. See [LICENSE](LICENSE).

The Scopes Tool application icon was generated with OpenAI image generation in
ChatGPT, then reviewed and selected by the project maintainer.

This project is independent and unofficial. It is not affiliated with, endorsed
by, sponsored by, or officially recognized by instrument manufacturers.

All manufacturer names, model names, product names, and trademarks remain the
property of their respective owners.

Users are responsible for complying with applicable vendor software, driver,
instrument, and documentation license terms.
