# Tektronix existing-operation support matrix

## Scope

This compatibility contract limits Tektronix integration to the existing scopes-tool product surface. It defines which existing operations and canonical options may be enabled for each model; it does not assert that a Tektronix driver is present. A WebUI command's default visibility is not evidence of Tektronix support.

The authorities are the Tektronix [TBS2000B Series Programmer Manual, 077-1149-04](https://download.tek.com/manual/TBS2000B-Programmer-Manual-EN-US-077114904.pdf) (B2 below) and [TBS1000/B/EDU, TDS2000/B/C and related Series Programmer Manual, 077-0444-03 Rev B](https://download.tek.com/manual/TBS1000-B-EDU-TDS2000-B-C-TDS1000-B-C-EDU-TDS200-TPS2000-B-Programmer-077044403_RevB.pdf) (B1 below). Command names in the last column identify the manual evidence; model conditions in B1 apply to the named family, not every model covered by that manual.

`SUPPORTED` means the documented equivalent satisfies the stated existing-operation contract and may be implemented for that model. `UNSUPPORTED` means the operation must remain disabled because no safe equivalent is established. A supported subset does not enable other options in the same command. Where a row has supported and unsupported options, only the explicitly listed subset is allowed.

## Target models

| Model | Family | Analog channels |
| --- | --- | ---: |
| TBS2074B | TBS2000B | 4 |
| TDS2024B | TDS2000B | 4 |
| TBS1052B | TBS1000B | 2 |

## Existing-operation support matrix

Rows cover the command families in `src/scopes_tool_webui/command_catalog.py`, including hidden commands. Presentation-only editors (`acquisition-control`, `channel-scale-range`, `external-trigger-range-level`, `front-panel-measurements`, `reference-waveform`, `reference-labels`, `system-information`, `diagnostics`, and `serial-decode`/`serial-trigger`/`serial-lister`) inherit the underlying rows. Related CLI variants have the same boundary. `B2` and `B1` refer to the manuals above. Host-only outputs are conditional on their listed instrument primitives; they do not independently establish hardware support.

| Existing operation / command group | TBS2074B | TDS2024B | TBS1052B | Manual basis or boundary |
| --- | --- | --- | --- | --- |
| Identify (`identify`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `*IDN?`. |
| Run / stop (`run`, `stop-acquisition`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `ACQuire:STATE`, `ACQuire:STOPAfter`. |
| Single acquisition (`single`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `ACQuire:STOPAfter SEQuence`, `ACQuire:STATE`. |
| Single acquisition / wait (`single-wait`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 `*OPC`, `ACQuire:STATE` are candidate primitives, but the existing bounded trigger-completion and timeout contract is not established. |
| Force trigger (`force-trigger`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `TRIGger FORCe`; the instrument must be in a suitable armed state. |
| Acquisition mode: sample, peak detect, average (`acquisition`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `ACQuire:MODe`. `high_resolution` is B2-only; B1 has no equivalent. |
| High-resolution acquisition option | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `ACQuire:MODe HIRes`; absent from B1 mode choices. |
| Averaging count option | SUPPORTED | SUPPORTED | SUPPORTED | B2 `ACQuire:NUMAVg`: powers of two, 2-512. B1: 4, 16, 64, 128. Other current UI values remain disabled. |
| Bare autoscale (`autoscale`, no options) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `AUTOSet`; this state does not cover the command's optional controls. |
| Autoscale channel/acquisition-mode options | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 `AUTOSet` has no documented equivalent for these current options. |
| Main timebase scale (`timebase-scale`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `HORizontal[:MAIn]:SCAle`, seconds/division. |
| Main timebase position in seconds (`timebase-position`) | UNSUPPORTED | SUPPORTED | SUPPORTED | B2 `HORizontal:POSition` uses percent of record; B1 `HORizontal:MAIn:POSition` uses seconds relative to center. |
| Main timebase reference (`timebase-reference`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No documented left/center/right equivalent to the current control. |
| Channel display, scale, coupling (`channel-display`, `channel-scale`, `channel-coupling`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `SELect:CH<x>`, `CH<x>:SCAle`, `CH<x>:COUPling`. Channel indices are bounded by the model table. |
| Channel voltage offset (`channel-offset`) | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `CH<x>:OFFSet` is a voltage acquisition-window offset. B1 has `CH<x>:POSition` in divisions, not voltage offset. |
| Channel probe attenuation, bandwidth limit, invert (`channel-probe`, `channel-bandwidth-limit`, `channel-invert`) | SUPPORTED | SUPPORTED | SUPPORTED | B2 probe set/query uses `CH<x>:PRObe:GAIN`; `CH<x>:PRObe?` is probe information only. Tek gain is output/input, so public attenuation `ratio = 1 / gain`: ratio 10 maps to `CH1:PROBE:GAIN 0.1`. B2 gain values depend on the attached probe. B1 `CH<x>:PRObe` accepts attenuation ratios 1, 10, 20, 50, 100, 500, 1000 on these families; other public ratios are excluded. B2 `CH<x>:BANdwidth` maps enabled to `TWEnty` (20 MHz) and disabled to `FULl`; B1 maps enabled/disabled to `ON`/`OFF`. B2/B1 `CH<x>:INVert` maps to `ON`/`OFF`. |
| Channel label (`channel-label`) | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `CH<x>:LABel`; no B1 equivalent for the current label control. |
| Channel units (`channel-units`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 `CH<x>:YUNit` or probe-unit readbacks do not establish the current set/query and V/A normalization contract. |
| Channel summary (`channel-summary`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | The aggregate includes channel fields without an established Tek readback mapping, including offset on B1. |
| Channel probe skew (`channel-probe-skew`) | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `CH<x>:DESKew` uses seconds with the current -100 to +100 ns range; B1 has no equivalent. |
| Channel range, impedance, vernier (`channel-range`, `channel-impedance`, `channel-vernier`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Current full-scale-range, selectable 50-ohm impedance, and vernier contracts lack a documented equivalent. |
| Display persistence (`display-persistence`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `DISplay:PERSistence:STATe/VALUe` and B1 `DISplay:PERSistence` do not establish the current modes/timing semantics. |
| Display vectors (`display-vectors`) | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 `DISplay:STYle` selects dots/vectors; B2 has no matching vector control. |
| Display label, clear, waveform intensity (`display-label`, `display-clear`, `display-intensity`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 backlight and B1 brightness are not the current waveform-intensity control; other controls lack matching contracts. |
| Direct basic measurements (`measure`, `measure-sweep`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `MEASUrement:IMMed:SOUrce[1]`, `TYPe`, `VALue?`; only the explicit canonical item subsets below are allowed. `measure-sweep` may compose only these direct items. |
| Front-panel measurement install/source/clear (`measure-install`, `measure-source`, `measure-clear`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 `MEASUrement:MEAS<x>` and source/state commands do not establish the existing slot, clear, and readback contract. |
| Measurement results dump, menu/show, statistics, window (`measure-results`, `measure-menu`, `measure-show`, `measurement-statistics`, `measure-window`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek measurement/gating/status facilities do not establish the existing aggregate, marker, statistics, or MAIN/ZOOM/AUTO/GATE contracts. |
| Waveform BYTE (`capture`, 1,000 points) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `DATa:SOUrce`, `DATa:ENCdg`, `DATa:WIDth 1`, `CURVe?`; B2 `WFMOutpre?`, B1 `WFMPre?`. Transfer requires a displayed source. |
| Waveform BYTE at 5,000/10,000 points | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `DATa:STARt/STOP` and record length do not establish exact current point choices; B1 legacy record lengths cannot satisfy them. |
| Waveform WORD (`capture`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 `DATa:WIDth 2`, `CURVe?`; B2 `WFMOutpre?`, B1 `WFMPre?`. The manuals describe 8-bit acquisition data padded in 16-bit transfer, without an established signedness, byte order, scaling, and point-choice mapping for the current contract. |
| Host screenshot (`screenshot`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `SAVe:IMAge` writes instrument storage, not host image bytes. B1 `HARDCopy` does not establish the existing host PNG/BMP transport and format contract. |
| Reference save/display (`reference-save`, `reference-display`) | SUPPORTED | SUPPORTED | SUPPORTED | Public slots 1/2 map to B2 `REF1`/`REF2`, and to B1 `REFA`/`REFB`; use `SAVe:WAVEform` and `SELect:REF<x>` with the family-specific location. Additional legacy reference locations, including `REFC`/`REFD`, are not exposed by this integration. |
| Reference aggregate query (`reference-query`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | The current aggregate includes a label readback; B2/B1 reference display queries alone cannot satisfy it. |
| Reference label/clear (`reference-label`, `reference-clear`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No equivalent label and explicit clear contract established by B2/B1. |
| Instrument save directory (`save-pwd`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `FILESystem:CWD`; this is only the existing working-directory setting, not a file manager. |
| Instrument image/waveform save and format (`save-image`, `save-image-format`, `save-waveform`, `save-waveform-format`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 `SAVe:IMAge`, `SAVe:IMAge:FILEFormat`, `SAVe:WAVEform`, `SAVe:WAVEform:FILEFormat` do not establish the existing storage/path, format, and completion contract. |
| Other instrument save settings (`save-filename`, `save-image-palette`, `save-image-ink-saver`, `save-image-factors`, `save-waveform-length`, `save-waveform-length-max`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No matching current base-name, palette, image-factor, and waveform-length/max-length contract in B2/B1. |
| Setup save/recall (`setup-save`, `setup-recall`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `SAVe:SETUp`, `RECAll:SETUp`, `*SAV`, `*RCL`; only the common public slot subset 1-9 is allowed. Tek slot 10 and public slot 0 are not mapped; file targets are unsupported because Tek paths/`.SET` do not satisfy the current `.scp` file contract. |
| Standard status / OPC (`system-status-byte`, `system-clear-status`, `system-opc`, `system-standard-event`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `*STB?`, `*CLS`, `*OPC?`, `*ESR?`. |
| Error/event queue (`check-error`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `ALLEv?`, `EVENT?`, `EVMsg?` with IEEE event status; requires Tek-specific draining and normalization. |
| Operation status and options (`system-operation-status`, `system-options`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 do not document equivalents for the current operation-status register and installed-options result contracts. |
| Edge trigger, mode/sweep, holdoff (`trigger-edge`, `trigger-edge-source`, `trigger-edge-slope`, `trigger-edge-level`, `trigger-edge-coupling`, `trigger-mode`, `trigger-sweep`, `trigger-holdoff`) | SUPPORTED | SUPPORTED | SUPPORTED | B2 `TRIGger:A:*`; B1 `TRIGger:MAIn:*`. Only the explicit canonical subsets below are allowed. |
| Pulse-width trigger (`trigger-pulse-width`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `TRIGger:A:PULse:WIDth:*` and B1 `TRIGger:MAIn:PULse:*` do not establish the current qualifier, threshold, and range contract. |
| External trigger range/level/probe/units/settings (`external-trigger-*`, `trigger-edge-external-level`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek external source support does not establish the current Keysight-specific range, probe, units, and level contract. |
| Other advanced trigger families (`trigger-runt`, `trigger-transition`, `trigger-delay`, `trigger-setup-hold`, `trigger-edge-burst`, `trigger-tv`, `trigger-pattern`, `trigger-or`, `trigger-noise-reject`, `trigger-hf-reject`, `trigger-edge-reject`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Some Tek trigger modes exist, but their complete existing parameter/readback contracts are not established by these manuals. |
| Manual cursor read/set/off (`cursor*`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 `CURSor:*` do not establish current X/Y units, delta readbacks, and mode mapping. Automatic vertical/timebase adjustment variants remain disabled. |
| Basic Math and FFT (`math-display`, `math-operator`, `fft`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 `MATH:DEFINE`, `SELect:MATH`; B1 TBS1000B FFT has a separate `FFT:*` dialect. The current operator/window and readback contracts are not established. |
| Advanced Math controls (`math-vertical`, `math-transform`, `math-filter`, `math-visualization`, `math-composite-source`, `math-clear`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | The existing transform/filter/visualization/function-slot contract is not represented by the documented basic Tek Math operations. |
| Annotation (`annotation*`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No matching existing annotation-slot contract. |
| DVM, WGEN, DEMO (`dvm-*`, `wgen-*`, `demo-*`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No equivalent existing feature-family contract for these Tek profiles. |
| Serial, Search, Segmented Memory (`serial-*`, `search-*`, `segmented-*`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Keep these existing feature families disabled for all three profiles. |
| Host device/status/diagnostic views (`list-resources`, `live-data-snapshot`, `system-information-snapshot`, `doctor`, `smoke`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | These host compositions have dependencies outside the supported Tek subset, including screenshot and aggregate channel/status readbacks. |
| Capture and measurement workflows (`capture-batch`, `capture-until`, `capture-monitor`, `measure-log`, `measure-until`, `triggered-measure-loop`, `triggered-capture-series`, `sequence`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | The complete existing dependency chains are not established, including bounded trigger wait, item restrictions, waveform choices, and screenshot paths. |

## Direct measurement item boundary

The canonical item names below are from `scopes_tool_core.measurements`. Each allowed item uses an analog channel as `MEASUrement:IMMed:SOUrce[1]`, a matching immediate `TYPe`, and `VALue?`; no front-panel measurement slot is involved. `measure-sweep` inherits the same per-model item set for each channel. Its current default item list includes unsupported `vrms`, so a Tek invocation requires an explicit allowed item list. Every canonical item absent from a model's supported cell is `UNSUPPORTED` for that model. A direct item does not authorize measurement window, gating, or statistics controls.

| Model | Supported direct single-source canonical items | Supported pair/two-source items | Supported parameterized items |
| --- | --- | --- | --- |
| TBS2074B (CH1-CH4) | `vpp`, `frequency`, `period`, `minimum`, `maximum`, `rise_time`, `fall_time`, `positive_width`, `negative_width` | None | None |
| TDS2024B (CH1-CH4) | `vpp`, `frequency`, `period`, `minimum`, `maximum` | None | None |
| TBS1052B (CH1-CH2) | `vpp`, `frequency`, `period`, `minimum`, `maximum`, `rise_time`, `fall_time`, `positive_width`, `negative_width` | None | None |

B2 immediate types are `PK2Pk`, `FREQuency`, `PERIod`, `MINImum`, `MAXimum`, `RISe`, `FALL`, `PWIdth`, and `NWIdth` for the TBS2074B set. B1 documents the five TDS2024B types directly; its rise/fall/width types depend on a TDS2MM measurement module, so they are not in the unconditional TDS2024B subset. B1 documents the larger TBS1000B type set for TBS1052B. These mappings use the documented peak, cycle, first-edge, 10%-90%, and 50%-width definitions, rather than matching type names alone.

All other canonical single-source items are `UNSUPPORTED`: `vavg`, `vrms`, `ac_rms`, `x_at_max`, `x_at_min`, `amplitude`, `top`, `base`, `overshoot`, `preshoot`, `duty_cycle`, `negative_duty_cycle`, `area`, `positive_edges`, `negative_edges`, `positive_pulses`, and `negative_pulses`. In particular, Tek whole-record/cycle RMS, mean, high/low/amplitude, duty, area, and count definitions do not establish equivalence to the current query and result contracts. The parameterized `y_at_x`, `time_at_edge`, and `time_at_value` are `UNSUPPORTED` on all three models: no immediate equivalent accepts the public time or level and slope/occurrence parameters. The pair items `phase` and `delay` are `UNSUPPORTED` on all three models. B2 has `MEASUrement:IMMed:SOUrce2` and phase/delay candidate types, but their direction, edge, and reference semantics do not establish the current direct pair contracts. B1 limits `MEASUrement:IMMed:SOURCE2` to TPS2000B/TPS2000 with the TPS2PWR1 module; listing `PHAse` or `DELay` in a B1 type list does not provide the required direct two-channel source contract for TDS2024B or TBS1052B. Canonical aliases inherit only their mapped canonical item's status.

## Trigger option boundary

`trigger-mode` is the canonical trigger *type*, distinct from Tek `TRIGger:A:MODe` or `TRIGger:MAIn:MODe`, which implement the public `trigger-sweep`. Pulse width and other trigger families keep their own operation status in the matrix; they are not enabled by the generic type option.

| Existing option or operation | TBS2074B | TDS2024B | TBS1052B | Manual basis or boundary |
| --- | --- | --- | --- | --- |
| `trigger-mode` | `edge` only | `edge` only | `edge` only | B2 `TRIGger:A:TYPe EDGE`; B1 `TRIGger:MAIn:TYPe EDGE`. All other current canonical types are excluded. |
| `trigger-sweep` | `auto`, `normal` | `auto`, `normal` | `auto`, `normal` | B2 `TRIGger:A:MODe`; B1 `TRIGger:MAIn:MODe`. |
| `trigger-edge-source` | `analog-channel` CH1-CH4 only | `analog-channel` CH1-CH4 only | `analog-channel` CH1-CH2 only | B2 `TRIGger:A:EDGE:SOUrce`; B1 `TRIGger:MAIn:EDGE:SOUrce`. Public `external` is excluded because its complete range/level/probe contract is not established; `line` is excluded because its level cannot be set. B2 AUX is not a public option. |
| `trigger-edge-slope`, `trigger-edge` slope | `positive`, `negative` | `positive`, `negative` | `positive`, `negative` | B2/B1 `RISe`/`FALL`. Public `either`/`alternate` are excluded. |
| `trigger-edge-coupling` | `dc`, `lf-reject` | `ac`, `dc`, `lf-reject` | `ac`, `dc`, `lf-reject` | B2 has no `AC` coupling; B1 has it. Tek `HFRej`/`NOISErej` do not enable other public trigger commands. |
| `trigger-edge-level`, `trigger-edge` source/level | Analog channels only | Analog channels only | Analog channels only | B2 `TRIGger:A:LEVel`; B1 `TRIGger:MAIn:LEVel`, in volts. AC LINE ignores level setting, so it is excluded from the combined edge operation. |
| `trigger-holdoff` | 40 ns to 8 s | 500 ns to 10 s | 500 ns to 10 s | B2 `TRIGger:A:HOLDOff:TIMe` documents 20 ns to 8 s, intersected with the public 40 ns to 10 s range; B1 `TRIGger:MAIn:HOLDOff:VALue` documents 500 ns to 10 s. Both set/query in seconds. |

## Important semantic differences

- Tek acquisition uses `ACQuire:STATE` and `ACQuire:STOPAfter`; it cannot reuse Keysight `:RUN`, `:STOP`, or `:SINGle` assumptions. B1 recommends `*OPC` to detect single-sequence completion.
- Tek waveform transfer uses `DATa:*`, `WFMPre?` (or model-specific output preamble queries), and `CURVe?`, not Keysight `:WAVeform:*`. Both manuals describe 16-bit transfer of padded 8-bit data; this is not a promise of 16-bit acquisition resolution.
- Tek errors/events use `*ESR?`, `ALLEv?`, `EVENT?`, and `EVMsg?`, not `:SYSTem:ERRor?`. Reading status/events can clear them.
- Measurement types and returned units use the direct item boundary above. Similar names alone do not establish identical semantics, especially RMS, duty, phase, delay, and area.
- B2 `CH<x>:OFFSet` is a real voltage offset and is distinct from `CH<x>:POSition` in divisions. B1 has the latter only; no position-to-offset conversion is justified by the existing offset contract.
- B2 horizontal position is a percentage of record, while B1 main horizontal position is seconds relative to center. Do not force-map B2 to the current seconds field.
- Tek setup slots are 1-10 and file names/paths use Tek storage rules and `.SET`. The current Keysight slot and `.scp` validation cannot be reused. Instrument-side save is distinct from returning a host screenshot or managing arbitrary instrument files.
