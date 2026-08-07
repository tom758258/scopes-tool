# Scopes Tool Changelog

## Unreleased

- Adds Core Workflow Foundation v1 with optional cooperative cancellation,
  interruptible interval waits, synchronous progress callbacks, and
  operation-specific sample callbacks.
- Moves the finite `capture-batch` execution loop into Core and adopts the
  shared workflow helpers in `measure-log` without changing their CLI commands,
  SCPI behavior, artifact schemas, or finite count/duration requirements.
- Connects the existing Worker `/stop` state to running Core measurement and
  capture workflows so they stop at safe boundaries and preserve completed
  artifacts. Worker protocol and schema version remain unchanged.
- Adds query-only segmented-memory state queries for registered Keysight 2000X,
  3000X, and 4000X profiles. It does not configure segmented mode, acquire
  waveform data, or export artifacts.
- Adds explicit segmented-memory enable/count and disable configuration for
  registered 2000X, 3000X, and 4000X profiles. Counts are validated against
  profile limits before segmented writes. Configuration does not start
  acquisition, capture waveform data, or export artifacts.
- Adds the finite single-channel `segmented-capture` workflow with bounded
  operation-condition readiness polling, per-segment host CSV export, a shared
  manifest and SCPI log, and partial-artifact retention on failure.
- Exposes `segmented-capture` through the Common v2 Scopes Worker with strict
  startup-bound validation, a Worker-owned artifact child directory, and
  existing succeeded/failed/cancelled lifecycle semantics.
- Stabilizes segmented-capture export by requiring two consecutive RUN-clear,
  remote-interface-enabled operation-condition samples before one acquired-count
  query, and stops issuing SCPI after any segmented-capture read timeout.
- Preserves segmented-capture read-timeout errors over earlier normal deadline
  errors.
- Adds `serial-trigger-uart` support for the shared basic UART trigger types
  and data qualifiers without changing Serial decode configuration or
  acquisition behavior.
- Adds `serial-trigger-i2c`, `serial-trigger-spi`, and `serial-trigger-can`
  support for common I2C, SPI, and CAN trigger criteria without changing
  Serial decode configuration or acquisition behavior.
- Requires Common schema version 2 for Scopes Worker lifecycle JSON, Worker
  artifacts, and one-shot CLI machine JSON. Lifecycle clients reject non-v2
  Worker responses without v1 fallback or version negotiation; independently
  versioned domain artifact schemas remain unchanged.

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
