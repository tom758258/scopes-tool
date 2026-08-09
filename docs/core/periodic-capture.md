# Periodic Capture v1

## Purpose And Mapping

Periodic Capture is the product-facing name for the existing fixed-purpose,
finite, time-driven waveform capture workflow. It does not introduce another
runtime surface:

```text
Periodic Capture
  -> CLI / Worker command: capture-batch
  -> Core request: CaptureBatchRequest
  -> Core operation: run_capture_batch()
```

There is no `periodic-capture` command, alias, request type, Core runner, or
second capture loop.

## Request Fields

The existing machine-facing fields map to the normalized Core request as
follows:

| CLI / Worker field | Core field | Availability |
| --- | --- | --- |
| `channel` | `channels` | CLI and Worker |
| `points` | `points` | CLI and Worker |
| `format` | `waveform_format` | CLI and Worker |
| `count` | `requested_count` | CLI and Worker |
| `interval_seconds` | `interval_seconds` | CLI and Worker |
| `output_dir` | `output_dir` | Direct CLI only; the Worker injects its job directory |
| `log_scpi` | `log_scpi` | Direct CLI only |

`count` is a required positive integer. `interval_seconds` defaults to zero
and must be finite and non-negative. Existing channel, point-count, and BYTE or
WORD format validation remains model-dependent.

## Execution And Timing

Each iteration captures the selected waveform data, writes its CSV and
metadata artifacts, records the post-capture system-error result in
`manifest.json`, and then invokes the optional sample and progress reporters.
The next interval begins only after this persistence and reporting boundary.

`interval_seconds` is a relative delay from completion of the previous
capture's persistence and reporting to the start of the next capture. It is
not an absolute wall-clock cadence. A value of zero starts the next capture
immediately after the previous boundary. The workflow stops after exactly
`count` completed attempts unless it fails or is cancelled first.

## Cancellation And Errors

Cancellation is cooperative. Core checks before captures, after persisted and
reported captures, and during interval waits. It does not forcibly interrupt a
blocking VISA or device read. Completed captures and artifacts remain in place.
A stop request observed only after the final capture is complete does not
replace `completed`; terminal precedence remains
`instrument_error > completed > cancelled`.

A post-capture instrument system error is recorded with that capture and stops
the remaining work. Transport, query, write, or persistence errors follow the
existing `capture-batch` error contract and preserve artifacts already written
when possible. Periodic Capture performs no retry.

## Artifacts

The existing `capture-batch` artifact layout is unchanged:

```text
waveform_0001.csv
waveform_0001_meta.json
waveform_0002.csv
waveform_0002_meta.json
...
manifest.json
scpi.log
```

Direct CLI may select `output_dir`. Worker jobs always use the Worker-owned job
artifact directory and do not accept caller-supplied `output_dir` or
`log_scpi` arguments. `scpi.log` is always created; direct CLI `--log-scpi`
also echoes the workflow SCPI log to stderr.

## Dry-Run And Simulation

Direct CLI dry-run validates the selected model and request without opening
VISA or writing artifacts. It reports one representative waveform capture
transaction and all planned artifact paths for the finite count. Simulator
mode runs the complete finite workflow and writes the normal artifacts using
the hardware-free simulator.

## Non-Goals

Periodic Capture v1 does not add duration-based or infinite execution,
trigger or wait-trigger behavior, screenshots, measurements, retries,
conditions, cleanup, state restore, absolute scheduling, cron, plots, nested
workflows, Generic Sequence actions, or WebUI runtime behavior. Triggered
waveform behavior remains outside this workflow.
