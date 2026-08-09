# Measure Until Condition v1

## Purpose

Measure Until Condition is a fixed-purpose, finite, read-only measurement
workflow. It repeatedly queries one existing single-channel measurement until
the numeric condition matches or the workflow timeout expires.

```text
Product name: Measure Until Condition
CLI / Worker command: measure-until
Core request: MeasureUntilRequest
Core planner: plan_measure_until()
Core runner: run_measure_until()
```

The workflow observes the oscilloscope's current acquisition state. It does
not configure, start, stop, force, or wait for a trigger.

## Request

| Field | Requirement |
|---|---|
| `channel` | Required single analog channel. `all`, arrays, digital channels, and aggregation are not supported. |
| `item` | Required existing non-parameterized single-channel measurement item. Pair and parameterized items are rejected. |
| `operator` | Required: `gt`, `gte`, `lt`, or `lte`. |
| `threshold` | Required finite number in the selected measurement's native unit. |
| `timeout_seconds` | Required positive finite workflow timeout. |
| `interval_seconds` | Optional non-negative finite relative delay; default `1.0`. |
| `output_dir` | Direct CLI only; defaults to `data/measure_until/<timestamp>/`. |
| `log_scpi` | Direct CLI execution option using the normal workflow SCPI log behavior. |

The operators mean `value > threshold`, `value >= threshold`,
`value < threshold`, and `value <= threshold`, respectively. No unit
conversion is performed.

## Execution and timeout boundary

Each iteration is:

```text
check cancellation
-> check timeout
-> query measurement
-> query :SYSTem:ERRor?
-> evaluate condition
-> persist CSV row
-> update manifest
-> report sample and progress
-> complete if matched, otherwise wait interval_seconds
```

The timeout controls whether another measurement query may start. A blocking
VISA/device read that started before the deadline is not forcibly interrupted.
When it returns, the workflow finishes the system-error check, comparison, and
persistence. A committed matching sample completes successfully even if the
deadline passed during that read. A committed non-matching sample is followed
by `condition_timeout` at the next safe boundary. Interval waits are capped by
the remaining timeout.

`interval_seconds` is a relative delay after the preceding sample and manifest
have been persisted and reporters have run. It is not an absolute cadence.

## Persistence and terminal behavior

A sample increases `completed_count` only after its CSV row and updated
manifest are persisted. Sample and progress reporters run after that commit.
If a later failure occurs, previously committed samples remain valid. A CSV row
that was written before a manifest write failure may remain for diagnostics,
but it is not counted as completed.

A valid matching sample returns `status: "completed"`, `matched: true`,
`termination_reason: "condition_met"`, and exit code `0`. The compact
`matched_sample` records its index, value, and elapsed time. A cancellation
observed only after that commit does not replace the completed result.

If the condition is not met before the finite timeout, the workflow returns
`status: "error"`, `matched: false`,
`termination_reason: "condition_timeout"`, exit code `1`, and a compact error
whose type is `condition_timeout`. Cancellation, interruption, transport,
query, parsing, persistence, and instrument system errors use the existing
workflow status/error contracts.

A normal invalid measurement sentinel is persisted as `NaN`, evaluates as
non-matching, and does not fail the workflow. Genuine measurement parsing,
query, transport, persistence, or instrument system errors stop immediately.

## Artifacts

```text
data/measure_until/<timestamp>/
  measurements.csv
  manifest.json
  scpi.log
```

The CSV columns are:

```text
index,timestamp_iso,elapsed_seconds,value,matched
```

The schema 1 manifest contains the fixed request, runtime identity, compact
completion and matching summary, terminal state, artifact paths, and error. It
does not duplicate the full sample series; measurement values remain in CSV.

## Dry-run, simulator, and Worker

Dry-run validates the selected model profile and request without opening VISA
or writing artifacts. It reports the finite timeout and interval and shows one
representative iteration: the selected measurement query and one
`:SYSTem:ERRor?`. It does not expand runtime polling.

Simulator mode runs the actual finite Core workflow and writes normal
artifacts. Common v2 Worker accepts only `channel`, `item`, `operator`,
`threshold`, `timeout_seconds`, and optional `interval_seconds`. The Worker
rejects `output_dir` and `log_scpi` and injects its owned job artifact
directory. Core completion maps to Worker success, Core cancellation to Worker
cancellation, and timeout or other Core failures to Worker failure.

## v1 non-goals

v1 does not provide multiple channels or conditions, AND/OR aggregation,
pair or parameterized measurements, equality/tolerance/hysteresis/debounce,
retry, trigger or acquisition control, waveform capture, screenshots, actions,
Generic Sequence integration, nested workflows, count or infinite execution,
absolute scheduling, cron, plots, WebUI runtime, or new hardware support.
