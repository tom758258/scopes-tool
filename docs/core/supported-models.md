# Supported Models

This document records public model support decisions for the Core runtime.
Command-level behavior remains documented in `../cli/README.md` and
`../contracts/`.

Capability profiles describe the runtime-supported and guarded feature surface.
They are not a claim that every feature has completed live validation on every
model, firmware, or transport.

## Canonical Physical Model Identity

Scopes Tool exposes a vendor-neutral product API while the currently
implemented hardware family remains Keysight InfiniiVision. The canonical
physical model registry contains:

| Canonical physical model ID | Manufacturer | Model | Series | Capability profile ID | Driver ID |
| --- | --- | --- | --- | --- | --- |
| `keysight-dsox2004a` | Keysight Technologies | DSOX2004A | 2000X | `keysight-infiniivision-2000x` | `keysight-infiniivision` |
| `keysight-dsox3024a` | Keysight Technologies | DSOX3024A | 3000X | `keysight-infiniivision-3000x` | `keysight-infiniivision` |
| `keysight-dsox4024a` | Keysight Technologies | DSOX4024A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |
| `keysight-dsox4034a` | Keysight Technologies | DSOX4034A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |

Canonical registration identifies a physical model; it does not claim that
every feature has completed live hardware validation. Each registered model
explicitly selects its runtime capability profile.

Every registered physical model is protected by a hardware-free consistency
gate covering vendor identity, capability lookup, driver selection, and
deterministic simulator identity resolution.

Core has an explicit driver-selection boundary keyed by each physical model's
registered driver ID. The only currently registered runtime driver is
`keysight-infiniivision`. Live selection follows the canonical physical model
resolved from the detected `*IDN?` identity; planning and expected identities
cannot override it. Unknown vendors, physical models, or missing or
unregistered driver IDs fail closed.

## Runtime Profiles

Core resolves live `*IDN?` manufacturer and model fields to a canonical
physical model ID, then follows the registered capability profile ID. Dry-run
and simulator `--model` values are canonical physical model IDs. Simulator
manufacturer/model IDN fields and capabilities are derived from that same
registry entry.

| Profile ID | Series | Registered models | Analog channels |
| --- | --- | ---: | --- |
| `keysight-infiniivision-2000x` | 2000X | DSOX2004A | 4 |
| `keysight-infiniivision-3000x` | 3000X | DSOX3024A | 4 |
| `keysight-infiniivision-4000x` | 4000X | DSOX4024A, DSOX4034A | 4 |

A model string that merely resembles a DSO-X or MSO-X series model is not
sufficient for capability selection. Unregistered names such as `DSOX4054A`
and raw model names such as `DSOX4024A` are rejected as `--model` values.

In live execution, capabilities come only from the canonical physical identity
resolved from the actual `*IDN?` manufacturer and model fields. A planning
identity cannot override that result. Live workers treat `--model` as an
expected canonical physical model ID and fail before command-specific SCPI
when it does not match the detected identity.

## Capability Summary

All supported series profiles currently expose:

### Instrument-Side Math Matrix

P0-P7 Math support is instrument-side only. Canonical operation and source
names remain independent of raw SCPI readbacks.

| Surface | 2000X | 3000X | 4000X |
| --- | --- | --- | --- |
| Math function slots and dialect | 1; unnumbered `:FUNCtion` | 1; unnumbered `:FUNCtion` | 4; indexed `:FUNCtion<n>` |
| Operators | `add`, `subtract`, `multiply`, `divide` | Same | Same |
| Transforms | `differentiate`, `integrate`, `sqrt`, `absolute`, `square`, `ln`, `log10`, `exp`, `exp10`, `linear` | Same | Same |
| Filters | `low-pass`, `high-pass` | Same | `low-pass`, `high-pass`, `average`, `smooth`, `envelope` |
| Visualizations | `magnify`, `trend` | Same | `magnify`, `trend`, `maximum`, `minimum`, `peak`, `max-hold`, `min-hold` |
| FFT | Basic magnitude FFT | Basic magnitude FFT | Magnitude FFT and FFT Phase with advanced controls |
| Composite / GOFT source | Global analog-channel composite | Same | Not supported |
| Math cascade source | Not supported | Not supported | Lower-numbered Math functions only |
| Accumulation clear | Not supported | Not supported | `average`, `max-hold`, `min-hold` |

