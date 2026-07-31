# Scopes Tool Core

Core runtime package for Keysight InfiniiVision oscilloscope control through
PyVISA-compatible backends.

Distribution: `scopes-tool`

Import package: `scopes_tool_core`

## Scope

Core owns runtime behavior:

- Safe resource opening and run-mode resolution.
- IDN parsing and canonical physical model identity resolution.
- Registry-linked capability profiles for supported InfiniiVision models.
- Channel, display label, display annotation, common display one-shot,
  timebase, trigger, acquisition, measurement, waveform, screenshot, and
  operation helpers.
- Analog channel advanced setting helpers for impedance, invert, full-scale
  range, units, vernier, and probe skew.
- Read-only analog channel summaries that aggregate common channel and probe
  setup for every analog channel in the active capability profile.
- Simulator and fake backend support for hardware-free tests.
- MATH-P1 instrument-side Math waveform display and vertical controls through
  `Oscilloscope.configure_math_display()`, `query_math_display()`,
  `configure_math_vertical()`, and `query_math_vertical()`. The controls use
  the single unindexed `:FUNCtion` subsystem on 2000X/3000X and indexed slots
  1 through 4 on 4000X. Vertical configuration supports scale or range plus an
  optional offset and does not automatically enable display or run autoscale.
  Instrument firmware may recalculate vertical scaling when Math display
  changes from OFF to ON, so callers that need explicit vertical settings
  should enable display before applying scale, range, or offset. Math operation
  selection, sources, host-side Math, license probing, and slot coordination
  are outside P1. Coverage is hardware-free only; no live validation was
  performed.
- MATH-P2 instrument-side dual-source Math operators through
  `Oscilloscope.configure_math_operator()` and `query_math_operator()`. P2
  supports `add`, `subtract`, `multiply`, and `divide` with two analog-channel
  sources. Both source1 and source2 remain analog-channel-only on every series.
  It reuses the single unindexed 2000X/3000X Math function and indexed 4000X
  slots, preserves normalized and raw query values, and does not enable display
  or change vertical controls. Reference, Math, bus, digital, external, and
  arbitrary-expression sources are not supported. Capability profiles describe
  the available runtime path, not validated instrument licenses. Coverage is
  hardware-free only; no live validation was performed.
- MATH-P3 instrument-side single-source Math transforms through
  `Oscilloscope.configure_math_transform()` and `query_math_transform()`. P3
  supports `differentiate`, `integrate`, `sqrt`, `absolute`, `square`, `ln`,
  `log10`, `exp`, `exp10`, and `linear` with one source.
  Integrate optionally sets input offset; linear optionally sets gain and
  linear offset. It reuses the unindexed 2000X/3000X function and indexed
  4000X slots, does not enable display, and leaves license availability to the
  instrument error queue. P4 permits the 2000X/3000X `composite` GOFT source
  and a lower-numbered Math function source on 4000X. Reference and bus sources,
  host-side calculation, and waveform export are not implemented. Coverage is
  hardware-free only; no live validation was performed.
- MATH-P4 global GOFT configuration through
  `Oscilloscope.configure_math_composite_source()` and
  `query_math_composite_source()`. The 2000X/3000X path supports `add`,
  `subtract`, or `multiply` over two analog channels and can feed that result
  to `math-transform` as `composite`. The 4000X path instead supports Math
  cascade by allowing only a lower-numbered Math function as the
  `math-transform` source. `math-operator` remains analog-channel-only.
  These controls do not calculate or export waveform data, enable display,
  change vertical settings, or probe licenses. Coverage is hardware-free only;
  no live validation was performed.
- MATH-P5 instrument-side Math filters through
  `Oscilloscope.configure_math_filter()`, `query_math_filter()`, and
  `clear_math()`. All registered series support `low-pass` and `high-pass`;
  4000X additionally supports `average`, `smooth`, and `envelope`. Filter
  sources reuse the P4 single-source rules: analog channels on all series,
  `composite` on 2000X/3000X, and a lower-numbered Math function on 4000X.
  Cutoff, average-count, and smooth-point writes are optional and
  operation-specific. Math clear is available only on profiles that support
  average and uses indexed 4000X `:FUNCtion<n>:CLEar`. These controls do not
  calculate waveforms, enable display, change vertical or acquisition state,
  probe licenses, or wait for completion. Coverage is hardware-free only; no
  live validation was performed.
