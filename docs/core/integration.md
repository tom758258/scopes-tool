# Core Integration

Import the Core runtime with:

```python
import scopes_tool_core
```

The public import surface is defined by `scopes_tool_core.__all__`. These
names are intended for package consumers and tests:

- `ChannelController`
- `DisplayController`
- `AnnotationState`
- `DisplayPersistence`
- `DVM_MODES`
- `DvmAutoRangeState`
- `DvmBooleanState`
- `DvmController`
- `DvmModeState`
- `DvmReading`
- `DvmSourceState`
- `DvmState`
- `DEMO_FUNCTIONS`
- `DEMO_FUNCTION_TOKENS`
- `DemoController`
- `DemoFunctionState`
- `DemoOutputState`
- `DemoPhaseState`
- `DemoState`
- `DelayTriggerController`
- `DelayTriggerState`
- `EdgeBurstTriggerController`
- `EdgeBurstTriggerState`
- `EdgeTriggerController`
- `EdgeTriggerState`
- `EdgeTriggerExternalLevelController`
- `EdgeTriggerExternalLevelState`
- `EdgeTriggerSourceController`
- `EdgeTriggerSourceState`
- `GlitchTriggerController`
- `EdgeTriggerCouplingController`
- `EdgeTriggerCouplingState`
- `EdgeTriggerLevelController`
- `EdgeTriggerLevelState`
- `EdgeTriggerRejectController`
- `EdgeTriggerRejectState`
- `EdgeTriggerSlopeController`
- `EdgeTriggerSlopeState`
- `ExternalTriggerRangeController`
- `ExternalTriggerRangeState`
- `ExternalTriggerProbeController`
- `ExternalTriggerProbeState`
- `ExternalTriggerSettingsController`
- `ExternalTriggerSettingsState`
- `ExternalTriggerUnitsController`
- `ExternalTriggerUnitsState`
- `GlitchTriggerState`
- `OrTriggerController`
- `OrTriggerState`
- `PatternTriggerController`
- `PatternTriggerState`
- `RuntTriggerController`
- `RuntTriggerState`
- `SetupHoldTriggerController`
- `SetupHoldTriggerState`
- `TransitionTriggerController`
- `TransitionTriggerState`
- `TriggerHfRejectController`
- `TriggerNoiseRejectController`
- `TriggerRejectState`
- `TriggerSweepController`
- `TriggerSweepState`
- `IDN`
- `PHYSICAL_MODEL_REGISTRY`
- `VENDOR_REGISTRY`
- `PhysicalModelInfo`
- `VendorInfo`
- `Oscilloscope`
- `SegmentedMemoryController`
- `SegmentedMemoryQueryResult`
- `MeasurementController`
- `MeasurementResult`
- `MeasurementShowState`
- `MeasurementSourceState`
- `MeasurementWindowState`
- `ReferenceWaveformController`
- `ReferenceWaveformState`
- `SAVE_IMAGE_FORMATS`
- `SAVE_IMAGE_PALETTES`
- `SAVE_WAVEFORM_FORMATS`
- `SaveBooleanState`
- `SaveExportController`
- `SaveFilenameState`
- `SaveImageFormatState`
- `SaveImagePaletteState`
- `SaveOperationResult`
- `SavePwdState`
- `SaveWaveformFormatState`
- `SaveWaveformLengthState`
- `SEARCH_MODES`
- `SearchController`
- `SearchCountState`
- `SearchEventState`
- `SearchModeState`
- `SearchState`
- `SerialSearchUartState`
- `SerialSearchI2CState`
- `SerialSearchSpiState`
- `SerialSearchCanState`
- `UART_SEARCH_MODES`
- `I2C_SEARCH_MODES`
- `SPI_SEARCH_MODES`
- `CAN_SEARCH_MODES`
- `CAN_SEARCH_ID_MODES`
- `SEARCH_QUALIFIERS`
- `SERIAL_MODES`
- `CAN_SIGNAL_DEFINITIONS`
- `I2C_ADDRESS_SIZES`
- `SERIAL_BIT_ORDERS`
- `SPI_CLOCK_SLOPES`
- `SPI_FRAMINGS`
- `UART_PARITIES`
- `UART_POLARITIES`
- `SerialController`
- `SerialDisplayState`
- `SerialCanState`
- `SerialI2CState`
- `SerialModeState`
- `SerialQueryState`
- `SerialSpiState`
- `SerialUartState`
- `MultiChannelWaveformCapture`
- `OperationCompleteState`
- `OperationPlan`
- `OperationResult`
- `ResolvedRunConfig`
- `RunModeOptions`
- `CaptureBatchRequest`
- `CaptureUntilRequest`
- `CaptureMonitorRequest`
- `CaptureRequest`
- `MeasureLogRequest`
- `MeasureRequest`
- `MeasureSweepRequest`
- `SmokeRequest`
- `AcquisitionCheckRequest`
- `HardcopyState`
- `ScreenshotCapture`
- `ScreenshotController`
- `ScreenshotOptions`
- `SequenceDocument`
- `SequenceRequest`
- `SequenceStep`
- `ScopeCapabilities`
- `SystemErrorEntry`
- `StatusController`
- `StatusRegisterState`
- `SystemOptionsState`
- `TimebaseController`
- `WGEN_FUNCTIONS`
- `WGEN_FUNCTION_TOKENS`
- `WGEN_LOADS`
- `WGEN_LOAD_TOKENS`
- `WgenController`
- `WgenFrequencyState`
- `WgenFunctionState`
- `WgenLoadState`
- `WgenOffsetState`
- `WgenOutputState`
- `WgenState`
- `WgenVoltageState`
- `TriggerWaitConfig`
- `TriggerWaitResult`
- `TvTriggerController`
- `TvTriggerState`
- `WaveformCapture`
- `WaveformPreamble`
- `ProgressReporter`
- `StopRequested`
- `WorkflowProgress`
- `capabilities_for_model`
- `capabilities_for_model_id`
- `canonical_physical_model_id`
- `physical_model_for_id`
- `detect_series`
- `parse_channel_display`
- `parse_channel_coupling`
- `parse_channel_impedance`
- `parse_channel_units`
- `parse_display_label`
- `parse_idn`
- `parse_operation_complete`
- `parse_status_register`
- `parse_system_error`
- `parse_system_options`
- `resolve_run_mode`
- `resolve_physical_model_identity`
- `resolve_resource`
- `require_resource`
- `open_scope_for_run`
- `plan_capture`
- `plan_doctor`
- `plan_measure`
- `plan_measure_sweep`
- `plan_smoke`
- `plan_sequence`
- `plan_triggered_measure_loop`
- `plan_triggered_capture_series`
- `plan_measure_until`
- `plan_capture_until`
- `plan_capture_monitor`
- `plan_acquisition_check`
- `query_instrument_summary`
- `run_capture`
- `run_capture_batch`
- `run_doctor`
- `run_measure_log`
- `run_measure`
- `run_measure_sweep`
- `run_smoke`
- `run_acquisition_check`
- `run_sequence`
- `run_triggered_measure_loop`
- `run_triggered_capture_series`
- `run_measure_until`
- `run_capture_until`
- `run_capture_monitor`
- `interruptible_wait`
- `load_sequence_document`
- `normalize_sequence_document`
- `SEQUENCE_ACTIONS`
- `SEQUENCE_MAX_ARTIFACT_STEPS`
- `SEQUENCE_MAX_LOOPS`
- `SEQUENCE_MAX_STEPS`
- `SEQUENCE_MAX_TOTAL_STEP_EXECUTIONS`
- `TriggeredMeasureLoopRequest`
- `TriggeredCaptureSeriesRequest`
- `MeasureUntilRequest`

