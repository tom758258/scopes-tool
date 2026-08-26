import ast
from pathlib import Path

import pytest

from scopes_tool_core.advanced import (
    CursorController as AdvancedCursorController,
    FFTController as AdvancedFFTController,
    MathController as AdvancedMathController,
    SetupController as AdvancedSetupController,
    TriggerHoldoffController as AdvancedTriggerHoldoffController,
    autoscale_commands,
    cursor_configure_commands,
    setup_recall_command,
    setup_save_command,
    trigger_holdoff_command,
    trigger_holdoff_commands,
)

from scopes_tool_core.cursor import CursorController
from scopes_tool_core.fft import FFTController
from scopes_tool_core.math import MathController
from scopes_tool_core.setup import SetupController
from scopes_tool_core.trigger_holdoff import TriggerHoldoffController

from scopes_tool_core.capabilities import capabilities_for_model

from scopes_tool_core.scope import Oscilloscope

from scopes_tool_core.simulator_backend import (
    SimulatorBackend,
    SimulatorBackendError,
)


def test_advanced_facade_reexports_canonical_domain_symbols():
    assert AdvancedCursorController is CursorController
    assert AdvancedFFTController is FFTController
    assert AdvancedMathController is MathController
    assert AdvancedSetupController is SetupController
    assert AdvancedTriggerHoldoffController is TriggerHoldoffController


def test_core_and_cli_do_not_import_advanced_facade():
    repo_root = Path(__file__).resolve().parents[2]
    scan_roots = (
        (repo_root / "src" / "scopes_tool_core", True),
        (repo_root / "src" / "scopes_tool_cli", False),
    )
    violations = []

    for package_root, exclude_facade in scan_roots:
        for path in sorted(package_root.rglob("*.py")):
            if exclude_facade and path.name == "advanced.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative_path = path.relative_to(repo_root).as_posix()
            for node in ast.walk(tree):
                imported_advanced = False
                if isinstance(node, ast.Import):
                    imported_advanced = any(
                        alias.name == "scopes_tool_core.advanced"
                        for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom):
                    imported_advanced = (
                        node.module == "advanced" and node.level >= 1
                    ) or (
                        node.module == "scopes_tool_core.advanced" and node.level == 0
                    ) or (
                        node.module == "scopes_tool_core"
                        and node.level == 0
                        and any(alias.name == "advanced" for alias in node.names)
                    ) or (
                        exclude_facade
                        and node.module is None
                        and node.level == 1
                        and any(alias.name == "advanced" for alias in node.names)
                    )
                if imported_advanced:
                    violations.append(f"{relative_path}:{node.lineno}")

    assert violations == [], "Unexpected advanced facade imports: " + ", ".join(violations)

def test_advanced_command_formatting():
    capabilities = capabilities_for_model("DSOX4024A")

    assert trigger_holdoff_command(1e-6) == ":TRIGger:HOLDoff 1e-6"
    assert trigger_holdoff_commands(1e-6) == [
        ":TRIGger:HOLDoff:RANDom OFF",
        ":TRIGger:HOLDoff 1e-6",
    ]
    assert cursor_configure_commands(
        1,
        0.0,
        1e-3,
        y1_volts=0.0,
        y2_volts=0.5,
        capabilities=capabilities,
    ) == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0",
        ":MARKer:X2Position 0.001",
        ":MARKer:Y1Position 0",
        ":MARKer:Y2Position 0.5",
    ]
    assert autoscale_commands((1, 2), capabilities=capabilities) == [
        ":AUToscale CHANnel1,CHANnel2"
    ]
    assert setup_save_command(slot=3) == ":SAVE:SETup 3"
    assert setup_recall_command(file_spec="\\usb\\setup.scp") == (
        ':RECall:SETup "\\usb\\setup.scp"'
    )


def test_trigger_holdoff_commands_series_gating():
    assert trigger_holdoff_commands(1e-6) == [
        ":TRIGger:HOLDoff:RANDom OFF",
        ":TRIGger:HOLDoff 1e-6",
    ]
    assert trigger_holdoff_commands(1e-6, series="4000X") == [
        ":TRIGger:HOLDoff:RANDom OFF",
        ":TRIGger:HOLDoff 1e-6",
    ]
    assert trigger_holdoff_commands(1e-6, series="3000X") == [
        ":TRIGger:HOLDoff 1e-6",
    ]
    assert trigger_holdoff_commands(1e-6, series="2000X") == [
        ":TRIGger:HOLDoff 1e-6",
    ]


@pytest.mark.parametrize(
    ("physical_model_id", "expected"),
    (
        (
            "keysight-dsox4024a",
            [":TRIGger:HOLDoff:RANDom OFF", ":TRIGger:HOLDoff 1e-6"],
        ),
        ("keysight-dsox3024a", [":TRIGger:HOLDoff 1e-6"]),
        ("keysight-dsox2004a", [":TRIGger:HOLDoff 1e-6"]),
    ),
)
def test_trigger_holdoff_series_execution(physical_model_id, expected):
    backend = SimulatorBackend(physical_model_id=physical_model_id)
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.set_trigger_holdoff(1e-6)

    holdoff_writes = [
        command
        for command in backend.history
        if command.startswith(":TRIGger:HOLDoff")
    ]
    assert holdoff_writes == expected


def test_simulator_advanced_state_round_trip():
    backend = SimulatorBackend()
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.set_trigger_holdoff(2e-6)
    assert scope.query_trigger_holdoff() == pytest.approx(2e-6)
    assert ":TRIGger:HOLDoff:RANDom OFF" in backend.history

    scope.configure_cursor(1, 0.0, 1e-3, y1_volts=0.1, y2_volts=0.6)
    cursor = scope.query_cursor()
    assert cursor.mode == "MANUAL"
    assert cursor.x_delta_seconds == pytest.approx(1e-3)
    assert cursor.y_delta_volts == pytest.approx(0.5)

    scope.configure_fft(1, 2, units="vrms", window="flattop", display=True)
    fft = scope.query_fft(1)
    assert fft.source_channel == 2
    assert fft.display is True

def test_simulator_rejects_unit_suffixes_for_advanced_numeric_writes():
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":TRIGger:HOLDoff 1 us")
    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":MARKer:X2Position 1 ms")
    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":MARKer:Y2Position 0.5 V")
