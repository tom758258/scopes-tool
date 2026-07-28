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
- `SearchModeState`
- `SearchState`
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
