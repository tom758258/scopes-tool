"""Shared argparse helpers for the Scopes Tool CLI parsers."""

from __future__ import annotations

import argparse

from scopes_tool_core.channel import (
    validate_channel_offset,
    validate_channel_scale,
    validate_probe_ratio,
    validate_probe_skew,
)
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.simulator_config import PRESET_NAMES
from scopes_tool_core.timebase import (
    validate_timebase_position,
    validate_timebase_scale,
)
from scopes_tool_core.trigger import validate_trigger_level
from scopes_tool_core.waveform import SUPPORTED_WAVEFORM_POINTS

def _add_channel_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )


def _add_bus_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bus", type=_positive_int, required=True)


def _add_function_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--function", type=_positive_int, required=True)


def _add_slot_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--slot", type=_positive_int, required=True)


def _add_scope_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--resource",
        default=None,
        help="VISA resource string. Defaults to SCOPES_TOOL_RESOURCE.",
    )
    parser.add_argument(
        "--visa-library",
        default=None,
        help="optional PyVISA library argument, such as @py",
    )
    parser.add_argument(
        "--log-scpi",
        action="store_true",
        help="write SCPI command and response logs to stderr",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="write a single machine-readable JSON object to stdout",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="use the deterministic hardware-free simulator backend",
    )
    parser.add_argument(
        "--simulate-signal",
        dest="simulate_signals",
        action="append",
        default=[],
        metavar="CH:shape:frequency_hz:vpp_v:offset_v:phase_deg[:noise_rms_v]",
        help=(
            "override one simulator channel signal; repeat per channel. "
            "Only valid with --simulate"
        ),
    )
    parser.add_argument(
        "--simulate-preset",
        choices=PRESET_NAMES,
        default=None,
        help="apply a built-in simulator preset; only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-scenario",
        default=None,
        help="load simulator scenario JSON; only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-system-error",
        dest="simulate_system_errors",
        action="append",
        default=[],
        metavar="CODE",
        help="seed one simulator system error code; repeatable and only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-binary-transfer-failure",
        action="store_true",
        help="fail simulator waveform binary transfers; only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-invalid-measurement",
        dest="simulate_invalid_measurement_channels",
        action="append",
        default=[],
        metavar="CH",
        help="make simulator measurements invalid for a channel; repeatable and only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-display-off",
        dest="simulate_display_off_channels",
        action="append",
        default=[],
        metavar="CH",
        help="start a simulator channel display off; repeatable and only valid with --simulate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate arguments and report the planned SCPI without opening a backend",
    )
    parser.add_argument(
        "--model",
        default="keysight-dsox4024a",
        help=(
            "canonical physical model ID used for dry-run and simulation planning; "
            "live execution uses the identity detected from *IDN?; "
            "defaults to keysight-dsox4024a"
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="one-shot compatibility flag for live mode; cannot be combined with --simulate or --dry-run",
    )


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _capture_until_count(value: str) -> int:
    parsed = _positive_int(value)
    if parsed > 255:
        raise argparse.ArgumentTypeError("must be between 1 and 255")
    return parsed


def _integer_value(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer or 0x hexadecimal value") from exc


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _capture_channel_arg(value: str) -> int | str:
    if value.strip().lower() == "all":
        return "all"
    try:
        return _positive_int(value)
    except argparse.ArgumentTypeError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer or all") from exc


def _finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_channel_offset(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_channel_scale(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _nonnegative_finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not parsed == parsed or parsed in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("must be finite")
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _probe_ratio_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_probe_ratio(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _probe_skew_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_probe_skew(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _finite_timebase_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_timebase_position(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _positive_timebase_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_timebase_scale(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _trigger_level_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_trigger_level(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _holdoff_seconds_arg(value: str) -> float:
    # The model-specific holdoff range is validated after model resolution.
    return _positive_plain_float(value)


def _strict_bool_arg(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("must be true or false")


def _setup_slot_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0 or parsed > 9:
        raise argparse.ArgumentTypeError("must be between 0 and 9")
    return parsed


def _positive_plain_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not parsed == parsed or parsed in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("must be finite")
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _measurement_finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not parsed == parsed or parsed in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("must be a finite number")
    return parsed


def _waveform_points_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed not in SUPPORTED_WAVEFORM_POINTS:
        supported = ", ".join(str(point_count) for point_count in SUPPORTED_WAVEFORM_POINTS)
        raise argparse.ArgumentTypeError(
            f"waveform capture supports only these point counts: {supported}"
        )
    return parsed
