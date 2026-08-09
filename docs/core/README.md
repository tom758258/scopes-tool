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
- Finite workflow execution helpers for cooperative cancellation,
  interruptible waits, synchronous progress reporting, and operation-specific
  sample reporting. Core owns workflow execution; CLI and Worker are adapters.
- Instrument-side Math waveform display and vertical controls through
  `Oscilloscope.configure_math_display()`, `query_math_display()`,
  `configure_math_vertical()`, and `query_math_vertical()`. The controls use
  the single unindexed `:FUNCtion` subsystem on 2000X/3000X and indexed slots
  1 through 4 on 4000X. Vertical configuration supports scale or range plus an
  optional offset and does not automatically enable display or run autoscale.
  Instrument firmware may recalculate vertical scaling when Math display
  changes from OFF to ON, so callers that need explicit vertical settings
  should enable display before applying scale, range, or offset. Math operation
  selection, sources, host-side Math, license probing, and slot coordination
  are not provided by this surface.
- Instrument-side dual-source Math operators through
  `Oscilloscope.configure_math_operator()` and `query_math_operator()`. This
  surface supports `add`, `subtract`, `multiply`, and `divide` with two
  analog-channel
  sources. Both source1 and source2 remain analog-channel-only on every series.
  It reuses the single unindexed 2000X/3000X Math function and indexed 4000X
  slots, preserves normalized and raw query values, and does not enable display
  or change vertical controls. Reference, Math, bus, digital, external, and
  arbitrary-expression sources are not supported. Capability profiles describe
  the available runtime path and do not detect instrument licenses.
- Instrument-side single-source Math transforms through
  `Oscilloscope.configure_math_transform()` and `query_math_transform()`. This
  supports `differentiate`, `integrate`, `sqrt`, `absolute`, `square`, `ln`,
  `log10`, `exp`, `exp10`, and `linear` with one source.
  Integrate optionally sets input offset; linear optionally sets gain and
  linear offset. It reuses the unindexed 2000X/3000X function and indexed
  4000X slots, does not enable display, and leaves license availability to the
  instrument error queue. The 2000X/3000X path also permits the `composite`
  GOFT source, and the 4000X path permits a lower-numbered Math function
  source. Reference and bus sources, host-side calculation, and waveform export
  are not supported.
- Instrument-side Math composite and cascade source configuration through
  `Oscilloscope.configure_math_composite_source()` and
  `query_math_composite_source()`. The 2000X/3000X path supports `add`,
  `subtract`, or `multiply` over two analog channels and can feed that result
  to `math-transform` as `composite`. The 4000X path instead supports Math
  cascade by allowing only a lower-numbered Math function as the
  `math-transform` source. `math-operator` remains analog-channel-only.
  These controls do not calculate or export waveform data, enable display,
  change vertical settings, or probe licenses.
- Instrument-side Math filters through
  `Oscilloscope.configure_math_filter()`, `query_math_filter()`, and
  `clear_math()`. All registered series support `low-pass` and `high-pass`;
  4000X additionally supports `average`, `smooth`, and `envelope`. Filter
  sources reuse the single-source rules: analog channels on all series,
  `composite` on 2000X/3000X, and a lower-numbered Math function on 4000X.
  Cutoff, average-count, and smooth-point writes are optional and
  operation-specific. Math clear is available only on profiles that support
  average and uses indexed 4000X `:FUNCtion<n>:CLEar`. These controls do not
  calculate waveforms, enable display, change vertical or acquisition state,
  probe licenses, or wait for completion.
- Instrument-side Math visualizations through
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
  state, or probe licenses.
- Instrument-side FFT through
  `Oscilloscope.configure_fft()` and `query_fft()`. The 2000X/3000X profiles
  retain basic magnitude FFT with the unindexed Math function. The 4000X
  profile adds indexed FFT Phase, start/stop frequency, Main/Zoom gating,
  phase reference, detector type and point controls, plus read-only bin size,
  FFT sample rate, and resolution bandwidth. Center/span and start/stop are
  alternate displayed-range controls and cannot be mixed. Phase reference is
  valid only for FFT Phase and is queried only when the current operation is
  FFT Phase. These controls do not calculate FFT data on the host, enable Math
  display, configure Zoom or timebase, run autoscale, or change acquisition
  state.
