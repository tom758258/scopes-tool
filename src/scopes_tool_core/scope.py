"""High-level oscilloscope object."""

from __future__ import annotations

from typing import Callable, Sequence

from .acquisition import AcquisitionConfig, AcquisitionController
from .cursor import (
    CursorController,
    CursorState,
)
from .fft import (
    FFTController,
    FFTState,
)
from .math import (
    MathController,
    MathCompositeSourceState,
    MathDisplayState,
    MathFilterState,
    MathOperatorState,
    MathTransformState,
    MathVisualizationState,
    MathVerticalState,
)
from .setup import (
    SetupController,
)
from .trigger_holdoff import (
    TriggerHoldoffController,
)
from .capabilities import ScopeCapabilities, capabilities_for_model_id
from .channel import ChannelController, ChannelSummaryEntry
from .cleanup import CleanupResult, execute_cleanup
from .display import AnnotationState, DisplayController, DisplayPersistence
from .dvm import (
    DvmAutoRangeState,
    DvmBooleanState,
    DvmController,
    DvmModeState,
    DvmReading,
    DvmSourceState,
    DvmState,
)
from .demo import (
    DemoController,
    DemoFunctionState,
    DemoOutputState,
    DemoPhaseState,
    DemoState,
)
from .errors import ParameterValidationError, UnsupportedModelError
from .idn import IDN, parse_idn
from .measurements import (
    MeasurementController,
    MeasurementResult,
    MeasurementResultsDump,
    MeasurementShowState,
    MeasurementSourceState,
    MeasurementStatisticsResult,
    MeasurementStatisticsState,
    MeasurementWindowState,
)
from .reference import ReferenceWaveformController, ReferenceWaveformState
from .save_export import (
    SaveBooleanState,
    SaveExportController,
    SaveFilenameState,
    SaveImageFormatState,
    SaveImagePaletteState,
    SaveOperationResult,
    SavePwdState,
    SaveWaveformFormatState,
    SaveWaveformLengthState,
)
from .segmented import SegmentedMemoryController, SegmentedMemoryQueryResult
from .search import (
    SearchController,
    SearchCountState,
    SearchEventState,
    SearchModeState,
    SearchState,
    SerialSearchUartState,
    SerialSearchI2CState,
    SerialSearchSpiState,
    SerialSearchCanState,
)
from .serial import (
    SerialController,
    SerialCanState,
    SerialCanTriggerState,
    SerialDisplayState,
    SerialI2CState,
    SerialI2CTriggerState,
    SerialListerDisplayState,
    SerialListerReferenceState,
    SerialListerState,
    SerialModeState,
    SerialQueryState,
    SerialSpiState,
    SerialSpiTriggerState,
    SerialUartState,
    SerialUartTriggerState,
)
from .scpi import SCPIBackend, SCPIClient
from .screenshot import HardcopyState, ScreenshotCapture, ScreenshotController, ScreenshotOptions
from .status import (
    OperationCompleteState,
    StatusController,
    StatusRegisterState,
    SystemErrorEntry,
    SystemOptionsState,
    parse_system_error,
)
from .timebase import TimebaseController, TimebaseReference
from .wgen import (
    WgenController,
    WgenFrequencyState,
    WgenFunctionState,
    WgenLoadState,
    WgenOffsetState,
    WgenOutputState,
    WgenState,
    WgenVoltageState,
)
from .trigger import (
    DelayTriggerController,
    DelayTriggerState,
    EdgeBurstTriggerController,
    EdgeBurstTriggerState,
    EdgeTriggerController,
    EdgeTriggerCouplingController,
    EdgeTriggerCouplingState,
    EdgeTriggerExternalLevelController,
    EdgeTriggerExternalLevelState,
    EdgeTriggerLevelController,
    EdgeTriggerLevelState,
    EdgeTriggerRejectController,
    EdgeTriggerRejectState,
    EdgeTriggerSlopeController,
    EdgeTriggerSlopeState,
    EdgeTriggerSourceController,
    EdgeTriggerSourceState,
    EdgeTriggerState,
    ExternalTriggerRangeController,
    ExternalTriggerRangeState,
    ExternalTriggerProbeController,
    ExternalTriggerProbeState,
    ExternalTriggerSettingsController,
    ExternalTriggerSettingsState,
    ExternalTriggerUnitsController,
    ExternalTriggerUnitsState,
    GlitchTriggerController,
    GlitchTriggerState,
    OrTriggerController,
    OrTriggerState,
    PatternTriggerController,
    PatternTriggerState,
    RuntTriggerController,
    RuntTriggerState,
    SetupHoldTriggerController,
    SetupHoldTriggerState,
    TransitionTriggerController,
    TransitionTriggerState,
    TriggerHfRejectController,
    TriggerNoiseRejectController,
    TriggerRejectState,
    TriggerSweepController,
    TriggerSweepState,
    TriggerWaitConfig,
    TriggerWaitResult,
    TvTriggerController,
    TvTriggerState,
    force_trigger_command,
    wait_for_trigger_completion,
)
from .visa_backend import VisaBackend
from .waveform import MultiChannelWaveformCapture, WaveformCapture, WaveformController