Display, vertical configuration, query, and the applicable clear behavior use
the same function-slot dialect. The 2000X/3000X profiles reject Math-function
cascade sources. The 4000X profile rejects composite/GOFT sources and rejects
self-reference or forward-reference before backend access. The existing
`fft` CLI and Worker command remains compatible across all profiles.

MATH-P8 bus-timing and bus-state are blocked by the missing MSO/digital-channel
foundation. They are absent from enabled capability operations, CLI choices,
Worker commands, Core builders, and simulator behavior; no hardware-free shell
is provided. This matrix has hardware-free validation only. Focused live
validation is still required for each registered model, relevant firmware,
and USB/LAN or Worker-live path.

- BYTE and WORD waveform capture with a conservative 10,000-point safe maximum.
- Read-only measurement helpers and screenshot capture.
- Measurement Control Pack v1 helpers for clearing measurements, enabling or
  querying measurement markers, selecting analog measurement sources, and
  selecting the MAIN, ZOOM, AUTO, or GATE measurement window. ZOOM is
  conditional on the zoomed timebase already being displayed; AUTO is safer
  when that state is unknown. A source1-only write may preserve source2 in
  instrument readback.
- Reference Waveform Pack v1 helpers for runtime-managed reference waveform
  slots 1 and 2. The instrument may turn off one slot's display when the other
  is enabled.
- DVM Common Pack v1 helpers for enable, analog source, `dc`, `dc-rms`, and
  `ac-rms` voltage modes, auto range, current voltage, and aggregate queries.
  DVM can be option/license dependent. This pack has hardware-free validation
  only and does not implement DVM frequency, independent `:COUNter`, or
  `:MEASure:COUNter` support.
- Demo Output Pack v1 aggregate and focused output/function/phase helpers.
  DEMO is option-/hardware-dependent; capability profiles guard the documented
  function names before session open, while live instrument errors remain
  authoritative for missing options or hardware.
- WGEN Basic P1 output, function, frequency, amplitude, offset, load, and
  aggregate query helpers. The 2000X/3000X profiles use `:WGEN`; the 4000X
  profile uses only generator 1 through `:WGEN1`. P1 settable functions are
  `sine`, `square`, `ramp`, `pulse`, `noise`, and `dc`.
- Serial Basic P0 raw aggregate query, mode, and display controls. Capability
  profiles guard bus count and settable modes. Serial decode can require an
  instrument license; Core does not probe licenses and preserves instrument
  errors for unavailable hardware or options.
- Search Basic Pack v1 state and count queries plus profile-guarded mode
  configuration. Unsupported modes are rejected before search SCPI is sent.
- Save/Export Pack v1 common instrument-side SAVE commands for current save
  directory and base name, image settings and start, and waveform settings and
  start. All three profiles also expose the query-only maximum-length mode
  readback. The configured waveform length minimum is 100 points; the actual
  maximum remains instrument/model dependent.
- Analog channel labels, display labels, and display annotation.
- Hardware-free Core/CLI/simulator/worker support for the documented one-shot
  trigger packs, including `trigger-tv` basic TV / video trigger configure and
  query.
- Triggered capture wait classification for DSO-X 2000X/3000X/4000X using the
  Operation Status Condition Run bit.

Series-specific differences:

| Series | Demo Output Pack v1 functions | Serial buses | Serial Basic P0 settable modes | Search Basic Pack v1 modes | Screenshot Format Pack v1 |
| --- | --- | ---: | --- | --- | --- |
| 2000X | Common/core set | 1 | `can`, `i2c`, `lin`, `spi`, `uart` | `serial1` | No; existing PNG capture remains supported |
| 3000X | Common/core set plus `i2s`, `can-lin`, `flexray`, `arinc`, `mil`, `mil2` | 2 | `a429`, `flexray`, `can`, `i2s`, `i2c`, `lin`, `m1553`, `spi`, `uart` | `edge`, `glitch`, `runt`, `transition`, `serial1`, `serial2` | No; existing PNG capture remains supported |
| 4000X | Same v1 set as 3000X | 2 | `a429`, `flexray`, `can`, `cxpi`, `i2s`, `i2c`, `lin`, `m1553`, `manchester`, `nrz`, `sent`, `spi`, `uart`, `usb`, `usb-pd` | `edge`, `glitch`, `runt`, `transition`, `serial1`, `serial2`, `peak` | PNG, BMP, BMP8bit, appearance controls, and state query |

