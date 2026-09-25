from dataclasses import replace

import pytest

from scopes_tool_core.drivers import (
    DRIVER_REGISTRY,
    driver_for_physical_model,
    scope_for_physical_model,
)
from scopes_tool_core.errors import UnsupportedModelError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.identity import (
    PHYSICAL_MODEL_REGISTRY,
    physical_model_for_id,
)
from scopes_tool_core.scope import Oscilloscope


def test_registered_models_select_registered_drivers():
    assert set(DRIVER_REGISTRY) == {"keysight-infiniivision", "tektronix"}
    assert {
        model.driver_id for model in PHYSICAL_MODEL_REGISTRY
    } == {"keysight-infiniivision", "tektronix"}

    physical_model = physical_model_for_id("keysight-dsox4024a")

    assert driver_for_physical_model(physical_model) is Oscilloscope
    assert isinstance(
        scope_for_physical_model(physical_model, FakeBackend()),
        Oscilloscope,
    )


@pytest.mark.parametrize("driver_id", ["", "unknown-driver"])
def test_missing_or_unknown_driver_id_fails_before_command_execution(driver_id):
    physical_model = replace(
        physical_model_for_id("keysight-dsox4024a"),
        driver_id=driver_id,
    )
    backend = FakeBackend()

    with pytest.raises(UnsupportedModelError, match="driver ID"):
        scope_for_physical_model(physical_model, backend)

    assert backend.history == []
