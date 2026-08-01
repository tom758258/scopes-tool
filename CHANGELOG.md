# Scopes Tool Changelog

## Unreleased

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
