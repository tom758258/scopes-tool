import pytest

from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.trigger import (
    TRIGGER_MODES,
    TriggerModeController,
    parse_trigger_mode,
    trigger_mode_command,
)


def test_trigger_modes_cover_the_supported_dso_modes():
    assert TRIGGER_MODES == (
        "edge",
        "glitch",
        "pattern",
        "tv",
        "delay",
        "edge-burst",
        "or",
        "runt",
        "setup-hold",
        "transition",
    )


@pytest.mark.parametrize(
    "mode, scpi",
    [
        ("edge", ":TRIGger:MODE EDGE"),
        ("glitch", ":TRIGger:MODE GLITch"),
        ("pattern", ":TRIGger:MODE PATTern"),
        ("tv", ":TRIGger:MODE TV"),
        ("delay", ":TRIGger:MODE DELay"),
        ("edge-burst", ":TRIGger:MODE EBURst"),
        ("or", ":TRIGger:MODE OR"),
        ("runt", ":TRIGger:MODE RUNT"),
        ("setup-hold", ":TRIGger:MODE SHOLd"),
        ("transition", ":TRIGger:MODE TRANsition"),
    ],
)
def test_trigger_mode_command_reuses_the_existing_builders(mode, scpi):
    assert trigger_mode_command(mode) == scpi
    assert parse_trigger_mode(scpi.rsplit(" ", 1)[1]) == mode


@pytest.mark.parametrize("mode", ["", "serial1", "edge2", "MODE EDGE", "ORX"])
def test_trigger_mode_command_rejects_unknown_modes(mode):
    with pytest.raises(ParameterValidationError):
        trigger_mode_command(mode)


def test_trigger_mode_controller_configures_and_queries():
    backend = FakeBackend(responses={":TRIGger:MODE?": "OR"})
    controller = TriggerModeController(SCPIClient(backend))

    controller.configure("or")
    queried = controller.query()

    assert queried.to_json() == {"mode": "or", "raw_mode": "OR"}
    assert backend.history == [":TRIGger:MODE OR", ":TRIGger:MODE?"]
