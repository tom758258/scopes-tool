# Model implementation notes

Maintainer documentation; not part of bundled Help. See [Supported Models](supported-models.md)
for the user-facing connection, feature, and safety boundaries. These implementation
notes do not expand Product support.

## Canonical Physical Model Identity

Scopes Tool exposes a vendor-neutral product API for the registered Keysight
InfiniiVision and Tektronix models. The canonical physical model registry contains:

| Canonical physical model ID | Manufacturer | Model | Series | Capability profile ID | Driver ID |
| --- | --- | --- | --- | --- | --- |
| `keysight-dsox2004a` | Keysight Technologies | DSOX2004A | 2000X | `keysight-infiniivision-2000x` | `keysight-infiniivision` |
| `keysight-dsox3024a` | Keysight Technologies | DSOX3024A | 3000X | `keysight-infiniivision-3000x` | `keysight-infiniivision` |
| `keysight-dsox4024a` | Keysight Technologies | DSOX4024A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |
| `keysight-dsox4034a` | Keysight Technologies | DSOX4034A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |
| `tektronix-tbs2074` | Tektronix | TBS2074 | TBS2000 | `tektronix-tbs2074` | `tektronix` |
| `tektronix-tds2024b` | Tektronix | TDS2024B | TDS2000B | `tektronix-tds2024b` | `tektronix` |
| `tektronix-tbs1052b` | Tektronix | TBS1052B | TBS1000B | `tektronix-tbs1052b` | `tektronix` |

Canonical registration identifies a physical model. Each registered model
explicitly selects its runtime capability profile.

Every registered physical model is protected by a hardware-free consistency
gate covering vendor identity, capability lookup, and driver selection.
Simulator identity resolution applies to simulator-enabled models.

Core has an explicit driver-selection boundary keyed by each physical model's
registered driver ID. The registered runtime drivers are
`keysight-infiniivision` and `tektronix`. Live selection follows the canonical
physical model resolved from the detected `*IDN?` identity; planning and
expected identities cannot override it. Unknown vendors, physical models,
or missing or unregistered driver IDs fail closed.

### Contributor Validation and Diagnostics

The following `@py` USB connections are restricted to controlled CLI-only
Validation Mode; they are not Product-open: `keysight-dsox2004a`,
`keysight-dsox3024a`, `keysight-dsox4024a`,
`keysight-dsox4034a`, and `tektronix-tbs1052b`.
Validation Mode also permits the three already-open `@py` TCPIP pairs, but
never overrides the detected model, capabilities, or safety requirements.
WebUI and Worker cannot enable this mode. `identify` and `list-resources`
are connection diagnostics, not Product authorization.

Direct Python calls to `Oscilloscope.open()` remain a low-level session
interface rather than a Product-policy entry point. Product CLI and Core-run
paths enforce the matrix before instrument-changing operations.

## Runtime Profiles

Core resolves live `*IDN?` manufacturer and model fields to a canonical
physical model ID, then follows the registered capability profile ID. Dry-run
`--model` values are canonical physical model IDs. Simulation is available for
the registered Keysight and Tektronix models. The simulator's
manufacturer/model IDN fields and capabilities are derived from that same
registry entry.

| Profile ID | Series | Registered models | Analog channels |
| --- | --- | ---: | --- |
| `keysight-infiniivision-2000x` | 2000X | DSOX2004A | 4 |
| `keysight-infiniivision-3000x` | 3000X | DSOX3024A | 4 |
| `keysight-infiniivision-4000x` | 4000X | DSOX4024A, DSOX4034A | 4 |
| `tektronix-tbs2074` | TBS2000 | TBS2074 | 4 |
| `tektronix-tds2024b` | TDS2000B | TDS2024B | 4 |
| `tektronix-tbs1052b` | TBS1000B | TBS1052B | 2 |

A model string that merely resembles a DSO-X or MSO-X series model is not
sufficient for capability selection. Unregistered names such as `DSOX4054A`
and raw model names such as `DSOX4024A` are rejected as `--model` values.

In live execution, capabilities come only from the canonical physical identity
resolved from the actual `*IDN?` manufacturer and model fields. A planning
identity cannot override that result. Live workers treat `--model` as an
expected canonical physical model ID and fail before command-specific SCPI
when it does not match the detected identity.

## Capability implementation notes

See [Adding a model](adding-a-model.md) for the Core extension boundary.
Tektronix dry-run and the stateful simulator use the Tektronix command dialect
for admitted operations, but simulation does not establish live hardware
support. Signal presets and system-error queue injection remain unavailable for
these profiles.

### Aggregate projections

Aggregates skip unsupported atomic queries and never mutate source/display,
measurement slots, trigger mode, or cursor units merely to discover support.

| Aggregate | TBS2074 projection | TDS2024B projection | TBS1052B projection |
| --- | --- | --- | --- |
| `channel-summary` | display, scale, offset, coupling, probe ratio, bandwidth limit, invert, label, probe skew, and V/A units on CH1-CH4. Range, impedance, and vernier unavailable. | display, scale, offset, coupling, probe ratio, bandwidth limit, invert, units. Label, probe skew, range, impedance and vernier unavailable. | Same as TDS2024B, CH1/CH2 only. |
| `live-data-snapshot` / `query_instrument_summary` | Channel display/scale/offset/units on CH1-CH4, timebase scale/position under the same Delay Mode ON prerequisite above, trigger type/sweep, edge source/slope, channel-qualified level and established source units. | Channel display/scale/offset/units, timebase scale/position, trigger type/sweep/source/slope. Current analog edge-source MAIN:LEVEL is valid snapshot data even though standalone named-channel level is unsupported. | Same as TDS2024B, bounded to two channels. |
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
reuses the admitted projections; reference labels remain nullable as described
above. Required-state results such as hardcopy state or DVM/WGEN/Demo queries do
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
