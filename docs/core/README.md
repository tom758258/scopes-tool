# Scopes Tool Core

[繁體中文](README.zh-TW.md)

Core runtime package for vendor-neutral oscilloscope control through
PyVISA-compatible backends.

Distribution: `scopes-tool`

Import package: `scopes_tool_core`

## Purpose And Ownership

Core owns the shared runtime and hardware-facing behavior used by the Scopes
Tool adapters. Its responsibilities include:

- Opening VISA resources safely and resolving the selected run mode.
- Detecting `*IDN?` identity and resolving the canonical physical model.
- Applying registry-linked capability profiles and driver behavior.
- Validating requests before unsafe or state-changing operations where
  applicable.
- Generating and executing model-appropriate instrument operations, including
  SCPI-facing queries, configuration, acquisition, and parsing.
- Providing simulator, fake-backend, and no-hardware planning paths.
- Running finite synchronous Core workflows with cooperative cancellation,
  progress reporting, and operation-specific samples.

CLI, Worker, and WebUI are adapters over Core. They own command parsing,
presentation, serialization, terminal/browser behavior, HTTP control, and
queue or job lifecycle. They must use Core identity, capabilities, validation,
drivers, and instrument behavior rather than implementing parallel versions.
Core does not import adapter packages.

## Identity, Capabilities, And Runtime Boundary

For live operation, the detected `*IDN?` response and the resolved canonical
physical model are the runtime authority. For simulator and dry‑run planning,
a planning physical model selects the registered capability profile used for
hardware-free planning and validation. In live mode an expected physical model
serves only as a safety guard and never replaces the identity or capability
profile detected through `*IDN?`. Unknown, unregistered, or mismatched live
vendors, models, profiles, or drivers fail closed.

Capability profiles describe the supported runtime surface for a model. They
do not prove that an optional instrument option or license is installed; live
instrument errors remain authoritative. Simulator and dry-run planning support
hardware-free development and validation, but do not constitute live hardware
validation.

Core owns hardware-facing behavior and safety validation. Adapters do not
define the Core validation contract. Core workflows support cooperative
cancellation, but a blocking VISA or device read is not forcibly interrupted.
Core also does not own Worker queue admission, persisted job lifecycle, HTTP
control, or WebUI presentation.

VISA library selectors are normalized to these Core identities:

- unset or blank selector → `system_visa`
- `@py` → `pyvisa_py`
- `@bt` → `pyvisa_bt`
- any other explicit selector → `custom_visa`

System VISA (unset, blank, or `system_visa`) explicitly opens `@ivi` and
checks the loaded library against PyVISA's `IVIVisaLibrary` type. A missing,
failed, or non-IVI backend fails closed; a created manager is closed on
verification failure. Installing pyvisa-py or setting `PYVISA_LIBRARY=@py`
does not change this selection. Other explicit selectors pass through unchanged.

