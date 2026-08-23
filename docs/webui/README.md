# Scopes Tool WebUI

The Scopes Tool WebUI is a localhost-only browser adapter over
`scopes_tool_core`. It does not import or depend on the CLI adapter, and it
does not own VISA, SCPI, instrument identity, capability, or safety behavior.

Import package: `scopes_tool_webui`

Maintainers should read [WebUI Change Rules](web-ui-change-rules.md) before
changing command exposure, browser state, capability presentation, or result
behavior.

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
- Core/CLI raw `list-resources` remains available as host VISA resource
  discovery. WebUI Scan Device is a separate Live-mode-only action that
  requests `live_only` discovery with bounded `*IDN?` probes.
- Simulate and Dry-run do not use WebUI Scan Device. Resource discovery does
  not require a selected Live resource or instrument lock.

## Basic Controls and Commands

Basic Controls provides Run, Stop, Single, and Screenshot. These are
shortcuts that submit the same command jobs used by the Command workbench.

The Command workbench exposes:

- Identity: `identify` (Read device information)
- Acquisition: `run`, `single`, `stop-acquisition`, `acquisition`
- Timebase: `timebase-scale`, `timebase-position`
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
- Save / Export: a dedicated editor with Path / Filename, Image, and Waveform
  groups over `save-pwd`, `save-filename`, `save-image-format`,
  `save-image-palette`, `save-image-ink-saver`, `save-image-factors`,
  `save-image`, `save-waveform-format`, `save-waveform-length`,
  `save-waveform-length-max`, and `save-waveform`
- System: `check-error`, `system-status-byte`, `system-operation-status`,
  `system-clear-status`, `system-opc`, `system-standard-event`,
  `system-options`
- DVM: `dvm-enable`, `dvm-source`, `dvm-mode`, `dvm-auto-range`,
  `dvm-current`, `dvm-query`
- FFT / MATH: basic `fft`, `math-display`, `math-vertical`, `math-operator`,
  `math-composite-source`, `math-clear`
- Trigger: a dedicated Trigger editor over the existing Edge, external,
  glitch/pulse-width, runt, transition, delay, setup/hold, edge-burst, TV,
  pattern/OR, sweep, reject, coupling, and holdoff commands
- Search: a dedicated Search editor covering Basic Search state, mode, and
  count, capability-gated Search event navigation, and Serial Search over
  UART/I2C/SPI/CAN with Bus and Protocol selection
- Serial: a dedicated mode-aware Serial editor covering bus selection, Serial
  Mode, Serial Display, UART/I2C/SPI/CAN configuration and triggers, and a
  protocol-independent Serial Lister section (display, reference, and
  host-side export), plus `serial-query`
- Segmented Memory: `segmented-memory` and `segmented-capture`
- Workflow: `capture-batch`, `measure-log`, `measure-until`,
  `triggered-measure-loop`, and `triggered-capture-series`

Resource scanning uses the internal `list-resources` command. Its jobs remain
in Result History, but it is not shown in the Command workbench.

The Command Browser keeps Category as its first level. Categories with group
metadata (Trigger, Search, Serial, Save / Export, and Workflow) show
Category → Group → Commands sections, while categories without group metadata
keep the plain Category → Commands list. Groups start expanded and can be
collapsed and reopened; collapse state lives only in the current page session
and resets to all-expanded after a reload. The command filter still applies
only to the active category. While a filter matches commands in a group, that
group temporarily stays expanded; clearing the filter restores the previous
collapse state. Selecting a command inside a collapsed group expands that
group first.

Grouping is presentation only: it does not change Core command semantics,
model or capability gating, or the metadata-driven forms. Dedicated editors
use the existing groups where described below.

Selecting `measure-log` or `triggered-measure-loop` opens the dedicated
Workflow editor. It provides model-projected analog channel and measurement
choices, channel-pair rows, shared pair measurements, and the command's
existing run limits. Selection and editing are browser-local and passive;
Run submits one job through the shared foreground execution admission. The
`capture-batch`, `measure-until`, and `triggered-capture-series` commands keep
their metadata-driven Generic Form.

