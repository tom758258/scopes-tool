import pytest

from dataclasses import replace

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import MeasurementResponseError, ParameterValidationError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.measurements import (
    INVALID_MEASUREMENT_REASON,
    MeasurementController,
    measurement_install_command,
    measurement_query,
    measurement_statistics_max_count_command,
    measurement_unit,
    normalize_measurement_item,
    pair_measurement_query,
    parse_measurement_results_dump,
    parse_measurement_result,
    parse_statistics_mode,
    parse_statistics_results,
    statistics_mode_scpi,
    validate_statistics_max_count,
    validate_statistics_items,
)
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


def test_measurement_query_uses_keysight_measure_syntax():
    assert measurement_query("vpp", 1) == ":MEASure:VPP? CHANnel1"
    assert measurement_query("frequency", 2) == ":MEASure:FREQuency? CHANnel2"
    assert measurement_query("freq", 2) == ":MEASure:FREQuency? CHANnel2"
    assert measurement_query("period", 1) == ":MEASure:PERiod? CHANnel1"
    assert measurement_query("vavg", 1) == ":MEASure:VAVerage? DISPlay,CHANnel1"
    assert measurement_query("vrms", 1) == ":MEASure:VRMS? DISPlay,DC,CHANnel1"
    assert measurement_query("ac_rms", 1) == ":MEASure:VRMS? DISPlay,AC,CHANnel1"
    assert measurement_query("minimum", 1) == ":MEASure:VMIN? CHANnel1"
    assert measurement_query("maximum", 1) == ":MEASure:VMAX? CHANnel1"
    assert measurement_query("x_at_max", 1) == ":MEASure:XMAX? CHANnel1"
    assert measurement_query("x_at_min", 1) == ":MEASure:XMIN? CHANnel1"
    assert measurement_query("rise_time", 1) == ":MEASure:RISetime? CHANnel1"
    assert measurement_query("fall_time", 1) == ":MEASure:FALLtime? CHANnel1"
    assert measurement_query("amplitude", 1) == ":MEASure:VAMPlitude? CHANnel1"
    assert measurement_query("top", 1) == ":MEASure:VTOP? CHANnel1"
    assert measurement_query("base", 1) == ":MEASure:VBASe? CHANnel1"
    assert measurement_query("overshoot", 1) == ":MEASure:OVERshoot? CHANnel1"
    assert measurement_query("preshoot", 1) == ":MEASure:PREShoot? CHANnel1"
    assert measurement_query("positive_width", 1) == ":MEASure:PWIDth? CHANnel1"
    assert measurement_query("negative_width", 1) == ":MEASure:NWIDth? CHANnel1"
    assert measurement_query("duty_cycle", 1) == ":MEASure:DUTYcycle? CHANnel1"
    assert measurement_query("negative_duty_cycle", 1) == ":MEASure:NDUTy? CHANnel1"
    assert measurement_query("area", 1) == ":MEASure:AREA? CHANnel1"
    assert measurement_query("positive_edges", 1) == ":MEASure:PEDGes? CHANnel1"
    assert measurement_query("negative_edges", 1) == ":MEASure:NEDGes? CHANnel1"
    assert measurement_query("positive_pulses", 1) == ":MEASure:PPULses? CHANnel1"
    assert measurement_query("negative_pulses", 1) == ":MEASure:NPULses? CHANnel1"
    assert measurement_query("acrms", 1) == ":MEASure:VRMS? DISPlay,AC,CHANnel1"
    assert measurement_query("vrms_ac", 1) == ":MEASure:VRMS? DISPlay,AC,CHANnel1"
    assert measurement_query("vmin", 1) == ":MEASure:VMIN? CHANnel1"
    assert measurement_query("vmax", 1) == ":MEASure:VMAX? CHANnel1"
    assert measurement_query("xmax", 1) == ":MEASure:XMAX? CHANnel1"
    assert measurement_query("x-at-max", 1) == ":MEASure:XMAX? CHANnel1"
    assert measurement_query("xmin", 1) == ":MEASure:XMIN? CHANnel1"
    assert measurement_query("x-at-min", 1) == ":MEASure:XMIN? CHANnel1"
    assert measurement_query("risetime", 1) == ":MEASure:RISetime? CHANnel1"
    assert measurement_query("falltime", 1) == ":MEASure:FALLtime? CHANnel1"
    assert measurement_query("vamp", 1) == ":MEASure:VAMPlitude? CHANnel1"
    assert measurement_query("vtop", 1) == ":MEASure:VTOP? CHANnel1"
    assert measurement_query("vbase", 1) == ":MEASure:VBASe? CHANnel1"
    assert measurement_query("pwidth", 1) == ":MEASure:PWIDth? CHANnel1"
    assert measurement_query("positive-width", 1) == ":MEASure:PWIDth? CHANnel1"
    assert measurement_query("pwid", 1) == ":MEASure:PWIDth? CHANnel1"
    assert measurement_query("nwidth", 1) == ":MEASure:NWIDth? CHANnel1"
    assert measurement_query("negative-width", 1) == ":MEASure:NWIDth? CHANnel1"
    assert measurement_query("nwid", 1) == ":MEASure:NWIDth? CHANnel1"
    assert measurement_query("duty", 1) == ":MEASure:DUTYcycle? CHANnel1"
    assert measurement_query("dutycycle", 1) == ":MEASure:DUTYcycle? CHANnel1"
    assert measurement_query("duty-cycle", 1) == ":MEASure:DUTYcycle? CHANnel1"
    assert measurement_query("nduty", 1) == ":MEASure:NDUTy? CHANnel1"
    assert measurement_query("negative-duty", 1) == ":MEASure:NDUTy? CHANnel1"
    assert measurement_query("negative-duty-cycle", 1) == ":MEASure:NDUTy? CHANnel1"
    assert measurement_query("pedges", 1) == ":MEASure:PEDGes? CHANnel1"
    assert measurement_query("positive-edges", 1) == ":MEASure:PEDGes? CHANnel1"
    assert measurement_query("nedges", 1) == ":MEASure:NEDGes? CHANnel1"
    assert measurement_query("negative-edges", 1) == ":MEASure:NEDGes? CHANnel1"
    assert measurement_query("ppulses", 1) == ":MEASure:PPULses? CHANnel1"
    assert measurement_query("positive-pulses", 1) == ":MEASure:PPULses? CHANnel1"
    assert measurement_query("npulses", 1) == ":MEASure:NPULses? CHANnel1"
    assert measurement_query("negative-pulses", 1) == ":MEASure:NPULses? CHANnel1"
    assert (
        measurement_query(
            "time_at_edge",
            1,
            slope="positive",
            occurrence=1,
        )
        == ":MEASure:TEDGe? +1,CHANnel1"
    )
    assert (
        measurement_query(
            "time-at-value",
            1,
            level=0.5,
            slope="negative",
            occurrence=2,
        )
        == ":MEASure:TVALue? 0.5,-2,CHANnel1"
    )


