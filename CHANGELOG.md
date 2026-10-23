# Changelog

## 1.0.0

### Breaking Changes

- The Worker moves from Common v2 to Common v3 with `v3-only` compatibility;
  there is no v2 fallback or version negotiation. Integrations must send the
  exact integer `schema_version: 3` in command requests, omit startup-bound
  request context, and update HTTP/JSONL response handling to the
  [Scopes Worker contract](docs/contracts/scopes-worker-contract.md).
- Consumers must handle Common Error objects, async-job acknowledgements and
  snapshots, `job_finished` terminals, and Worker summary/EOF/exit separately.
  An accepted command is not a completed job; job completion is not Worker
  shutdown. Correlate `run_id`, `worker_job_id`, and caller `job_id` as specified
  in the [workflow contract](docs/contracts/scopes-orchestrator-workflows.md).
- Worker HTTP and JSONL use schema 3; Manifest and ordinary CLI JSON remain
  schema 2. Do not upgrade all schemas together. The Manifest declares
  `multi_job` / `startup` and only `common.async_jobs` contract version 1;
  `common.job_cancel` and `common.streaming` are not declared.

### Added

- Provides the vendor-neutral Core API, CLI, Common v3 Worker, and localhost-only
  WebUI through one `scopes-tool` distribution with independent Core, CLI, and
  WebUI import packages.
- Supports registered Keysight InfiniiVision DSOX2004A, DSOX3024A, DSOX4024A,
  and DSOX4034A, and Tektronix TBS2074, TDS2024B, and TBS1052B models with
  detected identity, model-aware capabilities, and guarded live connections.
- Supports acquisition, channels, timebase, waveform and screenshot capture,
  measurements and statistics, and model-dependent DVM, Math, FFT, WGEN,
  Reference, Trigger, Search, Serial, and segmented-memory operations.
- Runs finite measurement, logging, periodic and triggered capture workflows,
  capture-until and capture-monitor workflows, and Generic Sequence v1 with
  structured results, artifacts, progress, and cooperative cancellation.
- Provides hardware-free simulation for registered Keysight and Tektronix models
  and Core-backed dry-run planning for supported operations.
- Includes an Electron Desktop shell and Windows onedir packaging with the
  Desktop, CLI, WebUI Launcher, and private Host sharing one `_internal`, plus
  versioned release archives, SHA-256 checksums, and no-hardware acceptance checks.
- Provides English and Traditional Chinese WebUI text, documentation, and offline
  CLI/WebUI Help, with System, Light, and Dark themes and a local Launcher with
  automatic port fallback and graceful shutdown.

### Changed / Fixed

- Align Worker ready/status declarations, structured errors, job terminal
  snapshots, stop responses, and summary handling with Common v3 while
  preserving Scopes queue, instrument, cleanup, and artifact behavior.
- Reject incompatible Worker versions and malformed known feature declarations
  in the CLI client; validate local control URLs and runtime correlation before
  using Worker responses.
- Preserve completed workflow artifacts and terminal state when later manifest
  writes fail, and classify manifest I/O errors consistently.
- Add `release-acceptance` to the manual Build Windows workflow. It builds once
  through the formal nine-step acceptance gate, verifies the report against
  the release version and source commit, and stages only that run's assets.
  Evidence reports remain separate from distributables. Only a successful
  acceptance on `main` can optionally create a Draft Release; existing tags
  and releases cannot be overwritten and publishing remains manual.
- Check the actual packaged and installed CLI Manifest for release-version and
  Common v3 compatibility as part of existing no-hardware packaging smoke.
- Synchronize Python, Core, Electron, and lockfile application versions at 1.0.0.

### Known Limitations

- Live operation is limited to registered models and the exact combinations in
  [Supported Models](docs/core/supported-models.md). System VISA USB is open
  for the seven registered models. System VISA TCPIP and `@py` TCPIP are open
  only for DSOX4024A, DSOX4034A, and TBS2074. Other model/transport/backend
  combinations fail closed.
- System VISA requires a separately installed IVI runtime; there is no automatic
  fallback to `@py`. USB through `@py`, GPIB, ASRL, Bluetooth, and custom VISA
  backends are not Product-open. USB backend dependencies and drivers are not
  bundled. Discovery depends on the instrument and network.
- Operations, option subsets, waveform formats/points, and installed instrument
  options remain model-dependent. Tektronix supports a documented subset;
  normalized `check-error` and simulator signal presets/error injection are
  unavailable for those models. Simulation does not establish live support.
- The Worker uses startup-bound context and serialized jobs, with no common
  per-job cancel or streaming extension, history, or replay. Existing cooperative
  Worker stop and workflow cancellation retain their tool-specific semantics.
- Generic Sequence v1 composes supported Core operations, not arbitrary SCPI.
  WebUI is localhost-only; Desktop packages target Windows x64. No-hardware
  acceptance does not validate GUI interaction or live instruments.
