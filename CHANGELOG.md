# Scopes Tool Changelog

## Unreleased

- Adds a mode-aware Serial editor to the WebUI that coordinates bus selection,
  Serial Mode with explicit Apply Mode and readback verification, Serial
  Display, and UART/I2C/SPI/CAN configuration over the existing commands while
  showing unsupported instrument protocols without protocol-specific queries,
  keeping the Protocol selector synchronized with confirmed readbacks,
  re-checking the active mode before configuration writes, and confirming
  before discarding unapplied edits on bus switches and unapplied
  configuration edits on protocol switches.
- Adds collapsible command groups to the WebUI Command Browser for dense
  Trigger, Search, Serial, Save/Export, and Workflow categories while keeping
  the flat command list for ungrouped categories.
- Expands the WebUI with Core-backed conditional command coverage for Trigger,
  Search, Serial, Segmented Memory, and finite Workflow operations while
  keeping Generic Sequence and advanced FFT/Math editors deferred.
- Fix WebUI query defaults that submitted set-only measurement and DVM channel fields.
- Expands the WebUI workbench with Core-backed Reference and instrument-side
  Save/Export commands without registering host artifacts for instrument saves.
- Expands the WebUI command workbench with Core-backed flat coverage for
  channel/display, measurement, system/status, DVM, and basic FFT/Math
  operations while leaving conditional command editors out of scope.
- Fix WebUI enum presentation fallback, expose only canonical measurement
  selector items, and add Launcher shutdown regression coverage.
- Fixes WebUI job shutdown so the Launcher waits for queued cancellation and
  natural completion of running jobs before stopping Uvicorn, reports shutdown
  timeouts or session-close failures without destroying the Launcher, and
  restricts dry-run acquisition to query operations.
- Adds the localhost-only WebUI server and English Launcher with a Core-backed
  command workbench, Basic Controls, simulated and dry-run jobs, result and
  artifact retrieval, English/Traditional Chinese UI text, health endpoint,
  default port 8025, and automatic fallback across up to 100 available local
  ports.
- Adds the finite `measure-until` Core workflow with CLI and Common v2 Worker
  adapters, condition and timeout terminal semantics, measurement artifacts,
  cooperative cancellation, and representative-iteration dry-run planning.
- Adds the finite `triggered-capture-series` Core workflow with CLI and Common
  v2 Worker adapters, natural trigger waiting, waveform artifacts, strict
  completion accounting, and representative-cycle dry-run planning.
- Defines Periodic Capture v1 as the product-facing name for the existing
  `capture-batch` CLI, Worker, and Core workflow, and restricts Worker requests
  to the Worker-owned job artifact directory.
- Adds the finite `triggered-measure-loop` Core workflow with CLI and Common v2
  Worker adapters, trigger-wait cancellation, measurement CSV/manifest/SCPI
  artifacts, and representative-cycle dry-run planning.

- Adds Generic Sequence Workflow v1 in Core and the direct CLI with strict JSON
  documents, finite ordered loops, dry-run planning, deterministic artifacts,
  cooperative cancellation, progress reporting, and the existing `wait`,
  `single`, `wait-trigger`, `measure`, `capture`, `screenshot`, and `cleanup`
  actions.
- Adds reusable Core workflow support for finite measurement and capture jobs,
  and connects Worker stop requests to `measure-log` and `capture-batch` at safe
  cancellation boundaries while preserving completed results and artifacts.
- Adds segmented-memory query and configuration support plus the finite
  `segmented-capture` workflow for registered Keysight 2000X, 3000X, and 4000X
  profiles, including Worker support and partial-artifact preservation on
  failures and read timeouts.
- Makes waveform artifacts vertical-unit aware, including `V`/`A` metadata and
  `_v`/`_a` CSV columns for capture-related outputs.
- Adds common UART, I2C, SPI, and CAN serial trigger criteria without changing
  Serial decode configuration or acquisition behavior.
- Requires Common schema version 2 for Worker lifecycle JSON, Worker artifacts,
  and one-shot CLI machine JSON.

## 0.1.0

- Publishes one `scopes-tool` distribution containing the
  `scopes_tool_core`, `scopes_tool_cli`, and `scopes_tool_webui`
  import packages.
- Maintains the current Core runtime for Keysight InfiniiVision oscilloscope
  automation.
- Adds the `scopes-tool` console script and
  `python -m scopes_tool_cli.cli` module entry point.
- Exposes the vendor-neutral `Oscilloscope` facade and `OscilloscopeError`
  base exception.
- Maintains the current WebUI package skeleton without adding a WebUI runtime
  dependency or console command.
- Public documentation covers the Core API surface, CLI command usage,
  integration notes, JSON behavior, automation safety, and WebUI ownership.
