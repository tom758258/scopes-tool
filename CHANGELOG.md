# Scopes Tool Changelog

## Unreleased

- Adds the localhost-only WebUI with a Core-backed command workbench, Basic
  Controls, Live/Simulate/Dry-run execution where Dry-run plans supported
  operations without opening an instrument, result and artifact retrieval,
  English/Traditional Chinese UI text, and an English Launcher with automatic
  local port fallback and graceful shutdown of running jobs.
- Expands the WebUI command workbench with Core-backed channel, display,
  measurement, system/status, DVM, basic FFT/Math, Reference, Save/Export,
  Trigger, Search, Serial, Segmented Memory, and finite Workflow operations
  behind model-aware capability gating and metadata-driven read-edit-Apply
  forms.
- Adds a dedicated mode-aware WebUI Serial editor for UART/I2C/SPI/CAN
  configuration and triggering with bus/display controls and a Serial Lister
  section for display/reference settings and host-side CSV export.
- Adds a dedicated WebUI Trigger editor over the existing Trigger commands:
  the Command Browser groups remain the only navigation, readback is scoped to
  the active group, each command keeps its own independent Apply, and applies
  are followed by an active-group readback.
- Adds collapsible command groups to the WebUI Command Browser for dense
  categories while keeping the flat command list for ungrouped categories.
- Adds the finite `measure-until`, `triggered-measure-loop`, and
  `triggered-capture-series` workflows with Core, CLI, and Common v2 Worker
  adapters, artifacts, and dry-run planning.
- Names the existing batch capture workflow Periodic Capture (`capture-batch`)
  and supports cooperative Worker stopping for finite measurement and capture
  jobs.
- Adds Generic Sequence Workflow v1 in Core and the direct CLI with strict
  JSON documents, finite ordered loops over `wait`, `single`, `wait-trigger`,
  `measure`, `capture`, `screenshot`, and `cleanup` actions, dry-run planning,
  deterministic artifacts, and cooperative cancellation.
- Adds segmented-memory configuration and the finite `segmented-capture`
  workflow for registered Keysight 2000X, 3000X, and 4000X profiles,
  including Worker support.
- Makes waveform artifacts vertical-unit aware with `V`/`A` metadata and
  unit-specific CSV columns for capture-related outputs.
- Adds common UART, I2C, SPI, and CAN serial trigger criteria to Core without
  changing Serial decode configuration or acquisition behavior.
- Requires Common schema version 2 for Worker lifecycle JSON, Worker
  artifacts, and one-shot CLI machine JSON.

## 0.1.0

- Publishes the `scopes-tool` distribution containing the `scopes_tool_core`,
  `scopes_tool_cli`, and `scopes_tool_webui` import packages with the
  `scopes-tool` console script and `python -m scopes_tool_cli.cli` module
  entry point.
- Exposes the vendor-neutral `Oscilloscope` facade and `OscilloscopeError`
  base exception over the Core runtime for Keysight InfiniiVision
  oscilloscope automation.
- Includes the WebUI package skeleton without adding a WebUI runtime
  dependency or console command.
- Provides public documentation covering the Core API surface, CLI command
  usage, integration notes, JSON behavior, automation safety, and WebUI
  ownership.