## Runtime Guidance

Use `resolve_run_mode`, `resolve_resource`, `require_resource`, and
`open_scope_for_run` to centralize live, simulated, and dry-run behavior.
Operation planning helpers return planned SCPI and artifact paths without
opening VISA. Operation runners execute against the selected backend.

Dry-run and simulator configuration uses a planning canonical physical model
ID. Live configuration keeps any expected canonical physical model ID separate
from the identity detected through `*IDN?`; the expected identity never
replaces the detected identity or its capability profile.

Core should remain independent from command-line parser types and WebUI
controller concepts. Package adapters may call Core, but Core should not import
from adapter packages.

Workflow consumers may pass optional callbacks to `run_measure_log()` and
`run_capture_batch()`:

```python
from scopes_tool_core import WorkflowProgress, run_capture_batch

def report_progress(progress: WorkflowProgress) -> None:
    print(progress.completed_count, progress.total_count)

result = run_capture_batch(
    scope,
    resource,
    request,
    stop_requested=lambda: stop_event.is_set(),
    progress_reporter=report_progress,
    sample_reporter=lambda capture: consume_capture(capture),
)
```

Measure-log samples contain `index`, `timestamp_iso`, `elapsed_seconds`,
`values`, and `system_error`. Capture-batch samples use the compact manifest
capture entry with `index`, relative CSV and metadata paths, `actual_points`,
and `system_error`. Measure-until samples contain `index`, `timestamp_iso`,
`elapsed_seconds`, `value`, `matched`, and `system_error`. These are
operation-specific payloads; Core does not define a universal sample contract.
Callbacks are synchronous, run only after the corresponding completed data is
persisted, and propagate exceptions unchanged.

