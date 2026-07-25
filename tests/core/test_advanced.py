import pytest

from scopes_tool_core.advanced import (
    autoscale_commands,
    cursor_auto_vertical_plan,
    cursor_auto_timebase_plan,
    cursor_configure_commands,
    fft_configure_commands,
    fft_query_commands,
    setup_recall_command,
    setup_save_command,
    trigger_holdoff_command,
    trigger_holdoff_commands,
)
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend, SimulatorBackendError


def test_advanced_command_formatting():
    capabilities = capabilities_for_model("DSOX4024A")

    assert trigger_holdoff_command(1e-6) == ":TRIGger:HOLDoff 1e-6"
    assert trigger_holdoff_commands(1e-6) == [
        ":TRIGger:HOLDoff:RANDom OFF",
        ":TRIGger:HOLDoff 1e-6",
    ]
    assert cursor_configure_commands(
        1,
        0.0,
        1e-3,
        y1_volts=0.0,
        y2_volts=0.5,
        capabilities=capabilities,
    ) == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0",
        ":MARKer:X2Position 0.001",
        ":MARKer:Y1Position 0",
        ":MARKer:Y2Position 0.5",
    ]
    assert autoscale_commands((1, 2), capabilities=capabilities) == [
        ":AUToscale CHANnel1,CHANnel2"
    ]
    assert setup_save_command(slot=3) == ":SAVE:SETup 3"
    assert setup_recall_command(file_spec="\\usb\\setup.scp") == (
        ':RECall:SETup "\\usb\\setup.scp"'
    )


@pytest.mark.parametrize(
    ("model", "prefix"),
    [
        ("DSOX2004A", ":FUNCtion"),
        ("DSOX3024A", ":FUNCtion"),
        ("DSOX4024A", ":FUNCtion1"),
    ],
)
def test_fft_commands_use_series_appropriate_function_prefix(model, prefix):
    capabilities = capabilities_for_model(model)

    assert fft_configure_commands(
        1,
        1,
        units="decibel",
        window="hanning",
        center_hz=1000,
        span_hz=10000,
        display=True,
        capabilities=capabilities,
    ) == [
        f"{prefix}:OPERation FFT",
        f"{prefix}:SOURce1 CHANnel1",
        f"{prefix}:FFT:VTYPe DECibel",
        f"{prefix}:FFT:WINDow HANNing",
        f"{prefix}:FFT:CENTer 1000",
        f"{prefix}:FFT:SPAN 10000",
        f"{prefix}:DISPlay ON",
    ]
    assert fft_query_commands(1, capabilities=capabilities) == [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
        f"{prefix}:FFT:VTYPe?",
        f"{prefix}:FFT:WINDow?",
        f"{prefix}:FFT:CENTer?",
        f"{prefix}:FFT:SPAN?",
        f"{prefix}:DISPlay?",
    ]


def test_fft_function_validation_uses_profile_function_count():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4024A")

    with pytest.raises(ParameterValidationError, match="between 1 and 1"):
        fft_configure_commands(2, 1, capabilities=single_function)

    assert fft_configure_commands(4, 1, capabilities=four_functions)[:2] == [
        ":FUNCtion4:OPERation FFT",
        ":FUNCtion4:SOURce1 CHANnel1",
    ]


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


@pytest.mark.parametrize("seconds", [39e-9, 10.1])
def test_trigger_holdoff_rejects_out_of_range(seconds):
    with pytest.raises(ParameterValidationError):
        trigger_holdoff_command(seconds)


def test_setup_file_rejects_quotes_and_wrong_extension():
    with pytest.raises(ParameterValidationError):
        setup_save_command(file_spec='"bad.scp"')
    with pytest.raises(ParameterValidationError):
        setup_save_command(file_spec="bad.txt")


def test_simulator_advanced_state_round_trip():
    backend = SimulatorBackend()
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.set_trigger_holdoff(2e-6)
    assert scope.query_trigger_holdoff() == pytest.approx(2e-6)
    assert ":TRIGger:HOLDoff:RANDom OFF" in backend.history

    scope.configure_cursor(1, 0.0, 1e-3, y1_volts=0.1, y2_volts=0.6)
    cursor = scope.query_cursor()
    assert cursor.mode == "MANUAL"
    assert cursor.x_delta_seconds == pytest.approx(1e-3)
    assert cursor.y_delta_volts == pytest.approx(0.5)

    scope.configure_fft(1, 2, units="vrms", window="flattop", display=True)
    fft = scope.query_fft(1)
    assert fft.source_channel == 2
    assert fft.display is True


def test_simulator_rejects_unit_suffixes_for_advanced_numeric_writes():
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":TRIGger:HOLDoff 1 us")
    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":MARKer:X2Position 1 ms")
    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":MARKer:Y2Position 0.5 V")
