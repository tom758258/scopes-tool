# Scopes Tool WebUI

The Scopes Tool WebUI is a localhost-only browser adapter over
`scopes_tool_core`. It does not import or depend on the CLI adapter, and it
does not own VISA, SCPI, instrument identity, capability, or safety behavior.

Import package: `scopes_tool_webui`

## Installation

Install the optional WebUI dependencies from a source checkout:

```powershell
uv pip install -e ".[webui]"
```

The extra provides FastAPI and Uvicorn. The WebUI remains part of the single
`scopes-tool` distribution.

## Start the WebUI

The server entry point binds directly to `127.0.0.1:8025` by default. A fixed
server port fails if it is unavailable:

```powershell
scopes-tool-webui
scopes-tool-webui --port 8030
```

The English Tk Launcher is the recommended local browser entry point:

```powershell
scopes-tool-webui-launcher
scopes-tool-webui-launcher --port 8030
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

- Live requires an explicit VISA resource. A model selection never overrides
  live physical identity; Core obtains identity from the instrument `*IDN?`.
- Simulate and Dry-run use an explicitly registered Core model profile. The
  default planning model is `keysight-dsox4024a`.
- Resource scanning uses Core VISA discovery and is a host discovery job; it
  does not require a selected Live resource or instrument lock.

## Basic Controls and Commands

Basic Controls provides Identify, Run, Stop, Single, and Screenshot. These are
shortcuts that submit the same command jobs used by the Command workbench.

The P2 Command workbench exposes:

- Identity: `identify`
- Acquisition: `run`, `single`, `stop-acquisition`, `acquisition`
- Channel: `channel-display`, `channel-scale`
- Measurement: `measure`
- Capture: `screenshot`, `capture`
- System: `check-error`, `system-status-byte`, `system-operation-status`
- Device: `list-resources`

The command form uses simple metadata-driven controls for ordinary values,
enums, numbers, and booleans. Complex conditional editors for Trigger,
Search, Serial, Segmented Memory, and Workflow commands are not included.

Dry-run is intentionally limited to host VISA discovery plus Core-planned
acquisition **query**, measurement, and waveform capture operations. Dry-run
acquisition `set` is rejected before a job is queued. Dry-run does not open an
instrument backend. Simulate uses Core's deterministic simulator; Live opens
the explicit resource through Core.

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
can be downloaded through the job result. Artifact downloads are limited to
files registered by that job.

## Language and current limitations

The browser UI supports English and Traditional Chinese (`zh-TW`). The
selected locale is remembered locally. The Launcher itself is English-only.
Command IDs, model IDs, VISA resources, SCPI, JSON keys, and raw diagnostics
remain unchanged.

P2 does not include remote access, authentication, multi-instrument sessions,
WebSockets/SSE, live waveform streaming, Live Data monitoring, dark mode,
Electron/onedir packaging, or the later complex command editors.
