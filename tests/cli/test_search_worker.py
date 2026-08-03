import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path, model="keysight-dsox4034a"):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model=model,
        resource=None,
        artifact_root=tmp_path,
        queue_max=1,
        output_format="jsonl",
    )


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("search-state", {"query": True}),
        ("search-state", {"enabled": True}),
        ("search-state", {"enabled": False}),
        ("search-mode", {"query": True}),
        ("search-mode", {"mode": "serial1"}),
        ("search-mode", {"mode": "serial2"}),
        ("search-mode", {"mode": "edge"}),
        ("search-mode", {"mode": "glitch"}),
        ("search-mode", {"mode": "runt"}),
        ("search-mode", {"mode": "transition"}),
        ("search-mode", {"mode": "peak"}),
        ("search-count", {"query": True}),
    ],
)
def test_worker_search_accepts_canonical_payloads(tmp_path, command, arguments):
    assert command in worker.DOMAIN_COMMANDS
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    assert parsed.command == command


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("search-state", {}),
        ("search-state", {"query": False}),
        ("search-state", {"query": True, "enabled": True}),
        ("search-state", {"enabled": "true"}),
        ("search-state", {"enabled": 1}),
        ("search-state", {"state": True}),
        ("search-mode", {}),
        ("search-mode", {"query": False}),
        ("search-mode", {"query": True, "mode": "edge"}),
        ("search-mode", {"mode": 1}),
        ("search-mode", {"mode": "ser1"}),
        ("search-mode", {"mode": "ser2"}),
        ("search-mode", {"mode": "glit"}),
        ("search-mode", {"mode": "tran"}),
        ("search-mode", {"mode": "pwid"}),
        ("search-mode", {"mode": "pulse-width"}),
        ("search-mode", {"mode": "off"}),
        ("search-mode", {"value": "edge"}),
        ("search-count", {}),
        ("search-count", {"query": False}),
        ("search-count", {"query": True, "count": 1}),
    ],
)
def test_worker_search_rejects_noncanonical_payloads_before_side_effects(
    tmp_path, command, arguments
):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize(
    "model, mode",
    [
        ("keysight-dsox2004a", "edge"),
        ("keysight-dsox2004a", "serial2"),
        ("keysight-dsox3024a", "peak"),
    ],
)
def test_worker_search_rejects_unsupported_mode_before_side_effects(tmp_path, model, mode):
    runtime = _runtime(tmp_path, model)
    with pytest.raises(OscilloscopeError, match="not supported by the selected"):
        worker.parse_domain_command("search-mode", {"mode": mode}, runtime)
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_search_profile_acceptance_matrix(tmp_path):
    assert worker.parse_domain_command(
        "search-mode", {"mode": "serial1"}, _runtime(tmp_path, "keysight-dsox2004a")
    ).mode == "serial1"
    assert worker.parse_domain_command(
        "search-mode", {"mode": "edge"}, _runtime(tmp_path, "keysight-dsox3024a")
    ).mode == "edge"
    assert worker.parse_domain_command(
        "search-mode", {"mode": "peak"}, _runtime(tmp_path, "keysight-dsox4034a")
    ).mode == "peak"


def test_worker_search_simulator_execution(tmp_path):
    parsed = worker.parse_domain_command(
        "search-mode", {"mode": "peak"}, _runtime(tmp_path)
    )
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert payload["result"]["mode"] == "peak"
    assert payload["result"]["enabled"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":SEARch:STATe 1",
        ":SEARch:MODE PEAK",
        ":SYSTem:ERRor?",
    ]


def test_worker_search_event_acceptance_and_rejection(tmp_path):
    runtime_4000x = _runtime(tmp_path, "keysight-dsox4034a")
    runtime_2000x = _runtime(tmp_path, "keysight-dsox2004a")

    p1 = worker.parse_domain_command("search-event", {"query": True}, runtime_4000x)
    assert p1.command == "search-event"

    p2 = worker.parse_domain_command("search-event", {"event": 1}, runtime_4000x)
    assert p2.command == "search-event"

    with pytest.raises(OscilloscopeError, match="must be an integer"):
        worker.parse_domain_command("search-event", {"event": "1"}, runtime_4000x)

    with pytest.raises(OscilloscopeError, match="must be a positive integer"):
        worker.parse_domain_command("search-event", {"event": 0}, runtime_4000x)

    with pytest.raises(OscilloscopeError, match="unknown argument"):
        worker.parse_domain_command("search-event", {"event": 1, "unknown": True}, runtime_4000x)

    with pytest.raises(OscilloscopeError, match="not supported by the selected"):
        worker.parse_domain_command("search-event", {"query": True}, runtime_2000x)


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("serial-search-uart", {"bus": 1, "mode": "rx-data", "data": 85, "qualifier": "equal"}),
        ("serial-search-i2c", {"bus": 1, "mode": "read7", "address": 80, "data": 165}),
        ("serial-search-spi", {"bus": 1, "mode": "mosi", "data": "0xA5XX", "width": 2}),
        ("serial-search-can", {"bus": 1, "mode": "data", "data": "0x12XX", "data_length": 2, "id": "0x123", "id_mode": "standard"}),
    ],
)
def test_worker_serial_search_accepts_canonical_payloads(tmp_path, command, arguments):
    assert command in worker.DOMAIN_COMMANDS
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    assert parsed.command == command
    assert parsed.bus == 1


def test_worker_serial_search_rejects_unsupported_bus_before_side_effects(tmp_path):
    runtime = _runtime(tmp_path, "keysight-dsox2004a")
    with pytest.raises(OscilloscopeError, match="Serial bus 2"):
        worker.parse_domain_command(
            "serial-search-uart", {"bus": 2, "mode": "rx-data"}, runtime
        )
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()
