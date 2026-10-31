"""Focused Core contracts for native numeric measurement streaming."""

from types import SimpleNamespace

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.measure_stream import (
    run_measure_stream,
    validate_measure_stream_options,
)
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


MODEL = "keysight-dsox4024a"


def _options(measurements=None, **kwargs):
    return validate_measure_stream_options(
        {
            "measurements": measurements or [
                {"id": "frequency", "channel": 1, "item": "frequency"},
                {"id": "vpp", "channel": 2, "item": "vpp"},
            ],
            **kwargs,
        },
        capabilities_for_model_id(MODEL),
    )


def test_measure_stream_real_simulator_multi_item_and_finite_cycles():
    with Oscilloscope(
        SimulatorBackend(physical_model_id=MODEL, resource_name=f"SIM::{MODEL}::INSTR")
    ) as scope:
        scope.query_idn()
        samples = []
        completed, invalid, reason = run_measure_stream(
            scope, _options(count=3, interval_seconds=0),
            stop_requested=lambda: False,
            wait_or_stop=lambda _seconds: False,
            sample_reporter=samples.append,
        )
    assert (completed, invalid, reason) == (3, 0, "count_reached")
    assert [s["index"] for s in samples] == [1, 2, 3]
    for sample in samples:
        assert list(sample["values"]) == ["frequency", "vpp"]
        assert sample["values"]["frequency"]["unit"] == "Hz"
        assert sample["values"]["vpp"]["unit"] == "V"
        assert all(value["valid"] for value in sample["values"].values())


def test_measure_stream_native_infinite_stops_and_wait_is_interruptible():
    samples = []
    waited = []
    with Oscilloscope(
        SimulatorBackend(physical_model_id=MODEL, resource_name=f"SIM::{MODEL}::INSTR")
    ) as scope:
        scope.query_idn()
        completed, _, reason = run_measure_stream(
            scope, _options(interval_seconds=0.5),
            stop_requested=lambda: len(samples) >= 2,
            wait_or_stop=lambda seconds: (waited.append(seconds), False)[1],
            sample_reporter=samples.append,
        )
    assert (completed, reason) == (2, "stop_requested")
    assert waited == [0.5, 0.5]


def test_measure_stream_invalid_value_and_partial_cycle_are_not_published():
    options = _options(count=2, interval_seconds=0)
    count = 0
    def query(channel, item, **_kwargs):
        nonlocal count
        count += 1
        if channel == 1:
            return SimpleNamespace(valid=False, value=None, unit="Hz",
                                   reason="invalid measurement sentinel")
        return SimpleNamespace(valid=True, value=2.5, unit="V", reason=None)
    scope = SimpleNamespace(
        capabilities=capabilities_for_model_id(MODEL),
        query_measurement=query,
    )
    samples = []
    completed, invalid, reason = run_measure_stream(
        scope, options, stop_requested=lambda: False,
        wait_or_stop=lambda _seconds: False,
        sample_reporter=samples.append,
    )
    assert (completed, invalid, reason) == (2, 2, "count_reached")
    assert samples[0]["values"]["frequency"] == {
        "value": None, "unit": "Hz", "valid": False,
        "reason": "invalid measurement sentinel",
    }
    assert samples[0]["values"]["vpp"]["value"] == 2.5

    count = 0
    samples = []
    completed, _, reason = run_measure_stream(
        scope, _options(count=1),
        stop_requested=lambda: count == 1,
        wait_or_stop=lambda _seconds: False,
        sample_reporter=samples.append,
    )
    assert (completed, reason, samples) == (0, "stop_requested", [])


@pytest.mark.parametrize("arguments", [
    {"measurements": []},
    {"measurements": [{"id": "x", "channel": 1, "item": "frequency"}], "count": 0},
    {"measurements": [{"id": "x", "channel": 1, "item": "frequency"}], "interval_seconds": -1},
    {"measurements": [{"id": "x", "channel": 1, "item": "frequency"}], "interval_seconds": float("nan")},
    {"measurements": [{"id": "x", "channel": 1, "item": "frequency"}, {"id": "x", "channel": 2, "item": "vpp"}]},
    {"measurements": [{"id": "x", "channel": 99, "item": "frequency"}]},
    {"measurements": [{"id": "x", "channel": 1, "item": "not_a_measure"}]},
])
def test_stream_request_invalid_fields_are_rejected_before_hardware(arguments):
    with pytest.raises((OscilloscopeError, ValueError)):
        validate_measure_stream_options(arguments, capabilities_for_model_id(MODEL))


def _tektronix_scope():
    from scopes_tool_core.run_config import (
        ResolvedRunConfig, RunModeOptions, open_scope_for_run,
    )

    model = "tektronix-tbs2074"
    return open_scope_for_run(ResolvedRunConfig(
        mode="simulate", planning_physical_model_id=model,
        expected_physical_model_id=None, capabilities=None,
        resource=f"SIM::{model}::INSTR",
        options=RunModeOptions(simulate=True, planning_physical_model_id=model),
    ))


def test_tektronix_stream_keeps_clean_invalid_item_and_next_cycles():
    with _tektronix_scope() as scope:
        scope.query_idn()
        scope.set_channel_display(2, False)
        samples = []
        completed, invalid, reason = run_measure_stream(
            scope, _options(count=2, interval_seconds=0),
            stop_requested=lambda: False,
            wait_or_stop=lambda _seconds: False,
            sample_reporter=samples.append,
        )
    assert (completed, invalid, reason) == (2, 2, "count_reached")
    assert [sample["index"] for sample in samples] == [1, 2]
    for sample in samples:
        assert sample["values"]["frequency"]["valid"] is True
        assert sample["values"]["frequency"]["value"] is not None
        missing = sample["values"]["vpp"]
        assert missing["valid"] is False
        assert missing["value"] is None
        assert missing["reason"]


def test_tektronix_stream_true_query_failure_still_fails_closed():
    with _tektronix_scope() as scope:
        scope.query_idn()
        scope.backend.query_failures[
            "MEASUrement:IMMed:VALue?"
        ] = OscilloscopeError("measurement failed")
        samples = []
        with pytest.raises(OscilloscopeError, match="measurement failed"):
            run_measure_stream(
                scope, _options(count=2, interval_seconds=0),
                stop_requested=lambda: False,
                wait_or_stop=lambda _seconds: False,
                sample_reporter=samples.append,
            )
    assert samples == []
