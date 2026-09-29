import pytest

from scopes_tool_cli import worker
from scopes_tool_core.errors import ParameterValidationError


def _runtime(tmp_path, model="keysight-dsox4024a"):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model=model,
        resource=None,
        queue_max=1,
        output_format="jsonl",
    )


def test_worker_cursor_accepts_partial_position_payload(tmp_path):
    parsed = worker.parse_domain_command(
        "cursor", {"source_channel": 1, "x1": 0.001}, _runtime(tmp_path)
    )

    assert parsed.command == "cursor"
    assert parsed.source_channel == 1
    assert parsed.x1 == 0.001
    assert parsed.x2 is None
    assert parsed.y1 is None
    assert parsed.y2 is None


def test_worker_cursor_rejects_dual_axis_tbs1052b_before_instrument_io(tmp_path):
    with pytest.raises(ParameterValidationError, match="single axis only"):
        worker.parse_domain_command(
            "cursor",
            {"source_channel": 1, "x1": 0.0, "y1": 0.0},
            _runtime(tmp_path, model="tektronix-tbs1052b"),
        )
