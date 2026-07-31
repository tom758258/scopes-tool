import json

import pytest

from scopes_tool_cli import cli


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize(
    "args, expected",
    [
        (["search-state", "--query"], [":SEARch:STATe?"]),
        (["search-state", "--enabled", "true"], [":SEARch:STATe 1"]),
        (["search-state", "--enabled", "false"], [":SEARch:STATe 0"]),
        (["search-mode", "--query"], [":SEARch:MODE?"]),
        (["search-mode", "--mode", "serial1"], [":SEARch:STATe 1", ":SEARch:MODE SERial1"]),
        (["search-mode", "--mode", "edge"], [":SEARch:STATe 1", ":SEARch:MODE EDGE"]),
        (["search-mode", "--mode", "glitch"], [":SEARch:STATe 1", ":SEARch:MODE GLITch"]),
        (["search-mode", "--mode", "runt"], [":SEARch:STATe 1", ":SEARch:MODE RUNT"]),
        (["search-mode", "--mode", "transition"], [":SEARch:STATe 1", ":SEARch:MODE TRANsition"]),
        (["search-mode", "--mode", "peak"], [":SEARch:STATe 1", ":SEARch:MODE PEAK"]),
        (["search-count", "--query"], [":SEARch:COUNt?"]),
    ],
)
def test_search_commands_dry_run_json(capsys, args, expected):
    assert cli.main([*args, "--dry-run", "--json", "--model", "keysight-dsox4034a"]) == 0
    payload = _payload(capsys)
    assert payload["scpi"]["planned"] == [*expected, ":SYSTem:ERRor?"]


def test_search_simulator_queries_are_deterministic_and_preserve_raw(capsys):
    assert cli.main(["search-state", "--query", "--simulate", "--json"]) == 0
    result = _payload(capsys)["result"]
    assert {key: result[key] for key in ("operation", "command", "enabled", "raw_state")} == {
        "operation": "query",
        "command": ":SEARch:STATe?",
        "enabled": False,
        "raw_state": "0",
    }

    assert cli.main(["search-mode", "--query", "--simulate", "--json"]) == 0
    result = _payload(capsys)["result"]
    assert {
        key: result[key]
        for key in ("operation", "command", "mode", "enabled", "raw_mode")
    } == {
        "operation": "query",
        "command": ":SEARch:MODE?",
        "mode": None,
        "enabled": False,
        "raw_mode": "OFF",
    }

    assert cli.main(["search-count", "--query", "--simulate", "--json"]) == 0
    result = _payload(capsys)["result"]
    assert {key: result[key] for key in ("operation", "command", "count", "raw_count")} == {
        "operation": "query",
        "command": ":SEARch:COUNt?",
        "count": 0,
        "raw_count": "0",
    }


@pytest.mark.parametrize(
    "args",
    [
        ["search-state"],
        ["search-state", "--query", "--enabled", "true"],
        ["search-mode"],
        ["search-mode", "--query", "--mode", "edge"],
    ],
)
def test_search_action_validation_fails_before_open(monkeypatch, capsys, args):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main([*args, "--simulate", "--json", "--model", "keysight-dsox4034a"]) == 1
    assert _payload(capsys)["ok"] is False


@pytest.mark.parametrize("mode", ["ser1", "ser2", "glit", "tran", "pwid", "pulse-width", "off", "EDGE"])
def test_search_mode_rejects_aliases(mode, capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["search-mode", "--mode", mode, "--simulate", "--json"])
    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "model, mode",
    [
        ("keysight-dsox2004a", "edge"),
        ("keysight-dsox2004a", "serial2"),
        ("keysight-dsox3024a", "peak"),
    ],
)
def test_search_mode_profile_rejection_happens_before_open(monkeypatch, capsys, model, mode):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main(
        ["search-mode", "--mode", mode, "--simulate", "--json", "--model", model]
    ) == 1
    payload = _payload(capsys)
    assert "not supported by the selected" in payload["error"]["message"]


def test_search_count_requires_query(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["search-count"])
    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


def test_search_event_cli_execution_and_validation(capsys):
    assert cli.main(["search-event", "--query", "--simulate", "--model", "keysight-dsox4034a", "--json"]) == 0
    res_query = _payload(capsys)["result"]
    assert res_query["operation"] == "query"
    assert res_query["command"] == ":SEARch:EVENt?"
    assert res_query["event"] == 1
    assert res_query["raw"] == "1"

    assert cli.main(["search-event", "--event", "1", "--simulate", "--model", "keysight-dsox4034a", "--json"]) == 0
    res_cfg = _payload(capsys)["result"]
    assert res_cfg["operation"] == "configure"
    assert res_cfg["command"] == ":SEARch:EVENt 1"
    assert res_cfg["event"] == 1
    assert res_cfg["state_changing"] is True

    with pytest.raises(SystemExit) as exc:
        cli.main(["search-event", "--simulate", "--model", "keysight-dsox4034a", "--json"])
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        cli.main(["search-event", "--query", "--event", "1", "--simulate", "--model", "keysight-dsox4034a", "--json"])
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        cli.main(["search-event", "--event", "0", "--simulate", "--model", "keysight-dsox4034a", "--json"])
    assert exc.value.code == 2



