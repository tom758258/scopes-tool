"""Shared WorkerRuntime setup for CLI worker tests."""

from scopes_tool_cli import worker


def make_worker_runtime(
    *,
    model="keysight-dsox4024a",
    mode="simulate",
    resource=None,
    queue_max=1,
):
    """Return a WorkerRuntime with the settings the CLI worker tests share."""

    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode=mode,
        model=model,
        resource=resource,
        queue_max=queue_max,
        output_format="jsonl",
    )
