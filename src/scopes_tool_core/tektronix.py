"""Tektronix command dialect for the registered TBS and TDS models."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping, Sequence

from .acquisition import AcquisitionConfig
from .acquisition import normalize_acquisition_type
from .capabilities import ScopeCapabilities, operation_supported
from .channel import (
    ChannelSummaryEntry, normalize_channel_units,
    validate_analog_channel,
    validate_channel_label,
    validate_channel_offset,
    validate_channel_scale,
)
from .errors import OscilloscopeError, ParameterValidationError
from .cursor import CursorState, cursor_auto_timebase_plan, validate_cursor_request
from .display import DisplayPersistence, validate_display_persistence
from .math import MathDisplayState, MathOperationState, MathOperatorState
from .measurements import validate_measurement_install_item
from .save_export import (
    _SAVE_COMPLETION_TIMEOUT_MS, SavePwdState, SaveImageFormatState, SaveBooleanState,
    SaveWaveformFormatState, SaveOperationResult, validate_save_quoted_string,
)
from .screenshot import (
    ScreenshotCapture, ScreenshotOptions, SCREENSHOT_TIMEOUT_MS,
    normalize_screenshot_background, normalize_screenshot_options,
    screenshot_bytes_from_values_for_format, validate_screenshot_capability,
)
from .scope import Oscilloscope
from .tektronix_simulator import TektronixSimulatorBackend
from .status import OperationCompleteState, StatusRegisterState
from .trigger import (
    EdgeTriggerState, EdgeTriggerSourceState, EdgeTriggerSlopeState,
    EdgeTriggerLevelState, EdgeTriggerCouplingState, TriggerModeState,
    TriggerSweepState, RuntTriggerState, TvTriggerState,
    runt_trigger_configure_commands, tv_trigger_configure_commands,
)


@dataclass(frozen=True)
class TekPostStatus:
    """Internal standard-event post-check result, distinct from an error queue."""

    value: int
    raw: str
    status_label = "Standard event status"
    is_system_error_queue = False

    @property
    def is_error(self) -> bool:
        return bool(self.value & 0x3C)

    def format(self) -> str:
        return f"SESR {self.raw} (error bits {self.value & 0x3C})"

    def to_json(self) -> dict[str, int | str]:
        return {"raw": self.raw, "value": self.value}


class _PlanningBackend(TektronixSimulatorBackend):
    """Plan using the same bounded dialect as simulated execution."""

    def __init__(self, capabilities: ScopeCapabilities) -> None:
        models = {"TBS2000B": "TBS2074B", "TDS2000B": "TDS2024B", "TBS1000B": "TBS1052B"}
        super().__init__(physical_model_id="tektronix-" + models[capabilities.series].lower())
        self.commands = self.history


def _payload(raw: str, expected_header: str) -> str:
    """Strip only the expected optional Tek command header from a query response."""

    value = raw.strip()
    if not value.startswith((":", "*")) and not re.match(r"[A-Za-z][A-Za-z0-9]*:", value):
        return value
    header, separator, payload = value.partition(" ")
    expected = expected_header.lstrip(":").rstrip("?").split(":")
    actual = header.lstrip(":").split(":")
    if expected[:2] in (["HORizontal", "MAIn"], ["TRIGger", "MAIn"]) and len(actual) == len(expected) - 1:
        expected = [expected[0], *expected[2:]]
    if not separator or len(actual) != len(expected):
        raise OscilloscopeError(f"Unexpected Tek response header: {raw!r}")
    for received, command in zip(actual, expected):
        minimum = "".join(char for char in command if char.isupper() or char.isdigit() or char == "*")
        if not (received.upper().startswith(minimum.upper()) and command.upper().startswith(received.upper())):
            raise OscilloscopeError(f"Unexpected Tek response header: {raw!r}")
    return payload.strip()


def _number(raw: str, header: str) -> float:
    try:
        number = float(_payload(raw, header))
    except ValueError as exc:
        raise OscilloscopeError(f"Invalid Tek numeric response: {raw!r}") from exc
    if not math.isfinite(number):
        raise OscilloscopeError(f"Invalid Tek numeric response: {raw!r}")
    return number


def _choice(value: str, choices: dict[str, str], name: str) -> str:
    try:
        key = value.lower() if value.lower() in choices else value.upper()
        return choices[key]
    except (AttributeError, KeyError) as exc:
        raise ParameterValidationError(f"Unsupported Tek {name}: {value!r}") from exc


def _boolean(raw: str, header: str) -> bool:
    value = _payload(raw, header).upper()
    if value in {"ON", "1"}:
        return True
    if value in {"OFF", "0"}:
        return False
    raise OscilloscopeError(f"Invalid Tek boolean response: {raw!r}")


class TektronixOscilloscope(Oscilloscope):
    """Core implementation of the supported existing-operation subset."""

    @classmethod
    def plan_webui_acquisition(cls, parameters: Mapping[str, object], capabilities: ScopeCapabilities) -> list[str]:
        backend = _PlanningBackend(capabilities)
        scope = cls(backend)
        scope.capabilities = capabilities
        if parameters.get("action") == "set":
            if "count" in parameters:
                scope.validate_acquisition_count(parameters["count"])
            if "type" in parameters:
                scope.set_acquisition_type(parameters["type"])
            if "count" in parameters:
                scope.set_acquisition_count(parameters["count"])
        scope.query_acquisition_config()
        backend.commands.append("*ESR?")
        return backend.commands

    @classmethod
    def plan_cli_operation(cls, args: object, capabilities: ScopeCapabilities) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
        command = getattr(args, "command")
        if not operation_supported(capabilities, command):
            raise ParameterValidationError(f"{command} is unsupported for this Tektronix model")
        if command == "identify":
            return ["*IDN?"], [], {"operation": "identify"}
        if command == "list-resources":
            return [], [], {"operation": "list-resources"}
        backend = _PlanningBackend(capabilities)
        scope = cls(backend)
        scope.capabilities = capabilities
        scope._plan_cli_action(args)
        explicit_status = command in {"system-clear-status", "system-opc", "system-status-byte", "system-standard-event"}
        if not explicit_status:
            backend.commands.append("*ESR?")
        business_commands = backend.commands if explicit_status else backend.commands[:-1]
        return backend.commands, [], {"operation": command, "commands": list(business_commands)}

    def _plan_cli_action(self, args: object) -> None:
        command = getattr(args, "command")
        if command == "run":
            self.run()
        elif command == "stop-acquisition":
            self.stop()
        elif command == "single":
            self.single()
        elif command == "force-trigger":
            self.force_trigger()
        elif command == "acquisition":
            if args.acq_query:
                self.query_acquisition_config()
            else:
                if args.acq_type is None:
                    raise ParameterValidationError("acquisition requires --type or --query")
                if args.acq_count is not None and normalize_acquisition_type(args.acq_type) != "AVERage":
                    raise ParameterValidationError("average count requires average mode")
                if args.acq_count is not None:
                    self.validate_acquisition_count(args.acq_count)
                self.set_acquisition_type(args.acq_type)
                if args.acq_count is not None:
                    self.set_acquisition_count(args.acq_count)
        elif command == "autoscale":
            channels = tuple(args.source_channel) if args.source_channel else None
            self.autoscale(channels, acquire_mode=args.acquire_mode, channels_mode=args.channels)
        elif command == "timebase-scale":
            self.query_timebase_scale() if args.timebase_scale_query else self.set_timebase_scale(args.timebase_scale_value)
        elif command == "timebase-position":
            self.query_timebase_position() if args.timebase_position_query else self.set_timebase_position(args.timebase_position_value)
        elif command in {"channel-display", "channel-bandwidth-limit", "channel-invert"}:
            action_name = {"channel-display": "display_action", "channel-bandwidth-limit": "bandwidth_action", "channel-invert": "invert_action"}[command]
            suffix = {"channel-display": "display", "channel-bandwidth-limit": "bandwidth_limit", "channel-invert": "invert"}[command]
            action = getattr(args, action_name)
            if action == "query":
                getattr(self, f"query_channel_{suffix}")(args.channel)
            else:
                getattr(self, f"set_channel_{suffix}")(args.channel, action == "on")
        elif command in {"channel-scale", "channel-offset", "channel-coupling", "channel-probe", "channel-label", "channel-probe-skew"}:
            query_field, value_field, suffix = {
                "channel-scale": ("scale_query", "scale_value", "scale"),
                "channel-offset": ("offset_query", "offset_value", "offset"),
                "channel-coupling": ("coupling_query", "coupling_value", "coupling"),
                "channel-probe": ("probe_query", "probe_ratio", "probe_ratio"),
                "channel-label": ("label_query", "label_text", "label"),
                "channel-probe-skew": ("probe_skew_query", "probe_skew_seconds", "probe_skew"),
            }[command]
            method = f"{'query' if getattr(args, query_field) else 'set'}_channel_{suffix}"
            values = (args.channel,) if getattr(args, query_field) else (args.channel, getattr(args, value_field))
            getattr(self, method)(*values)
        elif command == "channel-units":
            self.query_channel_units(args.channel) if args.units_query else self.set_channel_units(args.channel, args.units_value)
        elif command == "display-persistence":
            self.query_display_persistence() if args.query else self.set_display_persistence(args.seconds if args.seconds is not None else args.mode)
        elif command == "cursor":
            if args.cursor_query:
                self.query_cursor()
            elif args.cursor_off:
                self.cursor_off()
            else:
                self.configure_cursor(args.source_channel, x1_seconds=args.x1, x2_seconds=args.x2,
                    y1_volts=args.y1, y2_volts=args.y2, auto_timebase=args.auto_timebase, auto_vertical=args.auto_vertical)
                self.query_cursor()
        elif command == "math-display":
            self.query_math_display(args.function) if args.math_display_action == "query" else self.configure_math_display(args.function, args.math_display_action == "on")
        elif command == "math-operator":
            self.query_math_operator(args.function) if args.math_operator_query else self.configure_math_operator(args.function, args.math_operation, args.source1, args.source2)
        elif command == "measure-install":
            self.install_measurement(args.source_channel, args.item)
        elif command == "measure-clear":
            self.clear_measurements()
        elif command in {"sample-rate", "acquisition-points", "record-length"}:
            self._query_acquisition_readout(command, maximum=getattr(args, "sample_rate_maximum", False))
        elif command == "channel-summary":
            self.query_channel_summary()
        elif command == "trigger-mode":
            self.query_trigger_mode() if args.query else self.configure_trigger_mode(args.mode)
        elif command == "trigger-runt":
            if args.runt_query:
                self.query_runt_trigger()
            else:
                self.configure_runt_trigger(channel=args.channel, polarity=args.polarity, qualifier=args.qualifier,
                    time_seconds=args.time_seconds, low_level_volts=args.low_level_volts, high_level_volts=args.high_level_volts)
        elif command == "trigger-tv":
            self.query_tv_trigger() if args.tv_query else self.configure_tv_trigger(source_channel=args.source_channel,
                standard=args.standard, mode=args.mode, polarity=args.polarity, line=args.line)
        elif command in {"save-image-format", "save-waveform-format", "save-image-ink-saver"}:
            suffix = command.replace("-", "_")
            if args.query:
                getattr(self, f"query_{suffix}")()
            else:
                value = args.enabled if command == "save-image-ink-saver" else args.format
                getattr(self, f"configure_{suffix}")(value)
                if command != "save-image-ink-saver":
                    getattr(self, f"query_{suffix}")()
        elif command == "save-image":
            self.save_image(args.filename)
        elif command == "screenshot":
            options = ScreenshotOptions(format=args.format, ink_saver=args.ink_saver,
                                        palette=args.palette, layout=args.layout)
            validate_screenshot_capability(self.capabilities, options, query_hardcopy=args.query_hardcopy)
            self.capture_screenshot(options=options, background=args.background or "black")
        elif command == "display-vectors":
            if args.query:
                self.query_display_vectors()
            elif args.on:
                self.set_display_vectors_on()
            else:
                raise ParameterValidationError("display-vectors requires --query or --on")
        elif command == "reference-save":
            self.save_reference_waveform(args.slot, args.source_channel)
        elif command == "reference-display":
            self.query_reference_display(args.slot) if args.query else self.configure_reference_display(args.slot, args.state == "on")
        elif command == "save-pwd":
            self.query_save_pwd() if args.query else self.configure_save_pwd(args.path)
        elif command == "setup-save":
            self.save_setup(slot=args.slot, file_spec=args.setup_file)
        elif command == "setup-recall":
            self.recall_setup(slot=args.slot, file_spec=args.setup_file)
        elif command == "system-clear-status":
            self.clear_status()
        elif command == "system-opc":
            self.query_operation_complete()
        elif command == "system-status-byte":
            self.query_status_byte()
        elif command == "system-standard-event":
            self.query_standard_event_status()
        elif command == "trigger-edge":
            self.query_trigger_edge() if args.edge_query else self.configure_trigger_edge(args.source_channel, args.level, args.slope)
        elif command == "trigger-edge-source":
            self.query_trigger_edge_source() if args.trigger_edge_source_query else self.configure_trigger_edge_source(source="analog-channel" if args.source_channel is not None else args.source, source_channel=args.source_channel)
        elif command == "trigger-edge-slope":
            self.query_trigger_edge_slope() if args.trigger_edge_slope_query else self.configure_trigger_edge_slope(slope=args.slope)
        elif command == "trigger-edge-level":
            self.query_trigger_edge_level(source_channel=args.source_channel) if args.trigger_edge_level_query else self.configure_trigger_edge_level(source_channel=args.source_channel, level_volts=args.level_volts)
        elif command == "trigger-edge-coupling":
            self.query_trigger_edge_coupling() if args.trigger_edge_coupling_query else self.configure_trigger_edge_coupling(args.coupling)
        elif command == "trigger-sweep":
            self.query_trigger_sweep() if args.trigger_sweep_query else self.configure_trigger_sweep(args.mode)
        elif command == "trigger-holdoff":
            self.query_trigger_holdoff() if args.holdoff_query else self.set_trigger_holdoff(args.holdoff_seconds)
        else:
            raise ParameterValidationError(f"No Tek dry-run plan for {command}")

    @property
    def _b2(self) -> bool:
        return self.capabilities is not None and self.capabilities.series == "TBS2000B"

    @property
    def _trigger_root(self) -> str:
        return "TRIGger:A" if self._b2 else "TRIGger:MAIn"

    def _channel(self, channel: int) -> int:
        if self.capabilities is None:
            raise OscilloscopeError("Tek capabilities unavailable")
        return validate_analog_channel(channel, self.capabilities)

    def _b2_only(self, operation: str) -> None:
        if not self._b2:
            raise ParameterValidationError(f"{operation} is unsupported for this model")

    def _b1_only(self, operation: str) -> None:
        if self._b2:
            raise ParameterValidationError(f"{operation} is unsupported for this model")

    def _query(self, command: str) -> tuple[str, str]:
        raw = self.scpi.query(command)
        return _payload(raw, command), raw

    def _float(self, command: str) -> float:
        return _number(self.scpi.query(command), command)

    def _write_number(self, command: str, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ParameterValidationError("value must be a finite number")
        self.scpi.write(f"{command} {value:.12g}")

    def post_command_status(self, operation: str | None = None) -> TekPostStatus:
        """Read one SESR after an ordinary completed business operation."""

        if operation in {
            "identify",
            "system-clear-status", "system-opc", "system-status-byte",
            "system-standard-event",
        }:
            return TekPostStatus(0, "not read after explicit status operation")
        raw = self.scpi.query("*ESR?")
        number = _number(raw, "*ESR?")
        if not number.is_integer() or not 0 <= number <= 255:
            raise OscilloscopeError(f"Invalid Tek SESR response: {raw!r}")
        value = int(number)
        if value & 0x3C:
            raise OscilloscopeError(f"Tek command failed: raw SESR {raw!r}, error bits {value & 0x3C}")
        return TekPostStatus(value, raw)

    def post_webui_operation_status(self, operation: str) -> TekPostStatus:
        return self.post_command_status(operation)

    def uses_autoscale_error_recovery(self) -> bool:
        return False

    def clear_status(self) -> None:
        self.scpi.write("*CLS")

    def query_operation_complete(self) -> OperationCompleteState:
        raw = self.scpi.query("*OPC?")
        value = _number(raw, "*OPC?")
        if value != 1:
            raise OscilloscopeError(f"Invalid Tek OPC response: {raw!r}")
        return OperationCompleteState(True, raw)

    def _status_register(self, command: str) -> StatusRegisterState:
        raw = self.scpi.query(command)
        value = _number(raw, command)
        if not value.is_integer() or not 0 <= value <= 255:
            raise OscilloscopeError(f"Invalid Tek status response: {raw!r}")
        integer = int(value)
        return StatusRegisterState(integer, raw, tuple(bit for bit in range(8) if integer & (1 << bit)))

    def query_status_byte(self) -> StatusRegisterState:
        return self._status_register("*STB?")

    def query_standard_event_status(self) -> StatusRegisterState:
        return self._status_register("*ESR?")

    def run(self) -> None:
        self.scpi.write("ACQuire:STOPAfter RUNSTop")
        self.scpi.write("ACQuire:STATE ON")

    def stop(self) -> None:
        self.scpi.write("ACQuire:STATE OFF")

    def single(self) -> None:
        self.scpi.write("ACQuire:STATE OFF")
        self.scpi.write("ACQuire:STOPAfter SEQuence")
        self.scpi.write("ACQuire:STATE ON")

    def force_trigger(self) -> None:
        self.scpi.write("TRIGger FORCe")

    def set_acquisition_type(self, acquisition_type: str) -> None:
        normalized = "NORMal" if acquisition_type == "sample" else normalize_acquisition_type(acquisition_type)
        canonical, token = {
            "NORMal": ("normal", "SAMple"),
            "PEAK": ("peak", "PEAKdetect"),
            "AVERage": ("average", "AVErage"),
            "HRESolution": ("high_resolution", "HIRes"),
        }[normalized]
        if self.capabilities is None or self.capabilities.acquisition_modes is None or canonical not in self.capabilities.acquisition_modes:
            raise ParameterValidationError(f"Unsupported Tek acquisition mode: {acquisition_type!r}")
        self.scpi.write(f"ACQuire:MODe {token}")

    def query_acquisition_type(self) -> str:
        value, _ = self._query("ACQuire:MODe?")
        options = {"SAM": "normal", "SAMPLE": "normal", "PEAK": "peak",
                   "PEAKDETECT": "peak", "AVE": "average", "AVERAGE": "average",
                   "HIR": "high_resolution", "HIRES": "high_resolution",
                   "HIRESOLUTION": "high_resolution"}
        try:
            result = options[value.upper()]
        except KeyError as exc:
            raise OscilloscopeError(f"Invalid Tek acquisition mode: {value!r}") from exc
        if result == "high_resolution":
            self._b2_only("high-resolution acquisition")
        return result

    def validate_acquisition_count(self, count: int) -> int:
        valid = self.capabilities.average_counts if self.capabilities is not None else None
        if valid is None:
            raise OscilloscopeError("Tek averaging capabilities unavailable")
        if isinstance(count, bool) or not isinstance(count, int) or count not in valid:
            raise ParameterValidationError("Unsupported Tek average count")
        return count

    def set_acquisition_count(self, count: int) -> None:
        self.validate_acquisition_count(count)
        self.scpi.write(f"ACQuire:NUMAVg {count}")

    def query_acquisition_count(self) -> int:
        value = self._float("ACQuire:NUMAVg?")
        if not value.is_integer():
            raise OscilloscopeError("Invalid Tek average count response")
        return int(value)

    def query_acquisition_config(self) -> AcquisitionConfig:
        return AcquisitionConfig(self.query_acquisition_type(), self.query_acquisition_count())

    def autoscale(self, channels: Sequence[int] | None, *, acquire_mode: str | None = None,
                  channels_mode: str | None = None) -> None:
        if channels is not None or acquire_mode is not None or channels_mode is not None:
            raise ParameterValidationError("Tek autoscale supports no optional controls")
        self.scpi.write("AUTOSet EXECute")

    def set_timebase_scale(self, seconds_per_division: float) -> None:
        if seconds_per_division <= 0:
            raise ParameterValidationError("timebase scale must be positive")
        self._write_number("HORizontal:MAIn:SCAle", seconds_per_division)

    def query_timebase_scale(self) -> float:
        return self._float("HORizontal:MAIn:SCAle?")

    def set_timebase_position(self, seconds: float) -> None:
        self._b1_only("timebase-position")
        self._write_number("HORizontal:MAIn:POSition", seconds)

    def query_timebase_position(self) -> float:
        self._b1_only("timebase-position")
        return self._float("HORizontal:MAIn:POSition?")

    def set_channel_display(self, channel: int, enabled: bool) -> None:
        self.scpi.write(f"SELect:CH{self._channel(channel)} {'ON' if enabled else 'OFF'}")

    def query_channel_display(self, channel: int) -> bool:
        return _boolean(self.scpi.query(f"SELect:CH{self._channel(channel)}?"), f"SELect:CH{channel}?")

    def set_channel_scale(self, channel: int, volts_per_division: float) -> None:
        channel = self._channel(channel)
        self._write_number(f"CH{channel}:SCAle", validate_channel_scale(volts_per_division))

    def query_channel_scale(self, channel: int) -> float:
        return self._float(f"CH{self._channel(channel)}:SCAle?")

    def set_channel_offset(self, channel: int, volts: float) -> None:
        self._b2_only("channel-offset")
        channel = self._channel(channel)
        self._write_number(f"CH{channel}:OFFSet", validate_channel_offset(volts))

    def query_channel_offset(self, channel: int) -> float:
        self._b2_only("channel-offset")
        return self._float(f"CH{self._channel(channel)}:OFFSet?")

    def set_channel_coupling(self, channel: int, coupling: str) -> None:
        channel = self._channel(channel)
        self.scpi.write(f"CH{channel}:COUPling {_choice(coupling, {'ac': 'AC', 'dc': 'DC'}, 'coupling')}")

    def query_channel_coupling(self, channel: int) -> str:
        value, _ = self._query(f"CH{self._channel(channel)}:COUPling?")
        return _choice(value, {"AC": "ac", "DC": "dc"}, "coupling response")

    def set_channel_probe_ratio(self, channel: int, ratio: float) -> None:
        channel = self._channel(channel)
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or ratio <= 0:
            raise ParameterValidationError("probe ratio must be positive and finite")
        if self._b2:
            self._write_number(f"CH{channel}:PRObe:GAIN", 1 / ratio)
        else:
            if ratio not in {1, 10, 20, 50, 100, 500, 1000}:
                raise ParameterValidationError("Unsupported legacy Tek probe ratio")
            self._write_number(f"CH{channel}:PRObe", ratio)

    def query_channel_probe_ratio(self, channel: int) -> float:
        channel = self._channel(channel)
        value = self._float(f"CH{channel}:PRObe:GAIN?" if self._b2 else f"CH{channel}:PRObe?")
        if value <= 0:
            raise OscilloscopeError("Invalid Tek probe response")
        return 1 / value if self._b2 else value

    def set_channel_bandwidth_limit(self, channel: int, enabled: bool) -> None:
        channel = self._channel(channel)
        token = ("TWEnty" if enabled else "FULl") if self._b2 else ("ON" if enabled else "OFF")
        self.scpi.write(f"CH{channel}:BANdwidth {token}")

    def query_channel_bandwidth_limit(self, channel: int) -> bool:
        value, _ = self._query(f"CH{self._channel(channel)}:BANdwidth?")
        valid = {"TWE": True, "TWENTY": True, "FULL": False, "FUL": False} if self._b2 else {"ON": True, "OFF": False, "1": True, "0": False}
        try:
            return valid[value.upper()]
        except KeyError as exc:
            raise OscilloscopeError(f"Invalid Tek bandwidth response: {value!r}") from exc

    def set_channel_invert(self, channel: int, enabled: bool) -> None:
        self.scpi.write(f"CH{self._channel(channel)}:INVert {'ON' if enabled else 'OFF'}")

    def query_channel_invert(self, channel: int) -> bool:
        return _boolean(self.scpi.query(f"CH{self._channel(channel)}:INVert?"), f"CH{channel}:INVert?")

    def set_channel_label(self, channel: int, text: str) -> None:
        self._b2_only("channel-label")
        channel = self._channel(channel)
        if self.capabilities is None:
            raise OscilloscopeError("Tek capabilities unavailable")
        text = validate_channel_label(text, self.capabilities)
        self.scpi.write(f'CH{channel}:LABel "{text}"')

    def query_channel_label(self, channel: int) -> str:
        self._b2_only("channel-label")
        value, _ = self._query(f"CH{self._channel(channel)}:LABel?")
        return value.strip('"')

    def set_channel_probe_skew(self, channel: int, seconds: float) -> None:
        self._b2_only("channel-probe-skew")
        channel = self._channel(channel)
        if not -100e-9 <= seconds <= 100e-9:
            raise ParameterValidationError("Tek probe skew must be within -100 to 100 ns")
        self._write_number(f"CH{channel}:DESKew", seconds)

    def query_channel_probe_skew(self, channel: int) -> float:
        self._b2_only("channel-probe-skew")
        return self._float(f"CH{self._channel(channel)}:DESKew?")

    def set_display_vectors_on(self) -> None:
        self._b1_only("display-vectors")
        self.scpi.write("DISPlay:STYle VECtors")

    def query_display_vectors(self) -> tuple[bool, str]:
        self._b1_only("display-vectors")
        value, raw = self._query("DISPlay:STYle?")
        normalized = value.upper()
        if normalized in {"VEC", "VECTOR", "VECTORS"}:
            return True, raw.strip()
        if normalized in {"DOT", "DOTS"}:
            return False, raw.strip()
        raise OscilloscopeError(f"Invalid Tek display style response: {value!r}")

    def _reference(self, slot: int) -> str:
        if slot not in {1, 2} or isinstance(slot, bool):
            raise ParameterValidationError("Tek reference slot must be 1 or 2")
        return f"REF{slot}" if self._b2 else ("REFA" if slot == 1 else "REFB")

    def save_reference_waveform(self, slot: int, source_channel: int) -> None:
        reference = self._reference(slot)
        channel = self._channel(source_channel)
        self.scpi.write(f"SAVe:WAVEform CH{channel},{reference}")
        self.query_operation_complete()

    def configure_reference_display(self, slot: int, enabled: bool) -> None:
        self.scpi.write(f"SELect:{self._reference(slot)} {'ON' if enabled else 'OFF'}")

    def query_reference_display(self, slot: int) -> tuple[bool, str]:
        command = f"SELect:{self._reference(slot)}?"
        raw = self.scpi.query(command)
        return _boolean(raw, command), raw

    def configure_save_pwd(self, path: str) -> None:
        path = validate_save_quoted_string(path, label="Save path")
        self.scpi.write(f'FILESystem:CWD "{path}"')

    def query_save_pwd(self) -> SavePwdState:
        value, raw = self._query("FILESystem:CWD?")
        return SavePwdState(value.strip('"'), raw)

    def _setup_slot(self, slot: int | None, file_spec: str | None) -> int:
        if file_spec is not None or isinstance(slot, bool) or slot not in range(1, 10):
            raise ParameterValidationError("Tek setup supports slots 1 through 9 only")
        return slot

    def save_setup(self, *, slot: int | None = None, file_spec: str | None = None) -> None:
        self.scpi.write(f"SAVe:SETUp {self._setup_slot(slot, file_spec)}")

    def recall_setup(self, *, slot: int | None = None, file_spec: str | None = None) -> None:
        self.scpi.write(f"RECAll:SETUp {self._setup_slot(slot, file_spec)}")

    def configure_trigger_mode(self, mode: str) -> None:
        choices = {"edge": "EDGE", "glitch": "PULSE"}
        choices.update({"runt": "PULSE"} if self._b2 else {"tv": "VIDeo"})
        token = _choice(mode, choices, "trigger type")
        self.scpi.write(f"{self._trigger_root}:TYPe {token}")
        if self._b2 and token == "PULSE":
            self.scpi.write(f"{self._trigger_root}:PULSe:CLAss {'RUNT' if mode.lower() == 'runt' else 'WIDth'}")

    def query_trigger_mode(self) -> TriggerModeState:
        value, raw = self._query(f"{self._trigger_root}:TYPe?")
        choices = {"EDGE": "edge", "PULS": "glitch", "PULSE": "glitch"}
        if not self._b2:
            choices.update({"VID": "tv", "VIDEO": "tv"})
        mode = _choice(value, choices, "trigger type response")
        if self._b2 and mode == "glitch":
            pulse, pulse_raw = self._query(f"{self._trigger_root}:PULSe:CLAss?")
            mode = _choice(pulse, {"WID": "glitch", "WIDTH": "glitch", "RUNT": "runt"}, "pulse class response")
            raw = f"{raw};{pulse_raw}"
        return TriggerModeState(mode, raw)

    def configure_trigger_sweep(self, mode: str) -> None:
        self.scpi.write(f"{self._trigger_root}:MODe {_choice(mode, {'auto': 'AUTO', 'normal': 'NORMal'}, 'trigger sweep')}")

    def query_trigger_sweep(self) -> TriggerSweepState:
        value, raw = self._query(f"{self._trigger_root}:MODe?")
        return TriggerSweepState(_choice(value, {"AUTO": "auto", "NORM": "normal", "NORMAL": "normal"}, "trigger sweep response"), raw)

    def configure_trigger_edge_source(self, *, source: str, source_channel: int | None = None) -> None:
        if source == "analog-channel" and source_channel is not None:
            token = f"CH{self._channel(source_channel)}"
        elif source_channel is None:
            choices = {"line": "LINE"} if self._b2 else {"line": "ACLine", "external": "EXT"}
            token = _choice(source, choices, "edge source")
        else:
            raise ParameterValidationError("Tek non-channel source rejects source_channel")
        self.scpi.write(f"{self._trigger_root}:EDGE:SOUrce {token}")

    def query_trigger_edge_source(self) -> EdgeTriggerSourceState:
        value, raw = self._query(f"{self._trigger_root}:EDGE:SOUrce?")
        match = re.fullmatch(r"CH([1-4])", value.upper())
        if match is None:
            choices = {"LINE": "line"} if self._b2 else {"ACL": "line", "ACLINE": "line", "EXT": "external"}
            return EdgeTriggerSourceState(_choice(value, choices, "edge source response"), None, raw)
        channel = self._channel(int(match.group(1)))
        return EdgeTriggerSourceState("analog-channel", channel, raw)

    def configure_trigger_edge_slope(self, *, slope: str) -> None:
        token = _choice(slope, {"positive": "RISe", "negative": "FALL"}, "edge slope")
        self.scpi.write(f"{self._trigger_root}:EDGE:SLOpe {token}")

    def query_trigger_edge_slope(self) -> EdgeTriggerSlopeState:
        value, raw = self._query(f"{self._trigger_root}:EDGE:SLOpe?")
        return EdgeTriggerSlopeState(_choice(value, {"RISE": "positive", "RIS": "positive", "FALL": "negative"}, "edge slope response"), raw)

    def configure_trigger_edge_coupling(self, coupling: str) -> None:
        choices = {"dc": "DC", "lf-reject": "LFRej"}
        if not self._b2:
            choices["ac"] = "AC"
        token = _choice(coupling, choices, "edge coupling")
        self.scpi.write(f"{self._trigger_root}:EDGE:COUPling {token}")

    def query_trigger_edge_coupling(self) -> EdgeTriggerCouplingState:
        value, raw = self._query(f"{self._trigger_root}:EDGE:COUPling?")
        choices = {"DC": "dc", "LFREJ": "lf-reject", "LFREJECT": "lf-reject"}
        if not self._b2:
            choices["AC"] = "ac"
        return EdgeTriggerCouplingState(_choice(value, choices, "edge coupling response"), raw)

    def configure_trigger_edge_level(self, *, source_channel: int, level_volts: float) -> None:
        self._b2_only("trigger-edge-level")
        self._write_number(f"{self._trigger_root}:LEVel:CH{self._channel(source_channel)}", level_volts)

    def query_trigger_edge_level(self, *, source_channel: int) -> EdgeTriggerLevelState:
        self._b2_only("trigger-edge-level")
        channel = self._channel(source_channel)
        command = f"{self._trigger_root}:LEVel:CH{channel}?"
        raw = self.scpi.query(command)
        return EdgeTriggerLevelState(channel, _number(raw, command), raw)

    def configure_trigger_edge(self, source_channel: int, level_volts: float, slope: str) -> None:
        channel = self._channel(source_channel)
        token = _choice(slope, {"positive": "RISe", "negative": "FALL"}, "edge slope")
        if not math.isfinite(level_volts):
            raise ParameterValidationError("edge level must be finite")
        self.configure_trigger_edge_source(source="analog-channel", source_channel=channel)
        command = f"{self._trigger_root}:LEVel:CH{channel}" if self._b2 else f"{self._trigger_root}:LEVel"
        self._write_number(command, level_volts)
        self.scpi.write(f"{self._trigger_root}:EDGE:SLOpe {token}")

    def query_trigger_edge(self) -> EdgeTriggerState:
        source = self.query_trigger_edge_source()
        if source.source_channel is None:
            raise ParameterValidationError("Combined Tek edge trigger requires an analog source")
        command = f"{self._trigger_root}:LEVel:CH{source.source_channel}?" if self._b2 else f"{self._trigger_root}:LEVel?"
        level = self._float(command)
        slope = self.query_trigger_edge_slope().slope
        assert slope is not None
        return EdgeTriggerState(source.source_channel, level, slope)

    def set_trigger_holdoff(self, seconds: float) -> None:
        minimum, maximum = (40e-9, 8.0) if self._b2 else (500e-9, 10.0)
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not minimum <= seconds <= maximum:
            raise ParameterValidationError("Unsupported Tek trigger holdoff")
        command = f"{self._trigger_root}:HOLDOff:TIMe" if self._b2 else f"{self._trigger_root}:HOLDOff:VALue"
        self._write_number(command, seconds)

    def query_trigger_holdoff(self) -> float:
        command = f"{self._trigger_root}:HOLDOff:TIMe?" if self._b2 else f"{self._trigger_root}:HOLDOff:VALue?"
        return self._float(command)

    def _units_available(self, channel: int) -> bool:
        return not self._b2 or channel in (1, 2)

    def set_channel_units(self, channel: int, units: str) -> None:
        channel = self._channel(channel)
        if not self._units_available(channel):
            raise ParameterValidationError("Channel units are unsupported for this channel")
        token = {"volt": "V", "amp": "A"}[normalize_channel_units(units)]
        self.scpi.write(f"CH{channel}:YUNit {token}")

    def query_channel_units(self, channel: int) -> str:
        channel = self._channel(channel)
        if not self._units_available(channel):
            raise ParameterValidationError("Channel units are unsupported for this channel")
        value, _ = self._query(f"CH{channel}:YUNit?")
        return _choice(value.strip('"'), {"V": "volt", "A": "amp"}, "channel units response")

    def query_channel_summary(self) -> tuple[ChannelSummaryEntry, ...]:
        return tuple(ChannelSummaryEntry(
            channel=channel, display=self.query_channel_display(channel),
            label=self.query_channel_label(channel) if self._b2 else None,
            scale=self.query_channel_scale(channel), range=None,
            offset=self.query_channel_offset(channel) if self._b2 else None,
            coupling=self.query_channel_coupling(channel), impedance=None,
            invert=self.query_channel_invert(channel),
            bandwidth_limit=self.query_channel_bandwidth_limit(channel),
            units=self.query_channel_units(channel) if self._units_available(channel) else None,
            vernier=None, probe_ratio=self.query_channel_probe_ratio(channel),
            probe_skew=self.query_channel_probe_skew(channel) if self._b2 else None,
        ) for channel in range(1, self.capabilities.analog_channels + 1))

    def set_display_persistence(self, value: str | float) -> None:
        mode, seconds = validate_display_persistence(value, self.capabilities)
        token = "OFF" if mode == "minimum" else "INFInite" if mode == "infinite" else f"{seconds:g}"
        if self._b2:
            if mode != "minimum":
                self.scpi.write(f"DISplay:PERSistence:VALUe {token}")
            self.scpi.write(f"DISplay:PERSistence:STATe {'OFF' if mode == 'minimum' else 'ON'}")
        else:
            self.scpi.write(f"DISplay:PERSistence {token}")

    def query_display_persistence(self) -> DisplayPersistence:
        if self._b2:
            state, state_raw = self._query("DISplay:PERSistence:STATe?")
            value, raw = self._query("DISplay:PERSistence:VALUe?")
            if not _boolean(state, "DISplay:PERSistence:STATe?"):
                return DisplayPersistence("minimum", None, f"{state_raw};{raw}")
            raw = f"{state_raw};{raw}"
        else:
            value, raw = self._query("DISplay:PERSistence?")
        if value.upper() == "OFF":
            return DisplayPersistence("minimum", None, raw)
        if value.upper() in {"INF", "INFI", "INFINITE"}:
            return DisplayPersistence("infinite", None, raw)
        _, seconds = validate_display_persistence(value)
        if seconds is None or (not self._b2 and seconds not in self.capabilities.display_persistence_seconds):
            raise OscilloscopeError(f"Unsupported Tek persistence response: {raw!r}")
        return DisplayPersistence(None, seconds, raw)

    def cursor_off(self) -> None:
        self.scpi.write("CURSor:FUNCtion OFF")

    def query_cursor(self) -> CursorState:
        mode, _ = self._query("CURSor:FUNCtion?")
        x1 = x2 = y1 = y2 = dx = dy = None
        active = mode.upper()
        if active == "OFF":
            return CursorState(mode, x1, x2, y1, y2, dx, dy, None)
        source, _ = self._query("SELect:CONTROl?" if self._b2 else "CURSor:SELect:SOUrce?")
        # FFT positions remain frequency-valued even when the unit selector says seconds.
        time_source = source.upper() in {"CH1", "CH2", "CH3", "CH4", "MATH", "REF1", "REF2", "REFA", "REFB"}
        if source.upper() == "MATH":
            expression, _ = self._query("MATH:DEFINE?")
            time_source = not expression.strip('"').upper().startswith("FFT")
        if active in ({"TIME", "SCREEN"} if self._b2 else {"VBA", "VBARS"}) and time_source:
            units, _ = self._query("CURSor:VBArs:UNIts?")
            if units.upper() in {"SECO", "SECONDS"}:
                x1 = self._float("CURSor:VBArs:POSITION1?")
                x2 = self._float("CURSor:VBArs:POSITION2?")
                dx = self._float("CURSor:VBArs:DELTa?")
        if active in ({"AMPL", "AMPLITUDE", "SCREEN"} if self._b2 else {"HBA", "HBARS"}):
            units, _ = self._query("CURSor:HBArs:UNIts?")
            volts = False
            voltage_units = {"BASE", "BAS"} if self._b2 else {"VOLTS", "V"}
            voltage_sources = {f"CH{channel}" for channel in range(1, self.capabilities.analog_channels + 1)
                               if self._units_available(channel)}
            if units.upper() in voltage_units and source.upper() in voltage_sources:
                volts = self.query_channel_units(int(source[-1])) == "volt"
            if volts:
                y1 = self._float("CURSor:HBArs:POSITION1?")
                y2 = self._float("CURSor:HBArs:POSITION2?")
                dy = self._float("CURSor:HBArs:DELTa?")
        return CursorState(mode, x1, x2, y1, y2, dx, dy, None)

    def configure_cursor(self, source_channel: int, *, x1_seconds: float | None = None,
                         x2_seconds: float | None = None, y1_volts: float | None = None,
                         y2_volts: float | None = None, auto_timebase: bool = False,
                         auto_vertical: bool = False) -> None:
        validate_cursor_request(self.capabilities, x1_seconds=x1_seconds, x2_seconds=x2_seconds,
                                y1_volts=y1_volts, y2_volts=y2_volts,
                                auto_timebase=auto_timebase, auto_vertical=auto_vertical)
        channel = self._channel(source_channel)
        x_axis = x1_seconds is not None or x2_seconds is not None
        values = (x1_seconds, x2_seconds) if x_axis else (y1_volts, y2_volts)
        if x_axis:
            units, _ = self._query("CURSor:VBArs:UNIts?")
            if units.upper() not in {"SECO", "SECONDS"}:
                raise ParameterValidationError("X cursors require existing seconds units")
            scale, position = self.query_timebase_scale(), self.query_timebase_position()
            if auto_timebase:
                plan = cursor_auto_timebase_plan(scale, position, x1_seconds=x1_seconds, x2_seconds=x2_seconds)
                if plan.changed:
                    self.set_timebase_scale(plan.target_scale_seconds_per_division)
                    scale = self.query_timebase_scale()
            if any(value is not None and abs(value - position) > 5 * scale for value in values):
                raise ParameterValidationError("X cursor position is outside the graticule")
        else:
            if self.query_channel_units(channel) != "volt":
                raise ParameterValidationError("Y cursors require a channel with volt units")
            units, _ = self._query("CURSor:HBArs:UNIts?")
            if units.upper() not in {"VOLTS", "V"}:
                raise ParameterValidationError("Y cursors require existing volts units")
            scale = self.query_channel_scale(channel)
            position = self._float(f"CH{channel}:POSition?")
            if any(value is not None and abs(value / scale + position) > 4 for value in values):
                raise ParameterValidationError("Y cursor position is outside the graticule")
        axis = "VBArs" if x_axis else "HBArs"
        self.scpi.write(f"CURSor:SELect:SOUrce CH{channel}")
        self.scpi.write(f"CURSor:FUNCtion {axis}")
        for index, value in enumerate(values, 1):
            if value is not None:
                self._write_number(f"CURSor:{axis}:POSITION{index}", value)

    def _math_function(self, function: int) -> None:
        if isinstance(function, bool) or function != 1:
            raise ParameterValidationError("Tek Math supports function 1 only")

    def configure_math_display(self, function: int, enabled: bool) -> None:
        self._math_function(function)
        self.scpi.write(f"SELect:MATH {'ON' if enabled else 'OFF'}")

    def query_math_display(self, function: int) -> MathDisplayState:
        self._math_function(function)
        raw = self.scpi.query("SELect:MATH?")
        return MathDisplayState(function, _boolean(raw, "SELect:MATH?"), raw)

    def configure_math_operator(self, function: int, operation: str, source1: str, source2: str) -> None:
        self._math_function(function)
        symbol = _choice(operation, {"add": "+", "subtract": "-", "multiply": "*"}, "Math operation")
        sources = {f"channel{i}": f"CH{i}" for i in range(1, self.capabilities.analog_channels + 1)}
        expression = _choice(source1, sources, "Math source") + symbol + _choice(source2, sources, "Math source")
        if expression not in self.capabilities.math_expressions:
            raise ParameterValidationError("Unsupported Tek Math expression")
        self.scpi.write(f'MATH:DEFINE "{expression}"')

    def query_math_operator(self, function: int) -> MathOperatorState:
        self._math_function(function)
        value, raw = self._query("MATH:DEFINE?")
        expression = value.strip('"').upper()
        if expression not in self.capabilities.math_expressions:
            raise OscilloscopeError(f"Unsupported Tek Math expression: {raw!r}")
        first, symbol, second = re.fullmatch(r"(CH[1-4])([+*-])(CH[1-4])", expression).groups()
        return MathOperatorState(function, {"+": "add", "-": "subtract", "*": "multiply"}[symbol],
                                 raw, f"channel{first[-1]}", first, f"channel{second[-1]}", second)

    def query_math_operation(self, function: int) -> MathOperationState:
        state = self.query_math_operator(function)
        return MathOperationState(function, "operator", state.operation, state.operation_raw)

    def _measurement_types(self) -> dict[str, str]:
        return {
            "vpp": "PK2Pk", "vavg": "MEAN", "vrms": "RMS", "frequency": "FREQuency",
            "period": "PERIod", "minimum": "MINImum", "maximum": "MAXimum",
            "rise_time": "RISe", "fall_time": "FALL", "positive_width": "PWIdth", "negative_width": "NWIdth",
            "amplitude": "AMPlitude", "top": "HIGH", "base": "LOW", "overshoot": "POVERshoot", "preshoot": "NOVERshoot",
            "duty_cycle": "PDUty", "negative_duty_cycle": "NDUty", "area": "AREA",
            "positive_edges": "PEDGECount" if self._b2 else "REDGECount",
            "negative_edges": "NEDGECount" if self._b2 else "FEDGECount",
            "positive_pulses": "PPULSECount", "negative_pulses": "NPULSECount",
        }

    def _measurement_slots(self) -> range:
        return range(1, 6 if self.capabilities.series == "TDS2000B" else 7)

    def install_measurement(self, channel: int, item: str) -> None:
        channel = self._channel(channel)
        item = validate_measurement_install_item(item, self.capabilities)
        token = self._measurement_types()[item]
        source_name = "SOUrce1" if self._b2 else "SOUrce"
        unused = matching = None
        for slot in self._measurement_slots():
            root = f"MEASUrement:MEAS{slot}"
            if self._b2:
                available = not _boolean(self.scpi.query(f"{root}:STATE?"), f"{root}:STATE?")
                if available:
                    unused = unused or slot
                    continue
            kind, _ = self._query(f"{root}:TYPe?")
            if not self._b2 and kind.upper() == "NONE":
                unused = unused or slot
                continue
            # Match documented abbreviated or full type readbacks.
            minimum = ''.join(c for c in token if c.isupper() or c.isdigit())
            if kind.upper().startswith(minimum) and token.upper().startswith(kind.upper()):
                source, _ = self._query(f"{root}:{source_name}?")
                if source.upper() == f"CH{channel}":
                    matching = slot
                    break
        slot = matching or unused
        if slot is None:
            raise ParameterValidationError("Tek measurement bank is full")
        if matching is None:
            root = f"MEASUrement:MEAS{slot}"
            self.scpi.write(f"{root}:{source_name} CH{channel}")
            self.scpi.write(f"{root}:TYPe {token}")
            if self._b2:
                self.scpi.write(f"{root}:STATE ON")

    def clear_measurements(self) -> None:
        for slot in self._measurement_slots():
            self.scpi.write(f"MEASUrement:MEAS{slot}:" + ("STATE OFF" if self._b2 else "TYPe NONE"))

    def configure_save_image_format(self, format: str) -> None:
        self._b2_only("save-image-format")
        token = _choice(format, {"png": "PNG", "bmp": "BMP"}, "save image format")
        self.scpi.write(f"SAVe:IMAge:FILEFormat {token}")

    def query_save_image_format(self) -> SaveImageFormatState:
        self._b2_only("save-image-format")
        value, raw = self._query("SAVe:IMAge:FILEFormat?")
        return SaveImageFormatState(_choice(value, {"PNG": "png", "BMP": "bmp"}, "save image format response"), raw)

    def configure_save_image_ink_saver(self, enabled: bool) -> None:
        self._b1_only("save-image-ink-saver")
        self.scpi.write(f"HARDCopy:INKSaver {'ON' if enabled else 'OFF'}")

    def query_save_image_ink_saver(self) -> SaveBooleanState:
        self._b1_only("save-image-ink-saver")
        raw = self.scpi.query("HARDCopy:INKSaver?")
        return SaveBooleanState(_boolean(raw, "HARDCopy:INKSaver?"), raw)

    def save_image(self, filename: str) -> SaveOperationResult:
        filename = validate_save_quoted_string(filename, label="Save filename")
        command = f'SAVe:IMAge "{filename}"'
        original_timeout = self.scpi.timeout
        try:
            self.scpi.set_timeout(_SAVE_COMPLETION_TIMEOUT_MS)
            self.scpi.write(command)
            complete = self.query_operation_complete()
            return SaveOperationResult("save-image", filename, command, complete.raw)
        finally:
            self.scpi.set_timeout(original_timeout)

    def configure_save_waveform_format(self, format: str) -> None:
        self._b2_only("save-waveform-format")
        token = _choice(format, {"csv": "SPREADSheet"}, "save waveform format")
        self.scpi.write(f"SAVe:WAVEform:FILEFormat {token}")

    def query_save_waveform_format(self) -> SaveWaveformFormatState:
        self._b2_only("save-waveform-format")
        value, raw = self._query("SAVe:WAVEform:FILEFormat?")
        return SaveWaveformFormatState(_choice(value, {"SPREADS": "csv", "SPREADSHEET": "csv"}, "waveform format response"), raw)

    def capture_screenshot(self, *, options: ScreenshotOptions, background: str = "black") -> ScreenshotCapture:
        options = normalize_screenshot_options(options)
        background = normalize_screenshot_background(background)
        validate_screenshot_capability(self.capabilities, options)
        desired_ink = options.ink_saver if options.ink_saver is not None else background == "white"
        settings = [("HARDCopy:FORMat", "BMP"), ("HARDCopy:PORT", "USB"),
                    ("HARDCopy:INKSaver", "ON" if desired_ink else "OFF")]
        if options.layout is not None:
            settings.append(("HARDCopy:LAYout", "LANdscape" if options.layout == "landscape" else "PORTRait"))
        originals = [(command, self._query(command + "?")[0], desired) for command, desired in settings]
        restore = []
        original_timeout = self.scpi.timeout
        try:
            self.scpi.set_timeout(SCREENSHOT_TIMEOUT_MS)
            for command, original, desired in originals:
                same = (_boolean(original, command + "?") == desired_ink
                        if command.endswith("INKSaver") else original.upper() == desired.upper())
                if not same:
                    restore.append((command, original))
                    self.scpi.write(f"{command} {desired}")
            self.scpi.write("HARDCopy STARt")
            data = screenshot_bytes_from_values_for_format(self.scpi.read_raw(), "bmp")
            return ScreenshotCapture("BMP", None, data, "white" if desired_ink else "black")
        finally:
            try:
                # Attempt every restoration even if one instrument write fails.
                from contextlib import ExitStack
                with ExitStack() as stack:
                    for command, original in restore:
                        stack.callback(self.scpi.write, f"{command} {original}")
            finally:
                self.scpi.set_timeout(original_timeout)

    def configure_runt_trigger(self, *, channel: int, polarity: str, qualifier: str,
                               low_level_volts: float, high_level_volts: float,
                               time_seconds: float | None = None) -> None:
        self._b2_only("trigger-runt")
        polarity, qualifier = polarity.strip().lower(), qualifier.strip().lower()
        runt_trigger_configure_commands(channel=channel, polarity=polarity, qualifier=qualifier,
            low_level_volts=low_level_volts, high_level_volts=high_level_volts,
            time_seconds=time_seconds, capabilities=self.capabilities)
        self.configure_trigger_mode("runt")
        self.scpi.write(f"TRIGger:A:RUNT:SOUrce CH{channel}")
        self._write_number(f"TRIGger:A:LOWerthreshold:CH{channel}", low_level_volts)
        self._write_number(f"TRIGger:A:UPPerthreshold:CH{channel}", high_level_volts)
        self.scpi.write(f"TRIGger:A:RUNT:POLarity {'POSitive' if polarity == 'positive' else 'NEGative'}")
        if time_seconds is not None:
            self._write_number("TRIGger:A:RUNT:WIDth", time_seconds)
        token = {"none": "OCCURS", "less-than": "LESSthan", "greater-than": "MOREthan"}[qualifier]
        self.scpi.write(f"TRIGger:A:RUNT:WHEn {token}")

    def query_runt_trigger(self) -> RuntTriggerState:
        self._b2_only("trigger-runt")
        mode = self.query_trigger_mode()
        source, source_raw = self._query("TRIGger:A:RUNT:SOUrce?")
        if source.upper() not in {"CH1", "CH2"}:
            raise OscilloscopeError("Unsupported Tek runt source")
        channel = int(source[-1])
        commands = {"polarity": "TRIGger:A:RUNT:POLarity?", "qualifier": "TRIGger:A:RUNT:WHEn?",
                    "time": "TRIGger:A:RUNT:WIDth?", "low_level": f"TRIGger:A:LOWerthreshold:CH{channel}?",
                    "high_level": f"TRIGger:A:UPPerthreshold:CH{channel}?"}
        values = {key: self._query(command) for key, command in commands.items()}
        raw = {"mode": mode.raw_mode, "source": source_raw, **{key: value[1] for key, value in values.items()}}
        polarity = _choice(values["polarity"][0], {"POS": "positive", "POSITIVE": "positive", "NEG": "negative", "NEGATIVE": "negative"}, "runt polarity response")
        qualifier = _choice(values["qualifier"][0], {"OCCURS": "none", "LESS": "less-than", "LESSTHAN": "less-than", "MORE": "greater-than", "MORETHAN": "greater-than"}, "runt qualifier response")
        return RuntTriggerState(mode.mode, source, "channel", channel, polarity, qualifier,
            _number(raw["time"], commands["time"]), _number(raw["low_level"], commands["low_level"]),
            _number(raw["high_level"], commands["high_level"]), raw)

    def configure_tv_trigger(self, *, source_channel: int, standard: str, mode: str,
                             polarity: str, line: int | None = None) -> TvTriggerState:
        self._b1_only("trigger-tv")
        standard, mode, polarity = standard.strip().lower(), mode.strip().lower(), polarity.strip().lower()
        tv_trigger_configure_commands(source_channel=source_channel, standard=standard, mode=mode,
            polarity=polarity, line=line, capabilities=self.capabilities)
        self.configure_trigger_mode("tv")
        root = "TRIGger:MAIn:VIDeo"
        self.scpi.write(f"{root}:SOUrce CH{source_channel}")
        self.scpi.write(f"{root}:STANdard {standard.upper()}")
        self.scpi.write(f"{root}:POLarity {'INVert' if polarity == 'positive' else 'NORMal'}")
        self.scpi.write(f"{root}:SYNC " + {"field1": "ODD", "field2": "EVEN", "all-fields": "FIELD", "all-lines": "LINE"}[mode])
        return self.query_tv_trigger()

    def query_tv_trigger(self) -> TvTriggerState:
        self._b1_only("trigger-tv")
        mode = self.query_trigger_mode()
        root = "TRIGger:MAIn:VIDeo"
        source, source_raw = self._query(f"{root}:SOUrce?")
        match = re.fullmatch(r"CH([1-4])", source.upper())
        if match is None:
            raise OscilloscopeError("Unsupported Tek TV source")
        channel = self._channel(int(match[1]))
        standard, standard_raw = self._query(f"{root}:STANdard?")
        sync, sync_raw = self._query(f"{root}:SYNC?")
        polarity, polarity_raw = self._query(f"{root}:POLarity?")
        return TvTriggerState(mode.mode, source_raw, channel, standard_raw,
            _choice(standard, {"NTSC": "ntsc", "PAL": "pal"}, "TV standard response"), sync_raw,
            _choice(sync, {"ODD": "field1", "EVEN": "field2", "FIELD": "all-fields", "LINE": "all-lines"}, "TV sync response"),
            "", None, polarity_raw, _choice(polarity, {"INV": "positive", "INVERT": "positive", "NORM": "negative", "NORMAL": "negative"}, "TV polarity response"))

    def _query_acquisition_readout(self, operation: str, *, maximum: bool = False) -> tuple[float | int, str, str]:
        if not operation_supported(self.capabilities, operation):
            raise ParameterValidationError(f"{operation} is unsupported for this model")
        if operation == "sample-rate":
            command = "ACQuire:MAXSamplerate?" if maximum else "HORizontal:SAMPLERate?"
        else:
            command = "HORizontal:RECOrdlength?"
        raw = self.scpi.query(command)
        value = _number(raw, command)
        if value <= 0 or (operation != "sample-rate" and not value.is_integer()):
            raise OscilloscopeError(f"Invalid Tek acquisition readout: {raw!r}")
        return (value if operation == "sample-rate" else int(value)), raw, command

    def _query_instrument_summary(self) -> dict[str, object]:
        entries = self.query_channel_summary()
        channels = [{key: entry.to_json()[key] for key in ("channel", "display", "units", "scale", "offset")} for entry in entries]
        mode = self.query_trigger_mode().mode
        trigger = dict(type=mode, source=None, source_channel=None, level=None, units=None,
                       slope=None, sweep=self.query_trigger_sweep().mode)
        if mode == "edge":
            source = self.query_trigger_edge_source()
            trigger.update(source=source.source, source_channel=source.source_channel,
                           slope=self.query_trigger_edge_slope().slope)
            if source.source_channel is not None:
                channel = source.source_channel
                trigger['level'] = self._float(f"{self._trigger_root}:LEVel:CH{channel}?" if self._b2 else f"{self._trigger_root}:LEVel?")
                trigger['units'] = entries[channel - 1].units
        position = None
        if not self._b2:
            position = self.query_timebase_position()
        elif _boolean(self.scpi.query("HORizontal:DELay:MODe?"), "HORizontal:DELay:MODe?"):
            position = self._float("HORizontal:DELay:TIMe?")
        return dict(channels=channels, timebase=dict(scale=self.query_timebase_scale(), position=position),
                    trigger=trigger, acquisition={"mode": "unknown"})


def _unsupported(self: TektronixOscilloscope, *args: object, **kwargs: object) -> None:
    raise ParameterValidationError("Operation is unsupported for this Tektronix model")


_SUPPORTED_METHODS = {
    "query_idn", "close", "post_command_status", "post_webui_operation_status",
    "uses_autoscale_error_recovery",
    "validate_acquisition_count",
    "run", "stop", "single",
    "force_trigger", "set_acquisition_type", "query_acquisition_type",
    "set_acquisition_count", "query_acquisition_count", "query_acquisition_config",
    "autoscale", "set_timebase_scale", "query_timebase_scale",
    "set_timebase_position", "query_timebase_position", "set_channel_display",
    "query_channel_display", "set_channel_scale", "query_channel_scale",
    "set_channel_offset", "query_channel_offset", "set_channel_coupling",
    "query_channel_coupling", "set_channel_probe_ratio", "query_channel_probe_ratio",
    "set_channel_bandwidth_limit", "query_channel_bandwidth_limit",
    "set_channel_invert", "query_channel_invert", "set_channel_label",
    "query_channel_label", "set_channel_probe_skew", "query_channel_probe_skew",
    "set_display_vectors_on", "query_display_vectors", "save_reference_waveform",
    "configure_reference_display", "query_reference_display", "configure_save_pwd",
    "query_save_pwd", "save_setup", "recall_setup", "configure_trigger_mode",
    "query_trigger_mode", "configure_trigger_sweep", "query_trigger_sweep",
    "configure_trigger_edge_source", "query_trigger_edge_source",
    "configure_trigger_edge_slope", "query_trigger_edge_slope",
    "configure_trigger_edge_coupling", "query_trigger_edge_coupling",
    "configure_trigger_edge_level", "query_trigger_edge_level",
    "configure_trigger_edge", "query_trigger_edge", "set_trigger_holdoff",
    "query_trigger_holdoff", "clear_status", "query_operation_complete",
    "query_status_byte", "query_standard_event_status",
}

for _name, _method in vars(Oscilloscope).items():
    if not _name.startswith("_") and callable(_method) and _name not in _SUPPORTED_METHODS and _name not in vars(TektronixOscilloscope):
        setattr(TektronixOscilloscope, _name, _unsupported)
