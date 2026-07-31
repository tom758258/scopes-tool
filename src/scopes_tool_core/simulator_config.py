"""Configuration parsing for the deterministic simulator backend."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from .acquisition import normalize_acquisition_type, validate_acquisition_count
from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel, validate_channel_offset, validate_channel_scale
from .errors import OscilloscopeError
from .simulator_backend import SimulatedSignal
from .timebase import validate_timebase_position, validate_timebase_scale
from .trigger import normalize_edge_slope, validate_trigger_level


_SCENARIO_KEYS = frozenset(
    ("preset", "signals", "channels", "timebase", "trigger", "acquisition", "errors")
)
_SIGNAL_KEYS = frozenset(
    ("shape", "frequency_hz", "vpp_v", "offset_v", "phase_deg", "noise_rms_v")
)
_CHANNEL_KEYS = frozenset(("display", "scale_v_per_div", "offset_v"))
_TIMEBASE_KEYS = frozenset(("scale_s_per_div", "position_s"))
_TRIGGER_KEYS = frozenset(("source_channel", "level_v", "slope"))
_ACQUISITION_KEYS = frozenset(("type", "count"))
_ERROR_KEYS = frozenset(
    (
        "system_errors",
        "binary_transfer_failure",
        "invalid_measurement_channels",
        "display_off_channels",
    )
)


PRESET_NAMES = (
    "noisy-sine",
    "square-with-offset",
    "phase-shifted-pair",
    "dc-invalid-frequency",
    "trigger-misaligned",
)


_PRESETS: dict[str, dict[str, Any]] = {
    "noisy-sine": {
        "signals": {
            "CH1": {
                "shape": "sine",
                "frequency_hz": 1000.0,
                "vpp_v": 1.0,
                "offset_v": 0.0,
                "phase_deg": 0.0,
                "noise_rms_v": 0.03,
            }
        }
    },
    "square-with-offset": {
        "signals": {
            "CH1": {
                "shape": "square",
                "frequency_hz": 1000.0,
                "vpp_v": 2.0,
                "offset_v": 0.5,
                "phase_deg": 0.0,
                "noise_rms_v": 0.0,
            }
        },
        "channels": {"CH1": {"scale_v_per_div": 0.5}},
    },
    "phase-shifted-pair": {
        "signals": {
            "CH1": {
                "shape": "sine",
                "frequency_hz": 1000.0,
                "vpp_v": 1.0,
                "offset_v": 0.0,
                "phase_deg": 0.0,
                "noise_rms_v": 0.0,
            },
            "CH2": {
                "shape": "sine",
                "frequency_hz": 1000.0,
                "vpp_v": 1.0,
                "offset_v": 0.0,
                "phase_deg": 90.0,
                "noise_rms_v": 0.0,
            },
        }
    },
    "dc-invalid-frequency": {
        "signals": {
            "CH1": {
                "shape": "dc",
                "frequency_hz": 0.0,
                "vpp_v": 0.0,
                "offset_v": 1.25,
                "phase_deg": 0.0,
                "noise_rms_v": 0.0,
            }
        }
    },
    "trigger-misaligned": {
        "signals": {
            "CH1": {
                "shape": "sine",
                "frequency_hz": 1000.0,
                "vpp_v": 1.0,
                "offset_v": 0.0,
                "phase_deg": 0.0,
                "noise_rms_v": 0.0,
            }
        },
        "trigger": {"source_channel": "CH1", "level_v": 5.0, "slope": "positive"},
    },
}


def simulator_backend_kwargs(
    args: Any, resource: str, capabilities: ScopeCapabilities
) -> dict[str, Any]:
    """Return keyword arguments for ``SimulatorBackend`` from CLI arguments."""

    config: dict[str, Any] = {}
    cli_preset = getattr(args, "simulate_preset", None)
    if cli_preset:
        _merge_config(config, _preset(cli_preset))

    scenario_path = getattr(args, "simulate_scenario", None)
    if scenario_path:
        scenario = load_scenario(Path(scenario_path))
        scenario_preset = scenario.get("preset")
        if scenario_preset:
            _merge_config(config, _preset(_require_string(scenario_preset, "preset")))
        scenario_without_preset = dict(scenario)
        scenario_without_preset.pop("preset", None)
        _merge_config(config, scenario_without_preset)

    signal_overrides = _parse_simulate_signal_specs(
        getattr(args, "simulate_signals", []), capabilities
    )
    if signal_overrides:
        config.setdefault("signals", {}).update(
            {f"CH{channel}": signal for channel, signal in signal_overrides.items()}
        )

    errors = config.setdefault("errors", {})
    for entry in getattr(args, "simulate_system_errors", []) or []:
        errors.setdefault("system_errors", []).append(_parse_system_error_cli(entry))
    if getattr(args, "simulate_binary_transfer_failure", False):
        errors["binary_transfer_failure"] = True
    if getattr(args, "simulate_invalid_measurement_channels", None):
        errors.setdefault("invalid_measurement_channels", []).extend(
            getattr(args, "simulate_invalid_measurement_channels")
        )
    if getattr(args, "simulate_display_off_channels", None):
        errors.setdefault("display_off_channels", []).extend(
            getattr(args, "simulate_display_off_channels")
        )

    parsed = parse_config(config, capabilities)
    parsed.update(
        {
            "physical_model_id": args.planning_physical_model_id,
            "resource_name": resource,
        }
    )
    return parsed


def validate_simulator_args(args: Any, capabilities: ScopeCapabilities) -> None:
    """Validate simulator-only arguments and any referenced scenario."""

    _parse_simulate_signal_specs(getattr(args, "simulate_signals", []), capabilities)
    simulator_backend_kwargs(
        args,
        f"SIM::{args.planning_physical_model_id}::INSTR",
        capabilities,
    )


def load_scenario(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OscilloscopeError(f"could not read --simulate-scenario {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OscilloscopeError(
            f"invalid --simulate-scenario JSON {path}: {exc.msg} at line {exc.lineno} column {exc.colno}"
        ) from exc
    if not isinstance(data, dict):
        raise OscilloscopeError("--simulate-scenario JSON must contain an object")
    _reject_unknown(data, _SCENARIO_KEYS, "scenario")
    return data


def parse_config(config: Mapping[str, Any], capabilities: ScopeCapabilities) -> dict[str, Any]:
    _reject_unknown(config, _SCENARIO_KEYS - {"preset"}, "simulator config")
    kwargs: dict[str, Any] = {}

    if "signals" in config:
        kwargs["signals"] = _parse_signals(config["signals"], capabilities)
    if "channels" in config:
        channel_display, channel_scale, channel_offset = _parse_channels(
            config["channels"], capabilities
        )
        kwargs["channel_display"] = channel_display
        kwargs["channel_scale"] = channel_scale
        kwargs["channel_offset"] = channel_offset
    if "timebase" in config:
        kwargs.update(_parse_timebase(config["timebase"]))
    if "trigger" in config:
        kwargs.update(_parse_trigger(config["trigger"], capabilities))
    if "acquisition" in config:
        kwargs.update(_parse_acquisition(config["acquisition"]))
    if "errors" in config:
        _apply_errors(kwargs, config["errors"], capabilities)
    return kwargs


def _parse_signals(raw: Any, capabilities: ScopeCapabilities) -> dict[int, SimulatedSignal]:
    if not isinstance(raw, dict):
        raise OscilloscopeError("scenario signals must be an object")
    signals: dict[int, SimulatedSignal] = {}
    for key, value in raw.items():
        channel = _parse_channel_token(key, "signals")
        validate_analog_channel(channel, capabilities)
        if isinstance(value, SimulatedSignal):
            signals[channel] = value
            continue
        if not isinstance(value, dict):
            raise OscilloscopeError(f"scenario signals CH{channel} must be an object")
        _reject_unknown(value, _SIGNAL_KEYS, f"scenario signals CH{channel}")
        try:
            signals[channel] = SimulatedSignal(
                shape=str(value.get("shape", "sine")),
                frequency_hz=_finite_float(value.get("frequency_hz", 1000.0), f"CH{channel} frequency_hz"),
                vpp_v=_finite_float(value.get("vpp_v", 0.5 * channel), f"CH{channel} vpp_v"),
                offset_v=_finite_float(value.get("offset_v", 0.0), f"CH{channel} offset_v"),
                phase_deg=_finite_float(value.get("phase_deg", 0.0), f"CH{channel} phase_deg"),
                noise_rms_v=_finite_float(value.get("noise_rms_v", 0.0), f"CH{channel} noise_rms_v"),
            )
        except OscilloscopeError as exc:
            raise OscilloscopeError(f"invalid scenario signal CH{channel}: {exc}") from exc
    return signals


def _parse_channels(raw: Any, capabilities: ScopeCapabilities) -> tuple[dict[int, bool], dict[int, float], dict[int, float]]:
    if not isinstance(raw, dict):
        raise OscilloscopeError("scenario channels must be an object")
    displays: dict[int, bool] = {}
    scales: dict[int, float] = {}
    offsets: dict[int, float] = {}
    for key, value in raw.items():
        channel = _parse_channel_token(key, "channels")
        validate_analog_channel(channel, capabilities)
        if not isinstance(value, dict):
            raise OscilloscopeError(f"scenario channels CH{channel} must be an object")
        _reject_unknown(value, _CHANNEL_KEYS, f"scenario channels CH{channel}")
        if "display" in value:
            displays[channel] = _bool(value["display"], f"CH{channel} display")
        if "scale_v_per_div" in value:
            scales[channel] = validate_channel_scale(
                _finite_float(value["scale_v_per_div"], f"CH{channel} scale_v_per_div")
            )
        if "offset_v" in value:
            offsets[channel] = validate_channel_offset(
                _finite_float(value["offset_v"], f"CH{channel} offset_v")
            )
    return displays, scales, offsets


def _parse_timebase(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise OscilloscopeError("scenario timebase must be an object")
    _reject_unknown(raw, _TIMEBASE_KEYS, "scenario timebase")
    values: dict[str, Any] = {}
    if "scale_s_per_div" in raw:
        values["timebase_scale"] = validate_timebase_scale(
            _finite_float(raw["scale_s_per_div"], "timebase scale_s_per_div")
        )
    if "position_s" in raw:
        values["timebase_position"] = validate_timebase_position(
            _finite_float(raw["position_s"], "timebase position_s")
        )
    return values


def _parse_trigger(raw: Any, capabilities: ScopeCapabilities) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise OscilloscopeError("scenario trigger must be an object")
    _reject_unknown(raw, _TRIGGER_KEYS, "scenario trigger")
    values: dict[str, Any] = {"trigger_mode": "EDGE"}
    if "source_channel" in raw:
        channel = _parse_channel_token(raw["source_channel"], "trigger source_channel")
        values["trigger_source"] = validate_analog_channel(channel, capabilities)
    if "level_v" in raw:
        values["trigger_level"] = validate_trigger_level(
            _finite_float(raw["level_v"], "trigger level_v")
        )
    if "slope" in raw:
        values["trigger_slope"] = normalize_edge_slope(str(raw["slope"]))
    return values


def _parse_acquisition(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise OscilloscopeError("scenario acquisition must be an object")
    _reject_unknown(raw, _ACQUISITION_KEYS, "scenario acquisition")
    values: dict[str, Any] = {}
    acq_type = raw.get("type")
    if acq_type is not None:
        values["acquisition_type"] = normalize_acquisition_type(str(acq_type))
    if "count" in raw:
        count = raw["count"]
        if not isinstance(count, int) or isinstance(count, bool):
            raise OscilloscopeError("scenario acquisition count must be an integer")
        values["acquisition_count"] = validate_acquisition_count(count)
    return values


def _apply_errors(kwargs: dict[str, Any], raw: Any, capabilities: ScopeCapabilities) -> None:
    if not isinstance(raw, dict):
        raise OscilloscopeError("scenario errors must be an object")
    _reject_unknown(raw, _ERROR_KEYS, "scenario errors")
    system_errors = [_format_system_error(entry) for entry in raw.get("system_errors", [])]
    if system_errors:
        kwargs["system_errors"] = system_errors
    if raw.get("binary_transfer_failure", False):
        failure = OscilloscopeError("simulated binary transfer failure")
        binary_failures = kwargs.setdefault("binary_failures", {})
        binary_failures[":WAVeform:DATA?"] = failure
        binary_failures[":LISTer:DATA?"] = failure
    invalid_channels = _parse_channel_list(
        raw.get("invalid_measurement_channels", []),
        "invalid_measurement_channels",
        capabilities,
    )
    if invalid_channels:
        kwargs["invalid_measurement_channels"] = invalid_channels
    display_off_channels = _parse_channel_list(
        raw.get("display_off_channels", []), "display_off_channels", capabilities
    )
    if display_off_channels:
        kwargs.setdefault("channel_display", {}).update(
            {channel: False for channel in display_off_channels}
        )


def _parse_simulate_signal_specs(
    specs: Sequence[str], capabilities: ScopeCapabilities
) -> dict[int, SimulatedSignal]:
    signals: dict[int, SimulatedSignal] = {}
    for spec in specs:
        channel, signal = parse_simulate_signal_spec(spec)
        validate_analog_channel(channel, capabilities)
        if channel in signals:
            raise OscilloscopeError(f"duplicate --simulate-signal for CH{channel}")
        signals[channel] = signal
    return signals


def parse_simulate_signal_spec(spec: str) -> tuple[int, SimulatedSignal]:
    parts = spec.split(":")
    if len(parts) not in (6, 7):
        raise OscilloscopeError(
            "--simulate-signal must use "
            "CH:shape:frequency_hz:vpp_v:offset_v:phase_deg[:noise_rms_v]"
        )
    channel = _parse_channel_token(parts[0], "--simulate-signal channel")
    try:
        signal = SimulatedSignal(
            shape=parts[1].strip().lower(),
            frequency_hz=float(parts[2]),
            vpp_v=float(parts[3]),
            offset_v=float(parts[4]),
            phase_deg=float(parts[5]),
            noise_rms_v=float(parts[6]) if len(parts) == 7 else 0.0,
        )
    except ValueError as exc:
        raise OscilloscopeError("--simulate-signal numeric fields must be numbers") from exc
    except OscilloscopeError as exc:
        raise OscilloscopeError(f"invalid --simulate-signal {spec!r}: {exc}") from exc
    return channel, signal


def _merge_config(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, Mapping) and key in {
            "signals",
            "channels",
            "timebase",
            "trigger",
            "acquisition",
            "errors",
        }:
            existing = target.setdefault(key, {})
            if not isinstance(existing, dict):
                target[key] = dict(value)
            elif key in {"signals", "channels"}:
                for item_key, item_value in value.items():
                    if isinstance(item_value, Mapping) and isinstance(existing.get(item_key), dict):
                        existing[item_key].update(item_value)
                    else:
                        existing[item_key] = item_value
            elif key == "errors":
                _merge_errors(existing, value)
            else:
                existing.update(value)
        else:
            target[key] = value


def _merge_errors(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if key in {"system_errors", "invalid_measurement_channels", "display_off_channels"}:
            target.setdefault(key, []).extend(value)
        else:
            target[key] = value


def _preset(name: str) -> dict[str, Any]:
    try:
        return deepcopy(_PRESETS[name])
    except KeyError as exc:
        supported = ", ".join(PRESET_NAMES)
        raise OscilloscopeError(
            f"unknown simulator preset {name!r}; expected one of: {supported}"
        ) from exc


def _parse_system_error_cli(code: str) -> dict[str, Any]:
    try:
        parsed = int(code)
    except ValueError as exc:
        raise OscilloscopeError("--simulate-system-error CODE must be an integer") from exc
    return {"code": parsed, "message": "Simulated system error"}


def _format_system_error(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        raise OscilloscopeError("scenario errors system_errors entries must be objects")
    code = entry.get("code")
    message = entry.get("message", "Simulated system error")
    if not isinstance(code, int) or isinstance(code, bool):
        raise OscilloscopeError("scenario system error code must be an integer")
    if not isinstance(message, str):
        raise OscilloscopeError("scenario system error message must be a string")
    return f'{code},"{message}"'


def _parse_channel_list(
    raw: Any, name: str, capabilities: ScopeCapabilities
) -> set[int]:
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise OscilloscopeError(f"scenario errors {name} must be a list")
    channels = set()
    for item in raw:
        channel = _parse_channel_token(item, name)
        channels.add(validate_analog_channel(channel, capabilities))
    return channels


def _parse_channel_token(value: Any, context: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        channel = value
    elif isinstance(value, str):
        normalized = value.strip().upper()
        if normalized.startswith("CH"):
            normalized = normalized[2:]
        try:
            channel = int(normalized)
        except ValueError as exc:
            raise OscilloscopeError(f"{context} channel must be CHn or a positive integer") from exc
    else:
        raise OscilloscopeError(f"{context} channel must be CHn or a positive integer")
    if channel < 1:
        raise OscilloscopeError(f"{context} channel must be at least 1")
    return channel


def _finite_float(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise OscilloscopeError(f"scenario {name} must be a number") from exc
    if not math.isfinite(parsed):
        raise OscilloscopeError(f"scenario {name} must be finite")
    return parsed


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise OscilloscopeError(f"scenario {name} must be true or false")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise OscilloscopeError(f"scenario {name} must be a string")
    return value


def _reject_unknown(raw: Mapping[str, Any], allowed: frozenset[str], context: str) -> None:
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        raise OscilloscopeError(f"unknown {context} key: {unknown[0]}")
