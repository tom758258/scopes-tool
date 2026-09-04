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

Basic Controls provides Run, Stop, Single, Single + Wait, Force Trigger, and
Screenshot. These are shortcuts that submit the same command jobs used by the
Command workbench. The Single + Wait shortcut uses the command defaults: 5.0 s
timeout, 100 ms polling, and force-on-timeout disabled.
It also owns the WebUI's single **PC output folder** setting. A blank input uses
the default `data` root. **Select Folder** opens the Windows folder picker and
leaves the current value unchanged when cancelled. **Open Folder** creates the
effective folder when needed and opens it through the Windows shell; this is the
primary WebUI entry point for viewing host-side outputs. The value is
browser-session state only and is snapshotted when each job is submitted.

The setting applies to host-side artifacts created by `screenshot`, `capture`,
`serial-lister-export`, `segmented-capture`, `capture-batch`, `capture-until`,
`capture-monitor`, `measure-log`, `measure-until`,
`triggered-measure-loop`, `triggered-capture-series`, and `sequence`.
Their command workspaces show the current shared folder but do not add another
path control. Serial Lister Export accepts a filename only; its WebUI field
cannot select or escape the shared folder.

Command Workbench Single + Wait supports Live and Simulate. Trigger timeout is
shown in seconds and defaults to 5.0 s; force-on-timeout is an unchecked
checkbox. The Advanced disclosure is closed by default and contains only the
100 ms poll interval. Validation requires a finite positive timeout that maps
to at least 1 ms and a positive poll interval no greater than the timeout. The
result is command status using the existing trigger-wait fields and has no
artifacts.

Autoscale is an explicit Live/Simulate state-changing command. Source Channels,
Acquire mode (`normal` or `current`), and Channels mode (`all` or `displayed`)
are optional. Source Channels accepts only model-supported analog channel
numbers; leaving it unset runs Autoscale without an explicit source list. When
sources are selected, the instrument enables those sources, hides the others,
and performs Autoscale using displayed channels. Autoscale can change channel
display/scaling, timebase/delay, and trigger level, and may turn off cursors,
measurements, Math waveforms, and reference waveforms. The WebUI adds no
readback, rollback, or browser-side SCPI behavior for this operation.

The Command workbench exposes:

- Identity: `identify` (Read device information)
- Acquisition: `run`, `single`, `single-wait`, `stop-acquisition`,
  `force-trigger`, `autoscale`, `acquisition`
- Timebase: `timebase-scale`, `timebase-position`, `timebase-reference`
- Channel: `channel-display`, `channel-scale`, `channel-summary`,
  `channel-label`, `channel-offset`, `channel-coupling`, `channel-probe`,
  `channel-bandwidth-limit`, `channel-impedance`, `channel-invert`,
  `channel-range`, `channel-units`, `channel-vernier`, `channel-probe-skew`
- Display: `display-label`, `display-clear`, `display-persistence`,
  `display-intensity`, `display-vectors`
- Measurement: Single Measurement combines `measure` with the persistent
  `measure-window` setting. Multiple Measurements runs selected measurements across
  model-projected analog channels and optional channel pairs, with Dry-run
  using the existing Core planner. Front Panel Measurements combines
  `measure-install`, `measure-results`, `measure-show`, and `measure-clear` for
  installing one measurement at a time and managing the instrument's displayed
  measurements and measurement markers. The same workspace also offers an
  explicit action that opens the instrument Measurement menu (`measure-menu`). A successful install refreshes the
  displayed results when batch result queries are supported; installation
  remains available on models without that query capability.
  On capability-supported 3000X and 4000X models, the same workspace also
  exposes Advanced Measurement Statistics with Results Mode fixed to All:
  independent instrument statistics display, Infinite or 2..2000 maximum
  count, relative standard deviation, reset, explicit refresh, and the
  instrument-accumulated statistics table. Refresh is read-only, and Apply is
  available after a successful readback. It does not poll automatically or
  compute statistics in the browser. The 2000X profile does not expose this
  section.
  Measurement markers are always on for 2000X/3000X models; 4000X models
  support showing or hiding them. The `measure-source`
  backend helper remains available to existing API clients but is not shown in
  the normal workbench.
