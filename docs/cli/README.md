# Scopes Tool CLI

Command-line adapter for safe communication with Keysight InfiniiVision
oscilloscopes through PyVISA.

Distribution: `scopes-tool`

Console script: `scopes-tool`

Module entry point: `python -m scopes_tool_cli.cli`

## Install For Development

From the repository root:

```powershell
uv pip install -e ".[all,dev]"
```

## Basic Usage

After the editable install, prefer the Windows virtual-environment console
wrapper for normal CLI operations:

```powershell
.\.venv\Scripts\scopes-tool.exe identify --simulate --json
```

The module form remains supported as a development or fallback entry point:

```powershell
.\.venv\Scripts\python.exe -m scopes_tool_cli.cli identify --simulate --json
```

Commands that accept instrument access support dry-run, simulate, and live
modes. Agents and automation should use dry-run and simulate before requesting
real hardware access. JSON payloads include `schema_version: 1` and
`timestamp_utc`.

Shared machine contracts remain at root:

- `docs/contracts/common-cli-jsonl-contract.md`
- `docs/contracts/scopes-cli-jsonl-contract.md`
- `docs/contracts/common-worker-protocol.md`
- `docs/contracts/scopes-worker-contract.md`
- `docs/contracts/common-orchestrator-workflows.md`
- `docs/contracts/scopes-orchestrator-workflows.md`

Package-local CLI integration notes remain in `docs/cli-integration.md`.

## Implemented Scope

Current implemented scope:

- List VISA resource strings reported by the selected backend.
- Filter that list to resources that can be opened and respond to `*IDN?`.
- Verify basic communication by querying and parsing `*IDN?`.
- Select runtime capabilities through the canonical physical model registry.
  `--model` accepts a registered canonical physical model ID. A raw model name
  or a model string that merely resembles a supported series is rejected.
- Support canonical IDs `keysight-dsox2004a`, `keysight-dsox3024a`,
  `keysight-dsox4024a`, and `keysight-dsox4034a`, corresponding to physical
  models DSOX2004A, DSOX3024A, DSOX4024A, and DSOX4034A.
- Read one or more entries from the system error queue with
  `:SYSTem:ERRor?`.
- Send basic acquisition control commands: `:STOP`, `:RUN`, and `:SINGle`.
- Configure or query acquisition type and average count with
  `:ACQuire:TYPE` and `:ACQuire:COUNt`.
- Query the current analog acquisition sample rate in Hz with
  `:ACQuire:SRATe?`.
- Query the current analog acquisition points with `:ACQuire:POINts?`.
  This command is read-only and separate from waveform transfer point count
  controlled by `capture --points`.
- Query the current analog acquisition record length with `:ACQuire:RLENgth?`.
  This command is read-only and separate from acquisition points and waveform
  transfer point count controlled by `capture --points`.
- Enable, disable, or query analog channel display state with
  `:CHANnel<n>:DISPlay`.
- Set or query analog channel labels with `:CHANnel<n>:LABel`. 2000X/3000X
  profiles allow up to 10 printable ASCII characters; 4000X profiles allow up
  to 32. Text is sent as supplied and is not uppercased or truncated.
- Set or query analog channel scale and offset with `:CHANnel<n>:SCALe` and
  `:CHANnel<n>:OFFSet`.
- Set or query analog channel coupling, probe ratio, and bandwidth limit with
  `:CHANnel<n>:COUPling`, `:CHANnel<n>:PROBe`, and
  `:CHANnel<n>:BWLimit`.
- Set or query analog channel impedance, invert, full-scale range, units,
  vernier, and probe skew with `:CHANnel<n>:IMPedance`,
  `:CHANnel<n>:INVert`, `:CHANnel<n>:RANGe`, `:CHANnel<n>:UNITs`,
  `:CHANnel<n>:VERNier`, and `:CHANnel<n>:PROBe:SKEW`.
- Set or query horizontal timebase scale and position with `:TIMebase:SCALe`
  and `:TIMebase:POSition`.
- Configure or query analog edge trigger source, level, and slope with
  `:TRIGger:MODE EDGE` and `:TRIGger:EDGE:*`.
- Configure or query Edge Trigger coupling and reject-filter settings with
  `:TRIGger:EDGE:COUPling` and `:TRIGger:EDGE:REJect`.
- Configure or query common trigger sweep, noise reject, and high-frequency
  reject settings with `:TRIGger:SWEep`, `:TRIGger:NREJect`, and
  `:TRIGger:HFReject`.
- Configure or query analog-channel pulse-width trigger settings with
  `:TRIGger:MODE GLITch` and `:TRIGger:GLITch:*`.
- Configure or query analog-channel runt trigger settings with
  `:TRIGger:MODE RUNT`, `:TRIGger:RUNT:*`, and shared
  `:TRIGger:LEVel:LOW/HIGH` threshold commands.
- Configure or query analog-channel transition trigger settings with
  `:TRIGger:MODE TRANsition`, `:TRIGger:TRANsition:*`, and shared
  `:TRIGger:LEVel:LOW/HIGH` threshold commands.
- Configure or query DSO analog-channel Edge Then Edge / Delay trigger
  settings with `:TRIGger:MODE DELay` and `:TRIGger:DELay:*`.
- Configure or query DSO analog-channel setup-hold trigger settings with
  `:TRIGger:MODE SHOLd` and `:TRIGger:SHOLd:*`.
- Configure or query DSO analog-channel Nth Edge Burst trigger settings with
  `:TRIGger:MODE EBURst`, `:TRIGger:EBURst:*`, and optional source-qualified
  `:TRIGger:EDGE:LEVel`.
- Configure or query DSO analog-channel basic TV / video trigger settings with
  `:TRIGger:MODE TV` and `:TRIGger:TV:*`.
- Configure or query DSO analog ASCII pattern trigger settings with
  `:TRIGger:MODE PATTern`, `:TRIGger:PATTern:FORMat ASCii`,
  `:TRIGger:PATTern "<pattern>"`, and
  `:TRIGger:PATTern:QUALifier ENTered`.
- Configure or query DSO analog-only OR trigger settings with
  `:TRIGger:MODE OR` and `:TRIGger:OR "<pattern>"`. Pattern width follows the
  selected registered model's analog-channel capability. The currently
  registered models are all four-channel models, with Keysight OR trigger bit
  assignment CH4, CH3, CH2, CH1.
- Enable, disable, or query display labels with `:DISPlay:LABel`; clear
  waveform display data with `:DISPlay:CLEar`; set/query display persistence,
  waveform intensity, and vector display with `:DISPlay:PERSistence`,
  `:DISPlay:INTensity:WAVeform`, and `:DISPlay:VECTors`; set, clear, or query
  display annotations with `:DISPlay:ANNotation`. 4000X annotation commands use
  indexed slots `1..10` and support `X1Position`/`Y1Position`.
- Query, hide, or configure manual cursors; set/query trigger holdoff; run
  explicit autoscale; save/recall setup slots or `.scp` files; and configure
  FFT math functions.
- Query read-only Vpp, frequency, period, display average voltage, display
  DC RMS voltage, minimum, maximum, rise time, fall time, amplitude, top, base,
  overshoot, preshoot, positive width, negative width, duty cycle, negative
  duty cycle, area, edge count, pulse count, parameterized time, phase, and
  safe 4000X delay measurements with explicit invalid-sentinel handling.
- Rebuild front-panel quick measurements and query measurement statistics with
  `measure-stats`.
- Control common measurement subsystem state with `measure-clear`,
  `measure-show`, `measure-source`, and `measure-window`.
- Save, display, label, clear, or query reference waveform slots 1 and 2 with
  `reference-save`, `reference-display`, `reference-label`,
  `reference-clear`, and `reference-query`.
- Enable, disable, or query basic waveform search state; select a guarded
  search mode; and query the current search event count with `search-state`,
  `search-mode`, and `search-count`.
- Configure/query common instrument-side SAVE settings and start image or
  waveform saves with the Save/Export Pack v1 commands. These commands make the
  oscilloscope write to its own current save directory or storage device; they
  do not create host-side files.
- Query or configure the option-dependent built-in DEMO subsystem with
  `demo-query`, `demo-output`, `demo-function`, and `demo-phase`.
- Collect read-only diagnostic snapshots with `doctor`.
- Query multi-channel and optional pair measurement sweeps with
  continue-and-summarize failure handling.
- Log a finite batch of read-only measurements with `measure-log`, writing a
  CSV, `manifest.json`, and `scpi.log` into one run directory.
- Run capture-safe hardware smoke checks that write a report directory with
  JSON, SCPI log, waveform CSV, metadata, and screenshot artifacts.
- Capture one or more analog channel waveforms in BYTE or WORD format and
  export CSV plus JSON metadata, with optional PNG plot output, an optional
  default timestamped CSV path under `data`, and optional explicit triggered
  capture via `capture --wait-trigger`.
- Capture a finite batch of waveforms with `capture-batch`, writing per-capture
  CSV and metadata files, `manifest.json`, and `scpi.log` into one run
  directory.
- Capture the current oscilloscope screen as a PNG, BMP, or BMP8bit image,
  with an optional default timestamped output path under `data`.
- Provide hardware-free tests through `FakeBackend`.
- Force one trigger event explicitly with `force-trigger` / `:TRIGger:FORCe`,
  without changing the standalone `single` or default `capture` behavior.

The package does not send `*RST`, does not change VISA timeout defaults, and
does not perform return-to-local behavior. State-changing commands are exposed
only through explicit CLI commands; `doctor`, `smoke`, and `acquisition-check`
do not call the new cursor, holdoff, autoscale, setup, statistics, or FFT paths.

No acquisition run-state query is currently exposed. `:RSTate?` timed out on
the DSO-X 4024A used for validation and is not used by the CLI.

## Development

From PowerShell, change into the project directory, create or reuse the local
virtual environment, install the package with development dependencies, then
run the default hardware-free tests:

```powershell
cd path\to\scopes-tool
```

```powershell
uv venv .venv
```

```powershell
uv pip install -e ".[all,dev]"
```

This repository currently uses `uv` for the local virtual environment and
editable installs, but it is not configured as a `uv` workspace and does not
use a committed `uv.lock`. Do not commit a generated `uv.lock` unless the root
`pyproject.toml` is later changed to define an explicit uv workspace.

Run the repository test wrapper from the root directory:

```powershell
.\scripts\run-tests.ps1
```

This runs tests from all three areas: `tests/core`, `tests/cli`, and
`tests/webui`.

The wrapper creates an isolated pytest temporary directory, removes it after a
successful run, and preserves it after a failure for inspection. Additional
pytest arguments can be passed after the script path.

PyVISA will use the default VISA backend discovered on the computer. On the
instrument computer, the preferred backend is the installed Keysight IO
Libraries vendor VISA backend. `pyvisa-py` is a fallback for systems without a
usable vendor backend.

## Agent-safe Automation

Commands that accept instrument connections also accept `--json`, `--simulate`,
`--dry-run`, `--model`, and `--live`. Use `--dry-run` to validate arguments and
inspect planned SCPI without opening VISA or writing files; add `--json` when
automation needs the machine-readable payload. Use `--simulate --json` to run
against the deterministic hardware-free simulator; capture workflows write fake
output files for offline validation. JSON payloads include `schema_version: 1`
and `timestamp_utc`.

Simulator commands also accept presets, JSON scenarios, repeated signal
overrides, and error injection options, but only with `--simulate`.

```text
--simulate-preset noisy-sine
--simulate-scenario path\to\scenario.json
--simulate-signal CH:shape:frequency_hz:vpp_v:offset_v:phase_deg[:noise_rms_v]
--simulate-system-error -113
--simulate-binary-transfer-failure
--simulate-invalid-measurement CH2
--simulate-display-off CH1
```

`CH` may be `CH1` or `1`. Supported shapes are `sine`, `square`, `ramp`, `dc`,
and `noise`. Built-in presets are `noisy-sine`, `square-with-offset`,
`phase-shifted-pair`, `dc-invalid-frequency`, and `trigger-misaligned`.
Simulator configuration layers are applied in this order: built-in defaults,
`--simulate-preset`, `--simulate-scenario`, then explicit CLI overrides such as
`--simulate-signal` and error injection options. Scenario files are JSON only.

Agents should only access real hardware after explicit user approval. For a
one-shot command, an explicit `--resource <RESOURCE>` or
`SCOPES_TOOL_RESOURCE` opts in to that single live instrument. `--live`
remains accepted for one-shot compatibility, but is not required and cannot be
combined with `--simulate` or `--dry-run`. Live workers still require
`--live --resource`. SCPI debug logs from `--log-scpi` are written to stderr
and must not be parsed as JSON.

For dry-run and simulator modes, `--model` is the planning canonical physical
model ID. Simulator IDN fields and capabilities come from that registry entry.
One-shot live execution derives physical identity and capabilities from the
actual `*IDN?`; its `--model` value does not replace the detected identity.
For live workers, `--model` is an expected canonical physical model ID and a
mismatch fails before command-specific SCPI.

