# Scopes Tool Changelog

## Unreleased

- Marks the three Scopes-specific contracts as Common v2-only migration targets.
- Retains the existing queued-job lifecycle, startup-bound context, commands,
  artifacts, and hardware behavior.
- Defers runtime, clients, outputs, and tests; this documentation does not
  claim Common v2 implementation conformance.
- Replaces the three copied Common v1 contract documents with the shared
  v2-only Worker Protocol, CLI JSON/JSONL Contract, and Orchestrator Workflows.
- Documents the future Common v2 requirements for strict
  `schema_version: 2`, vendor-qualified model identity, execution context,
  structured errors, lifecycle correlation, and fail-closed Agent behavior.
  Scopes implementation conformance will be completed separately; this
  documentation update does not change the current Worker runtime, device
  behavior, hardware support, or product scope.

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
