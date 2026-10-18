# Changelog

## Unreleased

- Provides the vendor-neutral Core API, CLI, Common v2 Worker, and localhost-only
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