@pytest.mark.parametrize(
    "cmd_args, expected_protocol",
    [
        (
            ["serial-search-uart", "--bus", "1", "--mode", "rx-data", "--data", "85", "--qualifier", "equal"],
            "uart",
        ),
        (
            ["serial-search-i2c", "--bus", "1", "--mode", "read7", "--address", "80", "--data", "255", "--qualifier", "not-equal"],
            "i2c",
        ),
        (
            ["serial-search-spi", "--bus", "1", "--mode", "mosi", "--data", "0xa5xx", "--width", "8"],
            "spi",
        ),
        (
            ["serial-search-can", "--bus", "1", "--mode", "id-data", "--data", "0x12xx", "--data-length", "2", "--id", "0xabc", "--id-mode", "standard"],
            "can",
        ),
    ],
)
def test_simulator_cli_serial_search_configure(capsys, cmd_args, expected_protocol):
    assert cli.main([*cmd_args, "--simulate", "--json"]) == 0
    payload = _payload(capsys)
    res = payload["result"]
    assert res["operation"] == "configure"
    assert res["protocol"] == expected_protocol
    assert res["bus"] == 1
    assert res["state_changing"] is True
    assert res["commands"] == payload["scpi"]["sent"][1:-1]
    assert "*IDN?" not in res["commands"]
    assert ":SYSTem:ERRor?" not in res["commands"]
    if expected_protocol == "spi":
        assert res["data"] == "0xA5XX"
        assert ':SEARch:SERial:SPI:PATTern:DATA "0xA5XX"' in res["commands"]
    if expected_protocol == "can":
        assert res["data"] == "0x12XX"
        assert res["id"] == "0xABC"
        assert ':SEARch:SERial:CAN:PATTern:DATA "0x12XX"' in res["commands"]
        assert ':SEARch:SERial:CAN:PATTern:ID "0xABC"' in res["commands"]


def test_serial_search_uart_query_json(capsys):
    assert cli.main(["serial-search-uart", "--bus", "1", "--query", "--simulate", "--json"]) == 0
    res = _payload(capsys)["result"]
    assert res["operation"] == "query"
    assert res["protocol"] == "uart"
    assert res["bus"] == 1
    assert res["search_enabled"] is False
    assert res["raw_search_state"] == "0"
    assert res["raw_search_mode"] == "OFF"
    assert res["selected"] is False
    assert res["mode"] == "rx-data"
    assert res["raw_mode"] == "RDAT"


@pytest.mark.parametrize(
    "args, protocol, expected",
    [
        (
            ["serial-search-uart", "--bus", "1", "--mode", "rx-data", "--data", "85", "--qualifier", "equal"],
            "uart",
            {"mode": "rx-data", "data": 85, "qualifier": "equal"},
        ),
        (
            ["serial-search-i2c", "--bus", "1", "--mode", "read7", "--address", "80", "--data", "165"],
            "i2c",
            {"mode": "read7", "address": 80, "data": 165},
        ),
        (
            ["serial-search-spi", "--bus", "1", "--mode", "mosi", "--data", "0xA5XX", "--width", "8"],
            "spi",
            {"mode": "mosi", "data": "0xA5XX", "width": 8},
        ),
        (
            ["serial-search-can", "--bus", "1", "--mode", "id-data", "--data", "0x12XX", "--data-length", "2", "--id", "0xABC", "--id-mode", "standard"],
            "can",
            {"mode": "id-data", "data": "0x12XX", "data_length": 2, "id": "0xABC", "id_mode": "standard"},
        ),
    ],
)
def test_serial_search_simulator_json_configure(capsys, args, protocol, expected):
    assert cli.main([*args, "--simulate", "--json"]) == 0
    result = _payload(capsys)["result"]
    assert result["operation"] == "configure"
    assert result["protocol"] == protocol
    assert result["bus"] == 1
    assert result["state_changing"] is True
    for key, value in expected.items():
        assert result[key] == value
    assert result["commands"][:2] == [":SEARch:STATe 1", ":SEARch:MODE SERial1"]


def test_serial_search_dry_run_planned_order(capsys):
    args = [
        "serial-search-uart",
        "--bus",
        "1",
        "--mode",
        "rx-data",
        "--data",
        "85",
        "--qualifier",
        "equal",
        "--dry-run",
        "--json",
    ]
    assert cli.main(args) == 0
    record = _payload(capsys)
    assert record["scpi"]["planned"] == [
        ":SEARch:STATe 1",
        ":SEARch:MODE SERial1",
        ":SEARch:SERial:UART:MODE RDATa",
        ":SEARch:SERial:UART:DATA 85",
        ":SEARch:SERial:UART:QUALifier EQUal",
        ":SYSTem:ERRor?",
    ]
    res = record["result"]
    assert res["operation"] == "configure"
    assert res["protocol"] == "uart"
    assert res["bus"] == 1
    assert res["mode"] == "rx-data"