def test_pair_measurement_query_uses_keysight_measure_syntax():
    assert (
        pair_measurement_query("phase", 1, 2)
        == ":MEASure:PHASe? CHANnel1,CHANnel2"
    )
    assert (
        pair_measurement_query("delay", 1, 2, capabilities=capabilities_for_model("DSOX4024A"))
        == ":MEASure:DELay? AUTO,CHANnel1,CHANnel2"
    )


def test_delay_pair_measurement_uses_capability_flag_instead_of_series():
    disabled_4000x = replace(
        capabilities_for_model("DSOX4024A"),
        supports_delay_measurement=False,
    )
    enabled_3000x = replace(
        capabilities_for_model("DSOX3024A"),
        supports_delay_measurement=True,
    )

    with pytest.raises(ParameterValidationError, match="capability profile"):
        pair_measurement_query("delay", 1, 2, capabilities=disabled_4000x)
    assert (
        pair_measurement_query("delay", 1, 2, capabilities=enabled_3000x)
        == ":MEASure:DELay? AUTO,CHANnel1,CHANnel2"
    )


def test_measurement_item_normalization_accepts_aliases():
    assert normalize_measurement_item("freq") == "frequency"
    assert normalize_measurement_item("acrms") == "ac_rms"
    assert normalize_measurement_item("vrms_ac") == "ac_rms"
    assert normalize_measurement_item("min") == "minimum"
    assert normalize_measurement_item("vmin") == "minimum"
    assert normalize_measurement_item("max") == "maximum"
    assert normalize_measurement_item("vmax") == "maximum"
    assert normalize_measurement_item("xmax") == "x_at_max"
    assert normalize_measurement_item("x-at-max") == "x_at_max"
    assert normalize_measurement_item("xmin") == "x_at_min"
    assert normalize_measurement_item("x-at-min") == "x_at_min"
    assert normalize_measurement_item("risetime") == "rise_time"
    assert normalize_measurement_item("rise-time") == "rise_time"
    assert normalize_measurement_item("falltime") == "fall_time"
    assert normalize_measurement_item("fall-time") == "fall_time"
    assert normalize_measurement_item("vamp") == "amplitude"
    assert normalize_measurement_item("vtop") == "top"
    assert normalize_measurement_item("vbase") == "base"
    assert normalize_measurement_item("pwidth") == "positive_width"
    assert normalize_measurement_item("positive-width") == "positive_width"
    assert normalize_measurement_item("pwid") == "positive_width"
    assert normalize_measurement_item("nwidth") == "negative_width"
    assert normalize_measurement_item("negative-width") == "negative_width"
    assert normalize_measurement_item("nwid") == "negative_width"
    assert normalize_measurement_item("duty") == "duty_cycle"
    assert normalize_measurement_item("dutycycle") == "duty_cycle"
    assert normalize_measurement_item("duty-cycle") == "duty_cycle"
    assert normalize_measurement_item("nduty") == "negative_duty_cycle"
    assert normalize_measurement_item("negative-duty") == "negative_duty_cycle"
    assert normalize_measurement_item("negative-duty-cycle") == "negative_duty_cycle"
    assert normalize_measurement_item("pedges") == "positive_edges"
    assert normalize_measurement_item("positive-edges") == "positive_edges"
    assert normalize_measurement_item("nedges") == "negative_edges"
    assert normalize_measurement_item("negative-edges") == "negative_edges"
    assert normalize_measurement_item("ppulses") == "positive_pulses"
    assert normalize_measurement_item("positive-pulses") == "positive_pulses"
    assert normalize_measurement_item("npulses") == "negative_pulses"
    assert normalize_measurement_item("negative-pulses") == "negative_pulses"
    assert normalize_measurement_item("yatx") == "y_at_x"
    assert normalize_measurement_item("y-at-x") == "y_at_x"
    assert normalize_measurement_item("vtime") == "y_at_x"
    assert normalize_measurement_item("y_at_time") == "y_at_x"
    assert normalize_measurement_item("y-at-time") == "y_at_x"
    assert normalize_measurement_item("tedge") == "time_at_edge"
    assert normalize_measurement_item("time-at-edge") == "time_at_edge"
    assert normalize_measurement_item("tvalue") == "time_at_value"
    assert normalize_measurement_item("time-at-value") == "time_at_value"
    assert normalize_measurement_item("time_at_level") == "time_at_value"
    assert normalize_measurement_item("time-at-level") == "time_at_value"
    assert normalize_measurement_item("phase") == "phase"
    assert normalize_measurement_item("delay") == "delay"
    assert measurement_unit("frequency") == "Hz"
    assert measurement_unit("period") == "s"
    assert measurement_unit("vpp") == "V"
    assert measurement_unit("vavg") == "V"
    assert measurement_unit("vrms") == "V"
    assert measurement_unit("ac_rms") == "V"
    assert measurement_unit("minimum") == "V"
    assert measurement_unit("maximum") == "V"
    assert measurement_unit("x_at_max") == "s"
    assert measurement_unit("x_at_min") == "s"
    assert measurement_unit("rise_time") == "s"
    assert measurement_unit("fall_time") == "s"
    assert measurement_unit("amplitude") == "V"
    assert measurement_unit("top") == "V"
    assert measurement_unit("base") == "V"
    assert measurement_unit("overshoot") == "%"
    assert measurement_unit("preshoot") == "%"
    assert measurement_unit("positive_width") == "s"
    assert measurement_unit("negative_width") == "s"
    assert measurement_unit("duty_cycle") == "%"
    assert measurement_unit("negative_duty_cycle") == "%"
    assert measurement_unit("area") == "V*s"
    assert measurement_unit("positive_edges") == "count"
    assert measurement_unit("negative_edges") == "count"
    assert measurement_unit("positive_pulses") == "count"
    assert measurement_unit("negative_pulses") == "count"
    assert measurement_unit("y_at_x") == "V"
    assert measurement_unit("time_at_edge") == "s"
    assert measurement_unit("time_at_value") == "s"
    assert measurement_unit("phase") == "deg"
    assert measurement_unit("delay") == "s"