Selecting a Trigger command opens the dedicated Trigger editor instead of a
plain command form. The Command Browser remains the only Trigger navigation:
Category → Group → Commands. The editor does not add a second set of tabs.
Selecting any command inside a group opens that whole group on the right (for
example, selecting any Edge command shows Edge trigger, source, slope, level,
coupling, and reject together; selecting Runt shows only Runt), and the group
label above the sections names the group being edited. The editor presents the
group's existing settings for editing; it does not report or change which
trigger type the instrument currently uses. Selection and query-selector
changes are presentation-only. Explicit Refresh reads only the active group's
setting commands, and a successful Apply is followed by an active-group
readback so sibling forms do not go stale. Editor reads and applies are
serialized; Apply and Refresh stay
disabled until the current readback or write finishes. Each child command
keeps its own metadata-driven form and its own independent Apply over the
existing WebUI command; there is no Apply All, no transaction, and no merged
payload. Informational commands such as `external-trigger-settings` keep their
explicit Read action. Switching commands or groups discards unapplied edits
without confirmation, and manual Refresh re-reads the active group while
keeping unapplied edits. Model capability presentation continues to come from
the shared Core capability projection; unsupported commands stay disabled in
the Command Browser and are omitted from the group view.

Selecting a Search command opens the dedicated Search editor instead of a
plain command form. The Command Browser groups remain Basic, Event, and
Serial; the editor adds no second tab layer. Basic shows Search State and
Search Mode as independent read-edit-Apply settings plus a read-only Search
Count that is refreshed with the group. Explicit Refresh in Basic reads only
these three commands. Event exposes capability-gated event navigation: models
without Search event navigation show an unavailable note instead of controls,
a reported current event of 0 displays verbatim as readback, and Apply keeps
the existing Core validation rather than turning a displayed 0 into an editable
target. Selecting any Serial Search command opens the Serial Search view with
a Bus selector projected from the model's serial bus count and a Protocol
selector whose UART/I2C/SPI/CAN availability comes from the existing model
projection; the clicked command chooses the initial protocol. Switching Bus or
Protocol discards unapplied edits and changes presentation without querying;
explicit Refresh reads only the active protocol. A Serial Search Apply submits
exactly one existing `serial-search-*`
write with the selected bus and the metadata-driven criteria form — no separate
`search-state`/`search-mode` writes and no Serial decode mode recheck — then
runs `search-state`, `search-mode`, and the active criteria query again for
reconciliation. There is no Apply All, transaction, frontend capability
database, or SCPI generation in the editor, and non-Serial Search criteria
editors remain out of scope.

Selecting a Serial bus/mode/display/configuration/trigger/lister command opens
the dedicated Serial editor instead of a plain command form. The editor
projects the model's serial bus count and available protocols from Core
capabilities, shows the current protocol reported by the instrument, and
offers only UART, I2C, SPI, and CAN with an explicit Apply Mode action.
Configuration and Trigger queries run only after `serial-mode` readback
confirms the bus is in that protocol; when the bus reports another recognized
protocol such as LIN, FlexRay, or A429, the editor shows the current protocol
with an unsupported-configuration note instead of issuing protocol-specific
reads. The Protocol selector follows the protocol confirmed by the latest
readback. Mode, Display, each protocol Configuration, and the matching
Trigger remain separate Apply operations over the existing commands; an
Apply Trigger re-checks `serial-mode` first and skips stale writes the same
way as configuration applies. Switching Bus asks for confirmation before
discarding any unapplied Display/Configuration/Trigger edits, and applying a
different protocol asks before discarding old-protocol Configuration or
Trigger edits. Bus and Protocol navigation does not query the instrument;
explicit Refresh performs the existing mode, display, active-protocol, trigger,
and lister read sequence. A configuration Apply first re-checks `serial-mode` and skips
the write when the instrument no longer reports the expected protocol. The
Serial Lister section is independent of protocol and Bus: its state is
refreshed through the existing aggregate `serial-lister-query`, display and
reference settings apply through their existing commands, and Export performs
the existing host-side raw CSV retrieval with its registered job artifact.