```powershell
.\.venv\Scripts\scopes-tool.exe identify --dry-run --json
.\.venv\Scripts\scopes-tool.exe identify --simulate --json
.\.venv\Scripts\scopes-tool.exe acquisition-points --query --dry-run --json --model keysight-dsox4024a
.\.venv\Scripts\scopes-tool.exe acquisition-points --query --simulate --json --model keysight-dsox4024a
.\.venv\Scripts\scopes-tool.exe record-length --query --simulate --json --model keysight-dsox4024a
.\.venv\Scripts\scopes-tool.exe capture --simulate --json --simulate-preset phase-shifted-pair --channel 1 --channel 2 --csv .tmp_tests\preset.csv
.\.venv\Scripts\scopes-tool.exe measure --simulate --json --simulate-scenario path\to\scenario.json --channel 1 --item frequency
.\.venv\Scripts\scopes-tool.exe measure --simulate --json --simulate-signal CH1:square:1000:1.0:0:0:0.02 --channel 1 --item vpp
.\.venv\Scripts\scopes-tool.exe capture --simulate --json --simulate-binary-transfer-failure --channel 1 --csv .tmp_tests\failure.csv
.\.venv\Scripts\scopes-tool.exe capture-batch --simulate --json --channel 1 --count 2 --output-dir .tmp_tests\sim_batch
.\.venv\Scripts\scopes-tool.exe measure-log --simulate --json --channel 1 --items vpp,frequency --count 2 --output-dir .tmp_tests\sim_measure_log
```

Automation and orchestrator contracts live under `docs/contracts/`; start with
`docs/contracts/scopes-worker-contract.md`,
`docs/contracts/common-cli-jsonl-contract.md`,
`docs/contracts/scopes-cli-jsonl-contract.md`, and
`docs/contracts/scopes-orchestrator-workflows.md`. Keep dry-run or simulated
checks in front of live instrument access, and use an explicit operator-selected
resource for live commands.

## Commands

List VISA resource strings reported by the selected backend:

```powershell
.\.venv\Scripts\scopes-tool.exe list-resources
```

This is passive discovery only: a resource string can appear here even when the
instrument is not currently reachable. Plain `list-resources` does not open
the listed resources or send SCPI.

List only resources that can be opened and queried with `*IDN?`:

```powershell
.\.venv\Scripts\scopes-tool.exe list-resources --live-only
```

This opens each listed resource and sends `*IDN?`. Resources that cannot be
opened or do not respond to `*IDN?` are omitted. Add `--log-scpi` to show the
verification query for each live check.

ASRL/RS-232 live checks use a bounded best-effort discovery path with a 1000 ms
open/query timeout so a stale serial port does not prevent later USB or TCPIP
resources from being checked. This compatibility check is only for live
discovery and does not mean the Scope runtime supports full RS-232 acquisition
or control workflows.

For ASRL live discovery only, serial termination can be set when needed for a
specific adapter or instrument:

```powershell
.\.venv\Scripts\scopes-tool.exe list-resources --live-only --serial-read-termination CRLF --serial-write-termination NONE
```

Supported values are `CRLF`, `LF`, `CR`, and `NONE`. Omitted options leave the
PyVISA session attributes unchanged; explicit `NONE` sets the corresponding
termination attribute to `None`.

Set the operator-selected live resource once in the current PowerShell session:

```powershell
$env:SCOPES_TOOL_RESOURCE = "USB0::...::INSTR"
```

The remaining live examples assume this environment variable is set. Replace
the placeholder with the resource string selected by the operator.

Verify that one resource can be opened and queried with `*IDN?`:

```powershell
.\.venv\Scripts\scopes-tool.exe identify --resource "$env:SCOPES_TOOL_RESOURCE"
```

Add `--log-scpi` to print the SCPI command log for manual hardware checks:

```powershell
.\.venv\Scripts\scopes-tool.exe identify --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```

Read one system error queue entry:

```powershell
.\.venv\Scripts\scopes-tool.exe check-error --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```

Drain the system error queue until no error is reported or the read limit is
hit:

```powershell
.\.venv\Scripts\scopes-tool.exe check-error --resource "$env:SCOPES_TOOL_RESOURCE" --all --log-scpi
```

Use the low-risk System/Status Pack v1 primitives in dry-run or simulation:

```powershell
.\.venv\Scripts\scopes-tool.exe system-clear-status --dry-run --json
.\.venv\Scripts\scopes-tool.exe system-opc --query --simulate --json
.\.venv\Scripts\scopes-tool.exe system-status-byte --query --simulate --json
.\.venv\Scripts\scopes-tool.exe system-standard-event --query --simulate --json
.\.venv\Scripts\scopes-tool.exe system-operation-status --query --simulate --json
.\.venv\Scripts\scopes-tool.exe system-options --query --simulate --json
```

`system-clear-status` sends `*CLS` and takes no command-specific arguments.
The other five commands are query-only and require explicit `--query`. They
send `*OPC?`, `*STB?`, `*ESR?`, `:OPERegister:CONDition?`, and `*OPT?`,
respectively. Register results preserve `raw`, return an integer `value`, and
list set bit indexes from low to high. Options preserve `raw` and return
trimmed comma-separated tokens; a `0` response remains `raw: "0"` with an
`options` entry of `"0"`.

`system-standard-event` is a destructive event-register read: `*ESR?` clears
the events it returns according to SCPI behavior. `system-operation-status`
uses `:OPERegister:CONDition?`; `:RSTate?` remains intentionally unsupported.
Use `check-error` to read or drain `:SYSTem:ERRor?`; this pack does not replace
that command. The CLI keeps its normal one-entry system-error post-check after
each pack command.

This pack has hardware-free Core, CLI, simulator, and worker coverage only.
No live hardware validation was performed, and no WebUI runtime behavior was
added.

Send basic acquisition control commands:

```powershell
.\.venv\Scripts\scopes-tool.exe stop-acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe run --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe single --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```

The library methods `stop()`, `run()`, and `single()` each send only one SCPI
command. The CLI control commands additionally perform a transparent post-check
by querying one `:SYSTem:ERRor?` entry and printing the result. The
`:SYSTem:ERRor?` query removes the returned entry from the instrument error

Force one trigger event explicitly:

```powershell
.\.venv\Scripts\scopes-tool.exe force-trigger --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe force-trigger --dry-run --json
.\.venv\Scripts\scopes-tool.exe force-trigger --simulate --json --log-scpi
```

`force-trigger` is an explicit state-changing one-shot action. It first
queries `*IDN?`, then sends `:TRIGger:FORCe`, then performs one `:SYSTem:ERRor?`
post-check. It does not arm a single acquisition, does not wait for trigger
or acquisition completion, does not capture waveform data, and does not
change timebase, acquisition points, record length, acquisition mode,
sample-rate mode, waveform
points, waveform format, display state, VISA timeout, trigger source, trigger
level, trigger slope, trigger sweep, or return-to-local behavior. `force-trigger`
must not be combined with `capture`, `measure`, `doctor`, `smoke`,
`acquisition-check`, `single`, `run`, `stop-acquisition`, `autoscale`,
`setup-save`, or `setup-recall`. Worker `/command` support is available only
through the explicit `force-trigger` command with `arguments: {}`.
Triggered capture integration is available only through explicit
`capture --wait-trigger` options; the standalone `force-trigger` command
remains unchanged.

The long trigger force form is used for DSO-X 4000X firmware 07.20
compatibility.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command force-trigger --arguments-json "{}" --json
```

Configure or query acquisition type and average count:

```powershell
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --type normal --log-scpi
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --type average --count 16 --log-scpi
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --type high_resolution --log-scpi
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --type peak --log-scpi
```

The `acquisition` command first queries `*IDN?`, then sends only the requested
`:ACQuire:TYPE` and optional `:ACQuire:COUNt` commands before one
`:SYSTem:ERRor?` post-check. `--query` reads back both acquisition type and
average count. `--count` is only valid with average acquisition mode and must be
between 2 and 65536. Type aliases include `norm`, `aver`, `avg`,
`high-resolution`, `hresolution`, `hres`, `peak_detect`, and `peak-detect`.
This command does not change timeout defaults, trigger wait strategy,
acquisition mode, run/stop state, or return-to-local behavior.

Query the current analog acquisition sample rate:

```powershell
.\.venv\Scripts\scopes-tool.exe sample-rate --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

Query the maximum analog acquisition sample rate:

```powershell
.\.venv\Scripts\scopes-tool.exe sample-rate --resource "$env:SCOPES_TOOL_RESOURCE" --query --maximum --log-scpi
```

The `sample-rate` command is query-only and requires `--query`. It first
queries `*IDN?`, then sends `:ACQuire:SRATe?` for the current sample rate or
`:ACQuire:SRATe? MAXimum` when `--maximum` is supplied, and performs one
`:SYSTem:ERRor?` post-check. The response is parsed as an NR3 number and
reported in Hz together with the raw readback. Maximum queries report
`query_kind: "maximum"` and `maximum_sample_rate_hz` in JSON. This command does
not change timebase, acquisition points, record length, acquisition mode,
sample-rate auto/manual mode, waveform points, trigger settings, VISA timeout,
or return-to-local
behavior. The short query forms are used for DSO-X 4000X firmware 07.20
compatibility.

Worker usage requires the same query-only intent:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command sample-rate --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command sample-rate --arguments-json "{\"query\":true,\"maximum\":true}" --json
```

Query the current analog acquisition points:

```powershell
.\.venv\Scripts\scopes-tool.exe acquisition-points --query --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```

The `acquisition-points` command is query-only and requires `--query`. It first
queries `*IDN?`, then sends `:ACQuire:POINts?` and performs one
`:SYSTem:ERRor?` post-check. The response is parsed as an integer
representing the current analog acquisition points, together with the raw
readback. It does not configure acquisition points, record length, acquisition
mode, timebase, sample-rate, trigger settings, waveform format, waveform
points, VISA timeout, or return-to-local behavior. `acquisition-points --query`
is separate from `capture --points`, which controls waveform transfer point
count.

Worker usage requires the same query-only intent:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command acquisition-points --arguments-json "{\"query\":true}" --json
```

Query the current analog acquisition record length:

```powershell
.\.venv\Scripts\scopes-tool.exe record-length --query --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```

The `record-length` command is query-only and requires `--query`. It first
queries `*IDN?`, then sends `:ACQuire:RLENgth?` and performs one
`:SYSTem:ERRor?` post-check. The response is parsed as an integer
representing the current analog acquisition record length, together with the
raw readback. It does not configure record length, acquisition points,
acquisition mode, timebase, sample-rate, trigger settings, waveform format,
waveform points, VISA timeout, or return-to-local behavior.
`record-length --query` is separate from `capture --points`, which controls
waveform transfer point count.

