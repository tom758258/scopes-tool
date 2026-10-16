# Scopes Tool Core

Core runtime package for vendor-neutral oscilloscope control through
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

VISA library selectors are normalized to these Core identities:

- unset or blank selector → `system_visa`
- `@py` → `pyvisa_py`
- `@bt` → `pyvisa_bt`
- any other explicit selector → `custom_visa`

System VISA (unset, blank, or `system_visa`) explicitly opens `@ivi` and
checks the loaded library against PyVISA's `IVIVisaLibrary` type. A missing,
failed, or non-IVI backend fails closed; a created manager is closed on
verification failure. Installing pyvisa-py or setting `PYVISA_LIBRARY=@py`
does not change this selection. Other explicit selectors pass through unchanged.

Ordinary installations and Windows packages include `pyvisa-py` and its LAN
discovery dependencies (see [installation prerequisites](../../README.md#install)).
Other selected backends may require separate installation. Backend availability
does not grant Product Live support. Core checks the requested transport and
backend before opening VISA and the exact physical model resolved from `*IDN?`
before a Product command. System VISA Product support is limited to approved
model/USB or model/TCPIP pairs; `@py` Product support is limited to DSOX4024A,
DSOX4034A, and TBS2074 over TCPIP. The `@py` USB pairs are not Product-open.
`@bt` and explicitly selected custom VISA backends (including an explicit
`@ivi` selector) are not Product-open; use the default System VISA selector
to request the verified IVI backend.

Contributor Validation Mode is an explicit CLI-only option for registered
`@py` USB candidates and supported `@py` TCPIP scopes. It still requires
actual `*IDN?` identity and does not grant Product access. WebUI and Worker
cannot select Validation Mode. Identification and resource discovery remain
diagnostics; dry-run and simulation do not open a live VISA session.
Direct Python use of `Oscilloscope.open()` is a low-level session interface,
not a Product support entry point. See [Supported Models](supported-models.md)
for the exact connections and model-specific feature limits.

## Feature Areas

Core groups the instrument surface into these feature families:

- Connection, identity, capabilities, status, and safe resource/runtime
  handling.
- Channels, display, annotations, timebase, cursors, acquisition, and
  read-only instrument state summaries.
- Measurements, capability-gated advanced measurement statistics settings and
  results, waveform capture, screenshots, reference waveforms, and
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
`capture-batch`, Capture Until, Capture Monitor, Triggered Measurement Loop,
Triggered Capture Series, Measure Until Condition, Generic Sequence, and
`segmented-capture` where supported by the active profile. Workflow-owned
waveforms may be analyzed or retained in bounded RAM without changing the
artifact-producing behavior of standalone `capture`. Detailed contracts for
the workflow families documented by Core Integration — including request
fields, defaults, terminal behavior, artifact schemas, and Generic Sequence
rules where applicable — are maintained in
[Core Integration](integration.md).

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
