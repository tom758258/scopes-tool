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
    validate_analog_channel,
    validate_channel_label,
    validate_channel_offset,
    validate_channel_scale,
)
from .errors import OscilloscopeError, ParameterValidationError
from .save_export import SavePwdState, validate_save_quoted_string
from .scope import Oscilloscope
from .status import OperationCompleteState, StatusRegisterState
from .trigger import (
    EdgeTriggerState, EdgeTriggerSourceState, EdgeTriggerSlopeState,
    EdgeTriggerLevelState, EdgeTriggerCouplingState, TriggerModeState,
    TriggerSweepState,
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


class _PlanningBackend:
    """Record Core commands without opening an instrument."""

    def __init__(self, capabilities: ScopeCapabilities) -> None:
        self.commands: list[str] = []
        self.timeout: int | None = None
        self.capabilities = capabilities

    def write(self, command: str) -> None:
        self.commands.append(command)

    def query(self, command: str) -> str:
        self.commands.append(command)
        if command == "*OPC?":
            return "1"
        if command.startswith("*STB") or command.startswith("*ESR"):
            return "0"
        if command.endswith(":MODe?") and command.startswith("ACQuire"):
            return "SAMple"
        if command.endswith(":TYPe?"):
            return "EDGE"
        if command.endswith(":MODe?"):
            return "AUTO"
        if command.endswith(":SOUrce?"):
            return "CH1"
        if command.endswith(":SLOpe?"):
            return "RISe"
        if command.endswith(":COUPling?"):
            return "DC"
        if command.endswith(":BANdwidth?"):
            return "TWEnty" if self.capabilities.series == "TBS2000B" else "ON"
        if command.endswith(":CWD?"):
            return '"/"'
        if command.endswith(":LABel?"):
            return '""'
        if command == "DISPlay:STYle?":
            return "VECtors"
        return "1"

    def set_timeout(self, timeout_ms: int | None) -> None:
        self.timeout = timeout_ms

    def close(self) -> None:
        pass


def _payload(raw: str, expected_header: str) -> str:
    """Strip only the expected optional Tek command header from a query response."""

    value = raw.strip()
    if not value.startswith((":", "*")):
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
        self.scpi.write(f"{self._trigger_root}:TYPe {_choice(mode, {'edge': 'EDGE'}, 'trigger type')}")

    def query_trigger_mode(self) -> TriggerModeState:
        value, raw = self._query(f"{self._trigger_root}:TYPe?")
        return TriggerModeState(_choice(value, {"EDGE": "edge"}, "trigger type response"), raw)

    def configure_trigger_sweep(self, mode: str) -> None:
        self.scpi.write(f"{self._trigger_root}:MODe {_choice(mode, {'auto': 'AUTO', 'normal': 'NORMal'}, 'trigger sweep')}")

    def query_trigger_sweep(self) -> TriggerSweepState:
        value, raw = self._query(f"{self._trigger_root}:MODe?")
        return TriggerSweepState(_choice(value, {"AUTO": "auto", "NORM": "normal", "NORMAL": "normal"}, "trigger sweep response"), raw)

    def configure_trigger_edge_source(self, *, source: str, source_channel: int | None = None) -> None:
        if source != "analog-channel" or source_channel is None:
            raise ParameterValidationError("Tek edge source must be an analog channel")
        self.scpi.write(f"{self._trigger_root}:EDGE:SOUrce CH{self._channel(source_channel)}")

    def query_trigger_edge_source(self) -> EdgeTriggerSourceState:
        value, raw = self._query(f"{self._trigger_root}:EDGE:SOUrce?")
        match = re.fullmatch(r"CH([1-4])", value.upper())
        if match is None:
            raise OscilloscopeError(f"Unsupported Tek edge source response: {raw!r}")
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
        assert source.source_channel is not None
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
    if not _name.startswith("_") and callable(_method) and _name not in _SUPPORTED_METHODS:
        setattr(TektronixOscilloscope, _name, _unsupported)
