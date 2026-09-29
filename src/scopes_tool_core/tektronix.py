"""Tektronix command dialect for the registered TBS and TDS models."""

from __future__ import annotations

from dataclasses import dataclass, replace
import csv
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
from .measurements import (
    validate_measurement_install_item, measurement_query, normalize_measurement_item,
    parse_measurement_result, MeasurementResult,
)
from .reference import ReferenceWaveformState
from .waveform import (
    WaveformCapture, WaveformPreamble, MultiChannelWaveformCapture,
    validate_waveform_points, validate_waveform_channels, convert_byte_waveform,
    validate_waveform_vertical_unit,
)
from .errors import WaveformResponseError
from .workflow import StopRequested
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
    parse_tv_line_readback, GlitchTriggerState, TriggerWaitConfig, TriggerWaitResult,
    glitch_trigger_configure_commands, normalize_glitch_qualifier,
    normalize_glitch_polarity, validate_trigger_wait_config,
    _trigger_wait_result, _wait_for_trigger_poll,
    runt_trigger_configure_commands, tv_trigger_configure_commands,
)


@dataclass(frozen=True)
class TekPostStatus:
    """Internal standard-event post-check result, distinct from an error queue."""

    value: int
    raw: str
    event_raw: str | None = None
    events: tuple[dict[str, object], ...] = ()
    complete: bool = True
    status_label = "Standard event status"
    is_system_error_queue = False

    @property
    def is_error(self) -> bool:
        return not self.complete or bool(self.value & 0x3C) or any(
            event["category"] == "error" for event in self.events
        )

    def format(self) -> str:
        summary = f"SESR {self.raw} (error bits {self.value & 0x3C})"
        return summary if self.event_raw is None else f"{summary}; events {self.event_raw}"

    def to_json(self) -> dict[str, object]:
        result = {"raw": self.raw, "value": self.value}
        if self.event_raw is not None:
            result.update(source="tektronix-sesr", event_raw=self.event_raw,
                          events=list(self.events), complete=self.complete,
                          destructive_read=True, is_error=self.is_error)
        return result


class _PlanningBackend(TektronixSimulatorBackend):
    """Plan using the same bounded dialect as simulated execution."""

    def __init__(self, capabilities: ScopeCapabilities) -> None:
        if capabilities.physical_model_id is None:
            raise ParameterValidationError("Tek planning requires a registered physical model")
        from .capabilities import capabilities_for_model_id
        if capabilities != capabilities_for_model_id(capabilities.physical_model_id):
            raise ParameterValidationError("Planning capabilities do not match the registered physical model")
        super().__init__(physical_model_id=capabilities.physical_model_id)
        self.commands = self.history

    def write(self, command: str) -> None:
        if re.fullmatch(r"RECALL:SETUP [1-9]", command, re.IGNORECASE):
            # A plan cannot inspect the instrument's stored setups.
            self.history.append(command)
            return
        super().write(command)