class Oscilloscope:
    """High-level oscilloscope session wrapper."""

    def __init__(self, backend: SCPIBackend) -> None:
        self.backend = backend
        self.scpi = SCPIClient(backend)
        self.idn: IDN | None = None
        self.capabilities: ScopeCapabilities | None = None
        self._preloaded_idn: IDN | None = None

    @classmethod
    def open(cls, resource_name: str, visa_library: str | None = None) -> "Oscilloscope":
        """Open a PyVISA-backed oscilloscope session."""

        return cls(VisaBackend(resource_name, visa_library=visa_library))

    def query_idn(self) -> IDN:
        """Query, parse, and store `*IDN?` information."""

        if self._preloaded_idn is not None:
            parsed = self._preloaded_idn
            self._preloaded_idn = None
            return parsed

        parsed = parse_idn(self.scpi.query("*IDN?"))
        self.idn = parsed
        try:
            self.capabilities = capabilities_for_model_id(parsed.model_id)
        except UnsupportedModelError:
            self.capabilities = None
        return parsed

    def query_system_error(self) -> SystemErrorEntry:
        """Read one entry from the system error queue.

        This is a destructive queue read on the instrument: the returned entry is
        removed from the oscilloscope's error queue.
        """

        return parse_system_error(self.scpi.query(":SYSTem:ERRor?"))

    def drain_system_errors(self, max_reads: int = 30) -> tuple[SystemErrorEntry, ...]:
        """Read system errors until the queue reports no error or `max_reads` is hit."""

        if max_reads < 1:
            raise ValueError("max_reads must be at least 1.")

        entries = []
        for _ in range(max_reads):
            entry = self.query_system_error()
            entries.append(entry)
            if not entry.is_error:
                break
        return tuple(entries)

    def clear_status(self) -> None:
        """Clear status and event data with `*CLS`."""

        self._status_controller().clear_status()

    def query_operation_complete(self) -> OperationCompleteState:
        """Query successful completion with `*OPC?`."""

        return self._status_controller().query_operation_complete()

    def cleanup(self, profile: str = "minimal") -> CleanupResult:
        """Run one conservative cleanup profile."""

        return execute_cleanup(self, profile)

    def query_status_byte(self) -> StatusRegisterState:
        """Query the status byte with `*STB?`."""

        return self._status_controller().query_status_byte()

    def query_standard_event_status(self) -> StatusRegisterState:
        """Destructively read the standard event status register with `*ESR?`."""

        return self._status_controller().query_standard_event_status()

    def query_operation_status(self) -> StatusRegisterState:
        """Query the operation condition register."""

        return self._status_controller().query_operation_status()

    def query_system_options(self) -> SystemOptionsState:
        """Query installed option tokens with `*OPT?`."""

        return self._status_controller().query_system_options()

    def run(self) -> None:
        """Start repetitive acquisitions."""

        self.scpi.write(":RUN")

    def stop(self) -> None:
        """Stop acquisitions."""

        self.scpi.write(":STOP")

    def single(self) -> None:
        """Start one single acquisition without waiting for completion."""

        self.scpi.write(":SINGle")

    def single_wait(
        self,
        config: TriggerWaitConfig,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> TriggerWaitResult:
        """Start one single acquisition and wait finitely for completion."""

        if getattr(self.backend, "backend", None) == "Keysight simulator":
            classifier_profile = "simulator"
        elif self.capabilities is not None and self.capabilities.series in {
            "2000X",
            "3000X",
            "4000X",
        }:
            classifier_profile = self.capabilities.series.lower()
        else:
            classifier_profile = "live"
        return wait_for_trigger_completion(
            self.scpi,
            config,
            classifier_profile=classifier_profile,
            stop_requested=stop_requested,
        )

    def force_trigger(self) -> None:
        """Force one trigger event without waiting for the configured trigger condition."""

        self.scpi.write(force_trigger_command())

    def set_channel_display(self, channel: int, enabled: bool) -> None:
        """Turn one analog channel display on or off."""

        self._channel_controller().set_display(channel, enabled)

    def query_channel_display(self, channel: int) -> bool:
        """Query whether one analog channel display is enabled."""

        return self._channel_controller().query_display(channel)

    def set_channel_scale(self, channel: int, volts_per_division: float) -> None:
        """Set one analog channel vertical scale in volts per division."""

        self._channel_controller().set_scale(channel, volts_per_division)

    def query_channel_scale(self, channel: int) -> float:
        """Query one analog channel vertical scale in volts per division."""

        return self._channel_controller().query_scale(channel)

    def set_channel_offset(self, channel: int, volts: float) -> None:
        """Set one analog channel vertical offset in volts."""

        self._channel_controller().set_offset(channel, volts)

    def query_channel_offset(self, channel: int) -> float:
        """Query one analog channel vertical offset in volts."""

        return self._channel_controller().query_offset(channel)

    def set_channel_coupling(self, channel: int, coupling: str) -> None:
        """Set one analog channel input coupling."""

        self._channel_controller().set_coupling(channel, coupling)

    def query_channel_coupling(self, channel: int) -> str:
        """Query one analog channel input coupling."""

        return self._channel_controller().query_coupling(channel)

    def set_channel_probe_ratio(self, channel: int, ratio: float) -> None:
        """Set one analog channel probe attenuation ratio."""

        self._channel_controller().set_probe_ratio(channel, ratio)

    def query_channel_probe_ratio(self, channel: int) -> float:
        """Query one analog channel probe attenuation ratio."""

        return self._channel_controller().query_probe_ratio(channel)

    def set_channel_bandwidth_limit(self, channel: int, enabled: bool) -> None:
        """Turn one analog channel bandwidth limit on or off."""

        self._channel_controller().set_bandwidth_limit(channel, enabled)

    def query_channel_bandwidth_limit(self, channel: int) -> bool:
        """Query whether one analog channel bandwidth limit is enabled."""

        return self._channel_controller().query_bandwidth_limit(channel)

    def set_channel_impedance(self, channel: int, impedance: str) -> None:
        """Set one analog channel input impedance."""

        self._channel_controller().set_impedance(channel, impedance)

    def query_channel_impedance(self, channel: int) -> str:
        """Query one analog channel input impedance."""

        return self._channel_controller().query_impedance(channel)

    def set_channel_invert(self, channel: int, enabled: bool) -> None:
        """Turn one analog channel inversion on or off."""

        self._channel_controller().set_invert(channel, enabled)

    def query_channel_invert(self, channel: int) -> bool:
        """Query whether one analog channel inversion is enabled."""

        return self._channel_controller().query_invert(channel)

    def set_channel_range(self, channel: int, volts: float) -> None:
        """Set one analog channel full-scale range in volts."""

        self._channel_controller().set_range(channel, volts)

    def query_channel_range(self, channel: int) -> float:
        """Query one analog channel full-scale range in volts."""

        return self._channel_controller().query_range(channel)

    def set_channel_units(self, channel: int, units: str) -> None:
        """Set one analog channel units."""

        self._channel_controller().set_units(channel, units)

    def query_channel_units(self, channel: int) -> str:
        """Query one analog channel units."""

        return self._channel_controller().query_units(channel)

    def set_channel_vernier(self, channel: int, enabled: bool) -> None:
        """Turn one analog channel vernier scaling on or off."""

        self._channel_controller().set_vernier(channel, enabled)

    def query_channel_vernier(self, channel: int) -> bool:
        """Query whether one analog channel vernier scaling is enabled."""

        return self._channel_controller().query_vernier(channel)

    def set_channel_probe_skew(self, channel: int, seconds: float) -> None:
        """Set one analog channel probe skew in seconds."""

        self._channel_controller().set_probe_skew(channel, seconds)

    def query_channel_probe_skew(self, channel: int) -> float:
        """Query one analog channel probe skew in seconds."""

        return self._channel_controller().query_probe_skew(channel)

    def set_channel_label(self, channel: int, text: str) -> None:
        """Set one analog channel label."""

        self._channel_controller().set_label(channel, text)

    def query_channel_label(self, channel: int) -> str:
        """Query one analog channel label."""

        return self._channel_controller().query_label(channel)

    def query_channel_summary(self) -> tuple[ChannelSummaryEntry, ...]:
        """Query common setup fields for every analog channel."""

        return self._channel_controller().query_summary()

    def set_display_label(self, enabled: bool) -> None:
        """Turn display labels on or off."""

        self._display_controller().set_label(enabled)

    def query_display_label(self) -> bool:
        """Query whether display labels are enabled."""

        return self._display_controller().query_label()

    def clear_display(self) -> None:
        """Clear waveform display data and associated measurements."""

        self._display_controller().clear_display()

    def set_display_persistence(self, value: str | float) -> None:
        self._display_controller().set_persistence(value)

    def query_display_persistence(self) -> DisplayPersistence:
        return self._display_controller().query_persistence()

    def set_display_intensity(self, value: int) -> None:
        self._display_controller().set_intensity(value)

    def query_display_intensity(self) -> tuple[int, str]:
        return self._display_controller().query_intensity()

    def set_display_vectors_on(self) -> None:
        self._display_controller().set_vectors_on()

    def query_display_vectors(self) -> tuple[bool, str]:
        return self._display_controller().query_vectors()

    def set_annotation_enabled(self, enabled: bool, *, slot: int = 1) -> None:
        self._display_controller().set_annotation_enabled(enabled, slot=slot)

    def clear_annotation(self, *, slot: int = 1) -> None:
        self._display_controller().clear_annotation(slot=slot)

    def set_annotation_text(self, text: str, *, slot: int = 1) -> None:
        self._display_controller().set_annotation_text(text, slot=slot)

    def set_annotation_color(self, color: str, *, slot: int = 1) -> None:
        self._display_controller().set_annotation_color(color, slot=slot)

    def set_annotation_background(self, background: str, *, slot: int = 1) -> None:
        self._display_controller().set_annotation_background(background, slot=slot)

    def set_annotation_position(
        self, x: int | None = None, y: int | None = None, *, slot: int = 1
    ) -> None:
        self._display_controller().set_annotation_position(x=x, y=y, slot=slot)

    def query_annotation(self, *, slot: int = 1) -> AnnotationState:
        return self._display_controller().query_annotation(slot=slot)

    def set_timebase_scale(self, seconds_per_division: float) -> None:
        """Set the horizontal scale in seconds per division."""

        self._timebase_controller().set_scale(seconds_per_division)

    def query_timebase_scale(self) -> float:
        """Query the horizontal scale in seconds per division."""

        return self._timebase_controller().query_scale()

    def set_timebase_position(self, seconds: float) -> None:
        """Set the horizontal position in seconds."""

        self._timebase_controller().set_position(seconds)

    def query_timebase_position(self) -> float:
        """Query the horizontal position in seconds."""

        return self._timebase_controller().query_position()

    def set_timebase_reference(self, reference: str) -> None:
        """Set the horizontal timebase reference position."""

        self._timebase_controller().set_reference(reference)

    def query_timebase_reference(self) -> TimebaseReference:
        """Query the horizontal timebase reference position."""

        return self._timebase_controller().query_reference()

    def configure_trigger_edge(self, source_channel: int, level_volts: float, slope: str) -> None:
        """Configure analog edge trigger source, level, and slope."""

        self._edge_trigger_controller().configure(source_channel, level_volts, slope)

    def query_trigger_edge(self) -> EdgeTriggerState:
        """Query analog edge trigger source, level, and slope."""

        return self._edge_trigger_controller().query()

    def configure_trigger_edge_source(
        self,
        *,
        source: str,
        source_channel: int | None = None,
    ) -> None:
        """Configure the Edge Trigger source without changing other settings."""

        self._edge_trigger_source_controller().configure(
            source=source,
            source_channel=source_channel,
        )

    def query_trigger_edge_source(self) -> EdgeTriggerSourceState:
        """Query the Edge Trigger source without querying other settings."""

        return self._edge_trigger_source_controller().query()

    def configure_trigger_edge_slope(self, *, slope: str) -> None:
        """Configure Edge Trigger slope without changing other settings."""

        self._edge_trigger_slope_controller().configure(slope=slope)

    def query_trigger_edge_slope(self) -> EdgeTriggerSlopeState:
        """Query Edge Trigger slope without querying other settings."""

        return self._edge_trigger_slope_controller().query()

    def configure_trigger_edge_level(
        self,
        *,
        source_channel: int,
        level_volts: float,
    ) -> None:
        """Configure one named analog Edge Trigger level only."""

        self._edge_trigger_level_controller().configure(
            source_channel=source_channel,
            level_volts=level_volts,
        )

    def query_trigger_edge_level(self, *, source_channel: int) -> EdgeTriggerLevelState:
        """Query one named analog Edge Trigger level only."""

        return self._edge_trigger_level_controller().query(source_channel=source_channel)

    def configure_external_trigger_range(self, range_volts: float) -> None:
        """Configure the dedicated External trigger input range only."""

        self._external_trigger_range_controller().configure(range_volts=range_volts)

    def query_external_trigger_range(self) -> ExternalTriggerRangeState:
        """Query the dedicated External trigger input range only."""

        return self._external_trigger_range_controller().query()

    def configure_external_trigger_probe(self, attenuation: float) -> None:
        """Configure the External trigger probe attenuation only."""

        self._external_trigger_probe_controller().configure(attenuation=attenuation)

    def query_external_trigger_probe(self) -> ExternalTriggerProbeState:
        """Query the External trigger probe attenuation only."""

        return self._external_trigger_probe_controller().query()

    def configure_external_trigger_units(self, units: str) -> None:
        """Configure the External trigger input units only."""

        self._external_trigger_units_controller().configure(units=units)

    def query_external_trigger_units(self) -> ExternalTriggerUnitsState:
        """Query the External trigger input units only."""

        return self._external_trigger_units_controller().query()

    def query_external_trigger_settings(self) -> ExternalTriggerSettingsState:
        """Query aggregate External trigger input settings only."""

        return self._external_trigger_settings_controller().query()

    def configure_trigger_edge_external_level(self, *, level_volts: float) -> None:
        """Configure the External-qualified Edge Trigger level only."""

        self._edge_trigger_external_level_controller().configure(level_volts=level_volts)

    def query_trigger_edge_external_level(self) -> EdgeTriggerExternalLevelState:
        """Query the External-qualified Edge Trigger level only."""

        return self._edge_trigger_external_level_controller().query()

    def configure_trigger_sweep(self, mode: str) -> None:
        """Configure common trigger sweep mode."""

        self._trigger_sweep_controller().configure(mode)

    def query_trigger_sweep(self) -> TriggerSweepState:
        """Query common trigger sweep mode."""

        return self._trigger_sweep_controller().query()

    def configure_trigger_noise_reject(self, enabled: bool) -> None:
        """Configure common trigger noise reject."""

        self._trigger_noise_reject_controller().configure(enabled)

    def query_trigger_noise_reject(self) -> TriggerRejectState:
        """Query common trigger noise reject."""

        return self._trigger_noise_reject_controller().query()

    def configure_trigger_hf_reject(self, enabled: bool) -> None:
        """Configure common trigger high-frequency reject."""

        self._trigger_hf_reject_controller().configure(enabled)

    def query_trigger_hf_reject(self) -> TriggerRejectState:
        """Query common trigger high-frequency reject."""

        return self._trigger_hf_reject_controller().query()

    def configure_dvm_enable(self, enabled: bool) -> None:
        """Configure DVM enable state."""

        self._dvm_controller().configure_enable(enabled)

    def query_dvm_enable(self) -> DvmBooleanState:
        """Query DVM enable state."""

        return self._dvm_controller().query_enable()

    def configure_dvm_source(self, channel: int) -> None:
        """Configure the analog DVM source channel."""

        self._dvm_controller().configure_source(channel)

    def query_dvm_source(self) -> DvmSourceState:
        """Query the analog DVM source channel."""

        return self._dvm_controller().query_source()

    def configure_dvm_mode(self, mode: str) -> None:
        """Configure a DVM voltage mode."""

        self._dvm_controller().configure_mode(mode)

    def query_dvm_mode(self) -> DvmModeState:
        """Query the DVM voltage mode."""

        return self._dvm_controller().query_mode()

    def configure_dvm_auto_range(self, enabled: bool) -> None:
        """Configure DVM auto range."""

        self._dvm_controller().configure_auto_range(enabled)

    def query_dvm_auto_range(self) -> DvmAutoRangeState:
        """Query DVM auto range."""

        return self._dvm_controller().query_auto_range()

    def query_dvm_current(self) -> DvmReading:
        """Query the current DVM voltage reading."""

        return self._dvm_controller().query_current()

    def query_dvm(self) -> DvmState:
        """Query aggregate DVM state."""

        return self._dvm_controller().query()

    def configure_demo_output(self, enabled: bool) -> None:
        """Configure built-in DEMO output state."""

        self._demo_controller().configure_output(enabled)

    def query_demo_output(self) -> DemoOutputState:
        """Query built-in DEMO output state."""

        return self._demo_controller().query_output()

    def configure_demo_function(self, function: str) -> None:
        """Configure a profile-supported built-in DEMO function."""

        self._demo_controller().configure_function(function)

    def query_demo_function(self) -> DemoFunctionState:
        """Query the built-in DEMO function."""

        return self._demo_controller().query_function()

    def configure_demo_phase(self, degrees: float) -> None:
        """Configure built-in DEMO phase in degrees."""

        self._demo_controller().configure_phase(degrees)

    def query_demo_phase(self) -> DemoPhaseState:
        """Query built-in DEMO phase in degrees."""

        return self._demo_controller().query_phase()

    def query_demo(self) -> DemoState:
        """Query aggregate DEMO output state."""

        return self._demo_controller().query()

    def configure_wgen_output(self, enabled: bool) -> None:
        """Configure WGEN output state."""

        self._wgen_controller().configure_output(enabled)

    def query_wgen_output(self) -> WgenOutputState:
        """Query WGEN output state."""

        return self._wgen_controller().query_output()

    def configure_wgen_function(self, function: str) -> None:
        """Configure a WGEN function."""

        self._wgen_controller().configure_function(function)

    def query_wgen_function(self) -> WgenFunctionState:
        """Query the WGEN function."""

        return self._wgen_controller().query_function()

    def configure_wgen_frequency(self, frequency_hz: float) -> None:
        """Configure WGEN frequency in hertz."""

        self._wgen_controller().configure_frequency(frequency_hz)

    def query_wgen_frequency(self) -> WgenFrequencyState:
        """Query WGEN frequency."""

        return self._wgen_controller().query_frequency()

    def configure_wgen_voltage(self, amplitude_volts: float) -> None:
        """Configure WGEN peak-to-peak amplitude in volts."""

        self._wgen_controller().configure_voltage(amplitude_volts)

    def query_wgen_voltage(self) -> WgenVoltageState:
        """Query WGEN peak-to-peak amplitude."""

        return self._wgen_controller().query_voltage()

    def configure_wgen_offset(self, offset_volts: float) -> None:
        """Configure WGEN offset in volts."""

        self._wgen_controller().configure_offset(offset_volts)

    def query_wgen_offset(self) -> WgenOffsetState:
        """Query WGEN offset."""

        return self._wgen_controller().query_offset()

    def configure_wgen_load(self, load: str) -> None:
        """Configure the WGEN output load."""

        self._wgen_controller().configure_load(load)

    def query_wgen_load(self) -> WgenLoadState:
        """Query the WGEN output load."""

        return self._wgen_controller().query_load()

    def query_wgen(self) -> WgenState:
        """Query aggregate WGEN state."""

        return self._wgen_controller().query()

    def query_serial(self, bus: int) -> SerialQueryState:
        """Query the raw aggregate setup for one serial decode bus."""

        return self._serial_controller().query(bus)

    def configure_serial_mode(self, bus: int, mode: str) -> SerialModeState:
        """Configure one serial decode bus mode."""

        return self._serial_controller().configure_mode(bus, mode)

    def query_serial_mode(self, bus: int) -> SerialModeState:
        """Query one serial decode bus mode."""

        return self._serial_controller().query_mode(bus)

    def configure_serial_display(
        self, bus: int, enabled: bool
    ) -> SerialDisplayState:
        """Configure one serial decode bus display state."""

        return self._serial_controller().configure_display(bus, enabled)

    def query_serial_display(self, bus: int) -> SerialDisplayState:
        """Query one serial decode bus display state."""

        return self._serial_controller().query_display(bus)

    def query_serial_lister(self) -> SerialListerState:
        """Query global Serial Lister display and reference state."""

        return self._serial_controller().query_lister()

    def configure_serial_lister_display(self, display: str) -> SerialListerDisplayState:
        """Configure global Serial Lister display selection."""

        return self._serial_controller().configure_lister_display(display)

    def query_serial_lister_display(self) -> SerialListerDisplayState:
        """Query global Serial Lister display selection."""

        return self._serial_controller().query_lister_display()

    def configure_serial_lister_reference(self, reference: str) -> SerialListerReferenceState:
        """Configure global Serial Lister reference."""

        return self._serial_controller().configure_lister_reference(reference)

    def query_serial_lister_reference(self) -> SerialListerReferenceState:
        """Query global Serial Lister reference."""

        return self._serial_controller().query_lister_reference()

    def query_serial_lister_data(self) -> bytes:
        """Query and decode the raw global Serial Lister data block."""

        return self._serial_controller().query_lister_data()

    def configure_serial_uart(self, bus: int, **settings: object) -> SerialUartState:
        """Configure basic UART decode settings."""

        return self._serial_controller().configure_uart(bus, **settings)

    def query_serial_uart(self, bus: int) -> SerialUartState:
        """Query basic UART decode settings."""

        return self._serial_controller().query_uart(bus)

    def configure_serial_uart_trigger(
        self, bus: int, **settings: object
    ) -> SerialUartTriggerState:
        """Configure UART trigger criteria without changing UART decode settings."""

        return self._serial_controller().configure_uart_trigger(bus, **settings)

    def query_serial_uart_trigger(self, bus: int) -> SerialUartTriggerState:
        """Query UART trigger criteria and active serial trigger selection."""

        return self._serial_controller().query_uart_trigger(bus)

    def configure_serial_i2c_trigger(
        self, bus: int, **settings: object
    ) -> SerialI2CTriggerState:
        """Configure I2C trigger criteria without changing I2C decode settings."""

        return self._serial_controller().configure_i2c_trigger(bus, **settings)

    def query_serial_i2c_trigger(self, bus: int) -> SerialI2CTriggerState:
        """Query I2C trigger criteria and active serial trigger selection."""

        return self._serial_controller().query_i2c_trigger(bus)

    def configure_serial_spi_trigger(
        self, bus: int, **settings: object
    ) -> SerialSpiTriggerState:
        """Configure SPI trigger criteria without changing SPI decode settings."""

        return self._serial_controller().configure_spi_trigger(bus, **settings)

    def query_serial_spi_trigger(self, bus: int) -> SerialSpiTriggerState:
        """Query SPI trigger criteria and active serial trigger selection."""

        return self._serial_controller().query_spi_trigger(bus)

    def configure_serial_can_trigger(
        self, bus: int, **settings: object
    ) -> SerialCanTriggerState:
        """Configure CAN trigger criteria without changing CAN decode settings."""

        return self._serial_controller().configure_can_trigger(bus, **settings)

    def query_serial_can_trigger(self, bus: int) -> SerialCanTriggerState:
        """Query CAN trigger criteria and active serial trigger selection."""

        return self._serial_controller().query_can_trigger(bus)

    def configure_serial_i2c(self, bus: int, **settings: object) -> SerialI2CState:
        """Configure basic I2C decode settings."""

        return self._serial_controller().configure_i2c(bus, **settings)

    def query_serial_i2c(self, bus: int) -> SerialI2CState:
        """Query basic I2C decode settings."""

        return self._serial_controller().query_i2c(bus)

    def configure_serial_spi(self, bus: int, **settings: object) -> SerialSpiState:
        """Configure basic SPI decode settings."""

        return self._serial_controller().configure_spi(bus, **settings)

    def query_serial_spi(self, bus: int) -> SerialSpiState:
        """Query basic SPI decode settings."""

        return self._serial_controller().query_spi(bus)

    def configure_serial_can(self, bus: int, **settings: object) -> SerialCanState:
        """Configure basic CAN decode settings."""

        return self._serial_controller().configure_can(bus, **settings)

    def query_serial_can(self, bus: int) -> SerialCanState:
        """Query basic CAN decode settings."""

        return self._serial_controller().query_can(bus)

    def configure_search_state(self, enabled: bool) -> SearchState:
        """Configure waveform search enable state."""

        return self._search_controller().configure_state(enabled)

    def query_search_state(self) -> SearchState:
        """Query waveform search enable state."""

        return self._search_controller().query_state()

    def configure_search_mode(self, mode: str) -> SearchModeState:
        """Enable search and configure a profile-supported search mode."""

        return self._search_controller().configure_mode(mode)

    def query_search_mode(self) -> SearchModeState:
        """Query the current waveform search mode."""

        return self._search_controller().query_mode()

    def query_search_count(self) -> SearchCountState:
        """Query the current waveform search event count."""

        return self._search_controller().query_count()

    def configure_search_event(self, event: int) -> SearchEventState:
        """Configure selected search event."""

        return self._search_controller().set_event(event)

    def query_search_event(self) -> SearchEventState:
        """Query selected search event."""

        return self._search_controller().query_event()

    def configure_serial_search_uart(
        self,
        bus: int,
        mode: str,
        data: int | None = None,
        qualifier: str | None = None,
    ) -> SerialSearchUartState:
        """Configure UART serial search settings."""

        return self._search_controller().configure_serial_search_uart(
            bus, mode, data=data, qualifier=qualifier
        )

    def query_serial_search_uart(self, bus: int) -> SerialSearchUartState:
        """Query UART serial search settings."""

        return self._search_controller().query_serial_search_uart(bus)

    def configure_serial_search_i2c(
        self,
        bus: int,
        mode: str,
        address: int | None = None,
        data: int | None = None,
        data2: int | None = None,
        qualifier: str | None = None,
    ) -> SerialSearchI2CState:
        """Configure I2C serial search settings."""

        return self._search_controller().configure_serial_search_i2c(
            bus, mode, address=address, data=data, data2=data2, qualifier=qualifier
        )

    def query_serial_search_i2c(self, bus: int) -> SerialSearchI2CState:
        """Query I2C serial search settings."""

        return self._search_controller().query_serial_search_i2c(bus)

    def configure_serial_search_spi(
        self,
        bus: int,
        mode: str,
        data: str | None = None,
        width: int | None = None,
    ) -> SerialSearchSpiState:
        """Configure SPI serial search settings."""

        return self._search_controller().configure_serial_search_spi(
            bus, mode, data=data, width=width
        )

    def query_serial_search_spi(self, bus: int) -> SerialSearchSpiState:
        """Query SPI serial search settings."""

        return self._search_controller().query_serial_search_spi(bus)

    def configure_serial_search_can(
        self,
        bus: int,
        mode: str,
        data: str | None = None,
        data_length: int | None = None,
        id_val: str | None = None,
        id_mode: str | None = None,
    ) -> SerialSearchCanState:
        """Configure CAN serial search settings."""

        return self._search_controller().configure_serial_search_can(
            bus, mode, data=data, data_length=data_length, id_val=id_val, id_mode=id_mode
        )

    def query_serial_search_can(self, bus: int) -> SerialSearchCanState:
        """Query CAN serial search settings."""

        return self._search_controller().query_serial_search_can(bus)

    def configure_save_pwd(self, path: str) -> None:
        """Configure the instrument-side current save directory."""

        self._save_export_controller().configure_pwd(path)

    def query_save_pwd(self) -> SavePwdState:
        """Query the instrument-side current save directory."""

        return self._save_export_controller().query_pwd()

    def configure_save_filename(self, name: str) -> None:
        """Configure the instrument-side default save base name."""

        self._save_export_controller().configure_filename(name)

    def query_save_filename(self) -> SaveFilenameState:
        """Query the instrument-side default save base name."""

        return self._save_export_controller().query_filename()

    def configure_save_image_format(self, format: str) -> None:
        """Configure the instrument-side image save format."""

        self._save_export_controller().configure_image_format(format)

    def query_save_image_format(self) -> SaveImageFormatState:
        """Query the instrument-side image save format."""

        return self._save_export_controller().query_image_format()

    def configure_save_image_palette(self, palette: str) -> None:
        """Configure the instrument-side image save palette."""

        self._save_export_controller().configure_image_palette(palette)

    def query_save_image_palette(self) -> SaveImagePaletteState:
        """Query the instrument-side image save palette."""

        return self._save_export_controller().query_image_palette()

    def configure_save_image_ink_saver(self, enabled: bool) -> None:
        """Configure instrument-side image ink saver."""

        self._save_export_controller().configure_image_ink_saver(enabled)

    def query_save_image_ink_saver(self) -> SaveBooleanState:
        """Query instrument-side image ink saver."""

        return self._save_export_controller().query_image_ink_saver()

    def configure_save_image_factors(self, enabled: bool) -> None:
        """Configure instrument-side image measurement factors."""

        self._save_export_controller().configure_image_factors(enabled)

    def query_save_image_factors(self) -> SaveBooleanState:
        """Query instrument-side image measurement factors."""

        return self._save_export_controller().query_image_factors()

    def save_image(self, filename: str) -> SaveOperationResult:
        """Save an image on the instrument and wait for completion."""

        return self._save_export_controller().save_image(filename)

    def configure_save_waveform_format(self, format: str) -> None:
        """Configure the instrument-side waveform save format."""

        self._save_export_controller().configure_waveform_format(format)

    def query_save_waveform_format(self) -> SaveWaveformFormatState:
        """Query the instrument-side waveform save format."""

        return self._save_export_controller().query_waveform_format()

    def configure_save_waveform_length(self, points: int) -> None:
        """Configure the instrument-side waveform save length."""

        self._save_export_controller().configure_waveform_length(points)

    def query_save_waveform_length(self) -> SaveWaveformLengthState:
        """Query the instrument-side waveform save length."""

        return self._save_export_controller().query_waveform_length()

    def query_save_waveform_length_max(self) -> SaveBooleanState:
        """Query whether maximum waveform save length is enabled."""

        return self._save_export_controller().query_waveform_length_max()

    def save_waveform(self, filename: str) -> SaveOperationResult:
        """Save waveform data on the instrument and wait for completion."""

        return self._save_export_controller().save_waveform(filename)


    def configure_trigger_edge_coupling(self, coupling: str) -> None:
        """Configure Edge Trigger coupling."""

        self._edge_coupling_controller().configure(coupling)

    def query_trigger_edge_coupling(self) -> EdgeTriggerCouplingState:
        """Query Edge Trigger coupling."""

        return self._edge_coupling_controller().query()

    def configure_trigger_edge_reject(self, reject: str) -> None:
        """Configure Edge Trigger reject filter."""

        self._edge_reject_controller().configure(reject)

    def query_trigger_edge_reject(self) -> EdgeTriggerRejectState:
        """Query Edge Trigger reject filter."""

        return self._edge_reject_controller().query()

    def configure_glitch_trigger(
        self,
        *,
        channel: int,
        polarity: str,
        qualifier: str,
        time_seconds: float | None = None,
        min_time_seconds: float | None = None,
        max_time_seconds: float | None = None,
        level_volts: float | None = None,
    ) -> None:
        """Configure analog pulse-width trigger settings."""

        self._glitch_trigger_controller().configure(
            channel=channel,
            polarity=polarity,
            qualifier=qualifier,
            time_seconds=time_seconds,
            min_time_seconds=min_time_seconds,
            max_time_seconds=max_time_seconds,
            level_volts=level_volts,
        )

    def query_glitch_trigger(self) -> GlitchTriggerState:
        """Query pulse-width trigger settings."""

        return self._glitch_trigger_controller().query()

    def configure_runt_trigger(
        self,
        *,
        channel: int,
        polarity: str,
        qualifier: str,
        low_level_volts: float,
        high_level_volts: float,
        time_seconds: float | None = None,
    ) -> None:
        """Configure analog runt trigger settings."""

        self._runt_trigger_controller().configure(
            channel=channel,
            polarity=polarity,
            qualifier=qualifier,
            low_level_volts=low_level_volts,
            high_level_volts=high_level_volts,
            time_seconds=time_seconds,
        )

    def query_runt_trigger(self) -> RuntTriggerState:
        """Query runt trigger settings."""

        return self._runt_trigger_controller().query()

    def configure_transition_trigger(
        self,
        *,
        channel: int,
        slope: str,
        qualifier: str,
        low_level_volts: float,
        high_level_volts: float,
        time_seconds: float,
    ) -> None:
        """Configure analog transition trigger settings."""

        self._transition_trigger_controller().configure(
            channel=channel,
            slope=slope,
            qualifier=qualifier,
            low_level_volts=low_level_volts,
            high_level_volts=high_level_volts,
            time_seconds=time_seconds,
        )

    def query_transition_trigger(self) -> TransitionTriggerState:
        """Query transition trigger settings."""

        return self._transition_trigger_controller().query()

    def configure_delay_trigger(
        self,
        *,
        arm_channel: int,
        arm_slope: str,
        trigger_channel: int,
        trigger_slope: str,
        time_seconds: float,
        count: int,
    ) -> None:
        """Configure analog Edge Then Edge / Delay trigger settings."""

        self._delay_trigger_controller().configure(
            arm_channel=arm_channel,
            arm_slope=arm_slope,
            trigger_channel=trigger_channel,
            trigger_slope=trigger_slope,
            time_seconds=time_seconds,
            count=count,
        )

    def query_delay_trigger(self) -> DelayTriggerState:
        """Query delay trigger settings."""

        return self._delay_trigger_controller().query()

    def configure_setup_hold_trigger(
        self,
        *,
        clock_channel: int,
        data_channel: int,
        slope: str,
        setup_time_seconds: float,
        hold_time_seconds: float,
    ) -> SetupHoldTriggerState:
        """Configure DSO analog setup-hold trigger settings."""

        return self._setup_hold_trigger_controller().configure(
            clock_channel=clock_channel,
            data_channel=data_channel,
            slope=slope,
            setup_time_seconds=setup_time_seconds,
            hold_time_seconds=hold_time_seconds,
        )

    def query_setup_hold_trigger(self) -> SetupHoldTriggerState:
        """Query setup-hold trigger settings."""

        return self._setup_hold_trigger_controller().query()

    def configure_edge_burst_trigger(
        self,
        *,
        source_channel: int,
        slope: str,
        count: int,
        idle_time: float,
        level_volts: float | None = None,
    ) -> EdgeBurstTriggerState:
        """Configure DSO analog Nth Edge Burst trigger settings."""

        return self._edge_burst_trigger_controller().configure(
            source_channel=source_channel,
            slope=slope,
            count=count,
            idle_time=idle_time,
            level_volts=level_volts,
        )

    def query_edge_burst_trigger(self) -> EdgeBurstTriggerState:
        """Query Nth Edge Burst trigger settings."""

        return self._edge_burst_trigger_controller().query()

    def configure_tv_trigger(
        self,
        *,
        source_channel: int,
        standard: str,
        mode: str,
        polarity: str,
        line: int | None = None,
    ) -> TvTriggerState:
        """Configure DSO analog basic TV trigger settings."""

        return self._tv_trigger_controller().configure(
            source_channel=source_channel,
            standard=standard,
            mode=mode,
            polarity=polarity,
            line=line,
        )

    def query_tv_trigger(self) -> TvTriggerState:
        """Query basic TV trigger settings."""

        return self._tv_trigger_controller().query()

    def configure_pattern_trigger(self, pattern: str) -> PatternTriggerState:
        """Configure DSO ASCII pattern trigger settings."""

        return self._pattern_trigger_controller().configure(pattern)

    def query_pattern_trigger(self) -> PatternTriggerState:
        """Query pattern trigger settings."""

        return self._pattern_trigger_controller().query()

    def configure_or_trigger(self, pattern: str) -> OrTriggerState:
        """Configure DSO analog OR trigger settings."""

        return self._or_trigger_controller().configure(pattern)

    def query_or_trigger(self) -> OrTriggerState:
        """Query OR trigger settings."""

        return self._or_trigger_controller().query()

    def capture_waveform_byte(self, channel: int, points: int = 1000) -> WaveformCapture:
        """Capture one analog channel using BYTE waveform format."""

        return self._waveform_controller().capture_byte(channel, points=points)

    def capture_waveform_word(self, channel: int, points: int = 1000) -> WaveformCapture:
        """Capture one analog channel using WORD waveform format."""

        return self._waveform_controller().capture_word(channel, points=points)

    def capture_waveforms_byte(
        self, channels: Sequence[int], points: int = 1000
    ) -> MultiChannelWaveformCapture:
        """Capture multiple analog channels using BYTE waveform format."""

        return self._waveform_controller().capture_channels_byte(channels, points=points)

    def capture_waveforms_word(
        self, channels: Sequence[int], points: int = 1000
    ) -> MultiChannelWaveformCapture:
        """Capture multiple analog channels using WORD waveform format."""

        return self._waveform_controller().capture_channels_word(channels, points=points)

    def query_measurement(
        self,
        channel: int,
        item: str,
        *,
        time_s: float | None = None,
        level: float | None = None,
        slope: str | None = None,
        occurrence: int | None = None,
    ) -> MeasurementResult:
        """Query one read-only measurement item for one analog channel."""

        return self._measurement_controller().query(
            channel,
            item,
            time_s=time_s,
            level=level,
            slope=slope,
            occurrence=occurrence,
        )

    def query_pair_measurement(
        self,
        source_channel: int,
        reference_channel: int,
        item: str,
    ) -> MeasurementResult:
        """Query one read-only measurement item comparing two analog channels."""

        return self._measurement_controller().query_pair(
            source_channel,
            reference_channel,
            item,
        )

    def query_measurement_results(self) -> MeasurementResultsDump:
        """Query currently displayed front-panel measurement results."""

        return self._measurement_controller().query_results()

    def clear_measurements(self) -> None:
        self._measurement_controller().clear()

    def configure_measurement_show(self, enabled: bool = True) -> None:
        self._measurement_controller().set_show(enabled)

    def query_measurement_show(self) -> MeasurementShowState:
        return self._measurement_controller().query_show()

    def configure_measurement_source(
        self, source1_channel: int, source2_channel: int | None = None
    ) -> None:
        self._measurement_controller().set_source(source1_channel, source2_channel)

    def query_measurement_source(self) -> MeasurementSourceState:
        return self._measurement_controller().query_source()

    def configure_measurement_window(self, window: str) -> None:
        self._measurement_controller().set_window(window)

    def query_measurement_window(self) -> MeasurementWindowState:
        return self._measurement_controller().query_window()

    def save_reference_waveform(self, slot: int, source_channel: int) -> None:
        self._reference_waveform_controller().save(slot, source_channel)

    def configure_reference_display(self, slot: int, enabled: bool) -> None:
        self._reference_waveform_controller().set_display(slot, enabled)

    def query_reference_display(self, slot: int) -> tuple[bool, str]:
        return self._reference_waveform_controller().query_display(slot)

    def configure_reference_label(self, slot: int, label: str) -> None:
        self._reference_waveform_controller().set_label(slot, label)

    def query_reference_label(self, slot: int) -> tuple[str, str]:
        return self._reference_waveform_controller().query_label(slot)

    def clear_reference_waveform(self, slot: int) -> None:
        self._reference_waveform_controller().clear(slot)

    def query_reference_waveform(self, slot: int) -> ReferenceWaveformState:
        return self._reference_waveform_controller().query(slot)

    def configure_cursor(
        self,
        source_channel: int,
        x1_seconds: float,
        x2_seconds: float,
        *,
        y1_volts: float | None = None,
        y2_volts: float | None = None,
        auto_timebase: bool = False,
        auto_vertical: bool = False,
    ) -> None:
        self._cursor_controller().set_manual(
            source_channel,
            x1_seconds,
            x2_seconds,
            y1_volts=y1_volts,
            y2_volts=y2_volts,
            auto_timebase=auto_timebase,
            auto_vertical=auto_vertical,
        )

    def cursor_off(self) -> None:
        self._cursor_controller().off()

    def query_cursor(self) -> CursorState:
        return self._cursor_controller().query()

    def set_trigger_holdoff(self, seconds: float) -> None:
        self._trigger_holdoff_controller().set_seconds(seconds)

    def query_trigger_holdoff(self) -> float:
        return self._trigger_holdoff_controller().query_seconds()

    def query_measurement_statistics(
        self,
        channel: int,
        items: Sequence[str],
        *,
        mode: str = "all",
        reset: bool = False,
        max_count: int | None = None,
        settle_seconds: float | None = None,
    ) -> MeasurementStatisticsResult:
        return self._measurement_controller().statistics(
            channel,
            items,
            mode=mode,
            reset=reset,
            max_count=max_count,
            settle_seconds=settle_seconds,
        )

    def query_measurement_statistics_state(self) -> MeasurementStatisticsState:
        return self._measurement_controller().query_statistics_state()

    def configure_measurement_statistics_mode(self, mode: str) -> None:
        self._measurement_controller().set_statistics_mode(mode)

    def configure_measurement_statistics_display(self, enabled: bool) -> None:
        self._measurement_controller().set_statistics_display(enabled)

    def configure_measurement_statistics_max_count(self, value: int | None) -> None:
        self._measurement_controller().set_statistics_max_count(value)

    def configure_measurement_statistics_relative_stddev(self, enabled: bool) -> None:
        self._measurement_controller().set_statistics_relative_stddev(enabled)

    def reset_measurement_statistics(self) -> None:
        self._measurement_controller().reset_statistics()

    def increment_measurement_statistics(self) -> None:
        self._measurement_controller().increment_statistics()

    def autoscale(
        self,
        channels: Sequence[int] | None,
        *,
        acquire_mode: str | None = None,
        channels_mode: str | None = None,
    ) -> None:
        self._setup_controller().autoscale(
            channels,
            acquire_mode=acquire_mode,
            channels_mode=channels_mode,
            capabilities=self.capabilities,
        )

    def save_setup(self, *, slot: int | None = None, file_spec: str | None = None) -> None:
        self._setup_controller().save(slot=slot, file_spec=file_spec)

    def recall_setup(self, *, slot: int | None = None, file_spec: str | None = None) -> None:
        self._setup_controller().recall(slot=slot, file_spec=file_spec)

    def configure_fft(
        self,
        function: int,
        source_channel: int,
        *,
        units: str | None = None,
        window: str | None = None,
        center_hz: float | None = None,
        span_hz: float | None = None,
        display: bool | None = None,
        fft_operation: str = "fft",
        start_hz: float | None = None,
        stop_hz: float | None = None,
        gate: str | None = None,
        phase_reference: str | None = None,
        detection_type: str | None = None,
        detection_points: int | None = None,
    ) -> None:
        self._fft_controller().configure(
            function,
            source_channel,
            units=units,
            window=window,
            center_hz=center_hz,
            span_hz=span_hz,
            display=display,
            fft_operation=fft_operation,
            start_hz=start_hz,
            stop_hz=stop_hz,
            gate=gate,
            phase_reference=phase_reference,
            detection_type=detection_type,
            detection_points=detection_points,
        )

    def query_fft(self, function: int) -> FFTState:
        return self._fft_controller().query(function)

    def configure_math_display(self, function: int, enabled: bool) -> None:
        self._math_controller().set_display(function, enabled)

    def query_math_display(self, function: int) -> MathDisplayState:
        return self._math_controller().query_display(function)

    def configure_math_vertical(
        self,
        function: int,
        *,
        scale: float | None = None,
        range_value: float | None = None,
        offset: float | None = None,
    ) -> None:
        self._math_controller().configure_vertical(
            function,
            scale=scale,
            range_value=range_value,
            offset=offset,
        )

    def query_math_vertical(self, function: int) -> MathVerticalState:
        return self._math_controller().query_vertical(function)

    def configure_math_operator(
        self,
        function: int,
        operation: str,
        source1: str,
        source2: str,
    ) -> None:
        self._math_controller().configure_operator(
            function,
            operation,
            source1,
            source2,
        )

    def query_math_operator(self, function: int) -> MathOperatorState:
        return self._math_controller().query_operator(function)

    def configure_math_composite_source(
        self,
        operation: str,
        source1: str,
        source2: str,
    ) -> None:
        self._math_controller().configure_composite_source(
            operation,
            source1,
            source2,
        )

    def query_math_composite_source(self) -> MathCompositeSourceState:
        return self._math_controller().query_composite_source()

    def configure_math_transform(
        self,
        function: int,
        operation: str,
        source: str,
        *,
        input_offset: float | None = None,
        gain: float | None = None,
        linear_offset: float | None = None,
    ) -> None:
        self._math_controller().configure_transform(
            function,
            operation,
            source,
            input_offset=input_offset,
            gain=gain,
            linear_offset=linear_offset,
        )

    def query_math_transform(self, function: int) -> MathTransformState:
        return self._math_controller().query_transform(function)

    def configure_math_filter(
        self,
        function: int,
        operation: str,
        source: str,
        *,
        cutoff_hz: float | None = None,
        average_count: int | None = None,
        smooth_points: int | None = None,
    ) -> None:
        self._math_controller().configure_filter(
            function,
            operation,
            source,
            cutoff_hz=cutoff_hz,
            average_count=average_count,
            smooth_points=smooth_points,
        )

    def query_math_filter(self, function: int) -> MathFilterState:
        return self._math_controller().query_filter(function)

    def configure_math_visualization(
        self,
        function: int,
        operation: str,
        *,
        source: str | None = None,
        source2: str | None = None,
        measurement: str | None = None,
        measurement_slot: int | None = None,
    ) -> None:
        self._math_controller().configure_visualization(
            function,
            operation,
            source=source,
            source2=source2,
            measurement=measurement,
            measurement_slot=measurement_slot,
        )

    def query_math_visualization(
        self, function: int
    ) -> MathVisualizationState:
        return self._math_controller().query_visualization(function)

    def clear_math(self, function: int) -> None:
        self._math_controller().clear(function)

    def capture_screenshot_png(self, *, background: str = "black") -> ScreenshotCapture:
        """Capture the current screen as a color PNG image."""

        return self._screenshot_controller().capture_png(background=background)

    def capture_screenshot(
        self, *, options: ScreenshotOptions, background: str = "black"
    ) -> ScreenshotCapture:
        """Capture a screen image with optional hardcopy controls."""

        return self._screenshot_controller().capture(options=options, background=background)

    def query_hardcopy_state(self) -> HardcopyState:
        """Query the current hardcopy and screen-dump settings."""

        return self._screenshot_controller().query_hardcopy_state()

    def set_acquisition_type(self, acquisition_type: str) -> None:
        """Set the acquisition type."""

        self._acquisition_controller().set_type(acquisition_type)

    def query_acquisition_type(self) -> str:
        """Query the current acquisition type."""

        return self._acquisition_controller().query_type()

    def set_acquisition_count(self, count: int) -> None:
        """Set the average count for average acquisition mode."""

        self._acquisition_controller().set_count(count)

    def query_acquisition_count(self) -> int:
        """Query the current average count."""

        return self._acquisition_controller().query_count()

    def query_acquisition_config(self) -> AcquisitionConfig:
        """Query both acquisition type and count."""

        return self._acquisition_controller().query_config()

    def query_segmented_memory(self) -> SegmentedMemoryQueryResult:
        """Query segmented-memory state without changing acquisition state."""

        return self._segmented_memory_controller().query()

    def enable_segmented_memory(self, segments: int) -> None:
        """Enable segmented-memory acquisition with an explicit segment count."""

        self._segmented_memory_controller().enable(segments)

    def disable_segmented_memory(self) -> None:
        """Disable segmented-memory acquisition without changing its count."""

        self._segmented_memory_controller().disable()

    def query_segmented_mode(self) -> str:
        """Query only the normalized segmented-memory acquisition mode."""

        return self._segmented_memory_controller().query_mode()

    def query_segmented_acquired_count(self) -> int:
        """Query the number of acquired segmented waveforms."""

        return self._segmented_memory_controller().query_acquired_count()

    def select_segmented_memory(self, index: int) -> None:
        """Select one acquired segmented waveform index."""

        self._segmented_memory_controller().select_segment(index)

    def query_segmented_time_tag(self) -> float:
        """Query the selected segmented waveform time tag in seconds."""

        return self._segmented_memory_controller().query_time_tag()

    def close(self) -> None:
        """Close the underlying backend."""

        self.backend.close()

    def _channel_controller(self) -> ChannelController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Channel operations require known capabilities; call query_idn() first."
            )
        return ChannelController(self.scpi, self.capabilities)

    def _display_controller(self) -> DisplayController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Display operations require known capabilities; call query_idn() first."
            )
        return DisplayController(self.scpi, self.capabilities)

    def _status_controller(self) -> StatusController:
        return StatusController(self.scpi)

    def _save_export_controller(self) -> SaveExportController:
        return SaveExportController(self.scpi, self.capabilities)

    def _timebase_controller(self) -> TimebaseController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Timebase operations require known capabilities; call query_idn() first."
        )
        return TimebaseController(self.scpi)

    def _edge_trigger_controller(self) -> EdgeTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Edge trigger operations require known capabilities; call query_idn() first."
            )
        return EdgeTriggerController(self.scpi, self.capabilities)

    def _edge_trigger_source_controller(self) -> EdgeTriggerSourceController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Edge Trigger source operations require known capabilities; call query_idn() first."
            )
        return EdgeTriggerSourceController(self.scpi, self.capabilities)

    def _edge_trigger_slope_controller(self) -> EdgeTriggerSlopeController:
        return EdgeTriggerSlopeController(self.scpi)

    def _edge_trigger_level_controller(self) -> EdgeTriggerLevelController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Edge Trigger level operations require known capabilities; call query_idn() first."
            )
        return EdgeTriggerLevelController(self.scpi, self.capabilities)

    def _external_trigger_range_controller(self) -> ExternalTriggerRangeController:
        return ExternalTriggerRangeController(self.scpi)

    def _external_trigger_probe_controller(self) -> ExternalTriggerProbeController:
        return ExternalTriggerProbeController(self.scpi)

    def _external_trigger_units_controller(self) -> ExternalTriggerUnitsController:
        return ExternalTriggerUnitsController(self.scpi)

    def _external_trigger_settings_controller(self) -> ExternalTriggerSettingsController:
        return ExternalTriggerSettingsController(self.scpi)

    def _edge_trigger_external_level_controller(self) -> EdgeTriggerExternalLevelController:
        return EdgeTriggerExternalLevelController(self.scpi)

    def _trigger_sweep_controller(self) -> TriggerSweepController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Trigger sweep operations require known capabilities; "
                "call query_idn() first."
            )
        return TriggerSweepController(self.scpi)

    def _trigger_noise_reject_controller(self) -> TriggerNoiseRejectController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Trigger noise reject operations require known capabilities; "
                "call query_idn() first."
            )
        return TriggerNoiseRejectController(self.scpi)

    def _trigger_hf_reject_controller(self) -> TriggerHfRejectController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Trigger high-frequency reject operations require known capabilities; "
                "call query_idn() first."
            )
        return TriggerHfRejectController(self.scpi)


    def _edge_coupling_controller(self) -> EdgeTriggerCouplingController:
        if self.capabilities is None:
            raise ParameterValidationError(
                'Edge Trigger coupling operations require known capabilities; '
                'call query_idn() first.'
            )
        return EdgeTriggerCouplingController(self.scpi)

    def _edge_reject_controller(self) -> EdgeTriggerRejectController:
        if self.capabilities is None:
            raise ParameterValidationError(
                'Edge Trigger reject operations require known capabilities; '
                'call query_idn() first.'
            )
        return EdgeTriggerRejectController(self.scpi)

    def _glitch_trigger_controller(self) -> GlitchTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Glitch trigger operations require known capabilities; call query_idn() first."
            )
        return GlitchTriggerController(self.scpi, self.capabilities)

    def _runt_trigger_controller(self) -> RuntTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Runt trigger operations require known capabilities; call query_idn() first."
            )
        return RuntTriggerController(self.scpi, self.capabilities)

    def _transition_trigger_controller(self) -> TransitionTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Transition trigger operations require known capabilities; call query_idn() first."
            )
        return TransitionTriggerController(self.scpi, self.capabilities)

    def _delay_trigger_controller(self) -> DelayTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Delay trigger operations require known capabilities; call query_idn() first."
            )
        return DelayTriggerController(self.scpi, self.capabilities)

    def _setup_hold_trigger_controller(self) -> SetupHoldTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Setup-hold trigger operations require known capabilities; call query_idn() first."
            )
        return SetupHoldTriggerController(self.scpi, self.capabilities)

    def _edge_burst_trigger_controller(self) -> EdgeBurstTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Edge-burst trigger operations require known capabilities; call query_idn() first."
            )
        return EdgeBurstTriggerController(self.scpi, self.capabilities)

    def _tv_trigger_controller(self) -> TvTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "TV trigger operations require known capabilities; call query_idn() first."
            )
        return TvTriggerController(self.scpi, self.capabilities)

    def _pattern_trigger_controller(self) -> PatternTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Pattern trigger operations require known capabilities; call query_idn() first."
            )
        return PatternTriggerController(self.scpi, self.capabilities)

    def _or_trigger_controller(self) -> OrTriggerController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "OR trigger operations require known capabilities; call query_idn() first."
            )
        return OrTriggerController(self.scpi, self.capabilities)

    def _waveform_controller(self) -> WaveformController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Waveform operations require known capabilities; call query_idn() first."
            )
        return WaveformController(self.scpi, self.capabilities)

    def _measurement_controller(self) -> MeasurementController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Measurement operations require known capabilities; call query_idn() first."
            )
        return MeasurementController(self.scpi, self.capabilities)

    def _dvm_controller(self) -> DvmController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "DVM operations require known capabilities; call query_idn() first."
            )
        return DvmController(self.scpi, self.capabilities)

    def _demo_controller(self) -> DemoController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "DEMO operations require known capabilities; call query_idn() first."
            )
        return DemoController(self.scpi, self.capabilities)

    def _wgen_controller(self) -> WgenController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "WGEN operations require known capabilities; call query_idn() first."
            )
        return WgenController(self.scpi, self.capabilities)

    def _search_controller(self) -> SearchController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Search operations require known capabilities; call query_idn() first."
            )
        return SearchController(self.scpi, self.capabilities)

    def _serial_controller(self) -> SerialController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Serial operations require known capabilities; call query_idn() first."
            )
        return SerialController(self.scpi, self.capabilities)

    def _reference_waveform_controller(self) -> ReferenceWaveformController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Reference waveform operations require known capabilities; call query_idn() first."
            )
        return ReferenceWaveformController(self.scpi, self.capabilities)

    def _cursor_controller(self) -> CursorController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Cursor operations require known capabilities; call query_idn() first."
            )
        return CursorController(self.scpi, self.capabilities)

    def _trigger_holdoff_controller(self) -> TriggerHoldoffController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Trigger holdoff operations require known capabilities; call query_idn() first."
            )
        return TriggerHoldoffController(self.scpi, series=self.capabilities.series)

    def _setup_controller(self) -> SetupController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Setup operations require known capabilities; call query_idn() first."
            )
        return SetupController(self.scpi)

    def _fft_controller(self) -> FFTController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "FFT operations require known capabilities; call query_idn() first."
            )
        return FFTController(self.scpi, self.capabilities)

    def _math_controller(self) -> MathController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Math operations require known capabilities; call query_idn() first."
            )
        return MathController(self.scpi, self.capabilities)

    def _screenshot_controller(self) -> ScreenshotController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Screenshot operations require known capabilities; call query_idn() first."
            )
        return ScreenshotController(self.scpi, self.capabilities)

    def _acquisition_controller(self) -> AcquisitionController:
        if self.capabilities is None:
            raise ParameterValidationError(
                "Acquisition operations require known capabilities; call query_idn() first."
            )
        return AcquisitionController(self.scpi)

    def _segmented_memory_controller(self) -> SegmentedMemoryController:
        return SegmentedMemoryController(self.scpi, self.capabilities)

    def __enter__(self) -> "Oscilloscope":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.close()
