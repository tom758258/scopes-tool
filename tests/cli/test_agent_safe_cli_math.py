import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.simulator_backend import SimulatorBackend
from tests.cli._agent_safe_cli_support import _json_stdout


def test_fft_simulate_2000x_uses_unindexed_commands_for_configure_and_query(capsys):
    common = [
        "fft",
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox2004a",
        "--function",
        "1",
    ]
    assert cli.main([*common, "--source-channel", "1"]) == 0
    configured = _json_stdout(capsys)
    assert configured["scpi"]["sent"] == [
        "*IDN?",
        ":FUNCtion:OPERation FFT",
        ":FUNCtion:SOURce1 CHANnel1",
        ":SYSTem:ERRor?",
    ]

    assert cli.main([*common, "--query"]) == 0
    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["operation"] == "query"
    assert result["fft_operation"] == "FFT"
    assert result["function"] == 1
    assert result["source_channel"] == 1
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":FUNCtion:OPERation?",
        ":FUNCtion:SOURce1?",
        ":FUNCtion:FFT:VTYPe?",
        ":FUNCtion:FFT:WINDow?",
        ":FUNCtion:FFT:CENTer?",
        ":FUNCtion:FFT:SPAN?",
        ":FUNCtion:DISPlay?",
        ":SYSTem:ERRor?",
    ]
    assert payload["system_error"]["is_error"] is False


