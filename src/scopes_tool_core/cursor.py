"""Cursor controls and auto-adjustment plans."""

from __future__ import annotations

from dataclasses import dataclass

from .capabilities import ScopeCapabilities
from .channel import (
    channel_offset_command,
    channel_offset_query,
    channel_scale_command,
    channel_scale_query,
    validate_analog_channel,
)
from .errors import ParameterValidationError
from .math import _format_scpi_number, validate_finite_number
from .scpi import SCPIClient


@dataclass(frozen=True)
class CursorState:
    mode: str
    x1_seconds: float
    x2_seconds: float
    y1_volts: float
    y2_volts: float
    x_delta_seconds: float
    y_delta_volts: float
    dydx: float

@dataclass(frozen=True)
class CursorAutoTimebaseResult:
    enabled: bool
    strategy: str
    changed: bool | None
    original_scale_seconds_per_division: float | None
    original_position_seconds: float | None
    target_scale_seconds_per_division: float | None
    commands: tuple[str, ...]
    reason: str

@dataclass(frozen=True)
class CursorAutoVerticalResult:
    enabled: bool
    strategy: str
    changed: bool | None
    offset_changed: bool | None
    original_scale_volts_per_division: float | None
    original_offset_volts: float | None
    target_scale_volts_per_division: float | None
    target_offset_volts: float | None
    commands: tuple[str, ...]
    reason: str

