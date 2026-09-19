import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError


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
                queue_max=1,
        output_format="jsonl",
    )


def test_worker_serial_commands_are_allowlisted(tmp_path):
    for command, arguments in [
        ("serial-status", {"bus": 1}),
        ("serial-mode", {"bus": 1, "query": True}),
        ("serial-enable", {"bus": 1}),
        ("serial-disable", {"bus": 1}),
        ("serial-uart-set", {"bus": 1, "baud_rate": 115200}),
        ("serial-uart-show", {"bus": 1}),
        ("serial-trigger-uart-set", {"bus": 1, "type": "rx-start"}),
        ("serial-trigger-uart-show", {"bus": 1}),
        ("serial-trigger-i2c-set", {"bus": 1, "type": "start"}),
        ("serial-trigger-i2c-show", {"bus": 1}),
        ("serial-trigger-spi-set", {"bus": 1, "type": "mosi", "width": 8, "data": "1010XX01"}),
        ("serial-trigger-spi-show", {"bus": 1}),
        ("serial-trigger-can-set", {"bus": 1, "type": "start-of-frame"}),
        ("serial-trigger-can-show", {"bus": 1}),
        ("serial-i2c-set", {"bus": 1, "address_size": "bit7"}),
        ("serial-i2c-show", {"bus": 1}),
        ("serial-spi-set", {"bus": 1, "word_width": 8}),
        ("serial-spi-show", {"bus": 1}),
        ("serial-can-set", {"bus": 1, "baud_rate": 500000}),
        ("serial-can-show", {"bus": 1}),
        ("serial-lister-status", {}),
        ("serial-lister-display", {"query": True}),
        ("serial-lister-reference", {"query": True}),
        ("serial-data", {"output": "lister.csv"}),
    ]:
        assert command in worker.DOMAIN_COMMANDS
        assert worker.parse_domain_command(
            command, arguments, _runtime(tmp_path)
        ).command == command


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("serial-query", {"bus": 1}),
        ("serial-display", {"bus": 1, "query": True}),
        ("serial-uart", {"bus": 1, "query": True}),
        ("serial-trigger-uart", {"bus": 1, "query": True}),
        ("serial-lister-query", {}),
        ("serial-lister-export", {"output": "lister.csv"}),
    ],
)
def test_worker_serial_legacy_spellings_rejected(tmp_path, command, arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime(tmp_path))


def test_worker_serial_enable_maps_to_bus_only_namespace(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-disable", {"bus": 2}, _runtime(tmp_path)
    )
    assert parsed.command == "serial-disable"
    assert parsed.bus == 2


def test_worker_serial_status_result_shape(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-status", {"bus": 1}, _runtime(tmp_path)
    )
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    result = payload["result"]
    assert result["operation"] == "status"
    assert result["bus"] == 1
    assert result["mode"] == "uart"
    assert result["protocol"] == "uart"
    assert result["config"]["baud_rate"] == 115200


def test_worker_serial_uart_set_arguments_mapping(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-uart-set",
        {"bus": 1, "rx_source": "channel1", "baud_rate": 115200},
        _runtime(tmp_path),
    )
    assert parsed.command == "serial-uart-set"
    assert parsed.rx_source == "channel1"
    assert parsed.baud_rate == 115200


def test_worker_serial_uart_set_execution_preserves_command_result(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-uart-set",
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


def test_worker_serial_uart_trigger_configure_execution_uses_shared_core_path(
    tmp_path,
):
    parsed = worker.parse_domain_command(
        "serial-trigger-uart-set",
        {"bus": 1, "type": "rx-data", "data": 85, "qualifier": "equal"},
        _runtime(tmp_path),
    )

    assert parsed.command == "serial-trigger-uart-set"
    assert parsed.type == "rx-data"
    assert parsed.data == 85
    assert parsed.qualifier == "equal"
    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["result"]["type"] == "rx-data"
    assert payload["result"]["raw_type"] == "RDAT"
    assert payload["result"]["selected"] is True


def test_worker_serial_trigger_uart_show_succeeds(tmp_path):
    parsed = worker.parse_domain_command(
        "serial-trigger-uart-show", {"bus": 1}, _runtime(tmp_path)
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["protocol"] == "uart"


def test_worker_serial_trigger_uart_set_rejects_unknown_fields(tmp_path):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError, match="unknown argument"):
        worker.parse_domain_command(
            "serial-trigger-uart-set",
            {"bus": 1, "type": "rx-start", "unexpected": "value"},
            runtime,
        )
    with pytest.raises(OscilloscopeError, match="unknown argument"):
        worker.parse_domain_command(
            "serial-trigger-uart-show",
            {"bus": 1, "type": "rx-start"},
            runtime,
        )


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("serial-trigger-i2c-show", {"bus": 1}),
        ("serial-trigger-spi-show", {"bus": 1}),
        ("serial-trigger-can-show", {"bus": 1}),
    ],
)
def test_worker_serial_trigger_show_commands_route_and_query(tmp_path, command, arguments):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(command, arguments, runtime)
    assert parsed.command == command
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert payload["result"]["protocol"] == command.removeprefix("serial-trigger-").removesuffix("-show")


def test_worker_serial_trigger_rejects_unknown_and_extra_show_fields(tmp_path):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError, match="unknown argument"):
        worker.parse_domain_command(
            "serial-trigger-spi-set",
            {"bus": 1, "type": "mosi", "unexpected": "value"},
            runtime,
        )
    with pytest.raises(OscilloscopeError, match="unknown argument"):
        worker.parse_domain_command(
            "serial-trigger-can-show",
            {"bus": 1, "type": "start-of-frame"},
            runtime,
        )


def test_worker_serial_i2c_trigger_rejects_cross_field_request(tmp_path):
    with pytest.raises(ParameterValidationError, match="requires --address"):
        worker.parse_domain_command(
            "serial-trigger-i2c-set",
            {"bus": 1, "type": "address-no-ack"},
            _runtime(tmp_path),
        )


def test_worker_serial_data_uses_caller_supplied_output(tmp_path):
    output = tmp_path / "exports" / "lister.csv"
    parsed = worker.parse_domain_command(
        "serial-data",
        {"output": str(output)},
        _runtime(tmp_path),
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert output.read_bytes() == b"bus,time,value\r\nSBUS1,0,0\r\n"
    assert payload["files"] == [{"kind": "csv", "path": str(output)}]


def test_worker_serial_lister_rejects_mixed_query_and_configure(tmp_path):
    with pytest.raises(OscilloscopeError, match="cannot be combined"):
        worker.parse_domain_command(
            "serial-lister-display",
            {"query": True, "selection": "bus1"},
            _runtime(tmp_path),
        )


def test_worker_serial_spi_rejects_incompatible_framing_and_clock_timeout(tmp_path):
    runtime = _runtime(tmp_path)

    with pytest.raises(
        ParameterValidationError,
        match="framing is explicitly set to timeout",
    ):
        worker.parse_domain_command(
            "serial-spi-set",
            {"bus": 1, "framing": "no-chip-select", "clock_timeout": 1e-6},
            runtime,
        )

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("serial-status", {"bus": True}),
        ("serial-status", {"bus": 2}),
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
        worker.parse_domain_command("serial-status", {"bus": 2}, runtime)

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
