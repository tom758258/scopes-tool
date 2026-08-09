# Scopes Orchestrator Workflows

Common schema version: `2`

Compatibility policy: `v2-only`

Implementation status: `Common v2-only conformant`

This document gives Scopes-specific workflows for agents that drive the
Keysight oscilloscope CLI and worker. Shared lifecycle ordering is defined in
[Common Orchestrator Workflows](common-orchestrator-workflows.md). Shared event
envelope rules are defined in
[Common CLI JSON / JSONL Contract](common-cli-jsonl-contract.md). Worker
behavior is defined in [Scopes Worker Contract](scopes-worker-contract.md).

## Common v2 Compatibility

The current Scopes implementation supports Common schema 2 only. Send exact
integer `schema_version: 2`; do not send schema 1, use fallback, or perform
version negotiation. Malformed or non-v2 runtime boundaries fail closed.

## Periodic Capture Mapping

Periodic Capture is the product-facing workflow name. Both direct CLI and
Worker automation continue to use the machine-facing command `capture-batch`,
which delegates to the existing Core `CaptureBatchRequest` and
`run_capture_batch()` operation. There is no `periodic-capture` command or
alias.

Submit a Worker job with the existing schema 2 envelope:

```json
{
  "schema_version": 2,
  "command": "capture-batch",
  "arguments": {
    "channel": [1],
    "points": 1000,
    "format": "byte",
    "count": 10,
    "interval_seconds": 3
  }
}
```

The Worker owns the job artifact directory. Orchestrators must not send
`output_dir` or `log_scpi` for `capture-batch`.

## Worker Workflow

Scopes is a queued-job Worker with a startup-bound execution context. Live
startup `--model` maps to `expected_model_id`; simulate startup `--model` maps
to `planning_model_id`; detected live identity remains authoritative. Scopes
`/command` does not carry request-level `context`, because mode, model, and
resource are fixed at Worker startup. A top-level `context` field is not
allowed, and command arguments cannot override startup mode, model, or
resource.

Start a worker in simulator mode:

```text
scopes-tool worker --simulate --model keysight-dsox4024a --port 8765 --format jsonl
```

For live mode, require an operator-selected resource:

```text
scopes-tool worker --live --resource USB0::...::INSTR --model keysight-dsox4024a --port 8765 --format jsonl
```

Wait for the Common control-plane readiness signal: read the worker stdout
JSONL `ready` event or poll `GET /status` until a valid status response is
reachable. The Scopes CLI helper for polling is:

```text
scopes-tool wait-ready --port 8765 --json
```

After readiness, submit Scopes domain work with the Common `/command` envelope
through `scopes-tool send-command`:

