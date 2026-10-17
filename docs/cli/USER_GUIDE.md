# Scopes Tool CLI User Guide

[繁體中文](USER_GUIDE.zh-TW.md)

This guide covers normal operation of an installed `scopes-tool` command or
the Windows CLI executable. Feature availability depends on the exact model,
backend, transport, and installed instrument options in
[Supported Models](../core/supported-models.md). For each command's arguments,
use `scopes-tool <command> --help`.

## Start and open Help

Open PowerShell in the extracted application directory. Keep the executable
and its shared `_internal` directory together; do not copy only the executable.

```powershell
.\scopes-tool.exe --help
.\scopes-tool.exe user-guide
.\scopes-tool.exe user-guide --lang en
.\scopes-tool.exe user-guide --lang zh-TW
```

For a Python installation, replace `.\scopes-tool.exe` with `scopes-tool`.
`user-guide` defaults to English and opens bundled local HTML in the system
browser. It needs neither Internet access nor a running WebUI, and opens no
instrument session. Missing Help or a browser launch failure reports an error
on stderr and returns exit code `1`. Invalid arguments return `2`.
Help follows the system color scheme when opened from the CLI.

## Choose an execution mode

- `--simulate` executes against the Core simulator without hardware. Commands
  that save artifacts still write simulated files on the computer.
- `--dry-run` validates and plans supported operations without opening an
  instrument session or creating output files. Availability is command-specific.
- A one-shot Live command requires your explicit `--resource` or
  `SCOPES_TOOL_RESOURCE`. `--model` cannot replace detected Live identity.
  In simulation and planning, it selects a registered canonical model ID.

Start without hardware:

```powershell
.\scopes-tool.exe identify --simulate --json
.\scopes-tool.exe capabilities --model tektronix-tbs2074 --json
.\scopes-tool.exe measure --channel 1 --item vpp --simulate --json
.\scopes-tool.exe capture --channel 1 --points 1000 --csv data\waveform.csv --simulate --json
.\scopes-tool.exe capture --channel 1 --points 1000 --dry-run --json
```

Use a new output filename for each saved run. Simulator results do not establish
hardware support. Simulator settings are local to a standalone invocation;
Worker simulation retains successful state within that Worker session.

## Connect to an instrument

System VISA is the default and requires separately installed Keysight IO
Libraries or NI-VISA. Scopes Tool does not bundle that runtime and does not
fall back to PyVISA-py. The included `@py` backend can be selected explicitly
with `--visa-library @py`.

All seven registered models support Product Live through System VISA USB.
TCPIP/LAN through System VISA or `@py` is Product-open only for DSOX4024A,
DSOX4034A, and TBS2074. USB through `@py`, Bluetooth, GPIB, ASRL, and custom
backend selections are not Product-open. An explicit `@ivi` selector counts
as custom; leave the selector unset to use System VISA.

1. Check probe, input rating, DUT, trigger, and acquisition conditions before
   connecting. Queries can consume status or change temporary instrument state
   depending on the operation.
2. Use `list-resources` for backend-reported resource strings. If you explicitly
   want discovery to open listed resources and query `*IDN?`, use
   `list-resources --live-only`.
3. Copy your intended resource exactly. Do not guess a resource from these
   examples. `USB0::...::INSTR` and `TCPIP0::<HOST>::inst0::INSTR` illustrate
   formats only.
4. Set the resource and identify it before a Product command:

```powershell
$env:SCOPES_TOOL_RESOURCE = "<RESOURCE>"
.\scopes-tool.exe identify --resource "$env:SCOPES_TOOL_RESOURCE" --json
.\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vpp --json
```

For an approved LAN connection through PyVISA-py, add `--visa-library @py`
to each applicable command. Discovery depends on drivers and network conditions;
a listed resource or successful Identify does not authorize Product operations.
Unknown or mismatched models fail closed.

## Read and change settings

Use explicit queries before changing settings. For example:

```powershell
.\scopes-tool.exe acquisition --query --simulate --json
.\scopes-tool.exe channel-scale --channel 1 --query --simulate --json
.\scopes-tool.exe timebase-scale --query --simulate --json
.\scopes-tool.exe trigger-edge --query --simulate --json
```

Run, Stop, Single, Force Trigger, Autoscale, setup recall, output controls,
and configuration setters can change front-panel state. Autoscale can change
channels, timebase, trigger, and displayed analysis. Only request these actions
when their effects are acceptable. No reset, preset, autoscale, setup recall,
or return-to-local action runs automatically as ordinary cleanup.

