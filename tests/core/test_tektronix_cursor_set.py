"""Hardware-free coverage for Tektronix cursor-set behavior."""

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id, operation_supported
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.operations import query_instrument_summary
from scopes_tool_core.tektronix import TektronixOscilloscope
from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend


TBS2074 = "tektronix-tbs2074"
LEGACY_TEK_MODELS = ("tektronix-tds2024b", "tektronix-tbs1052b")
TEK_MODELS = (TBS2074, *LEGACY_TEK_MODELS)


def simulated_scope(model_id=TBS2074):
    backend = TektronixSimulatorBackend(physical_model_id=model_id)
    if model_id == TBS2074:
        backend.tek_settings["HORIZONTAL:DELAY:MODE"] = "ON"
    scope = TektronixOscilloscope(backend)
    scope.query_idn()
    backend.history.clear()
    return scope, backend


def test_tek_profiles_declare_cursor_source_and_fixed_realtime_memory():
    tbs = capabilities_for_model_id(TBS2074)
    assert tbs.cursor_source_selection == "selected-waveform"
    assert tbs.fixed_acquisition_memory_mode == "realtime"
    assert tbs.vertical_display_divisions == 10
    assert tbs.horizontal_display_divisions == 15
    assert operation_supported(tbs, "cursor-set")

    for model_id in LEGACY_TEK_MODELS:
        capabilities = capabilities_for_model_id(model_id)
        assert capabilities.cursor_source_selection == "independent"
        assert capabilities.fixed_acquisition_memory_mode == "realtime"
        assert operation_supported(capabilities, "cursor-set")


@pytest.mark.parametrize("model_id", TEK_MODELS)
def test_tek_instrument_summary_reports_realtime_memory_and_sampling_type(model_id):
    scope, _ = simulated_scope(model_id)

    summary = query_instrument_summary(scope)

    assert summary["acquisition"] == {"mode": "realtime", "type": "normal"}


@pytest.mark.parametrize(
    ("positions", "mode", "unit_commands", "position_commands"),
    [
        (
            {"x1_seconds": 0.0005},
            "VBArs",
            ["CURSor:VBArs:UNIts SECOnds"],
            ["CURSor:VBArs:POSITION1 0.0005"],
        ),
        (
            {"y1_volts": 0.5},
            "HBArs",
            ["CURSor:HBArs:UNIts BASe"],
            ["CURSor:HBArs:POSITION1 0.5"],
        ),
        (
            {"x1_seconds": 0.0005, "y2_volts": 0.5},
            "SCREEN",
            ["CURSor:VBArs:UNIts SECOnds", "CURSor:HBArs:UNIts BASe"],
            ["CURSor:VBArs:POSITION1 0.0005", "CURSor:HBArs:POSITION2 0.5"],
        ),
    ],
)
def test_tbs2074_cursor_set_uses_only_requested_axes(
    positions, mode, unit_commands, position_commands
):
    scope, backend = simulated_scope()
    backend.tek_settings["CURSOR:MODE"] = "TRACK"

    scope.configure_cursor(1, **positions)

    assert f"CURSor:FUNCtion {mode}" in backend.history
    assert [command for command in backend.history if ":UNIts " in command] == unit_commands
    assert [
        command
        for command in backend.history
        if ":POSITION" in command and not command.endswith("?")
    ] == position_commands
    assert "CURSor:MODe INDependent" not in backend.history
    if mode == "VBArs":
        assert backend.tek_settings["CURSOR:VBARS:POSITION2"] == "0.001"
        assert not any("HBArs" in command for command in backend.history)
    elif mode == "HBArs":
        assert backend.tek_settings["CURSOR:HBARS:POSITION2"] == "1"
        assert not any("VBArs" in command for command in backend.history)


@pytest.mark.parametrize(
    ("function", "expected"),
    [
        ("off", ["CURSor:FUNCtion OFF"]),
        ("screen", ["CURSor:FUNCtion SCREEN"]),
        ("waveform", ["CURSor:FUNCtion WAVEform"]),
        ("vbars", ["CURSor:FUNCtion VBArs"]),
        ("hbars", ["CURSor:FUNCtion HBArs"]),
    ],
)
def test_tbs2074_cursor_function_switches_without_positions(function, expected):
    scope, backend = simulated_scope()

    scope.configure_cursor(function=function)

    assert backend.history == expected
    assert backend.acquisition_reset_count == 0


