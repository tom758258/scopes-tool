# Generic Sequence Workflow v1

Generic Sequence v1 is a Core-owned finite workflow for running existing
oscilloscope operations in a strict order. The CLI is an adapter; Sequence is
not exposed through the Worker or WebUI.

## Document

Sequence documents are strict JSON:

```json
{
  "version": 1,
  "loop_count": 2,
  "steps": [
    {"action": "single", "parameters": {}},
    {"action": "wait-trigger", "parameters": {"timeout_seconds": 5}},
    {"action": "measure", "parameters": {"item": "vpp", "channel": 1}},
    {"action": "wait", "parameters": {"seconds": 1}}
  ]
}
```

`version` must be the JSON integer `1`. `loop_count` defaults to `1` and must
be a positive JSON integer. Boolean values are not accepted as integers.
`steps` must be non-empty. Unknown document, step, or parameter fields fail
closed, as do unknown actions and non-standard JSON numbers such as `NaN` and
`Infinity`.

## Actions

- `wait`: requires non-negative finite `seconds` and uses the shared
  interruptible host wait.
- `single`: accepts no parameters and starts one single acquisition.
- `wait-trigger`: requires positive finite `timeout_seconds` and waits for an
  acquisition that was already started. It does not send `:SINGle` or force a
  trigger. Use `single` followed by `wait-trigger` for a synchronized
  single-shot flow.
- `measure`: uses the existing `MeasureRequest` fields `item`, `channel`,
  `source_channel`, `reference_channel`, `time_s`, `level`, `slope`, and
  `occurrence` with their existing item-specific rules.
- `capture`: requires `channels`; `points` defaults to `1000`,
  `waveform_format` to `byte`, and `allow_time_axis_tolerance` to `false`.
- `screenshot`: captures the existing cross-series PNG form and accepts an
  optional `background` of `black` or `white`.
- `cleanup`: accepts the existing `minimal` or `safe` profile and directly
  uses Core Safe Cleanup. It does not expand the cleanup safety boundary.

Execution is finite, ordered, single-threaded, and fail-fast. There are no
conditions, variables, retries, parallel or nested steps, arbitrary SCPI,
shell execution, or automatic cleanup.

## Execution And Artifacts

The complete document is validated against the detected model before the run
directory is created. A run writes `manifest.json` and `scpi.log`. Capture and
screenshot files use deterministic loop and step paths, for example:

```text
loop_0001/
  step_0004_capture/
    waveform.csv
    waveform_meta.json
  step_0005_screenshot.png
```

The manifest uses independent `schema_version: 1` and stores normalized input,
completed execution records, files, failure details, and terminal status. The
one-shot result remains bounded by returning one summary per document step;
the manifest holds the repeated execution history.

Cooperative cancellation is checked before steps, after persisted successful
steps, at loop boundaries, and during host and trigger polling waits. Completed
steps and artifacts remain valid. `completed` has precedence over a stop
request observed after all finite work; system or step failure has precedence
over cancellation. Cooperative cancellation returns `status: "cancelled"`,
`error: null`, and exit code `130`. `KeyboardInterrupt` returns
`status: "interrupted"` and remains distinct. Cancellation never runs cleanup
unless the document reaches an explicit `cleanup` step.

Reporter callbacks are synchronous and run after the completed step record is
persisted. `WorkflowProgress.completed_count` counts completed step executions,
and `total_count` is `loop_count * step_count`.

The sequence `scpi.log` begins after identity and capability preflight. It is
the Core workflow execution trace, not a complete process or VISA-session log.

## CLI

```powershell
scopes-tool sequence --simulate --file workflow.json --output-dir data\sequence-run
scopes-tool sequence --dry-run --json --file workflow.json
scopes-tool sequence --resource "$env:SCOPES_TOOL_RESOURCE" --file workflow.json
```

Dry-run loads and validates the complete document, opens no VISA resource, and
writes no runtime artifacts. It reports normalized steps, loop and execution
counts, artifact path templates, and a bounded one-pass SCPI plan where the
existing operation planners can provide one safely.