Worker usage requires the same query-only intent:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command record-length --arguments-json "{\"query\":true}" --json
```

Run the acquisition configuration validation workflow and write a report
directory:

```powershell
.\.venv\Scripts\scopes-tool.exe acquisition-check --dry-run --json --model keysight-dsox4034a
.\.venv\Scripts\scopes-tool.exe acquisition-check --simulate --json --model keysight-dsox4034a --output-dir .tmp_tests\acquisition_check
.\.venv\Scripts\scopes-tool.exe acquisition-check --resource "$env:SCOPES_TOOL_RESOURCE" --json --log-scpi
```

`acquisition-check` runs the fixed validation sequence
`query -> normal -> average count 16 -> query -> high_resolution -> peak ->
final query`. It writes `report.json` and `scpi.log` under
`data/hardware_acquisition/YYYY-MM-DD-HH-mm-ss` unless `--output-dir` is
supplied. Use `--average-count N` to override the default count of 16. The
workflow intentionally leaves the instrument in `peak` acquisition mode after a
successful run so the command sequence stays explicit and avoids a hidden
restore write.

Enable, disable, or query one analog channel display:

```powershell
.\.venv\Scripts\scopes-tool.exe channel-display --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --on --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-display --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-display --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --off --log-scpi
```

The `channel-display` command first queries `*IDN?` so the channel number can be
validated against the detected model before any channel display command is sent.
It prints the planned change or query, then performs one `:SYSTem:ERRor?`
post-check. `--query` only reads back the current display state with
`:CHANnel<n>:DISPlay?`; it should not change the oscilloscope screen.

Set or query one analog channel vertical scale:

```powershell
.\.venv\Scripts\scopes-tool.exe channel-scale --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --volts-per-division 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-scale --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```

Set or query one analog channel vertical offset:

```powershell
.\.venv\Scripts\scopes-tool.exe channel-offset --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --volts 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-offset --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```

Scale must be a positive finite number in volts per division. Offset must be a
finite number in volts. These commands first query `*IDN?` to validate the
channel number against the detected model, then perform one
`:SYSTem:ERRor?` post-check.

Set or query one analog channel input coupling:

```powershell
.\.venv\Scripts\scopes-tool.exe channel-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --coupling dc --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```

Set or query one analog channel probe attenuation ratio:

```powershell
.\.venv\Scripts\scopes-tool.exe channel-probe --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --ratio 10 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-probe --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```

Enable, disable, or query one analog channel bandwidth limit:

```powershell
.\.venv\Scripts\scopes-tool.exe channel-bandwidth-limit --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --on --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-bandwidth-limit --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-bandwidth-limit --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --off --log-scpi
```

Channel coupling supports `ac` and `dc`. Probe ratio must be a positive finite
number. Bandwidth limit is a per-channel on/off setting. These commands first
query `*IDN?` to validate the channel number against the detected model, then
perform one `:SYSTem:ERRor?` post-check.

Set or query additional analog channel settings:

```powershell
.\.venv\Scripts\scopes-tool.exe channel-impedance --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --impedance one-meg --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-impedance --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --impedance fifty --allow-50-ohm --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-impedance --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-invert --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --on --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-invert --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-range --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --volts-full-scale 4 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-range --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-units --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --units volt --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-units --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-vernier --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --off --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-vernier --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-probe-skew --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --seconds 1e-9 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-probe-skew --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```

These commands first query `*IDN?`, validate the channel number against the
detected model, send only the requested command or query, and then perform one
`:SYSTem:ERRor?` post-check. `channel-range --volts-full-scale` must be positive and
finite. `channel-probe-skew --seconds` must be finite and within
`-100e-9..100e-9`. Units are `volt` or `amp`; impedance is `one-meg` or
`fifty`. Setting `fifty` requires `--allow-50-ohm` before any backend is
opened. In this CLI, 50 ohm channel impedance is supported only on DSO-X 3000X
and 4000X profiles. DSO-X 2000X channel impedance is one-meg only; even with
`--allow-50-ohm`, a detected 2000X is rejected after `*IDN?` and before
`:CHANnel<n>:IMPedance FIFTy`.

Worker `/command` accepts these advanced channel commands using the same option
names as JSON keys without leading dashes. For example, `channel-range` uses
`volts_full_scale`, not `volts`.

Set or query one analog channel label:

```powershell
.\.venv\Scripts\scopes-tool.exe channel-label --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --text "Input A" --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-label --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```

Channel labels accept printable ASCII text without double quotes or control
characters. The CLI validates model-specific length before sending SCPI:
2000X/3000X allow up to 10 characters, and 4000X allows up to 32. Some
instruments may normalize returned label case; JSON reports the query readback
as returned by SCPI parsing.

Enable, disable, or query front-panel label display:

```powershell
.\.venv\Scripts\scopes-tool.exe display-label --resource "$env:SCOPES_TOOL_RESOURCE" --on --log-scpi
.\.venv\Scripts\scopes-tool.exe display-label --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

Run common display one-shot commands:

```powershell
.\.venv\Scripts\scopes-tool.exe display-clear --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe display-persistence --resource "$env:SCOPES_TOOL_RESOURCE" --mode minimum --log-scpi
.\.venv\Scripts\scopes-tool.exe display-persistence --resource "$env:SCOPES_TOOL_RESOURCE" --seconds 1.0 --log-scpi
.\.venv\Scripts\scopes-tool.exe display-persistence --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe display-intensity --resource "$env:SCOPES_TOOL_RESOURCE" --value 75 --log-scpi
.\.venv\Scripts\scopes-tool.exe display-intensity --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe display-vectors --resource "$env:SCOPES_TOOL_RESOURCE" --on --log-scpi
.\.venv\Scripts\scopes-tool.exe display-vectors --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

These commands first query `*IDN?`, then send the target display command or
query, then perform one `:SYSTem:ERRor?` post-check. `display-clear` clears
waveform display data and resets associated measurements. Display persistence
accepts `minimum`, `infinite`, or finite seconds from `0.1` through `60.0`.
Waveform intensity accepts integer values from `0` through `100`.
`display-vectors` supports query and setting ON only; setting OFF is not part
of this common v1 surface. `display-persistence-clear` is intentionally not
implemented in this common pack; it may be considered later as a separately
guarded 2000X-only command with its own validation plan.

Set, clear, or query display annotations:

```powershell
.\.venv\Scripts\scopes-tool.exe annotation --resource "$env:SCOPES_TOOL_RESOURCE" --on --text "Run note" --color white --background opaque --log-scpi
.\.venv\Scripts\scopes-tool.exe annotation --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe annotation --resource "$env:SCOPES_TOOL_RESOURCE" --model keysight-dsox4024a --slot 2 --text "Run note" --x 10 --y 20 --log-scpi
```

`annotation --query` cannot be combined with setters. Non-query annotation
commands require at least one setter/action. `--clear` sends an empty annotation
text string and cannot be combined with `--text`. 2000X/3000X annotation uses
the unindexed `:DISPlay:ANNotation` commands and does not send or query X/Y
position; JSON query results still include `x: null` and `y: null`. 4000X uses
indexed `:DISPlay:ANNotation<n>` slots from 1 through 10 and validates `--x`
as 0 through 800 and `--y` as 0 through 480 before sending
`:X1Position`/`:Y1Position` SCPI. Annotation background values are `opaque`,
`inverted`, and `transparent`; annotation color values are `ch1`, `ch2`,
`ch3`, `ch4`, `dig`, `math`, `ref`, `marker`, `white`, and `red`.
Annotation text accepts printable ASCII text up to 254 characters and must not
contain double quotes or control characters.
Annotation value forms are distinct:

- CLI input aliases: `white`, `marker`, and `transparent`.
- SCPI command tokens: `WHITE`, `MARKer`, and `OPAQ`.
- Query canonical enums: `WHITE`, `MARK`, `DIG`, `OPAQ`, and `TRAN`.

Annotation query results preserve instrument semantics using canonical SCPI
enum values. Color readback abbreviations such as `WHIT` are accepted and
normalized to stable canonical values such as `WHITE`; background readback
canonical values remain `OPAQ`, `INV`, and `TRAN`.

These one-shot commands are also accepted by the worker `/command` interface
using the same argument names as the CLI options without leading dashes.

Set or query the horizontal timebase scale:

```powershell
.\.venv\Scripts\scopes-tool.exe timebase-scale --resource "$env:SCOPES_TOOL_RESOURCE" --seconds-per-division 0.001 --log-scpi
.\.venv\Scripts\scopes-tool.exe timebase-scale --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

Set or query the horizontal timebase position:

```powershell
.\.venv\Scripts\scopes-tool.exe timebase-position --resource "$env:SCOPES_TOOL_RESOURCE" --seconds 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe timebase-position --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

Timebase scale must be a positive finite number in seconds per division.
Timebase position must be a finite number in seconds. These commands first
query `*IDN?` to verify the connected scope model is recognized, then perform
one `:SYSTem:ERRor?` post-check.

Configure or query analog edge trigger source, level, and slope with the
canonical `trigger-edge` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --level 0.25 --slope positive --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-edge --simulate --json --model keysight-dsox4024a --source-channel 1 --level 0.5 --slope positive
```

The configure command sends `:TRIGger:MODE EDGE`, then sets source, level, and
slope. Supported slopes are `positive`, `negative`, `either`, and `alternate`.
Only DSO analog channel sources are supported. Trigger level must be a finite
number in volts. External trigger, digital/MSO source, trigger coupling/reject,
and broader trigger-tree expansion are not included. The old `edge-trigger`
command name is not accepted.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge --arguments-json "{\"source_channel\":1,\"level\":0.5,\"slope\":\"positive\"}" --json
```

Worker JSON for `trigger-edge` accepts only `query`, `source_channel`,
`level`, and `slope`. Aliases and unknown fields are rejected before enqueue,
artifact creation, simulator/VISA session open, or SCPI.

Configure or query only the Edge Trigger source with the canonical
`trigger-edge-source` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-source --dry-run --json --model keysight-dsox2004a --source-channel 1
.\.venv\Scripts\scopes-tool.exe trigger-edge-source --simulate --json --model keysight-dsox3024a --source external
.\.venv\Scripts\scopes-tool.exe trigger-edge-source --simulate --json --model keysight-dsox4024a --source line
.\.venv\Scripts\scopes-tool.exe trigger-edge-source --simulate --json --model keysight-dsox4034a --query
```

Exactly one operation is required: `--query`, `--source-channel <int>`, or
`--source external|line`. Analog configuration maps to
`:TRIGger:EDGE:SOURce CHANnel<n>`; External maps to
`:TRIGger:EDGE:SOURce EXTernal`; AC Line maps to
`:TRIGger:EDGE:SOURce LINE`; query sends `:TRIGger:EDGE:SOURce?`. The command
does not send `:TRIGger:MODE EDGE` and does not change level, slope, coupling,
reject, sweep, noise reject, HF reject, holdoff, or acquisition state.

This command is distinct from the existing `trigger-edge` command, which
continues to configure analog source, level, and slope together. The source-only
configure surface is the documented common `CHANnel<n>`, `EXTernal`, and
`LINE` values for target DSOX2004A, DSOX3024A, DSOX4024A, and DSOX4034A models;
analog channels are checked against the selected model profile. It does not
configure external level/range or WGEN, WMOD, digital/MSO sources. Query JSON
preserves `raw_source` and normalizes only analog-channel, external, or line;
`NONE`, WaveGen, digital, unsupported, and future readbacks return null
normalized source fields without failing solely for that readback.

