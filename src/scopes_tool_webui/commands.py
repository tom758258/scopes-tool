"""WebUI command compatibility façade."""

from __future__ import annotations

from .command_catalog import (
    COMMANDS,
    TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS,
    _COMMAND_BY_ID,
    _COMMAND_FIELDS,
    _TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS,
    command_catalog,
    model_catalog,
)
from .command_execution import (
    ScopeSessionCloseError,
    _capture_batch_request,
    _execute_dry_run,
    _execute_trigger_search_serial_segmented_workflow_command,
    _execute_scope_command,
    _jsonable,
    _measure_log_request,
    _measure_request,
    _measure_until_request,
    _operation_payload,
    _run_config,
    _simple_scope_result,
    _state_scope_result,
    _triggered_capture_series_request,
    _triggered_measure_loop_request,
    execute_command,
)
from .command_validation import (
    DEFAULT_MODEL_ID,
    WebUIRequestError,
    _segmented_capture_request,
    _validate_parameters,
    validate_job_request,
)

__all__ = [
    "COMMANDS",
    "TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS",
    "_COMMAND_BY_ID",
    "_COMMAND_FIELDS",
    "_TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS",
    "command_catalog",
    "model_catalog",
    "DEFAULT_MODEL_ID",
    "WebUIRequestError",
    "validate_job_request",
    "_segmented_capture_request",
    "_validate_parameters",
    "ScopeSessionCloseError",
    "execute_command",
    "_execute_dry_run",
    "_execute_scope_command",
    "_execute_trigger_search_serial_segmented_workflow_command",
    "_run_config",
    "_operation_payload",
    "_state_scope_result",
    "_simple_scope_result",
    "_measure_request",
    "_capture_batch_request",
    "_measure_log_request",
    "_measure_until_request",
    "_triggered_measure_loop_request",
    "_triggered_capture_series_request",
    "_jsonable",
]