Finite workflow termination uses `instrument_error > completed > cancelled`.
Once a count, duration, or measurement condition is satisfied, a later
observed stop request does not replace the completed result. Cancellation is
reported only when finite work remains.

Workflow `scpi.log` ownership begins and ends with the Core operation. SCPI
activity from adapter-level resource opening, live identity validation, driver
selection, or other preflight before the operation is not guaranteed to be
present. Consumers must not treat this artifact as a complete process or
session trace or add a parallel adapter logging lifecycle.

## Periodic Capture v1

Periodic Capture is the product-facing name for the existing finite,
time-driven waveform capture operation. It does not introduce a second Core
runtime surface, command, request type, or capture loop:

```text
Periodic Capture
  -> CaptureBatchRequest
  -> run_capture_batch()
```

`CaptureBatchRequest` contains `channels`, `points`, `waveform_format`,
`requested_count`, `interval_seconds`, optional `output_dir`, and `log_scpi`.
`requested_count` must be positive. `interval_seconds` defaults to zero and
must be finite and non-negative. Existing channel, point-count, and BYTE or
WORD validation remains capability-profile dependent.

Each iteration captures the selected waveform data, writes its CSV and
metadata artifacts, records the post-capture system-error result in the
manifest, and then invokes optional sample and progress reporters. The next
relative interval begins only after this persistence and reporting boundary.
Cancellation is cooperative before captures, after persisted captures, and
during interval waits; a blocking VISA or device read is not forcibly
interrupted. A post-capture instrument error stops remaining work, and no
retry is performed. Finite termination precedence is
`instrument_error > completed > cancelled`.

The normal Core artifact set is:

```text
waveform_0001.csv
waveform_0001_meta.json
waveform_0002.csv
waveform_0002_meta.json
...
manifest.json
scpi.log
```

Planning validates the selected model and request without opening VISA or
writing artifacts. It reports one representative capture transaction and the
finite artifact paths. Simulator execution runs the complete finite operation
with the normal hardware-free artifacts.

Periodic Capture does not add duration-based or infinite execution, trigger
waiting, screenshots, measurements, retries, conditions, cleanup, state
restore, absolute scheduling, plots, nested workflows, or Generic Sequence
actions.

## Triggered Measurement Loop v1

Triggered Measurement Loop uses `TriggeredMeasureLoopRequest`,
`plan_triggered_measure_loop()`, and `run_triggered_measure_loop()` for a
finite `Single` -> trigger wait -> measurement loop. It uses the trigger
configuration already present on the oscilloscope.

The request contains `count`, `trigger_timeout_seconds`, optional `channels`,
`items`, `pairs`, and `pair_items`, plus `interval_seconds`, `output_dir`, and
`log_scpi`. Count must be at least one, trigger timeout must be positive and
finite, and interval must be finite and non-negative. Measurement defaults and
selection rules match `measure-log`: omitted channels use the existing default
channel selection, `items` defaults to `vpp,frequency`, `pairs` defaults to
none, and `pair_items` defaults to `phase,delay`. `interval_seconds` defaults
to zero.

Each cycle starts `Single`, waits through the existing Operation Status
Condition Run-bit path, queries the selected measurements, persists the
completed cycle, and then reports progress and the operation-specific sample.
The interval starts after that persistence and reporting boundary. Invalid
measurement sentinels are stored as `NaN` and do not fail the cycle. Query,
transport, parsing, instrument system, and trigger-timeout errors fail fast.
Cancellation is cooperative and does not interrupt a blocking VISA read. A
trigger timeout does not force a trigger, retry, or start another cycle;
completed cycles and their artifacts remain valid.

