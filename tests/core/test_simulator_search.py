import pytest

from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend, SimulatorBackendError


def test_simulator_search_state_mode_and_count_are_deterministic():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    assert scope.query_search_state().to_json() == {"enabled": False, "raw_state": "0"}
    assert scope.query_search_mode().to_json() == {
        "mode": None,
        "enabled": False,
        "raw_mode": "OFF",
    }
    assert scope.query_search_count().to_json() == {"count": 0, "raw_count": "0"}

    scope.configure_search_mode("peak")
    assert scope.query_search_state().enabled is True
    assert scope.query_search_mode().to_json() == {
        "mode": "peak",
        "enabled": True,
        "raw_mode": "PEAK",
    }

    scope.configure_search_state(False)
    assert scope.query_search_mode().mode is None


@pytest.mark.parametrize(
    "model_id, command",
    [
        ("keysight-dsox2004a", ":SEARch:MODE EDGE"),
        ("keysight-dsox2004a", ":SEARch:MODE SERial2"),
        ("keysight-dsox3024a", ":SEARch:MODE PEAK"),
    ],
)
def test_simulator_rejects_search_modes_outside_model_profile(model_id, command):
    backend = SimulatorBackend(physical_model_id=model_id)
    with pytest.raises(SimulatorBackendError, match="not supported by simulator model"):
        backend.write(command)


def test_simulator_accepts_profile_supported_search_modes():
    SimulatorBackend(physical_model_id="keysight-dsox2004a").write(":SEARch:MODE SERial1")
    SimulatorBackend(physical_model_id="keysight-dsox3024a").write(":SEARch:MODE EDGE")
    SimulatorBackend(physical_model_id="keysight-dsox4034a").write(":SEARch:MODE PEAK")


@pytest.mark.parametrize(
    "protocol, configure, query, expected",
    [
        (
            "uart",
            lambda scope: scope.configure_serial_search_uart(1, "rx-data", data=85, qualifier="equal"),
            lambda scope: scope.query_serial_search_uart(1),
            {"mode": "rx-data", "data": 85, "qualifier": "equal", "selected": True},
        ),
        (
            "i2c",
            lambda scope: scope.configure_serial_search_i2c(1, "nack", address=-1, data=80),
            lambda scope: scope.query_serial_search_i2c(1),
            {"mode": "nack", "address": -1, "data": 80, "selected": True},
        ),
        (
            "spi",
            lambda scope: scope.configure_serial_search_spi(1, "miso", data="0xa5xx", width=8),
            lambda scope: scope.query_serial_search_spi(1),
            {"mode": "miso", "data": "0xA5XX", "width": 8, "selected": True},
        ),
        (
            "can",
            lambda scope: scope.configure_serial_search_can(1, "id-data", data="0x12xx", data_length=2, id_val="0x123", id_mode="standard"),
            lambda scope: scope.query_serial_search_can(1),
            {"mode": "id-data", "data": "0x12XX", "data_length": 2, "id": "0x123", "id_mode": "standard", "selected": True},
        ),
    ],
)
def test_simulator_serial_search_round_trip(protocol, configure, query, expected):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    configured = configure(scope)
    queried = query(scope).to_json()

    assert configured.bus == 1
    for key, value in expected.items():
        assert queried[key] == value


def test_simulator_search_event_default_and_set():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    assert scope.query_search_event().to_json() == {"event": 1, "raw": "1"}
    assert scope.configure_search_event(2).to_json() == {"event": 2}
    assert scope.query_search_event().to_json() == {"event": 2, "raw": "2"}


@pytest.mark.parametrize("model_id", ["keysight-dsox2004a", "keysight-dsox3024a"])
def test_simulator_search_event_unsupported_models_reject(model_id):
    backend = SimulatorBackend(physical_model_id=model_id)
    with pytest.raises(SimulatorBackendError, match="not supported by simulator model"):
        backend.query(":SEARch:EVENt?")
    with pytest.raises(SimulatorBackendError, match="not supported by simulator model"):
        backend.write(":SEARch:EVENt 1")


@pytest.mark.parametrize("command", [":SEARch:EVENt 0", ":SEARch:EVENt -1", ":SEARch:EVENt abc"])
def test_simulator_search_event_rejects_invalid_values(command):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    with pytest.raises(SimulatorBackendError, match="Invalid search event for simulator"):
        backend.write(command)
