import pytest

from scopes_tool_core.cursor import (
    cursor_auto_vertical_plan,
    cursor_auto_timebase_plan,
)

from scopes_tool_core.errors import ParameterValidationError

from scopes_tool_core.scope import Oscilloscope

from scopes_tool_core.simulator_backend import SimulatorBackend

def test_cursor_auto_timebase_plan_keeps_visible_positions():
    result = cursor_auto_timebase_plan(1e-3, 0.0, 0.0, 1e-3)

    assert result.changed is False
    assert result.target_scale_seconds_per_division == pytest.approx(1e-3)
    assert result.commands == (":TIMebase:SCALe?", ":TIMebase:POSition?")

def test_cursor_auto_timebase_plan_widens_for_out_of_range_x2():
    result = cursor_auto_timebase_plan(1e-3, 0.0, 0.0, 0.01)

    assert result.changed is True
    assert result.target_scale_seconds_per_division == pytest.approx(0.0025)
    assert result.commands == (
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:SCALe 0.0025",
    )

def test_cursor_auto_timebase_plan_uses_current_position():
    result = cursor_auto_timebase_plan(1e-3, 0.01, 0.009, 0.011)

    assert result.changed is False
    assert result.target_scale_seconds_per_division == pytest.approx(1e-3)

def test_cursor_auto_vertical_plan_keeps_visible_positions():
    result = cursor_auto_vertical_plan(1, 1.0, 0.0, y1_volts=-1.0, y2_volts=1.0)

    assert result.changed is False
    assert result.offset_changed is False
    assert result.target_scale_volts_per_division == pytest.approx(1.0)
    assert result.target_offset_volts == pytest.approx(0.0)
    assert result.commands == (":CHANnel1:SCALe?", ":CHANnel1:OFFSet?")

def test_cursor_auto_vertical_plan_uses_scale_only_when_reasonable():
    result = cursor_auto_vertical_plan(1, 1.0, 0.0, y1_volts=0.0, y2_volts=5.0)

    assert result.changed is True
    assert result.offset_changed is False
    assert result.target_scale_volts_per_division == pytest.approx(5.0 / 3.5)
    assert result.target_offset_volts == pytest.approx(0.0)
    assert result.commands == (
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1.42857142857",
    )

def test_cursor_auto_vertical_plan_centers_common_positive_waveform_range():
    result = cursor_auto_vertical_plan(1, 0.2, 0.0, y1_volts=0.0, y2_volts=2.5)

    assert result.changed is True
    assert result.offset_changed is True
    assert result.target_scale_volts_per_division == pytest.approx(2.5 / 2.0 / 3.5)
    assert result.target_offset_volts == pytest.approx(1.25)
    assert result.commands == (
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 0.357142857143",
        ":CHANnel1:OFFSet 1.25",
    )

def test_cursor_auto_vertical_plan_moves_offset_to_avoid_coarse_scale():
    result = cursor_auto_vertical_plan(1, 1.0, 0.0, y1_volts=20.0, y2_volts=21.0)

    assert result.changed is True
    assert result.offset_changed is True
    assert result.target_scale_volts_per_division == pytest.approx(1.0)
    assert result.target_offset_volts == pytest.approx(20.5)
    assert result.commands == (
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1",
        ":CHANnel1:OFFSet 20.5",
    )

def test_cursor_auto_vertical_plan_handles_single_negative_y():
    result = cursor_auto_vertical_plan(1, 0.5, 0.0, y1_volts=-20.0)

    assert result.changed is True
    assert result.offset_changed is True
    assert result.target_scale_volts_per_division == pytest.approx(0.5)
    assert result.target_offset_volts == pytest.approx(-20.0)

@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"y1_volts": float("nan")},
        {"y2_volts": float("inf")},
    ],
)
def test_cursor_auto_vertical_plan_rejects_missing_or_nonfinite_y(kwargs):
    with pytest.raises(ParameterValidationError):
        cursor_auto_vertical_plan(1, 1.0, 0.0, **kwargs)

def test_configure_cursor_auto_timebase_sends_scale_before_cursor_commands():
    backend = SimulatorBackend(timebase_scale=1e-3, timebase_position=0.0)
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_cursor(1, 0.0, 0.01, auto_timebase=True)

    assert backend.history[1:4] == [
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:SCALe 0.0025",
    ]
    assert backend.history[4:9] == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0",
        ":MARKer:X2Position 0.01",
    ]

def test_configure_cursor_auto_vertical_sends_scale_offset_before_cursor_commands():
    backend = SimulatorBackend(channel_scale={1: 1.0}, channel_offset={1: 0.0})
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_cursor(1, 0.0, 1e-3, y1_volts=20.0, y2_volts=21.0, auto_vertical=True)

    assert backend.history[1:5] == [
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1",
        ":CHANnel1:OFFSet 20.5",
    ]
    assert backend.history[5:10] == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0",
        ":MARKer:X2Position 0.001",
    ]

def test_configure_cursor_invalid_x_fails_before_auto_timebase_or_vertical_write():
    backend = SimulatorBackend(timebase_scale=1e-3, channel_scale={1: 1.0})
    scope = Oscilloscope(backend)
    scope.query_idn()

    with pytest.raises(ParameterValidationError, match="--x1 must be a finite number"):
        scope.configure_cursor(1, float("nan"), 0.01, auto_timebase=True, auto_vertical=True, y1_volts=1.0)

    assert backend.history == ["*IDN?"]


def test_query_cursor_off_only_queries_mode():
    backend = SimulatorBackend(marker_mode="OFF")
    scope = Oscilloscope(backend)
    scope.query_idn()

    state = scope.query_cursor()

    assert state.mode == "OFF"
    assert state.x1_seconds is None
    assert state.x2_seconds is None
    assert state.y1_volts is None
    assert state.y2_volts is None
    assert state.x_delta_seconds is None
    assert state.y_delta_volts is None
    assert state.dydx is None
    assert backend.history == ["*IDN?", ":MARKer:MODE?"]


def test_query_cursor_active_3000x_omits_unsupported_dydx_query():
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox3024a",
        marker_mode="MANual",
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    state = scope.query_cursor()

    assert state.dydx is None
    assert ":MARKer:DYDX?" not in backend.history
    assert backend.history == [
        "*IDN?",
        ":MARKer:MODE?",
        ":MARKer:X1Position?",
        ":MARKer:X2Position?",
        ":MARKer:Y1Position?",
        ":MARKer:Y2Position?",
        ":MARKer:XDELTa?",
        ":MARKer:YDELTa?",
    ]


def test_query_cursor_active_4000x_includes_dydx_query():
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a",
        marker_mode="MANual",
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    state = scope.query_cursor()

    assert state.dydx == pytest.approx(500.0)
    assert backend.history[-1] == ":MARKer:DYDX?"
