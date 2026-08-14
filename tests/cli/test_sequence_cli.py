import json

from scopes_tool_cli import cli, runtime


def _write_sequence(path, *, loop_count=1, steps=None):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "loop_count": loop_count,
                "steps": steps
                or [{"action": "wait", "parameters": {"seconds": 0}}],
            }
        ),
        encoding="utf-8",
    )


def test_sequence_cli_executes_json_file_in_simulation(tmp_path, capsys):
    document = tmp_path / "workflow.json"
    output_dir = tmp_path / "run"
    _write_sequence(document, loop_count=2)

    code = cli.main(
        [
            "sequence",
            "--simulate",
            "--file",
            str(document),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert code == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["completed_step_executions"] == 2
    assert (output_dir / "scpi.log").exists()
    assert "Sequence status: completed" in capsys.readouterr().out


def test_sequence_dry_run_validates_without_opening_scope_or_writing_artifacts(
    monkeypatch, tmp_path, capsys
):
    document = tmp_path / "workflow.json"
    output_dir = tmp_path / "planned"
    _write_sequence(
        document,
        loop_count=3,
        steps=[
            {"action": "single", "parameters": {}},
            {"action": "wait-trigger", "parameters": {"timeout_seconds": 1}},
        ],
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("opened"))),
    )

    code = cli.main(
        [
            "sequence",
            "--dry-run",
            "--file",
            str(document),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert code == 0
    assert not output_dir.exists()
    output = capsys.readouterr().out
    assert "Planned sequence: 3 loop(s), 2 step(s), 6 execution(s)" in output
    assert output.count("Command: :SINGle") == 1


def test_sequence_invalid_document_fails_before_scope_open(monkeypatch, tmp_path, capsys):
    document = tmp_path / "invalid.json"
    document.write_text(
        '{"version":1,"steps":[{"action":"single","parameters":{},"extra":true}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("opened"))),
    )

    code = cli.main(
        [
            "sequence",
            "--resource",
            "USB0::FAKE::INSTR",
            "--file",
            str(document),
        ]
    )

    assert code == 1
    assert "unknown field" in capsys.readouterr().err


def test_sequence_json_uses_one_shot_envelope(tmp_path, capsys):
    document = tmp_path / "workflow.json"
    output_dir = tmp_path / "json-run"
    _write_sequence(document)

    code = cli.main(
        [
            "sequence",
            "--simulate",
            "--json",
            "--file",
            str(document),
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["schema_version"] == 2
    assert payload["command"] == "sequence"
    assert payload["ok"] is True
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["completed_step_executions"] == 1
    assert payload["error"] is None
    assert any(item["kind"] == "manifest" for item in payload["files"])