- Math is instrument-side only. Bus timing and bus state are not supported
  because the required MSO/digital-channel foundation is not available; no
  capability operation, CLI choice, Worker command, Core builder, or simulator
  behavior is provided for them.
- System and status helpers for `*CLS`, `*OPC?`, `*STB?`, destructive
  `*ESR?`, `:OPERegister:CONDition?`, and `*OPT?`. Parsers preserve raw
  responses, expose bounded integer register values and stable set-bit indexes,
  and preserve trimmed option tokens including a raw no-option-style `0`.
  `:RSTate?`, service-request or event-enable writes, UI locking, return to
  local, date/time, and a replacement for the existing
  system-error helpers are not supported. Core does not add WebUI runtime
  behavior.
- Conservative `minimal` and `safe` cleanup profiles compose existing status,
  display, DVM, search, annotation, and Demo helpers. Unsupported steps are
  reported instead of adding new subsystems; cleanup never performs reset,
  preset, autoscale, or broad state restoration.
- Instrument-side image and waveform save helpers for common
  2000X/3000X/4000X behavior. This surface configures the current save
  directory, base filename, image format/palette/ink-saver/factors, and
  waveform format/length; it can then start an image or waveform save with an
  explicit filename and wait with `*OPC?`. It does not retrieve bytes or create
  host-side files. Existing capture and screenshot APIs remain PC-side
  workflows. Image and waveform format queries normalize the read-only `NONE`
  sentinel to canonical `none`; `none` is not a settable format. Results,
  lister, mask, multi, power, arbitrary, compliance, setup, and WMEMory export
  are not supported. Query and configuration of segmented memory, together
  with the finite `segmented-capture` workflow, are documented separately.
- Serial Lister global display/reference query and configuration plus
  host-side raw CSV export through `:LISTer:DATA?`. The export preserves the
  instrument payload without protocol-specific parsing and does not enable
  decode, acquire traffic, or change SBUS display state. Lister display
  selection uses `off`, `bus1`, `bus2`, and `all`; `bus2` is unavailable on
  2000X and available on 3000X/4000X profiles.
- Serial trigger support provides common I2C, SPI, and CAN trigger criteria through
  Core, CLI, Worker, and Simulator paths. The matching Serial bus must be
  configured first; trigger configure selects the corresponding `SBUS<n>`
  Trigger Mode last and does not change decode settings or acquire data.
- Measurement control helpers for clearing screen measurements,
  enabling or querying measurement markers, selecting one or two analog
  measurement source channels, and selecting `MAIN`, `ZOOM`, `AUTO`, or
  `GATE` measurement windows. Marker OFF is not exposed.
  A source1-only write sets source1 but may preserve an existing source2
  selection in instrument readback; callers that require an explicit
  two-source default should set both sources. `ZOOM` is conditional on the
  zoomed timebase already being displayed. DSO-X 4034A firmware 07.20 may
  return `-221,"Settings conflict"` otherwise, so `AUTO` is safer when zoom
  state is unknown.
- DVM helpers for enabling DVM, selecting one analog source,
  selecting `dc`, `dc-rms`, or `ac-rms` voltage mode, controlling auto range,
  reading current voltage, and querying aggregate state. DVM availability may
  depend on an instrument option or license. `:DVM:FREQuency`, DVM frequency
  mode, the independent `:COUNter` subsystem, and `:MEASure:COUNter` are not
  supported.
- Demo output helpers for querying aggregate built-in DEMO state and
  configuring or querying DEMO output, function, and phase. Function sets are
  capability-profile guarded; unknown function readbacks remain available as
  raw values. DEMO is option-/hardware-dependent, so unsupported live
  instruments may report normal instrument errors. It remains separate from
  WGEN, excludes additional 4000X-only DEMO functions, and adds no WebUI
  runtime behavior.
- Waveform generator helpers for output, function, frequency, peak-to-peak
  amplitude, offset, load, and aggregate queries. The 2000X and 3000X use the
  unindexed `:WGEN` subsystem; the 4000X uses generator 1 through `:WGEN1`.
  Settable functions are limited to `sine`, `square`, `ramp`, `pulse`, `noise`,
  and `dc`. Software safety guards require positive finite frequency,
  `0 < amplitude <= 5.0` volts, and `-2.5 <= offset <= 2.5` volts.
