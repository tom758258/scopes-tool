# Supported Models

This document records public model support decisions for the Core runtime.
Command-level behavior remains documented in `../cli/README.md` and
`../contracts/`.

Capability profiles describe the runtime-supported and guarded feature surface.
They do not detect instrument options or licenses, and live instrument errors
remain authoritative for unavailable hardware or options.

## Canonical Physical Model Identity

Scopes Tool exposes a vendor-neutral product API for the registered Keysight
InfiniiVision and Tektronix models. The canonical physical model registry contains:

| Canonical physical model ID | Manufacturer | Model | Series | Capability profile ID | Driver ID |
| --- | --- | --- | --- | --- | --- |
| `keysight-dsox2004a` | Keysight Technologies | DSOX2004A | 2000X | `keysight-infiniivision-2000x` | `keysight-infiniivision` |
| `keysight-dsox3024a` | Keysight Technologies | DSOX3024A | 3000X | `keysight-infiniivision-3000x` | `keysight-infiniivision` |
| `keysight-dsox4024a` | Keysight Technologies | DSOX4024A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |
| `keysight-dsox4034a` | Keysight Technologies | DSOX4034A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |
| `tektronix-tbs2074b` | Tektronix | TBS2074B | TBS2000B | `tektronix-tbs2074b` | `tektronix` |
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

## VISA Backend Boundary

Backend identity is not a model capability or a support declaration. Core
classifies an unset or blank selector as `system_visa`, `@py` as `pyvisa_py`,
`@bt` as `pyvisa_bt`, and any other non-empty selector as `custom_visa`.
Scopes Tool does not currently define an exact backend support policy, and no
existing model capability becomes Bluetooth-supported because `@bt` is
recognized. There is no current Scopes live Bluetooth support scope.

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
| `tektronix-tbs2074b` | TBS2000B | TBS2074B | 4 |
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

## Capability Summary

The Tektronix profiles admit only the existing operation subsets documented
in the Tektronix model-support section below. All three support BYTE waveform
capture, model-specific single-source measurements, voltage channel offsets,
source-qualified instrument waveform saves, native-status workflows,
capability-driven acquisition checks and cleanup, and a model-specific sequence
subset. TBS2074B supports native PNG screenshots with black background and the
Smoke workflow; TDS2024B supports explicit BMP screenshots over USBTMC;
TBS1052B screenshots remain unsupported. Normalized `check-error` is
unsupported on all three. Tek workflow status remains separate from the
normalized Keysight system-error queue.

See [Adding a model](adding-a-model.md) for the Core extension boundary.
Tektronix dry-run and the stateful simulator use the Tektronix command dialect
for admitted operations, but simulation does not establish live hardware
support. Signal presets and system-error queue injection remain unavailable for
these profiles.

## Tektronix Model Support

The registered Tektronix models use the existing public Scopes Tool contracts; this
section records the model-specific hardware boundary. A driver method, simulator
response, capability flag, or WebUI visibility setting does not establish live
hardware support.

Support terms are normative:

- **SUPPORTED** means the operation and the explicitly listed existing option
  subset satisfy the public contract, including required readback and completion.
  Unlisted options remain unsupported; a subset never creates a Tektronix-only
  public enum.
- **PARTIAL AGGREGATE** applies only to an existing read-only projection whose
  contract already permits unavailable fields. Unsupported atomic queries are
  skipped rather than attempted and caught. Nullable fields do not authorize
  partial setters, artifacts, measurements, or workflows, and raw/provenance
  fields still describe operations that actually ran.
- **UNSUPPORTED** means a required semantic or result cannot be supplied. A
  mandatory readback is never replaced by an echoed setter argument, invented
  value, or empty string presented as hardware state.

