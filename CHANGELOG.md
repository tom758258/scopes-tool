# Scopes Tool Changelog

## Unreleased

- Adds query-only segmented-memory state queries for registered Keysight 2000X,
  3000X, and 4000X profiles through Core, CLI, Simulator, Worker, and Common
  v2 JSON. It does not configure segmented mode, acquire waveform data, or
  export artifacts.
- Adds explicit segmented-memory enable/count and disable configuration for
  registered 2000X, 3000X, and 4000X profiles. Counts are validated against
  profile limits before segmented writes; acquisition, capture, and export
  remain out of scope.
- Adds the finite single-channel `segmented-capture` workflow with bounded
  acquired-segment polling, per-segment host CSV export, a shared manifest and
  SCPI log, and partial-artifact retention on failure. It has no live hardware
  validation yet.
- Exposes `segmented-capture` through the Common v2 Scopes Worker with strict
  startup-bound validation, a Worker-owned artifact child directory, and
  existing succeeded/failed/cancelled lifecycle semantics.
- Adds the Serial UART Trigger P0 vertical slice through Core, CLI, Worker,
  Simulator, Common v2 JSON, and focused tests. It supports the shared basic
  UART trigger types and data qualifiers without changing Serial P1 decode
  configuration or acquisition behavior.
- Adds Serial Trigger P1 common I2C, SPI, and CAN criteria through Core, CLI,
  Worker, Simulator, and Common v2 JSON without changing Serial decode
  configuration or acquisition behavior.
- Completes Common v2-only migration for the Scopes Worker runtime, lifecycle
  clients, Worker JSONL/artifacts, and general one-shot CLI machine JSON.
- Passes the hardware-independent test suite, installed simulator/dry-run CLI
  smokes, and wheel/sdist package build validation.
- Marks the three Scopes-specific contracts as Common v2-only conformant while
  preserving independently versioned domain artifact schemas.
- Leaves Skill and Skill examples for future independent work; Local
  documentation remains unchanged and out of scope.

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