- Waveform search helpers for enabling or disabling waveform search,
  selecting a model-profile-supported basic search mode, and querying the
  search event count. Mode configuration enables search before setting the
  mode. DSO-X 2000X supports `serial1`; 3000X supports `edge`, `glitch`,
  `runt`, `transition`, `serial1`, and `serial2`; 4000X additionally supports
  `peak`. Serial Search adds model-guarded serial search controls for UART,
  I2C, SPI, and CAN; 2000X exposes bus 1, while 3000X and 4000X expose buses 1
  and 2. Configure the matching Serial bus before using Serial Search.
- Reference waveform helpers for saving an analog channel to reference
  slot 1 or 2, configuring or querying display and label state, clearing a
  slot, and querying aggregate display/label state. Labels are limited to
  1-10 printable ASCII characters without double quotes. File-based reference
  save/recall and reference scale, skew, offset, and range controls are not
  supported. Enabling one
  reference slot for display may turn off the other slot; this is normal
  instrument-managed display behavior, not a command failure.
- Read-only analog acquisition sample rate query helpers.
- Screenshot format helpers for 4000X screen-dump PNG, BMP, and
  8-bit BMP capture plus hardcopy ink saver, palette, layout, and aggregate
  state queries. Existing cross-series color PNG capture remains unchanged.
- Read-only acquisition points and record-length query helpers, separate from
  waveform transfer points.
- Segmented-memory query and explicit configuration through
  `Oscilloscope.query_segmented_memory()`,
  `Oscilloscope.enable_segmented_memory()`, and
  `Oscilloscope.disable_segmented_memory()`. Configuration selects segmented
  mode and an explicit count without starting acquisition. The finite
  single-channel `segmented-capture` workflow starts one acquisition, waits for
  two consecutive RUN-clear and remote-interface-enabled operation-condition
  samples, queries the acquired count once, and writes one host CSV per exported
  segment plus a shared manifest and SCPI log. Counts are limited to 2-250 on
  2000X and 2-1000 on 3000X/4000X; actual instrument limits may be lower for a
  selected memory
  depth. Average acquisition must be changed to a non-average type by the
  caller before enabling segmented memory. Capture does not restore state,
  disable segmented mode, force a trigger, merge CSVs, or perform
  instrument-side save/export. Availability may depend on an SGM option or
  license; capability support does not claim that the option is installed.
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
  `Oscilloscope.query_trigger_edge_source()`. This API uses only
  `:TRIGger:EDGE:SOURce` and configures analog channels, External, or AC Line
  sources without changing trigger mode, level, slope, coupling, reject, or
  acquisition state. The common DSO-X 2000X/3000X/4000X target models support
  `CHANnel<n>`, `EXTernal`, and `LINE`; analog channels are validated against
  the selected model profile. Query parsing preserves the stripped raw source
  and tolerates unsupported, digital, WaveGen, `NONE`, and unknown readbacks by
  returning no normalized source. WGEN/WMOD/digital source configuration is not
  supported.
- Edge Trigger slope and analog level helpers exposed through
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
  DSOX2004A, DSOX3024A, DSOX4024A, and DSOX4034A model coverage is supported.
  Line, WaveGen, WMOD, and digital/MSO level controls are not supported.
- External Trigger range and External Edge level helpers exposed
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
  rejection. Line, WaveGen, WMOD, and digital/MSO External-level variants
  remain out of scope.
- External Trigger input settings helpers exposed through
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
  range, and External Edge level independently.
- Common trigger general setting helpers exposed through
  `Oscilloscope.configure_trigger_sweep()`,
  `Oscilloscope.query_trigger_sweep()`,
  `Oscilloscope.configure_trigger_noise_reject()`,
  `Oscilloscope.query_trigger_noise_reject()`,
  `Oscilloscope.configure_trigger_hf_reject()`, and
  `Oscilloscope.query_trigger_hf_reject()`. This `trigger-sweep`,
  `trigger-noise-reject`, and `trigger-hf-reject` commands use only
  `:TRIGger:SWEep`, `:TRIGger:NREJect`, and `:TRIGger:HFReject`. Query mode
  preserves raw readbacks while normalizing sweep to `auto` or `normal` and
  the common reject settings to booleans.