Runtime artifacts contain `measurements.csv`, `manifest.json`, and `scpi.log`.
The measurement CSV contains `index`, `timestamp_iso`, `elapsed_seconds`,
`trigger_elapsed_seconds`, and the selected measurement columns.
Planning validates the request and one representative cycle without opening
VISA or writing artifacts. The representative plan contains `:SINGle`, one
Operation Status Condition query, selected measurement queries, and one
`:SYSTem:ERRor?`. Simulator mode executes the complete finite workflow.

The workflow does not configure triggers, capture waveforms or screenshots,
run cleanup, force triggers, retry, or expand Generic Sequence v1.

## Triggered Capture Series v1

Triggered Capture Series uses `TriggeredCaptureSeriesRequest`,
`plan_triggered_capture_series()`, and `run_triggered_capture_series()` for a
finite waveform capture series after natural trigger completion. It uses the
existing trigger configuration and does not configure, restore, or force
trigger settings.

The request contains required `channels`, `count`, and
`trigger_timeout_seconds`, plus `points`, `waveform_format`,
`interval_seconds`, `output_dir`, and `log_scpi`. Count must be positive,
trigger timeout must be positive and finite, and interval must be finite and
non-negative. `points` defaults to `1000`, `waveform_format` defaults to the
canonical `byte` value, and `interval_seconds` defaults to zero. The trigger
timeout applies independently to every cycle.

Each cycle performs:

```text
check cancellation
-> :SINGle
-> wait for current trigger/acquisition completion
-> capture waveform channels
-> write waveform CSV and metadata
-> query :SYSTem:ERRor?
-> commit cycle to manifest.json
-> report sample and progress
-> optionally wait interval_seconds
```

A cycle increments the completed count only after natural trigger completion,
successful waveform and metadata writes, a successful system-error check, and
a successful manifest update. Cancellation during trigger polling does not
capture the cycle. A trigger timeout stops without retry or force trigger, and
previously committed cycles remain valid after later failures.

The normal artifact set contains per-cycle waveform CSV and metadata files,
`manifest.json`, and `scpi.log`. Planning validates one representative cycle
without opening VISA or writing artifacts; simulator mode executes the finite
workflow and writes normal artifacts.

The workflow does not add trigger configuration, force trigger, retry,
duration or infinite execution, absolute scheduling, measurements, conditions,
cleanup, screenshots, segmented capture, instrument-side Save/Export, Generic
Sequence actions, or new hardware support.

## Measure Until Condition v1

Measure Until Condition uses `MeasureUntilRequest`,
`plan_measure_until()`, and `run_measure_until()` for a finite, read-only
workflow. It repeatedly queries one existing single-channel measurement until
a numeric condition matches or the workflow timeout expires. It observes the
current acquisition state and does not configure, start, stop, force, or wait
for a trigger.

The request contains required `channel`, `item`, `operator`, `threshold`, and
`timeout_seconds`, plus `interval_seconds`, `output_dir`, and `log_scpi`.
The operator is one of `gt`, `gte`, `lt`, or `lte`; the threshold is finite;
the timeout is positive and finite; and `interval_seconds` defaults to `1.0`
and must be finite and non-negative. No unit conversion is performed.

Each iteration checks cancellation and timeout, queries the measurement,
queries `:SYSTem:ERRor?`, evaluates the condition, persists a CSV row and
manifest update, reports sample and progress, and waits the relative interval
when another sample is allowed. The timeout controls whether another
measurement query may start; a blocking read that started before the deadline
is not forcibly interrupted. After that read returns, Core completes the
system-error check, condition evaluation, and persistence, so a committed
matching sample can still complete successfully. Interval waits are capped by
the remaining timeout. A matching result has Core status `completed` and
termination reason `condition_met`; an unmet finite timeout has Core status
`error` and termination reason `condition_timeout`. Invalid measurement
sentinels are persisted as `NaN` and evaluate as non-matching.

Artifacts contain `measurements.csv`, `manifest.json`, and `scpi.log`; the
manifest stores the request, runtime identity, compact matching summary,
terminal state, paths, and error while measurement values remain in CSV.
The CSV columns are `index`, `timestamp_iso`, `elapsed_seconds`, `value`, and
`matched`.
Planning validates one representative query and system-error iteration without
opening VISA or writing artifacts. Simulator mode executes the finite workflow.

