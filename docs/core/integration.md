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
- `plan_acquisition_check`
- `run_capture`
- `run_doctor`
- `run_measure_log`
- `run_measure`
- `run_measure_sweep`
- `run_smoke`
- `run_acquisition_check`

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

For 4000X Screenshot Format Pack v1 capture and hardcopy state queries:

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

System/Status Pack v1 is available through `Oscilloscope.clear_status()`,
`query_operation_complete()`, `query_status_byte()`,
`query_standard_event_status()`, `query_operation_status()`, and
`query_system_options()`. These methods do not require an IDN or capability
profile. `query_standard_event_status()` performs the destructive `*ESR?`
event-register read. `query_operation_status()` uses
`:OPERegister:CONDition?`; it does not introduce the intentionally unsupported
`:RSTate?` query. Existing `query_system_error()` and `drain_system_errors()`
remain the APIs for `:SYSTem:ERRor?`.

Save/Export Pack v1 is available through the focused
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

Serial support is delivered in five focused surfaces:

- P0 provides basic bus mode and display controls through
  `Oscilloscope.query_serial()`, `configure_serial_mode()`,
  `query_serial_mode()`, `configure_serial_display()`, and
  `query_serial_display()`. Aggregate `:SBUS<n>?` results preserve the
  trimmed subsystem response without parsing it. Mode and display writes send
  only their target commands.
- Serial UART Trigger P0 provides `SerialUartTriggerState` through
  `Oscilloscope.configure_serial_uart_trigger()` and
  `Oscilloscope.query_serial_uart_trigger()`. The target UART bus must first
  be configured through Serial P1. Configure writes UART trigger criteria and
  selects the matching global `SBUS<n>` Trigger Mode last; it does not modify
  UART decode settings or perform acquisition. P0 excludes burst, idle time,
  9-bit, pattern-sequence, and other protocol triggers. The canonical public
  choices are `UART_TRIGGER_TYPES` and `UART_TRIGGER_QUALIFIERS`.
- Serial Trigger P1 provides `SerialI2CTriggerState`,
  `SerialSpiTriggerState`, and `SerialCanTriggerState` through
  `Oscilloscope.configure_serial_i2c_trigger()`,
  `query_serial_i2c_trigger()`, `configure_serial_spi_trigger()`,
  `query_serial_spi_trigger()`, `configure_serial_can_trigger()`, and
  `query_serial_can_trigger()`. These commands require the matching Serial P1
  Bus configuration, write protocol criteria before selecting the matching
  global `SBUS<n>` Trigger Mode, preserve raw readbacks, and do not modify
  decode settings or run acquisition. They expose only the documented common
  I2C/SPI/CAN trigger subset; canonical choices are exposed through
  `I2C_TRIGGER_TYPES`, `I2C_TRIGGER_QUALIFIERS`, `SPI_TRIGGER_TYPES`,
  `CAN_TRIGGER_TYPES`, and `CAN_TRIGGER_ID_MODES`.
- P1 provides UART, I2C, SPI, and CAN decode configuration through the
  protocol-specific configure/query methods. Configure methods set the
  selected mode first and then write supplied fields in controller-defined
  order. Query methods preserve raw readbacks alongside canonical values. P1
  does not include Search, serial trigger, Lister, export, or advanced
  protocol settings.
- P2 provides Serial Lister display/reference query and configuration plus
  host-side raw CSV export through `:LISTer:DATA?`. It does not acquire
  traffic, enable decode, or parse protocol-specific CSV rows.
- P3 provides UART, I2C, SPI, and CAN Serial Search configure/query controls.
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
  P3 does not support LIN, advanced protocols, symbolic CAN, or Search export.

Serial decode may require an instrument license. Core does not probe licenses;
an unavailable option remains a normal instrument error through the existing
SCPI error path.
