"""Single authoritative owner for every hardware-free Windows PowerShell case.

Stage 1: classify tests without changing any parameter sets or test behavior.
Unknown Windows cases fail collection instead of being silently omitted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

GROUPS = ("shared", "keysight", "tektronix")

MODULE_GROUPS = {
    "test_live_script_invocation.py": "shared",
    "test_live_script_validators.py": "shared",
    "test_windows_python_boundary.py": "shared",
    "test_live_script_controls.py": "keysight",
    "test_live_script_artifacts.py": "keysight",
    "test_live_script_dvm_segmented.py": "keysight",
    "test_live_script_serial.py": "keysight",
    "test_live_measurement_validation.py": "keysight",
    "test_preflight_cli_script.py": "keysight",
    "test_live_tektronix_script.py": "tektronix",
    "test_live_workflow_script.py": "tektronix",
}


def owner_for_windows_case(
    module: str, test_name: str, parameters: Mapping[str, object] | None = None,
) -> str:
    """Return the only vendor group for an existing windows_powershell node."""
    module = Path(module).name
    if module == "test_live_trigger_validation.py":
        if test_name.startswith("test_tektronix_"):
            return "tektronix"
        if test_name.startswith("test_keysight_"):
            return "keysight"
        raise ValueError(f"Unclassified trigger case: {test_name}")

    if module == "test_live_autoscale_script.py":
        if test_name.startswith("test_tektronix_"):
            return "tektronix"
        target = (parameters or {}).get("target")
        if target is not None:
            if not isinstance(target, str):
                raise ValueError(f"Unexpected autoscale target: {target!r}")
            if target.startswith("tektronix-"):
                return "tektronix"
            if target.startswith("keysight-"):
                return "keysight"
            raise ValueError(f"Unknown autoscale target: {target}")
        # Other cases use the Keysight representative fixture.
        return "keysight"

    try:
        return MODULE_GROUPS[module]
    except KeyError as error:
        raise ValueError(f"Unowned Windows PowerShell module: {module}") from error