The workflow does not provide multiple conditions, aggregation, parameterized
measurements, equality/tolerance/debounce, retry, trigger or acquisition
control, waveform capture, screenshots, Generic Sequence integration, or
infinite execution.

## Capture Until v1

Capture Until uses `CaptureUntilRequest`, `plan_capture_until()`, and
`run_capture_until()` to retrieve waveforms until it has saved the requested
number of matching acquisitions. The request selects one or more capture
channels and one condition channel that must be among them. The condition is
one metric (`max`, `min`, `peak-to-peak`, or `abs-max`) and one operator (`gt`,
`gte`, `lt`, or `lte`) against a finite threshold. Metrics are computed from
the condition channel's already-retrieved `WaveformCapture.vertical_values`;
the workflow does not issue another waveform query for analysis.

`count` means matching acquisitions, defaults to `1`, and is limited by the
Scopes Tool product contract to `1..255`. It is not a hardware limit. Every
iteration preserves the invariant `capture -> analyze -> persist the same
capture`: a match writes all selected channels from that acquisition through
the normal waveform CSV and metadata writers, while a non-match writes no
waveform or metadata artifact and is not retained as waveform history. Match
files are named `match_001.csv`, `match_001_meta.json`, and so on.

One positive finite timeout controls the entire workflow and is not restarted
after a match. On `condition_timeout`, already completed match artifacts remain,
the result reports the requested and completed matching counts plus the total
waveform capture count, and execution returns non-zero. Cancellation likewise
preserves completed matches. The workflow uses the current waveform retrieval
behavior and does not configure, arm, wait for, or force a trigger.

Planning validates one representative waveform capture and system-error check
without expanding the possible acquisition count. Runtime artifacts also
include `manifest.json` and `scpi.log`. Final results contain compact request,
count, termination, and path metadata only; waveform samples and discarded
evaluation history remain absent.

## Capture Monitor v1

Capture Monitor uses `CaptureMonitorRequest`, `plan_capture_monitor()`, and
`run_capture_monitor()` for a finite repeated waveform capture session. It
supports multiple selected channels, `1000`, `5000`, or `10000` points per
capture, BYTE or WORD transfer, a positive capture count, a finite
non-negative relative interval, and optional result saving. It uses current
waveform retrieval behavior without trigger setup, Single, trigger waiting, or
force trigger.

Retention defaults to `250000` points per channel. It must be at least one
capture and an integer multiple of points per capture. Core keeps a bounded
deque of complete acquisition chunks; overflow drops the oldest complete
chunk. Retention is per channel, so selecting more channels does not divide the
point limit among them. Running maximum, minimum, peak-to-peak, and absolute
maximum statistics cover every observed sample in the session even after old
chunks are dropped. The compact result also reports completed captures and
observed, retained, and dropped points per channel.

Repeated captures are not represented as one continuous time-domain
acquisition. Each chunk keeps its local `time_s`; acquisition and communication
gaps may exist between chunks. Runtime presentation uses an accumulated global
sample index as its main X axis.

Saving is enabled by default. Natural completion writes only the final retained
window to the dedicated `retained_waveforms.csv`, plus `manifest.json` and
`scpi.log`; dropped waveforms are never streamed or reconstructed. CSV rows
include `capture_index`, `global_sample_index`, local `sample_index`, local
`time_s`, and one value column per selected channel. With saving disabled, no
workflow artifacts are created. On cooperative cancellation or
`KeyboardInterrupt`, saving remains enabled only when requested: if at least
one successful capture is retained, the stopped final window is saved while
the workflow remains cancelled or interrupted; cancellation before the first
successful capture creates no empty waveform CSV.

The optional monitor sample callback reports only the newly completed chunk
and compact counters/statistics. It is intended for bounded adapter runtime
presentation and does not add waveform arrays to final Core, CLI, or Worker
results. Planning describes one representative capture and the final retained
artifact shape.

## Generic Sequence v1

Generic Sequence uses `load_sequence_document()`, `plan_sequence()`, and
`run_sequence()` to run existing Core operations in strict finite order. The
Core request is `SequenceRequest`, containing a normalized `SequenceDocument`,
optional `output_dir`, and `log_scpi`.