`single` arms acquisition; `single-wait` adds bounded trigger waiting.
`capture` transfers the current waveform unless trigger waiting is explicitly
requested. A trigger timeout does not force a trigger unless the corresponding
force-on-timeout option was explicitly selected. Do not assume an acquisition
will be returned to its original run state by every command.

## Measurements, captures, and files

`measure` and `measure-sweep` read supported measurements. `measure-install`,
`measure-clear`, and `measure-stats` can change front-panel measurement
configuration. Invalid measurement sentinels and instrument errors must be
checked; a numeric-looking raw value is not sufficient evidence of validity.

`capture` saves host CSV and metadata, with optional plots. Tektronix capture
uses BYTE, displayed analog channels, and at most 1000 requested points; `all`
includes hidden channels and can fail rather than enabling them. Tektronix
screenshot formats are model-specific: TBS2074 PNG on black background,
TDS2024B BMP, and TBS1052B JPEG over USBTMC. Consult Supported Models before
selecting a format or optional feature.

`screenshot` and `capture` retrieve files to the computer. `save-image`,
`save-waveform`, and `setup-save` target instrument-side storage, not the PC.
Reference memory, DVM, WGEN, Math, FFT, Serial, Search, and segmented memory
remain limited by the model and any required installed option.

Finite workflows include `measure-log`, `measure-until`, `capture-batch`,
`capture-until`, `capture-monitor`, `triggered-measure-loop`,
`triggered-capture-series`, `segmented-capture`, and `sequence` where supported.
Choose finite counts, timeouts, and output destinations. Some workflows offer
`--no-save`; standalone `capture` always produces artifacts.

Generic Sequence supports `wait`, `single`, `wait-trigger`, `measure`,
`capture`, `screenshot`, and `cleanup`, subject to model capabilities.
Limits are 1–255 steps, 1–255 loops, 65,025 total step executions, and at most
10 combined capture/screenshot steps per loop. It does not accept arbitrary
SCPI. Cancellation is cooperative and blocking VISA I/O may delay completion;
cancellation does not automatically run Safe Cleanup.

## Worker operation

The Worker provides a local queued command service for automation. It is
separate from the browser WebUI. Start a simulator Worker in one terminal:

```powershell
.\scopes-tool.exe worker --simulate --model keysight-dsox4024a --port 8765 --format jsonl
```

In another terminal:

```powershell
.\scopes-tool.exe wait-ready --port 8765 --json
.\scopes-tool.exe send-command --port 8765 --command identify --json
.\scopes-tool.exe status --port 8765 --json
.\scopes-tool.exe stop --port 8765 --json
```

Live Workers require both `--live --resource <RESOURCE>` and the correct
expected canonical `--model`. Mode, model, and resource are fixed at startup.
An accepted command is queued, not completed: observe `job_finished` or the
terminal `last_job`. Output-producing Worker jobs require explicit destinations.
Stop cancels queued work and requests cooperative cancellation of active work;
wait for cleanup and the final summary before treating shutdown as complete.
Do not expose Worker or WebUI ports to untrusted networks.

## Errors and troubleshooting

| Symptom | Action |
| --- | --- |
| System VISA cannot load | Install or repair the external IVI runtime; Scopes Tool does not silently switch backends. |
| No LAN resource appears | Check the instrument LAN configuration and network discovery; use your known explicit resource. |
| Product operation is rejected | Check the exact model/backend/transport matrix and command capability. Identify success alone is insufficient. |
| Capture or screenshot fails | Check displayed channels, point/format limits, storage, destination permissions, and the original diagnostic. |
| A command option is rejected | Run `<command> --help`; support and Dry-run availability differ by command. |
| Help does not open | Read stderr, open the reported HTML manually, or repair the installation if files are missing. |
| Stop takes time | VISA I/O is not forcibly interrupted; allow operation-specific timeouts and session cleanup to finish. |

Use `--json` for commands that support it. Machine stdout contains structured
JSON/JSONL only; `--log-scpi` writes diagnostics to stderr. Check process return
code, `ok`, and command-specific status. One-shot instrument errors generally
return `1`; parser usage errors return `2`, and identity mismatch in one-shot
JSON returns `3`. Worker clients use `2` for validation and `3` for runtime,
connection, and admission failures. Do not infer job success from admission.
`user-guide` is a local text-mode utility and does not accept `--json`.

`doctor` reads status before its snapshot and can consume an error entry;
`smoke` performs measurements, capture, screenshot, and status checks and may
write artifacts. Error-queue reads consume entries. Use diagnostics explicitly
after considering instrument state, and remove private resources and serial
numbers before sharing logs or artifacts.