- Edge Trigger coupling and reject filter helpers exposed through
  `Oscilloscope.configure_trigger_edge_coupling()`,
  `Oscilloscope.query_trigger_edge_coupling()`,
  `Oscilloscope.configure_trigger_edge_reject()`, and
  `Oscilloscope.query_trigger_edge_reject()`. These commands use only
  `:TRIGger:EDGE:COUPling` and `:TRIGger:EDGE:REJect`. Each command
  configures or queries its own SCPI setting independently. Query mode
  preserves raw readbacks while normalizing coupling to `ac`, `dc`, or
  `lf-reject`, and reject to `off`, `lf-reject`, or `hf-reject`. It does not add
  holdoff, generic trigger settings, run, stop, single, force-trigger,
  wait-trigger, or capture.
- Analog-channel pulse-width trigger helpers for the Keysight
  `:TRIGger:GLITch...` command family. These helpers configure and query
  pulse-width trigger state only; it does not run, stop, single, force trigger,
  wait for trigger, or capture waveform data.
- Analog-channel runt trigger helpers for the Keysight `:TRIGger:RUNT...` and
  shared `:TRIGger:LEVel:LOW/HIGH` command families. These helpers configure and
  queries runt trigger state only; it does not run, stop, single, force
  trigger, wait for trigger, or capture waveform data.
- Analog-channel transition trigger helpers for the Keysight
  `:TRIGger:TRANsition...` and shared `:TRIGger:LEVel:LOW/HIGH` command
  families. These helpers configure and query transition trigger state only;
  it does not run, stop, single, force trigger, wait for trigger, or capture
  waveform data.
- DSO analog-channel Edge Then Edge / Delay trigger helpers for the Keysight
  `:TRIGger:DELay...` command family. These `trigger-delay` helpers
  configure analog arm and trigger source channels, positive/negative arm and
  trigger slopes, delay time, and Nth trigger edge count. Query mode preserves
  raw readbacks and tolerates digital or unknown source state. It does not add
  run, stop, single, force trigger, wait-trigger, or capture.
- DSO analog-channel setup-hold trigger helpers for the Keysight
  `:TRIGger:SHOLd...` command family. These `trigger-setup-hold` helpers
  configure analog clock and data source channels, positive/negative clock
  slope, setup time, and hold time. Query mode preserves raw readbacks and
  tolerates digital or unknown source state, but configure mode intentionally
  rejects MSO/digital, external, and unknown sources. MSO/digital
  configuration, signal-trigger behavior, and broader trigger-tree behavior
  are not supported by this surface.
- DSO analog-channel Nth Edge Burst trigger helpers for the Keysight
  `:TRIGger:EBURst...` command family. These `trigger-edge-burst` helpers
  configures `:TRIGger:MODE EBURst`, analog source channel, positive/negative
  slope, edge count, idle time, and optional source-qualified analog
  `:TRIGger:EDGE:LEVel`. Query mode preserves raw source readbacks and
  tolerates digital, `NONE`, or unknown source state without querying analog
  level unless the source safely parses as analog. MSO/digital configuration,
  signal-trigger behavior, and broader trigger-tree behavior are not supported
  by this surface.
- DSO analog-channel basic TV / video trigger helpers for the Keysight
  `:TRIGger:TV...` command family. These `trigger-tv` helpers configure
  `:TRIGger:MODE TV`, analog source channel, basic standard
  `ntsc`/`pal`/`palm`/`secam`, basic TV mode, optional line number for line
  modes, and positive/negative polarity. Query mode preserves raw readbacks and
  tolerates digital, external, extended-standard, `LINE` mode, or unknown TV
  subtree states without crashing. It does not add extended video/UDTV,
  MSO/digital or external source configuration, signal-trigger behavior, run,
  stop, single, wait-trigger, or capture.
- DSO analog ASCII pattern trigger helpers for the Keysight
  `:TRIGger:PATTern...` command family. These helpers configure
  `:TRIGger:MODE PATTern`, `:TRIGger:PATTern:FORMat ASCii`, raw `0/1/X`
  patterns, and `:TRIGger:PATTern:QUALifier ENTered`; query mode preserves
  raw pattern, edge source, and edge readbacks.
- DSO analog-only OR trigger helpers for the Keysight `:TRIGger:OR` command
  family. These helpers configure `:TRIGger:MODE OR` and raw `R/F/E/X` edge
  masks, and queries `:TRIGger:MODE?` plus `:TRIGger:OR?`. Pattern order
  follows Keysight OR trigger bit assignment: CH4, CH3, CH2, CH1 on
  4-channel DSO models and CH2, CH1 on 2-channel DSO models. MSO/digital OR
  trigger mapping is not supported.