```text
scopes-tool send-command --port 8765 --command identify --arguments-json "{}" --json
scopes-tool send-command --port 8765 --command capture --arguments-json "{\"channel\":[1],\"points\":1000}" --json
scopes-tool send-command --port 8765 --command capture --arguments-json "{\"channel\":[1],\"points\":1000,\"wait_trigger\":true,\"trigger_timeout_ms\":5000,\"trigger_poll_interval_ms\":100}" --json
scopes-tool send-command --port 8765 --command sample-rate --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command sample-rate --arguments-json "{\"query\":true,\"maximum\":true}" --json
scopes-tool send-command --port 8765 --command acquisition-points --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command record-length --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command segmented-memory --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command force-trigger --arguments-json "{}" --json
scopes-tool send-command --port 8765 --command dvm-enable --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command dvm-source --arguments-json "{\"channel\":1}" --json
scopes-tool send-command --port 8765 --command dvm-mode --arguments-json "{\"mode\":\"dc-rms\"}" --json
scopes-tool send-command --port 8765 --command dvm-auto-range --arguments-json "{\"enabled\":true}" --json
scopes-tool send-command --port 8765 --command dvm-current --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command dvm-query --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command demo-query --arguments-json "{}" --json
scopes-tool send-command --port 8765 --command demo-output --arguments-json "{\"enabled\":true}" --json
scopes-tool send-command --port 8765 --command demo-function --arguments-json "{\"function\":\"runt\"}" --json
scopes-tool send-command --port 8765 --command demo-phase --arguments-json "{\"degrees\":90}" --json
scopes-tool send-command --port 8765 --command wgen-query --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command wgen-output --arguments-json "{\"enabled\":true}" --json
scopes-tool send-command --port 8765 --command wgen-function --arguments-json "{\"function\":\"sine\"}" --json
scopes-tool send-command --port 8765 --command wgen-frequency --arguments-json "{\"hz\":1000}" --json
scopes-tool send-command --port 8765 --command wgen-voltage --arguments-json "{\"amplitude\":0.5}" --json
scopes-tool send-command --port 8765 --command wgen-offset --arguments-json "{\"volts\":0}" --json
scopes-tool send-command --port 8765 --command wgen-load --arguments-json "{\"load\":\"one-meg\"}" --json
scopes-tool send-command --port 8765 --command search-state --arguments-json "{\"enabled\":true}" --json
scopes-tool send-command --port 8765 --command search-mode --arguments-json "{\"mode\":\"edge\"}" --json
scopes-tool send-command --port 8765 --command search-count --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-edge --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-edge --arguments-json "{\"source_channel\":1,\"level\":0.5,\"slope\":\"positive\"}" --json
scopes-tool send-command --port 8765 --command trigger-sweep --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-sweep --arguments-json "{\"mode\":\"normal\"}" --json
scopes-tool send-command --port 8765 --command trigger-noise-reject --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-noise-reject --arguments-json "{\"enabled\":false}" --json
scopes-tool send-command --port 8765 --command trigger-hf-reject --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-hf-reject --arguments-json "{\"enabled\":true}" --json
scopes-tool send-command --port 8765 --command trigger-pulse-width --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-pulse-width --arguments-json "{\"channel\":1,\"polarity\":\"positive\",\"qualifier\":\"less_than\",\"time_seconds\":0.000001}" --json
scopes-tool send-command --port 8765 --command trigger-runt --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-runt --arguments-json "{\"channel\":1,\"polarity\":\"either\",\"qualifier\":\"none\",\"low_level_volts\":-0.5,\"high_level_volts\":0.5}" --json
scopes-tool send-command --port 8765 --command trigger-transition --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-transition --arguments-json "{\"channel\":1,\"slope\":\"positive\",\"qualifier\":\"greater_than\",\"time_seconds\":0.000005,\"low_level_volts\":-0.5,\"high_level_volts\":0.5}" --json
scopes-tool send-command --port 8765 --command trigger-delay --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-delay --arguments-json "{\"arm_channel\":1,\"arm_slope\":\"positive\",\"trigger_channel\":2,\"trigger_slope\":\"negative\",\"time_seconds\":0.000001,\"count\":2}" --json
scopes-tool send-command --port 8765 --command trigger-edge-burst --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-edge-burst --arguments-json "{\"source_channel\":1,\"slope\":\"positive\",\"count\":3,\"idle_time\":0.000001}" --json
scopes-tool send-command --port 8765 --command trigger-tv --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-tv --arguments-json "{\"source_channel\":1,\"standard\":\"ntsc\",\"mode\":\"line-field1\",\"line\":20,\"polarity\":\"negative\"}" --json
scopes-tool send-command --port 8765 --command trigger-pattern --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-pattern --arguments-json "{\"pattern\":\"XXX1\"}" --json
scopes-tool send-command --port 8765 --command trigger-or --arguments-json "{\"query\":true}" --json
scopes-tool send-command --port 8765 --command trigger-or --arguments-json "{\"pattern\":\"XXXR\"}" --json
scopes-tool send-command --port 8765 --command channel-impedance --arguments-json "{\"channel\":1,\"impedance\":\"one-meg\"}" --json
scopes-tool send-command --port 8765 --command channel-impedance --arguments-json "{\"channel\":1,\"impedance\":\"fifty\",\"allow_50_ohm\":true}" --json
scopes-tool send-command --port 8765 --command channel-range --arguments-json "{\"channel\":1,\"volts_full_scale\":4}" --json
scopes-tool send-command --port 8765 --command channel-vernier --arguments-json "{\"channel\":1,\"off\":true}" --json
```

The accepted response only means the Common envelope was accepted and the
Scopes job was enqueued. It is not command success, trigger success, or query
success. Poll status or read the job artifact:

```text
scopes-tool status --port 8765 --json
```

Then read `data/worker/<run_id>/<worker_job_id>/result.json`. Use
`result.json` state, `ok`, `exit_code`, `error`, and command artifact files for
pass/fail decisions.

For `capture` jobs with `wait_trigger`, use
`result.json.result.trigger.outcome` and `capture_allowed` to distinguish
natural trigger completion, forced trigger completion, timeout, and unknown
poll state. `timeout` and `unknown` outcomes do not produce capture artifacts.