- MATH-P6 instrument-side visualizations through
  `Oscilloscope.configure_math_visualization()` and
  `query_math_visualization()`. All registered series support `magnify` and
  `trend`; 4000X additionally supports `maximum`, `minimum`, `peak`,
  `max-hold`, and `min-hold`. Non-Trend sources reuse the existing
  single-source rules. Trend uses an analog source and canonical measurement
  on 2000X/3000X, with source2 only for `vratio`; 4000X Trend selects an
  already-installed measurement slot and does not read or write Math sources.
  Math clear applies to 4000X `average`, `max-hold`, and `min-hold`
  accumulations. These controls do not install measurements, calculate or
  export waveform data, enable display, run autoscale, change acquisition
  state, or probe licenses. Coverage is hardware-free only; no live validation
  was performed.
- MATH-P7 completes the existing instrument-side FFT path through
  `Oscilloscope.configure_fft()` and `query_fft()`. The 2000X/3000X profiles
  retain basic magnitude FFT with the unindexed Math function. The 4000X
  profile adds indexed FFT Phase, start/stop frequency, Main/Zoom gating,
  phase reference, detector type and point controls, plus read-only bin size,
  FFT sample rate, and resolution bandwidth. Center/span and start/stop are
  alternate displayed-range controls and cannot be mixed. Phase reference is
  valid only for FFT Phase and is queried only when the current operation is
  FFT Phase. These controls do not calculate FFT data on the host, enable Math
  display, configure Zoom or timebase, run autoscale, or change acquisition
  state. Coverage is hardware-free only; no live validation was performed.
- MATH-P9 closes the P0-P7 instrument-side Math surface with cross-layer
  consistency gates for capability operations, Core builders and parsers,
  CLI choices, Worker schemas, simulator state, function-slot dialects, and
  legacy FFT behavior. Math remains instrument-side only. MATH-P8 bus-timing
  and bus-state are not enabled because the required MSO/digital-channel
  foundation is not implemented. The closure is hardware-free; focused live
  validation remains required by registered model, firmware, and transport.
- System/Status Pack v1 helpers for `*CLS`, `*OPC?`, `*STB?`, destructive
  `*ESR?`, `:OPERegister:CONDition?`, and `*OPT?`. Parsers preserve raw
  responses, expose bounded integer register values and stable set-bit indexes,
  and preserve trimmed option tokens including a raw no-option-style `0`.
  `:RSTate?`, service-request or event-enable writes, UI locking, return to
  local, date/time, and a replacement for the existing
  system-error helpers are not implemented. Coverage is hardware-free; no live
  hardware validation was performed, and no WebUI runtime behavior was added.
- Conservative `minimal` and `safe` cleanup profiles compose existing status,
  display, DVM, search, annotation, and Demo helpers. Unsupported steps are
  reported instead of adding new subsystems; cleanup never performs reset,
  preset, autoscale, or broad state restoration.
- Save/Export Pack v1 helpers for common 2000X/3000X/4000X instrument-side
  image and waveform file saving. The pack configures the current save
  directory, base filename, image format/palette/ink-saver/factors, and
  waveform format/length; it can then start an image or waveform save with an
  explicit filename and wait with `*OPC?`. It does not retrieve bytes or create
  host-side files. Existing capture and screenshot APIs remain PC-side
  workflows. Image and waveform format queries normalize the read-only `NONE`
  sentinel to canonical `none`; `none` is not a settable format. Results,
  lister, mask, multi, power, arbitrary, compliance,
  segmented, setup, and WMEMory export are outside v1. Coverage is
  hardware-free; no live hardware validation was performed.
- Serial Lister P2 global display/reference query and configuration plus
  host-side raw CSV export through `:LISTer:DATA?`. The export preserves the
  instrument payload without protocol-specific parsing and does not enable
  decode, acquire traffic, or change SBUS display state. Lister display
  selection uses `off`, `bus1`, `bus2`, and `all`; `bus2` is unavailable on
  2000X and available on 3000X/4000X profiles.
