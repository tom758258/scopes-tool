# Supported Models

This document records public model support decisions for the Core runtime.
Command-level behavior remains documented in `../cli/README.md` and
`../contracts/`.

Capability profiles describe the runtime-supported and guarded feature surface.
They do not detect instrument options or licenses, and live instrument errors
remain authoritative for unavailable hardware or options.

## Canonical Physical Model Identity

Scopes Tool exposes a vendor-neutral product API while the supported hardware
family is Keysight InfiniiVision. The canonical
physical model registry contains:

| Canonical physical model ID | Manufacturer | Model | Series | Capability profile ID | Driver ID |
| --- | --- | --- | --- | --- | --- |
| `keysight-dsox2004a` | Keysight Technologies | DSOX2004A | 2000X | `keysight-infiniivision-2000x` | `keysight-infiniivision` |
| `keysight-dsox3024a` | Keysight Technologies | DSOX3024A | 3000X | `keysight-infiniivision-3000x` | `keysight-infiniivision` |
| `keysight-dsox4024a` | Keysight Technologies | DSOX4024A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |
| `keysight-dsox4034a` | Keysight Technologies | DSOX4034A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |

Canonical registration identifies a physical model. Each registered model
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

Math support is instrument-side only. Canonical operation and source names
remain independent of raw SCPI readbacks.

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

Bus timing and bus state are not supported because the required MSO/digital-
channel foundation is not available. They are absent from enabled capability
operations, CLI choices, Worker commands, Core builders, and simulator behavior.

- BYTE and WORD waveform capture with a conservative 10,000-point safe maximum.
- Read-only measurement helpers and screenshot capture.
- Measurement control helpers for clearing measurements, enabling or
  querying measurement markers, selecting analog measurement sources, and
  selecting the MAIN, ZOOM, AUTO, or GATE measurement window. ZOOM is
  conditional on the zoomed timebase already being displayed; AUTO is safer
  when that state is unknown. A source1-only write may preserve source2 in
  instrument readback.
- Reference waveform helpers for runtime-managed reference waveform
  slots 1 and 2. The instrument may turn off one slot's display when the other
  is enabled.
- DVM helpers for enable, analog source, `dc`, `dc-rms`, and
  `ac-rms` voltage modes, auto range, current voltage, and aggregate queries.
  DVM can be option/license dependent. It does not support DVM frequency,
  independent `:COUNter`, or `:MEASure:COUNter` support.
- DEMO output aggregate and focused output/function/phase helpers.
  DEMO is option-/hardware-dependent; capability profiles guard the documented
  function names before session open, while live instrument errors remain
  authoritative for missing options or hardware.
- Waveform generator output, function, frequency, amplitude, offset, load, and
  aggregate query helpers. The 2000X/3000X profiles use `:WGEN`; the 4000X
  profile uses only generator 1 through `:WGEN1`. Settable functions are
  `sine`, `square`, `ramp`, `pulse`, `noise`, and `dc`.
- Serial bus aggregate query, mode, and display controls plus UART, I2C, SPI,
  and CAN basic protocol settings. Capability profiles
  guard bus count and settable modes. Serial decode can require an
  instrument license; Core does not probe licenses and preserves instrument
  errors for unavailable hardware or options.
- Serial trigger support provides the documented common I2C, SPI, and CAN trigger
  subset on the same capability profiles. It does not add a capability field;
  model profiles continue to guard bus count and protocol mode availability.
- Waveform search state and count queries plus profile-guarded mode
  configuration. Unsupported modes are rejected before search SCPI is sent.
- Instrument-side SAVE commands for current save
  directory and base name, image settings and start, and waveform settings and
  start. All three profiles also expose the query-only maximum-length mode
  readback. The configured waveform length minimum is 100 points; the actual
  maximum remains instrument/model dependent.
- Analog channel labels, display labels, and display annotation.
- Core/CLI/simulator/worker support for the documented one-shot trigger
  commands, including `trigger-tv` basic TV / video trigger configure and
  query.
