# Scopes Tool WebUI

The Scopes Tool WebUI is a localhost-only browser adapter over
`scopes_tool_core`. It does not import or depend on the CLI adapter, and it
does not own VISA, SCPI, instrument identity, capability, or safety behavior.

Import package: `scopes_tool_webui`

## Installation

From the repository root, create or reuse the local virtual environment and
install the optional WebUI dependencies:

```powershell
uv venv .venv
uv sync --extra webui --link-mode=copy
```

The extra provides FastAPI and Uvicorn. The WebUI remains part of the single
`scopes-tool` distribution.

## Start the WebUI

The server entry point binds directly to `127.0.0.1:8025` by default. A fixed
server port fails if it is unavailable:

```powershell
.\.venv\Scripts\scopes-tool-webui.exe
.\.venv\Scripts\scopes-tool-webui.exe --port 8030
```

The Launcher is the recommended local browser entry point:

```powershell
.\.venv\Scripts\scopes-tool-webui-launcher.exe
.\.venv\Scripts\scopes-tool-webui-launcher.exe --port 8030
```

Without an explicit port, the Launcher tries up to 100 ports beginning at
8025. It automatically falls back only for port-in-use conflicts, waits for
`GET /api/health` to verify the `scopes-tool-webui` service identity, and opens
the browser only after readiness succeeds. If all automatic candidates are
unavailable, it provides a manual-port fallback. An explicit `--port` is
fixed unless `--auto-port` is also supplied.

Remote binding is not supported.

## Device and Resource

The default execution mode is **Live**. Open the settings gear in the
Device / Resource panel to select Live, Simulate, or Dry-run.

- Live requires an explicit VISA resource. The detected model is read-only;
  Core obtains identity from the instrument `*IDN?` and uses it for capability
  validation.
- Simulate and Dry-run use an explicitly registered Core model profile. The
  default planning model is `keysight-dsox4024a`.
- Resource scanning uses Core VISA discovery and is a host discovery job; it
  does not require a selected Live resource or instrument lock.

## Basic Controls and Commands

Basic Controls provides Run, Stop, Single, and Screenshot. These are
shortcuts that submit the same command jobs used by the Command workbench.

The Command workbench exposes:

- Identity: `identify` (Read device information)
- Acquisition: `run`, `single`, `stop-acquisition`, `acquisition`
- Channel: `channel-display`, `channel-scale`, `channel-summary`,
  `channel-label`, `channel-offset`, `channel-coupling`, `channel-probe`,
  `channel-bandwidth-limit`, `channel-impedance`, `channel-invert`,
  `channel-range`, `channel-units`, `channel-vernier`, `channel-probe-skew`
- Display: `display-label`, `display-clear`, `display-persistence`,
  `display-intensity`, `display-vectors`
- Measurement: `measure`, `measure-results`, `measure-clear`, `measure-show`,
  `measure-source`, `measure-window`
- Capture: `screenshot`, `capture`
- Reference: `reference-save`, `reference-display`, `reference-label`,
  `reference-clear`, `reference-query`
- Save / Export: `save-pwd`, `save-filename`, `save-image-format`,
  `save-image-palette`, `save-image-ink-saver`, `save-image-factors`,
  `save-image`, `save-waveform-format`, `save-waveform-length`,
  `save-waveform-length-max`, `save-waveform`
- System: `check-error`, `system-status-byte`, `system-operation-status`,
  `system-clear-status`, `system-opc`, `system-standard-event`,
  `system-options`
- DVM: `dvm-enable`, `dvm-source`, `dvm-mode`, `dvm-auto-range`,
  `dvm-current`, `dvm-query`
- FFT / MATH: basic `fft`, `math-display`, `math-vertical`, `math-operator`,
  `math-composite-source`, `math-clear`
- Trigger: Edge, external, glitch/pulse-width, runt, transition, delay,
  setup/hold, edge-burst, TV, pattern, OR, sweep, reject, coupling, and
  holdoff commands
- Search: basic Search state/mode/event/count and UART/I2C/SPI/CAN serial
  Search commands
- Serial: query/mode/display, UART/I2C/SPI/CAN configuration and triggers,
  and Serial Lister query/display/reference/export
- Segmented Memory: `segmented-memory` and `segmented-capture`
- Workflow: `capture-batch`, `measure-log`, `measure-until`,
  `triggered-measure-loop`, and `triggered-capture-series`

Resource scanning uses the internal `list-resources` command. Its jobs remain
in Result History, but it is not shown in the Command workbench.

The command form uses simple metadata-driven controls for ordinary values,
enums, numbers, booleans, and small conditional field groups. Trigger,
Search, Serial, Segmented Memory, and Workflow commands use only the
conditional visibility needed by their existing Core parameter semantics.

The added instrument-setting commands use Live or Simulate mode and the
existing Core capability and validation boundaries. They do not add new
WebUI-specific SCPI behavior. The basic FFT and Math commands use flat forms;
operation-dependent Math transform, filter, and visualization controls remain
outside the current command workbench.

Dry-run is intentionally limited to host VISA discovery plus Core-planned
acquisition **query**, measurement, and waveform capture operations. Dry-run
acquisition `set` is rejected before a job is queued. The additional instrument
commands are not advertised in Dry-run because no corresponding Core planner
exists. Dry-run does not open an instrument backend. Simulate uses Core's
deterministic simulator; Live opens the explicit resource through Core.

## Jobs, results, and artifacts

Command submission returns a job ID. The browser polls job status through the
WebUI API. Jobs report `queued`, `running`, `completed`, `failed`, or
`cancelled` and expose structured Core results, errors, and diagnostic lines.

Only queued jobs can be cancelled. Running VISA I/O is not forcibly
interrupted. When the Launcher is closed, it first stops accepting jobs,
cancels queued jobs, and waits for running jobs to finish and close their own
sessions before stopping Uvicorn. This shutdown has a timeout; if jobs do not
finish or a session close fails, the Launcher displays **Shutdown incomplete**
and remains available so Quit can be retried. No implicit Safe Cleanup is run.
Screenshot and waveform capture jobs register their generated artifacts, which
can be downloaded through the job result. Instrument-side `save-image` and
`save-waveform` commands return the Core save result but do not create host
WebUI artifacts. Artifact downloads are limited to files registered by that
job.

## Language and current limitations

The browser UI supports English and Traditional Chinese (`zh-TW`). The
selected locale is remembered locally. The Launcher itself is English-only.
Command IDs, model IDs, VISA resources, SCPI, JSON keys, and raw diagnostics
remain unchanged.

The WebUI does not include remote access, authentication, multi-instrument
sessions, WebSockets/SSE, live waveform streaming, Live Data monitoring, dark
mode, Electron/onedir packaging, Generic Sequence editing, advanced FFT/Math
transform/filter/visualization editors, or conditional editors for features
not exposed by the current Core APIs. Dry-run remains limited to commands with
existing Core planners; `capture-batch` and `measure-log` are Live/Simulate
only.
