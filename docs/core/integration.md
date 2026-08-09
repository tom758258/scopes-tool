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
- `plan_acquisition_check`
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
- `interruptible_wait`
- `load_sequence_document`
- `normalize_sequence_document`
- `TriggeredMeasureLoopRequest`

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
and `system_error`. These are operation-specific payloads; Core does not define
a universal sample contract. Callbacks are synchronous, run only after the
corresponding completed data is persisted, and propagate exceptions unchanged.

Finite workflow termination uses `instrument_error > completed > cancelled`.
Once a count or duration completion condition is satisfied, a later observed
stop request does not replace the completed result. Cancellation is reported
only when finite work remains.

Workflow `scpi.log` ownership begins and ends with the Core operation. SCPI
activity from adapter-level resource opening, live identity validation, driver
selection, or other preflight before the operation is not guaranteed to be
present. Consumers must not treat this artifact as a complete process or
session trace or add a parallel adapter logging lifecycle.

Generic Sequence v1 uses `load_sequence_document()`, `plan_sequence()`, and
`run_sequence()`. Planning validates all steps against one capability profile
without opening hardware or writing artifacts. Runtime validation uses the
detected model before creating the run directory. `run_sequence()` accepts the
same optional stop and progress callbacks as the Workflow Foundation; it does
not define a sequence-specific progress or sample type. Public document,
action, result, and artifact behavior is documented in `sequence.md` and
`sequence.zh-TW.md`.

Triggered Measurement Loop v1 uses `TriggeredMeasureLoopRequest`,
`plan_triggered_measure_loop()`, and `run_triggered_measure_loop()`. Planning
validates measurement selection and one representative cycle without opening
hardware or writing artifacts. Runtime owns the finite acquisition loop and
accepts the Workflow Foundation stop, progress, and operation-specific sample
callbacks. Public behavior is documented in `triggered-measure-loop.md` and
`triggered-measure-loop.zh-TW.md`.

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