- Measurement Control Pack v1 helpers for clearing screen measurements,
  enabling or querying measurement markers, selecting one or two analog
  measurement source channels, and selecting `MAIN`, `ZOOM`, `AUTO`, or
  `GATE` measurement windows. Marker OFF is intentionally not exposed in v1.
  A source1-only write sets source1 but may preserve an existing source2
  selection in instrument readback; callers that require an explicit
  two-source default should set both sources. `ZOOM` is conditional on the
  zoomed timebase already being displayed. DSO-X 4034A firmware 07.20 may
  return `-221,"Settings conflict"` otherwise, so `AUTO` is safer when zoom
  state is unknown.
- DVM Common Pack v1 helpers for enabling DVM, selecting one analog source,
  selecting `dc`, `dc-rms`, or `ac-rms` voltage mode, controlling auto range,
  reading current voltage, and querying aggregate state. DVM availability may
  depend on an instrument option or license. `:DVM:FREQuency`, DVM frequency
  mode, the independent `:COUNter` subsystem, and `:MEASure:COUNter` are not
  implemented. Coverage is hardware-free; no live hardware validation was
  performed for this pack.
- Demo Output Pack v1 helpers for querying aggregate built-in DEMO state and
  configuring or querying DEMO output, function, and phase. Function sets are
  capability-profile guarded; unknown function readbacks remain available as
  raw values. DEMO is option-/hardware-dependent, so unsupported live
  instruments may report normal instrument errors. This pack is hardware-free
  validated only, remains separate from WGEN, excludes additional 4000X-only
  DEMO functions, and adds no WebUI runtime behavior.
- WGEN Basic P1 helpers for output, function, frequency, peak-to-peak
  amplitude, offset, load, and aggregate queries. The 2000X and 3000X use the
  unindexed `:WGEN` subsystem; the 4000X uses generator 1 through `:WGEN1`.
  Settable functions are limited to `sine`, `square`, `ramp`, `pulse`, `noise`,
  and `dc`. Software safety guards require positive finite frequency,
  `0 < amplitude <= 5.0` volts, and `-2.5 <= offset <= 2.5` volts. Coverage is
  hardware-free only; no live hardware validation was performed.
- Search Basic Pack v1 helpers for enabling or disabling waveform search,
  selecting a model-profile-supported basic search mode, and querying the
  search event count. Mode configuration enables search before setting the
  mode. DSO-X 2000X supports `serial1`; 3000X supports `edge`, `glitch`,
  `runt`, `transition`, `serial1`, and `serial2`; 4000X additionally supports
  `peak`. Serial Search P3 adds model-guarded serial search controls for UART,
  I2C, SPI, and CAN; 2000X exposes bus 1, while 3000X and 4000X expose buses 1
  and 2. Configure the matching Serial bus before using Serial Search. Coverage is hardware-free; no
  live hardware validation was performed for this pack.
- Reference Waveform Pack v1 helpers for saving an analog channel to reference
  slot 1 or 2, configuring or querying display and label state, clearing a
  slot, and querying aggregate display/label state. Labels are limited to
  1-10 printable ASCII characters without double quotes. File-based reference
  save/recall and reference scale, skew, offset, and range controls are not
  implemented. Focused DSO-X 4034A USB CLI live validation passed for save,
  display, label, query, and clear operations on both slots. Enabling one
  reference slot for display may turn off the other slot on that instrument;
  this is normal instrument-managed display behavior.
- Read-only analog acquisition sample rate query helpers.
- Screenshot Format Pack v1 helpers for 4000X screen-dump PNG, BMP, and
  8-bit BMP capture plus hardcopy ink saver, palette, layout, and aggregate
  state queries. Existing cross-series color PNG capture remains unchanged.
- Read-only acquisition points and record-length query helpers, separate from
  waveform transfer points.
- Explicit triggered-capture wait helpers that arm `:SINGle`, poll
  `:OPERegister:CONDition?`, classify DSO-X 2000X/3000X/4000X completion by
  the Operation Status Condition Run bit, and expose raw poll values for
  adapter JSON.