- Triggered capture wait classification for DSO-X 2000X/3000X/4000X using the
  Operation Status Condition Run bit.

Series-specific differences:

| Series | DEMO output functions | Serial buses | Serial settable modes | Waveform search modes | Screenshot formats |
| --- | --- | ---: | --- | --- | --- |
| 2000X | Common/core set | 1 | `can`, `i2c`, `lin`, `spi`, `uart` | `serial1` | No; existing PNG capture remains supported |
| 3000X | Common/core set plus `i2s`, `can-lin`, `flexray`, `arinc`, `mil`, `mil2` | 2 | `a429`, `flexray`, `can`, `i2s`, `i2c`, `lin`, `m1553`, `spi`, `uart` | `edge`, `glitch`, `runt`, `transition`, `serial1`, `serial2` | No; existing PNG capture remains supported |
| 4000X | Same documented set as 3000X | 2 | `a429`, `flexray`, `can`, `cxpi`, `i2s`, `i2c`, `lin`, `m1553`, `manchester`, `nrz`, `sent`, `spi`, `uart`, `usb`, `usb-pd` | `edge`, `glitch`, `runt`, `transition`, `serial1`, `serial2`, `peak` | PNG, BMP, BMP8bit, appearance controls, and state query |

The common/core DEMO set is `sine`, `noisy`, `phase`, `lf-sine`, `am`,
`rf-burst`, `fm-burst`, `harmonics`, `coupling`, `ringing`, `single`, `clock`,
`runt`, `transition`, `setup-hold`, `mso`, `burst`, `glitch`,
`edge-then-edge`, `i2c`, `uart`, `spi`, `can`, and `lin`. The documented DEMO
function set excludes additional 4000X-only functions. It does not include WGEN
behavior and adds no WebUI runtime behavior.

Screenshot format support is capability-gated to 4000X because its explicit
format transfer uses the documented `:HCOPY:SDUMp` command family.

All three profiles support `search-state` and query-only `search-count`.
`search-mode` enables search before setting the mode. Search event navigation is supported on 4000X via `search-event`.
Serial Search provides protocol-specific search controls for UART, I2C, SPI,
and CAN. 2000X supports bus 1; 3000X and 4000X support buses 1 and 2. The
selected Serial bus must be configured with the matching Serial command first.

- 2000X and 3000X channel labels allow up to 10 printable ASCII characters.
- 4000X channel labels allow up to 32 printable ASCII characters.
- 2000X and 3000X annotation uses one unindexed slot and does not support X/Y
  annotation position.
- 4000X annotation supports indexed slots 1 through 10 and X/Y annotation
  position.
- 4000X supports the guarded `delay` pair measurement path. 2000X and 3000X do
  not expose that helper because their delay query depends on measurement
  definition state.

Raw waveform points mode remains disabled. Segmented memory query, explicit
mode/count configuration, and the finite single-channel `segmented-capture`
workflow are available for the registered 2000X, 3000X, and 4000X profiles.
The documented count ranges are 2-250 on 2000X and 2-1000 on 3000X/4000X,
while the actual maximum may be lower for the selected memory depth.
Segmented-memory availability may depend on an SGM option or license; the
capability flag permits this documented command-family path but does not claim
that the option is installed. Segmented capture does not perform continuous
acquisition, restore state, disable segmented mode, force a trigger, merge CSVs,
or perform instrument-side save/export. Serial
decode capability represents command-family availability, not the presence of
an instrument license.

Serial aggregate responses remain raw. Serial protocol configuration provides
only basic UART, I2C, SPI, and CAN source/decode settings. Serial Lister adds
global display/reference controls and host-side raw CSV export through
`:LISTer:DATA?`; it does not support protocol-specific CSV
parsing, or instrument-side `:SAVE:LISTer`. Serial Search provides
protocol-specific UART, I2C, SPI, and CAN search controls after the matching
Serial bus has been configured. Lister display selection `bus2` is unavailable
on 2000X and available on 3000X/4000X; `all` remains valid on 2000X.