def test_measurement_item_normalization_rejects_unknown_item():
    with pytest.raises(ParameterValidationError):
        normalize_measurement_item("ratio")


def test_parse_measurement_result_keeps_valid_numeric_value():
    result = parse_measurement_result("5.0E-1", item="vpp", channel=1)

    assert result.valid is True
    assert result.value == 0.5
    assert result.raw_value == "5.0E-1"
    assert result.reason is None
    assert result.unit == "V"


def test_parse_pair_measurement_result_preserves_reference_channel():
    result = parse_measurement_result(
        "9.0E+1",
        item="phase",
        channel=1,
        reference_channel=2,
    )

    assert result.valid is True
    assert result.value == 90.0
    assert result.raw_value == "9.0E+1"
    assert result.unit == "deg"
    assert result.channel == 1
    assert result.reference_channel == 2


@pytest.mark.parametrize("raw", ["9.9E+37", "9.900000E+37", "-9.9E+37"])
def test_parse_measurement_result_marks_invalid_sentinel_without_losing_raw(raw):
    result = parse_measurement_result(raw, item="frequency", channel=1)

    assert result.valid is False
    assert result.value is None
    assert result.raw_value == raw
    assert result.reason == INVALID_MEASUREMENT_REASON
    assert result.unit == "Hz"


@pytest.mark.parametrize(
    ("item", "unit"),
    [
        ("overshoot", "%"),
        ("positive_width", "s"),
        ("area", "V*s"),
        ("x_at_max", "s"),
        ("positive_edges", "count"),
    ],
)
def test_parse_measurement_result_preserves_invalid_sentinel_for_new_units(item, unit):
    result = parse_measurement_result("9.9E+37", item=item, channel=1)

    assert result.valid is False
    assert result.value is None
    assert result.raw_value == "9.9E+37"
    assert result.reason == INVALID_MEASUREMENT_REASON
    assert result.unit == unit