- Capture: `screenshot`, `capture`
- Reference: a single Reference waveform workspace over `reference-save`,
  `reference-display`, `reference-label`, `reference-clear`, and
  `reference-query`
- Save / Export: a single workspace with Path / Filename, Image, Waveform,
  and Setup sections over `save-pwd`, `save-filename`, `save-image-format`,
  `save-image-palette`, `save-image-ink-saver`, `save-image-factors`,
  `save-image`, `save-waveform-format`, `save-waveform-length`,
  `save-waveform`, `setup-save`, and `setup-recall`
  (`save-waveform-length-max` remains an underlying
  query-only operation; the WebUI does not query or configure it and only
  displays the maximum-length-mode limitation; `setup-save` and `setup-recall`
  remain hidden from the Command Browser and are owned by the workspace)
- System: `check-error`, `system-status-byte`, `system-operation-status`,
  `system-clear-status`, `system-opc`, `system-standard-event`,
  `system-options`
- DVM: `dvm-enable`, `dvm-source`, `dvm-mode`, `dvm-auto-range`,
  `dvm-current`, `dvm-query`
- FFT / MATH: capability-driven `fft` with basic controls on all supported
  models and Advanced FFT controls on 4000X, plus `math-display`,
  `math-vertical`, `math-operator`, `math-transform`, `math-filter`,
  `math-visualization`, `math-composite-source`, and `math-clear`
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
- Segmented Memory: a dedicated state view for explicit Refresh, Enter, Exit,
  segment selection, and current Time Tag readback over `segmented-memory`,
  plus `segmented-capture`
- Cursor: a dedicated Cursor editor for explicit Refresh, manual cursor
  configuration over `cursor` (query, set, off), and current state readback
- Annotation: a dedicated Annotation editor for explicit Refresh, annotation
  text/color/background editing, on/off/clear actions, and current state
  readback over `annotation`, with slot and position controls projected from
  Core capabilities
- WGEN: a dedicated Waveform Generator editor for explicit Refresh through the
  aggregate `wgen-query` and independent output, function, frequency,
  amplitude, offset, and load settings; settings never switch the output on
- DEMO: a dedicated Demo Signals editor for explicit Refresh through the
  aggregate `demo-query` and independent output, function, and phase settings;
  function options are projected from the model's `demo_functions` capability
  and settings never switch the output on
- Workflow: `capture-batch`, `capture-until`, `capture-monitor`, `measure-log`,
  `measure-until`, `triggered-measure-loop`, and
  `triggered-capture-series`, plus Generic Sequence v1 under Automation

Resource scanning uses the internal `list-resources` command. Its jobs remain
in Result History, but it is not shown in the Command workbench.

The Command Browser keeps Category as its first level. Categories with group
metadata (Trigger, Search, Serial, Workflow, Cursor, Annotation, WGEN, and
DEMO) show
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

Selecting Reference waveform opens one workspace for saving and comparing a
source channel with a selected reference waveform. Save and display runs the
existing `reference-save` command, then `reference-display` only after the save
completes, and finally refreshes display and label state with `reference-query`.
The shared reference waveform selector is visible before Live identity is
available and is then limited by the detected model's projected capabilities.
Selection is passive; explicit Refresh reads only display and label state for
the selected waveform. Display, Label, and Clear remain independent actions
through the normal foreground execution path.

Selecting `measure-log`, `triggered-measure-loop`, `capture-batch`,
`measure-until`, `capture-until`, `capture-monitor`, or
`triggered-capture-series` opens the dedicated Workflow editor. `measure-log`
and `triggered-measure-loop` provide model-projected channel and measurement
choices, channel-pair rows, shared pair measurements, and the command's existing
run limits.
`capture-batch`, `measure-until`, and `triggered-capture-series` use the same
dedicated editor with their workflow-specific configuration panels. Capture
Until provides selected capture channels, a condition channel limited to that
selection, points, format, one metric/operator/threshold, `1..255` matches, one
whole-workflow timeout, and a relative interval. A match saves the exact
multi-channel acquisition that was evaluated; it does not capture again.

