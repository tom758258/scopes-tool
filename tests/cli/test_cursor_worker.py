from scopes_tool_cli import worker


def _runtime(tmp_path):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model="keysight-dsox4024a",
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