Sequence documents are strict JSON. `version` must be the JSON integer `1`,
`loop_count` defaults to `1` and must be in `1..255`, and documents must contain
`1..255` steps. Total step executions (`loop_count * step_count`) must not
exceed 65,025. A document may contain at most 10 combined `capture` and
`screenshot` steps per loop; at 255 loops this naturally permits at most 2,550
such executions. These are Scopes Tool product limits, not oscilloscope
hardware limits. Unknown document, step, parameter, and action fields fail
closed. Boolean values are not accepted as integers. Non-standard JSON numbers
such as `NaN` and `Infinity` are rejected. The supported action contract is:

- `wait` requires non-negative finite `seconds`.
- `single` accepts no parameters.
- `wait-trigger` requires positive finite `timeout_seconds` and waits for an
  acquisition already started by `single`; it does not arm or force a trigger.
- `measure` requires `item` and accepts the existing `MeasureRequest` fields
  `channel`, `source_channel`, `reference_channel`, `time_s`, `level`, `slope`,
  and `occurrence`.
- `capture` requires `channels`; `points` defaults to `1000`,
  `waveform_format` to `byte`, and `allow_time_axis_tolerance` to `false`.
- `screenshot` accepts optional `background`, whose current default is `black`
  and whose supported values are `black` and `white`.
- `cleanup` accepts optional `profile`, defaulting to `minimal`; supported
  profiles are `minimal` and `safe`.

Planning validates the complete document against one capability profile without
opening hardware or writing artifacts. Runtime validation uses the detected
model before creating the run directory. Execution is single-threaded and
fail-fast, with no conditions, variables, retries, parallel or nested steps,
arbitrary SCPI, shell execution, or automatic cleanup.

Runtime writes `manifest.json` and `scpi.log`. Capture and screenshot files use
deterministic loop and step paths. The manifest uses independent
`schema_version: 1`, stores normalized input and completed execution records,
and preserves partial artifacts without counting incomplete steps as complete.
Cooperative cancellation is checked at workflow and step boundaries and during
host or trigger waits. Pre-start cancellation occurs before hardware I/O and
run-directory creation, creates no runtime artifacts, and keeps `output_dir`,
`manifest_path`, and `scpi_log_path` null. Reporters run after the completed
step record is persisted; `WorkflowProgress.total_count` is
`loop_count * step_count`.

Planning writes no runtime artifacts and reports normalized steps, loop and
execution counts, artifact templates, and a bounded one-pass SCPI plan.
Simulator mode executes the complete finite document with normal artifacts.

## Adapter Boundary For Core Workflows

CLI, Worker, and WebUI are adapters around these Core workflow requests and
runners. Core does not own adapter parser fields, queue or HTTP lifecycle,
adapter artifact directories, output serialization, or presentation. The
cross-package Worker, orchestrator, and CLI JSONL contracts remain under
`docs/contracts/`.

For 4000X Screenshot capture and hardcopy state queries:

```python
from scopes_tool_core import ScreenshotOptions

capture = scope.capture_screenshot(
    options=ScreenshotOptions(
        format="bmp8bit",
        ink_saver=False,
        palette="grayscale",
        layout="landscape",
    )
)
state = scope.query_hardcopy_state()
```

An explicit format uses `:HCOPY:SDUMp:DATA? PNG|BMP|BMP8bit`. The query state
contains canonical `area`, `ink_saver`, `palette`, `layout`, and `format`
values plus the corresponding raw instrument readbacks. The existing
`capture_screenshot_png(background=...)` API and its
`:DISPlay:DATA? PNG, COLor` behavior remain available for 2000X, 3000X, and
4000X compatibility.

System and status operations are available through `Oscilloscope.clear_status()`,
`query_operation_complete()`, `query_status_byte()`,
`query_standard_event_status()`, `query_operation_status()`, and
`query_system_options()`. These methods do not require an IDN or capability
profile. `query_standard_event_status()` performs the destructive `*ESR?`
event-register read. `query_operation_status()` uses
`:OPERegister:CONDition?`; it does not introduce the intentionally unsupported
`:RSTate?` query. Existing `query_system_error()` and `drain_system_errors()`
remain the APIs for `:SYSTem:ERRor?`.