The common/core DEMO set is `sine`, `noisy`, `phase`, `lf-sine`, `am`,
`rf-burst`, `fm-burst`, `harmonics`, `coupling`, `ringing`, `single`, `clock`,
`runt`, `transition`, `setup-hold`, `mso`, `burst`, `glitch`,
`edge-then-edge`, `i2c`, `uart`, `spi`, `can`, and `lin`. Demo Output Pack v1
intentionally excludes the additional 4000X-only DEMO functions until their
short command and readback tokens are added with unambiguous coverage. It does
not include WGEN behavior and adds no WebUI runtime behavior. Validation is
hardware-free only; no physical model, firmware revision, USB/LAN path, or
worker live path was validated for this pack.

Screenshot Format Pack v1 is capability-gated to 4000X because its explicit
format transfer uses the documented `:HCOPY:SDUMp` command family. This is
hardware-free support only; no live instrument validation has been run for the
pack.

All three profiles support `search-state` and query-only `search-count`.
`search-mode` enables search before setting the mode. Search event navigation is supported on 4000X via `search-event`.
Mode-specific search parameter commands and serial search pattern
configuration are outside Search Basic Pack v1.

- 2000X and 3000X channel labels allow up to 10 printable ASCII characters.
- 4000X channel labels allow up to 32 printable ASCII characters.
- 2000X and 3000X annotation uses one unindexed slot and does not support X/Y
  annotation position.
- 4000X annotation supports indexed slots 1 through 10 and X/Y annotation
  position.
- 4000X supports the guarded `delay` pair measurement path. 2000X and 3000X do
  not expose that helper because their delay query depends on measurement
  definition state.

Capability flags for raw waveform points mode and segmented memory remain
disabled. Serial decode capability represents command-family availability, not
the presence of an instrument license.

Serial Basic P0 implements only aggregate query, mode, and display. The
aggregate response remains raw. Protocol-specific configuration, serial
sources, Lister, export, serial trigger, and serial search are not implemented.

These common pack entries describe runtime capability support. They do not
imply live hardware validation on every supported model, firmware, or USB/LAN
transport.

Save/Export Pack v1 has hardware-free Core, simulator, CLI, and worker
coverage only. It does not claim live validation and does not include results,
lister, mask, multi, power, arbitrary, compliance, segmented, setup, or
WMEMory export.

## Live Validation Summary

Live validation is opt-in and model-specific. Normal automated tests remain
hardware-free.

| Model | Series | Connection | Public validation status |
| --- | --- | --- | --- |
| DSOX4024A | 4000X | USB | Full documented USB hardware plan passed by user report for the supported workflow set. |
| DSOX4024A | 4000X | LAN | Deferred until an explicit LAN resource is available and approved. |
| DSOX4034A | 4000X | USB | Focused validations passed by user report for recent compatibility work, including sample-rate, acquisition-points, record-length, force-trigger, triggered capture wait, channel labels, display labels, indexed annotation, Measurement Control Pack v1, and Reference Waveform Pack v1. Measurement-window zoom requires the zoomed timebase to be displayed; source1-only writes may preserve source2; enabling one reference display may turn off the other. A full model matrix remains deferred. |
| DSOX4034A | 4000X | LAN | Deferred until an explicit LAN resource is available and approved. |
| DSOX3024A | 3000X | USB or LAN | Runtime profile exists; live validation is deferred until hardware is available. |
| DSOX2004A | 2000X | USB or LAN | Runtime profile exists; live validation is deferred until hardware is available. |

Detailed local hardware notes, exact lab resources, serial numbers, report
paths, and operator context belong in local-only validation notes, not in this
public document.

## Validation Boundaries

- Public capability JSON reports the runtime-supported feature surface only.
- Hardware validation must name the real instrument and command that was run.
- LAN support should be validated only after USB evidence and an explicit
  operator-selected LAN resource.
- Worker live validation is separate from one-shot CLI validation.
- No public document should hard-code private VISA resource strings, serial
  numbers, lab IP addresses, or local artifact paths.