@pytest.mark.parametrize("raw", ["not-a-number", "NaN", "INF"])
def test_parse_measurement_result_rejects_unparseable_response(raw):
    with pytest.raises(MeasurementResponseError):
        parse_measurement_result(raw, item="vpp", channel=1)


def test_statistics_helpers_reject_parameterized_or_pair_items():
    with pytest.raises(ParameterValidationError):
        validate_statistics_items(("vpp", "y_at_x"))
    with pytest.raises(ParameterValidationError):
        validate_statistics_items(("phase",))


def test_measurement_install_command_uses_measure_command_without_query_suffix():
    assert measurement_install_command("frequency") == ":MEASure:FREQuency"
    assert measurement_install_command("vrms") == ":MEASure:VRMS"
    assert measurement_install_command("ac_rms") == ":MEASure:VRMS DISPlay,AC"
    with pytest.raises(ParameterValidationError, match="area measurement is not supported"):
        measurement_install_command(
            "area", capabilities=capabilities_for_model("DSOX2004A")
        )


def test_measurement_controller_installs_supported_item_and_rejects_pair_item():
    backend = FakeBackend()
    controller = MeasurementController(
        SCPIClient(backend), capabilities_for_model("DSOX4024A")
    )

    controller.install(1, "frequency")

    assert backend.history == [
        ":MEASure:SOURce CHANnel1",
        ":MEASure:FREQuency",
    ]
    with pytest.raises(ParameterValidationError, match="cannot be installed"):
        controller.install(1, "phase")
    assert backend.history == [
        ":MEASure:SOURce CHANnel1",
        ":MEASure:FREQuency",
    ]


def test_statistics_all_mode_uses_keysight_on_keyword():
    assert statistics_mode_scpi("all") == "ON"


@pytest.mark.parametrize(
    ("raw", "expected"),
    (("STDD", "stddev"), ("COUN", "count")),
)
def test_parse_statistics_mode_accepts_canonical_keysight_readback(raw, expected):
    assert parse_statistics_mode(raw) == expected


def test_parse_statistics_results_with_item_labels():
    result = parse_statistics_results(
        "vpp,5.0E-1,4.9E-1,5.1E-1,5.0E-1,2.5E-3,16",
        channel=1,
        items=("vpp",),
        mode="all",
    )

    assert result.channel == 1
    assert result.records[0].item == "vpp"
    assert result.records[0].current == pytest.approx(0.5)
    assert result.records[0].count == 16


def test_parse_statistics_results_accepts_keysight_front_panel_labels():
    result = parse_statistics_results(
        (
            "Pk-Pk(1),9.9E+37,9.9E+37,9.9E+37,9.9E+37,9.9E+37,0,"
            "Frequency(1),1.0E+3,9.9E+37,9.9E+37,9.9E+37,9.9E+37,1"
        ),
        channel=1,
        items=("vpp", "frequency"),
        mode="all",
    )

    assert result.records[0].item == "vpp"
    assert result.records[0].current is None
    assert result.records[0].count == 0
    assert result.records[1].item == "frequency"
    assert result.records[1].current == pytest.approx(1000.0)
    assert result.records[1].minimum is None
    assert result.records[1].count == 1


def test_parse_statistics_results_maps_stddev_values_by_requested_order():
    result = parse_statistics_results(
        "1.2E-3,4.5E+1",
        channel=1,
        items=("vpp", "frequency"),
        mode="stddev",
    )

    assert [record.item for record in result.records] == ["vpp", "frequency"]
    assert [record.stddev for record in result.records] == pytest.approx([0.0012, 45.0])
    for record in result.records:
        assert record.current is None
        assert record.minimum is None
        assert record.maximum is None
        assert record.mean is None
        assert record.count is None
    assert [record.raw_values for record in result.records] == [
        ("1.2E-3",),
        ("4.5E+1",),
    ]


def test_parse_statistics_results_count_preserves_integer_and_sentinel_conventions():
    result = parse_statistics_results(
        "12,9.9E+37",
        channel=1,
        items=("vpp", "frequency"),
        mode="count",
    )

    assert [record.count for record in result.records] == [12, None]


def test_parse_statistics_results_rejects_non_all_value_count_mismatch():
    with pytest.raises(MeasurementResponseError):
        parse_statistics_results(
            "1.2E-3",
            channel=1,
            items=("vpp", "frequency"),
            mode="stddev",
        )


def test_measurement_statistics_parses_simulator_non_all_response():
    scope = Oscilloscope(
        SimulatorBackend(physical_model_id="keysight-dsox4024a")
    )
    scope.query_idn()

    result = scope.query_measurement_statistics(
        1,
        ("vpp", "frequency"),
        mode="stddev",
    )

    assert [record.item for record in result.records] == ["vpp", "frequency"]
    assert all(record.stddev is not None for record in result.records)
    assert all(len(record.raw_values) == 1 for record in result.records)
    assert all(record.current is None for record in result.records)


