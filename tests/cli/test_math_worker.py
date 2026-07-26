import pytest

from scopes_tool_cli import worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path, model="keysight-dsox4024a"):
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


def test_worker_accepts_math_display_request(tmp_path):
    assert "math-display" in worker.DOMAIN_COMMANDS

    parsed = worker.parse_domain_command(
        "math-display",
        {"function": 1, "on": True},
        _runtime(tmp_path, "keysight-dsox2004a"),
    )

    assert parsed.command == "math-display"
    assert parsed.function == 1
    assert parsed.math_display_action == "on"


def test_worker_accepts_math_vertical_request(tmp_path):
    assert "math-vertical" in worker.DOMAIN_COMMANDS

    parsed = worker.parse_domain_command(
        "math-vertical",
        {"function": 2, "scale": 2.0, "offset": 0.5},
        _runtime(tmp_path),
    )

    assert parsed.command == "math-vertical"
    assert parsed.function == 2
    assert parsed.scale == 2.0
    assert parsed.offset == 0.5


def test_worker_rejects_unsupported_math_function_before_enqueue(tmp_path):
    runtime = _runtime(tmp_path, "keysight-dsox2004a")

    with pytest.raises(OscilloscopeError, match="between 1 and 1"):
        worker.parse_domain_command(
            "math-display",
            {"function": 2, "query": True},
            runtime,
        )

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_rejects_oversized_math_vertical_value_before_enqueue(tmp_path):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError, match="finite number"):
        worker.parse_domain_command(
            "math-vertical",
            {"function": 1, "scale": 10**10000},
            runtime,
        )

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_accepts_math_operator_configure_and_query(tmp_path):
    assert "math-operator" in worker.DOMAIN_COMMANDS
    runtime = _runtime(tmp_path)

    configured = worker.parse_domain_command(
        "math-operator",
        {
            "function": 2,
            "operation": "multiply",
            "source1": "math1",
            "source2": "channel2",
        },
        runtime,
    )
    queried = worker.parse_domain_command(
        "math-operator",
        {"function": 2, "query": True},
        runtime,
    )

    assert configured.command == "math-operator"
    assert configured.function == 2
    assert configured.math_operation == "multiply"
    assert configured.source1 == "math1"
    assert configured.source2 == "channel2"
    assert queried.math_operator_query is True


def test_worker_rejects_math_operator_query_conflict_before_enqueue(tmp_path):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError, match="cannot be combined"):
        worker.parse_domain_command(
            "math-operator",
            {
                "function": 1,
                "query": True,
                "operation": "add",
                "source1": "channel1",
                "source2": "channel2",
            },
            runtime,
        )

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_accepts_math_transform_configure_and_query(tmp_path):
    assert "math-transform" in worker.DOMAIN_COMMANDS
    runtime = _runtime(tmp_path)

    configured = worker.parse_domain_command(
        "math-transform",
        {
            "function": 2,
            "operation": "linear",
            "source": "channel1",
            "gain": 2,
            "linear_offset": -1,
        },
        runtime,
    )
    queried = worker.parse_domain_command(
        "math-transform",
        {"function": 2, "query": True},
        runtime,
    )

    assert configured.command == "math-transform"
    assert configured.function == 2
    assert configured.math_transform_operation == "linear"
    assert configured.source == "channel1"
    assert configured.gain == 2.0
    assert configured.linear_offset == -1.0
    assert queried.math_transform_query is True


def test_worker_rejects_math_transform_irrelevant_parameter_before_enqueue(
    tmp_path,
):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError, match="only valid.*integrate"):
        worker.parse_domain_command(
            "math-transform",
            {
                "function": 1,
                "operation": "absolute",
                "source": "channel1",
                "input_offset": 0,
            },
            runtime,
        )

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_accepts_math_composite_source_configure_and_query(tmp_path):
    assert "math-composite-source" in worker.DOMAIN_COMMANDS
    runtime = _runtime(tmp_path, "keysight-dsox2004a")

    configured = worker.parse_domain_command(
        "math-composite-source",
        {
            "operation": "subtract",
            "source1": "channel1",
            "source2": "channel2",
        },
        runtime,
    )
    queried = worker.parse_domain_command(
        "math-composite-source",
        {"query": True},
        runtime,
    )

    assert configured.command == "math-composite-source"
    assert configured.math_composite_operation == "subtract"
    assert configured.source1 == "channel1"
    assert configured.source2 == "channel2"
    assert queried.math_composite_query is True


def test_worker_rejects_invalid_math_composite_source_before_enqueue(tmp_path):
    runtime = _runtime(tmp_path, "keysight-dsox2004a")

    with pytest.raises(OscilloscopeError, match="add, subtract, or multiply"):
        worker.parse_domain_command(
            "math-composite-source",
            {
                "operation": "divide",
                "source1": "channel1",
                "source2": "channel2",
            },
            runtime,
        )

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()
