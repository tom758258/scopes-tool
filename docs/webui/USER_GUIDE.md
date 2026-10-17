# Scopes Tool WebUI and Desktop User Guide

[繁體中文](USER_GUIDE.zh-TW.md)

The browser WebUI and Electron Desktop share the same controls and this guide.
They use Core's model, capability, and safety rules. Check
[Supported Models](../core/supported-models.md) for the exact supported
model/backend/transport combinations and optional feature limits.

## Start and close the application

For a Windows directory package, keep all extracted files together, including
the single shared `_internal` directory. Start `Scopes Tool.exe` for Desktop,
or `scopes-tool-webui-launcher.exe` for the browser Launcher. An already
installed Python application provides `scopes-tool-webui-launcher`.

The browser Launcher starts a localhost server and opens the browser after its
identity and readiness checks succeed. It begins at port 8025 and tries up to
100 ports when no port was explicitly selected. If necessary, enter a manual
port in the Launcher. An explicitly selected occupied port fails without an
automatic fallback. The direct `scopes-tool-webui` server defaults to
`127.0.0.1:8025`; it does not provide the Launcher window.

Close the Launcher to stop its server; closing a browser tab alone does not
stop it. Close the Desktop window to request Host shutdown. Both wait for
active work and session cleanup. If **Shutdown incomplete** or a cleanup
warning appears, leave the application available and retry closing after the
operation finishes. Blocking VISA I/O is not forcibly interrupted. Shutdown
does not implicitly run Safe Cleanup.

## Language, theme, and offline Help

Use the page header to choose English or 繁體中文 and cycle System, Light,
and Dark themes. Language is remembered in browser local storage; theme uses
the existing local cookie. The Launcher itself is English-only. Command IDs,
model IDs, SCPI, VISA resources, JSON keys, and raw diagnostics stay unchanged.

**Help** opens the bundled guide in the current interface language and passes
the current theme preference. Browser WebUI opens a new tab. Desktop opens
the same local WebUI Help in the system default browser; keep the Desktop
running while reading it. No separate Desktop Help bundle exists. Help needs
no Internet connection, but WebUI-served pages need the local server to remain
running. CLI Help can also be opened independently with
`scopes-tool user-guide --lang zh-TW`.

## Select a mode and device

Start with **Simulate** to practice without hardware. Choose a registered
planning model; the Core simulator supplies its identity and capabilities.
Simulated outputs are still files when saving is enabled. **Dry-run** only
plans commands that have Core planners; many settings and workflows are
unavailable in this mode and no instrument session is opened.

For **Live**:

1. Check probes, input ratings, DUT, acquisition, and trigger conditions.
2. In Device / Resource settings select System VISA or PyVISA-py. System VISA
   requires separately installed Keysight IO Libraries or NI-VISA and never
   silently falls back to `@py`.
3. Enter your exact VISA resource or explicitly scan for resources. A scan
   uses live-only discovery and can open listed resources to query `*IDN?`.
   Do not guess instrument addresses or use an example placeholder as a device.
4. Select the intended resource and wait for identification. The detected
   `*IDN?` model is authoritative; a planning model cannot override it.
5. Use Supported Devices and the command availability explanation to confirm
   the selected connection is Product-open before running operations.

System VISA USB is Product-open for all seven registered models. System VISA
TCPIP and `@py` TCPIP are open only for DSOX4024A, DSOX4034A, and TBS2074.
`@py` USB is not Product-open. Bluetooth, GPIB, ASRL, and custom backends do
not gain Product support. Identification and discovery are diagnostics and do
not authorize other operations. WebUI cannot enable contributor Validation Mode.

Changing mode, resource, or planning model changes the result context. A
previous context's values must not be used as the current instrument state.
An initial Live Data snapshot can run after a supported device is selected;
Live Data does not continuously poll or stream waveforms.

## Commands and settings

Select commands through the Command Browser; filter or show Advanced commands
when needed. Unsupported commands remain disabled with an explanation.
Selecting a command or navigating an editor does not perform instrument I/O.

For settings, use **Read current settings**, edit the desired fields, then
**Apply**. Review the returned readback. Unapplied edits are retained instead
of being overwritten by later reads. Ordinary information and diagnostic
commands use explicit Read or Run actions. Only one foreground operation can
run at a time, including device-management actions.

Basic Controls offers Run, Stop, Single, Force Trigger, and black/white
screenshot shortcuts. Acquisition Control also offers Single + Wait with a
5-second default timeout and optional force-on-timeout, off by default.
Autoscale, acquisition control, setup and output settings can change instrument
state; review the effects before applying. Autoscale may change channels,
timebase, trigger, cursors, Math, measurements, and reference display. It has
no automatic rollback. Setup Recall and arbitrary SCPI are not exposed in the
Command Browser.