Public validation and documented hardware limits both apply. Supported actions
can still report instrument errors, unavailable waveforms, missing storage, or
timeouts. The manual authorities are the Tektronix
[TBS2000B Series Programmer Manual, 077-1149-04](https://download.tek.com/manual/TBS2000B-Programmer-Manual-EN-US-077114904.pdf)
for TBS2074B and
[TBS1000/B/EDU, TDS2000/B/C and related Series Programmer Manual, 077-0444-03 Rev B](https://download.tek.com/manual/TBS1000-B-EDU-TDS2000-B-C-TDS1000-B-C-EDU-TDS200-TPS2000-B-Programmer-077044403_RevB.pdf)
for TDS2024B and TBS1052B. Conditions documented only for older TDS200 models
or TDS2MM modules do not apply to these registered models.

Raw fields retain the actual instrument response from the operation required by
the contract, and readback must describe the setting being queried rather than
a related setting. Unrecognized or out-of-subset instrument state is not
normalized into a supported value. An admitted option subset applies only to
existing public surfaces that already accept and execute it. Artifact encoding,
filename, and adapter behavior remain part of the existing public contract.

Unless marked aggregate, workflow, or host, the rows below cover the atomic
action and its existing query/set forms. Presentation-only editors inherit their
constituent operations: `acquisition-control`, `channel-scale-range`,
`external-trigger-range-level`, `front-panel-measurements`,
`reference-waveform`, `reference-labels`, `system-information`,
`diagnostics`, `serial-decode`, `serial-trigger`, and `serial-lister`.
An editor may show unavailable fields without enabling unsupported actions;
adapter aliases do not create additional hardware features.

### Acquisition, timebase, and channels

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Boundary |
| --- | --- | --- | --- | --- |
| `identify` | SUPPORTED | SUPPORTED | SUPPORTED | `*IDN?`; detected identity and registered-model fail-closed rules remain authoritative. |
| `run`, `stop-acquisition` | SUPPORTED | SUPPORTED | SUPPORTED | Continuous run uses `STOPAfter RUNSTOP` plus `STATE RUN`; stop uses `STATE STOP`. |
| `single` | SUPPORTED | SUPPORTED | SUPPORTED | `STOPAfter SEQuence`, then `STATE RUN`; arms one acquisition but does not promise trigger completion. |
| `single-wait` | SUPPORTED | SUPPORTED | SUPPORTED | One single acquisition plus finite `BUSY?` polling; optional timeout force-trigger is followed by another bounded poll. Cancellation and timeout remain bounded. |
| `force-trigger` | SUPPORTED | SUPPORTED | SUPPORTED | `TRIGger FORCe`; requires an armed instrument and is not itself a completion wait. |
| `acquisition` | SUPPORTED | SUPPORTED | SUPPORTED | normal/sample, peak, average; TBS2074B also high-resolution. Average counts: powers of two 2-512 on TBS2074B, and 4/16/64/128 on TDS2024B/TBS1052B. |
| `autoscale` | SUPPORTED | SUPPORTED | SUPPORTED | Bare `AUTOSet` only; optional channel-list, acquisition-mode, or channel-selection policy requests remain unsupported. |
| `sample-rate` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074B has current/maximum sample-rate readbacks. Reciprocal waveform X increment on the B1 models is not a hardware sample-rate readback. |
| `acquisition-points`, `record-length` | SUPPORTED | SUPPORTED | SUPPORTED | Query-only acquisition size. TDS2024B/TBS1052B are fixed at 2500 points; no new record-length setter. |
| `timebase-scale` | SUPPORTED | SUPPORTED | SUPPORTED | Seconds/division read/write. |
| `timebase-position` | SUPPORTED | SUPPORTED | SUPPORTED | TDS2024B/TBS1052B use native seconds. TBS2074B Delay Mode ON reads/writes delay time directly; with Delay Mode OFF, integer horizontal percent is converted with `duration = record_length / sample_rate` and `seconds = (50 - percent) / 100 * duration`. Setters round the inverse percentage and queries return effective readback seconds. Neither path changes Delay Mode. TBS2000B pp. 113-118. |
| `timebase-reference` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No independent left/center/right reference setting/readback; horizontal percentage changes position instead. |
| `channel-display`, `channel-scale`, `channel-coupling` | SUPPORTED | SUPPORTED | SUPPORTED | Analog channels; public coupling subset remains AC/DC. Tek display changes can restart acquisition. |
| `channel-offset` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074B uses native volts. TDS2024B/TBS1052B convert public center voltage as `-POSITION * SCALE`; setting volts writes `POSITION = -volts / SCALE`. Later scale changes need not preserve volts. B1 p. 2-55. |
| `channel-probe` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074B derives attenuation from probe gain with probe-dependent limits. B1 ratios are 1, 10, 20, 50, 100, 500, 1000. |
| `channel-bandwidth-limit`, `channel-invert` | SUPPORTED | SUPPORTED | SUPPORTED | Bandwidth means the documented 20 MHz limiter, not a numeric bandwidth setting; invert is native on all three. |
| `channel-label`, `channel-probe-skew` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074B label limit is 30 characters; probe skew uses the public -100 to +100 ns subset. B1 models lack writable labels/deskew. |
| `channel-units` | SUPPORTED | SUPPORTED | SUPPORTED | Public volts/amps map to V/A. TBS2074B units are admitted only on CH1/CH2; CH3/CH4 remain excluded. B1 units apply to all model analog channels. |
| `channel-range` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Volts/division and trace position do not establish the public full-scale acquisition-range semantic. |
| `channel-impedance`, `channel-vernier` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Fixed impedance is not a selectable setting/readback, and no fine-scale enable contract is available. |
| `channel-summary` | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Projection is defined below; unavailable fields do not authorize unsupported atomic queries. |

### Display, cursors, Math, and measurements

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Boundary |
| --- | --- | --- | --- | --- |
| `display-persistence` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074B supports minimum/off, infinite, and finite 0.1-60 s. B1 models support off, infinite, and exactly 1/2/5 s. No AUTO mode is added. |
| `display-vectors` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 models can enable/query vectors; the existing setter does not add dots/OFF. |
| `display-label`, `display-clear`, `display-intensity` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No matching global-label visibility, waveform-display clear, or waveform-intensity contract. |
| `cursor-off` (`cursor` off action) | SUPPORTED | SUPPORTED | SUPPORTED | Uses cursor function OFF; does not disable the educator-controlled cursor feature. |
| `cursor-query` (`cursor` query action) | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Only axes with established active mode and physical seconds/volts are projected; details below. |
| `cursor-set` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074B uses selected-waveform TIME/AMPLitude/SCREEN semantics and may reset acquisition when selection/display changes. B1 models use independent source selection with X-only VBARS or Y-only HBARS. X auto-timebase is supported; auto-vertical is unsupported on all three. |
| `math-display`, `math-operator`, `query_math_operation` | SUPPORTED | SUPPORTED | SUPPORTED | Function 1 only. Exact admitted expressions are listed below; no divide or extra functions. |
| `math-vertical` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek scale plus position does not supply the required scale/full-range/voltage-offset contract. |
| `fft` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Required frequency center/full-span semantics are not established; assumed display divisions must not be used to synthesize Hz values. |
| `math-transform`, `math-filter`, `math-visualization`, `math-composite-source`, `math-clear` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No equivalent public transform/filter/cascade/visualization or accumulator-clear semantics. TBS1052B Trend Plot is not Math trend. |
| `measure`, `measure-sweep` | SUPPORTED | SUPPORTED | SUPPORTED | Single-source immediate items use the model-specific subset below. Immediate TYPE/SOURCE state is restored even after query failure; pair/parameterized items remain unsupported. |
| `measure-install` | SUPPORTED | SUPPORTED | SUPPORTED | Periodic measurement slots: 6 on TBS2074B, 5 on TDS2024B, 6 on TBS1052B. Reuse a matching or unused slot; a full bank must not silently replace another measurement. |
| `measure-clear` | SUPPORTED | SUPPORTED | SUPPORTED | Clears installed periodic measurements using the native per-slot mechanism; not snapshot/acquisition-data clear. |
| `measure-results` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Existing contract requires one native results response and its raw provenance. Multiple TYPE/SOURCE/UNITS/VALUE queries must not be concatenated into a synthetic results dump. |
| `measure-source`, `measure-menu`, `measure-show`, `measure-window`, `measurement-statistics`, `measure-stats` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Immediate/per-slot source is not a global default; Tek gating is not MAIN/ZOOM/AUTO/GATE; aggregate examples do not establish public statistics or marker-visibility controls. |
| `annotation`, `annotation-on`, `annotation-off`, `annotation-set`, `annotation-clear`, `annotation-query` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Channel labels do not provide annotation-slot text/color/background/position/enable semantics. |

For `math-operator`, TBS2074B admits exactly CH1+CH2, CH1-CH2, CH2-CH1,
and CH1*CH2. TDS2024B additionally admits the documented CH3/CH4 pair forms
CH3+CH4, CH3-CH4, CH4-CH3, and CH3*CH4. TBS1052B is limited to CH1/CH2.
Readback is parsed into existing operation/source fields while preserving source
order. Arbitrary cross-pairs, self-pairs, cascade sources, divide, and unlisted
reverse orders are unsupported. The TBS2000B manual mentions CH3/CH4 but does
not list their expressions, so none are inferred.

The admitted single-source measurement items are:

| Existing item group | TBS2074B | TDS2024B | TBS1052B | Native mapping / restriction |
| --- | --- | --- | --- | --- |
| vpp, frequency, period, minimum, maximum, rise_time, fall_time, positive_width, negative_width | SUPPORTED | SUPPORTED | SUPPORTED | PK2Pk, FREQuency, PERIod, MINImum, MAXimum, RISe, FALL, PWIdth, NWIdth. |
| vavg | SUPPORTED | SUPPORTED | SUPPORTED | MEAN; whole-waveform arithmetic mean, not CMEAN. |
| vrms | SUPPORTED | UNSUPPORTED | SUPPORTED | RMS; TDS2024B cycle RMS/CURSORRMS do not satisfy displayed-waveform RMS. |
| amplitude, top, base, overshoot, preshoot | SUPPORTED | UNSUPPORTED | SUPPORTED | AMPlitude, HIGH, LOW, POVERshoot, NOVERshoot. |
| duty_cycle, negative_duty_cycle | SUPPORTED | UNSUPPORTED | SUPPORTED | PDUty/NDUty; the applicability text excludes TDS2000B despite broader syntax. |
| area, positive_edges, negative_edges, positive_pulses, negative_pulses | SUPPORTED | UNSUPPORTED | SUPPORTED | AREA, edge-count, and pulse-count periodic types; no new gate control. |
| ac_rms, x_at_max, x_at_min | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No matching AC-only RMS or time-at-extremum periodic type. |

Parameterized y_at_x/time_at_edge/time_at_value and phase/delay pair items remain
unsupported by the existing single-channel installation operation. Periodic
installation does not enable native result dumps or a global measurement source.

### Trigger operations

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Boundary |
| --- | --- | --- | --- | --- |
| `trigger-mode` | SUPPORTED | SUPPORTED | SUPPORTED | This is trigger type, not sweep. TBS2074B admits edge/glitch/runt; B1 models admit edge/glitch/tv. Type selection alone does not imply a full configuration operation. |
| `trigger-sweep` | SUPPORTED | SUPPORTED | SUPPORTED | auto/normal only. |
| `trigger-edge-source` | SUPPORTED | SUPPORTED | SUPPORTED | Analog channels and line on all three; B1 models also admit external. TBS2074B AUX is not assumed equivalent to public external. |
| `trigger-edge-slope` | SUPPORTED | SUPPORTED | SUPPORTED | positive/negative only; no either/alternate. |
| `trigger-edge-coupling` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074B: dc/lf-reject. B1 models: ac/dc/lf-reject. HF/noise rejection does not create extra public coupling values. |
| `trigger-edge` | SUPPORTED | SUPPORTED | SUPPORTED | Combined analog source/level/slope only, positive/negative. B1 combined configuration may select the source before MAIN:LEVEL. Line/external are excluded from this combined contract. |
| `trigger-edge-level` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074B has channel-qualified level access. B1 MAIN:LEVEL is selected-source state and cannot satisfy the standalone named-channel operation without source mutation. |
| `trigger-holdoff` | SUPPORTED | SUPPORTED | SUPPORTED | Public intersection is 40 ns-8 s on TBS2074B and 500 ns-10 s on B1 models. |
| `trigger-pulse-width` | SUPPORTED | SUPPORTED | SUPPORTED | Analog positive/negative, less-than/greater-than only. Only the active threshold is supplied; inactive/range thresholds are null and min+max/range requests are rejected before writes. |
| `trigger-runt` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074B CH1-CH2 only, positive/negative, occurs/less-than/greater-than. No either or undocumented CH3/CH4. |
| `trigger-tv` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 models: NTSC/PAL, analog source, positive/negative polarity, field1/field2/all-fields/all-lines. Line-field variants and SECAM/other standards remain unsupported. |
| `trigger-noise-reject`, `trigger-hf-reject`, `trigger-edge-reject` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | A single mutually exclusive Tek coupling selector cannot supply independent rejection controls/readbacks. |
| `external-trigger-range`, `external-trigger-probe`, `external-trigger-units`, `trigger-edge-external-level`, `external-trigger-settings` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Source selection or selected-source level does not establish independent external range/probe/units/level semantics, and there is no useful aggregate projection. |
| `trigger-transition`, `trigger-delay`, `trigger-setup-hold`, `trigger-edge-burst`, `trigger-pattern`, `trigger-or` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No matching public thresholds/timing/count/pattern/readback contracts. Horizontal delay is not event-delay triggering. |

For TBS2074B runt, the admitted spellings come from the documented
`TRIGger:A:RUNT:*` command entries. Conflicting examples do not introduce
`PULSE:RUNT`, new values, or a wider numeric range.

### Waveforms, screenshots, reference memory, and storage

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Boundary |
| --- | --- | --- | --- | --- |
| `capture` | SUPPORTED | SUPPORTED | SUPPORTED | BYTE only, displayed analog channels, safe maximum 1000 requested points. Hidden channels fail without display mutation. Multi-channel capture uses successive transfers; `all` includes hidden channels and fails rather than filtering. No WORD, acquisition reconfiguration, or resampling. |
| `screenshot` explicit BMP host artifact | UNSUPPORTED | SUPPORTED | UNSUPPORTED | TDS2024B uses native `HARDCopy START` over USBTMC with BMP bytes and `.bmp` host artifact semantics. TBS2074B uses a separate native PNG path. TBS1052B BMP applicability remains ambiguous and unsupported. |
| `capture_screenshot_png`; CLI default/explicit PNG | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074B temporarily saves native PNG, waits for OPC, reads the file, validates PNG, and attempts cleanup. Requires writable instrument storage. Black is the only supported background. |
| `screenshot --query-hardcopy`; `query_hardcopy_state` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Required hardcopy area/ink-saver/palette/layout/format readbacks are not all available. |
| `reference-save`, `reference-display`, `reference-query` | SUPPORTED | SUPPORTED | SUPPORTED | Two slots only. Save has OPC completion; query returns actual display state while label/raw_label remain null because Tek lacks matching label readback. |
| `reference-label`, `reference-clear` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No writable reference label or explicit memory-clear action; hiding is not clearing. |
| `save-pwd` | SUPPORTED | SUPPORTED | SUPPORTED | Native filesystem current-directory set/query, subject to public and model filesystem validation. |
| `save-image` | SUPPORTED | SUPPORTED | SUPPORTED | Instrument-side file action, no host artifact; completion requires successful OPC with the existing temporary 15-second timeout restored in `finally`. The current instrument encoding does not add a public format enum. |
| `save-image-format` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074B PNG/BMP setter and matching readback. B1 `SAVE:IMAGE:FILEFORMAT` has no established matching query; `HARDCopy:FORMat?` reads a different setting and cannot be substituted. |
| `save-image-ink-saver` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 `HARDCopy:INKSaver` controls saved images. TBS2074B has no equivalent background/ink-saver control. |
| `save-image-palette`, `save-image-factors`, `save-filename` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No independent matching state/readback. |
| `save-waveform-format` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074B public subset is CSV/SPREADSheet with readback. B1 CSV export has no independent format setter/readback. |
| `save-waveform` | SUPPORTED | SUPPORTED | SUPPORTED | Tek requires the existing optional `source_channel`, bounded to model analog channels, then OPC completion with the temporary 15-second timeout restored. |
| `save-waveform-length`, `save-waveform-length-max` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Record length and transfer start/stop are not export point-count/max-length settings. |
| `setup-save`, `setup-recall` | SUPPORTED | SUPPORTED | SUPPORTED | Slots 1-9 only. File targets remain unsupported; Tek setup-file formats do not satisfy the existing `.scp` contract. |

TDS2024B BMP capture reads through end-of-message, validates the BMP signature,
keeps native BMP bytes, and preserves `.bmp` artifact semantics. Temporary
10-second timeout, hardcopy format, port, and requested ink-saver/background
settings are
restored even after failure. Explicit landscape/portrait and ink-saver controls
map only to documented B1 controls; no palette is invented.

TBS2074B PNG capture uses an instrument temporary filename that obeys TBS2000B
8.3 rules, reads the native file through VISA end-of-message, restores image
format and the temporary 10-second timeout in `finally`, and attempts temporary
file deletion. It does not change working directory or acquisition state.
Neither padded 8-bit data in 16-bit transfers nor larger native record lengths
authorize WORD capture or requested 5000/10000-point capture.

### Aggregate projections

Aggregates skip unsupported atomic queries and never mutate source/display,
measurement slots, trigger mode, or cursor units merely to discover support.

| Aggregate | TBS2074B projection | TDS2024B projection | TBS1052B projection |
| --- | --- | --- | --- |
| `channel-summary` | display, scale, offset, coupling, probe ratio, bandwidth limit, invert, label, probe skew; V/A units on CH1/CH2. Range, impedance, vernier and CH3/CH4 units unavailable. | display, scale, offset, coupling, probe ratio, bandwidth limit, invert, units. Label, probe skew, range, impedance and vernier unavailable. | Same as TDS2024B, CH1/CH2 only. |
| `live-data-snapshot` / `query_instrument_summary` | Channel display/scale/offset, CH1/CH2 units, timebase scale/position using the Delay-Mode conversion above, trigger type/sweep, edge source/slope, channel-qualified level and established source units. | Channel display/scale/offset/units, timebase scale/position, trigger type/sweep/source/slope. Current analog edge-source MAIN:LEVEL is valid snapshot data even though standalone named-channel level is unsupported. | Same as TDS2024B, bounded to two channels. |
| `system-information-snapshot` / `query_acquisition_readouts` | Identity, sample rate, acquisition points and record length available: SUPPORTED. | Identity, acquisition points and record length available; sample rate unavailable: PARTIAL AGGREGATE. | Same as TDS2024B: PARTIAL AGGREGATE. |
| `cursor-query` | Native X positions/delta only when time-based; Y positions/delta only when physical volts are established. Percent/Hz/dB/divisions/amps are not seconds/volts. Inactive/unestablished axes and dydx unavailable. | Active VBARS seconds positions/delta or active HBARS volts positions/delta. Other axis/dydx and FFT/amp/unknown-unit fields unavailable. | Same as TDS2024B. |

`live-data-snapshot` is PARTIAL AGGREGATE on all three. Each registered profile
declares fixed realtime acquisition architecture; absence of segmented-memory
support alone would not establish that. Acquisition processing type remains a
separate `ACQuire:MODe` readback. Unknown fields fall back independently; line
or external source-channel/units/analog-level fields remain unavailable rather
than receiving artificial values.

Cursor OFF projects null positions/deltas/dydx. TBS2074B X-only, Y-only, and
combined X/Y setters use the selected/displayed waveform semantics; source
selection can enable display and reset acquisition and is intentionally not
restored because that would retarget the cursors. Single-axis sets use
independent tracking. Physical-volts Y validation on CH3/CH4 temporarily uses
the waveform transfer source only to verify units and restores that transfer
source in `finally`. B1 setters are X-only time or Y-only physical-volts;
mixed-axis writes and auto-vertical remain unsupported. All returned positions
are actual readbacks rather than echoed input. The source/unit rules retain
manual evidence from TBS2000B pp. 64, 67-73, 77, 161, 191-201 and B1
pp. 2-61-2-68.

`measure-results` is intentionally excluded from nullable projections.
`MEASUrement?` and per-slot aggregate queries describe settings, not the one
native results response required by the public result/raw contract. Doctor
reuses the admitted projections; reference labels remain nullable as described
above. Required-state results such as hardcopy state or DVM/WGEN/Demo queries do
not become partial aggregates merely because a surrounding result allows nulls.

### System, diagnostics, workflows, and host functions

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Boundary |
| --- | --- | --- | --- | --- |
| `live-data-snapshot` | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Projection above. |
| `system-information-snapshot` | SUPPORTED | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Acquisition-readout projection above. |
| `system-status-byte`, `system-clear-status`, `system-opc`, `system-standard-event` | SUPPORTED | SUPPORTED | SUPPORTED | Native `*STB?`, `*CLS`, `*OPC?`, `*ESR?`; destructive reads retain their native semantics. |
| `system-operation-status`, `system-options` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek acquisition/status is not the existing Operation Condition bit contract; model assumptions are not installed-option readback. |
| `check-error`, `query_system_error`, `drain_system_errors` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek Event Queue/SESR semantics are not the normalized system-error queue/drain/clean-state contract. |
| `doctor` | SUPPORTED | SUPPORTED | SUPPORTED | Native-status preflight fails on preexisting errors before the read-only snapshot; unavailable non-edge/non-analog trigger details remain nullable without source/type mutation. |
| `smoke` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | Requires native preflight, BYTE capture, and native PNG screenshot with black background. Disabling artifact saving does not remove those instrument operations. |
| `acquisition-check` | SUPPORTED | SUPPORTED | SUPPORTED | Exercises only profile-supported acquisition modes/counts; unsupported modes are skipped. Check-only is read-only; requested restoration is verified by native status and actual readback. |
| `cleanup` | SUPPORTED | SUPPORTED | SUPPORTED | Capability-driven CLS/OPC/native-status sequence. Unavailable auxiliary/display steps are skipped; `final_error_queue_clean` stays null. |
| `capture-batch`, `capture-until`, `capture-monitor` | SUPPORTED | SUPPORTED | SUPPORTED | BYTE/1000-point analog subset with native status checkpoints and bounded host workflow behavior. |
| `measure-log`, `measure-until` | SUPPORTED | SUPPORTED | SUPPORTED | Model-specific single-source immediate subset with TYPE/SOURCE restoration and native status checkpoints. |
| `triggered-measure-loop`, `triggered-capture-series` | SUPPORTED | SUPPORTED | SUPPORTED | Exactly one single acquisition per iteration, then wait on the current completion without rearming. |
| `sequence` | SUPPORTED | SUPPORTED | SUPPORTED | wait, single, wait-trigger, measure, capture and cleanup on all three; screenshot only on TBS2074B and only PNG/black. All steps/options are validated before writes. |
| `list-resources`, `capabilities`, `manifest`, `hardware-report` | SUPPORTED | SUPPORTED | SUPPORTED | Host VISA enumeration/profile/report operations; offline report rendering and simulation are not hardware proof. |
| `worker`, `status`, `wait-ready`, `send-command`, `stop` | SUPPORTED | SUPPORTED | SUPPORTED | Existing lifecycle/admission rules apply. `send-command` is not arbitrary SCPI; worker stop and acquisition stop remain distinct. |

Host planners, schemas, identity/capability resolution, artifact writers,
progress/cancellation, session open/close, and interruptible waits are
infrastructure rather than extra hardware features. Core plan/run pairs inherit
the workflow rows. Dry-run and simulator output do not establish live support.

### Other unsupported feature families

These existing families are UNSUPPORTED on TBS2074B, TDS2024B, and TBS1052B.
Query-shaped APIs are not partial aggregates when no feature-specific
settings/results exist.

| Existing operation / adapter aliases | Shared boundary |
| --- | --- |
| `dvm-enable`, `dvm-source`, `dvm-mode`, `dvm-auto-range`, `dvm-current`, `dvm-query` | No integrated DVM state/reading contract; periodic RMS is not a DVM. |
| `wgen-output`, `wgen-function`, `wgen-frequency`, `wgen-voltage`, `wgen-offset`, `wgen-load`, `wgen-query` | No generator output/function/frequency/amplitude/offset/load command set. |
| `demo-output`, `demo-function`, `demo-phase`, `demo-query` | No programmable demo output/function/phase; probe compensation is not this feature. |
| `serial-mode`, `serial-display` (`serial-enable`, `serial-disable`), `serial-query` (`serial-status`) | No bus-slot decode mode/display/state; RS-232 interface commands are not waveform serial decoding. |
| `serial-uart` (`serial-uart-set`, `serial-uart-show`), `serial-i2c` (`serial-i2c-set`, `serial-i2c-show`), `serial-spi` (`serial-spi-set`, `serial-spi-show`), `serial-can` (`serial-can-set`, `serial-can-show`) | No protocol signal/threshold/framing/address/rate decode configuration/readback. |
| `serial-trigger-uart` (`serial-trigger-uart-set`, `serial-trigger-uart-show`), `serial-trigger-i2c` (`serial-trigger-i2c-set`, `serial-trigger-i2c-show`), `serial-trigger-spi` (`serial-trigger-spi-set`, `serial-trigger-spi-show`), `serial-trigger-can` (`serial-trigger-can-set`, `serial-trigger-can-show`) | No protocol/data/address/error trigger selectors/readbacks; edge/pulse cannot substitute. |
| `serial-lister-display`, `serial-lister-reference`, `serial-lister-query` (`serial-lister-status`), `serial-lister-export` (`serial-data`) | No decoded-event lister visibility/reference/data/count/export source. |
| `search-state`, `search-mode`, `search-count`, `search-event` | No search enable/type/count/navigation contract; zoom/cursors are not event navigation. |
| `serial-search-uart`, `serial-search-i2c`, `serial-search-spi`, `serial-search-can` | No protocol-qualified search configuration/results. |
| `segmented-memory`, `segmented-capture` | No segmented count/selection/time-tag/all-segment waveform contract; repeated acquisitions/reference slots do not substitute. |

### Tek post-command status boundary

Ordinary supported Tek operations that use the transparent post-command status
seam perform one internal `*ESR?` after the business response completes. Only
SESR bits 5-2 (CME, EXE, DDE, QYE) are operation errors. PON, URQ, RQC, and OPC
alone do not indicate operation failure.

Ordinary post-checks do not issue `EVENT?`, `EVMsg?`, `ALLEv?`, or `EVQty?`,
do not emulate a normalized system-error queue, and do not populate top-level
`system_error`. A nonzero error mask follows the existing structured error path
and retains raw SESR. Because `*ESR?` is destructive, `system-standard-event`
gets exactly its requested read; `system-clear-status`, `system-status-byte`,
and `system-opc` do not receive an extra hidden SESR read. Post-checking is not
a completion wait and never makes an unsupported operation supported. The
`measure` and `capture` primitives use this post-command seam; composed
workflows use the native workflow checkpoint below rather than performing a
second primitive SESR read.

### Native workflow status

Workflow checkpoints first read `DESE?` and require error bits 2-5 to be
enabled. They then consume one `*ESR?` followed by `ALLEv?` before any later
SESR read. They do not modify DESE, ESE, or SRE. This ordering follows the
documented destructive SESR/event cohort: a later SESR read can discard unread
events from the preceding cohort. See TBS2000B pp. 206-209 and B1 chapter 3.

Workflow results keep `system_error: null` and expose `post_command_status` with
source `tektronix-sesr`, raw SESR/event responses, decoded events/categories,
completeness, and destructive-read flags. Samples and sequence/acquisition steps
use the same representation. Command, execution, device, and query error bits
fail the checkpoint; informational events alone do not. A warning that sets an
error bit still fails. Malformed responses, queue overflow (350), and incomplete
status fail closed and prevent further workflow steps. No retry may consume a
second SESR to hide an unread or malformed cohort.

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
  `HARDCopy:FORMat?` is not treated as a readback of
  `SAVE:IMAGE:FILEFORMAT`; format-independent `save-image` and documented
  ink-saver control remain separate support decisions.
- TBS2000B manual p. 64 restricts `CH<x>:YUNit` to CH1/CH2. The Math section
  mentions CH3/CH4 but lists only CH1/CH2 expressions; missing subsets are not
  inferred.
- TBS2000B FFT documentation does not establish the full-span conversion or
  frequency reference needed by the public atomic result (pp. 93-97).
- TBS2000B cursor documentation refers to a source without a corresponding
  command entry. The selected-waveform adapter therefore uses documented
  `SELect:CONTROl` semantics, including selection/display/acquisition effects
  (pp. 67-73, 161).
- Some TBS2000B trigger examples contradict the command syntax. Only
  independently documented trigger controls and the explicit runt subset are
  admitted (pp. 172, 174, 177-180); pulse-width exposes only its selected
  less-than/greater-than threshold, not retained independent thresholds or
  range.
- TBS2000B measurement aggregate examples show statistics/indicator fields
  without defined matching controls. They do not establish the public
  measurement-statistics or marker-visibility features.

No ambiguity in this section authorizes new public operations, enums, waveform
conversions, filesystem helpers, or support decisions.

## Keysight InfiniiVision Model Support


### Instrument-Side Math Matrix

Math support is instrument-side only. Canonical operation and source names
remain independent of raw SCPI readbacks.

| Surface | 2000X | 3000X | 4000X |
| --- | --- | --- | --- |
| Math function slots and dialect | 1; unnumbered `:FUNCtion` | 1; unnumbered `:FUNCtion` | 4; indexed `:FUNCtion<n>` |
| Operators | `add`, `subtract`, `multiply`, `divide` | Same | Same |
| Transforms | `differentiate`, `integrate`, `sqrt`, `absolute`, `square`, `ln`, `log10`, `exp`, `exp10`, `linear` | Same | Same |
| Filters | `low-pass`, `high-pass` | Same | `low-pass`, `high-pass`, `average`, `smooth`, `envelope` |
| Visualizations | `magnify`, `trend` | Same | `magnify`, `trend`, `maximum`, `minimum`, `peak`, `max-hold`, `min-hold` |
| FFT | Basic magnitude FFT | Basic magnitude FFT | Magnitude FFT and FFT Phase with advanced controls |
| Composite / GOFT source | Global analog-channel composite | Same | Not supported |
| Math cascade source | Not supported | Not supported | Lower-numbered Math functions only |
| Accumulation clear | Not supported | Not supported | `average`, `max-hold`, `min-hold` |

Display, vertical configuration, query, and the applicable clear behavior use
the same function-slot dialect. The 2000X/3000X profiles reject Math-function
cascade sources. The 4000X profile rejects composite/GOFT sources and rejects
self-reference or forward-reference before backend access. The existing
`fft` CLI and Worker command remains compatible across all profiles.

Bus timing and bus state are not supported because the required MSO/digital-
channel foundation is not available. They are absent from enabled capability
operations, CLI choices, Worker commands, Core builders, and simulator behavior.

- BYTE and WORD waveform capture with a conservative 10,000-point safe maximum.
- Read-only measurement helpers and screenshot capture.
- Measurement control helpers for clearing measurements, enabling or
  querying measurement markers, selecting analog measurement sources, and
  selecting the MAIN, ZOOM, AUTO, or GATE measurement window. ZOOM is
  conditional on the zoomed timebase already being displayed; AUTO is safer
  when that state is unknown. A source1-only write may preserve source2 in
  instrument readback.
- Advanced measurement statistics are capability-gated to 3000X and 4000X.
  Core queries instrument-accumulated current, minimum, maximum, mean,
  standard-deviation, and count results and controls statistics mode, LCD
  display, maximum count, relative standard deviation, reset, and manual
  increment. The 2000X profile does not advertise this capability.
- Reference waveform helpers for runtime-managed reference waveform
  slots 1 and 2. The instrument may turn off one slot's display when the other
  is enabled.
- DVM helpers for enable, analog source, `dc`, `dc-rms`, and
  `ac-rms` voltage modes, auto range, current voltage, and aggregate queries.
  DVM can be option/license dependent. It does not support DVM frequency,
  independent `:COUNter`, or `:MEASure:COUNter` support.
- DEMO output aggregate and focused output/function/phase helpers.
  DEMO is option-/hardware-dependent; capability profiles guard the documented
  function names before session open, while live instrument errors remain
  authoritative for missing options or hardware.
- Waveform generator output, function, frequency, amplitude, offset, load, and
  aggregate query helpers. The 2000X/3000X profiles use `:WGEN`; the 4000X
  profile uses only generator 1 through `:WGEN1`. Settable functions are
  `sine`, `square`, `ramp`, `pulse`, `noise`, and `dc`.
- Serial bus aggregate query, mode, and display controls plus UART, I2C, SPI,
  and CAN basic protocol settings. Capability profiles
  guard bus count and settable modes. Serial decode can require an
  instrument license; Core does not probe licenses and preserves instrument
  errors for unavailable hardware or options.
- Serial trigger support provides the documented common I2C, SPI, and CAN trigger
  subset on the same capability profiles. It does not add a capability field;
  model profiles continue to guard bus count and protocol mode availability.
- Waveform search state and count queries plus profile-guarded mode
  configuration. Unsupported modes are rejected before search SCPI is sent.
- Instrument-side SAVE commands for current save
  directory and base name, image settings and start, and waveform settings and
  start. All three profiles also expose the query-only maximum-length mode
  readback. The configured waveform length minimum is 100 points; the actual
  maximum remains instrument/model dependent.
- Analog channel labels, display labels, and display annotation.
- Core/CLI/simulator/worker support for the documented one-shot trigger
  commands, including `trigger-tv` basic TV / video trigger configure and
  query.
- Triggered capture wait classification for DSO-X 2000X/3000X/4000X using the
  Operation Status Condition Run bit.

Series-specific differences:

| Series | DEMO output functions | Serial buses | Serial settable modes | Waveform search modes | Screenshot formats |
| --- | --- | ---: | --- | --- | --- |
| 2000X | Common/core set | 1 | `can`, `i2c`, `lin`, `spi`, `uart` | `serial1` | No; existing PNG capture remains supported |
| 3000X | Common/core set plus `i2s`, `can-lin`, `flexray`, `arinc`, `mil`, `mil2` | 2 | `a429`, `flexray`, `can`, `i2s`, `i2c`, `lin`, `m1553`, `spi`, `uart` | `edge`, `glitch`, `runt`, `transition`, `serial1`, `serial2` | No; existing PNG capture remains supported |
| 4000X | Same documented set as 3000X | 2 | `a429`, `flexray`, `can`, `cxpi`, `i2s`, `i2c`, `lin`, `m1553`, `manchester`, `nrz`, `sent`, `spi`, `uart`, `usb`, `usb-pd` | `edge`, `glitch`, `runt`, `transition`, `serial1`, `serial2`, `peak` | PNG, BMP, BMP8bit, appearance controls, and state query |

The common/core DEMO set is `sine`, `noisy`, `phase`, `lf-sine`, `am`,
`rf-burst`, `fm-burst`, `harmonics`, `coupling`, `ringing`, `single`, `clock`,
`runt`, `transition`, `setup-hold`, `mso`, `burst`, `glitch`,
`edge-then-edge`, `i2c`, `uart`, `spi`, `can`, and `lin`. The documented DEMO
function set excludes additional 4000X-only functions. It does not include WGEN
behavior and adds no WebUI runtime behavior.

Screenshot format support is capability-gated to 4000X because its explicit
format transfer uses the documented `:HCOPY:SDUMp` command family.

All three profiles support `search-state` and query-only `search-count`.
`search-mode` enables search before setting the mode. Search event navigation is supported on 4000X via `search-event`.
Serial Search provides protocol-specific search controls for UART, I2C, SPI,
and CAN. 2000X supports bus 1; 3000X and 4000X support buses 1 and 2. The
selected Serial bus must be configured with the matching Serial command first.

- 2000X and 3000X channel labels allow up to 10 printable ASCII characters.
- 4000X channel labels allow up to 32 printable ASCII characters.
- 2000X and 3000X annotation uses one unindexed slot and does not support X/Y
  annotation position.
- 4000X annotation supports indexed slots 1 through 10 and X/Y annotation
  position.
- 4000X supports the guarded `delay` pair measurement path. 2000X and 3000X do
  not expose that helper because their delay query depends on measurement
  definition state.

Raw waveform points mode remains disabled. Segmented memory query, explicit
mode/count configuration, and the finite single-channel `segmented-capture`
workflow are available for the registered 2000X, 3000X, and 4000X profiles.
The documented count ranges are 2-250 on 2000X and 2-1000 on 3000X/4000X,
while the actual maximum may be lower for the selected memory depth.
Segmented-memory availability may depend on an SGM option or license; the
capability flag permits this documented command-family path but does not claim
that the option is installed. Segmented capture does not perform continuous
acquisition, restore state, disable segmented mode, force a trigger, merge CSVs,
or perform instrument-side save/export. Serial
decode capability represents command-family availability, not the presence of
an instrument license.

Serial aggregate responses remain raw. Serial protocol configuration provides
only basic UART, I2C, SPI, and CAN source/decode settings. Serial Lister adds
global display/reference controls and host-side raw CSV export through
`:LISTer:DATA?`; it does not support protocol-specific CSV
parsing, or instrument-side `:SAVE:LISTer`. Serial Search provides
protocol-specific UART, I2C, SPI, and CAN search controls after the matching
Serial bus has been configured. Lister display selection `bus2` is unavailable
on 2000X and available on 3000X/4000X; `all` remains valid on 2000X.