Capture Monitor provides channels, points, format, finite capture count,
relative interval, retention points, and **Save results to files**. Before a
run, the editor explains that the retained waveform is bounded per channel,
overflow drops oldest complete captures, metrics cover all observed samples,
the plot and saved CSV cover only retained history, and repeated acquisitions
are not a continuous time-domain waveform. Saving is enabled by default;
disabling it runs without host-side workflow artifacts. Selection and editing
are browser-local and passive; Run submits one job through shared foreground
execution admission.

Selecting Sequence under Workflow / Automation opens the Generic Sequence v1
editor. It loads and saves `.sequence.json`/JSON documents and edits the seven
Core actions `wait`, `single`, `wait-trigger`, `measure`, `capture`,
`screenshot`, and `cleanup`. Load, Save, and Execute validate through Core;
dry-run delegates to `plan_sequence()`, while Live and Simulate delegate to
`run_sequence()` through the normal job, progress, cancellation, result, and
artifact infrastructure. The editor exposes `Save results to files` (default
enabled, using `field.save_results`); when disabled no host-side run
directory, manifest, or `scpi.log` is created and the result shows no `Files`,
`Output dir`, `Manifest`, or `SCPI log` paths. This disabled mode is not
supported when the document contains `capture` or `screenshot` steps. The editor
does not execute steps itself and does not provide arbitrary SCPI.

Documents use `1..255` steps and `loop_count` `1..255`, with at most 65,025
total step executions. A document may contain at most 10 combined capture and
screenshot steps per loop, which naturally permits at most 2,550 such
executions at 255 loops. These are Scopes Tool product limits, not oscilloscope
hardware limits.

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
the existing host-side raw CSV retrieval with its registered job artifact. Its
filename-only field writes under the PC output folder selected in Basic
Controls and fails rather than overwriting an existing file with that name.

Selecting a Cursor, Annotation, WGEN, or DEMO command opens the matching dedicated
editor instead of a plain command form. The Command Browser remains the only
navigation; the editors add no second tab layer. Cursor offers explicit
Refresh, manual cursor configuration (source channel, X1/X2, optional Y1/Y2),
Off, and current state readback (mode, positions, deltas, and DYDX where the
instrument reports it). Annotation offers explicit Refresh, text/color/
background editing, on/off/clear actions, and current state readback; the slot
selector is hidden on single-slot models and X/Y position controls appear only
where Core capabilities report position support. WGEN Refresh reads the whole
generator state through the single aggregate `wgen-query`; output, function,
frequency, amplitude, offset, and load each keep an independent Apply over
their existing command, and applying a setting never switches the output on.
DEMO Refresh reads the whole DEMO state through the single aggregate
`demo-query`; output, function, and phase each keep an independent Apply over
their existing command, and applying a setting never switches the output on.
Unsupported commands stay disabled in the Command Browser with the existing
capability reason.

Selecting Save / Export opens one workspace with Default save location, Image,
Waveform, and Setup sections. The underlying commands remain available to the
workspace but are hidden from the Command Browser. Selection is
presentation-only. Explicit Refresh serially reads every readable setting
in the Default save location, Image, and Waveform sections without running
Save Image or Save Waveform
(`save-waveform-length-max` is not queried; the WebUI only displays the
maximum-length-mode limitation). Setup has no readback. Entering Setup
performs no instrument I/O, and Reload instrument settings is unavailable
in Setup mode. Each setting
keeps an independent Apply over its existing command, and a successful Apply
is followed by its existing group readback that preserves unapplied sibling
edits. The editor shows readback progress and identifies settings whose current
value could not be read; after a failed read, an operator can retry the
workspace or enter and apply a new value manually. There is no Apply All,
merged payload, transaction, or rollback.