Channel, timebase, trigger, measurements, reference memory, cursor, annotation,
WGEN, DEMO, Serial, Search, and segmented-memory workspaces appear according
to Core capability metadata. Readback availability does not imply every setter
or option is supported. A profile does not prove an optional hardware license
is installed. For TBS2074 Time Offset, Horizontal Delay Mode must already be
ON; the tool does not change that mode automatically. TBS2074 cursor source
selection can reset acquisition. Follow the model-specific limits in Supported
Models.

## Output folders and saved data

Set the shared **PC output folder** in Basic Controls. Blank means `data`.
**Select Folder** uses the Windows folder picker; cancelling leaves the value
unchanged. **Open Folder** creates the effective directory if needed and opens
it through the Windows shell. The setting is browser-session state and is
captured with each submitted job.

Screenshot and waveform capture write host files under this root. Workflows
use their own subdirectories. Serial Lister Export requires a filename and
will not overwrite an existing file. Output failures are reported instead of
silently using another folder. Jobs without host artifacts do not create or
validate the folder; Dry-run only plans paths.

Save Image, Save Waveform, and Save Setup use instrument-side storage. They
do not create PC downloads and do not inherit the PC output folder. Image and
waveform saves need explicit per-save filenames; setup saves use a slot or
instrument-side file. TDS2024B and TBS1052B do not expose setup, reference
memory, or instrument-side storage. TBS2074 supports native black PNG
screenshots; TDS2024B BMP and TBS1052B JPEG have their own limits. Waveform
capture on Tektronix uses displayed channels, BYTE, and at most 1000 requested
points. It does not enable hidden channels automatically.

## Workflows and Generic Sequence

Choose finite counts, trigger timeouts, retention limits, and save options for
measurement logging, condition monitoring, periodic capture, triggered
measurement/capture, and segmented capture where supported. Capture Monitor
displays a bounded rolling waveform window and all-session statistics;
successive acquisitions are separate records and may have gaps. It is not
continuous real-time waveform streaming. Saving can be disabled for supported
workflows; standalone capture always produces files.

Generic Sequence uses the same Core validation as CLI. Its seven actions are
`wait`, `single`, `wait-trigger`, `measure`, `capture`, `screenshot`, and
`cleanup`; model capabilities can restrict them. Set 1–255 steps and 1–255
loops, at most 65,025 step executions, and at most 10 combined capture/screenshot
steps per loop. Edit locally, then submit Run as one job. Validation reports
invalid documents before execution. Sequence is not an arbitrary SCPI macro.

## Jobs, results, and stopping

Result History shows job progress and the states `queued`, `running`,
`completed`, `failed`, and `cancelled`. Workspace Result shows the most recent
successful result for the exact command and execution context. A later failure
does not erase it. Use Result Detail for complete structured payloads and raw
diagnostics; use Open Folder to view files. The UI does not add artifact
download links.

Cancel removes queued jobs immediately. Running jobs accept a cooperative
stop request and remain running until Core execution and cleanup finish.
Completed work can remain in artifacts; cancellation does not automatically
restore every setting or run Safe Cleanup. Do not mistake a stop request for
a completed shutdown. Segmented Capture keeps the actual Core terminal result,
including a completion that occurs before a late cancellation request.

Doctor checks pre-existing status before its read-only snapshot and performs
a final status check. Reading status may consume an error entry. Smoke performs
measurements, waveform and screenshot transfers, and final status checks.
Its WebUI **Save diagnostic artifacts** option is off by default; enabling it
uses the shared PC output root. Run these diagnostics explicitly after
considering their effects.

## Troubleshooting and limits

| Symptom | Action |
| --- | --- |
| Launcher cannot start | Check the selected local port; use the manual-port fallback when offered. |
| Resource appears but commands are disabled | Check detected identity, backend, transport, execution mode, and the support explanation. |
| System VISA fails | Install or repair the external IVI runtime. Selecting `@py` only works for its approved connections. |
| Settings show old values | Confirm the execution context, explicitly Read, and review unapplied edits before Apply. |
| Capture or screenshot fails | Check displayed channels, model format/point limits, instrument storage, and PC permissions. |
| Help fails to load | Keep the local server/Desktop running and verify the extracted installation is complete. |
| Shutdown remains incomplete | Wait for VISA I/O and cleanup, then retry closing; review the warning. |

WebUI is localhost-only and provides no remote access or authentication,
multi-instrument sessions, WebSockets/SSE, general waveform streaming, or
automatic Live Data polling. FFT and Advanced Math use metadata-driven forms;
there are no dedicated editors for every Core feature. Use CLI or documented
integration APIs for operations intentionally omitted from the UI. Before
sharing logs or saved files, remove private resource addresses and serial numbers.