def test_measurement_statistics_uses_generalized_install_command():
    backend = FakeBackend(
        responses={
            ":MEASure:RESults?": "frequency,1.0,0.9,1.1,1.0,0.01,10",
        }
    )
    controller = MeasurementController(
        SCPIClient(backend), capabilities_for_model("DSOX4024A")
    )

    controller.statistics(1, ("frequency",))

    assert backend.history[:3] == [
        ":MEASure:CLEar",
        ":MEASure:SOURce CHANnel1",
        measurement_install_command("frequency"),
    ]


def test_measurement_controller_queries_vpp_for_channel():
    backend = FakeBackend(responses={":MEASure:VPP? CHANnel1": "1.25E+0"})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    result = controller.query(1, "vpp")

    assert result.valid is True
    assert result.value == 1.25
    assert backend.history == [":MEASure:VPP? CHANnel1"]


@pytest.mark.parametrize("model", ["DSOX3024A", "DSOX4024A"])
def test_measurement_controller_queries_displayed_results_on_supported_series(model):
    command = ":MEASure:RESults?"
    backend = FakeBackend(responses={command: "Frequency,1.000000E+06"})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model(model))

    controller.query_results()

    assert backend.history == [command]


def test_measurement_controller_rejects_displayed_results_on_2000x():
    backend = FakeBackend()
    controller = MeasurementController(
        SCPIClient(backend), capabilities_for_model("DSOX2004A")
    )

    with pytest.raises(ParameterValidationError, match="2000X"):
        controller.query_results()

    assert backend.history == []


def test_parse_measurement_results_dump_accepts_empty_response():
    result = parse_measurement_results_dump("")

    assert result.raw == ""
    assert result.items == ()
    assert result.statistics_items == ()


def test_parse_measurement_results_dump_accepts_simple_label_value_pairs():
    raw = "Frequency,1.000000E+06,Vpp,3.280000E+00"

    result = parse_measurement_results_dump(raw)

    assert result.raw == raw
    assert [(item.label, item.value) for item in result.items] == [
        ("Frequency", 1000000.0),
        ("Vpp", 3.28),
    ]
    assert result.statistics_items == ()


def test_parse_measurement_results_dump_accepts_statistics_layout():
    raw = (
        "Period(1),1.0E-06,9.0E-07,1.1E-06,1.0E-06,5.0E-08,42,"
        "Amplitude(2),+2.48E+00,+2.40E+00,+2.50E+00,"
        "+2.48000000000000E+00,+0.0E+00,386"
    )

    result = parse_measurement_results_dump(raw)

    assert result.raw == raw
    assert result.items == ()
    assert [
        (
            item.label,
            item.current,
            item.minimum,
            item.maximum,
            item.mean,
            item.stddev,
            item.count,
        )
        for item in result.statistics_items
    ] == [
        ("Period(1)", 1e-06, 9e-07, 1.1e-06, 1e-06, 5e-08, 42),
        ("Amplitude(2)", 2.48, 2.4, 2.5, 2.48, 0.0, 386),
    ]


def test_parse_measurement_results_dump_accepts_live_invalid_sentinel():
    raw = (
        "Period(1),9.9E+37,9.9E+37,9.9E+37,9.9E+37,9.9E+37,0,"
        "Frequency(1),9.9E+37,9.9E+37,9.9E+37,9.9E+37,9.9E+37,0"
    )

    result = parse_measurement_results_dump(raw)

    assert result.raw == raw
    assert result.items == ()
    assert len(result.statistics_items) == 2
    assert result.statistics_items[0].current is None
    assert result.statistics_items[1].count == 0


def test_advanced_statistics_state_and_actions_use_documented_scpi_family():
    responses = {
        ":MEASure:STATistics?": "ON",
        ":MEASure:STATistics:DISPlay?": "1",
        ":MEASure:STATistics:MCOUnt?": "INFinite",
        ":MEASure:STATistics:RSDeviation?": "0",
    }
    backend = FakeBackend(responses=responses)
    controller = MeasurementController(
        SCPIClient(backend), capabilities_for_model("DSOX4024A")
    )

    state = controller.query_statistics_state()
    controller.set_statistics_mode("mean")
    controller.set_statistics_display(False)
    controller.set_statistics_max_count(2000)
    controller.set_statistics_max_count(None)
    controller.set_statistics_relative_stddev(True)
    controller.reset_statistics()
    controller.increment_statistics()

    assert state.mode == "all"
    assert state.display_enabled is True
    assert state.max_count is None
    assert state.relative_stddev_enabled is False
    assert backend.history == [
        ":MEASure:STATistics?",
        ":MEASure:STATistics:DISPlay?",
        ":MEASure:STATistics:MCOUnt?",
        ":MEASure:STATistics:RSDeviation?",
        ":MEASure:STATistics MEAN",
        ":MEASure:STATistics:DISPlay OFF",
        ":MEASure:STATistics:MCOUnt 2000",
        ":MEASure:STATistics:MCOUnt INFinite",
        ":MEASure:STATistics:RSDeviation ON",
        ":MEASure:STATistics:RESet",
        ":MEASure:STATistics:INCRement",
    ]