@pytest.mark.parametrize(
    ("function", "positions"),
    [
        ("off", {"x1_seconds": 0.0}),
        ("off", {"y1_volts": 0.0}),
        ("waveform", {"x1_seconds": 0.0}),
        ("waveform", {"y1_volts": 0.0}),
        ("vbars", {"y1_volts": 0.0}),
        ("hbars", {"x1_seconds": 0.0}),
    ],
)
def test_tbs2074_cursor_rejects_positions_before_instrument_writes(function, positions):
    scope, backend = simulated_scope()

    with pytest.raises(ParameterValidationError):
        scope.configure_cursor(1, function=function, **positions)

    assert backend.history == []
    assert backend.acquisition_reset_count == 0


def test_tbs2074_rejects_unknown_cursor_function_before_instrument_writes():
    scope, backend = simulated_scope()

    with pytest.raises(ParameterValidationError, match="Unsupported cursor function"):
        scope.configure_cursor(1, function="time")

    assert backend.history == []


def test_tbs2074_cursor_function_requires_source_channel_for_positions():
    scope, backend = simulated_scope()

    with pytest.raises(ParameterValidationError, match="source-channel"):
        scope.configure_cursor(x1_seconds=0.0)

    assert backend.history == []


@pytest.mark.parametrize("model_id", LEGACY_TEK_MODELS)
def test_legacy_tek_models_reject_explicit_cursor_function(model_id):
    scope, backend = simulated_scope(model_id)

    with pytest.raises(ParameterValidationError, match="unsupported for this model"):
        scope.configure_cursor(1, function="vbars")

    assert backend.history == []


@pytest.mark.parametrize(
    ("function", "x1", "x2", "y1", "y2"),
    [
        ("SCREEN", 0.0, 0.001, 0.0, 1.0),
        ("WAVEform", 0.0, 0.001, 0.0, 1.0),
        ("VBArs", 0.0, 0.001, None, None),
        ("HBArs", None, None, 0.0, 1.0),
    ],
)
def test_tbs2074_cursor_query_recognizes_first_generation_functions(
    function, x1, x2, y1, y2
):
    scope, backend = simulated_scope()
    backend.tek_settings["CURSOR:FUNCTION"] = function

    state = scope.query_cursor()

    assert state.mode == function
    assert state.x1_seconds == x1
    assert state.x2_seconds == x2
    assert state.y1_volts == y1
    assert state.y2_volts == y2


@pytest.mark.parametrize("function", ["TIME", "AMPLitude"])
def test_tbs2074_cursor_query_rejects_b_series_functions(function):
    scope, backend = simulated_scope()
    backend.tek_settings["CURSOR:FUNCTION"] = function

    with pytest.raises(OscilloscopeError, match="cursor function"):
        scope.query_cursor()


def test_tbs2074_cursor_off_state_projects_no_positions():
    scope, backend = simulated_scope()
    backend.tek_settings["CURSOR:FUNCTION"] = "OFF"
    backend.history.clear()

    state = scope.query_cursor()

    assert state.mode == "OFF"
    assert all(
        getattr(state, name) is None
        for name in ("x1_seconds", "x2_seconds", "y1_volts", "y2_volts",
                     "x_delta_seconds", "y_delta_volts", "dydx")
    )
    assert backend.history == ["CURSor:FUNCtion?"]


def test_tbs2074_skips_select_control_when_source_is_already_displayed():
    scope, backend = simulated_scope()
    backend.tek_settings["SELECT:CONTROL"] = "CH2"
    backend.channel_display[2] = True

    scope.configure_cursor(2, x1_seconds=0.0)

    assert "SELect:CONTROl CH2" not in backend.history