- Analog-channel edge trigger helpers exposed through
  `Oscilloscope.configure_trigger_edge()` and
  `Oscilloscope.query_trigger_edge()`. This canonical API configures and
  queries the existing `:TRIGger:MODE EDGE` and `:TRIGger:EDGE:*` SCPI
  behavior for DSO analog channels only; external and digital/MSO edge trigger
  expansion is not included.
- Edge Trigger source-only helpers exposed through
  `Oscilloscope.configure_trigger_edge_source()` and
  `Oscilloscope.query_trigger_edge_source()`. This v1 slice uses only
  `:TRIGger:EDGE:SOURce` and configures analog channels, External, or AC Line
  sources without changing trigger mode, level, slope, coupling, reject, or
  acquisition state. The common DSO-X 2000X/3000X/4000X target models support
  `CHANnel<n>`, `EXTernal`, and `LINE`; analog channels are validated against
  the selected model profile. Query parsing preserves the stripped raw source
  and tolerates unsupported, digital, WaveGen, `NONE`, and future readbacks by
  returning no normalized source. This implementation is hardware-free only;
  live validation has not been run. WGEN/WMOD/digital source configuration is
  not implemented.
- Phase 13C - Edge Trigger Slope and Analog Level v1 helpers exposed through
  `Oscilloscope.configure_trigger_edge_slope()`,
  `Oscilloscope.query_trigger_edge_slope()`,
  `Oscilloscope.configure_trigger_edge_level()`, and
  `Oscilloscope.query_trigger_edge_level()`. The slope command uses only
  `:TRIGger:EDGE:SLOPe` for `positive`, `negative`, `either`, or `alternate`;
  query preserves the stripped raw slope and tolerates unknown values without
  claiming configure support. The level command always uses an explicitly
  named analog channel with `:TRIGger:EDGE:LEVel <level>,CHANnel<n>` or
  `:TRIGger:EDGE:LEVel? CHANnel<n>`. It validates only a finite real value and
  the selected profile's analog channel count; the current vertical range and
  center remain instrument-state dependent, so Core performs no scale, offset,
  or range queries and does not clamp levels. These commands do not switch
  trigger mode or source and do not change coupling, reject, common trigger
  settings, holdoff, acquisition, or channel settings. The documented target
  DSOX2004A, DSOX3024A, DSOX4024A, and DSOX4034A model coverage is
  hardware-free only; live validation has not been run. Line, WaveGen, WMOD,
  and digital/MSO level controls are not implemented.
- Phase 14 External Trigger Range and External Edge Level v1 helpers exposed
  through `Oscilloscope.configure_external_trigger_range()`,
  `Oscilloscope.query_external_trigger_range()`,
  `Oscilloscope.configure_trigger_edge_external_level()`, and
  `Oscilloscope.query_trigger_edge_external_level()`. They use only
  `:EXTernal:RANGe` and External-qualified `:TRIGger:EDGE:LEVel ...,EXTernal`
  SCPI, without changing trigger mode or source. Local range validation is
  finite-positive only; it does not query External probe attenuation or clamp
  values. Local External level validation is finite-real only; it does not
  query range or clamp levels. The instrument error queue remains authoritative
  for probe-, model-, firmware-, and hardware-dependent limits. At 1:1, the
  manuals document 8 V for 2000X/3000X and 1.6 V or 8 V for 4000X; this
  hardware-free simulator does not emulate every model/probe-dependent range
  rejection. Target DSOX2004A, DSOX3024A, DSOX4024A, and DSOX4034A coverage
  has not received live hardware validation. Line, WaveGen, WMOD, and
  digital/MSO External-level variants remain out of scope.