- Model capability profiles for the runtime-supported feature surface.
  DSO-X 3000X and 4000X profiles enable 50 ohm channel impedance support;
  DSO-X 2000X profiles keep channel impedance guarded to one-meg only.

## Workflow Foundation

Workflow Foundation v1 is a small synchronous Core layer used by
`measure-log`, Periodic Capture v1 through `capture-batch`, Triggered
Measurement Loop v1, Triggered Capture Series v1, and Generic Sequence v1.
`StopRequested`, `WorkflowProgress`,
`ProgressReporter`, and `interruptible_wait()` provide optional cooperative
cancellation and progress without an async runtime, scheduler, persistence
layer, or event bus. A long interval wait checks cancellation periodically;
an active VISA query is never forcibly interrupted.

`run_measure_log()` and `run_capture_batch()` accept optional stop, progress,
and operation-specific sample callbacks. Measure-log checks cancellation
between completed measurement queries and discards an uncommitted partial row.
Capture-batch retains completed CSV and metadata artifacts and does not begin a
new capture after cancellation. Reporter callbacks run synchronously after the
corresponding data is persisted. Reporter exceptions are not suppressed and
remain the caller's responsibility.

Periodic Capture v1 is the product-facing name for the existing
`capture-batch` command, `CaptureBatchRequest`, and `run_capture_batch()` Core
operation. It keeps the existing finite, completion-relative interval model
and artifacts. See [Periodic Capture v1](periodic-capture.md) and
[繁體中文](periodic-capture.zh-TW.md).

Triggered Measurement Loop v1 owns a finite `Single` -> trigger wait ->
measurement loop. It preserves completed cycles, stores invalid measurement
sentinels as `NaN`, and fails immediately on trigger timeout or genuine query,
transport, parsing, or system errors. See [Triggered Measurement Loop
v1](triggered-measure-loop.md) and [繁體中文](triggered-measure-loop.zh-TW.md).

Triggered Capture Series v1 owns a finite `Single` -> trigger wait -> waveform
capture loop. It uses the oscilloscope's existing trigger configuration,
commits a cycle only after waveform artifacts, the system-error check, and the
manifest update succeed, and preserves earlier committed cycles. See
[Triggered Capture Series v1](triggered-capture-series.md) and
[繁體中文](triggered-capture-series.zh-TW.md).

Generic Sequence v1 validates a strict JSON document, then runs existing Core
operations in finite loop/step order. It supports `wait`, `single`,
`wait-trigger`, `measure`, `capture`, `screenshot`, and `cleanup`. Trigger wait
does not arm an acquisition; documents use `single` followed by
`wait-trigger` when that flow is required. See [Generic Sequence Workflow
v1](sequence.md) and [繁體中文](sequence.zh-TW.md).

Finite termination precedence is `instrument_error > completed > cancelled`.
Cooperative cancellation returns Core status `cancelled`, a null error, and
exit code 130 only while finite work remains. A stop request observed after the
count or duration completion condition is satisfied does not replace
`completed`. `KeyboardInterrupt` remains `interrupted` with error
`KeyboardInterrupt`.

Workflow `scpi.log` files record SCPI activity produced while the Core
operation is executing. Resource opening, live identity validation, driver
selection, and other CLI or Worker preflight before the Core operation are
outside this boundary and are not guaranteed to appear in the log. The log is
not a complete process or session trace, and adapters do not maintain a
parallel workflow logging lifecycle. Worker job queues, persisted job
lifecycle, and HTTP control remain adapter responsibilities. Core never
imports CLI or WebUI.

Core does not own CLI output schema, command-line parser behavior, console
script documentation, Worker persistence, or WebUI presentation.

## Docs

- Public import and API integration: `docs/integration.md`
- Periodic Capture v1: `periodic-capture.md`, `periodic-capture.zh-TW.md`
- Triggered Measurement Loop v1: `triggered-measure-loop.md`,
  `triggered-measure-loop.zh-TW.md`
- Triggered Capture Series v1: `triggered-capture-series.md`,
  `triggered-capture-series.zh-TW.md`
- Generic Sequence v1: `sequence.md`, `sequence.zh-TW.md`
- Supported model profiles: `supported-models.md`
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
indicating acquisition in progress when set and completion when clear; an
unclassified operation-condition state on other series does not authorize
waveform capture.
