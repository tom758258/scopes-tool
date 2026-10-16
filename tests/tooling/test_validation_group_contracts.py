"""Guard the explicit Windows PowerShell test ownership rules on every OS."""

import pytest

from tests.tooling._validation_grouping import GROUPS, MODULE_GROUPS, owner_for_windows_case


@pytest.mark.parametrize(
    ("module", "case", "parameters", "expected"),
    [
        ("test_live_script_invocation.py", "test_invoke_cli_raw_preserves_native_process_results", {}, "shared"),
        ("test_live_script_validators.py", "test_live_validators_enforce_canonical_target_contract", {"script_name": "live-dvm-check.ps1"}, "shared"),
        ("test_windows_python_boundary.py", "test_selected_python_cli_arguments_json_and_failure", {"transport": "captured"}, "shared"),
        ("test_live_script_controls.py", "test_baseline_wgen_applicability_and_runtime_failure", {}, "keysight"),
        ("test_live_script_dvm_segmented.py", "test_segmented_configuration_readback_recovery", {}, "keysight"),
        ("test_live_script_serial.py", "test_serial_lister_export_waits_for_fresh_acquisition", {}, "keysight"),
        ("test_live_tektronix_script.py", "test_default_case_flow_with_fake_cli", {}, "tektronix"),
        ("test_live_workflow_script.py", "test_workflow_clean_baseline_preserves_history", {}, "tektronix"),
        ("test_live_trigger_validation.py", "test_tektronix_special_triggers_execute_from_edge_and_restore", {}, "tektronix"),
        ("test_live_trigger_validation.py", "test_keysight_edge_final_state_and_restore", {}, "keysight"),
        ("test_live_autoscale_script.py", "test_registered_model_transport_flow_and_restore", {"target": "tektronix-tbs2074"}, "tektronix"),
        ("test_live_autoscale_script.py", "test_registered_model_transport_flow_and_restore", {"target": "keysight-dsox4024a"}, "keysight"),
        ("test_live_autoscale_script.py", "test_tektronix_native_error_is_failure_without_restore", {}, "tektronix"),
        ("test_live_autoscale_script.py", "test_confirmation_fails_closed_before_status_or_state_changes", {}, "keysight"),
    ],
)
def test_windows_validation_case_ownership(module, case, parameters, expected):
    assert owner_for_windows_case(module, case, parameters) == expected


def test_windows_validation_group_names_and_unknown_cases_fail_closed():
    assert GROUPS == ("shared", "keysight", "tektronix")
    assert set(MODULE_GROUPS.values()) == set(GROUPS)
    with pytest.raises(ValueError, match="Unowned"):
        owner_for_windows_case("test_live_new_script.py", "test_unclassified")
    with pytest.raises(ValueError, match="Unclassified"):
        owner_for_windows_case("test_live_trigger_validation.py", "test_new_trigger_case")
    with pytest.raises(ValueError, match="Unknown autoscale target"):
        owner_for_windows_case("test_live_autoscale_script.py", "test_new_case", {"target": "unknown-scope"})