Use cooperative cleanup:

```text
scopes-tool stop --port 8765 --json
```

## Subprocess Example

This simulator example treats worker stdout events and terminal artifacts as
the source of truth. It does not rely on the subprocess return code alone.

```python
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


events = queue.Queue()
event_backlog = []
ready = None
summary = None
workflow_error = None
stderr_lines = []
worker = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "scopes_tool_cli.cli",
        "worker",
        "--simulate",
        "--model",
        "keysight-dsox4024a",
        "--port",
        "8765",
        "--format",
        "jsonl",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)


def read_stdout():
    assert worker.stdout is not None
    for line in worker.stdout:
        events.put(json.loads(line))


def read_stderr():
    assert worker.stderr is not None
    for line in worker.stderr:
        stderr_lines.append(line.rstrip())


threading.Thread(target=read_stdout, daemon=True).start()
threading.Thread(target=read_stderr, daemon=True).start()


def wait_event(name, *, predicate=None, timeout=10):
    deadline = time.monotonic() + timeout

    while True:
        for index, event in enumerate(event_backlog):
            if event.get("event") != name:
                continue
            if predicate is not None and not predicate(event):
                continue
            return event_backlog.pop(index)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(name)

        try:
            event = events.get(timeout=min(0.2, remaining))
        except queue.Empty:
            continue

        if event.get("event") == name and (
            predicate is None or predicate(event)
        ):
            return event

        event_backlog.append(event)


try:
    ready = wait_event("ready")
    assert ready["event"] == "ready"
    assert ready["schema_version"] == 2
    assert ready["service"] == "scopes-tool"
    assert ready["run_id"]
    assert ready["host"] == "127.0.0.1"
    assert ready["port"] == 8765
    assert ready["mode"] == "simulate"
    assert ready["model"] == "keysight-dsox4024a"
    assert ready["resource"] is None
    assert ready["command_url"].endswith("/command")
    assert ready["status_url"].endswith("/status")
    assert ready["stop_url"].endswith("/stop")
    assert "trigger_url" not in ready

    wait_ready = subprocess.run(
        [
            sys.executable,
            "-m",
            "scopes_tool_cli.cli",
            "wait-ready",
            "--port",
            "8765",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    wait_payload = json.loads(wait_ready.stdout)
    assert wait_ready.returncode == 0
    assert wait_payload["run_id"] == ready["run_id"]
    assert wait_payload["service"] == "scopes-tool"
    assert wait_payload["mode"] == ready["mode"]
    assert wait_payload["model"] == ready["model"]
    assert wait_payload["resource"] == ready["resource"]
    assert wait_payload["urls"]["command_url"] == ready["command_url"]
    assert wait_payload["urls"]["status_url"] == ready["status_url"]
    assert wait_payload["urls"]["stop_url"] == ready["stop_url"]
    assert "command_url" not in wait_payload
    assert "status_url" not in wait_payload
    assert "stop_url" not in wait_payload
    assert "trigger_url" not in wait_payload
    assert "trigger_url" not in wait_payload["urls"]

    client_job_id = "client-job-1"
    send = subprocess.run(
        [
            sys.executable,
            "-m",
            "scopes_tool_cli.cli",
            "send-command",
            "--port",
            "8765",
            "--command",
            "identify",
            "--arguments-json",
            "{}",
            "--job-id",
            client_job_id,
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    accepted = json.loads(send.stdout)
    assert send.returncode == 0
    assert accepted["status"] == "accepted"
    assert accepted["command"] == "identify"
    assert accepted["job_id"] == client_job_id
    assert accepted["worker_job_id"]
    assert accepted["artifact_path"]

    worker_job_id = accepted["worker_job_id"]

    started = wait_event(
        "job_started",
        predicate=lambda event: event.get("worker_job_id") == worker_job_id,
    )
    assert started["worker_job_id"] == worker_job_id
    assert started["job_id"] == client_job_id
    assert started["command"] == "identify"

    finished = wait_event(
        "job_finished",
        predicate=lambda event: event.get("worker_job_id") == worker_job_id,
    )
    assert finished["worker_job_id"] == worker_job_id
    assert finished["job_id"] == client_job_id
    assert finished["command"] == "identify"

    artifact_path = Path(accepted["artifact_path"])
    request_payload = json.loads((artifact_path / "request.json").read_text())
    result_payload = json.loads((artifact_path / "result.json").read_text())
    assert request_payload["job_id"] == client_job_id
    assert request_payload["command"] == "identify"
    assert result_payload["run_id"] == ready["run_id"]
    assert result_payload["worker_job_id"] == worker_job_id
    assert result_payload["job_id"] == client_job_id
    assert result_payload["command"] == "identify"
    assert result_payload["state"] == "succeeded"
    assert result_payload["ok"] is True
    assert result_payload["exit_code"] == 0
    assert finished["result_path"] == str(artifact_path / "result.json")
except Exception as exc:
    workflow_error = exc
finally:
    stop = subprocess.run(
        [
            sys.executable,
            "-m",
            "scopes_tool_cli.cli",
            "stop",
            "--port",
            "8765",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if stop.stdout:
        json.loads(stop.stdout)
    if ready is not None:
        try:
            summary = wait_event(
                "summary",
                predicate=lambda event: event.get("run_id") == ready["run_id"],
                timeout=10,
            )
        except TimeoutError:
            pass
    try:
        worker.wait(timeout=10)
    except subprocess.TimeoutExpired:
        worker.terminate()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=5)

workflow_failed = (
    workflow_error is not None
    or ready is None
    or summary is None
    or summary.get("event") != "summary"
    or summary.get("run_id") != ready["run_id"]
    or summary.get("ok") is not True
    or summary.get("failed") != 0
    or summary.get("cancelled") != 0
    or worker.returncode != 0
)
if workflow_failed:
    raise RuntimeError(
        "worker workflow failed: "
        f"error={workflow_error!r} "
        f"summary={summary} "
        f"worker.returncode={worker.returncode} "
        f"stderr_tail={stderr_lines[-20:]}"
    )
```

