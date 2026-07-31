import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(
    tmp_path,
    model="keysight-dsox4034a",
    *,
    mode="simulate",
    resource=None,
):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode=mode,
        model=model,
        resource=resource,
        artifact_root=tmp_path,
        queue_max=1,
        output_format="jsonl",
    )


def test_worker_serial_commands_are_allowlisted(tmp_path):
    for command, arguments in [
        ("serial-query", {"bus": 1}),
        ("serial-mode", {"bus": 1, "query": True}),
        ("serial-display", {"bus": 1, "query": True}),
        ("serial-uart", {"bus": 1, "query": True}),
        ("serial-i2c", {"bus": 1, "query": True}),
        ("serial-spi", {"bus": 1, "query": True}),
        ("serial-can", {"bus": 1, "query": True}),
    ]:
        assert command in worker.DOMAIN_COMMANDS
        assert worker.parse_domain_command(
            command, arguments, _runtime(tmp_path)
        ).command == command


def test_worker_serial_display_configure_arguments_mapping(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-display", {"bus": 2, "enabled": False}, _runtime(tmp_path)
    )
    assert parsed.bus == 2
    assert parsed.enabled is False


def test_worker_serial_query_result_preservation(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-query", {"bus": 1}, _runtime(tmp_path)
    )
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert payload["result"]["bus"] == 1
    assert payload["result"]["raw"] == ":SBUS1:DISP 0;MODE UART;"


def test_worker_serial_uart_configure_arguments_mapping(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-uart",
        {"bus": 1, "rx_source": "channel1", "baud_rate": 115200},
        _runtime(tmp_path),
    )
    assert parsed.command == "serial-uart"
    assert parsed.rx_source == "channel1"
    assert parsed.baud_rate == 115200


def test_worker_serial_uart_configure_execution_preserves_p1_result(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-uart",
        {"bus": 1, "rx_source": "channel1", "baud_rate": 115200},
        _runtime(tmp_path),
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["result"]["rx_source"] == "channel1"
    assert payload["result"]["commands"] == [
        ":SBUS1:MODE UART",
        ":SBUS1:UART:SOURce:RX CHANnel1",
        ":SBUS1:UART:BAUDrate 115200",
    ]


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("serial-query", {"bus": True}),
        ("serial-query", {"bus": 2}),
        ("serial-mode", {"bus": 1, "mode": "usb-pd"}),
    ],
)
def test_worker_serial_rejects_invalid_2000x_arguments_before_side_effects(
    tmp_path, command, arguments
):
    runtime = _runtime(tmp_path, "keysight-dsox2004a")
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}


def test_worker_live_serial_rejects_invalid_startup_model_arguments_before_side_effects(
    tmp_path,
):
    runtime = _runtime(
        tmp_path,
        "keysight-dsox2004a",
        mode="live",
        resource="FAKE::SCOPE",
    )

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("serial-query", {"bus": 2}, runtime)

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
