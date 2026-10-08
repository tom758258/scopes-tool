from scopes_tool_cli import cli, runtime
from scopes_tool_core.identity import physical_model_for_id
from scopes_tool_core.simulator_backend import SimulatorBackend
from tests.cli._agent_safe_cli_support import _json_stdout


def test_measure_simulate_json_reports_measurement_fields(capsys):
    assert cli.main(["measure", "--simulate", "--json", "--channel", "1", "--item", "vpp"]) == 0

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["item"] == "vpp"
    assert result["channel"] == 1
    assert result["valid"] is True
    assert result["value"] == 0.5
    assert result["unit"] == "V"
    assert result["raw_value"] == "5.000000E-01"
    assert result["parameters"] == {}
    assert payload["system_error"]["is_error"] is False


def test_measure_pair_phase_simulate_json_uses_signal_model(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "phase",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["item"] == "phase"
    assert result["channel"] == 1
    assert result["reference_channel"] == 2
    assert result["valid"] is True
    assert result["value"] == 45.0
    assert result["unit"] == "deg"


def test_measure_pair_delay_simulate_json_on_4000x_uses_signal_model(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "delay",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["item"] == "delay"
    assert result["reference_channel"] == 2
    assert result["valid"] is True
    assert result["value"] == 45.0 / 360.0 / 1000.0
    assert result["unit"] == "s"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":SYSTem:ERRor?",
        ":MEASure:DELay? AUTO,CHANnel1,CHANnel2",
        ":SYSTem:ERRor?",
    ]


def test_measure_pair_delay_simulate_json_rejects_non_4000x_before_measurement(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox3024a",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "delay",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "capability profile" in payload["error"]["message"]
    assert payload["scpi"]["sent"] == ["*IDN?"]


def test_measure_pair_phase_simulate_json_supported_across_target_models(capsys):
    for model in (
        "keysight-dsox4024a",
        "keysight-dsox4034a",
        "keysight-dsox3024a",
        "keysight-dsox2004a",
    ):
        assert (
            cli.main(
                [
                    "measure",
                    "--simulate",
                    "--json",
                    "--model",
                    model,
                    "--source-channel",
                    "1",
                    "--reference-channel",
                    "2",
                    "--item",
                    "phase",
                ]
            )
            == 0
        )
        payload = _json_stdout(capsys)
        assert payload["idn"]["model"] == physical_model_for_id(
            model
        ).canonical_model
        assert payload["result"]["value"] == 45.0


def test_measure_simulate_json_reports_invalid_sentinel(monkeypatch, capsys):
    backend = SimulatorBackend(invalid_measurement_channels={1})
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert cli.main(["measure", "--simulate", "--json", "--channel", "1", "--item", "vpp"]) == 1

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert payload["ok"] is False
    assert result["valid"] is False
    assert result["value"] is None
    assert result["raw_value"] == "9.9E+37"
    assert result["reason"] == "invalid measurement sentinel"


def test_measure_pair_simulate_json_reports_reference_channel_invalid_sentinel(
    monkeypatch, capsys
):
    backend = SimulatorBackend(invalid_measurement_channels={2})
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "phase",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert payload["ok"] is False
    assert result["valid"] is False
    assert result["value"] is None
    assert result["raw_value"] == "9.9E+37"
    assert result["reason"] == "invalid measurement sentinel"


def test_measure_simulate_json_accepts_signal_override(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--simulate-signal",
                "1:dc:0:0:1.25:0",
                "--channel",
                "1",
                "--item",
                "vavg",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["value"] == 1.25


def test_measure_sweep_simulate_json_all_channels(capsys):
    assert cli.main(["measure-sweep", "--simulate", "--json", "--channel", "all"]) == 0

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["channels"] == [1, 2, 3, 4]
    assert result["items"] == ["vpp", "frequency", "period", "vrms"]
    assert len(result["measurements"]) == 16
    assert result["summary"] == {
        "valid_count": 16,
        "invalid_count": 0,
        "error_count": 0,
    }


def test_measure_sweep_simulate_json_pair_items_on_4000x(capsys):
    assert (
        cli.main(
            [
                "measure-sweep",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--channel",
                "1",
                "--items",
                "vpp",
                "--pair",
                "1:2",
                "--pair-items",
                "phase,delay",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    measurements = payload["result"]["measurements"]
    assert [item["item"] for item in measurements] == ["vpp", "phase", "delay"]
    assert measurements[1]["reference_channel"] == 2
    assert measurements[2]["valid"] is True
    assert payload["result"]["summary"]["valid_count"] == 3


def test_measure_sweep_invalid_measurement_continues_and_exits_one(capsys):
    assert (
        cli.main(
            [
                "measure-sweep",
                "--simulate",
                "--json",
                "--simulate-invalid-measurement",
                "CH2",
                "--channel",
                "all",
                "--items",
                "vpp",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert len(result["measurements"]) == 4
    assert result["measurements"][1]["channel"] == 2
    assert result["measurements"][1]["valid"] is False
    assert result["measurements"][1]["reason"] == "invalid measurement sentinel"
    assert result["summary"] == {
        "valid_count": 3,
        "invalid_count": 1,
        "error_count": 0,
    }