class CursorController:
    """Manual marker/cursor controls."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def set_manual(
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
        source_channel = validate_analog_channel(source_channel, self.capabilities)
        pending_commands = cursor_configure_commands(
            source_channel,
            x1_seconds,
            x2_seconds,
            y1_volts=y1_volts,
            y2_volts=y2_volts,
            capabilities=self.capabilities,
        )
        if auto_timebase:
            scale = self.scpi.query_float(":TIMebase:SCALe?")
            position = self.scpi.query_float(":TIMebase:POSition?")
            auto_result = cursor_auto_timebase_plan(
                scale,
                position,
                x1_seconds,
                x2_seconds,
            )
            if auto_result.changed and auto_result.target_scale_seconds_per_division is not None:
                self.scpi.write(
                    f":TIMebase:SCALe {_format_scpi_number(auto_result.target_scale_seconds_per_division)}"
                )
        if auto_vertical:
            scale = self.scpi.query_float(channel_scale_query(source_channel))
            offset = self.scpi.query_float(channel_offset_query(source_channel))
            auto_vertical_result = cursor_auto_vertical_plan(
                source_channel,
                scale,
                offset,
                y1_volts=y1_volts,
                y2_volts=y2_volts,
                capabilities=self.capabilities,
            )
            if auto_vertical_result.changed:
                assert auto_vertical_result.target_scale_volts_per_division is not None
                assert auto_vertical_result.target_offset_volts is not None
                self.scpi.write(
                    channel_scale_command(
                        source_channel,
                        auto_vertical_result.target_scale_volts_per_division,
                    )
                )
                if auto_vertical_result.offset_changed:
                    self.scpi.write(
                        channel_offset_command(
                            source_channel,
                            auto_vertical_result.target_offset_volts,
                        )
                    )
        for command in pending_commands:
            self.scpi.write(command)

    def off(self) -> None:
        self.scpi.write(":MARKer:MODE OFF")

    def query(self) -> CursorState:
        return CursorState(
            mode=self.scpi.query(":MARKer:MODE?"),
            x1_seconds=self.scpi.query_float(":MARKer:X1Position?"),
            x2_seconds=self.scpi.query_float(":MARKer:X2Position?"),
            y1_volts=self.scpi.query_float(":MARKer:Y1Position?"),
            y2_volts=self.scpi.query_float(":MARKer:Y2Position?"),
            x_delta_seconds=self.scpi.query_float(":MARKer:XDELta?"),
            y_delta_volts=self.scpi.query_float(":MARKer:YDELta?"),
            dydx=self.scpi.query_float(":MARKer:DYDX?"),
        )

def cursor_configure_commands(
    source_channel: int,
    x1_seconds: float,
    x2_seconds: float,
    *,
    y1_volts: float | None = None,
    y2_volts: float | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    channel = (
        validate_analog_channel(source_channel, capabilities)
        if capabilities is not None
        else source_channel
    )
    x1_seconds = validate_finite_number(x1_seconds, "--x1")
    x2_seconds = validate_finite_number(x2_seconds, "--x2")
    commands = [
        ":MARKer:MODE MANual",
        f":MARKer:X1Y1source CHANnel{channel}",
        f":MARKer:X2Y2source CHANnel{channel}",
        f":MARKer:X1Position {_format_scpi_number(x1_seconds)}",
        f":MARKer:X2Position {_format_scpi_number(x2_seconds)}",
    ]
    if y1_volts is not None:
        commands.append(
            f":MARKer:Y1Position {_format_scpi_number(validate_finite_number(y1_volts, '--y1'))}"
        )
    if y2_volts is not None:
        commands.append(
            f":MARKer:Y2Position {_format_scpi_number(validate_finite_number(y2_volts, '--y2'))}"
        )
    return commands

def cursor_auto_timebase_plan(
    current_scale_seconds_per_division: float,
    current_position_seconds: float,
    x1_seconds: float,
    x2_seconds: float,
) -> CursorAutoTimebaseResult:
    current_scale_seconds_per_division = validate_finite_number(
        current_scale_seconds_per_division,
        "timebase scale",
    )
    current_position_seconds = validate_finite_number(
        current_position_seconds,
        "timebase position",
    )
    if current_scale_seconds_per_division <= 0:
        raise ParameterValidationError("timebase scale must be greater than 0 s/div.")
    x1_seconds = validate_finite_number(x1_seconds, "--x1")
    x2_seconds = validate_finite_number(x2_seconds, "--x2")

    visible_half_span_seconds = current_scale_seconds_per_division * 4.5
    max_delta_seconds = max(
        abs(x1_seconds - current_position_seconds),
        abs(x2_seconds - current_position_seconds),
    )
    changed = max_delta_seconds > visible_half_span_seconds
    target_scale = (
        max(current_scale_seconds_per_division, max_delta_seconds / 4.0)
        if changed
        else current_scale_seconds_per_division
    )
    commands = [":TIMebase:SCALe?", ":TIMebase:POSition?"]
    if changed:
        commands.append(f":TIMebase:SCALe {_format_scpi_number(target_scale)}")
    reason = (
        "requested X cursor position is outside the current visible half-span"
        if changed
        else "requested X cursor positions fit within the current visible half-span"
    )
    return CursorAutoTimebaseResult(
        enabled=True,
        strategy="scale_only",
        changed=changed,
        original_scale_seconds_per_division=current_scale_seconds_per_division,
        original_position_seconds=current_position_seconds,
        target_scale_seconds_per_division=target_scale,
        commands=tuple(commands),
        reason=reason,
    )

def cursor_auto_timebase_dry_run_plan() -> CursorAutoTimebaseResult:
    return CursorAutoTimebaseResult(
        enabled=True,
        strategy="scale_only",
        changed=None,
        original_scale_seconds_per_division=None,
        original_position_seconds=None,
        target_scale_seconds_per_division=None,
        commands=(":TIMebase:SCALe?", ":TIMebase:POSition?"),
        reason=(
            "dry-run will query the current timebase and widen scale only if the "
            "requested X cursor positions are outside the visible range"
        ),
    )

def cursor_auto_timebase_json(result: CursorAutoTimebaseResult) -> dict[str, object]:
    return {
        "enabled": result.enabled,
        "strategy": result.strategy,
        "changed": result.changed,
        "original_scale_seconds_per_division": result.original_scale_seconds_per_division,
        "original_position_seconds": result.original_position_seconds,
        "target_scale_seconds_per_division": result.target_scale_seconds_per_division,
        "commands": list(result.commands),
        "reason": result.reason,
    }

def cursor_auto_vertical_plan(
    source_channel: int,
    current_scale_volts_per_division: float,
    current_offset_volts: float,
    *,
    y1_volts: float | None = None,
    y2_volts: float | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> CursorAutoVerticalResult:
    channel = (
        validate_analog_channel(source_channel, capabilities)
        if capabilities is not None
        else source_channel
    )
    current_scale_volts_per_division = validate_finite_number(
        current_scale_volts_per_division,
        "channel scale",
    )
    current_offset_volts = validate_finite_number(
        current_offset_volts,
        "channel offset",
    )
    if current_scale_volts_per_division <= 0:
        raise ParameterValidationError("channel scale must be greater than 0 V/div.")
    targets = _cursor_y_targets(y1_volts=y1_volts, y2_volts=y2_volts)
    min_y = min(targets)
    max_y = max(targets)
    usable_half_span_volts = current_scale_volts_per_division * 3.5
    max_delta_volts = max(abs(value - current_offset_volts) for value in targets)
    changed = max_delta_volts > usable_half_span_volts
    target_scale = current_scale_volts_per_division
    target_offset = current_offset_volts
    offset_changed = False
    commands = [channel_scale_query(channel), channel_offset_query(channel)]
    if changed:
        scale_only = max(current_scale_volts_per_division, max_delta_volts / 3.5)
        midpoint = (min_y + max_y) / 2.0
        midpoint_half_span = max(abs(min_y - midpoint), abs(max_y - midpoint))
        midpoint_scale = max(current_scale_volts_per_division, midpoint_half_span / 3.5)
        if scale_only >= midpoint_scale * 1.5:
            target_scale = midpoint_scale
            target_offset = midpoint
            offset_changed = target_offset != current_offset_volts
        else:
            target_scale = scale_only
        commands.append(channel_scale_command(channel, target_scale))
        if offset_changed:
            commands.append(channel_offset_command(channel, target_offset))
    reason = (
        "requested Y cursor position is outside the current vertical display range"
        if changed
        else "requested Y cursor positions fit within the current vertical display range"
    )
    return CursorAutoVerticalResult(
        enabled=True,
        strategy="scale_then_offset",
        changed=changed,
        offset_changed=offset_changed,
        original_scale_volts_per_division=current_scale_volts_per_division,
        original_offset_volts=current_offset_volts,
        target_scale_volts_per_division=target_scale,
        target_offset_volts=target_offset,
        commands=tuple(commands),
        reason=reason,
    )

def cursor_auto_vertical_dry_run_plan(source_channel: int) -> CursorAutoVerticalResult:
    return CursorAutoVerticalResult(
        enabled=True,
        strategy="scale_then_offset",
        changed=None,
        offset_changed=None,
        original_scale_volts_per_division=None,
        original_offset_volts=None,
        target_scale_volts_per_division=None,
        target_offset_volts=None,
        commands=(channel_scale_query(source_channel), channel_offset_query(source_channel)),
        reason=(
            "dry-run will query the source channel vertical settings and adjust "
            "scale/offset only if requested Y cursor positions are outside the "
            "visible range"
        ),
    )

def cursor_auto_vertical_json(result: CursorAutoVerticalResult) -> dict[str, object]:
    return {
        "enabled": result.enabled,
        "strategy": result.strategy,
        "changed": result.changed,
        "offset_changed": result.offset_changed,
        "original_scale_volts_per_division": result.original_scale_volts_per_division,
        "original_offset_volts": result.original_offset_volts,
        "target_scale_volts_per_division": result.target_scale_volts_per_division,
        "target_offset_volts": result.target_offset_volts,
        "commands": list(result.commands),
        "reason": result.reason,
    }

def _cursor_y_targets(*, y1_volts: float | None, y2_volts: float | None) -> tuple[float, ...]:
    targets = []
    if y1_volts is not None:
        targets.append(validate_finite_number(y1_volts, "--y1"))
    if y2_volts is not None:
        targets.append(validate_finite_number(y2_volts, "--y2"))
    if not targets:
        raise ParameterValidationError("--auto-vertical requires --y1 or --y2.")
    return tuple(targets)