@pytest.mark.parametrize(("action", "expected_state"), [("run", "running"), ("stop", "stopped")])
def test_tbs2074_source_selection_preserves_acquisition_run_state(action, expected_state):
    scope, backend = simulated_scope()
    getattr(scope, action)()
    reset_count = backend.acquisition_reset_count
    backend.history.clear()

    scope.configure_cursor(2, x1_seconds=0.0)

    assert "SELect:CONTROl CH2" in backend.history
    assert backend.acquisition_reset_count == reset_count + 1
    assert backend.run_state == expected_state
    assert backend.tek_settings["SELECT:CONTROL"] == "CH2"
    assert backend.channel_display[2] is True


@pytest.mark.parametrize("x_position", [-0.0075, 0.0075])
def test_tbs2074_accepts_visible_x_cursor_edges(x_position):
    scope, backend = simulated_scope()
    backend.timebase_scale = 0.001

    scope.configure_cursor(1, x1_seconds=x_position)

    assert float(backend.tek_settings["CURSOR:VBARS:POSITION1"]) == pytest.approx(x_position)


def test_tbs2074_rejects_x_outside_visible_graticule_before_source_selection():
    scope, backend = simulated_scope()
    backend.timebase_scale = 0.001

    with pytest.raises(ParameterValidationError, match="outside the graticule"):
        scope.configure_cursor(2, x1_seconds=0.0075001)

    assert "SELect:CONTROl CH2" not in backend.history
    assert backend.acquisition_reset_count == 0


def test_tbs2074_checks_y_using_offset_scale_and_channel_position():
    scope, backend = simulated_scope()
    backend.channel_scale[2] = 2.0
    backend.channel_offset[2] = 0.5
    backend.tek_settings["CH2:POSITION"] = "0.25"

    scope.configure_cursor(2, y1_volts=10.0)

    assert float(backend.tek_settings["CURSOR:HBARS:POSITION1"]) == pytest.approx(10.0)

    backend.history.clear()
    with pytest.raises(ParameterValidationError, match="outside the graticule"):
        scope.configure_cursor(2, y1_volts=10.0001)
    assert "CURSor:FUNCtion AMPLitude" not in backend.history


def test_tbs2074_rejects_current_units_before_source_selection():
    scope, backend = simulated_scope()
    backend.channel_units[2] = "amp"

    with pytest.raises(ParameterValidationError, match="volt units"):
        scope.configure_cursor(2, y1_volts=0.0)

    assert "SELect:CONTROl CH2" not in backend.history


@pytest.mark.parametrize(("channel", "units"), [(3, "volt"), (3, "amp"), (4, "volt"), (4, "amp")])
def test_tbs2074_upper_channel_cursor_uses_yunit_without_transfer_source(channel, units):
    scope, backend = simulated_scope()
    backend.channel_units[channel] = units

    if units == "volt":
        scope.configure_cursor(channel, y1_volts=0.0)
    else:
        with pytest.raises(ParameterValidationError, match="volt units"):
            scope.configure_cursor(channel, y1_volts=0.0)

    assert f"CH{channel}:YUNit?" in backend.history
    assert "WFMOutpre:YUNit?" not in backend.history
    assert not any(command.startswith("DATa:SOUrce ") for command in backend.history)
    assert backend.waveform_source == 1


def test_tbs2074_cursor_auto_timebase_uses_fifteen_divisions():
    scope, _ = simulated_scope()

    plan = scope.plan_cursor_auto_timebase(x1_seconds=0.01)

    assert plan.target_scale_seconds_per_division == pytest.approx(0.01 / 6)


@pytest.mark.parametrize("model_id", LEGACY_TEK_MODELS)
def test_legacy_tek_models_keep_independent_single_axis_cursor_set(model_id):
    scope, backend = simulated_scope(model_id)

    scope.configure_cursor(1, x1_seconds=0.0)

    assert "CURSor:SELect:SOUrce CH1" in backend.history
    assert "CURSor:FUNCtion VBArs" in backend.history
    assert not any(command.startswith("SELect:CONTROl ") for command in backend.history)
    backend.history.clear()
    with pytest.raises(ParameterValidationError):
        scope.configure_cursor(1, x1_seconds=0.0, y1_volts=0.0)
    assert backend.history == []