- Phase 15 External Trigger Input Settings v1 helpers exposed through
  `Oscilloscope.configure_external_trigger_probe()`,
  `Oscilloscope.query_external_trigger_probe()`,
  `Oscilloscope.configure_external_trigger_units()`,
  `Oscilloscope.query_external_trigger_units()`, and
  `Oscilloscope.query_external_trigger_settings()`. They use only
  `:EXTernal:PROBe`, `:EXTernal:UNITs`, and the read-only aggregate
  `:EXTernal?` query. Probe attenuation validation is finite-positive only;
  units configure accepts only `volts` and `amps`. The aggregate parser
  tolerates abbreviated, full, reordered, and unknown fields while preserving
  the complete raw response; malformed known numeric values still fail. No
  External bandwidth-limit setter (use existing `trigger-hf-reject` for common
  high-frequency rejection), AutoProbe discovery, probe-aware range or
  level scaling, trigger mode/source modification, or automatic compensation
  is implemented. The simulator intentionally stores probe attenuation, units,
  range, and External Edge level independently. These DSO-X 2000X/3000X/4000X
  paths are hardware-free only; live hardware validation has not been run.
- Common trigger general setting helpers exposed through
  `Oscilloscope.configure_trigger_sweep()`,
  `Oscilloscope.query_trigger_sweep()`,
  `Oscilloscope.configure_trigger_noise_reject()`,
  `Oscilloscope.query_trigger_noise_reject()`,
  `Oscilloscope.configure_trigger_hf_reject()`, and
  `Oscilloscope.query_trigger_hf_reject()`. This `trigger-sweep`,
  `trigger-noise-reject`, and `trigger-hf-reject` v1 slice uses only
  `:TRIGger:SWEep`, `:TRIGger:NREJect`, and `:TRIGger:HFReject`. Query mode
  preserves raw readbacks while normalizing sweep to `auto` or `normal` and
  the common reject settings to booleans.

- Edge Trigger coupling and reject filter helpers exposed through
  `Oscilloscope.configure_trigger_edge_coupling()`,
  `Oscilloscope.query_trigger_edge_coupling()`,
  `Oscilloscope.configure_trigger_edge_reject()`, and
  `Oscilloscope.query_trigger_edge_reject()`. This v1 slice uses only
  `:TRIGger:EDGE:COUPling` and `:TRIGger:EDGE:REJect`. Each command
  configures or queries its own SCPI setting independently. Query mode
  preserves raw readbacks while normalizing coupling to `ac`, `dc`, or
  `lf-reject`, and reject to `off`, `lf-reject`, or `hf-reject`. It is
  hardware-free only so far; no live
  hardware validation has been run, and it does not add holdoff, generic
  trigger settings, run, stop, single, force-trigger, wait-trigger, capture, or
  WebUI runtime behavior.
- Analog-channel pulse-width trigger helpers for the Keysight
  `:TRIGger:GLITch...` command family. This first slice configures and queries
  pulse-width trigger state only; it does not run, stop, single, force trigger,
  wait for trigger, or capture waveform data.
- Analog-channel runt trigger helpers for the Keysight `:TRIGger:RUNT...` and
  shared `:TRIGger:LEVel:LOW/HIGH` command families. This slice configures and
  queries runt trigger state only; it does not run, stop, single, force
  trigger, wait for trigger, or capture waveform data.
- Analog-channel transition trigger helpers for the Keysight
  `:TRIGger:TRANsition...` and shared `:TRIGger:LEVel:LOW/HIGH` command
  families. This v1 slice configures and queries transition trigger state only;
  it does not run, stop, single, force trigger, wait for trigger, or capture
  waveform data.
- DSO analog-channel Edge Then Edge / Delay trigger helpers for the Keysight
  `:TRIGger:DELay...` command family. This `trigger-delay v1` slice
  configures analog arm and trigger source channels, positive/negative arm and
  trigger slopes, delay time, and Nth trigger edge count. Query mode preserves
  raw readbacks and tolerates digital or unknown source state. It is
  hardware-free only so far; no live hardware validation has been run, and it
  does not add run, stop, single, force trigger, wait-trigger, capture, or
  WebUI runtime behavior.
- DSO analog-channel setup-hold trigger helpers for the Keysight
  `:TRIGger:SHOLd...` command family. This `trigger-setup-hold v1` slice
  configures analog clock and data source channels, positive/negative clock
  slope, setup time, and hold time. Query mode preserves raw readbacks and
  tolerates digital or unknown source state, but configure mode intentionally
  rejects MSO/digital, external, and unknown sources. Focused DSO-X 4034A USB
  CLI live validation passed on 2026-07-08. Worker live, LAN, WebUI, other
  DSO-X models, MSO/digital configuration, signal-trigger behavior, run, stop,
  single, wait-trigger, capture, and broader trigger-tree behavior remain not
  run or out of scope.