Save Image and Save Waveform each require their own explicit filename and
submit only their existing instrument-side Save command. They do not inherit
or update `save-filename`; the editor makes this filename separation explicit.
They do not add filename extensions, refresh unrelated settings, or create
WebUI download artifacts. Screenshot and Capture remain separate host-side
retrieval paths that register downloadable artifacts. The Basic Controls PC
output folder does not change `save-pwd`, `save-filename`, or any other
instrument-side `:SAVE:*` behavior.

Setup targets an instrument slot (0 through 9) or an instrument-side file
such as `\usb\baseline.scp`. Setup files do not use the shared Save PWD or
Filename. Save Setup is an explicit action. Recall Setup asks for
confirmation first because it replaces the oscilloscope's current setup.
Like other saves, setup targets are instrument-side storage, not PC downloads.

The command form uses simple metadata-driven controls for ordinary values,
enums, numbers, booleans, multi-select lists, and small conditional field
groups. Multiple Measurements uses the Measurement editor for model-projected channel
and measurement choices, structured Source and Reference pair rows, and shared
pair-measurement choices. For `measure-log` and `triggered-measure-loop`, the
dedicated Workflow editor provides the corresponding workflow controls.
Periodic Capture (`capture-batch`), Measure Until, and Triggered Capture Series
use the dedicated Workflow editor. Trigger, Search, Serial, Segmented Memory,
Workflow, Cursor, Annotation, WGEN, and DEMO commands use only the conditional
visibility needed by their existing Core parameter semantics.

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

Timebase scale, position, and reference use the same
read-edit-Apply-verification pattern. Reference accepts Left, Center, or Right.
Core does not currently expose public Timebase mode controls, so the WebUI does
not invent them. Display persistence uses explicit Minimum, Infinite, and Timed
modes instead of requiring a magic string.

The added instrument-setting commands use Live or Simulate mode and the
existing Core capability and validation boundaries. They do not add new
WebUI-specific SCPI behavior. FFT and Math commands use flat forms.
The 4000X FFT form projects the Core-owned operation, start/stop, gate, phase
reference, and detector controls by capability. Math transform, filter, and
visualization also use flat metadata-driven forms. Their operation and source
choices come from Core constants and model capabilities. 2000X/3000X Trend
uses source and measurement fields, while 4000X Trend selects an existing
measurement slot. Cascaded Math sources remain subject to Core's lower-numbered
function rule.

Dry-run is intentionally limited to host VISA discovery plus Core-planned
acquisition **query**, measurement, measurement sweep, and waveform capture
operations. Dry-run
acquisition `set` is rejected before a job is queued. The additional instrument
commands are not advertised in Dry-run because no corresponding Core planner
exists. Dry-run does not open an instrument backend. Simulate uses Core's
deterministic simulator; Live opens the explicit resource through Core.

## Live Data

Live Data keeps the existing WebUI, command, and Live status indicators and
adds a small read-only summary of analog channels, horizontal settings, and
the common trigger state. **Refresh** is an explicit foreground action that
uses the same Core-backed job admission as other commands. Live requires a
selected resource with confirmed identity, Simulate uses the Core simulator,
and Dry-run reports the summary as unavailable.

The summary is cleared when its mode, resource, detected model, or planning
model changes. A failed refresh leaves the previous successful summary visible
for the same context. Live Data does not poll automatically or stream waveform
data.

## Jobs, results, and artifacts

Command submission returns a job ID. The browser polls job status through the
WebUI API. Jobs report `queued`, `running`, `completed`, `failed`, or
`cancelled` and expose structured Core results, errors, and diagnostic lines.
Measurement workflows present a compact status/count summary and their final
measurement in Result. Their complete sample history is not copied into the
terminal job result; when saving is enabled, existing workflow files retain
their persistence role.

While `capture-monitor` runs, the existing job polling path requests only
transient updates newer than the browser's last sequence. Each normal update
contains one completed capture chunk plus compact counters and all-session
metrics. Backend and frontend runtime state both discard oldest complete chunks
at the configured retention boundary, so they do not retain unbounded waveform
history or resend the full retained window on every poll. A bounded reset is
used only when a polling client has fallen behind the retained update window.
Transient waveform arrays are WebUI-runtime data only: they are not copied into
the final job result, CLI JSON, or Common Worker result and need not survive job
completion. The rolling plot uses global sample index on X; each capture's
`time_s` remains local and gaps may exist between repeated acquisitions.