Save and export operations are available through the
`Oscilloscope.configure_save_*()` and `Oscilloscope.query_save_*()` methods,
plus `save_image(filename)` and `save_waveform(filename)`. These methods send
`:SAVE...` commands so the oscilloscope writes to its current instrument-side
storage location. The start methods require an explicit printable-ASCII
filename, reject unsafe quoted-SCPI characters, and wait with `*OPC?` before
returning `SaveOperationResult`. Image saves temporarily use a bounded 15-second
timeout for that completion query and then restore the prior timeout; waveform
saves retain the current session timeout. They do not create or inspect
host-side files.
`capture_waveform_*()` and screenshot capture remain separate PC-side byte
transfer APIs. The maximum accepted configured save length is model-, option-,
and instrument-state-dependent; Core enforces the common minimum of 100 points
and preserves the raw length readback.

Serial support includes the following surfaces:

- Serial configuration provides basic bus mode and display controls through
  `Oscilloscope.query_serial()`, `configure_serial_mode()`,
  `query_serial_mode()`, `configure_serial_display()`, and
  `query_serial_display()`. Aggregate `:SBUS<n>?` results preserve the
  trimmed subsystem response without parsing it. Mode and display writes send
  only their target commands.
- UART serial trigger provides `SerialUartTriggerState` through
  `Oscilloscope.configure_serial_uart_trigger()` and
  `Oscilloscope.query_serial_uart_trigger()`. The target UART bus must first
  be configured through Serial configuration. Configure writes UART trigger
  criteria and selects the matching global `SBUS<n>` Trigger Mode last; it does
  not modify UART decode settings or perform acquisition. The supported UART
  trigger subset excludes burst, idle time, 9-bit, pattern-sequence, and other
  protocol triggers. The canonical public choices are `UART_TRIGGER_TYPES` and
  `UART_TRIGGER_QUALIFIERS`.
- I2C/SPI/CAN serial trigger provides `SerialI2CTriggerState`,
  `SerialSpiTriggerState`, and `SerialCanTriggerState` through
  `Oscilloscope.configure_serial_i2c_trigger()`,
  `query_serial_i2c_trigger()`, `configure_serial_spi_trigger()`,
  `query_serial_spi_trigger()`, `configure_serial_can_trigger()`, and
  `query_serial_can_trigger()`. These commands require the matching Serial bus
  configuration, write protocol criteria before selecting the matching
  global `SBUS<n>` Trigger Mode, preserve raw readbacks, and do not modify
  decode settings or run acquisition. They expose only the documented common
  I2C/SPI/CAN trigger subset; canonical choices are exposed through
  `I2C_TRIGGER_TYPES`, `I2C_TRIGGER_QUALIFIERS`, `SPI_TRIGGER_TYPES`,
  `CAN_TRIGGER_TYPES`, and `CAN_TRIGGER_ID_MODES`.
- Serial decode configuration provides UART, I2C, SPI, and CAN decode
  configuration through the
  protocol-specific configure/query methods. Configure methods set the
  selected mode first and then write supplied fields in controller-defined
  order. Query methods preserve raw readbacks alongside canonical values. Serial
  decode configuration does not include Search, serial trigger, Lister, export,
  or advanced protocol settings.
- Serial Lister provides display/reference query and configuration plus
  host-side raw CSV export through `:LISTer:DATA?`. It does not acquire
  traffic, enable decode, or parse protocol-specific CSV rows.
- Serial Search provides UART, I2C, SPI, and CAN configure/query controls.
  The matching Serial bus must first be configured with
  `configure_serial_uart()`, `configure_serial_i2c()`,
  `configure_serial_spi()`, or `configure_serial_can()` as appropriate.
  Serial Search does not query, modify, or force validation of the current
  SBUS protocol configuration. Query results preserve canonical values and
  trimmed raw values for both Search state/mode and protocol fields.
  Known 4000X-only I2C/CAN mode readbacks return `mode: null` while preserving
  `raw_mode`; other malformed readbacks raise `SearchResponseError`.
  SPI Search width is measured in bytes; when both `data` and `width` are
  supplied, the hexadecimal/wildcard pattern must contain exactly `width * 2`
  digits. CAN `id-data` searches ID only, while `data` searches ID, Data, and
  DLC. When both CAN `id` and `id-mode` are supplied, standard IDs are limited
  to `0x000` through `0x7FF`, and extended IDs to `0x00000000` through
  `0x1FFFFFFF`.
  Serial Search does not support LIN, advanced protocols, symbolic CAN, or
  Search export.

Serial decode may require an instrument license. Core does not probe licenses;
an unavailable option remains a normal instrument error through the existing
SCPI error path.
