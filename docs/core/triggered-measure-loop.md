# Triggered Measurement Loop v1

Triggered Measurement Loop is a fixed-purpose finite Core workflow. Each cycle
starts `Single`, waits for the current acquisition through the existing
Operation Status Condition Run-bit path, queries the selected measurements,
persists the completed cycle, and optionally waits before starting the next
cycle. It uses the trigger configuration already present on the oscilloscope.

The request fields are `channels`, `items`, `pairs`, `pair_items`, `count`,
`trigger_timeout_seconds`, `interval_seconds`, and `output_dir`, plus the
existing `log_scpi` execution option. `count` and `trigger_timeout_seconds` are
required. Count must be at least one, trigger timeout must be positive and
finite, and interval defaults to zero and must be non-negative and finite.
Measurement selection and defaults match `measure-log`: omitted channels select
the existing default channel set, items default to `vpp,frequency`, pairs
default to none, and pair items default to `phase,delay`.

For every completed cycle, Core writes one CSV row, updates `manifest.json`,
and then invokes the sample and progress reporters. The interval begins only
after that persistence and reporting boundary. `WorkflowProgress.total_count`
is the requested count. A normal invalid measurement response or sentinel is
stored as `NaN` and does not fail the cycle. Query, transport, parsing, or
instrument system errors fail immediately.

A trigger timeout fails the workflow without forcing a trigger, retrying, or
starting another cycle. Cancellation is cooperative at safe boundaries and
does not forcibly interrupt a VISA read. Previously completed cycles remain
valid for timeout, failure, cancellation, or interruption.

Runtime output uses one directory, normally
`data/triggered_measure_loops/<timestamp>/`, containing:

- `measurements.csv`, with `index`, `timestamp_iso`, `elapsed_seconds`,
  `trigger_elapsed_seconds`, and measurement columns such as `ch1_vpp` and
  `ch1_ch2_phase`;
- `manifest.json`, with the request, completed cycle summaries, files, and a
  compact terminal error when applicable;
- `scpi.log`, covering SCPI issued inside the Core workflow.

Dry-run validates the request and selected model profile without opening VISA
or writing artifacts. It reports the finite requested count and one
representative cycle: `:SINGle`, `:OPERegister:CONDition?`, the selected
measurement queries, and one `:SYSTem:ERRor?`.

The workflow does not configure triggers, capture waveforms or screenshots,
run cleanup, force triggers, retry, or expand Generic Sequence v1.
