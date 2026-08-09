# Triggered Capture Series v1

## Purpose

Triggered Capture Series is a fixed-purpose finite Core workflow for acquiring
waveforms after natural trigger completion. It uses the trigger configuration
already present on the oscilloscope and does not configure, replace, restore,
or force trigger settings.

The public mapping is:

```text
Triggered Capture Series
  -> CLI / Worker command: triggered-capture-series
  -> Core request: TriggeredCaptureSeriesRequest
  -> Core planner: plan_triggered_capture_series()
  -> Core runner: run_triggered_capture_series()
```

## Request And CLI Fields

The Core request fields are `channels`, `points`, `waveform_format`, `count`,
`trigger_timeout_seconds`, `interval_seconds`, `output_dir`, and `log_scpi`.
CLI uses `--channel`, `--points`, `--format`, `--count`,
`--trigger-timeout-seconds`, `--interval-seconds`, `--output-dir`, and the
common `--log-scpi` option.

Channels are required and follow existing waveform capture semantics,
including repeatable ordered channels and the single value `all`. Points
default to `1000`; format defaults to BYTE. Count is a required positive
integer. Trigger timeout is required, positive, finite, and applies separately
to every cycle. Interval defaults to zero and must be finite and non-negative.

## Execution Order

Each cycle performs:

```text
check cancellation
-> :SINGle
-> wait for the current trigger/acquisition completion
-> capture the requested waveform channels
-> write waveform CSV and metadata
-> query :SYSTem:ERRor?
-> commit the cycle to manifest.json
-> report sample and progress
-> optionally wait interval_seconds
```

The trigger wait uses the same current-acquisition Operation Status Condition
classifier and cooperative polling path as Triggered Measurement Loop. It does
not retry or send `:TRIGger:FORCe`. Waveform acquisition, BYTE/WORD scaling,
multi-channel alignment, and files use the existing capture implementation.

`interval_seconds` is a relative wait that begins after persistence and
reporting complete. It is not an absolute wall-clock cadence.

## Persistence And Completion Boundary

A cycle increases `completed_count` only after natural trigger completion,
successful waveform capture, successful CSV and metadata writes, a successful
post-capture system-error check, and a successful manifest update. Sample and
progress reporters run only after that commit.

If the system-error check reports an instrument error, waveform files already
written may remain for diagnostics, but the failing cycle is omitted from
`cycles` and does not increase `completed_count`. Earlier committed cycles
remain valid after later cancellation, timeout, interruption, transport,
query, persistence, or instrument errors.

## Cancellation And Errors

Cancellation is cooperative before cycles, during trigger polling, after
committed cycles, and during interval waits. Cancellation during trigger wait
does not capture that cycle. Blocking VISA or device reads are not forcibly
interrupted. A stop observed after the requested final cycle is committed does
not replace `completed`.

A trigger timeout returns `error`, records the cycle index and elapsed trigger
wait, and stops without retry, force trigger, or another cycle. Instrument
system errors return `instrument_error`; other runtime failures return `error`.
`KeyboardInterrupt` returns `interrupted`. Completed artifacts are preserved.

## Artifacts

Direct CLI defaults to `data/triggered_capture_series/<timestamp>/`. One run
directory contains:

```text
waveform_0001.csv
waveform_0001_meta.json
waveform_0002.csv
waveform_0002_meta.json
...
manifest.json
scpi.log
```

The manifest records the request, session identity, status, completed count,
relative files, compact committed cycle entries, and terminal error. Each
committed cycle records its index, trigger elapsed time, CSV and metadata
paths, actual points, and system-error result. Raw waveform samples remain in
the CSV files rather than the manifest.

## Dry-Run, Simulator, And Worker

Dry-run validates the selected model profile and request without opening VISA
or writing artifacts. It reports the finite count and one representative
cycle: `:SINGle`, one Operation Status Condition query, waveform capture SCPI,
and one `:SYSTem:ERRor?`. Polling and cycles are not statically repeated.

Simulator mode executes the complete finite workflow and writes normal
artifacts. Common v2 Worker accepts only `channel`, `points`, `format`,
`count`, `trigger_timeout_seconds`, and `interval_seconds`. The Worker rejects
caller-supplied `output_dir` and `log_scpi`, and injects its owned job artifact
directory.

## v1 Non-Goals

Triggered Capture Series v1 does not add trigger configuration or restoration,
force trigger, retry, duration or infinite execution, absolute scheduling,
measurements, conditions, cleanup, screenshots, plots, segmented capture,
instrument-side Save/Export, Generic Sequence actions, WebUI runtime, new
hardware support, or a new workflow engine.

