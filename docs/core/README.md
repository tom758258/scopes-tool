# Scopes Tool Core

Core runtime package for Keysight InfiniiVision oscilloscope control through
PyVISA-compatible backends.

Distribution: `scopes-tool`

Import package: `scopes_tool_core`

## Purpose And Ownership

Core owns the shared runtime and hardware-facing behavior used by the Scopes
Tool adapters. Its responsibilities include:

- Opening VISA resources safely and resolving the selected run mode.
- Detecting `*IDN?` identity and resolving the canonical physical model.
- Applying registry-linked capability profiles and driver behavior.
- Validating requests before unsafe or state-changing operations where
  applicable.
- Generating and executing model-appropriate instrument operations, including
  SCPI-facing queries, configuration, acquisition, and parsing.
- Providing simulator, fake-backend, and no-hardware planning paths.
- Running finite synchronous Core workflows with cooperative cancellation,
  progress reporting, and operation-specific samples.

CLI, Worker, and WebUI are adapters over Core. They own command parsing,
presentation, serialization, terminal/browser behavior, HTTP control, and
queue or job lifecycle. They must use Core identity, capabilities, validation,
drivers, and instrument behavior rather than implementing parallel versions.
Core does not import adapter packages.

## Identity, Capabilities, And Runtime Boundary

For live operation, the detected `*IDN?` response and the resolved canonical
physical model are the runtime authority. For simulator and dry‑run planning,
a planning physical model selects the registered capability profile used for
hardware-free planning and validation. In live mode an expected physical model
serves only as a safety guard and never replaces the identity or capability
profile detected through `*IDN?`. Unknown, unregistered, or mismatched live
vendors, models, profiles, or drivers fail closed.

Capability profiles describe the supported runtime surface for a model. They
do not prove that an optional instrument option or license is installed; live
instrument errors remain authoritative. Simulator and dry-run planning support
hardware-free development and validation, but do not constitute live hardware
validation.

Core owns hardware-facing behavior and safety validation. Adapters do not
define the Core validation contract. Core workflows support cooperative
cancellation, but a blocking VISA or device read is not forcibly interrupted.
Core also does not own Worker queue admission, persisted job lifecycle, HTTP
control, or WebUI presentation.

VISA library selectors are normalized to these Core identities without changing
the selector passed to the runtime:

- unset or blank selector → `system_visa`
- `@py` → `pyvisa_py`
- `@bt` → `pyvisa_bt`
- any other explicit selector → `custom_visa`

This classification does not guarantee that the selected backend is installed
or available in the runtime environment.

## Feature Areas

Core groups the instrument surface into these feature families:

- Connection, identity, capabilities, status, and safe resource/runtime
  handling.
- Channels, display, annotations, timebase, cursors, acquisition, and
  read-only instrument state summaries.
- Measurements, waveform capture, screenshots, reference waveforms, and
  instrument-side or host-side save/export helpers.
- Trigger families, common trigger settings, one-shot trigger control, and
  finite trigger wait/capture helpers.
- Serial bus configuration, serial triggering and search, lister state, and
  raw lister data export.
- Instrument-side Math and FFT configuration, including supported transforms,
  operators, filters, visualizations, and series-specific capability paths.
- Optional or instrument-side features such as DVM, WGEN, Demo output, and
  segmented memory, subject to profile and instrument support.
- Finite Core workflows and simulator support for hardware-free execution,
  planning, callbacks, and deterministic error-path testing.

Feature-family descriptions here are an overview, not a command reference or
an exhaustive API, SCPI, model, firmware, or option-support matrix.

## Workflow Foundation

Core provides finite synchronous workflows built from existing instrument
operations. Workflows can accept cooperative stop requests, synchronous
progress reporters, and operation-specific sample callbacks; they do not
introduce an async runtime, scheduler, persistence layer, or event bus.

The current workflow surface includes `measure-log`, Periodic Capture through
`capture-batch`, Triggered Measurement Loop, Triggered Capture Series, Measure
Until Condition, Generic Sequence, and `segmented-capture` where supported by
the active profile. Detailed contracts for the workflow families documented by
Core Integration — including request fields, defaults, terminal behavior,
artifact schemas, and Generic Sequence rules where applicable — are maintained
in [Core Integration](integration.md).

## Public Package Surface

Downstream Python consumers should prefer imports from the
`scopes_tool_core` package root. The package-root `__all__` defines the public
import boundary. The complete current public import list and integration
examples are maintained in [Core Integration](integration.md).

Implementation-only submodules and helpers are not public API merely because
they are importable; README cleanup does not expand that boundary.

## Validation

From the repository root, the focused Core documentation and ownership check
can be run with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_core_docs_ownership.py -q -p no:cacheprovider --basetemp .tmp_tests\core-docs
```

## Docs

- [Core Integration](integration.md)
- [Supported Models](supported-models.md)
- [CLI documentation](../cli/README.md)
- [Shared CLI, Worker, and orchestrator contracts](../contracts/)