Queued jobs can be cancelled immediately. Running jobs accept a cooperative
cancellation request and remain running until Core execution and session
cleanup finish; blocking VISA I/O is not forcibly interrupted. When the
Launcher is closed, it first stops accepting jobs, requests cancellation, and
waits for running jobs to finish and close their own sessions before stopping
Uvicorn. This shutdown has a timeout; if jobs do not finish or a session close
fails, the Launcher displays **Shutdown incomplete** and remains available so
Quit can be retried. No implicit Safe Cleanup is run.
For a save-enabled Capture Monitor job cancelled after at least one successful
capture, Core writes the stopped final retained window and the WebUI keeps the
job cancelled. It does not re-capture or present cancellation as natural
completion. Cancellation before the first successful capture creates no empty
waveform CSV; with saving disabled it creates no workflow artifacts.
Screenshot and waveform capture jobs register their generated artifacts.
Instrument-side `save-image` and `save-waveform` commands return the Core save
result but do not create host WebUI artifacts. The Result UI keeps structured
result details but does not add artifact download links; use **Open Folder** in
Basic Controls to view host-side files. Backend artifact registration and the
job-scoped download API remain available, and downloads resolve only exact files
registered by that job. Resolved artifacts must also remain inside its submitted
output root.

The submitted PC output folder is the actual host-side output root. Screenshots
and waveform captures write directly under that root using the existing Core/CLI
timestamp naming convention. Serial Lister Export uses its explicit filename.
Multi-file workflows retain their existing command-specific and timestamped
output directories beneath the root. Jobs that do not create host-side artifacts
do not create or validate the PC output folder, and Dry-run only plans paths
without creating them. Both absolute and relative roots are accepted and created
when an output command needs them; creation or write failures are reported
instead of falling back.

During finite workflow execution, the central Result History shows the current
completed work and elapsed time for the active job. When a workflow has a fixed
total, it additionally shows the completed/total count in the same summary. The
`capture-monitor` workflow keeps its own waveform and metrics runtime
presentation, and Generic Sequence keeps its own step-execution progress; these
remain separate from the generic workflow progress shown in Result History.

## Core coverage boundary

The Command workbench intentionally exposes operator-facing settings,
captures, finite workflows, and structured information commands that have a
clear browser interaction. Resource discovery uses the hidden
`list-resources` helper. System identity (`identify`) is read through the
System Information section (not through a standalone command card); the
underlying identity backend remains available for resource/model detection
and capability gating.

Advanced or diagnostic CLI paths are not automatically browser commands.
Current intentional omissions include direct SCPI sending, broad cleanup
operations, and worker/doctor/hardware-report
tooling. Acquisition settings/controls (sample-rate setters, memory-depth
setters, and similar low-level controls) remain CLI/Core paths and are not
exposed in the WebUI. Read-only System Information (identity readback) and
low-level Acquisition Information (current sample rate, acquisition points,
record length) are now presented directly in the System Information section,
but settings and control interfaces for these values remain unexposed. These
omissions avoid exposing a Core operation without an appropriate interaction,
capability, and result model.
Basic FFT unit and window values remain Core-validated text until Core exposes
public option metadata that the WebUI can project without duplicating it.

## Language and current limitations

The browser UI supports English and Traditional Chinese (`zh-TW`). The
selected locale is remembered locally. The Launcher itself is English-only.
Command IDs, model IDs, VISA resources, SCPI, JSON keys, and raw diagnostics
remain unchanged.

The WebUI does not include remote access, authentication, multi-instrument
sessions, WebSockets/SSE, general live waveform streaming, automatic Live Data
polling, dark mode, Electron/onedir packaging, dedicated FFT or Advanced Math
editors, or conditional editors for features not exposed by the current Core
APIs. Dry-run remains
limited to commands with existing Core planners; `capture-batch` and
`measure-log` are Live/Simulate only.