- DSO analog-channel Nth Edge Burst trigger helpers for the Keysight
  `:TRIGger:EBURst...` command family. This `trigger-edge-burst v1` slice
  configures `:TRIGger:MODE EBURst`, analog source channel, positive/negative
  slope, edge count, idle time, and optional source-qualified analog
  `:TRIGger:EDGE:LEVel`. Query mode preserves raw source readbacks and
  tolerates digital, `NONE`, or unknown source state without querying analog
  level unless the source safely parses as analog. Focused DSO-X 4034A USB CLI
  live validation passed on 2026-07-09. Worker live, LAN, WebUI, other DSO-X
  models, MSO/digital configuration, signal-trigger behavior, run, stop,
  single, wait-trigger, capture, and broader trigger-tree behavior remain not
  run or out of scope.
- DSO analog-channel basic TV / video trigger helpers for the Keysight
  `:TRIGger:TV...` command family. This `trigger-tv v1` slice configures
  `:TRIGger:MODE TV`, analog source channel, basic standard
  `ntsc`/`pal`/`palm`/`secam`, basic TV mode, optional line number for line
  modes, and positive/negative polarity. Query mode preserves raw readbacks and
  tolerates digital, external, extended-standard, `LINE` mode, or unknown TV
  subtree states without crashing. It is hardware-free only so far; no live
  hardware validation has been run, and it does not add extended video/UDTV,
  MSO/digital or external source configuration, signal-trigger behavior, run,
  stop, single, wait-trigger, capture, or WebUI runtime behavior.
- DSO analog ASCII pattern trigger helpers for the Keysight
  `:TRIGger:PATTern...` command family. This v1 slice configures
  `:TRIGger:MODE PATTern`, `:TRIGger:PATTern:FORMat ASCii`, raw `0/1/X`
  patterns, and `:TRIGger:PATTern:QUALifier ENTered`; query mode preserves
  raw pattern, edge source, and edge readbacks. It is hardware-free only so
  far; no live hardware validation has been run.
- DSO analog-only OR trigger helpers for the Keysight `:TRIGger:OR` command
  family. This v1 slice configures `:TRIGger:MODE OR` and raw `R/F/E/X` edge
  masks, and queries `:TRIGger:MODE?` plus `:TRIGger:OR?`. Pattern order
  follows Keysight OR trigger bit assignment: CH4, CH3, CH2, CH1 on
  4-channel DSO models and CH2, CH1 on 2-channel DSO models. MSO/digital OR
  trigger mapping is not implemented. It is hardware-free only so far; no live
  hardware validation has been run.
- Model capability profiles for the runtime-supported feature surface.
  DSO-X 3000X and 4000X profiles enable 50 ohm channel impedance support;
  DSO-X 2000X profiles keep channel impedance guarded to one-meg only.

Core does not own CLI output schema, command-line parser behavior, console
script documentation, or WebUI workflow.

## Docs

- Public import and API integration: `docs/integration.md`
- Supported model profiles and public validation status:
  `docs/supported-models.md`
- Shared CLI, worker, and orchestrator contracts: `../contracts/`



## Force Trigger

The Core runtime exposes a one-shot force-trigger helper:

```python
from scopes_tool_core.trigger import force_trigger_command

force_trigger_command() == ":TRIGger:FORCe"
```

The helper only returns the SCPI command string. It does not open VISA,
does not wait for the instrument, and does not change any acquisition or
trigger configuration. Higher-level force-trigger behavior belongs to the
CLI `force-trigger` command, which sends `:TRIGger:FORCe` and then performs one
`:SYSTem:ERRor?` post-check.

`capture --wait-trigger` uses separate Core trigger-wait helpers. That path is
explicitly opt-in, sends `:SINGle`, polls `:OPERegister:CONDition?`, and may
send `:TRIGger:FORCe` only when the caller requested force-on-timeout. DSO-X
2000X/3000X/4000X waits treat the Operation Status Condition Run bit as
pending when set and complete when clear; other live series remain conservative
until separately validated.