Worker usage accepts only canonical JSON:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-source --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-source --arguments-json "{\"source_channel\":1}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-source --arguments-json "{\"source\":\"external\"}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-source --arguments-json "{\"source\":\"line\"}" --json
```

Worker validation requires exactly one operation, lowercase `external` or
`line`, and a non-boolean integer analog channel within the selected model.
Query/configure mixes, `query: false`, aliases, camelCase keys, unknown keys,
uppercase source values, and unsupported source values are rejected before
enqueue, artifact creation, simulator/VISA session open, or SCPI. This v1
implementation has hardware-free Core/CLI/simulator/worker coverage only;
live hardware, LAN, and worker live validation have not been run.

Phase 13C - Edge Trigger Slope and Analog Level v1 adds two independent
commands. `trigger-edge-slope` accepts exactly one of `--query` or
`--slope positive|negative|either|alternate`:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-slope --dry-run --json --model keysight-dsox2004a --slope positive
.\.venv\Scripts\scopes-tool.exe trigger-edge-slope --simulate --json --model keysight-dsox4034a --query
```

Its configure mappings are `positive` to `:TRIGger:EDGE:SLOPe POSitive`,
`negative` to `NEGative`, `either` to `EITHer`, and `alternate` to
`ALTernate`; query sends `:TRIGger:EDGE:SLOPe?`. Query normalizes documented
short/long readbacks (`POS`, `NEG`, `EITH`, `ALT`) while preserving
`raw_slope`; unknown values return a null normalized `slope`. It neither
queries nor changes trigger mode, and it does not redirect to TV polarity.

`trigger-edge-level` always requires `--source-channel <int>` and accepts
exactly one of `--query` or `--level-volts <number>`:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-level --dry-run --json --model keysight-dsox2004a --source-channel 1 --level-volts 0.5
.\.venv\Scripts\scopes-tool.exe trigger-edge-level --simulate --json --model keysight-dsox4034a --source-channel 2 --query
```

Configure sends `:TRIGger:EDGE:LEVel <level>,CHANnel<n>` and query sends
`:TRIGger:EDGE:LEVel? CHANnel<n>`; no active-source implicit form is used.
The named channel's stored level is addressed without switching the active
source. Local validation checks only the selected model profile's analog
channel count and a finite numeric level. The instrument enforces the dynamic
level range based on current vertical range and center; this command makes no
scale, offset, or range queries and never clamps a value.

Both commands are distinct from `trigger-edge`, which continues to configure
mode, source, level, and slope together. They have no aliases. Their canonical
worker JSON forms are `{"query":true}` or
`{"slope":"positive"}` for `trigger-edge-slope`, and
`{"query":true,"source_channel":1}` or
`{"source_channel":1,"level_volts":0.5}` for `trigger-edge-level`.
Workers reject unknown/alias keys, aliases, query/configure mixes, uppercase
or undocumented slope values, invalid or boolean channel values, and
non-finite/non-numeric levels before enqueue, artifacts, simulator/VISA open,
or SCPI. The documented DSOX2004A, DSOX3024A, DSOX4024A, and DSOX4034A scope
is hardware-free only; live hardware, LAN, and worker-live validation have not
run. External, Line, WaveGen, WMOD, and digital/MSO levels are excluded.

Phase 14 adds two independent External-input controls. `external-trigger-range`
accepts exactly one of `--query` or `--range-volts <finite-positive-number>`:

```powershell
.\.venv\Scripts\scopes-tool.exe external-trigger-range --dry-run --json --model keysight-dsox2004a --range-volts 8.0
.\.venv\Scripts\scopes-tool.exe external-trigger-range --simulate --json --model keysight-dsox4034a --query
```

It sends only `:EXTernal:RANGe <range>` or `:EXTernal:RANGe?`; it does not
query or configure `:EXTernal:PROBe`, change Edge source/mode/level, or alter
acquisition state. Local validation accepts any finite positive range and does
not restrict input to 1.6 V or 8 V. The manuals document 8 V at 1:1 probe
attenuation for 2000X/3000X, and 1.6 V or 8 V at 1:1 for 4000X. Because this
phase does not inspect probe attenuation, the instrument and its error queue
remain authoritative for actual model-, firmware-, probe-, and hardware-valid
range selection. The simulator enforces only finite-positive input and does not
emulate every model/probe-dependent range rejection.

`trigger-edge-external-level` accepts exactly one of `--query` or
`--level-volts <finite-number>`:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-external-level --dry-run --json --model keysight-dsox2004a --level-volts 0.5
.\.venv\Scripts\scopes-tool.exe trigger-edge-external-level --simulate --json --model keysight-dsox4034a --query
```

It always sends `:TRIGger:EDGE:LEVel <level>,EXTernal` or
`:TRIGger:EDGE:LEVel? EXTernal`; it never uses active-source implicit level
SCPI, changes Edge source or mode, or queries/changes External range. This is
separate from the analog-channel-only `trigger-edge-level` command. Local
validation accepts finite positive, negative, or zero values only; it does not
query the dynamic External range or clamp levels. The instrument/error queue
enforces the documented current-range limit. Neither command has aliases.

Canonical worker JSON is `{"query":true}` or `{"range_volts":8.0}` for
`external-trigger-range`, and `{"query":true}` or `{"level_volts":0.5}`
for `trigger-edge-external-level`. Workers reject empty arguments,
`query: false`, query/configure mixes, unknown or alias keys, booleans,
non-numeric and non-finite values, and zero/negative External ranges before
enqueue, artifact creation, simulator/VISA open, or SCPI. These target
DSOX2004A, DSOX3024A, DSOX4024A, and DSOX4034A paths are hardware-free only;
live hardware, LAN, and worker-live validation have not been run.

Phase 15 — External Trigger Input Settings v1 adds three independent common
DSO-X 2000X/3000X/4000X commands. `external-trigger-probe` accepts exactly
one of `--query` or `--attenuation <finite-positive-number>` and sends only
`:EXTernal:PROBe?` or `:EXTernal:PROBe <attenuation>`. It does not apply a
shared hardware attenuation range: probe, model, firmware, and AutoProbe
acceptance remain instrument/error-queue authority.

`external-trigger-units` accepts exactly one of `--query`, `--units volts`,
or `--units amps`; it sends only `:EXTernal:UNITs?`, `:EXTernal:UNITs VOLT`,
or `:EXTernal:UNITs AMPere`. `external-trigger-settings` is query-only and
requires explicit `--query`; it sends one `:EXTernal?` query rather than four
separate queries. Its JSON result preserves `raw_response` and normalizes
known probe attenuation, range value, units, and BWL readback fields. Units
readbacks accept `VOLT`, `AMP`, and `AMPere`; unknown future readbacks are
preserved without being presented as configure support.

Canonical worker JSON is `{"query":true}` or `{"attenuation":10}` for
`external-trigger-probe`, `{"query":true}` or `{"units":"volts"}` for
`external-trigger-units`, and only `{"query":true}` for
`external-trigger-settings`. Workers reject empty arguments, `query: false`,
operation mixes, aliases, unknown keys, incorrect JSON types, non-finite
values, and oversized integers before enqueue, artifacts, simulator/VISA open,
or SCPI. These commands do not set External BWLimit (the aggregate BWL field
is compatibility/readback information only; use existing `trigger-hf-reject`
for common high-frequency rejection), discover AutoProbe, query probe
type, convert range/level values, modify trigger source/mode, or control
acquisition. Real firmware may relate these settings, but the library issues
no compensating writes; the simulator stores probe, units, range, and External
Edge level independently to detect unintended side effects. Hardware, LAN, and
worker-live validation have not been run.

Configure or query common trigger general settings:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --mode auto --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --mode normal --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-noise-reject --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-noise-reject --resource "$env:SCOPES_TOOL_RESOURCE" --enabled true --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-noise-reject --resource "$env:SCOPES_TOOL_RESOURCE" --enabled false --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-hf-reject --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-hf-reject --resource "$env:SCOPES_TOOL_RESOURCE" --enabled true --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-hf-reject --resource "$env:SCOPES_TOOL_RESOURCE" --enabled false --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-sweep --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-noise-reject --simulate --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-hf-reject --simulate --json --model keysight-dsox4024a --enabled true
```

`trigger-sweep` uses `:TRIGger:SWEep` and accepts only `--mode auto` or
`--mode normal`. Query mode sends `:TRIGger:SWEep?` and reports normalized
`mode` plus `raw_value` in JSON. `trigger-noise-reject` uses
`:TRIGger:NREJect`; `trigger-hf-reject` uses `:TRIGger:HFReject`. Both reject
commands accept only `--enabled true` or `--enabled false`; query mode
normalizes `0`/`1` readback to boolean `enabled` and preserves `raw_value`.
Each command rejects `--query` combined with configure options and rejects
missing configure options when not querying.

These commands are explicit one-shot state changes or queries. They do not
change trigger holdoff, do not add generic trigger settings APIs, do not run,
stop, single, force trigger, wait for trigger, capture waveform data, or change
WebUI runtime behavior. This v1 package has hardware-free CLI/Core/simulator
and worker validation only; live CLI, worker live, LAN, WebUI runtime, DSO-X
2000X/3000X/4024A/4034A live validation, and prior trigger pack live status
changes have not been run or made. Phase 10 `trigger-edge` live validation
remains pending and is not abandoned.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-sweep --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-sweep --arguments-json "{\"mode\":\"normal\"}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-noise-reject --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-noise-reject --arguments-json "{\"enabled\":false}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-hf-reject --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-hf-reject --arguments-json "{\"enabled\":true}" --json
```

Worker JSON for `trigger-sweep` accepts only `query` or `mode`. Worker JSON for
`trigger-noise-reject` and `trigger-hf-reject` accepts only `query` or
`enabled`. `query` must be exactly JSON `true`; `enabled` must be a JSON
boolean. Unknown fields and aliases such as `sweep`, `sweep_mode`,
`trigger_sweep`, `noise_reject`, `nreject`, `nrej`, `state`, `on`, `enable`,
`hf_reject`, `hfreject`, and `high_frequency_reject` are rejected before
enqueue, artifact creation, simulator/VISA session open, or SCPI.

Set or query fixed trigger holdoff:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --query --json
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --seconds 1e-6 --json
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --dry-run --json --model keysight-dsox4024a --seconds 1e-6
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --simulate --json --model keysight-dsox4024a --query
```

`trigger-holdoff --seconds` is an explicit state-changing command. It disables
random holdoff with `:TRIGger:HOLDoff:RANDom OFF`, then sends
`:TRIGger:HOLDoff <seconds>`. Query mode sends `:TRIGger:HOLDoff?`. The v1
range is `40e-9` through `10.0` seconds. `doctor`, `smoke`, and
`acquisition-check` never run `trigger-holdoff`.

Worker JSON for `trigger-holdoff` accepts only `{"query": true}` or
`{"seconds": 0.000001}`. Empty arguments, `query: false`, query combined with
seconds, string/boolean/null seconds, unknown fields, and holdoff mode aliases
are rejected before enqueue, artifact creation, simulator/VISA session open, or
SCPI. Random holdoff and minimum/maximum holdoff commands are not implemented.

Configure or query Keysight Edge Trigger Coupling and Reject filter settings with the canonical `trigger-edge-coupling` and `trigger-edge-reject` commands:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --coupling ac --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --coupling dc --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --coupling lf-reject --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi

.\.venv\Scripts\scopes-tool.exe trigger-edge-reject --resource "$env:SCOPES_TOOL_RESOURCE" --reject off --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-reject --resource "$env:SCOPES_TOOL_RESOURCE" --reject lf-reject --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-reject --resource "$env:SCOPES_TOOL_RESOURCE" --reject hf-reject --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-reject --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

`trigger-edge-coupling` uses `:TRIGger:EDGE:COUPling` and accepts only `--coupling ac`, `--coupling dc`, or `--coupling lf-reject`. `trigger-edge-reject` uses `:TRIGger:EDGE:REJect` and accepts only `--reject off`, `--reject lf-reject`, or `--reject hf-reject`.

Each command rejects `--query` combined with configure options and rejects missing configure options when not querying.

**Coupling Interaction Warning**:
Changing Edge Trigger coupling may affect the reject filter readback, and changing reject-filter may affect the coupling readback on the real instrument. The system does not attempt to force both simultaneously, automatically restore, or add hidden corrective/extra SCPI commands. Each command configures or queries only its own SCPI setting, and the simulator does not emulate all hardware coupling side effects.

**Distinction from existing commands**:
The Phase 11 common command `trigger-hf-reject` uses `:TRIGger:HFReject` and represents a general high-frequency reject filter setting. The new `trigger-edge-reject` command is specific to the Edge Trigger surface and operates through the separate `:TRIGger:EDGE:REJect` path. These commands are independent and do not redirect or replace each other.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-coupling --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-coupling --arguments-json "{\"coupling\":\"ac\"}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-reject --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-reject --arguments-json "{\"reject\":\"hf-reject\"}" --json
```

Worker JSON for `trigger-edge-coupling` accepts only `query` or `coupling`. Worker JSON for `trigger-edge-reject` accepts only `query` or `reject`. Invalid inputs, uppercase value strings, unknown fields, and alias commands/keys (such as `edge-trigger-coupling`, `edge-trigger-reject`, `couple`, `reject_mode`, `filter`, etc.) are rejected before enqueue, artifact creation, simulator/VISA session open, or SCPI.


Configure or query Keysight pulse-width trigger settings with the canonical
`trigger-pulse-width` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-pulse-width --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity positive --qualifier less-than --time-seconds 1e-6 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pulse-width --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity negative --qualifier greater-than --time-seconds 5e-6 --level-volts 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pulse-width --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity positive --qualifier range --min-time-seconds 1e-6 --max-time-seconds 10e-6 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pulse-width --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

`trigger-pulse-width` configures and queries the Keysight Pulse Width trigger
using the underlying `:TRIGger:GLITch...` SCPI family. Configure mode is
state-changing: it selects Pulse Width trigger mode, sets an analog source
channel, optionally sets the trigger level, then sets
polarity and the selected pulse-width qualifier. Range configure maps
`--max-time-seconds` to the first SCPI `RANGe` parameter and
`--min-time-seconds` to the second parameter. Query mode preserves raw source
and level responses and tolerates current instrument state such as digital,
external, or `NONE` source readback.

This slice is analog-channel-only for configure mode. It does not run, stop,
single, force trigger, wait for a trigger, capture waveform data, or implement
pattern, delay, TV, USB, serial bus, digital/MSO, zone, or other trigger types.
Hardware-free tests cover this command; broader live validation remains opt-in
and model/transport-specific.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-pulse-width --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-pulse-width --arguments-json "{\"channel\":1,\"polarity\":\"positive\",\"qualifier\":\"less_than\",\"time_seconds\":0.000001}" --json
```

Configure or query analog runt trigger settings with the canonical
`trigger-runt` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-runt --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity either --qualifier none --low-level-volts -0.5 --high-level-volts 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-runt --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity positive --qualifier greater-than --time-seconds 5e-6 --low-level-volts -0.25 --high-level-volts 0.75 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-runt --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

`trigger-runt` configures and queries the Keysight Runt trigger using
`:TRIGger:MODE RUNT`, `:TRIGger:RUNT:*`, and shared
`:TRIGger:LEVel:LOW/HIGH` threshold commands. Configure mode is
state-changing: it selects Runt trigger mode, sets an analog source channel,
sets low and high analog thresholds, then sets polarity and qualifier. The
qualifier is `greater-than`, `less-than`, or `none`; only the timed qualifiers
send `:TRIGger:RUNT:TIME`. `none` rejects `--time-seconds`. Query mode reads
mode, source, polarity, qualifier, and stored runt time first, then reads
LOW/HIGH levels only when the source readback safely parses as an analog
`CHAN<n>` or `CHANnel<n>` source. Non-analog or unrecognized source readbacks
are preserved in JSON with `channel`, `low_level_volts`, and
`high_level_volts` set to `null`.

This slice is analog-channel-only for configure mode. It does not run, stop,
single, force trigger, wait for a trigger, capture waveform data, or implement
generic trigger configuration, transition, pattern, search, wait, force,
run/stop, capture, waveform, or WebUI runtime behavior. Hardware-free tests
cover the CLI, Core, simulator, and worker paths; live hardware validation has
not been run for `trigger-runt`.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-runt --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-runt --arguments-json "{\"channel\":1,\"polarity\":\"either\",\"qualifier\":\"none\",\"low_level_volts\":-0.5,\"high_level_volts\":0.5}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-runt --arguments-json "{\"channel\":1,\"polarity\":\"positive\",\"qualifier\":\"greater_than\",\"time_seconds\":0.000005,\"low_level_volts\":-0.25,\"high_level_volts\":0.75}" --json
```

Configure or query analog transition trigger settings with the canonical
`trigger-transition` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-transition --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --slope positive --qualifier greater-than --time-seconds 5e-6 --low-level-volts -0.5 --high-level-volts 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-transition --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --slope negative --qualifier less-than --time-seconds 2e-6 --low-level-volts -0.25 --high-level-volts 0.75 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-transition --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```

`trigger-transition` configures and queries the Keysight Transition trigger
using `:TRIGger:MODE TRANsition`, `:TRIGger:TRANsition:*`, and shared
`:TRIGger:LEVel:LOW/HIGH` threshold commands. Configure mode is
state-changing: it selects Transition trigger mode, sets an analog source
channel, sets low and high analog thresholds, then sets slope, time, and
qualifier. The slope is `positive` or `negative`; the qualifier is
`greater-than` or `less-than`; `--time-seconds`, `--low-level-volts`, and
`--high-level-volts` are required, and low must be less than high.

Query mode reads mode, source, slope, qualifier, and transition time first,
then reads LOW/HIGH levels only when the source readback safely parses as an
analog `CHAN<n>` or `CHANnel<n>` source. Non-analog or unrecognized source
readbacks are preserved in JSON with `channel`, `low_level_volts`, and
`high_level_volts` set to `null`.

This v1 slice is analog-channel-only for configure mode. It does not configure
digital/MSO or external transition sources, add aliases, run, stop, single,
force trigger, wait for a trigger, capture waveform data, or implement generic
trigger-tree behavior. Hardware-free tests cover the CLI, Core, simulator, and
worker paths. Live CLI validation, worker live validation, LAN validation,
WebUI validation, DSO-X 2000X/3000X/4024A/4034A live validation, digital/MSO
source validation, and broader trigger-tree validation have not been run.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-transition --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-transition --arguments-json "{\"channel\":1,\"slope\":\"positive\",\"qualifier\":\"greater_than\",\"time_seconds\":0.000005,\"low_level_volts\":-0.5,\"high_level_volts\":0.5}" --json
```

Configure or query analog-channel Edge Then Edge / Delay trigger settings with
the canonical `trigger-delay` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-delay --resource "$env:SCOPES_TOOL_RESOURCE" --arm-channel 1 --arm-slope positive --trigger-channel 2 --trigger-slope negative --time-seconds 1e-6 --count 2 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-delay --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-delay --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-delay --simulate --json --query
```

`trigger-delay` v1 configures and queries the Keysight Edge Then Edge / Delay
trigger using `:TRIGger:MODE DELay` and the `:TRIGger:DELay:*` SCPI family.
Configure mode is state-changing and DSO analog-channel-only: it sets an
analog arm source channel, arm slope, delay time, Nth trigger edge count,
analog trigger source channel, and trigger slope. Public slope values are only
`positive` and `negative`; aliases such as `pos`, `neg`, `rising`, `falling`,
`either`, and `alternate` are rejected. `--time-seconds` must be from `4e-9`
through `10.0`, and `--count` must be an integer at least `1`.

Query mode reads `:TRIGger:MODE?`,
`:TRIGger:DELay:ARM:SOURce?`, `:TRIGger:DELay:ARM:SLOPe?`,
`:TRIGger:DELay:TDELay:TIME?`,
`:TRIGger:DELay:TRIGger:COUNt?`,
`:TRIGger:DELay:TRIGger:SOURce?`, and
`:TRIGger:DELay:TRIGger:SLOPe?`. It preserves raw readbacks and tolerates
digital or unknown source state; configure mode does not accept digital,
external, level-volts, threshold, source-alias, or generic trigger-tree
arguments. Every live or simulated command performs one `:SYSTem:ERRor?`
post-check. This slice has hardware-free CLI, Core, simulator, and worker
validation only; no live hardware validation, LAN validation, worker live
validation, DSO-X 2000X/3000X/4024A/4034A live validation, or WebUI runtime
validation is implied. It does not add run, stop, single, force-trigger,
wait-trigger, or capture integration.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-delay --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-delay --arguments-json "{\"arm_channel\":1,\"arm_slope\":\"positive\",\"trigger_channel\":2,\"trigger_slope\":\"negative\",\"time_seconds\":0.000001,\"count\":2}" --json
```

Configure or query DSO analog-channel setup-hold trigger settings with the
canonical `trigger-setup-hold` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-setup-hold --resource "$env:SCOPES_TOOL_RESOURCE" --clock-channel 1 --data-channel 2 --slope positive --setup-time 1e-9 --hold-time 1e-9 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-setup-hold --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-setup-hold --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-setup-hold --simulate --json --query
```

`trigger-setup-hold` v1 configures and queries the Keysight Setup and Hold
trigger using `:TRIGger:MODE SHOLd` and the `:TRIGger:SHOLd:*` SCPI family.
Configure mode is state-changing and DSO analog-channel-only: it sets analog
clock and data source channels, clock slope, setup time, and hold time. Public
slope values are only `positive` and `negative`; aliases such as `pos`, `neg`,
`rising`, and `falling` are rejected. `--setup-time` and `--hold-time` are
plain seconds values and must be positive finite numbers. v1 does not parse
time suffixes.

Query mode reads `:TRIGger:MODE?`,
`:TRIGger:SHOLd:SOURce:CLOCk?`, `:TRIGger:SHOLd:SOURce:DATA?`,
`:TRIGger:SHOLd:SLOPe?`, `:TRIGger:SHOLd:TIME:SETup?`, and
`:TRIGger:SHOLd:TIME:HOLD?`. Query JSON preserves raw mode/source/slope/time
readbacks, normalizes `SHOL`/`SHOLD` mode readbacks to `setup-hold`, normalizes
common analog channel and positive/negative slope readbacks, and tolerates
digital or unknown source readback by leaving the parsed analog channel null.
Query does not fail only because the current trigger mode is not setup-hold.

Configure mode rejects partial configure requests, `--query` combined with
configure options, non-integer channels, channels outside the selected model
profile, digital/MSO source aliases such as `D0`, `DIG0`, `digital0`, `pod`, or
`bus`, unknown source aliases, invalid slopes, and non-finite, zero, negative,
or nonnumeric setup/hold times before instrument access. MSO/digital and
external setup-hold sources are intentionally unsupported in v1 even though
the instrument SCPI family may support digital sources on MSO models. This
command does not implement threshold/level convenience helpers, run, stop,
single, force trigger, wait-trigger, capture integration, actual
signal-trigger validation, or a generic trigger-tree framework.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-setup-hold --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-setup-hold --arguments-json "{\"clock_channel\":1,\"data_channel\":2,\"slope\":\"positive\",\"setup_time\":0.000000001,\"hold_time\":0.000000001}" --json
```

Worker JSON uses canonical keys `setup_time` and `hold_time`, matching the CLI
`--setup-time` and `--hold-time` options. Focused DSO-X 4034A USB CLI live
validation passed on 2026-07-08. Worker live, LAN, WebUI, DSO-X
2000X/3000X/4024A live validation, additional DSO-X 4034A live validation,
MSO/digital source validation, actual signal-trigger behavior, and broader
trigger-tree validation have not been run for `trigger-setup-hold`.

Configure or query DSO analog-channel Nth Edge Burst trigger settings with the
canonical `trigger-edge-burst` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --slope positive --count 3 --idle-time 1e-6 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --slope positive --count 3 --idle-time 1e-6 --level-volts 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --dry-run --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --simulate --json --query
```

`trigger-edge-burst` v1 configures and queries the Keysight Nth Edge Burst
trigger using `:TRIGger:MODE EBURst`,
`:TRIGger:EBURst:SOURce`, `:TRIGger:EBURst:SLOPe`,
`:TRIGger:EBURst:COUNt`, and `:TRIGger:EBURst:IDLE`.
Configure mode is state-changing and DSO analog-channel-only: it accepts
`--source-channel`, `--slope positive|negative`, `--count`, `--idle-time`, and
optional `--level-volts`. When `--level-volts` is provided, the command sends
`:TRIGger:EDGE:LEVel <level>, CHANnel<n>` after the EBURst fields; when it is
omitted, no level write is sent.

Query mode reads EBURst mode/source/slope/count/idle fields. It reads analog
edge level only when the source readback safely parses as analog `CHAN<n>` or
`CHANnel<n>`. Digital, `NONE`, and unknown source readbacks are preserved in
raw fields and do not fail query solely because the current source is outside
this v1 configure surface.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-burst --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-burst --arguments-json "{\"source_channel\":1,\"slope\":\"positive\",\"count\":3,\"idle_time\":0.000001}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-burst --arguments-json "{\"source_channel\":1,\"slope\":\"positive\",\"count\":3,\"idle_time\":0.000001,\"level_volts\":0.5}" --json
```

Worker support has hardware-free validation only. It accepts only `query`,
`source_channel`, `slope`, `count`, `idle_time`, and optional `level_volts`;
aliases such as `channel`, `source`, `edge_count`, `idle_time_seconds`,
`time_seconds`, `trigger_level`, and `level` are not accepted. Focused DSO-X
4034A USB CLI live validation passed on 2026-07-09. Worker live, LAN, WebUI,
DSO-X 2000X/3000X/4024A, additional DSO-X 4034A, MSO/digital source
validation, actual signal-trigger behavior, broader trigger-tree behavior, and
capture/wait-trigger/run/stop/single workflow integration have not been run or
implemented for `trigger-edge-burst`.

Configure or query DSO analog-channel basic TV / video trigger settings with
the canonical `trigger-tv` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-tv --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-tv --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --standard ntsc --mode field1 --polarity negative --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-tv --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --standard ntsc --mode line-field1 --line 20 --polarity negative --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-tv --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 2 --standard pal --mode line-field2 --line 400 --polarity positive --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-tv --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-tv --simulate --json --query
```

`trigger-tv` v1 configures and queries the common Keysight TV trigger subtree
using `:TRIGger:MODE TV`, `:TRIGger:TV:SOURce`,
`:TRIGger:TV:STANdard`, `:TRIGger:TV:MODE`, optional
`:TRIGger:TV:LINE`, and `:TRIGger:TV:POLarity`. Configure mode is
state-changing and DSO analog-channel-only: it accepts `--source-channel`,
`--standard ntsc|pal|palm|secam`, `--mode field1|field2|all-fields|all-lines|line-field1|line-field2|line-alternate`,
`--polarity positive|negative`, and optional `--line` only for line modes.
Extended video standards, UDTV commands, 3000X/4000X-only `LINE` mode,
digital/MSO, external, USB, NFC, serial/bus, and zone trigger configuration
are not part of this v1 surface.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-tv --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-tv --arguments-json "{\"source_channel\":1,\"standard\":\"ntsc\",\"mode\":\"field1\",\"polarity\":\"negative\"}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-tv --arguments-json "{\"source_channel\":1,\"standard\":\"ntsc\",\"mode\":\"line-field1\",\"line\":20,\"polarity\":\"negative\"}" --json
```

Worker support has hardware-free validation only. It accepts only `query`,
`source_channel`, `standard`, `mode`, `line`, and `polarity`; aliases such as
`channel`, `source`, `tv_source`, `tv_standard`, `trigger_standard`, `tv_mode`,
`trigger_mode`, `line_number`, `field`, `pol`, `trigger_polarity`,
`polarity_raw`, `sourceChannel`, and `source_channel_number` are not accepted.
Live CLI, worker live, LAN, WebUI, DSO-X 2000X/3000X/4024A/4034A live
validation, MSO/digital source validation, extended video/UDTV, actual
signal-trigger behavior, and capture/wait-trigger/run/stop/single workflow
integration have not been run or implemented for `trigger-tv`.

Configure or query DSO analog ASCII pattern trigger settings with the canonical
`trigger-pattern` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-pattern --resource "$env:SCOPES_TOOL_RESOURCE" --pattern XXX1 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pattern --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pattern --dry-run --json --pattern XXX1
.\.venv\Scripts\scopes-tool.exe trigger-pattern --simulate --json --query
```

`trigger-pattern` v1 configures and queries the Keysight Pattern trigger using
the DSO analog ASCII entered-pattern surface only. Configure mode is
state-changing and sends `:TRIGger:MODE PATTern`,
`:TRIGger:PATTern:FORMat ASCii`, `:TRIGger:PATTern "<pattern>"`, and
`:TRIGger:PATTern:QUALifier ENTered`. The pattern is a raw ASCII string using
only `0`, `1`, and `X`; lowercase input is normalized to uppercase. The CLI
rejects empty strings, whitespace, commas, quotes, `R`, `F`, `0x...`, and other
characters before opening an instrument. Pattern length must match the selected
model profile analog channel count.

Query mode reads `:TRIGger:MODE?`, `:TRIGger:PATTern:FORMat?`,
`:TRIGger:PATTern?`, and `:TRIGger:PATTern:QUALifier?`. JSON normalizes common
readbacks such as `ASC`/`ASCii` to `ascii`, `HEX` to `hex`, and
`ENT`/`ENTered` to `entered`, while preserving raw pattern response,
edge-source, and edge readback fields.

This v1 slice does not support HEX configure mode, digital/MSO pattern
configuration, `R`/`F`, edge source/edge configure parameters, duration
qualifiers, pattern range commands, source commands, level commands, aliases,
or generic trigger-tree behavior. Hardware-free Core/CLI/simulator/worker
tests cover this command. No live hardware validation was run because no
instrument is currently available. Pending validation includes live CLI,
worker live, LAN, WebUI, DSO-X 2000X/3000X/4024A/4034A live validation,
MSO/digital validation, and broader trigger-tree validation.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-pattern --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-pattern --arguments-json "{\"pattern\":\"XXX1\"}" --json
```

Configure or query DSO analog-only OR trigger settings with the canonical
`trigger-or` command:

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-or --resource "$env:SCOPES_TOOL_RESOURCE" --pattern XXXR --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-or --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-or --dry-run --json --pattern XXXR
.\.venv\Scripts\scopes-tool.exe trigger-or --simulate --json --query
```

`trigger-or` v1 configures and queries the Keysight OR trigger using the DSO
analog-only `:TRIGger:OR` surface. Configure mode is state-changing and sends
`:TRIGger:MODE OR` followed by `:TRIGger:OR "<pattern>"`. The pattern is a raw
edge string using only `R` for rising edge, `F` for falling edge, `E` for
either edge, and `X` for don't care; lowercase input is normalized to
uppercase. The CLI rejects empty strings, whitespace, commas, quotes, digits
`0`/`1`, `0x...`, and other characters before opening an instrument. Pattern
length must match the selected registered model's analog-channel capability.

For DSO analog-only mapping, string order follows Keysight OR trigger bit
assignment. The currently registered models are all four-channel models, so
positions are CH4, CH3, CH2, CH1. CH1 rising only is `XXXR`, CH1 rising OR CH2
falling is `XXFR`, and any analog channel either edge is `EEEE`.

Query mode reads `:TRIGger:MODE?` and `:TRIGger:OR?`. JSON preserves
`raw_mode` and `raw_pattern`, normalizes common quoted or unquoted valid
readbacks to uppercase `pattern`, and tolerates non-OR current trigger mode
without failing solely because the mode is not OR.

This v1 slice does not implement MSO/digital OR trigger mapping, aliases,
generic trigger-tree behavior, run, stop, single, force trigger, wait for a
trigger, capture waveform data, or WebUI runtime behavior. Hardware-free
Core/CLI/simulator/worker tests cover this command. No live hardware
validation was run. Worker support is hardware-free only until separately
live-tested.

Worker usage:

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-or --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-or --arguments-json "{\"pattern\":\"XXXR\"}" --json
```

Control common measurement subsystem state:

```powershell
.\.venv\Scripts\scopes-tool.exe measure-clear --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-show --on --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-show --query --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-source --source-channel 1 --source2-channel 2 --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-source --query --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-window --window gate --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-window --query --simulate --json
```

`measure-clear` clears installed screen measurements. `measure-show` supports
ON and query only; OFF is intentionally not exposed because the common
2000X/3000X behavior documents always-on measurement markers. `measure-source`
accepts one or two analog channels validated against the selected model
profile. Digital, math/function, and reference measurement sources are not
accepted. `--source-channel <n>` sets source1 but does not necessarily clear an
existing source2 selection. A later query may therefore report source1 together
with the preserved source2; treat that as success when source1 matches and the
instrument error queue is clean. Use both `--source-channel <n>` and
`--source2-channel <m>` when an explicit two-source default is required.
Source2 is mainly meaningful for two-source measurements such as delay and
phase.

`measure-window` accepts `main`, `zoom`, `auto`, or `gate`. `zoom` is
conditional on the oscilloscope already displaying the zoomed timebase. On
DSO-X 4034A firmware 07.20, setting `zoom` while that timebase is not displayed
may return `-221,"Settings conflict"`. Use `auto` as the safer portable choice
when the current zoom state is unknown.

Control or query DVM Common Pack v1:

```powershell
.\.venv\Scripts\scopes-tool.exe dvm-enable --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-enable --query --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-source --channel 1 --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-source --query --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-mode --mode dc-rms --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-mode --query --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-auto-range --enabled false --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-current --query --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-query --query --simulate --json
```

The only public modes are `dc`, `dc-rms`, and `ac-rms`; no aliases or
uppercase values are accepted. Boolean configuration uses only
`--enabled true|false`. DVM source is an analog channel validated against the
selected model profile. Current and aggregate results preserve raw readbacks;
sentinel or non-finite readings return `value: null`, `valid: false`, and a
reason instead of crashing. DVM availability may depend on an instrument
option or license, and live rejection flows through the normal instrument
error handling path.

`dvm-frequency`, `:DVM:FREQuency?`, `:DVM:MODE FREQuency`, the independent
`:COUNter` subsystem, Counter CLI commands, and `:MEASure:COUNter` are
intentionally unsupported in DVM Common Pack v1. Normal tests are
hardware-free, and no live hardware validation was performed for this pack.

Worker requests use the same canonical values and require `{"query": true}`
for query operations. Unknown keys, aliases, mixed query/configure payloads,
non-boolean `enabled`, and channels outside the model profile are rejected
before enqueue or artifact/session creation.

Control Demo Output Pack v1:

```powershell
.\.venv\Scripts\scopes-tool.exe demo-query --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-output --query --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-output --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-function --query --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-function --function runt --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-phase --query --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-phase --degrees 90 --simulate --json
```

`demo-output`, `demo-function`, and `demo-phase` require exactly one query or
configure action. Functions use lowercase canonical names only. Phase must be
a finite number from 0 through 360 inclusive. Function support is checked
against the selected model profile before session open. Aggregate
`demo-query` preserves exact raw readbacks; an unknown function token produces
`function: null` and `function_scpi: null`, while malformed output or phase
readbacks fail normally.

The common/core function set is `sine`, `noisy`, `phase`, `lf-sine`, `am`,
`rf-burst`, `fm-burst`, `harmonics`, `coupling`, `ringing`, `single`, `clock`,
`runt`, `transition`, `setup-hold`, `mso`, `burst`, `glitch`,
`edge-then-edge`, `i2c`, `uart`, `spi`, `can`, and `lin`. The 3000X and 4000X
profiles additionally expose `i2s`, `can-lin`, `flexray`, `arinc`, `mil`, and
`mil2`. Additional 4000X-only DEMO functions are intentionally excluded from
v1.

DEMO is option-/hardware-dependent. Unsupported live instruments may surface
errors through the normal post-command instrument error check. This pack has
hardware-free Core, CLI, simulator, and worker validation only; live hardware,
USB/LAN, and worker live validation were not run. It does not implement WGEN
and adds no WebUI runtime behavior.

Control reference waveform slots:

```powershell
.\.venv\Scripts\scopes-tool.exe reference-save --slot 1 --source-channel 1 --simulate --json
.\.venv\Scripts\scopes-tool.exe reference-display --slot 1 --state on --simulate --json
.\.venv\Scripts\scopes-tool.exe reference-label --slot 1 --text BASELINE --simulate --json
.\.venv\Scripts\scopes-tool.exe reference-query --slot 1 --simulate --json
.\.venv\Scripts\scopes-tool.exe reference-clear --slot 1 --simulate --json
```

Reference Waveform Pack v1 supports slots 1 and 2. `reference-save` accepts an
analog channel source only. `reference-display` configures or queries slot
display state, `reference-label` configures or queries a 1-10 character
printable ASCII label without double quotes, and `reference-query` reads both
display and label state while preserving raw readbacks in JSON. File-based
`:SAVE:WMEMory`/`:RECall:WMEMory` workflows and reference skew, offset, range,
and scale controls are not implemented. Focused DSO-X 4034A USB CLI live
validation passed for save, display, label, query, and clear operations on
slots 1 and 2. Enabling display for one reference slot may turn off display for
the other slot on this instrument; this instrument-managed interaction is
normal behavior, not a command failure. The simulator tracks the two display
states independently and does not emulate that interaction. LAN, worker live,
other-model, and broader reference-waveform validation have not been run.

Control Search Basic Pack v1:

```powershell
.\.venv\Scripts\scopes-tool.exe search-state --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe search-state --query --simulate --json
.\.venv\Scripts\scopes-tool.exe search-mode --mode serial1 --simulate --json --model keysight-dsox2004a
.\.venv\Scripts\scopes-tool.exe search-mode --mode edge --simulate --json --model keysight-dsox3024a
.\.venv\Scripts\scopes-tool.exe search-mode --mode peak --simulate --json --model keysight-dsox4034a
.\.venv\Scripts\scopes-tool.exe search-mode --query --simulate --json
.\.venv\Scripts\scopes-tool.exe search-count --query --simulate --json
```

`search-state` accepts exactly one of `--query` or
`--enabled true|false`. `search-mode` accepts exactly one of `--query` or one
lowercase canonical mode. Configuring a mode sends `:SEARch:STATe 1` before
`:SEARch:MODE <mode>`. `search-count` is query-only and requires `--query`.

Runtime support is capability-profile guarded: 2000X supports `serial1` only;
3000X supports `edge`, `glitch`, `runt`, `transition`, `serial1`, and
`serial2`; 4000X supports those modes plus `peak`. Aliases such as `ser1`,
`ser2`, `glit`, `tran`, and `off` are rejected. Unsupported modes are rejected
before search SCPI is sent. Search event navigation, mode-specific search
parameter commands, and serial search pattern configuration are not
implemented in this pack. Tests are hardware-free; no live hardware validation
was performed.

Use Save/Export Pack v1 for instrument-side file saving:

```powershell
.\.venv\Scripts\scopes-tool.exe save-pwd --path "USB:\captures" --simulate --json
.\.venv\Scripts\scopes-tool.exe save-pwd --query --simulate --json
.\.venv\Scripts\scopes-tool.exe save-filename --name scope_01 --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image-format --format png --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image-palette --palette color --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image-ink-saver --enabled false --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image-factors --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image --filename "USB:\captures\screen.png" --simulate --json
.\.venv\Scripts\scopes-tool.exe save-waveform-format --format csv --simulate --json
.\.venv\Scripts\scopes-tool.exe save-waveform-length --points 1000 --simulate --json
.\.venv\Scripts\scopes-tool.exe save-waveform-length-max --query --simulate --json
.\.venv\Scripts\scopes-tool.exe save-waveform --filename "USB:\captures\wave.csv" --simulate --json
```

Query-capable commands require exactly `--query` or their setting argument.
Settable image formats are `png`, `bmp`, `bmp8`, and `bmp24`; palettes are
`color` and `grayscale`; settable waveform formats are `ascii-xy`, `csv`, and
`binary`. Format queries may return the instrument sentinel `NONE`, normalized
to canonical `none`, when the other file-format family is selected. Boolean
settings require explicit `true|false`. Waveform length must be an integer of
at least 100 points; the actual maximum is instrument/model dependent.
`save-waveform-length-max` is query-only.

All quoted SAVE strings must be printable ASCII and cannot contain double
quotes, controls, CR/LF, or semicolons. `save-filename --name` is a base name
only and also rejects path and drive separators. Instrument paths and explicit
image/waveform file specifications may contain `/`, `\`, and `:`. Values are
not trimmed, sanitized, escaped, or given automatic extensions. `save-image`
and `save-waveform` require an explicit filename in v1 for agent safety and
wait for `*OPC?` after starting the save. `save-image` uses a bounded 15-second
timeout for this completion query and then restores the prior session timeout;
`save-waveform` retains the current session timeout.

These commands send `:SAVE...` SCPI so the oscilloscope writes to its own
current save directory, internal storage, or attached USB storage. They do not
create or check host-side files. Existing `capture`, `capture-batch`, and
`screenshot` continue to retrieve bytes and write PC-side artifacts. Save/
Export Pack v1 excludes results, lister, mask, multi, power, arbitrary,
compliance, segmented, setup changes, and WMEMory export. It has hardware-free
validation only; live hardware validation was not performed.

Query read-only measurements:

```powershell
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vpp --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item frequency --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item period --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vavg --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vrms --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item ac_rms --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item minimum --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item maximum --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item x_at_max --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item x_at_min --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item rise_time --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item fall_time --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item amplitude --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item top --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item base --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item overshoot --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item preshoot --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item positive_width --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item negative_width --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item duty_cycle --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item negative_duty_cycle --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item area --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item positive_edges --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item negative_edges --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item positive_pulses --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item negative_pulses --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item y_at_x --time 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item time_at_edge --slope positive --occurrence 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item time_at_value --level 0.5 --slope positive --occurrence 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --reference-channel 2 --item phase --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --reference-channel 2 --item delay --log-scpi
```

The current measurement slice supports `vpp`, `frequency` (`freq` alias),
`period`, `vavg`, `vrms`, `ac_rms` (`acrms` and `vrms_ac` aliases),
`minimum` (`min` and `vmin` aliases), `maximum` (`max` and `vmax` aliases),
`x_at_max` (`xmax` and `x-at-max` aliases), `x_at_min` (`xmin` and
`x-at-min` aliases), `rise_time` (`risetime` and `rise-time` aliases),
`fall_time` (`falltime` and `fall-time` aliases), `amplitude` (`vamp` alias),
`top` (`vtop` alias), `base` (`vbase` alias), `overshoot`, `preshoot`,
`positive_width` (`pwidth`, `positive-width`, and `pwid` aliases),
`negative_width` (`nwidth`, `negative-width`, and `nwid` aliases),
`duty_cycle` (`duty`, `dutycycle`, and `duty-cycle` aliases), and
`negative_duty_cycle` (`nduty`, `negative-duty`, and `negative-duty-cycle`
aliases), `area`, `positive_edges` (`pedges` and `positive-edges` aliases),
`negative_edges` (`nedges` and `negative-edges` aliases), `positive_pulses`
(`ppulses` and `positive-pulses` aliases), and `negative_pulses` (`npulses`
and `negative-pulses` aliases), plus parameterized single-channel queries:
`y_at_x` (`yatx`, `y-at-x`, `vtime`, `y_at_time`, and `y-at-time` aliases),
`time_at_edge` (`tedge` and `time-at-edge` aliases), and `time_at_value`
(`tvalue`, `time-at-value`, `time_at_level`, and `time-at-level` aliases),
plus two-channel `phase` and 4000X-only safe `delay`.
`y_at_x` requires `--time`; `time_at_value` requires `--level`;
`time_at_edge` and `time_at_value` accept `--slope positive|negative` and
`--occurrence N`, defaulting to positive occurrence 1. Two-channel items require
a source channel and reference channel; `--channel` remains a compatibility
alias for `--source-channel`, and cannot be combined with it. Single-channel
items reject `--reference-channel`. The command first queries `*IDN?`,
validates the analog channel or channel pair, sends one read-only measurement
query such as `:MEASure:VPP? CHANnel1`, and performs one `:SYSTem:ERRor?`
post-check. The added item queries are
`:MEASure:VRMS? DISPlay,AC,CHANnelN`, `:MEASure:XMAX? CHANnelN`,
`:MEASure:XMIN? CHANnelN`,
`:MEASure:VAMPlitude? CHANnelN`, `:MEASure:VTOP? CHANnelN`,
`:MEASure:VBASe? CHANnelN`, `:MEASure:OVERshoot? CHANnelN`,
`:MEASure:PREShoot? CHANnelN`, `:MEASure:PWIDth? CHANnelN`,
`:MEASure:NWIDth? CHANnelN`, `:MEASure:DUTYcycle? CHANnelN`,
`:MEASure:NDUTy? CHANnelN`, `:MEASure:AREA? CHANnelN`,
`:MEASure:PEDGes? CHANnelN`, `:MEASure:NEDGes? CHANnelN`,
`:MEASure:PPULses? CHANnelN`, `:MEASure:NPULses? CHANnelN`,
`:MEASure:VTIMe? <time>,CHANnelN`,
`:MEASure:TEDGe? +/-<occurrence>,CHANnelN`, and
`:MEASure:TVALue? <level>,+/-<occurrence>,CHANnelN`,
`:MEASure:PHASe? CHANnel<src>,CHANnel<ref>`, and
`:MEASure:DELay? AUTO,CHANnel<src>,CHANnel<ref>`. `delay` is intentionally
limited to 4000X models because the 2000X/3000X delay query depends on
`:MEASure:DEFine` state. It does not change acquisition mode, trigger settings,
measurement source, measurement window, display state, VISA timeout, or
return-to-local behavior.
Invalid measurement sentinels such as `9.9E+37` are printed as
`Value: unavailable` with `Valid: false` and the original raw response
preserved; the CLI exits non-zero so automation does not treat the unavailable
value as usable data.

Collect a read-only diagnostic snapshot:

```powershell
.\.venv\Scripts\scopes-tool.exe doctor --resource "$env:SCOPES_TOOL_RESOURCE" --json --log-scpi
```

`doctor` queries `*IDN?`, backend and timeout metadata, acquisition type and
count, every analog channel's display, scale, offset, coupling, probe ratio,
and bandwidth limit, horizontal scale and position, and analog edge trigger
source, level, and slope. It performs one final `:SYSTem:ERRor?` post-check and
does not drain the full error queue.

Sweep common measurements across channels:

```powershell
.\.venv\Scripts\scopes-tool.exe measure-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --channel all --items vpp,frequency,period,vrms --json --log-scpi
.\.venv\Scripts\scopes-tool.exe measure-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --channel all --items vpp,frequency,period,vrms,rise_time,fall_time --pair 1:2 --pair-items phase,delay --json --log-scpi
```

`measure-sweep` defaults to `--channel all` and
`--items vpp,frequency,period,vrms`. Repeat `--channel` for explicit channels,
or add `--pair SRC:REF` with `--pair-items phase,delay` for pair measurements.
Each measurement record preserves validity, value, unit, raw response, reason,
SCPI command, and system error result. Invalid sentinels or per-item query
errors do not stop the sweep; the command returns non-zero after completing if
any invalid or error records were observed.

Log a finite batch of measurements:

```powershell
.\.venv\Scripts\scopes-tool.exe measure-log --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --items vpp,frequency --count 10 --interval-seconds 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure-log --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --items vpp,frequency --pair 1:2 --pair-items phase --count 5 --output-dir data\measure_logs\ch1_ch2 --log-scpi
```

`measure-log` is a finite read-only measurement logger. It requires `--count`
or `--duration-seconds` so an agent cannot accidentally start an unbounded
recorder. It defaults to `--channel all`, `--items vpp,frequency`,
`--pair-items phase,delay`, and `--interval-seconds 1.0`; pair measurements
run only when `--pair SRC:REF` is supplied. The command opens one session,
queries `*IDN?`, validates channels and measurement items, then writes
`measurements.csv`, `manifest.json`, and `scpi.log` under
`data/measure_logs/YYYY-MM-DD-HH-mm-ss` unless `--output-dir` is supplied.
The output directory must not exist or must be empty.

Each CSV row contains `timestamp_iso`, `elapsed_seconds`, one column per
requested measurement, and `NaN` for invalid measurement sentinels or per-item
query failures. One `:SYSTem:ERRor?` post-check is read after each row and
recorded in the manifest. With `--stop-on-error`, the command stops after the
row that reports an instrument error, leaves existing files in place, and
returns non-zero. It does not send `*RST`, change acquisition mode, wait for a
trigger, change timeout defaults, use background threads, or perform
return-to-local behavior.

Run a capture-safe smoke check:

```powershell
.\.venv\Scripts\scopes-tool.exe smoke --resource "$env:SCOPES_TOOL_RESOURCE" --json --log-scpi
```

`smoke` writes `report.json`, `scpi.log`, `capture.csv`,
`capture_meta.json`, and `screen.png` under
`data/hardware_smoke/YYYY-MM-DD-HH-mm-ss`, appending `-2`, `-3`, and so on if a
default directory already exists. Use `--output-dir DIR` to choose a directory;
it must not exist or must be empty. The default flow runs a doctor snapshot,
queries CH1 `vpp` and `vrms`, captures CH1 BYTE waveform data at 1000 points,
captures a black-background screenshot, and performs a final system error
post-check. Invalid measurement sentinels are warnings; capture, screenshot,
backend, output, or system-error failures make the command return non-zero.

Capture waveform data:

```powershell
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 10000 --csv data\ch1.csv --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --csv data\ch1.csv --plot data\ch1.png --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --format word --csv data\ch1_word.csv --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --points 1000 --csv data\ch1_ch2.csv --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --points 1000 --csv data\ch1_ch2.csv --allow-time-axis-tolerance --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel all --points 1000 --csv data\all_channels.csv --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --wait-trigger --trigger-timeout-ms 5000 --trigger-poll-interval-ms 100 --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --wait-trigger --trigger-timeout-ms 5000 --force-trigger-on-timeout --log-scpi
```

The current capture slice supports BYTE and WORD waveform formats with 1000,
5000, and 10000 requested points. BYTE remains the default. WORD capture sets
`:WAVeform:BYTeorder MSBFirst` and `:WAVeform:UNSigned ON` before reading data.
Capability flags describe the runtime-supported and guarded feature surface,
not whether each feature has completed live validation on every model.
Repeat `--channel` to capture multiple analog channels sequentially in one
session. Use `--channel all` to capture every analog channel reported by the
detected model capability profile; this does not query or filter by displayed
channels. Multi-channel CSV output uses the first channel's `time_s` axis and
writes voltage columns in requested order, such as `time_s,ch1_v,ch2_v`.
`--channel all` cannot be combined with explicit channel numbers.
Duplicate channels and channels outside the detected model capabilities are
rejected before waveform SCPI is sent. If the captured channel time axes or
sample counts do not match, the command fails instead of writing a misleading
aligned CSV. For `capture` only, `--allow-time-axis-tolerance` keeps sample
count checks strict but allows a small multi-channel time-axis drift when every
non-canonical channel is within half of CH1's sample interval at every point
when CH1 is included. The CSV still writes only the canonical `time_s` axis; the
command does not interpolate or resample. Metadata and `--json` output include
the canonical channel, max allowed delta, and per-channel max observed delta
when the opt-in tolerance is enabled.
If `--csv` is omitted, the CLI writes to `data/YYYY-MM-DD-HH-mm-ss.csv` using
the `UTC+8` timezone. If `--csv PATH` is provided, it writes exactly to that
path. Metadata JSON defaults to the same stem with `_meta.json` beside the CSV.
Single-channel metadata keeps the existing top-level `channel` and
`actual_points` fields. Multi-channel metadata has top-level IDN, resource,
model, series, format, and requested point fields plus ordered `channels`
entries containing each channel number, actual point count, preamble, and WORD
byte-order fields where applicable.
The command performs one `:SYSTem:ERRor?` post-check. It does not change VISA
timeout, acquisition mode, waveform point mode, or return-to-local behavior. If
the CSV or metadata file cannot be written because it is open in another
program or the folder is not writable, the CLI reports a plain `error:` message
instead of a Python traceback.

`capture --wait-trigger` is an explicit state-changing triggered capture mode.
It sends `:SINGle`, then polls only `:OPERegister:CONDition?` before waveform
readout. `--trigger-timeout-ms` is required with `--wait-trigger`.
`--trigger-poll-interval-ms` defaults to 100 ms and must be less than or equal
to the timeout. `--force-trigger-on-timeout` is valid only with
`--wait-trigger`; after the first finite wait times out it sends
`:TRIGger:FORCe`, then repeats the same finite poll window before capture. The
command does not use `:TRIGger:STATus?` or `*OPC?`.
For DSO-X 2000X/3000X/4000X models, operation-condition classification uses
the Operation Status Condition Run bit: Run set is pending, and Run clear is
complete. Other live series remain conservative until separately validated.

Triggered capture JSON adds `result.trigger`. Outcomes are `natural`, `forced`,
`timeout`, or `unknown`. Only `natural` and `forced` write waveform artifacts.
`timeout`, unsupported poll query, parse failure, or unclassified operation
condition state returns non-zero, writes no capture artifacts, records raw poll
values in `raw_values` and `condition_values`, and still performs one
`:SYSTem:ERRor?` post-check when possible. Unsupported live operation-condition
values remain unclassified and do not allow capture.

Capture a finite waveform batch:

```powershell
.\.venv\Scripts\scopes-tool.exe capture-batch --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --format byte --count 3 --interval-seconds 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe capture-batch --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --points 1000 --format word --count 2 --output-dir data\captures\ch1_ch2_batch --log-scpi
.\.venv\Scripts\scopes-tool.exe capture-batch --resource "$env:SCOPES_TOOL_RESOURCE" --channel all --points 1000 --count 2
```

`capture-batch` is a conservative finite batch capture command. `--count` is
required and must be a positive integer. `--interval-seconds` defaults to `0`
and must be a finite non-negative number; when non-zero, the sleep is applied
only between captures. The command opens one VISA session, queries `*IDN?`,
validates the detected capabilities, channels, point count, and waveform
format, then repeats the existing waveform capture APIs the requested number of
times. It performs one `:SYSTem:ERRor?` post-check after each capture.

If `--output-dir` is omitted, output is written under
`data/captures/YYYY-MM-DD-HH-mm-ss` using the `UTC+8` timezone. If that default
directory already exists, the CLI appends `-2`, `-3`, and so on to avoid
overwriting prior data. If `--output-dir DIR` is provided, `DIR` must not exist
or must be empty. This prevents new captures from being mixed with old files.

Each batch capture writes `waveform_0001.csv`,
`waveform_0001_meta.json`, and so on, using a sequence width of at least four
digits. The run directory also contains `manifest.json` with run parameters,
IDN fields, capture file paths, actual point counts, and system error results,
plus `scpi.log`. For `capture-batch`, `scpi.log` is always written; `--log-scpi`
additionally echoes the same package SCPI debug log to stderr for live hardware
checks.

If a post-capture system error is reported, the command leaves the already
written capture files and manifest in place, stops the remaining captures, and
returns non-zero. If interrupted from Python control flow, it writes a best
effort manifest with status `interrupted` and returns `130`.

Additional DSO-X 4024A controls:

```powershell
.\.venv\Scripts\scopes-tool.exe cursor --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe cursor --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --x1 0 --x2 1e-3 --y1 0 --y2 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --resource "$env:SCOPES_TOOL_RESOURCE" --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --resource "$env:SCOPES_TOOL_RESOURCE" --seconds 1e-6 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure-stats --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --items vpp,frequency --mode all --reset --log-scpi
.\.venv\Scripts\scopes-tool.exe autoscale --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --source-channel 2 --log-scpi
.\.venv\Scripts\scopes-tool.exe setup-save --resource "$env:SCOPES_TOOL_RESOURCE" --slot 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe setup-recall --resource "$env:SCOPES_TOOL_RESOURCE" --file "\usb\setup.scp" --log-scpi
.\.venv\Scripts\scopes-tool.exe fft --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --source-channel 1 --units decibel --window hanning --center-hz 1000 --span-hz 10000 --display on --log-scpi
.\.venv\Scripts\scopes-tool.exe fft --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --source-channel 1 --display off --log-scpi
.\.venv\Scripts\scopes-tool.exe fft --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe fft --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --source-channel 1 --fft-operation fft-phase --start-hz 100 --stop-hz 1000000 --gate zoom --phase-reference display --detection-type average --detection-points 4096 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-display --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --on --log-scpi
.\.venv\Scripts\scopes-tool.exe math-display --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-vertical --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --scale 2 --offset 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-vertical --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --range 8 --offset 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-vertical --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-operator --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation subtract --source1 channel1 --source2 channel2 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-operator --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-composite-source --resource "$env:SCOPES_TOOL_RESOURCE" --operation subtract --source1 channel1 --source2 channel2 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-composite-source --resource "$env:SCOPES_TOOL_RESOURCE" --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-transform --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation integrate --source channel1 --input-offset 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-transform --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation linear --source channel1 --gain 2 --linear-offset -1 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-transform --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-filter --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation low-pass --source channel1 --cutoff-hz 1000000 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-filter --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --operation average --source math1 --average-count 64 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-filter --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation magnify --source composite --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation trend --source channel1 --source2 channel2 --measurement vratio --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --operation max-hold --source math1 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --operation trend --measurement-slot 3 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-clear --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --log-scpi
```

The existing `fft`, `math-display`, `math-vertical`, `math-operator`, and
`math-transform`, `math-filter`, `math-visualization`, and `math-clear`
commands use the model's instrument-side Math function layout. 2000X and
3000X models have one unindexed `:FUNCtion` subsystem and
require `--function 1`. 4000X models use indexed `:FUNCtion1` through
`:FUNCtion4` slots and accept `--function 1..4`. The global
`math-composite-source` command is available only on 2000X/3000X and does not
take `--function`.

The existing `fft` command retains its basic 2000X/3000X magnitude behavior
and defaults to `--fft-operation fft`. On 4000X, `--fft-operation fft-phase`
selects FFT Phase. The 4000X-only optional controls are `--start-hz`,
`--stop-hz`, `--gate`, `--phase-reference`, `--detection-type`, and
`--detection-points`. Center/span and start/stop cannot be mixed in one
configure request. Phase reference is accepted only with FFT Phase.
`--units` applies only to magnitude FFT and must be omitted for FFT Phase.
`fft --query` additionally reports `start_hz`, `stop_hz`, `gate`,
`detection_type`, `detection_points`, `bin_size_hz`, `sample_rate_hz`,
`resolution_bandwidth_hz`, and a nullable `phase_reference` on 4000X.
The command does not automatically enable Math display, configure Zoom or
timebase, run autoscale, or change acquisition state. The derived query fields
come from the instrument and do not represent host-side FFT calculation.
This path has hardware-free validation only; no live hardware validation was
performed.

The P0-P7 instrument-side Math commands are closed under a hardware-free
consistency gate covering CLI choices, Worker keys, capability guards, Core
SCPI builders and parsers, simulator round trips, and the 2000X/3000X
unnumbered versus 4000X indexed function dialect. The supported per-series
operation matrix is documented in `../core/supported-models.md`. MATH-P8
bus-timing and bus-state remain unavailable because MSO/digital-channel
support is not implemented. No Math command performs host-side waveform
calculation.

`math-display` requires exactly one of `--on`, `--off`, or `--query`.
`math-vertical` query mode cannot include setters. Configure mode requires
`--scale`, `--range`, or `--offset`; scale and range are mutually exclusive,
while either may be combined with offset. Vertical configuration does not
automatically enable Math display, and the tool does not run autoscale.
Instrument firmware may recalculate vertical scaling when Math display changes
from OFF to ON. To preserve explicit vertical settings, run
`math-display --function N --on` before applying the desired `math-vertical`
scale, range, or offset setters. Enabling one 4000X Math slot does not actively
disable another slot; any single-visible-slot behavior is managed by the
instrument. MATH-P1 does not configure Math operations or sources, probe
licenses, or calculate host-side Math. These commands have hardware-free
validation only; no live hardware validation was performed.

`math-operator` configures or queries one instrument-side dual-source Math
operator. Configure requires `--operation`, `--source1`, and `--source2`;
query mode cannot include those options. P2 accepts `add`, `subtract`,
`multiply`, and `divide`. Source1 and source2 must both be canonical analog
channels `channel1` through `channel4` supported by the selected model.
It does not automatically enable Math display, alter Math vertical settings,
perform autoscale, calculate host-side waveforms, or probe licenses. Other
Math operations and reference, Math, bus, digital, external, or expression
sources are not supported. This path has hardware-free validation only;
license availability and live instrument behavior have not been validated.

`math-transform` configures or queries one instrument-side, single-source Math
transform. Supported operations are `differentiate`, `integrate`, `sqrt`,
`absolute`, `square`, `ln`, `log10`, `exp`, `exp10`, and `linear`. Configure
requires `--operation` and `--source`; sources include canonical analog channels
`channel1` through `channel4` within the selected model's channel count.
2000X/3000X additionally accept `composite`, while 4000X accepts only a
lower-numbered `math1` through `math3` source for the selected destination
function.
`--input-offset` is optional only for `integrate`. `--gain` and
`--linear-offset` are optional only for `linear`; omitting them preserves the
instrument's current values. Query mode cannot include configure options and
conditionally reads integrate or linear parameters after identifying the
current operation. It reports an error, without changing state, when the
current operation is not a P3 transform.

`math-composite-source` configures or queries the global 2000X/3000X `g(t)`
source. Configure requires `--operation`, `--source1`, and `--source2`;
supported operations are `add`, `subtract`, and `multiply`, and both sources
must be supported analog channels. `divide` is not accepted. Query is exclusive
with configure options. The canonical `composite` value is accepted by
`math-transform`, `math-filter`, and supported `math-visualization`
operations; it is not accepted by `math-operator` or as source2. GOFT is not
exposed on the public 4000X path.

`math-filter` configures or queries an instrument-side, single-source Math
filter. `low-pass` and `high-pass` are available on 2000X, 3000X, and 4000X
and optionally accept a positive finite `--cutoff-hz`. The 4000X path also
supports `average` with an optional power-of-two `--average-count` from 2
through 65536, `smooth` with optional odd `--smooth-points` of at least 3,
and `envelope` without an additional parameter. Sources reuse the P4
single-source contract: analog channels on every series, `composite` on
2000X/3000X, and a lower-numbered Math function on 4000X. Query first reads
operation and source, then reads only the parameter applicable to the current
filter. Oversized integers that cannot be safely serialized are rejected as
parameter errors. `math-clear --function N` is available only on 4000X and
clears the selected Math accumulation without querying its operation or
waiting for completion.

`math-visualization` configures or queries instrument-side visualization
waveforms. All registered series support `magnify` and `trend`; 4000X also
supports `maximum`, `minimum`, `peak`, `max-hold`, and `min-hold`. Non-Trend
operations require one source and reuse the single-source rules: analog
channels on all series, `composite` on 2000X/3000X, and a lower-numbered Math
function on 4000X. For 2000X/3000X, Trend requires an analog `--source` and
one canonical `--measurement`; only `vratio` also requires analog
`--source2`. For 4000X, Trend instead requires `--measurement-slot 1..10`,
rejects source options, and assumes that the compatible measurement is already
installed in that slot. Query preserves raw operation, source, and measurement
readbacks and does not issue source queries for 4000X Trend.

`math-clear` applies to 4000X `average`, `max-hold`, and `min-hold`
accumulations. It does not inspect the current operation before issuing the
indexed clear command.

These Math commands do not automatically enable display, change vertical
settings, run autoscale, install or modify measurements, change acquisition
state, probe licenses, calculate host-side waveforms, or export waveform data.
Reference waveform, bus, and digital sources remain unsupported. License
availability remains subject to the live instrument error queue. These Math
paths have hardware-free validation only; live instrument behavior and license
availability have not been validated.

These commands are explicit user actions and are never called by `doctor`,
`smoke`, or `acquisition-check`. Some change front-panel state, such as cursor,
holdoff, autoscale, setup, FFT, Math display/vertical controls, and front-panel
measurement statistics.

Phase 6A `capture-batch` intentionally does not change acquisition mode, wait
for a trigger, poll for acquisition completion, change VISA timeout defaults,
perform return-to-local behavior, start background threads, or run an infinite
recorder loop.

Capture the current oscilloscope screen as an image file:

```powershell
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --output data\screen.png --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --background white --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --format png --output data\screen.png --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --format bmp --output data\screen.bmp --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --format bmp8bit --ink-saver false --palette grayscale --layout landscape --output data\screen-8bit.bmp --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --query-hardcopy --json --log-scpi
```

The `screenshot` command first queries `*IDN?`, sets `:HARDcopy:INKSaver` for
the requested image background, reads the current screen with
`:DISPlay:DATA? PNG, COLor`, restores the previous ink saver setting, and
performs one `:SYSTem:ERRor?` post-check. The default background is black,
matching the oscilloscope screen; `--background white` enables the inverted
white-background hardcopy style. If `--output` is omitted, the CLI writes to
`data/YYYY-MM-DD-HH-mm-ss.png` using the `UTC+8` timezone. The command validates
that the returned bytes have a PNG signature. Because screen images are larger
than normal query responses, screenshot capture temporarily sets the VISA
timeout to 10000 ms for the image transfer and restores the previous timeout
afterward. It does not change acquisition state, trigger settings, display
state, the default timeout, or return-to-local behavior.

On a 4000X profile, `--format png|bmp|bmp8bit` uses
`:HCOPY:SDUMp:DATA? <format>` and validates the returned PNG or BMP signature.
PNG output uses `.png`; BMP and BMP8bit output use `.bmp`. An explicit output
path with the wrong extension is rejected before opening the backend.
`--ink-saver true|false`, `--palette color|grayscale|none`, and
`--layout landscape|portrait` send the corresponding hardcopy settings before
the image query. These explicit settings remain in instrument state. When
`--ink-saver` is omitted, the existing background-based temporary ink saver
behavior is preserved.

`--query-hardcopy` is query-only: it returns canonical area, ink saver,
palette, layout, and format state with raw readbacks, captures no image bytes,
and creates no artifact. It cannot be combined with capture or setting
options. Screenshot Format Pack v1 is not exposed on 2000X or 3000X profiles;
their existing PNG screenshot behavior is unchanged. Printer jobs,
hardcopy area selection, and network printer support are outside this pack.
Instrument-side image saving is a separate Save/Export Pack v1 workflow and
does not change screenshot's PC-side byte retrieval behavior.

## Tests

Normal tests are hardware-free:

```powershell
.\scripts\run-tests.ps1
```

This runs tests from all three areas: `tests/core`, `tests/cli`, and
`tests/webui`.

For a filtered hardware-free run, pass pytest arguments after the script path:

```powershell
.\scripts\run-tests.ps1 tests/cli -q
```

Do not pass `--basetemp`; the wrapper creates an isolated pytest temporary
directory and preserves it only when the run fails.

Real instrument checks are manual. Start with `--dry-run --json`, then
`--simulate --json`, and only use an explicit `--resource <RESOURCE>` or
`SCOPES_TOOL_RESOURCE` after an operator selects the instrument. `--live`
may be included for one-shot compatibility and remains required for live
worker startup. Live checks should begin with USB communication verification
before running state-changing or artifact-writing commands.

## Hardware Validation

The public test baseline is the hardware-free pytest suite. Live hardware
validation is opt-in and should confirm representative workflows for the target
instrument model and transport:

- `identify` and `check-error` for communication and error-queue behavior.
- Read-only measurement and diagnostic commands before configuration changes.
- Channel, acquisition, timebase, trigger, setup, and autoscale commands only
  when changing instrument state is acceptable.
- Waveform, screenshot, smoke, batch capture, and measurement logging commands
  with explicit output paths.

Do not scan or rotate through resources inside an active live workflow. Use one
explicit resource selected by the operator for the whole workflow.