def test_statistics_max_count_accepts_numeric_and_infinite_and_rejects_boundaries():
    assert validate_statistics_max_count(2) == 2
    assert measurement_statistics_max_count_command(None) == (
        ":MEASure:STATistics:MCOUnt INFinite"
    )
    with pytest.raises(ParameterValidationError, match="between 2 and 2000"):
        validate_statistics_max_count(1)
    with pytest.raises(ParameterValidationError, match="between 2 and 2000"):
        validate_statistics_max_count(2001)


def test_parse_measurement_results_dump_preserves_malformed_statistics_layout():
    raw = "Period(1),1.0E-06,9.0E-07,not-a-number,1.0E-06,5.0E-08,42"

    result = parse_measurement_results_dump(raw)

    assert result.raw == raw
    assert result.items == ()
    assert result.statistics_items == ()


def test_measurement_controller_rejects_unsupported_single_query_before_scpi():
    backend = FakeBackend()
    capabilities = replace(capabilities_for_model("DSOX4024A"), supports_measurements=False)
    controller = MeasurementController(SCPIClient(backend), capabilities)

    with pytest.raises(ParameterValidationError, match="measurements are not supported"):
        controller.query(1, "vpp")

    assert not any(command.startswith(":MEASure:") for command in backend.history)


def test_measurement_controller_rejects_unsupported_pair_query_before_scpi():
    backend = FakeBackend()
    capabilities = replace(capabilities_for_model("DSOX4024A"), supports_measurements=False)
    controller = MeasurementController(SCPIClient(backend), capabilities)

    with pytest.raises(ParameterValidationError, match="measurements are not supported"):
        controller.query_pair(1, 2, "phase")

    assert not any(command.startswith(":MEASure:") for command in backend.history)


def test_measurement_controller_rejects_unsupported_statistics_before_scpi():
    backend = FakeBackend()
    capabilities = replace(capabilities_for_model("DSOX4024A"), supports_measurements=False)
    controller = MeasurementController(SCPIClient(backend), capabilities)

    with pytest.raises(ParameterValidationError, match="measurements are not supported"):
        controller.statistics(1, ("vpp",))

    assert not any(command.startswith(":MEASure:") for command in backend.history)


@pytest.mark.parametrize(
    ("model", "expected_command"),
    [
        ("DSOX2004A", ":MEASure:PHASe? CHANnel1,CHANnel2"),
        ("DSOX3024A", ":MEASure:PHASe? CHANnel1,CHANnel2"),
        ("DSOX4024A", ":MEASure:PHASe? CHANnel1,CHANnel2"),
    ],
)
def test_measurement_controller_queries_phase_pair(model, expected_command):
    backend = FakeBackend(responses={expected_command: "9.0E+1"})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model(model))

    result = controller.query_pair(1, 2, "phase")

    assert result.valid is True
    assert result.value == 90.0
    assert result.unit == "deg"
    assert result.channel == 1
    assert result.reference_channel == 2
    assert backend.history == [expected_command]


def test_measurement_controller_queries_delay_pair_on_4000x():
    command = ":MEASure:DELay? AUTO,CHANnel1,CHANnel2"
    backend = FakeBackend(responses={command: "1.25E-6"})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    result = controller.query_pair(1, 2, "delay")

    assert result.valid is True
    assert result.value == 1.25e-6
    assert result.unit == "s"
    assert result.channel == 1
    assert result.reference_channel == 2
    assert backend.history == [command]


def test_measurement_controller_preserves_pair_invalid_sentinel():
    command = ":MEASure:PHASe? CHANnel1,CHANnel2"
    backend = FakeBackend(responses={command: "9.9E+37"})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    result = controller.query_pair(1, 2, "phase")

    assert result.valid is False
    assert result.value is None
    assert result.raw_value == "9.9E+37"
    assert result.reason == INVALID_MEASUREMENT_REASON
    assert result.unit == "deg"
    assert result.channel == 1
    assert result.reference_channel == 2
    assert backend.history == [command]


@pytest.mark.parametrize("model", ["DSOX2004A", "DSOX3024A"])
def test_measurement_controller_rejects_delay_pair_before_scpi_when_unsupported(model):
    backend = FakeBackend()
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model(model))

    with pytest.raises(ParameterValidationError) as excinfo:
        controller.query_pair(1, 2, "delay")

    assert "capability profile" in str(excinfo.value)
    assert backend.history == []


@pytest.mark.parametrize(
    ("source_channel", "reference_channel", "message"),
    [
        (1, 1, "different"),
        (5, 1, "channel 5 is not available"),
        (1, 5, "channel 5 is not available"),
    ],
)
def test_measurement_controller_rejects_invalid_pair_channels_before_scpi(
    source_channel, reference_channel, message
):
    backend = FakeBackend()
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    with pytest.raises(ParameterValidationError) as excinfo:
        controller.query_pair(source_channel, reference_channel, "phase")

    assert message in str(excinfo.value)
    assert backend.history == []