def test_fft_4000x_advanced_dry_run_and_query_shape(capsys):
    assert (
        cli.main(
            [
                "fft",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--function",
                "2",
                "--source-channel",
                "1",
                "--fft-operation",
                "fft-phase",
                "--start-hz",
                "100",
                "--stop-hz",
                "1000",
                "--gate",
                "zoom",
                "--phase-reference",
                "display",
                "--detection-type",
                "positive-peak",
                "--detection-points",
                "2048",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    commands = configured["result"]["commands"]
    assert configured["result"]["fft_operation_canonical"] == "fft-phase"
    assert "fft_operation" not in configured["result"]
    assert commands == [
        ":FUNCtion2:OPERation FFTPhase",
        ":FUNCtion2:SOURce1 CHANnel1",
        ":FUNCtion2:FREQuency:STARt 100",
        ":FUNCtion2:FREQuency:STOP 1000",
        ":FUNCtion2:GATE ZOOM",
        ":FUNCtion2:PHASe:REFerence DISPlay",
        ":FUNCtion2:DETection:TYPE PPOSitive",
        ":FUNCtion2:DETection:POINts 2048",
    ]
    assert all("<" not in command and ">" not in command for command in commands)

    assert (
        cli.main(
            [
                "fft",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--function",
                "1",
                "--query",
            ]
        )
        == 0
    )
    queried = _json_stdout(capsys)["result"]
    assert queried["fft_operation"] == "FFT"
    assert queried["fft_operation_canonical"] == "fft"
    assert queried["phase_reference"] is None
    assert queried["detection_type"] == "off"
    assert queried["detection_points"] == 640
    assert queried["bin_size_hz"] == pytest.approx(1000)
    assert queried["sample_rate_hz"] == pytest.approx(1e9)
    assert queried["resolution_bandwidth_hz"] == pytest.approx(1500)


@pytest.mark.parametrize(
    ("model", "extra"),
    [
        ("keysight-dsox2004a", ["--fft-operation", "fft-phase"]),
        (
            "keysight-dsox4024a",
            ["--center-hz", "1000", "--start-hz", "100"],
        ),
        (
            "keysight-dsox4024a",
            ["--fft-operation", "fft-phase", "--units", "decibel"],
        ),
    ],
)
def test_fft_invalid_or_unsupported_configuration_fails_before_open(
    monkeypatch, capsys, model, extra
):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "fft",
                "--simulate",
                "--json",
                "--model",
                model,
                "--function",
                "1",
                "--source-channel",
                "1",
                *extra,
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_display_simulate_2000x_uses_unindexed_scpi(capsys):
    assert (
        cli.main(
            [
                "math-display",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
                "--function",
                "1",
                "--on",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["operation"] == "set"
    assert result["function"] == 1
    assert result["enabled"] is True
    assert result["command"] == ":FUNCtion:DISPlay ON"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":FUNCtion:DISPlay ON",
        ":SYSTem:ERRor?",
    ]


def test_math_vertical_simulate_4000x_uses_indexed_scpi(capsys):
    assert (
        cli.main(
            [
                "math-vertical",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--function",
                "2",
                "--scale",
                "2",
                "--offset",
                "0.5",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["operation"] == "set"
    assert result["function"] == 2
    assert result["scale"] == 2.0
    assert result["range"] is None
    assert result["offset"] == 0.5
    assert result["commands"] == [
        ":FUNCtion2:SCALe 2",
        ":FUNCtion2:OFFSet 0.5",
    ]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":FUNCtion2:SCALe 2",
        ":FUNCtion2:OFFSet 0.5",
        ":SYSTem:ERRor?",
    ]


def test_math_vertical_query_with_setter_fails_before_open(
    monkeypatch, capsys
):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-vertical",
                "--simulate",
                "--json",
                "--function",
                "1",
                "--query",
                "--offset",
                "0",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


@pytest.mark.parametrize(
    ("model", "function", "prefix"),
    [
        ("keysight-dsox2004a", "1", ":FUNCtion"),
        ("keysight-dsox3024a", "1", ":FUNCtion"),
        ("keysight-dsox4024a", "2", ":FUNCtion2"),
    ],
)
def test_math_operator_dry_run_uses_model_function_dialect(
    model, function, prefix, capsys
):
    assert (
        cli.main(
            [
                "math-operator",
                "--dry-run",
                "--json",
                "--model",
                model,
                "--function",
                function,
                "--operation",
                "subtract",
                "--source1",
                "channel1",
                "--source2",
                "channel2",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["operation"] == "set"
    assert result["function"] == int(function)
    assert result["math_operation"] == "subtract"
    assert result["source1"] == "channel1"
    assert result["source2"] == "channel2"
    assert result["commands"] == [
        f"{prefix}:OPERation SUBTract",
        f"{prefix}:SOURce1 CHANnel1",
        f"{prefix}:SOURce2 CHANnel2",
    ]
    if model == "keysight-dsox4024a":
        assert all(
            command.startswith(":FUNCtion2") for command in result["commands"]
        )
    else:
        assert all(":FUNCtion1" not in command for command in result["commands"])
    assert payload["scpi"]["planned"] == [
        *result["commands"],
        ":SYSTem:ERRor?",
    ]


def test_math_operator_missing_source2_fails_before_open(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-operator",
                "--simulate",
                "--json",
                "--function",
                "1",
                "--operation",
                "add",
                "--source1",
                "channel1",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_transform_dry_run_configures_integrate(capsys):
    assert (
        cli.main(
            [
                "math-transform",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox2004a",
                "--function",
                "1",
                "--operation",
                "integrate",
                "--source",
                "channel1",
                "--input-offset",
                "0",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result == {
        "operation": "set",
        "function": 1,
        "math_operation": "integrate",
        "source": "channel1",
        "input_offset": 0.0,
        "gain": None,
        "linear_offset": None,
        "commands": [
            ":FUNCtion:OPERation INTegrate",
            ":FUNCtion:SOURce1 CHANnel1",
            ":FUNCtion:INTegrate:IOFFset 0",
        ],
    }
    assert payload["scpi"]["planned"] == [
        *result["commands"],
        ":SYSTem:ERRor?",
    ]


def test_math_transform_simulate_configure_query_round_trip(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: simulator_backend())
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--function",
        "2",
    ]
    assert (
        cli.main(
            [
                "math-transform",
                *common,
                "--operation",
                "linear",
                "--source",
                "channel1",
                "--gain",
                "2",
                "--linear-offset",
                "-1",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion2:OPERation LINear",
        ":FUNCtion2:SOURce1 CHANnel1",
        ":FUNCtion2:LINear:GAIN 2",
        ":FUNCtion2:LINear:OFFSet -1",
    ]

    assert cli.main(["math-transform", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    result = queried["result"]
    assert result["operation"] == "query"
    assert result["function"] == 2
    assert result["math_operation"] == "linear"
    assert result["operation_raw"] == "LINEAR"
    assert result["source"] == "channel1"
    assert result["source_raw"] == "CHANnel1"
    assert result["input_offset"] is None
    assert result["gain"] == 2.0
    assert result["linear_offset"] == -1.0
    assert queried["scpi"]["sent"][-5:] == [
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:SOURce1?",
        ":FUNCtion2:LINear:GAIN?",
        ":FUNCtion2:LINear:OFFSet?",
        ":SYSTem:ERRor?",
    ]


def test_math_transform_invalid_option_fails_before_open(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-transform",
                "--simulate",
                "--json",
                "--function",
                "1",
                "--operation",
                "absolute",
                "--source",
                "channel1",
                "--gain",
                "2",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_composite_source_simulate_configure_query_round_trip(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: simulator_backend())
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox2004a",
    ]
    assert (
        cli.main(
            [
                "math-composite-source",
                *common,
                "--operation",
                "subtract",
                "--source1",
                "channel1",
                "--source2",
                "channel2",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion:GOFT:OPERation SUBTract",
        ":FUNCtion:GOFT:SOURce1 CHANnel1",
        ":FUNCtion:GOFT:SOURce2 CHANnel2",
    ]

    assert cli.main(["math-composite-source", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    result = queried["result"]
    assert result["operation"] == "query"
    assert result["math_operation"] == "subtract"
    assert result["operation_raw"] == "SUBTRACT"
    assert result["source1"] == "channel1"
    assert result["source1_raw"] == "CHANnel1"
    assert result["source2"] == "channel2"
    assert result["source2_raw"] == "CHANnel2"


def test_math_transform_4000x_cascade_dry_run(capsys):
    assert (
        cli.main(
            [
                "math-transform",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--function",
                "2",
                "--operation",
                "absolute",
                "--source",
                "math1",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["source"] == "math1"
    assert payload["result"]["commands"] == [
        ":FUNCtion2:OPERation ABSolute",
        ":FUNCtion2:SOURce1 FUNCtion1",
    ]


def test_math_transform_unsupported_composite_fails_before_open(
    monkeypatch, capsys
):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-transform",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--function",
                "1",
                "--operation",
                "absolute",
                "--source",
                "composite",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_filter_common_simulate_configure_query_round_trip(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: simulator_backend())
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox2004a",
        "--function",
        "1",
    ]
    assert (
        cli.main(
            [
                "math-filter",
                *common,
                "--operation",
                "high-pass",
                "--source",
                "composite",
                "--cutoff-hz",
                "1000",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion:OPERation HIGHpass",
        ":FUNCtion:SOURce1 GOFT",
        ":FUNCtion:FREQuency:HIGHpass 1000",
    ]

    assert cli.main(["math-filter", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    assert queried["result"]["math_operation"] == "high-pass"
    assert queried["result"]["source"] == "composite"
    assert queried["result"]["cutoff_hz"] == 1000.0
    assert queried["result"]["average_count"] is None
    assert queried["result"]["smooth_points"] is None
    assert queried["scpi"]["sent"][-4:] == [
        ":FUNCtion:OPERation?",
        ":FUNCtion:SOURce1?",
        ":FUNCtion:FREQuency:HIGHpass?",
        ":SYSTem:ERRor?",
    ]


def test_math_filter_advanced_and_clear_simulate(monkeypatch, capsys):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: simulator_backend())
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--function",
        "2",
    ]
    assert (
        cli.main(
            [
                "math-filter",
                *common,
                "--operation",
                "average",
                "--source",
                "math1",
                "--average-count",
                "64",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion2:OPERation AVERage",
        ":FUNCtion2:SOURce1 FUNCtion1",
        ":FUNCtion2:AVERage:COUNt 64",
    ]

    assert cli.main(["math-filter", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    assert queried["result"]["math_operation"] == "average"
    assert queried["result"]["source"] == "math1"
    assert queried["result"]["average_count"] == 64
    assert queried["scpi"]["sent"][-4:] == [
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:SOURce1?",
        ":FUNCtion2:AVERage:COUNt?",
        ":SYSTem:ERRor?",
    ]

    assert cli.main(["math-clear", *common]) == 0
    cleared = _json_stdout(capsys)
    assert cleared["result"]["operation"] == "clear"
    assert cleared["result"]["function"] == 2
    assert cleared["result"]["cleared"] is True
    assert cleared["result"]["command"] == ":FUNCtion2:CLEar"
    assert cleared["scpi"]["sent"][-2:] == [
        ":FUNCtion2:CLEar",
        ":SYSTem:ERRor?",
    ]


def test_math_filter_irrelevant_parameter_fails_before_open(
    monkeypatch, capsys
):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-filter",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--function",
                "1",
                "--operation",
                "envelope",
                "--source",
                "channel1",
                "--cutoff-hz",
                "1000",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_visualization_common_and_trend_simulate_round_trips(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: simulator_backend())
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox2004a",
        "--function",
        "1",
    ]
    assert (
        cli.main(
            [
                "math-visualization",
                *common,
                "--operation",
                "magnify",
                "--source",
                "composite",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion:OPERation MAGNify",
        ":FUNCtion:SOURce1 GOFT",
    ]

    assert cli.main(["math-visualization", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    assert queried["result"]["math_operation"] == "magnify"
    assert queried["result"]["source"] == "composite"

    assert (
        cli.main(
            [
                "math-visualization",
                *common,
                "--operation",
                "trend",
                "--source",
                "channel1",
                "--source2",
                "channel2",
                "--measurement",
                "vratio",
            ]
        )
        == 0
    )
    _json_stdout(capsys)

    assert cli.main(["math-visualization", *common, "--query"]) == 0
    trend = _json_stdout(capsys)
    assert trend["result"]["math_operation"] == "trend"
    assert trend["result"]["source"] == "channel1"
    assert trend["result"]["source2"] == "channel2"
    assert trend["result"]["measurement"] == "vratio"
    assert trend["result"]["measurement_slot"] is None


def test_math_visualization_4000x_advanced_and_trend_slot_simulate(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: simulator_backend())
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--function",
        "2",
    ]
    assert (
        cli.main(
            [
                "math-visualization",
                *common,
                "--operation",
                "max-hold",
                "--source",
                "math1",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion2:OPERation MAXHold",
        ":FUNCtion2:SOURce1 FUNCtion1",
    ]

    assert cli.main(["math-visualization", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    assert queried["result"]["math_operation"] == "max-hold"
    assert queried["result"]["source"] == "math1"

    assert (
        cli.main(
            [
                "math-visualization",
                *common,
                "--operation",
                "trend",
                "--measurement-slot",
                "3",
            ]
        )
        == 0
    )
    trend_configured = _json_stdout(capsys)
    assert trend_configured["result"]["commands"] == [
        ":FUNCtion2:OPERation TRENd",
        ":FUNCtion2:TRENd:NMEasurement MEAS3",
    ]

    assert cli.main(["math-visualization", *common, "--query"]) == 0
    trend = _json_stdout(capsys)
    assert trend["result"]["math_operation"] == "trend"
    assert trend["result"]["source"] is None
    assert trend["result"]["measurement"] is None
    assert trend["result"]["measurement_raw"] == "MEAS3"
    assert trend["result"]["measurement_slot"] == 3


def test_math_visualization_capability_rejection_fails_before_open(
    monkeypatch, capsys
):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-visualization",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
                "--function",
                "1",
                "--operation",
                "maximum",
                "--source",
                "channel1",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False