Selecting a Save / Export command opens the dedicated Save / Export editor
instead of a plain command form. The Command Browser remains the only
navigation and keeps the Path / Filename, Image, and Waveform groups; the
editor adds no second tab layer. Selecting any command shows its whole group.
Selection is presentation-only. Explicit Refresh reads `save-pwd` and
`save-filename` for Path / Filename; Image reads its format, palette, ink-saver,
and measurement-factor settings; Waveform reads its format and length settings
plus the read-only maximum-length state. Each setting
keeps an independent Apply over its existing command, and a successful Apply
is followed by an active-group readback that preserves unapplied sibling
edits. The editor shows readback progress and identifies settings whose current
value could not be read; after a failed read, an operator can retry the group
or enter and apply a new value manually. There is no Apply All, merged payload,
transaction, or rollback.

Save Image and Save Waveform each require their own explicit filename and
submit only their existing instrument-side Save command. They do not inherit
or update `save-filename`; the editor makes this filename separation explicit.
They do not add filename extensions, refresh unrelated settings, or create
WebUI download artifacts. Screenshot and Capture remain separate host-side
retrieval paths that register downloadable artifacts.

The command form uses simple metadata-driven controls for ordinary values,
enums, numbers, booleans, multi-select lists, and small conditional field
groups. For `measure-log` and `triggered-measure-loop`, the dedicated Workflow
editor provides structured Source and Reference pair rows and shared
pair-measurement choices. `capture-batch`, `measure-until`, and
`triggered-capture-series` remain metadata-driven Generic Forms. Trigger,
Search, Serial, Segmented Memory, and Workflow commands use only the
conditional visibility needed by their existing Core parameter semantics.

Commands that expose the existing Core `query` / `set` contract as an
instrument setting use a read-edit-Apply workflow in the browser. Command
selection and presentation-only navigation are passive. Refresh explicitly
reads current state, Apply submits the existing set action, and the set result's
Core readback refreshes the editor. Unsaved field edits are not overwritten by
later readback. Information and diagnostic commands
remain explicit Read or Run actions.

Model-aware command availability and field limits are projected from Core
capabilities. Live uses the detected physical model; Simulate and Dry-run use
the selected planning model. The command workspace shows the latest successful
result for that exact command and execution context, while Result History and
raw Result Detail retain the full job and diagnostic views.

Timebase scale and position use the same read-edit-Apply-verification pattern.
Core does not currently expose public Timebase mode or reference controls, so
the WebUI does not invent them. Display persistence uses explicit Minimum,
Infinite, and Timed modes instead of requiring a magic string.

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

## Core coverage boundary

The Command workbench intentionally exposes operator-facing settings,
captures, finite workflows, and structured information commands that have a
clear browser interaction. Resource discovery uses the hidden
`list-resources` helper, while `identify` remains the visible Read device
information command.

Advanced or diagnostic CLI paths are not automatically browser commands.
Current intentional omissions include direct SCPI sending, setup recall/save,
autoscale and broad cleanup operations, worker/doctor/hardware-report tooling,
Generic Sequence editing, Cursor and Annotation editors, WGEN controls,
advanced measurement sweeps/statistics, and advanced FFT/Math
transform/filter/visualization controls. Acquisition points, record length,
sample rate, and similar low-level information remain CLI/Core paths until a
coherent WebUI presentation is defined. These omissions avoid exposing a Core
operation without an appropriate interaction, capability, and result model.
Basic FFT unit and window values remain Core-validated text until Core exposes
public option metadata that the WebUI can project without duplicating it.

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