@pytest.mark.parametrize(
    ("item", "source_channel", "reference_channel", "kwargs", "message"),
    [
        ("phase", 1, 2, {"time_s": 0.0}, "--time"),
        ("phase", 1, 2, {"level": 0.5}, "--level"),
        ("phase", 1, 2, {"slope": "positive"}, "--slope"),
        ("phase", 1, 2, {"occurrence": 1}, "--occurrence"),
        ("vpp", 1, 2, {}, "single channel"),
        ("phase", 1, 1, {}, "different"),
        ("delay", 1, 2, {}, "known scope capabilities"),
        (
            "delay",
            1,
            2,
            {"capabilities": capabilities_for_model("DSOX3024A")},
            "capability profile",
        ),
    ],
)
def test_pair_measurement_query_rejects_invalid_pair_args(
    item, source_channel, reference_channel, kwargs, message
):
    with pytest.raises(ParameterValidationError) as excinfo:
        pair_measurement_query(item, source_channel, reference_channel, **kwargs)

    assert message in str(excinfo.value)


@pytest.mark.parametrize(
    ("model", "expected_command"),
    [
        ("DSOX2004A", ":MEASure:VTIMe? 0,CHANnel1"),
        ("DSOX3024A", ":MEASure:VTIMe? 0,CHANnel1"),
        ("DSOX4024A", ":MEASure:VTIMe? 0,CHANnel1"),
    ],
)
def test_measurement_controller_queries_y_at_x_with_legacy_query(model, expected_command):
    backend = FakeBackend(responses={expected_command: "2.50E-1"})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model(model))

    result = controller.query(1, "y_at_x", time_s=0.0)

    assert result.valid is True
    assert result.value == 0.25
    assert result.unit == "V"
    assert backend.history == [expected_command]


@pytest.mark.parametrize(
    ("item", "kwargs", "expected_command", "expected_value"),
    [
        (
            "time_at_edge",
            {"slope": "positive", "occurrence": 2},
            ":MEASure:TEDGe? +2,CHANnel1",
            1.25e-6,
        ),
        (
            "time_at_edge",
            {"slope": "negative", "occurrence": 1},
            ":MEASure:TEDGe? -1,CHANnel1",
            2.5e-6,
        ),
        (
            "time_at_value",
            {"level": 0.5, "slope": "positive", "occurrence": 1},
            ":MEASure:TVALue? 0.5,+1,CHANnel1",
            3.75e-6,
        ),
    ],
)
def test_measurement_controller_queries_parameterized_time_items(
    item, kwargs, expected_command, expected_value
):
    backend = FakeBackend(responses={expected_command: f"{expected_value:.2E}"})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    result = controller.query(1, item, **kwargs)

    assert result.valid is True
    assert result.value == expected_value
    assert result.unit == "s"
    assert backend.history == [expected_command]


@pytest.mark.parametrize(
    ("item", "kwargs", "message"),
    [
        ("y_at_x", {}, "--time"),
        ("time_at_value", {}, "--level"),
        ("vpp", {"time_s": 0.0}, "--time"),
        ("y_at_x", {"time_s": 0.0, "level": 0.5}, "--level"),
        ("time_at_edge", {"level": 0.5}, "--level"),
        ("time_at_value", {"level": 0.5, "time_s": 0.0}, "--time"),
        ("time_at_edge", {"slope": "either"}, "--slope"),
        ("time_at_edge", {"occurrence": 1.5}, "--occurrence"),
        ("time_at_edge", {"occurrence": 0}, "--occurrence"),
    ],
)
def test_measurement_query_rejects_missing_or_extra_parameterized_args(
    item, kwargs, message
):
    with pytest.raises(ParameterValidationError) as excinfo:
        measurement_query(
            item,
            1,
            capabilities=capabilities_for_model("DSOX4024A"),
            **kwargs,
        )

    assert message in str(excinfo.value)