Ordinary installations and Windows packages include `pyvisa-py` and its LAN
discovery dependencies (see [installation prerequisites](../../README.md#install)).
Other selected backends may require separate installation. Backend availability
does not grant Product Live support. Core checks the requested transport and
backend before opening VISA and the exact physical model resolved from `*IDN?`
before a Product command. System VISA Product support is limited to approved
model/USB or model/TCPIP pairs; `@py` Product support is limited to DSOX4024A,
DSOX4034A, and TBS2074 over TCPIP. The `@py` USB pairs are not Product-open.
`@bt` and explicitly selected custom VISA backends (including an explicit
`@ivi` selector) are not Product-open; use the default System VISA selector
to request the verified IVI backend.

Contributor validation is an explicit CLI-only option. Core admits exact detected
model, transport, and backend combinations that are either formally supported or
registered for validation only. It is not restricted to `@py`: System VISA uses
its existing supported connections, with no additional validation-only pairs.
`@bt` and custom backends have no registered validation connections. A backend
and transport without a registered combination are rejected before VISA opens;
the actual `*IDN?` model is checked again before instrument operations.
Validation preserves model capabilities, installed-option checks, instrument
status checks, and safety limits. WebUI and Worker cannot select this mode.
Identification and resource discovery remain diagnostics; dry-run and simulation
do not open a live VISA session.

New validation-only features must have an implementation and safety checks,
an exact Core registration for model, transport, backend, and feature, and a
Core admission check at the operation entry. Normal operation must
reject those features; metadata alone must not authorize execution.
Validation results do not expand formal support. Extending formal support
requires maintainer review of hardware evidence, explicit operator approval,
updates to Core support declarations and public documentation, and relevant
policy tests. Keep hardware evidence in private or separately shared review
artifacts.
Direct Python use of `Oscilloscope.open()` is a low-level session interface,
not a Product support entry point. See [Supported Models](supported-models.md)
for the exact connections and model-specific feature limits.

## Workflow Manifest Persistence

Measurement Log, Triggered Measurement Loop, Periodic Capture, Triggered
Capture Series, Segmented Capture, Capture Until, and Generic Sequence append
each committed history record to an internal JSONL journal. While running,
`manifest.json` contains compact progress and state rather than accumulated
history or artifact lists. CSV rows and capture artifacts are written first;
history and the progress snapshot must succeed before completion counts are
advanced and sample/progress callbacks are notified.

On completion, cooperative cancellation, or a handled error/interruption,
the committed records are assembled into the full final `manifest.json`,
preserving its existing schema, fields, history order, and artifact paths.
The final manifest is published by atomic replacement before the journal is
removed. If final publication fails, the operation cannot report success;
already written data and the journal are retained where possible. Automatic
recovery after process termination or power loss is outside this contract.
Supported no-save workflows create no journal or manifest.

## Feature Areas

Core groups the instrument surface into these feature families:

- Connection, identity, capabilities, status, and safe resource/runtime
  handling.
- Channels, display, annotations, timebase, cursors, acquisition, and
  read-only instrument state summaries.
- Measurements, capability-gated advanced measurement statistics settings and
  results, waveform capture, screenshots, reference waveforms, and
  instrument-side or host-side save/export helpers.
- Trigger families, common trigger settings, one-shot trigger control, and
  finite trigger wait/capture helpers.
- Serial bus configuration, serial triggering and search, lister state, and
  raw lister data export.
- Instrument-side Math and FFT configuration, including supported transforms,
  operators, filters, visualizations, and series-specific capability paths.
- Optional or instrument-side features such as DVM, WGEN, Demo output, and
  segmented memory, subject to profile and instrument support.
- Finite Core workflows and simulator support for hardware-free execution,
  planning, callbacks, and deterministic error-path testing.

Feature-family descriptions here are an overview, not a command reference or
an exhaustive API, SCPI, model, firmware, or option-support matrix.

## Workflow Foundation

Core provides finite synchronous workflows built from existing instrument
operations. Workflows can accept cooperative stop requests, synchronous
progress reporters, and operation-specific sample callbacks; they do not
introduce an async runtime, scheduler, or event bus.

The current workflow surface includes `measure-log`, Periodic Capture through
`capture-batch`, Capture Until, Capture Monitor, Triggered Measurement Loop,
Triggered Capture Series, Measure Until Condition, Generic Sequence, and
`segmented-capture` where supported by the active profile. Workflow-owned
waveforms may be analyzed or retained in bounded RAM without changing the
artifact-producing behavior of standalone `capture`. Detailed contracts for
the workflow families documented by Core Integration — including request
fields, defaults, terminal behavior, artifact schemas, and Generic Sequence
rules where applicable — are maintained in
[Core Integration](integration.md).

## Public Package Surface

Downstream Python consumers should prefer imports from the
`scopes_tool_core` package root. The package-root `__all__` defines the public
import boundary. The complete current public import list and integration
examples are maintained in [Core Integration](integration.md).

Implementation-only submodules and helpers are not public API merely because
they are importable; README cleanup does not expand that boundary.

## Model Profiles and Tektronix Implementation Boundaries

The user-facing model and connection support matrix is in
[Supported Models](supported-models.md). Core uses the registered profiles
below; the registered driver IDs are `keysight-infiniivision` for Keysight and
`tektronix` for Tektronix. Profile selection uses the actual `*IDN?`
identity for Live; a requested planning or expected model never overrides it.

| Profile ID | Series | Registered models | Analog channels |
| --- | --- | ---: | --- |
| `keysight-infiniivision-2000x` | 2000X | DSOX2004A | 4 |
| `keysight-infiniivision-3000x` | 3000X | DSOX3024A | 4 |
| `keysight-infiniivision-4000x` | 4000X | DSOX4024A, DSOX4034A | 4 |
| `tektronix-tbs2074` | TBS2000 | TBS2074 | 4 |
| `tektronix-tds2024b` | TDS2000B | TDS2024B | 4 |
| `tektronix-tbs1052b` | TBS1000B | TBS1052B | 2 |

Validation-only `@py` USB targets and contributor CLI validation procedures
are documented in the [CLI README](../cli/README.md); they do not expand
Product Live support.

### Aggregate projections

Aggregates skip unsupported atomic queries and never mutate source/display,
measurement slots, trigger mode, or cursor units merely to discover support.

| Aggregate | TBS2074 projection | TDS2024B projection | TBS1052B projection |
| --- | --- | --- | --- |
| `channel-summary` | display, scale, offset, coupling, probe ratio, bandwidth limit, invert, label, probe skew, and V/A units on CH1-CH4. Range, impedance, and vernier unavailable. | display, scale, offset, coupling, probe ratio, bandwidth limit, invert, units. Label, probe skew, range, impedance and vernier unavailable. | Same as TDS2024B, CH1/CH2 only. |
| `live-data-snapshot` / `query_instrument_summary` | Channel display/scale/offset/units on CH1-CH4, timebase scale/position under the TBS2074 Delay Mode ON prerequisite in [Supported Models](supported-models.md#acquisition-timebase-and-channels), trigger type/sweep, edge source/slope, channel-qualified level and established source units. | Channel display/scale/offset/units, timebase scale/position, trigger type/sweep/source/slope. Current analog edge-source MAIN:LEVEL is valid snapshot data even though standalone named-channel level is unsupported. | Same as TDS2024B, bounded to two channels. |
| `system-information-snapshot` / `query_acquisition_readouts` | Identity, sample rate, acquisition points and record length available: SUPPORTED. | Identity, acquisition points and record length available; sample rate unavailable: PARTIAL AGGREGATE. | Same as TDS2024B: PARTIAL AGGREGATE. |
| `cursor-query` | Native X positions/delta only for time readback with a time-based source; Y positions/delta only for SCREEN readback when physical volts are established. Ambiguous axes remain null. Percent/Hz/dB/divisions/amps are not seconds/volts. Inactive/unestablished axes and dydx unavailable. | Active VBARS seconds positions/delta or active HBARS volts positions/delta. Other axis/dydx and FFT/amp/unknown-unit fields unavailable. | Same as TDS2024B. |

`live-data-snapshot` is PARTIAL AGGREGATE on all three. Each registered profile
declares fixed realtime acquisition architecture; absence of segmented-memory
support alone would not establish that. Acquisition processing type remains a
separate `ACQuire:MODe` readback. Unknown fields fall back independently; line
or external source-channel/units/analog-level fields remain unavailable rather
than receiving artificial values.

Cursor OFF projects null positions/deltas/dydx. TBS2074 selects its cursor
function through `CURSor:FUNCtion` using the five first-generation values:
`OFF`, `SCREEN`, `WAVEform`, `VBArs`, and `HBArs`. The operator may request a
function explicitly; without an explicit request the requested axes keep the
previous mapping, where X only uses VBArs, Y only uses HBArs, and X plus Y uses
SCREEN. `OFF` and `WAVEform` only switch the function and require no source
channel and no positions; `WAVEform` has no position setter in this surface.
`VBArs` accepts only X positions and `HBArs` only Y positions; every other
combination is rejected before any instrument write. `CURSor:FUNCtion?` can
return `TIME` after `WAVEform` or `VBArs`, and `SCREEN` after `SCREEN` or
`HBArs`. Query reports the native value and leaves axes that cannot be
established from it null; configure results retain the requested function.
`AMPLitude` remains unsupported.

TBS2074 setters use the selected/displayed waveform semantics; source selection
can enable display and reset acquisition and is intentionally not restored
because that would retarget the cursors. Physical-volts Y validation on CH3/CH4
temporarily uses the waveform transfer source only to verify units and restores
that transfer source in `finally`. B1 setters are X-only time or Y-only
physical-volts; mixed-axis writes and auto-vertical remain unsupported. All
returned positions are actual readbacks rather than echoed input. The
source/unit rules follow the documented definitions in TBS2000 pp. 64, 67-73, 77, 161,
191-201 and B1 pp. 2-61-2-68.

`measure-results` is intentionally excluded from nullable projections.
`MEASUrement?` and per-slot aggregate queries describe settings, not the one
native results response required by the public result/raw contract. Doctor
reuses the admitted projections; reference labels may be unavailable under
the model support matrix. Required-state results such as hardcopy state or DVM/WGEN/Demo queries do
not become partial aggregates merely because a surrounding result allows nulls.

### Tek post-command status boundary

Ordinary supported Tek operations that use the transparent post-command status
seam perform one internal `*ESR?` after the business response completes. Only
SESR bits 5-2 (CME, EXE, DDE, QYE) are operation errors. PON, URQ, RQC, and OPC
alone do not indicate operation failure.

Ordinary non-measurement post-checks do not issue `EVENT?`, `EVMsg?`, `ALLEv?`,
or `EVQty?`, do not emulate a normalized system-error queue, and do not populate top-level
`system_error`. A nonzero error mask follows the existing structured error path
and retains raw SESR. Because `*ESR?` is destructive, `system-standard-event`
gets exactly its requested read; `system-clear-status`, `system-status-byte`,
and `system-opc` do not receive an extra hidden SESR read. Post-checking is not
a completion wait and never makes an unsupported operation supported. The
`capture` primitive uses this post-command seam; `measure` and composed
workflows use the native workflow checkpoint below without a second primitive
SESR read.

### Native workflow status

Workflow checkpoints first read `DESE?` and require error bits 2-5 to be
enabled. They then consume one `*ESR?` followed by `ALLEv?` before any later
SESR read. They do not modify DESE, ESE, or SRE. This ordering follows the
documented destructive SESR/event cohort: a later SESR read can discard unread
events from the preceding cohort. See TBS2000 pp. 206-209 and B1 chapter 3.

Workflow results keep `system_error: null` and expose `post_command_status` with
source `tektronix-sesr`, raw SESR/event responses, decoded events/categories,
completeness, and destructive-read flags. Samples and sequence/acquisition steps
use the same representation. Command, execution, device, and query error bits
fail the checkpoint; informational events alone do not. A warning that sets an
error bit still fails outside the measurement exception below. Malformed
responses, queue overflow (350), and incomplete status fail closed and prevent
further workflow steps. No retry may consume a
second SESR to hide an unread or malformed cohort.

Immediate measurements permit events 540–549 only when the value is valid and
finite, the SESR has no other error bits besides Execution bit 4, and the event
cohort is complete and contains only these measurement warnings with messages.
The value, raw SESR, event codes and warning messages remain in the existing
measurement status fields. A strict checkpoint after TYPE/SOURCE and units
configuration separates earlier work from the value query; restoration receives
a separate strict checkpoint. This rule applies to measure, sweep, log, until,
triggered measurement loops, sequence measurement steps and Smoke measurements.
Invalid values, other events, mixed errors and communication failures still fail.
Tektronix Smoke also fails on invalid measurement sentinels; the Keysight Smoke
policy of reporting invalid sentinels as warnings is unchanged.
Capture, acquisition, trigger and cleanup checkpoints retain their error rules.

Doctor stops on preexisting errors. Other workflows report stale events before
proceeding according to the existing preflight policy; an incomplete preflight
always fails. Cleanup explicitly clears status as a requested action and then
verifies completion and native status. Public `check-error`,
`query_system_error`, `drain_system_errors`, and `system-operation-status`
remain unsupported.

`wait_for_current_trigger_completion` observes the current acquisition and
never arms it. `single_wait` arms once and delegates to that wait. Triggered
workflows compose one `single` with one current-acquisition wait; sequence
`wait-trigger` likewise does not silently issue another `single`.

### Manual ambiguities and excluded interpretations

These references are retained because the ambiguity could otherwise expand
support incorrectly:

- TDS2000B/TBS1000B manual p. 2-98 includes BMP in TBS1000B
  `HARDCopy:FORMat` syntax and applies it to USB-file/USBTMC output, while
  p. 2-99 describes BMP as non-TBS1000B. TBS1052B BMP screenshot therefore
  remains unsupported pending authoritative resolution. Separately,
  JPEG is explicitly documented for TBS1000B on pp. 2-98 to 2-99,
  with `HARDCopy START` output and USB Device port routing on pp. 2-96 to
  2-102. This supports the separate JPEG path without admitting BMP.
  `HARDCopy:FORMat?` is not a readback of `SAVE:IMAGE:FILEFORMAT`;
  legacy instrument-side storage remains outside the public operation set.
- TBS2000 FFT documentation does not establish the full-span conversion or
  frequency reference needed by the public atomic result (pp. 93-97).
- TBS2000 cursor documentation refers to a source without a corresponding
  command entry. The selected-waveform adapter therefore uses documented
  `SELect:CONTROl` semantics, including selection/display/acquisition effects
  (pp. 67-73, 161).
- Some TBS2000 trigger examples contradict the command syntax. Only
  independently documented trigger controls and the explicit runt subset are
  admitted (pp. 172, 174, 177-180); pulse-width exposes only its selected
  less-than/greater-than threshold, not retained independent thresholds or
  range.
- TBS2000 measurement aggregate examples show statistics/indicator fields
  without defined matching controls. They do not establish the public
  measurement-statistics or marker-visibility features.

No ambiguity in this section authorizes new public operations, enums, waveform
conversions, filesystem helpers, or support decisions.

## Validation

From the repository root, the focused Core documentation and ownership check
can be run with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_core_docs_ownership.py -q -p no:cacheprovider --basetemp .tmp_tests\core-docs
```

## Docs

- [Core Integration](integration.md)
- [Supported Models](supported-models.md)
- [CLI documentation](../cli/README.md)
- [Shared CLI, Worker, and orchestrator contracts](../contracts/)
