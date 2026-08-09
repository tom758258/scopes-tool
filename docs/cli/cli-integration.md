# CLI Integration

The CLI package adapts `argparse.Namespace` inputs into Core run-mode,
planning, and operation calls. Keep parser-only naming and compatibility fields
in this package.

CLI-only fields include:

- `measurement_cli_name`
- command names such as `measure-log`, `capture-batch`,
  `triggered-measure-loop`, `sequence`, and `hardware-report`
- process return-code behavior
- stderr SCPI diagnostic handling
- parser validation messages

DVM adapter commands are `dvm-enable`, `dvm-source`,
`dvm-mode`, `dvm-auto-range`, `dvm-current`, and `dvm-query`. Boolean
configuration uses canonical `--enabled true|false`; `dvm-current` and
`dvm-query` require `--query`. The adapter does not expose DVM frequency,
independent Counter, or `:MEASure:COUNter` commands.

WGEN adapter commands are `wgen-query`, `wgen-output`,
`wgen-function`, `wgen-frequency`, `wgen-voltage`, `wgen-offset`, and
`wgen-load`. The selected model profile determines the concrete `:WGEN` or
`:WGEN1` SCPI root. The adapter does not expose a generator selector.

Serial configuration commands are `serial-query`, `serial-mode`, and
`serial-display`. Every command requires `--bus`. Mode and display require
exactly one of query or configure action; display configuration uses canonical
`--enabled true|false`. `serial-query` preserves the trimmed aggregate
subsystem response without deriving mode or display fields. Simulation and
dry-run use the selected model profile to validate bus count and settable mode
before backend open; live workers use their startup model for the same strict
pre-open validation. A normal live one-shot opens the requested resource,
queries `*IDN?`, and then validates Serial bus and mode support from the
detected model before sending any `:SBUS...` command; `--model` does not
override that detected identity. Serial configuration also provides
`serial-uart`, `serial-i2c`, `serial-spi`, and `serial-can` for basic protocol
source and decode settings. Each command accepts `--query` or one or more protocol
options, queries `MODE?` before protocol fields, and fails before field queries
when the mode does not match. Sources use `channelN` (bounded by the model's
analog-channel capability) or `external`; I2C emits the instrument `IIC` token,
and CAN uses `difl` as the canonical differential signal value. Capability
profiles determine bus count and available protocol modes; instrument licenses
may still be required. Serial configuration does not expose serial trigger,
Lister, or export configuration; Search configuration and Serial Search are
documented below.

Search adapter commands are `search-state`, `search-mode`, `serial-search-uart`, `serial-search-i2c`, `serial-search-spi`, `serial-search-can`,
query-only `search-count`, and 4000X `search-event`. Boolean configuration uses canonical
`--enabled true|false`; search modes use lowercase canonical values and are
validated against the selected model capability profile before search SCPI.
Mode configuration enables search before selecting the mode.

These fields are adapter behavior, not Core schema. Core receives normalized
requests and returns runtime data; the CLI decides how to render human text,
JSON stdout, stderr logs, and exit codes.

`measure-log`, `capture-batch`, and `triggered-measure-loop` execution is
Core-owned. Their CLI adapters normalize arguments into `MeasureLogRequest`,
`CaptureBatchRequest`, or `TriggeredMeasureLoopRequest`, open
the selected run-mode session, invoke the Core operation, and render its
`OperationResult`. Internal JSON dispatch accepts an optional cancellation
predicate so the Worker can reuse the same operations; normal direct CLI calls
use the no-op default. The CLI does not maintain a parallel batch loop or
workflow scheduler.

Triggered measurement dry-run delegates one representative cycle to
`plan_triggered_measure_loop()`. Runtime delegates the finite acquisition loop
to `run_triggered_measure_loop()`. Direct CLI may provide `--output-dir`; the
Worker rejects that request field and injects its owned job directory.

`sequence` loads a strict JSON document before opening a scope, builds a
`SequenceRequest`, and delegates planning or execution to Core. Dry-run uses
`plan_sequence()` and writes no artifacts. Simulate and live execution use
`run_sequence()`; the CLI does not implement a parallel step loop. Sequence is
direct-CLI-only in v1 and is not added to the Worker command allowlist.

Workflow `scpi.log` files cover SCPI activity produced during the Core
operation. Resource opening, live identity validation, driver selection, and
other CLI or Worker preflight before that call are outside the workflow log
boundary and are not guaranteed to appear. The CLI does not wrap the operation
in a second logging lifecycle, and the artifact is not a complete process or
session trace.

For one-shot commands, an explicit `--resource` or
`SCOPES_TOOL_RESOURCE` selects one live instrument. The optional `--live`
flag is retained for compatibility and conflicts with `--simulate` and
`--dry-run`. Worker startup remains a separate lifecycle path that requires
`--live --resource`; `list-resources --live-only` remains the only discovery
path that opens each enumerated resource.

The installed console script remains:

```text
scopes-tool = scopes_tool_cli.cli:main
```

The module form remains:

```powershell
python -m scopes_tool_cli.cli
```

CLI JSON behavior is documented by the root Scopes contract:
`docs/contracts/scopes-cli-jsonl-contract.md`. One-shot and lifecycle JSON
payloads include `schema_version: 2` and `timestamp_utc`.
