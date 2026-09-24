# Tektronix existing-operation support matrix

## Scope

This integration reuses the existing scopes-tool product surface. The decision here is which existing operations can be enabled for each Tektronix model; new instrument-specific product features are out of scope. This is a manual-based support boundary, not a claim of implemented or live-validated support. The current identity registry and driver still recognize Keysight models only. A WebUI command's default visibility is not evidence of Tektronix support.

The authorities are the Tektronix [TBS2000B Series Programmer Manual, 077-1149-04](https://download.tek.com/manual/TBS2000B-Programmer-Manual-EN-US-077114904.pdf) (B2 below) and [TBS1000/B/EDU, TDS2000/B/C and related Series Programmer Manual, 077-0444-03 Rev B](https://download.tek.com/manual/TBS1000-B-EDU-TDS2000-B-C-TDS1000-B-C-EDU-TDS200-TPS2000-B-Programmer-077044403_RevB.pdf) (B1 below). Command names in the last column identify the manual evidence; model conditions in B1 apply to the named family, not every model covered by that manual.

`SUPPORTED` means a documented equivalent can satisfy the stated existing operation after a Tek implementation. `UNSUPPORTED` means no safe equivalent for that operation or its contract. `LIVE-CONFIRM` means the manual describes a candidate but the item stays disabled until the remaining detail is confirmed on real hardware. A supported subset does not enable other options in the same command.

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
| Single acquisition / wait (`single-wait`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2/B1 `*OPC`, `ACQuire:STATE`; confirm bounded trigger-completion and timeout behavior. |
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
| Channel probe attenuation, bandwidth limit, invert (`channel-probe`, `channel-bandwidth-limit`, `channel-invert`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `CH<x>:PRObe`, `CH<x>:BANdwidth`, `CH<x>:INVert`; allowed ratios and limit values are model-specific. |
| Channel label (`channel-label`) | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `CH<x>:LABel`; no B1 equivalent for the current label control. |
| Channel units (`channel-units`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2/B1 `CH<x>:YUNit` or probe-unit readbacks; confirm set/query behavior and V/A normalization. |
| Channel summary (`channel-summary`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | Aggregates nullable channel fields; confirm omitted fields and readback normalization, especially offset. |
| Channel probe skew (`channel-probe-skew`) | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `CH<x>:DESKew` uses seconds with the current -100 to +100 ns range; B1 has no equivalent. |
| Channel range, impedance, vernier (`channel-range`, `channel-impedance`, `channel-vernier`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Current full-scale-range, selectable 50-ohm impedance, and vernier contracts lack a documented equivalent. |
| Display persistence (`display-persistence`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2 `DISplay:PERSistence:STATe/VALUe`; B1 `DISplay:PERSistence`. Confirm current modes/timing semantics. |
| Display vectors (`display-vectors`) | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 `DISplay:STYle` selects dots/vectors; B2 has no matching vector control. |
| Display label, clear, waveform intensity (`display-label`, `display-clear`, `display-intensity`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 backlight and B1 brightness are not the current waveform-intensity control; other controls lack matching contracts. |
| Direct basic measurements (`measure`, `measure-sweep`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `MEASUrement:IMMed:TYPe/VALue?` cover a model-specific subset, such as frequency, period, peak-to-peak, min/max, rise/fall. Only names with matching definitions/units may be mapped. |
| Front-panel measurement install/source/clear (`measure-install`, `measure-source`, `measure-clear`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2/B1 `MEASUrement:MEAS<x>`, source and state commands; confirm slot, clear, and readback semantics. |
| Measurement results dump, menu/show, statistics, window (`measure-results`, `measure-menu`, `measure-show`, `measurement-statistics`, `measure-window`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek measurement/gating/status facilities do not establish the existing aggregate, marker, statistics, or MAIN/ZOOM/AUTO/GATE contracts. |
| Waveform BYTE (`capture`, 1,000 points) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `DATa:SOUrce`, `DATa:ENCdg`, `DATa:WIDth 1`, `CURVe?`; B2 `WFMOutpre?`, B1 `WFMPre?`. Transfer requires a displayed source. |
| Waveform BYTE at 5,000/10,000 points | LIVE-CONFIRM | UNSUPPORTED | UNSUPPORTED | B2 `DATa:STARt/STOP` and record length require exact-point confirmation; B1 legacy record lengths cannot satisfy these current point choices. |
| Waveform WORD (`capture`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2/B1 `DATa:WIDth 2`, `CURVe?`; B2 `WFMOutpre?`, B1 `WFMPre?`. Both manuals describe 8-bit acquisition data padded in 16-bit transfer. Confirm signedness, byte order, scaling, and current point choices. |
| Host screenshot (`screenshot`) | UNSUPPORTED | LIVE-CONFIRM | LIVE-CONFIRM | B2 `SAVe:IMAge` writes instrument storage, not host image bytes. B1 `HARDCopy` may stream an image; confirm transport, format, and host PNG/BMP contract. |
| Reference save/display/query (`reference-save`, `reference-display`, `reference-query`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `SAVe:WAVEform`, `SELect:REF<x>`, `REF<x>?`; slot names and counts differ. |
| Reference label/clear (`reference-label`, `reference-clear`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No equivalent label and explicit clear contract established by B2/B1. |
| Instrument save directory (`save-pwd`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `FILESystem:CWD`; this is only the existing working-directory setting, not a file manager. |
| Instrument image/waveform save and format (`save-image`, `save-image-format`, `save-waveform`, `save-waveform-format`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2/B1 `SAVe:IMAge`, `SAVe:IMAge:FILEFormat`, `SAVe:WAVEform`, `SAVe:WAVEform:FILEFormat`; confirm storage/path, supported format subset, and completion behavior. |
| Other instrument save settings (`save-filename`, `save-image-palette`, `save-image-ink-saver`, `save-image-factors`, `save-waveform-length`, `save-waveform-length-max`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No matching current base-name, palette, image-factor, and waveform-length/max-length contract in B2/B1. |
| Setup save/recall (`setup-save`, `setup-recall`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `SAVe:SETUp`, `RECAll:SETUp`, `*SAV`, `*RCL`; slots are 1-10 and files use Tek paths and `.SET`, not current Keysight 0-9/`.scp` rules. |
| Standard status / OPC (`system-status-byte`, `system-clear-status`, `system-opc`, `system-standard-event`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `*STB?`, `*CLS`, `*OPC?`, `*ESR?`. |
| Error/event queue (`check-error`) | SUPPORTED | SUPPORTED | SUPPORTED | B2/B1 `ALLEv?`, `EVENT?`, `EVMsg?` with IEEE event status; requires Tek-specific draining and normalization. |
| Operation status and options (`system-operation-status`, `system-options`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | B2/B1 do not document equivalents for the current operation-status register and installed-options result contracts. |
| Edge trigger, mode/sweep, holdoff (`trigger-edge`, `trigger-edge-source`, `trigger-edge-slope`, `trigger-edge-level`, `trigger-edge-coupling`, `trigger-mode`, `trigger-sweep`, `trigger-holdoff`) | SUPPORTED | SUPPORTED | SUPPORTED | B2 `TRIGger:A:*`; B1 `TRIGger:MAIn:*`; only common source/slope/coupling/mode values and documented holdoff ranges. |
| Pulse-width trigger (`trigger-pulse-width`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2 `TRIGger:A:PULse:WIDth:*`; B1 `TRIGger:MAIn:PULse:*`; confirm qualifiers, thresholds, and range against the current command. |
| External trigger range/level/probe/units/settings (`external-trigger-*`, `trigger-edge-external-level`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek external source support does not establish the current Keysight-specific range, probe, units, and level contract. |
| Other advanced trigger families (`trigger-runt`, `trigger-transition`, `trigger-delay`, `trigger-setup-hold`, `trigger-edge-burst`, `trigger-tv`, `trigger-pattern`, `trigger-or`, `trigger-noise-reject`, `trigger-hf-reject`, `trigger-edge-reject`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Some Tek trigger modes exist, but their complete existing parameter/readback contracts are not established by these manuals. |
| Manual cursor read/set/off (`cursor*`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2/B1 `CURSor:*`; confirm current X/Y units, delta readbacks, and mode mapping. Automatic vertical/timebase adjustment variants remain disabled. |
| Basic Math and FFT (`math-display`, `math-operator`, `fft`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | B2/B1 `MATH:DEFINE`, `SELect:MATH`; B1 TBS1000B FFT has a separate `FFT:*` dialect. Confirm exact operator/window and readback subsets. |
| Advanced Math controls (`math-vertical`, `math-transform`, `math-filter`, `math-visualization`, `math-composite-source`, `math-clear`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | The existing transform/filter/visualization/function-slot contract is not represented by the documented basic Tek Math operations. |
| Annotation (`annotation*`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No matching existing annotation-slot contract. |
| DVM, WGEN, DEMO (`dvm-*`, `wgen-*`, `demo-*`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No equivalent existing feature-family contract for these Tek profiles. |
| Serial, Search, Segmented Memory (`serial-*`, `search-*`, `segmented-*`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Keep these existing feature families disabled for all three profiles. |
| Host device/status/diagnostic views (`list-resources`, `live-data-snapshot`, `system-information-snapshot`, `doctor`, `smoke`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | Host compositions depend on supported identity, status, capture, screenshot, and error operations; confirm each composite's actual dependencies. |
| Capture and measurement workflows (`capture-batch`, `capture-until`, `capture-monitor`, `measure-log`, `measure-until`, `triggered-measure-loop`, `triggered-capture-series`, `sequence`) | LIVE-CONFIRM | LIVE-CONFIRM | LIVE-CONFIRM | Existing host workflows compose acquisition, trigger wait, measurement, waveform, screenshot, and status. Enable only variants whose complete dependency chain is supported and live-confirmed. |

## Important semantic differences

- Tek acquisition uses `ACQuire:STATE` and `ACQuire:STOPAfter`; it cannot reuse Keysight `:RUN`, `:STOP`, or `:SINGle` assumptions. B1 recommends `*OPC` to detect single-sequence completion.
- Tek waveform transfer uses `DATa:*`, `WFMPre?` (or model-specific output preamble queries), and `CURVe?`, not Keysight `:WAVeform:*`. Both manuals describe 16-bit transfer of padded 8-bit data; this is not a promise of 16-bit acquisition resolution.
- Tek errors/events use `*ESR?`, `ALLEv?`, `EVENT?`, and `EVMsg?`, not `:SYSTem:ERRor?`. Reading status/events can clear them.
- Measurement types and returned units need Tek-specific mapping to scopes-tool canonical names. Similar names do not establish identical semantics, especially RMS, duty, phase, delay, and area.
- B2 `CH<x>:OFFSet` is a real voltage offset and is distinct from `CH<x>:POSition` in divisions. B1 has the latter only; no position-to-offset conversion is justified by the existing offset contract.
- B2 horizontal position is a percentage of record, while B1 main horizontal position is seconds relative to center. Do not force-map B2 to the current seconds field.
- Tek setup slots are 1-10 and file names/paths use Tek storage rules and `.SET`. The current Keysight slot and `.scp` validation cannot be reused. Instrument-side save is distinct from returning a host screenshot or managing arbitrary instrument files.

## P1 implementation inputs

- Model/family identity: TBS2074B/TBS2000B (4 channels), TDS2024B/TDS2000B (4), TBS1052B/TBS1000B (2).
- The supported existing operations and restricted option subsets in the matrix.
- Model-specific differences in acquisition modes/counts, channel offset and skew, timebase position, waveform length, Math/FFT, and storage.
- Tek SCPI implementations for enabled acquisition, autoscale, channel, timebase, display, trigger, measurement, waveform, reference, instrument save, setup, status, and error operations.
- All `LIVE-CONFIRM` rows remain disabled until real-hardware evidence resolves their listed detail.
