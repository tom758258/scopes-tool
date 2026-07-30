from scopes_tool_cli import cli, worker


def _runtime(tmp_path):
    return worker.WorkerRuntime(
        "127.0.0.1",
        0,
        "simulate",
        "keysight-dsox4034a",
        None,
        tmp_path,
        1,
        "jsonl",
    )


def test_channel_summary_worker_reuses_query_only_cli_path(tmp_path):
    accepted = worker.validate_command_request(
        {"command": "channel-summary", "arguments": {}}
    )

    assert accepted[:2] == ("channel-summary", {})
    parsed = worker.parse_domain_command(accepted[0], accepted[1], _runtime(tmp_path))
    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert len(payload["result"]["channels"]) == 4
    assert payload["scpi"]["sent"][0] == "*IDN?"
    assert all(command.endswith("?") for command in payload["scpi"]["sent"])