@pytest.mark.parametrize(
    ("item", "response", "expected_value", "expected_history"),
    [
        ("period", "1.25E-4", 0.000125, [":MEASure:PERiod? CHANnel1"]),
        ("vavg", "-2.5E-2", -0.025, [":MEASure:VAVerage? DISPlay,CHANnel1"]),
        ("vrms", "7.07E-1", 0.707, [":MEASure:VRMS? DISPlay,DC,CHANnel1"]),
        ("ac_rms", "6.00E-1", 0.6, [":MEASure:VRMS? DISPlay,AC,CHANnel1"]),
        ("minimum", "-1.25E+0", -1.25, [":MEASure:VMIN? CHANnel1"]),
        ("maximum", "1.25E+0", 1.25, [":MEASure:VMAX? CHANnel1"]),
        ("x_at_max", "1.25E-6", 0.00000125, [":MEASure:XMAX? CHANnel1"]),
        ("x_at_min", "2.50E-6", 0.0000025, [":MEASure:XMIN? CHANnel1"]),
        ("rise_time", "1.00E-6", 0.000001, [":MEASure:RISetime? CHANnel1"]),
        ("fall_time", "1.50E-6", 0.0000015, [":MEASure:FALLtime? CHANnel1"]),
        ("amplitude", "1.20E+0", 1.2, [":MEASure:VAMPlitude? CHANnel1"]),
        ("top", "7.50E-1", 0.75, [":MEASure:VTOP? CHANnel1"]),
        ("base", "-4.50E-1", -0.45, [":MEASure:VBASe? CHANnel1"]),
        ("overshoot", "5.50E+0", 5.5, [":MEASure:OVERshoot? CHANnel1"]),
        ("preshoot", "2.50E+0", 2.5, [":MEASure:PREShoot? CHANnel1"]),
        ("positive_width", "2.00E-6", 0.000002, [":MEASure:PWIDth? CHANnel1"]),
        ("negative_width", "3.00E-6", 0.000003, [":MEASure:NWIDth? CHANnel1"]),
        ("duty_cycle", "4.80E+1", 48.0, [":MEASure:DUTYcycle? CHANnel1"]),
        ("negative_duty_cycle", "5.20E+1", 52.0, [":MEASure:NDUTy? CHANnel1"]),
        ("area", "1.20E-6", 0.0000012, [":MEASure:AREA? CHANnel1"]),
        ("positive_edges", "4", 4.0, [":MEASure:PEDGes? CHANnel1"]),
        ("negative_edges", "4", 4.0, [":MEASure:NEDGes? CHANnel1"]),
        ("positive_pulses", "2", 2.0, [":MEASure:PPULses? CHANnel1"]),
        ("negative_pulses", "2", 2.0, [":MEASure:NPULses? CHANnel1"]),
    ],
)
def test_measurement_controller_queries_additional_read_only_items(
    item, response, expected_value, expected_history
):
    backend = FakeBackend(responses={expected_history[0]: response})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    result = controller.query(1, item)

    assert result.valid is True
    assert result.value == expected_value
    assert backend.history == expected_history


def test_measurement_controller_rejects_invalid_channel_before_scpi():
    backend = FakeBackend()
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    with pytest.raises(ParameterValidationError):
        controller.query(5, "vpp")

    assert backend.history == []


def test_measurement_query_area_uses_capability_flag_instead_of_series():
    with pytest.raises(ParameterValidationError, match="capability profile"):
        measurement_query("area", 1, capabilities=capabilities_for_model("DSOX2004A"))
    assert measurement_query(
        "area", 1, capabilities=capabilities_for_model("DSOX4024A")
    ) == ":MEASure:AREA? CHANnel1"


def test_measurement_controller_rejects_area_before_scpi_when_unsupported():
    backend = FakeBackend()
    controller = MeasurementController(
        SCPIClient(backend), capabilities_for_model("DSOX2004A")
    )

    with pytest.raises(ParameterValidationError, match="capability profile"):
        controller.query(1, "area")

    assert backend.history == []


def test_measurement_capability_profiles_for_area_and_statistics():
    caps_2000x = capabilities_for_model("DSOX2004A")
    caps_3000x = capabilities_for_model("DSOX3024A")
    caps_4000x = capabilities_for_model("DSOX4024A")

    assert caps_2000x.supports_area_measurement is False
    assert caps_2000x.supports_measure_statistics is False
    assert caps_3000x.supports_area_measurement is True
    assert caps_3000x.supports_measure_statistics is True
    assert caps_4000x.supports_area_measurement is True
    assert caps_4000x.supports_measure_statistics is True
    # existing flags unchanged
    assert caps_2000x.supports_measure_results_dump is False
    assert caps_3000x.supports_measure_results_dump is True
    assert caps_4000x.supports_measure_results_dump is True


def test_measurement_controller_rejects_statistics_before_scpi_when_unsupported():
    backend = FakeBackend()
    controller = MeasurementController(
        SCPIClient(backend), capabilities_for_model("DSOX2004A")
    )

    with pytest.raises(ParameterValidationError, match="capability profile"):
        controller.statistics(1, ("vpp",))

    assert backend.history == []


def test_measurement_controller_statistics_uses_capability_flag():
    # 4000X with statistics disabled should still reject even though measurements are supported
    disabled_4000x = replace(
        capabilities_for_model("DSOX4024A"), supports_measure_statistics=False
    )
    backend = FakeBackend()
    controller = MeasurementController(SCPIClient(backend), disabled_4000x)

    with pytest.raises(ParameterValidationError, match="capability profile"):
        controller.statistics(1, ("vpp",))

    assert backend.history == []
    # 3000X with flag enabled should not be rejected at validation time
    enabled_3000x = capabilities_for_model("DSOX3024A")
    backend2 = FakeBackend(
        responses={
            ":MEASure:RESults?": "vpp,1.0,0.9,1.1,1.0,0.01,10",
        }
    )
    controller2 = MeasurementController(SCPIClient(backend2), enabled_3000x)
    # Should not raise at validation; will proceed to SCPI (may fail on missing stubs but not on capability)
    try:
        controller2.statistics(1, ("vpp",))
    except ParameterValidationError:
        pytest.fail("3000X statistics should be supported")
    # At least one SCPI should have been attempted
    assert any(cmd.startswith(":MEASure:") for cmd in backend2.history)