If a process is force-terminated, it may not write terminal `result.json`,
`job_finished`, or final `summary`. Treat missing terminal artifacts or missing
summary as incomplete or failed.

## One-Shot JSON Helper

The CLI still supports single-response JSON for one-shot work:

```python
import json
import subprocess


def run_scope_json(args):
    proc = subprocess.run(
        ["python", "-m", "scopes_tool_cli.cli", *args, "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(proc.stdout)
    if proc.returncode != 0 or not payload.get("ok", False):
        raise RuntimeError(
            f"scope command failed: rc={proc.returncode} payload={payload}"
        )
    return payload
```

If `--log-scpi` is used, parse stdout only. Stderr is diagnostic text.

## Simulator Workflow

Use simulator mode before any live workflow:

```python
from pathlib import Path

payload = run_scope_json([
    "capture",
    "--simulate",
    "--model", "keysight-dsox4024a",
    "--simulate-preset", "phase-shifted-pair",
    "--channel", "1",
    "--channel", "2",
    "--csv", ".tmp_tests/preset.csv",
])

for item in payload["files"]:
    assert Path(item["path"]).exists()
```

For finite workflow validation:

```python
payload = run_scope_json([
    "acquisition-check",
    "--simulate",
    "--model", "keysight-dsox4034a",
    "--output-dir", ".tmp_tests/acquisition_check",
])
assert payload["result"]["status"] == "completed"
```

## Live Capture Workflow

Live workflows must use an explicit operator-selected resource. For a one-shot
command, `--resource <RESOURCE>` selects and opts in to that single instrument;
the optional `--live` flag is retained for compatibility. Live worker startup
still requires `--live --resource <RESOURCE>`.

1. Optionally run `identify --resource <RESOURCE> --json`.
2. Optionally save setup with `setup-save --resource <RESOURCE> --slot N --json`.
3. Start a live worker with that same resource, or run a one-shot command with
   explicit artifact paths.
4. Require accepted worker jobs to reach terminal `result.json` with
   `ok: true`, or require one-shot JSON `ok: true`.
5. Restore state explicitly when setup-changing commands were used.
6. Run `check-error --resource <RESOURCE> --json` when a final error
   queue check is required.

Do not scan or rotate resources during the live workflow. If discovery is
needed, run `list-resources` as a separate operator-approved step before
selecting the resource.

## Cleanup Rule

Prefer `scopes-tool stop` for worker cleanup. Queued jobs become
`cancelled`; running jobs stop at cooperative checkpoints. If a blocking device
operation is still in progress, process termination may be required after the
operator-defined timeout.

Restore instrument state explicitly when setup-changing commands were used:
`setup-recall`, `acquisition-check --restore-type`, or the documented inverse
configuration command.