def _payload(raw: str, expected_header: str) -> str:
    """Strip only the expected optional Tek command header from a query response."""

    value = raw.strip()
    if not value.startswith((":", "*")) and not re.match(r"[A-Za-z][A-Za-z0-9]*:", value):
        return value
    header, separator, payload = value.partition(" ")
    expected = expected_header.lstrip(":").rstrip("?").split(":")
    actual = header.lstrip(":").split(":")
    if len(actual) > 2 and actual[2].upper() == "PULSEWIDTH":
        actual[2:3] = ["PULSE", "WIDTH"]
        if expected[2:] == ["PULSe", "SOUrce"]:
            expected.insert(3, "WIDth")
    if expected[:2] in (["HORizontal", "MAIn"], ["TRIGger", "MAIn"]) and len(actual) == len(expected) - 1:
        expected = [expected[0], *expected[2:]]
    if not separator or len(actual) != len(expected):
        raise OscilloscopeError(f"Unexpected Tek response header: {raw!r}")
    for received, command in zip(actual, expected):
        minimum = "".join(char for char in command if char.isupper() or char.isdigit() or char == "*")
        if not (received.upper() == minimum.upper() or
                (received.upper().startswith(minimum.upper()) and command.upper().startswith(received.upper()))):
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
    def plan_capture_scpi(cls, channels, points, waveform_format, capabilities) -> list[str]:
        backend = _PlanningBackend(capabilities)
        scope = cls(backend)
        scope.capabilities = capabilities
        scope.capture_waveforms_byte(channels, points)
        return backend.commands

    @classmethod
    def plan_measure_scpi(cls, item, channel, reference_channel, capabilities, **parameters) -> list[str]:
        backend = _PlanningBackend(capabilities)
        scope = cls(backend)
        scope.capabilities = capabilities
        if reference_channel is not None:
            raise ParameterValidationError("Pair measurements are unsupported for this model")
        scope.query_measurement(channel, item, **parameters)
        return backend.commands

    @classmethod
    def plan_workflow_step(cls, action, capabilities, **parameters) -> list[str]:
        backend = _PlanningBackend(capabilities)
        scope = cls(backend)
        scope.capabilities = capabilities
        if action == "status":
            scope.workflow_status()
        elif action == "command-status":
            scope.post_command_status()
        elif action == "single":
            scope.single()
        elif action == "wait-trigger":
            backend.query("BUSY?")
        elif action == "acquisition-query":
            scope.query_acquisition_config()
        elif action == "acquisition-set":
            if parameters.get("count") is not None:
                scope.validate_acquisition_count(parameters["count"])
            scope.set_acquisition_type(parameters["type"])
            if parameters.get("count") is not None:
                scope.set_acquisition_count(parameters["count"])
        elif action == "screenshot":
            scope.capture_screenshot_png(background=parameters.get("background", "black"))
        elif action == "doctor":
            from .operations import run_doctor
            run_doctor(scope, "")
        else:
            raise ParameterValidationError(f"Unsupported workflow planning step: {action}")
        return backend.commands

    @classmethod
    def plan_cli_operation(cls, args: object, capabilities: ScopeCapabilities) -> tuple[list[str], list[dict[str, str]], dict[str, object]] | None:
        command = getattr(args, "command")
        if not operation_supported(capabilities, command):
            raise ParameterValidationError(f"{command} is unsupported for this Tektronix model")
        if command in {"doctor", "capture-batch", "capture-until", "capture-monitor", "measure-sweep", "measure-log", "measure-until", "triggered-capture-series", "triggered-measure-loop", "acquisition-check", "cleanup", "sequence", "smoke"}:
            return None
        if command == "identify":
            return ["*IDN?"], [], {"operation": "identify"}
        if command == "list-resources":
            return [], [], {"operation": "list-resources"}
        if command in {"measure", "capture"}:
            from .planning import CapturePlanRequest, MeasurePlanRequest, plan_capture, plan_measure
            if command == "measure":
                request = MeasurePlanRequest(args.item, args.channel, args.source_channel,
                    args.reference_channel, args.time_s, args.level, args.slope, args.occurrence)
                plan = plan_measure(request, capabilities)
            else:
                request = CapturePlanRequest(args.channel, args.points, args.waveform_format,
                    args.csv_path, args.meta_path, args.plot_path)
                plan = plan_capture(request, capabilities)
            commands = list(plan.planned_scpi)
            result = dict(plan.result)
            if command == "capture" and args.wait_trigger:
                config = TriggerWaitConfig(args.trigger_timeout_ms, args.trigger_poll_interval_ms, args.force_trigger_on_timeout)
                validate_trigger_wait_config(config)
                wait_commands = ["ACQuire:STOPAfter SEQuence", "ACQuire:STATE ON", "BUSY?"]
                if config.force_on_timeout:
                    wait_commands.extend(["TRIGger FORCe", "BUSY?"])
                commands = wait_commands + commands
                result["trigger"] = TriggerWaitResult("unknown", False, False, 0, 0, capture_block_reason="dry_run",
                    poll_source="busy", poll_command="BUSY?",
                    arm_command="ACQuire:STOPAfter SEQuence;ACQuire:STATE ON", force_command="TRIGger FORCe").to_json(config)
            return commands, list(plan.files), result
        backend = _PlanningBackend(capabilities)
        scope = cls(backend)
        scope.capabilities = capabilities
        scope._plan_cli_action(args)
        explicit_status = command in {"system-clear-status", "system-opc", "system-status-byte", "system-standard-event"}
        if not explicit_status:
            backend.commands.append("*ESR?")
        business_commands = backend.commands if explicit_status else backend.commands[:-1]
        if command == "single-wait":
            config = TriggerWaitConfig(args.trigger_timeout_ms, args.trigger_poll_interval_ms, args.force_trigger_on_timeout)
            result = TriggerWaitResult("unknown", False, False, 0, 0, capture_block_reason="dry_run",
                poll_source="busy", poll_command="BUSY?",
                arm_command="ACQuire:STOPAfter SEQuence;ACQuire:STATE ON", force_command="TRIGger FORCe")
            return backend.commands, [], {"operation": command, **result.to_json(config)}
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
        elif command == "single-wait":
            config = validate_trigger_wait_config(TriggerWaitConfig(args.trigger_timeout_ms, args.trigger_poll_interval_ms, args.force_trigger_on_timeout))
            self.single()
            self.scpi.query("BUSY?")
            if config.force_on_timeout:
                self.force_trigger()
                self.scpi.query("BUSY?")
        elif command == "trigger-pulse-width":
            if not args.glitch_query:
                self.configure_glitch_trigger(channel=args.channel, polarity=args.polarity, qualifier=args.qualifier,
                    time_seconds=args.time_seconds, min_time_seconds=args.min_time_seconds,
                    max_time_seconds=args.max_time_seconds, level_volts=args.level_volts)
            self.query_glitch_trigger()
        elif command == "reference-query":
            self.query_reference_waveform(args.slot)
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
        elif command == "save-waveform":
            self.save_waveform(args.filename, source_channel=args.source_channel)
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
    def _is_tbs2000b(self) -> bool:
        if self.capabilities is None or self.capabilities.series not in {"TBS2000B", "TDS2000B", "TBS1000B"}:
            raise ParameterValidationError("Tektronix series is unsupported for this model")
        return self.capabilities.series == "TBS2000B"

    @property
    def _trigger_root(self) -> str:
        return "TRIGger:A" if self._is_tbs2000b else "TRIGger:MAIn"

    def _channel(self, channel: int) -> int:
        if self.capabilities is None:
            raise OscilloscopeError("Tek capabilities unavailable")
        return validate_analog_channel(channel, self.capabilities)

    def _require_tbs2000b(self, operation: str) -> None:
        if not self._is_tbs2000b:
            raise ParameterValidationError(f"{operation} is unsupported for this model")

    def _require_tds2000b_or_tbs1000b(self, operation: str) -> None:
        if self.capabilities is None or self.capabilities.series not in {"TDS2000B", "TBS1000B"}:
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

    def doctor_trigger_snapshot(self) -> dict[str, object]:
        trigger = self._query_instrument_summary()["trigger"]
        result = {"type": trigger["type"], "source": trigger["source"],
                  "source_channel": trigger["source_channel"],
                  "level_volts": trigger["level"], "slope": trigger["slope"]}
        if trigger["type"] != "edge":
            result["unavailable_reason"] = "current_trigger_is_not_edge"
        elif trigger["source_channel"] is None:
            result["unavailable_reason"] = "current_source_is_not_an_analog_channel"
        return result

    def workflow_status(self) -> TekPostStatus:
        """Consume one SESR summary and its events before another SESR read."""
        mask = _number(re.sub(r"^:?(?:DESE)\s+", "", self.scpi.query("DESE?"), flags=re.IGNORECASE), "DESE?")
        if not mask.is_integer() or not 0 <= mask <= 255 or int(mask) & 0x3C != 0x3C:
            raise OscilloscopeError("Tek status reporting is incomplete: DESE must enable error bits 2..5")
        raw = self.scpi.query("*ESR?")
        number = _number(raw, "*ESR?")
        if not number.is_integer() or not 0 <= number <= 255:
            raise OscilloscopeError(f"Invalid Tek SESR response: {raw!r}")
        event_raw = self.scpi.query("ALLEv?")
        payload = re.sub(r"^:?(?:ALLEV|ALLEVENTS)\s+", "", event_raw.strip(), flags=re.IGNORECASE)
        try:
            values = next(csv.reader([payload], skipinitialspace=True, strict=True))
            if len(values) % 2 or not values or len(values) > 40:
                raise ValueError("expected at most 20 event code/message pairs")
            events = []
            for i in range(0, len(values), 2):
                code = int(values[i])
                if code < 0:
                    raise ValueError("negative event code")
                if code:
                    category = "warning" if code in {528, 532, 533, *range(540, 550)} else "event"
                    if 100 <= code < 400 or code in {404, 410, 420, 430, 440}:
                        category = "error"
                    events.append({"code": code, "message": values[i + 1], "category": category})
        except (ValueError, csv.Error) as exc:
            raise OscilloscopeError(f"Invalid Tek event response: {event_raw!r}") from exc
        complete = not any(event["code"] == 350 for event in events)
        if int(number) & 0x3C and not events:
            complete = False
        return TekPostStatus(int(number), raw, event_raw, tuple(events), complete)

    def preflight_status(self, *, diagnostic: bool = False, max_reads: int = 30) -> tuple:
        if max_reads < 1:
            raise ValueError("max_reads must be at least 1.")
        status = self.workflow_status()
        if not status.complete:
            raise OscilloscopeError(f"Incomplete Tek pre-operation status: {status.format()}")
        return (status,) if diagnostic or status.events or status.is_error else ()

    def post_webui_operation_status(self, operation: str) -> TekPostStatus | None:
        if operation in {"doctor", "capture-batch", "capture-until", "capture-monitor", "measure-sweep", "measure-log", "measure-until", "triggered-capture-series", "triggered-measure-loop", "acquisition-check", "cleanup", "sequence", "smoke", "measure", "capture"}:
            return None
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
            self._require_tbs2000b("high-resolution acquisition")
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

    def _timebase_record_duration(self) -> float:
        length = self._float("HORizontal:RECOrdlength?")
        rate = self._float("HORizontal:SAMPLERate?")
        if length <= 0 or rate <= 0:
            raise OscilloscopeError("Invalid Tek horizontal record geometry")
        return length / rate

    def set_timebase_position(self, seconds: float) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds):
            raise ParameterValidationError("value must be a finite number")
        if not self._is_tbs2000b:
            self._write_number("HORizontal:MAIn:POSition", seconds)
        elif _boolean(self.scpi.query("HORizontal:MAIn:DELay:MODe?"), "HORizontal:MAIn:DELay:MODe?"):
            self._write_number("HORizontal:MAIn:DELay:TIMe", seconds)
        else:
            percent = 50.0 - seconds / self._timebase_record_duration() * 100.0
            self._write_number("HORizontal:POSition", round(percent))

    def query_timebase_position(self) -> float:
        if not self._is_tbs2000b:
            return self._float("HORizontal:MAIn:POSition?")
        if _boolean(self.scpi.query("HORizontal:MAIn:DELay:MODe?"), "HORizontal:MAIn:DELay:MODe?"):
            return self._float("HORizontal:MAIn:DELay:TIMe?")
        percent = self._float("HORizontal:POSition?")
        return (50.0 - percent) / 100.0 * self._timebase_record_duration()

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
        channel = self._channel(channel)
        volts = validate_channel_offset(volts)
        if self._is_tbs2000b:
            self._write_number(f"CH{channel}:OFFSet", volts)
        else:
            # TDS2000B/TBS1000B positive POSITION raises the signal; offset is the center voltage.
            self._write_number(f"CH{channel}:POSition", -volts / self.query_channel_scale(channel))

    def query_channel_offset(self, channel: int) -> float:
        channel = self._channel(channel)
        if self._is_tbs2000b:
            return self._float(f"CH{channel}:OFFSet?")
        return -self._float(f"CH{channel}:POSition?") * self.query_channel_scale(channel)

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
        if self._is_tbs2000b:
            self._write_number(f"CH{channel}:PRObe:GAIN", 1 / ratio)
        else:
            if ratio not in {1, 10, 20, 50, 100, 500, 1000}:
                raise ParameterValidationError("Unsupported TDS2000B/TBS1000B probe ratio")
            self._write_number(f"CH{channel}:PRObe", ratio)

    def query_channel_probe_ratio(self, channel: int) -> float:
        channel = self._channel(channel)
        value = self._float(f"CH{channel}:PRObe:GAIN?" if self._is_tbs2000b else f"CH{channel}:PRObe?")
        if value <= 0:
            raise OscilloscopeError("Invalid Tek probe response")
        return 1 / value if self._is_tbs2000b else value

    def set_channel_bandwidth_limit(self, channel: int, enabled: bool) -> None:
        channel = self._channel(channel)
        token = ("TWEnty" if enabled else "FULl") if self._is_tbs2000b else ("ON" if enabled else "OFF")
        self.scpi.write(f"CH{channel}:BANdwidth {token}")

    def query_channel_bandwidth_limit(self, channel: int) -> bool:
        value, _ = self._query(f"CH{self._channel(channel)}:BANdwidth?")
        valid = {"TWE": True, "TWENTY": True, "FULL": False, "FUL": False} if self._is_tbs2000b else {"ON": True, "OFF": False, "1": True, "0": False}
        try:
            return valid[value.upper()]
        except KeyError as exc:
            raise OscilloscopeError(f"Invalid Tek bandwidth response: {value!r}") from exc

    def set_channel_invert(self, channel: int, enabled: bool) -> None:
        self.scpi.write(f"CH{self._channel(channel)}:INVert {'ON' if enabled else 'OFF'}")

    def query_channel_invert(self, channel: int) -> bool:
        return _boolean(self.scpi.query(f"CH{self._channel(channel)}:INVert?"), f"CH{channel}:INVert?")

    def set_channel_label(self, channel: int, text: str) -> None:
        self._require_tbs2000b("channel-label")
        channel = self._channel(channel)
        if self.capabilities is None:
            raise OscilloscopeError("Tek capabilities unavailable")
        text = validate_channel_label(text, self.capabilities)
        self.scpi.write(f'CH{channel}:LABel "{text}"')

    def query_channel_label(self, channel: int) -> str:
        self._require_tbs2000b("channel-label")
        value, _ = self._query(f"CH{self._channel(channel)}:LABel?")
        return value.strip('"')

    def set_channel_probe_skew(self, channel: int, seconds: float) -> None:
        self._require_tbs2000b("channel-probe-skew")
        channel = self._channel(channel)
        if not -100e-9 <= seconds <= 100e-9:
            raise ParameterValidationError("Tek probe skew must be within -100 to 100 ns")
        self._write_number(f"CH{channel}:DESKew", seconds)

    def query_channel_probe_skew(self, channel: int) -> float:
        self._require_tbs2000b("channel-probe-skew")
        return self._float(f"CH{self._channel(channel)}:DESKew?")

    def set_display_vectors_on(self) -> None:
        self._require_tds2000b_or_tbs1000b("display-vectors")
        self.scpi.write("DISPlay:STYle VECtors")

    def query_display_vectors(self) -> tuple[bool, str]:
        self._require_tds2000b_or_tbs1000b("display-vectors")
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
        return f"REF{slot}" if self._is_tbs2000b else ("REFA" if slot == 1 else "REFB")

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
        choices.update({"runt": "PULSE"} if self._is_tbs2000b else {"tv": "VIDeo"})
        token = _choice(mode, choices, "trigger type")
        self.scpi.write(f"{self._trigger_root}:TYPe {token}")
        if self._is_tbs2000b and token == "PULSE":
            self.scpi.write(f"{self._trigger_root}:PULSe:CLAss {'RUNT' if mode.lower() == 'runt' else 'WIDth'}")

    def query_trigger_mode(self) -> TriggerModeState:
        value, raw = self._query(f"{self._trigger_root}:TYPe?")
        choices = {"EDGE": "edge", "PULS": "glitch", "PULSE": "glitch"}
        if not self._is_tbs2000b:
            choices.update({"VID": "tv", "VIDEO": "tv"})
        mode = _choice(value, choices, "trigger type response")
        if self._is_tbs2000b and mode == "glitch":
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
            choices = {"line": "LINE"} if self._is_tbs2000b else {"line": "ACLine", "external": "EXT"}
            token = _choice(source, choices, "edge source")
        else:
            raise ParameterValidationError("Tek non-channel source rejects source_channel")
        self.scpi.write(f"{self._trigger_root}:EDGE:SOUrce {token}")

    def query_trigger_edge_source(self) -> EdgeTriggerSourceState:
        value, raw = self._query(f"{self._trigger_root}:EDGE:SOUrce?")
        match = re.fullmatch(r"CH([1-4])", value.upper())
        if match is not None:
            channel = int(match.group(1))
            if channel <= self.capabilities.analog_channels:
                return EdgeTriggerSourceState("analog-channel", channel, raw)
            return EdgeTriggerSourceState(None, None, raw)
        choices = {"LINE": "line"} if self._is_tbs2000b else {"ACL": "line", "ACLINE": "line", "EXT": "external"}
        return EdgeTriggerSourceState(choices.get(value.upper()), None, raw)

    def configure_trigger_edge_slope(self, *, slope: str) -> None:
        token = _choice(slope, {"positive": "RISe", "negative": "FALL"}, "edge slope")
        self.scpi.write(f"{self._trigger_root}:EDGE:SLOpe {token}")

    def query_trigger_edge_slope(self) -> EdgeTriggerSlopeState:
        value, raw = self._query(f"{self._trigger_root}:EDGE:SLOpe?")
        return EdgeTriggerSlopeState(_choice(value, {"RISE": "positive", "RIS": "positive", "FALL": "negative"}, "edge slope response"), raw)

    def configure_trigger_edge_coupling(self, coupling: str) -> None:
        choices = {"dc": "DC", "lf-reject": "LFRej"}
        if not self._is_tbs2000b:
            choices["ac"] = "AC"
        token = _choice(coupling, choices, "edge coupling")
        self.scpi.write(f"{self._trigger_root}:EDGE:COUPling {token}")

    def query_trigger_edge_coupling(self) -> EdgeTriggerCouplingState:
        value, raw = self._query(f"{self._trigger_root}:EDGE:COUPling?")
        choices = {"DC": "dc", "LFREJ": "lf-reject", "LFREJECT": "lf-reject"}
        if not self._is_tbs2000b:
            choices["AC"] = "ac"
        return EdgeTriggerCouplingState(_choice(value, choices, "edge coupling response"), raw)

    def configure_trigger_edge_level(self, *, source_channel: int, level_volts: float) -> None:
        self._require_tbs2000b("trigger-edge-level")
        self._write_number(f"{self._trigger_root}:LEVel:CH{self._channel(source_channel)}", level_volts)

    def query_trigger_edge_level(self, *, source_channel: int) -> EdgeTriggerLevelState:
        self._require_tbs2000b("trigger-edge-level")
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
        command = f"{self._trigger_root}:LEVel:CH{channel}" if self._is_tbs2000b else f"{self._trigger_root}:LEVel"
        self._write_number(command, level_volts)
        self.scpi.write(f"{self._trigger_root}:EDGE:SLOpe {token}")

    def query_trigger_edge(self) -> EdgeTriggerState:
        source = self.query_trigger_edge_source()
        if source.source_channel is None:
            raise ParameterValidationError("Combined Tek edge trigger requires an analog source")
        command = f"{self._trigger_root}:LEVel:CH{source.source_channel}?" if self._is_tbs2000b else f"{self._trigger_root}:LEVel?"
        level = self._float(command)
        slope = self.query_trigger_edge_slope().slope
        assert slope is not None
        return EdgeTriggerState(source.source_channel, level, slope)

    def set_trigger_holdoff(self, seconds: float) -> None:
        minimum, maximum = (40e-9, 8.0) if self._is_tbs2000b else (500e-9, 10.0)
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not minimum <= seconds <= maximum:
            raise ParameterValidationError("Unsupported Tek trigger holdoff")
        command = f"{self._trigger_root}:HOLDOff:TIMe" if self._is_tbs2000b else f"{self._trigger_root}:HOLDOff:VALue"
        self._write_number(command, seconds)

    def query_trigger_holdoff(self) -> float:
        command = f"{self._trigger_root}:HOLDOff:TIMe?" if self._is_tbs2000b else f"{self._trigger_root}:HOLDOff:VALue?"
        return self._float(command)

    def _units_available(self, channel: int) -> bool:
        return not self._is_tbs2000b or channel in (1, 2)

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
            label=self.query_channel_label(channel) if self._is_tbs2000b else None,
            scale=self.query_channel_scale(channel), range=None,
            offset=self.query_channel_offset(channel),
            coupling=self.query_channel_coupling(channel), impedance=None,
            invert=self.query_channel_invert(channel),
            bandwidth_limit=self.query_channel_bandwidth_limit(channel),
            units=self.query_channel_units(channel) if self._units_available(channel) else None,
            vernier=None, probe_ratio=self.query_channel_probe_ratio(channel),
            probe_skew=self.query_channel_probe_skew(channel) if self._is_tbs2000b else None,
        ) for channel in range(1, self.capabilities.analog_channels + 1))

    def set_display_persistence(self, value: str | float) -> None:
        mode, seconds = validate_display_persistence(value, self.capabilities)
        token = "OFF" if mode == "minimum" else "INFInite" if mode == "infinite" else f"{seconds:g}"
        if self._is_tbs2000b:
            if mode != "minimum":
                self.scpi.write(f"DISplay:PERSistence:VALUe {token}")
            self.scpi.write(f"DISplay:PERSistence:STATe {'OFF' if mode == 'minimum' else 'ON'}")
        else:
            self.scpi.write(f"DISplay:PERSistence {token}")

    def query_display_persistence(self) -> DisplayPersistence:
        if self._is_tbs2000b:
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
        if not self._is_tbs2000b:
            seconds = _number(value, "DISPlay:PERSistence?")
            if seconds == 0:
                return DisplayPersistence("minimum", None, raw)
            if seconds == 99:
                return DisplayPersistence("infinite", None, raw)
            if seconds not in self.capabilities.display_persistence_seconds:
                raise OscilloscopeError(f"Unsupported Tek persistence response: {raw!r}")
            return DisplayPersistence(None, seconds, raw)
        _, seconds = validate_display_persistence(value)
        if seconds is None:
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
        source, _ = self._query("SELect:CONTROl?" if self._is_tbs2000b else "CURSor:SELect:SOUrce?")
        # FFT positions remain frequency-valued even when the unit selector says seconds.
        time_source = source.upper() in {"CH1", "CH2", "CH3", "CH4", "MATH", "REF1", "REF2", "REFA", "REFB"}
        if source.upper() == "MATH":
            expression, _ = self._query("MATH:DEFINE?")
            time_source = not expression.strip('"').upper().startswith("FFT")
        if active in ({"TIME", "SCREEN"} if self._is_tbs2000b else {"VBA", "VBARS"}) and time_source:
            units, _ = self._query("CURSor:VBArs:UNIts?")
            if units.upper() in {"SECO", "SECONDS"}:
                x1 = self._float("CURSor:VBArs:POSITION1?")
                x2 = self._float("CURSor:VBArs:POSITION2?")
                dx = self._float("CURSor:VBArs:DELTa?")
        if active in ({"AMPL", "AMPLITUDE", "SCREEN"} if self._is_tbs2000b else {"HBA", "HBARS"}):
            units, _ = self._query("CURSor:HBArs:UNIts?")
            volts = False
            voltage_units = {"BASE", "BAS"} if self._is_tbs2000b else {"VOLTS", "V"}
            voltage_sources = {f"CH{channel}" for channel in range(1, self.capabilities.analog_channels + 1)}
            if units.upper() in voltage_units and source.upper() in voltage_sources:
                volts = self._cursor_channel_is_voltage(int(source[-1]))
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
        if self.capabilities.cursor_source_selection == "selected-waveform":
            self._configure_selected_waveform_cursor(channel, x1_seconds=x1_seconds,
                x2_seconds=x2_seconds, y1_volts=y1_volts, y2_volts=y2_volts,
                auto_timebase=auto_timebase)
            return
        self._require_tds2000b_or_tbs1000b("independent cursor source")
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

    def _cursor_channel_is_voltage(self, channel: int) -> bool:
        if self._units_available(channel):
            return self.query_channel_units(channel) == "volt"
        self._require_tbs2000b("cursor waveform units")
        # The waveform preamble also covers channels without a YUNit control.
        source, _ = self._query("DATa:SOUrce?")
        source = source.upper()
        sources = {f"CH{i}" for i in range(1, self.capabilities.analog_channels + 1)}
        if source not in sources | {"MATH", "REF1", "REF2"}:
            raise OscilloscopeError("Unsupported waveform source readback")
        target = f"CH{channel}"
        try:
            if source != target:
                self.scpi.write(f"DATa:SOUrce {target}")
            units, _ = self._query("WFMOutpre:YUNit?")
            return units.strip('"').upper() in {"V", "VOLTS"}
        finally:
            if source != target:
                self.scpi.write(f"DATa:SOUrce {source}")

    def plan_cursor_auto_timebase(self, *, x1_seconds=None, x2_seconds=None):
        start = len(self.backend.history)
        plan = cursor_auto_timebase_plan(self.query_timebase_scale(), self.query_timebase_position(),
            x1_seconds=x1_seconds, x2_seconds=x2_seconds,
            display_divisions=self.capabilities.horizontal_display_divisions)
        commands = list(self.backend.history[start:])
        if plan.changed:
            commands.append(f"HORizontal:MAIn:SCAle {plan.target_scale_seconds_per_division:g}")
        return replace(plan, commands=tuple(commands))

    def _configure_selected_waveform_cursor(self, channel: int, *, x1_seconds=None,
            x2_seconds=None, y1_volts=None, y2_volts=None, auto_timebase=False) -> None:
        self._require_tbs2000b("selected waveform cursor")
        x_values, y_values = (x1_seconds, x2_seconds), (y1_volts, y2_volts)
        x_axis = any(value is not None for value in x_values)
        y_axis = any(value is not None for value in y_values)
        # Validate coordinates before selecting or enabling the source waveform.
        if y_axis:
            if self._units_available(channel) and not self._cursor_channel_is_voltage(channel):
                raise ParameterValidationError("Y cursors require a channel with volt units")
            scale, offset = self.query_channel_scale(channel), self.query_channel_offset(channel)
            position = self._float(f"CH{channel}:POSition?")
            if scale <= 0:
                raise OscilloscopeError("Invalid channel scale")
            if any(value is not None and abs((value - offset) / scale + position) >
                   self.capabilities.vertical_display_divisions / 2 for value in y_values):
                raise ParameterValidationError("Y cursor position is outside the graticule")
        if x_axis:
            plan = self.plan_cursor_auto_timebase(x1_seconds=x1_seconds, x2_seconds=x2_seconds)
            scale = plan.original_scale_seconds_per_division
            position = plan.original_position_seconds
            if auto_timebase and plan.changed:
                self.set_timebase_scale(plan.target_scale_seconds_per_division)
                scale, position = self.query_timebase_scale(), self.query_timebase_position()
            if any(value is not None and abs(value - position) >
                   self.capabilities.horizontal_display_divisions / 2 * scale for value in x_values):
                raise ParameterValidationError("X cursor position is outside the graticule")
        source, _ = self._query("SELect:CONTROl?")
        if source.upper() != f"CH{channel}" or not self.query_channel_display(channel):
            self.scpi.write(f"SELect:CONTROl CH{channel}")
        source, _ = self._query("SELect:CONTROl?")
        if source.upper() != f"CH{channel}" or not self.query_channel_display(channel):
            raise OscilloscopeError("Cursor source selection did not take effect")
        if y_axis and not self._units_available(channel) and not self._cursor_channel_is_voltage(channel):
            raise ParameterValidationError("Y cursors require a channel with volt units")
        mode = "SCREEN" if x_axis and y_axis else "TIME" if x_axis else "AMPLitude"
        self.scpi.write(f"CURSor:FUNCtion {mode}")
        if not (x_axis and y_axis):
            self.scpi.write("CURSor:MODe INDependent")
        for axis, values, units in (("VBArs", x_values, "SECOnds"), ("HBArs", y_values, "BASe")):
            if any(value is not None for value in values):
                self.scpi.write(f"CURSor:{axis}:UNIts {units}")
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

    def measurement_query_command(self, channel: int, item: str, **kwargs: object) -> str:
        validate_analog_channel(channel, self.capabilities)
        measurement_query(item, channel, capabilities=self.capabilities, **kwargs)
        return "MEASUrement:IMMed:VALue?"

    def query_measurement(self, channel: int, item: str, **kwargs: object) -> MeasurementResult:
        self.measurement_query_command(channel, item, **kwargs)
        item = normalize_measurement_item(item)
        root = "MEASUrement:IMMed"
        source = "SOUrce1" if self._is_tbs2000b else "SOUrce"
        original_type = self._query(f"{root}:TYPe?")[0]
        original_source = self._query(f"{root}:{source}?")[0]
        try:
            self.scpi.write(f"{root}:TYPe {self._measurement_types()[item]}")
            self.scpi.write(f"{root}:{source} CH{channel}")
            raw = self.scpi.query(f"{root}:VALue?")
            self._query(f"{root}:UNIts?")
            result = parse_measurement_result(_payload(raw, f"{root}:VALue?"), item=item, channel=channel)
            return replace(result, raw_value=raw)
        finally:
            try:
                self.scpi.write(f"{root}:TYPe {original_type}")
            finally:
                self.scpi.write(f"{root}:{source} {original_source}")

    def capture_waveform_byte(self, channel: int, points: int = 1000) -> WaveformCapture:
        channel = validate_analog_channel(channel, self.capabilities)
        points = validate_waveform_points(points, self.capabilities)
        if not self.query_channel_display(channel):
            raise WaveformResponseError(f"CH{channel} is not displayed; waveform capture requires a displayed analog channel")
        self.scpi.write(f"DATa:SOUrce CH{channel}")
        self.scpi.write("DATa:ENCdg RPBInary")
        self.scpi.write("DATa:WIDth 1")
        self.scpi.write("DATa:STARt 1")
        self.scpi.write(f"DATa:STOP {points}")
        root = "WFMOutpre" if self._is_tbs2000b else "WFMPre"
        raw = {name: self.scpi.query(f"{root}:{name}?") for name in (
            "NR_Pt", "XINcr", "XZEro", "YMUlt", "YZEro", "YOFf", "YUNit"
        )}
        number = lambda name: _number(raw[name], f"{root}:{name}?")
        preamble = WaveformPreamble(
            raw=";".join(raw.values()), format_code=0, type_code=0,
            points=int(number("NR_Pt")), count=1,
            x_increment=number("XINcr"), x_origin=number("XZEro"), x_reference=0,
            y_increment=number("YMUlt"), y_origin=number("YZEro"), y_reference=number("YOFf"),
        )
        unit = validate_waveform_vertical_unit(_payload(raw["YUNit"], f"{root}:YUNit?").strip('"'))
        samples = tuple(int(value) for value in self.scpi.query_binary_values("CURVe?", datatype="B"))
        if not samples:
            raise WaveformResponseError("Waveform data query returned no samples.")
        return convert_byte_waveform(channel, points, preamble, samples, vertical_unit=unit)

    def capture_waveforms_byte(self, channels: Sequence[int], points: int = 1000) -> MultiChannelWaveformCapture:
        channels = validate_waveform_channels(channels, self.capabilities)
        validate_waveform_points(points, self.capabilities)
        return MultiChannelWaveformCapture(tuple(self.capture_waveform_byte(channel, points) for channel in channels))

    def single_wait(self, config: TriggerWaitConfig, *, stop_requested: StopRequested | None = None) -> TriggerWaitResult:
        config = validate_trigger_wait_config(config)
        self.single()
        result = self.wait_for_current_trigger_completion(config, stop_requested=stop_requested)
        return replace(result, arm_command="ACQuire:STOPAfter SEQuence;ACQuire:STATE ON")

    def wait_for_current_trigger_completion(self, config: TriggerWaitConfig, *, stop_requested=None) -> TriggerWaitResult:
        config = validate_trigger_wait_config(config)
        start = config.clock()
        raw_values, values = [], []

        def poll() -> tuple[str, str | None]:
            deadline = config.clock() + config.timeout_ms / 1000.0
            while True:
                if stop_requested is not None and stop_requested():
                    return "cancelled", None
                try:
                    raw = self.scpi.query("BUSY?")
                    value = _number(raw, "BUSY?")
                    if value not in (0, 1):
                        return "unknown", f"Invalid Tek BUSY response: {raw!r}"
                except Exception as exc:
                    return "unknown", str(exc)
                raw_values.append(raw)
                values.append(int(value))
                if value == 0:
                    return "complete", None
                remaining = deadline - config.clock()
                if remaining <= 0:
                    return "timeout", None
                if not _wait_for_trigger_poll(config, min(config.poll_interval_ms / 1000.0, remaining), stop_requested=stop_requested):
                    return "cancelled", None

        outcome, error = poll()
        forced = False
        if outcome == "timeout" and config.force_on_timeout:
            self.force_trigger()
            forced = True
            outcome, error = poll()
        if outcome == "complete":
            outcome = "forced" if forced else "natural"
        result = _trigger_wait_result(outcome, forced, outcome == "timeout", start, config, raw_values, values, error=error)
        return replace(result, poll_source="busy", poll_command="BUSY?",
            arm_command=None, force_command="TRIGger FORCe")

    def configure_glitch_trigger(self, *, channel: int, polarity: str, qualifier: str,
        time_seconds: float | None = None, min_time_seconds: float | None = None,
        max_time_seconds: float | None = None, level_volts: float | None = None) -> None:
        glitch_trigger_configure_commands(channel=channel, polarity=polarity, qualifier=qualifier,
            time_seconds=time_seconds, min_time_seconds=min_time_seconds, max_time_seconds=max_time_seconds,
            level_volts=level_volts, capabilities=self.capabilities)
        qualifier = normalize_glitch_qualifier(qualifier)
        when = ({"LESSthan": "LESSthan", "GREaterthan": "MOREthan"} if self._is_tbs2000b else
                {"LESSthan": "INside", "GREaterthan": "OUTside"})[qualifier]
        self.configure_trigger_mode("glitch")
        root = f"{self._trigger_root}:PULSe:WIDth"
        self.scpi.write(f"{self._trigger_root}:PULSe:SOUrce CH{channel}")
        self.scpi.write(f"{root}:POLarity {normalize_glitch_polarity(polarity)}")
        self._write_number(f"{root}:WIDth", time_seconds)
        self.scpi.write(f"{root}:WHEn {when}")
        if level_volts is not None:
            self._write_number(f"{self._trigger_root}:LEVel" + (f":CH{channel}" if self._is_tbs2000b else ""), level_volts)

    def query_glitch_trigger(self) -> GlitchTriggerState:
        root = f"{self._trigger_root}:PULSe:WIDth"
        mode = self.query_trigger_mode()
        raw = {"source": self.scpi.query(f"{self._trigger_root}:PULSe:SOUrce?")}
        raw.update({key: self.scpi.query(f"{root}:{command}?") for key, command in
            (("polarity", "POLarity"), ("qualifier", "WHEn"), ("width", "WIDth"))})
        source = _payload(raw["source"], f"{self._trigger_root}:PULSe:SOUrce?")
        match = re.fullmatch(r"CH([1-4])", source.upper())
        if match is None:
            raise OscilloscopeError(f"Unsupported Tek pulse source: {source!r}")
        channel = validate_analog_channel(int(match[1]), self.capabilities)
        qualifier = _choice(_payload(raw["qualifier"], f"{root}:WHEn?"),
            {"LESS": "less-than", "LESSTHAN": "less-than", "MORE": "greater-than", "MORETHAN": "greater-than"} if self._is_tbs2000b else
            {"IN": "less-than", "INSIDE": "less-than", "OUT": "greater-than", "OUTSIDE": "greater-than"}, "pulse qualifier response")
        polarity = _choice(_payload(raw["polarity"], f"{root}:POLarity?"),
            {"POS": "positive", "POSITIVE": "positive", "NEG": "negative", "NEGATIVE": "negative"}, "pulse polarity response")
        width = _number(raw["width"], f"{root}:WIDth?")
        command = f"{self._trigger_root}:LEVel" + (f":CH{channel}" if self._is_tbs2000b else "") + "?"
        raw["level"] = self.scpi.query(command)
        raw["mode"] = mode.raw_mode
        return GlitchTriggerState(mode.mode, source, "analog-channel", channel, None, polarity, qualifier,
            width if qualifier == "greater-than" else None, width if qualifier == "less-than" else None,
            None, None, _number(raw["level"], command), raw)

    def query_reference_waveform(self, slot: int) -> ReferenceWaveformState:
        displayed, raw = self.query_reference_display(slot)
        return ReferenceWaveformState(slot, displayed, raw, None, None)

    def _measurement_types(self) -> dict[str, str]:
        return {
            "vpp": "PK2Pk", "vavg": "MEAN", "vrms": "RMS", "frequency": "FREQuency",
            "period": "PERIod", "minimum": "MINImum", "maximum": "MAXimum",
            "rise_time": "RISe", "fall_time": "FALL", "positive_width": "PWIdth", "negative_width": "NWIdth",
            "amplitude": "AMPlitude", "top": "HIGH", "base": "LOW", "overshoot": "POVERshoot", "preshoot": "NOVERshoot",
            "duty_cycle": "PDUty", "negative_duty_cycle": "NDUty", "area": "AREA",
            "positive_edges": "PEDGECount" if self._is_tbs2000b else "REDGECount",
            "negative_edges": "NEDGECount" if self._is_tbs2000b else "FEDGECount",
            "positive_pulses": "PPULSECount", "negative_pulses": "NPULSECount",
        }

    def _measurement_slots(self) -> range:
        if self.capabilities is None or self.capabilities.series not in {"TBS2000B", "TDS2000B", "TBS1000B"}:
            raise ParameterValidationError("Tektronix measurement slots are unsupported for this model")
        return range(1, 6 if self.capabilities.series == "TDS2000B" else 7)

    def install_measurement(self, channel: int, item: str) -> None:
        channel = self._channel(channel)
        item = validate_measurement_install_item(item, self.capabilities)
        token = self._measurement_types()[item]
        source_name = "SOUrce1" if self._is_tbs2000b else "SOUrce"
        unused = matching = None
        for slot in self._measurement_slots():
            root = f"MEASUrement:MEAS{slot}"
            if self._is_tbs2000b:
                available = not _boolean(self.scpi.query(f"{root}:STATE?"), f"{root}:STATE?")
                if available:
                    unused = unused or slot
                    continue
            kind, _ = self._query(f"{root}:TYPe?")
            if not self._is_tbs2000b and kind.upper() == "NONE":
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
            if self._is_tbs2000b:
                self.scpi.write(f"{root}:STATE ON")

    def clear_measurements(self) -> None:
        for slot in self._measurement_slots():
            self.scpi.write(f"MEASUrement:MEAS{slot}:" + ("STATE OFF" if self._is_tbs2000b else "TYPe NONE"))

    def configure_save_image_format(self, format: str) -> None:
        self._require_tbs2000b("save-image-format")
        token = _choice(format, {"png": "PNG", "bmp": "BMP"}, "save image format")
        self.scpi.write(f"SAVe:IMAge:FILEFormat {token}")

    def query_save_image_format(self) -> SaveImageFormatState:
        self._require_tbs2000b("save-image-format")
        value, raw = self._query("SAVe:IMAge:FILEFormat?")
        return SaveImageFormatState(_choice(value, {"PNG": "png", "BMP": "bmp"}, "save image format response"), raw)

    def configure_save_image_ink_saver(self, enabled: bool) -> None:
        self._require_tds2000b_or_tbs1000b("save-image-ink-saver")
        self.scpi.write(f"HARDCopy:INKSaver {'ON' if enabled else 'OFF'}")

    def query_save_image_ink_saver(self) -> SaveBooleanState:
        self._require_tds2000b_or_tbs1000b("save-image-ink-saver")
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

    def save_waveform(self, filename: str, *, source_channel: int | None = None) -> SaveOperationResult:
        filename = validate_save_quoted_string(filename, label="Save filename")
        if source_channel is None:
            raise ParameterValidationError("save-waveform requires source_channel for this model")
        if isinstance(source_channel, bool) or not isinstance(source_channel, int):
            raise ParameterValidationError("source_channel must be an integer")
        channel = self._channel(source_channel)
        command = f'SAVe:WAVEform CH{channel},"{filename}"'
        original_timeout = self.scpi.timeout
        try:
            self.scpi.set_timeout(_SAVE_COMPLETION_TIMEOUT_MS)
            self.scpi.write(command)
            complete = self.query_operation_complete()
            return SaveOperationResult("save-waveform", filename, command, complete.raw)
        finally:
            self.scpi.set_timeout(original_timeout)

    def configure_save_waveform_format(self, format: str) -> None:
        self._require_tbs2000b("save-waveform-format")
        token = _choice(format, {"csv": "SPREADSheet"}, "save waveform format")
        self.scpi.write(f"SAVe:WAVEform:FILEFormat {token}")

    def query_save_waveform_format(self) -> SaveWaveformFormatState:
        self._require_tbs2000b("save-waveform-format")
        value, raw = self._query("SAVe:WAVEform:FILEFormat?")
        return SaveWaveformFormatState(_choice(value, {"SPREADS": "csv", "SPREADSHEET": "csv"}, "waveform format response"), raw)

    def capture_screenshot(self, *, options: ScreenshotOptions, background: str = "black") -> ScreenshotCapture:
        options = normalize_screenshot_options(options)
        background = normalize_screenshot_background(background)
        validate_screenshot_capability(self.capabilities, options)
        if self._is_tbs2000b:
            return self._capture_native_png(options, background)
        from .visa_backend import VisaBackend
        if isinstance(self.backend, VisaBackend):
            resource = self.backend.resource_name.strip().upper()
            if not (resource.startswith("USB") and resource.endswith("::INSTR")):
                raise OscilloscopeError("Tek BMP screenshot capture requires a USBTMC resource.")
        desired_ink = options.ink_saver if options.ink_saver is not None else background == "white"
        temporary_settings = [("HARDCopy:FORMat", "BMP"), ("HARDCopy:PORT", "USB")]
        if options.ink_saver is None:
            temporary_settings.append(("HARDCopy:INKSaver", "ON" if desired_ink else "OFF"))
        originals = [
            (command, self._query(command + "?")[0], desired)
            for command, desired in temporary_settings
        ]
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
            if options.ink_saver is not None:
                self.scpi.write(f"HARDCopy:INKSaver {'ON' if desired_ink else 'OFF'}")
            if options.layout is not None:
                layout = "LANdscape" if options.layout == "landscape" else "PORTRait"
                self.scpi.write(f"HARDCopy:LAYout {layout}")
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

    def capture_screenshot_png(self, *, background: str = "black") -> ScreenshotCapture:
        return self.capture_screenshot(options=ScreenshotOptions(format="png"), background=background)

    def _capture_native_png(self, options: ScreenshotOptions, background: str) -> ScreenshotCapture:
        if background != "black" or options.ink_saver is not None or options.layout is not None:
            raise ParameterValidationError("This model screenshot supports black background without appearance controls")
        from uuid import uuid4
        from contextlib import ExitStack

        filename = f"{uuid4().hex[:8]}.png"
        original_timeout = self.scpi.timeout
        with ExitStack() as restore:
            restore.callback(self.scpi.set_timeout, original_timeout)
            self.scpi.set_timeout(SCREENSHOT_TIMEOUT_MS)
            original_format, _ = self._query("SAVe:IMAge:FILEFormat?")
            original_format = _choice(original_format, {"PNG": "PNG", "BMP": "BMP", "JPG": "JPG"}, "image format response")
            if original_format != "PNG":
                restore.callback(self.scpi.write, f"SAVe:IMAge:FILEFormat {original_format}")
                self.scpi.write("SAVe:IMAge:FILEFormat PNG")
            # Register deletion before the save: a failed save may still create a file.
            restore.callback(self.scpi.write, f'FILESystem:DELEte "{filename}"')
            self.scpi.write(f'SAVe:IMAge "{filename}"')
            self.query_operation_complete()
            self.scpi.write(f'FILESystem:READFile "{filename}"')
            data = screenshot_bytes_from_values_for_format(self.scpi.read_raw(), "png")
            return ScreenshotCapture("PNG", None, data, background)

    def configure_runt_trigger(self, *, channel: int, polarity: str, qualifier: str,
                               low_level_volts: float, high_level_volts: float,
                               time_seconds: float | None = None) -> None:
        self._require_tbs2000b("trigger-runt")
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
        self._require_tbs2000b("trigger-runt")
        mode = self.query_trigger_mode()
        source, source_raw = self._query("TRIGger:A:RUNT:SOUrce?")
        match = re.fullmatch(r"CH([12])", source.upper())
        channel = int(match.group(1)) if match is not None else None
        commands = {"polarity": "TRIGger:A:RUNT:POLarity?", "qualifier": "TRIGger:A:RUNT:WHEn?",
                    "time": "TRIGger:A:RUNT:WIDth?"}
        values = {key: self._query(command) for key, command in commands.items()}
        raw = {"mode": mode.raw_mode, "source": source_raw, **{key: value[1] for key, value in values.items()}}
        low_level = None
        high_level = None
        if channel is not None:
            for key, command in {
                "low_level": f"TRIGger:A:LOWerthreshold:CH{channel}?",
                "high_level": f"TRIGger:A:UPPerthreshold:CH{channel}?",
            }.items():
                value, raw_value = self._query(command)
                raw[key] = raw_value
                parsed = _number(value, command)
                if key == "low_level":
                    low_level = parsed
                else:
                    high_level = parsed
        polarity = {"POS": "positive", "POSITIVE": "positive", "NEG": "negative", "NEGATIVE": "negative"}.get(values["polarity"][0].upper())
        qualifier = {"OCCURS": "none", "LESS": "less-than", "LESSTHAN": "less-than", "MORE": "greater-than", "MORETHAN": "greater-than"}.get(values["qualifier"][0].upper())
        return RuntTriggerState(mode.mode, source, "channel" if channel is not None else None,
            channel, polarity, qualifier, _number(values["time"][0], commands["time"]),
            low_level, high_level, raw)

    def configure_tv_trigger(self, *, source_channel: int, standard: str, mode: str,
                             polarity: str, line: int | None = None) -> TvTriggerState:
        self._require_tds2000b_or_tbs1000b("trigger-tv")
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
        self._require_tds2000b_or_tbs1000b("trigger-tv")
        mode = self.query_trigger_mode()
        root = "TRIGger:MAIn:VIDeo"
        source, source_raw = self._query(f"{root}:SOUrce?")
        match = re.fullmatch(r"CH([1-4])", source.upper())
        channel = int(match[1]) if match is not None else None
        if channel is not None and channel > self.capabilities.analog_channels:
            channel = None
        standard, standard_raw = self._query(f"{root}:STANdard?")
        sync, sync_raw = self._query(f"{root}:SYNC?")
        polarity, polarity_raw = self._query(f"{root}:POLarity?")
        line_value, line_raw = self._query(f"{root}:LINE?")
        line = parse_tv_line_readback(line_value)
        return TvTriggerState(mode.mode, source_raw, channel, standard_raw,
            {"NTSC": "ntsc", "PAL": "pal"}.get(standard.upper()), sync_raw,
            {"ODD": "field1", "EVEN": "field2", "FIELD": "all-fields", "LINE": "all-lines"}.get(sync.upper()),
            line_raw, line, polarity_raw,
            {"INV": "positive", "INVERT": "positive", "NORM": "negative", "NORMAL": "negative"}.get(polarity.upper()))

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
                trigger['level'] = self._float(f"{self._trigger_root}:LEVel:CH{channel}?" if self._is_tbs2000b else f"{self._trigger_root}:LEVel?")
                trigger['units'] = entries[channel - 1].units
        position = self.query_timebase_position()
        return dict(channels=channels, timebase=dict(scale=self.query_timebase_scale(), position=position),
                    trigger=trigger)


def _unsupported(self: TektronixOscilloscope, *args: object, **kwargs: object) -> None:
    raise ParameterValidationError("Operation is unsupported for this Tektronix model")


_SUPPORTED_METHODS = {
    "query_idn", "close", "post_command_status", "post_webui_operation_status",
    "uses_autoscale_error_recovery",
    "validate_acquisition_count", "cleanup",
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
