# Tektronix existing-operation support matrix

## Scope and decision rules

This document defines hardware compatibility with the **existing** Scopes Tool public contracts. It is not an implementation-status table. A driver method, simulator response, capability flag, or WebUI visibility setting does not establish hardware support. The models covered are TBS2074B (four analog channels), TDS2024B (four analog channels), and TBS1052B (two analog channels).

- **SUPPORTED**: the operation and explicitly listed existing option subset satisfy the public contract, including required readback and completion. Other options remain unsupported; a subset never introduces a Tek-only enum.
- **PARTIAL AGGREGATE**: an existing read-only projection can return useful fields while representing unavailable fields using its existing null/unknown/omitted-value convention. Unsupported queries must be skipped, not attempted and caught. This does not authorize partial setters, artifacts, measurements, or workflows.
- **UNSUPPORTED**: a required semantic or result cannot be supplied. Multiple fields alone do not make a result nullable. A mandatory readback cannot be replaced by an invented value, an echoed setter argument, or an empty string presented as hardware state.

Inputs must satisfy both public validation and documented hardware limits. Raw fields retain actual instrument responses. Unrecognized or out-of-subset instrument state must not be normalized into a supported value. Supported actions still report instrument errors, unavailable waveforms, missing storage, and timeouts; support does not guarantee success in every instrument state.

## Authorities and public surface

References use printed page numbers:

- **B2**: [TBS2000B Series Programmer Manual, 077-1149-04](https://download.tek.com/manual/TBS2000B-Programmer-Manual-EN-US-077114904.pdf), for TBS2074B.
- **B1**: [TBS1000/B/EDU, TDS2000/B/C and related Series Programmer Manual, 077-0444-03 Rev B](https://download.tek.com/manual/TBS1000-B-EDU-TDS2000-B-C-TDS1000-B-C-EDU-TDS200-TPS2000-B-Programmer-077044403_RevB.pdf), for TDS2024B and TBS1052B. Conditions for older TDS200 models and TDS2MM modules do not apply to these newer families.

The inventory comes from [Core exports](../../src/scopes_tool_core/__init__.py), [Oscilloscope methods](../../src/scopes_tool_core/scope.py), [capabilities](../../src/scopes_tool_core/capabilities.py), [operation compositions](../../src/scopes_tool_core/operations.py), the actual [CLI parser](../../src/scopes_tool_cli/parser.py), and the complete [WebUI catalog](../../src/scopes_tool_webui/command_catalog.py), including hidden and dynamically constructed commands. Contract authorities are the [CLI JSON/JSONL contract](../contracts/scopes-cli-jsonl-contract.md), [worker contract](../contracts/scopes-worker-contract.md), [Core integration guide](integration.md), and corresponding controllers. Adapter aliases share rows rather than being counted as additional hardware features.

Unless marked aggregate, workflow, or host, rows describe atomic actions and their query/set forms. Presentation-only editors inherit their constituent operations: `acquisition-control`, `channel-scale-range`, `external-trigger-range-level`, `front-panel-measurements`, `reference-waveform`, `reference-labels`, `system-information`, `diagnostics`, `serial-decode`, `serial-trigger`, and `serial-lister`. An editor may display unavailable fields without enabling unsupported actions.

## Acquisition, timebase, and channels

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Contract, subset, and manual evidence |
| --- | --- | --- | --- | --- |
| `identify` | SUPPORTED | SUPPORTED | SUPPORTED | `*IDN?`; detected identity and registered-model fail-closed rules remain authoritative. |
| `run`, `stop-acquisition` | SUPPORTED | SUPPORTED | SUPPORTED | `ACQuire:STOPAfter RUNSTOP` plus `STATE RUN` for continuous run; `STATE STOP` for stop. B2 pp. 43-44; B1 pp. 2-42-2-43. |
| `single` | SUPPORTED | SUPPORTED | SUPPORTED | `STOPAfter SEQuence`, then `STATE RUN`. Arms acquisition; it does not promise trigger completion. |
| `single-wait` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Existing bounded natural/forced/timeout result uses operation-condition register polling. Tek BUSY, ACQuire:STATE, TRIGger:STATE, and OPC do not supply that register or completion classification. |
| `force-trigger` | SUPPORTED | SUPPORTED | SUPPORTED | `TRIGger FORCe`, B2 p. 167; B1 p. 2-193. Requires an armed instrument; not a completion wait. |
| `acquisition` (type, count, combined query) | SUPPORTED | SUPPORTED | SUPPORTED | `ACQuire:MODe` and `NUMAVg`: normal = SAMPLE, peak = PEAKdetect, average = AVERage. B2 also high_resolution = HIRes. B2 counts: powers of two 2-512; B1: 4, 16, 64, 128. B2 pp. 41-44; B1 pp. 2-40-2-43. |
| `autoscale` | SUPPORTED | SUPPORTED | SUPPORTED | Bare AUTOSet only. No equivalent for optional channel list, acquisition mode, or channel-selection policy. Do not discard requested options. |
| `sample-rate` (current/maximum queries) | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 `HORizontal:SAMPLERate?`, `ACQuire:MAXSamplerate?`, pp. 41, 115-116. B1 lacks acquisition-rate readbacks; reciprocal WFMPre:XINcr can describe interpolated/transfer points, not hardware sampling rate. |
| `acquisition-points`, `record-length` (queries) | SUPPORTED | SUPPORTED | SUPPORTED | `HORizontal:RECOrdlength?`: acquisition size, not DATa transfer-window size. B2 p. 118; B1 p. 2-113 (fixed 2500). No new record-length setter. |
| `timebase-scale` | SUPPORTED | SUPPORTED | SUPPORTED | `HORizontal[:MAIn]:SCAle`, seconds/division; B2 pp. 116-117; B1 p. 2-112. |
| `timebase-position` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 MAIN:POSITION is seconds. B2 POSITION is percent; DELay:TIMe is seconds but controls position only with delay mode ON. An unconditional seconds query/set cannot read a dormant delay value or silently change the separate delay mode. B2 pp. 113-115. |
| `timebase-reference` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No independent left/center/right reference setting/readback. Setting horizontal percentage changes position instead. |
| `channel-display`, `channel-scale`, `channel-coupling` | SUPPORTED | SUPPORTED | SUPPORTED | `SELect:CH<x>`, `CH<x>:SCAle`, `CH<x>:COUPling`; analog channels, existing ac/dc only. B2 pp. 57, 62-64, 160; B1 pp. 2-51-2-58, 2-173. Tek display changes can restart acquisition. |
| `channel-offset` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 OFFSet is voltage acquisition offset (p. 59). B1 POSITION moves the trace in divisions, not acquisition offset. |
| `channel-probe` | SUPPORTED | SUPPORTED | SUPPORTED | B2 PROBE:GAIN: attenuation ratio = 1/gain, with probe-dependent limits; PROBE? alone is probe information. B1 PROBE ratios: 1, 10, 20, 50, 100, 500, 1000. B2 pp. 60-62; B1 p. 2-55. |
| `channel-bandwidth-limit`, `channel-invert` | SUPPORTED | SUPPORTED | SUPPORTED | B2 bandwidth TWEnty/FULl; B1 bandwidth ON/OFF. CH<x>:INVert on both. Enabled means documented 20 MHz limiting, not a new numeric option. |
| `channel-label`, `channel-probe-skew` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 LABel (30 characters), DESKew (public -100 to +100 ns), pp. 57-59. B1 lacks writable channel labels and deskew. |
| `channel-units` | SUPPORTED | SUPPORTED | SUPPORTED | YUNit set/query: public volt/amp maps to V/A only. B2 explicitly documents CH1-CH2 (p. 64); CH3-CH4 excluded pending clarification. B1 covers all model analog channels (pp. 2-57-2-58). |
| `channel-range` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Full-scale voltage-range set/query is not established by volts/division or trace position. No documented equivalent acquisition-range readback; do not invent it from display geometry. |
| `channel-impedance`, `channel-vernier` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No selectable input impedance or fine-scale enable set/query. Fixed hardware impedance is not a successful setting/readback operation. |
| `channel-summary` (aggregate) | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Supported readbacks remain available; field projection below. |

## Display, cursors, Math, and measurements

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Contract, subset, and manual evidence |
| --- | --- | --- | --- | --- |
| `display-persistence` | SUPPORTED | SUPPORTED | SUPPORTED | B2 PERSistence:STATe/VALUe: minimum = OFF, infinite = ON/INFInite, finite seconds = ON/value (public 0.1-60 s intersection), pp. 86-87. B1 PERSistence: OFF, INFInite, 1, 2, 5 seconds only (p. 2-82). Query state and value on B2; no new AUTO mode. |
| `display-vectors` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 DISplay:STYle VECTORS and query (p. 2-83). Existing setter enables vectors only; no new dots/OFF setter. B2 lacks the control. |
| `display-label`, `display-clear`, `display-intensity` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No global label visibility or waveform-display clear action. Backlight/brightness/contrast are not waveform intensity; CLEARMenu only closes menus. |
| `cursor-off` (`cursor` off action) | SUPPORTED | SUPPORTED | SUPPORTED | CURSor:FUNCtion OFF; B2 p. 67; B1 p. 2-61. Does not disable the educator-controlled cursor feature. |
| `cursor-query` (`cursor` query action; aggregate) | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Native position/delta queries supply axes whose physical units and active mode match; projection below. |
| `cursor-set` (`cursor` set action), auto-timebase/auto-vertical | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 existing X-only or Y-only request: CURSor:SELect:SOUrce CH<x>, FUNCtion VBARS/HBARS and POSITION1/2, pp. 2-61-2-68. No simultaneous X/Y request. X-only auto-timebase can use existing scale/position; auto-vertical cannot supply required voltage offset. B2 references an undefined cursor source command; SELect:CONTROl also enables display/restarts acquisition (p. 161), violating source isolation. |
| `math-display`, `math-operator`; Core `query_math_operation` | SUPPORTED | SUPPORTED | SUPPORTED | Function 1 only: SELect:MATH and MATH:DEFINE set/query. B2 pp. 124-125, 162; B1 pp. 2-130-2-131, 2-173. Exact expressions below; no divide/additional functions. |
| `math-vertical` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Requires scale, full range, and voltage offset. Tek display scale plus position in divisions does not supply the full range/offset contract (B2 p. 127; B1 Math vertical commands). |
| `fft` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Required result includes frequency center/full span. B2 documents horizontal scale without a full-span conversion and does not specify position's frequency reference (pp. 93-97). B1 position/zoom are percentage/discrete magnification (pp. 2-91-2-95, 2-132-2-135), not the complete Hz center/span contract. |
| `math-transform`, `math-filter`, `math-visualization`, `math-composite-source`, `math-clear` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No equivalent transform/filter parameters, visualization/cascade sources, or average/max-hold/min-hold accumulator clear action. TBS1052B Trend Plot is not the Math trend operation. |
| `measure`, `measure-sweep` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Direct items require read-only item/source-specific queries. Tek immediate measurement first changes TYPE/SOURCE. Saving/restoring still violates the contract. |
| `measure-install` | SUPPORTED | SUPPORTED | SUPPORTED | Owns periodic measurement configuration. MEASUrement:MEAS<x>:TYPE/SOURCE (B2 SOURCE1 and STATE ON). B2 six slots; TDS2024B five; TBS1052B six. B2 pp. 135-141; B1 pp. 2-144-2-150. Subset/allocation below. |
| `measure-clear` | SUPPORTED | SUPPORTED | SUPPORTED | Clear installed measurements: B2 per-slot STATE OFF; B1 per-slot TYPE NONE. Not B2 CLEARSNapshot or acquisition-data clear. |
| `measure-results` (aggregate) | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Read displayed periodic slots without reconfiguration; current-value projection and unavailable statistics below. |
| `measure-source` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Global default source for subsequent installations has no equivalent; immediate source and per-slot source are different settings. |
| `measure-menu`, `measure-show` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Menu opening without changing installed measurements and measurement-marker visibility are distinct contracts. TYPE/STATE/SNAPSHOT change calculations/display, not those settings. |
| `measure-window` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | MAIN/ZOOM/AUTO/GATE is not Tek OFF/SCREEN/CURSOR gating; token substitution changes window semantics. |
| `measurement-statistics`, `measure-stats` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Mode/display/count/reset/increment/relative-deviation controls and statistics workflow are not supplied by documented periodic commands. B2 aggregate examples do not define these controls; B1 Trend Plot has different state/results. |
| `annotation`, `annotation-on`, `annotation-off`, `annotation-set`, `annotation-clear`, `annotation-query` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No annotation-slot text/color/background/position/enable contract. Channel labels are separate. |

For `math-operator`, B2 expressions are exactly CH1+CH2, CH1-CH2, CH2-CH1, CH1*CH2. B1 additionally documents CH3+CH4, CH3-CH4, CH4-CH3, CH3*CH4 on TDS2024B; TBS1052B has only CH1/CH2 expressions. Parse actual MATH:DEFINE? into existing operation/source fields, preserving source order. No arbitrary cross-pairs, self-pairs, cascade sources, divide, or unlisted reverse-order expressions. B2 mentions CH3/CH4 but omits their expressions; none are inferred.

The `measure-install` item intersection is below. B2 pp. 139-140 and B1 pp. 2-146-2-149 define the periodic measurement types and their model conditions. The action configures a displayed item; it does not promise a currently valid numeric result or enable the global `measure-source` action. Use a matching existing slot or unused slot; a full bank must not silently replace another measurement. No public Tek slot selector or channel-display mutation is added.

| Existing installation items | TBS2074B | TDS2024B | TBS1052B | Periodic type mapping or mismatch |
| --- | --- | --- | --- | --- |
| vpp, frequency, period, minimum, maximum, rise_time, fall_time, positive_width, negative_width | SUPPORTED | SUPPORTED | SUPPORTED | PK2Pk, FREQuency, PERIod, MINImum, MAXimum, RISe, FALL, PWIdth, NWIdth respectively. |
| vavg | SUPPORTED | SUPPORTED | SUPPORTED | MEAN, whole-waveform arithmetic mean; not CMEAN. |
| vrms | SUPPORTED | UNSUPPORTED | SUPPORTED | RMS, whole-waveform true RMS including DC. TDS2024B has cycle CRMS; its CURSORRMS applicability excludes this model. Neither substitutes for displayed-waveform RMS. |
| amplitude, top, base, overshoot, preshoot | SUPPORTED | UNSUPPORTED | SUPPORTED | AMPlitude, HIGH, LOW, POVERshoot, NOVERshoot. Overshoot = (maximum-high)/amplitude; preshoot = (low-minimum)/amplitude, in percent. TDS2024B lacks these periodic types. |
| duty_cycle, negative_duty_cycle | SUPPORTED | UNSUPPORTED | SUPPORTED | PDUty/NDUty. B1's broad syntax includes PDUTY, but its applicability paragraph excludes TDS2000B; honor that restriction. |
| area, positive_edges, negative_edges, positive_pulses, negative_pulses | SUPPORTED | UNSUPPORTED | SUPPORTED | AREA, B2 PEDGECount/NEDGECount or B1 REDGECount/FEDGECount, PPULSECount/NPULSECount. Whole waveform or existing gate; do not introduce a new gate control. TDS2024B lacks these types. |
| ac_rms, x_at_max, x_at_min | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No AC-only/DC-removed RMS or time-at-extremum periodic type. CRMS means cycle RMS, not AC RMS. |

The other five canonical items (the three parameterized items and phase/delay pairs) are not accepted by the existing single-channel installation operation; their Tek equivalents do not add an installation feature. Existing gate/reference-level state remains instrument state; installation must not silently reset it.

Direct `measure` is unsupported for all 31 canonical items: vpp, vavg, vrms, ac_rms, frequency, period, minimum, maximum, x_at_max, x_at_min, amplitude, top, base, overshoot, preshoot, rise_time, fall_time, positive_width, negative_width, duty_cycle, negative_duty_cycle, area, positive_edges, negative_edges, positive_pulses, negative_pulses; parameterized y_at_x, time_at_edge, time_at_value; and pair items phase, delay. Aliases inherit canonical classification. Periodic installation never enables direct queries or host measurement workflows.

## Trigger operations

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Contract, subset, and manual evidence |
| --- | --- | --- | --- | --- |
| `trigger-mode` | SUPPORTED | SUPPORTED | SUPPORTED | Trigger type, not sweep: B2 edge/glitch/runt via TYPE EDGE/PULSE and PULSE:CLASS WIDTH/RUNT; B1 edge/glitch/tv via TYPE EDGE/PULSE/VIDEO. Type selection does not enable a full configuration operation. |
| `trigger-sweep` | SUPPORTED | SUPPORTED | SUPPORTED | auto/normal via B2 A:MODe and B1 MAIN:MODe; B2 p. 173; B1 p. 2-198. |
| `trigger-edge-source` | SUPPORTED | SUPPORTED | SUPPORTED | Analog channels and line: B2 CH1-CH4/LINE; B1 model-bounded CH<x>/ACLINE. B1 external = EXT also supported. Selection requires neither line-level adjustment nor external range/probe controls. B2 AUX is not assumed equivalent to the public external input. |
| `trigger-edge-slope` | SUPPORTED | SUPPORTED | SUPPORTED | positive/negative = RISe/FALL; no either/alternate. B2 p. 169; B1 p. 2-196. |
| `trigger-edge-coupling` | SUPPORTED | SUPPORTED | SUPPORTED | B2 dc/lf-reject; B1 ac/dc/lf-reject. DC/LFRej/AC set/query. B2 has no AC. HFRej/NOISErej do not add public coupling enums. |
| `trigger-edge` (combined source/level/slope) | SUPPORTED | SUPPORTED | SUPPORTED | Analog channels, positive/negative only. Owns source selection, allowing B1 to select channel then set/query MAIN:LEVEL. Excludes line/external from the combined contract. |
| `trigger-edge-level` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 A:LEVel:CH<x> addresses a channel without changing source (pp. 171-172). B1 selected-source MAIN:LEVEL would require changing source for the standalone named-channel operation. |
| `trigger-holdoff` | SUPPORTED | SUPPORTED | SUPPORTED | B2 A:HOLDOff:TIMe, public intersection 40 ns-8 s. B1 MAIN:HOLDOff:VALue, 500 ns-10 s. Seconds set/query. |
| `trigger-pulse-width` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Public readback exposes independent greater-than, less-than, and two-ended range thresholds. Tek has one WIDTH/WHEN selector, not independent retained thresholds or configurable min/max range. Setter-only translation does not satisfy the operation. B2 pp. 174-176; B1 pp. 2-199-2-201. |
| `trigger-runt` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 CH1-CH2, positive/negative; none/less-than/greater-than = OCCURS/LESSthan/MOREthan. TYPE PULSE, CLASS RUNT, RUNT source/polarity/when/width, LOWERthreshold/UPPERthreshold:CH<x>; pp. 172, 174, 177-180. No either or undocumented CH3/CH4. B1 lacks runt. |
| `trigger-tv` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 VIDEO, NTSC/PAL, analog source; positive/negative = INVERT/NORMAL; field1/field2/all-fields/all-lines = ODD/EVEN/FIELD/LINE, pp. 2-202-2-205. Exclude line-field1/line-field2/line-alternate: LINENUM uses different full-frame addressing. Exclude SECAM/other standards because readback cannot distinguish them. B2 lacks VIDEO. |
| `trigger-noise-reject`, `trigger-hf-reject`, `trigger-edge-reject` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Independent rejection controls cannot be supplied by replacing the single mutually exclusive Tek coupling selector; this changes coupling/other rejection state and loses independent readback. |
| `external-trigger-range`, `external-trigger-probe`, `external-trigger-units`, `trigger-edge-external-level` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | EXT/EXT5/AUX selection is not independent range/probe/units and source-independent external-level set/query. B1 MAIN:LEVEL only addresses the selected source. |
| `external-trigger-settings` (aggregate) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Although parsed fields are nullable, none of the external probe/range/units/bandwidth fields has a matching documented readback. No useful field projection or actual external-settings response is available. Do not fabricate values from EXT/EXT5. |
| `trigger-transition`, `trigger-delay`, `trigger-setup-hold`, `trigger-edge-burst` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No documented slew thresholds/time, event-delay count/time, setup/hold dual-source timing, or burst count/idle-time parameter/readback contracts. Horizontal delay is not event-delay triggering. |
| `trigger-pattern`, `trigger-or` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No entered ASCII per-channel pattern/OR configuration and readback; generic logic references do not define those operations. |

For B2 runt, use command entries' TRIGger:A:RUNT:* roots. Some examples incorrectly add PULSE:RUNT or contain invalid arguments; syntax, descriptions, and source-query example establish the subset above. Malformed examples are not new spellings or values. Existing public numeric validation remains; the supplied manual does not specify a complete runt-width hardware range and cannot justify expanding it.

## Waveforms, screenshots, reference memory, and storage

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Contract, subset, and manual evidence |
| --- | --- | --- | --- | --- |
| `capture` (BYTE/WORD; single/all channels; point modes) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Accepts explicit analog channels without changing display. CURVe? requires an active/displayed source. No hidden display enabling/acquisition, host resampling, or filtering of all. B2 pp. 74-78, 187-199; B1 pp. 2-68-2-74, 2-209-2-221. |
| `screenshot` (host artifact) | UNSUPPORTED | SUPPORTED | UNSUPPORTED | TDS2024B explicit existing BMP only: HARDCopy START over USBTMC, format BMP, port USB, INKSaver (B1 pp. 2-96-2-102). Default PNG/bmp8bit unsupported. B2 file-save/readback lacks required background/ink-saver controls. TBS1052B BMP applicability conflicts; see ambiguities. |
| `screenshot --query-hardcopy`; Core `query_hardcopy_state` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | HardcopyState requires area, ink saver, palette, layout, format and raw readbacks. Neither manual supplies all; these fields are not nullable. |
| `reference-save` | SUPPORTED | SUPPORTED | SUPPORTED | Slots 1/2 = B2 REF1/REF2, B1 REFA/REFB. SAVe:WAVEform CH<x>,REF... and OPC completion; B2 pp. 159, 208-209; B1 pp. 2-170-2-171, 3-7. No implicit display changes/additional slots. |
| `reference-display` | SUPPORTED | SUPPORTED | SUPPORTED | SELect:REF<x> or SELect:REFA/REFB set/query for two slots; B2 p. 162; B1 pp. 2-172-2-173. |
| `reference-query` (required-state query) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | ReferenceWaveformState requires label/raw_label strings as actual readbacks. Only displayed/raw_displayed is available. Null or fabricated empty labels change the contract; editors can use reference-display independently. |
| `reference-label`, `reference-clear` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No writable reference label or explicit memory-clear action. Hiding a reference does not clear it. |
| `save-pwd` | SUPPORTED | SUPPORTED | SUPPORTED | FILESystem:CWD set/query; B2 p. 98; B1 File System group. Public validation plus model filesystem rules; not a file manager. |
| `save-image` (instrument action) | SUPPORTED | SUPPORTED | SUPPORTED | SAVe:IMAge filename then OPC; B2 pp. 157, 208-209; B1 pp. 2-168-2-169, 3-7. Writes instrument storage, returns actual command/completion, creates no host artifact. Details below. |
| `save-image-format` | SUPPORTED | SUPPORTED | UNSUPPORTED | B2 PNG/BMP via SAVE:IMAGE:FILEFORMAT set/query. TDS2024B BMP via HARDCopy:FORMat set/query, expressly applicable to USB-file images (B1 p. 2-98). B1 SAVE:IMAGE:FILEFORMAT alone has no query; TBS1052B alternate BMP route conflicts. No JPG/bmp8/bmp24. |
| `save-image-ink-saver` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 HARDCopy:INKSaver set/query expressly controls saved images (p. 2-100). B2 lacks equivalent background/ink-saver controls. |
| `save-image-palette`, `save-image-factors`, `save-filename` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No independent color/grayscale palette, embedded setup-factor boolean, or persistent default base-name set/query. Filename arguments/automatic numbering do not provide that state. |
| `save-waveform-format` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | B2 csv only = SPREADSheet, set/query (p. 160). INTERNAL/ISF is not public Keysight binary; no ascii-xy mapping. B1 writes CSV but has no independent format setter/readback. |
| `save-waveform` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Public filename-only action uses instrument save selection; Tek requires a source. Inventing CH1, adding a parameter, or producing multiple files changes the contract. Format setting does not enable saving. |
| `save-waveform-length`, `save-waveform-length-max` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No export point-count setting/maximum-length boolean. Record length and DATa start/stop are different settings. |
| `setup-save`, `setup-recall` | SUPPORTED | SUPPORTED | SUPPORTED | Slots 1-9 via SAVe:SETUp/RECAll:SETUp or *SAV/*RCL. Public 0/Tek 10 excluded. File targets unsupported: Tek format/.SET does not satisfy existing .scp contract. |

BYTE 1000, 5000, 10000 points and WORD all share the active-source restriction. B1 additionally has only 2500 acquisition points. B2 record-length/transfer-window controls do not authorize acquisition reconfiguration or resampling to manufacture point counts. Both manuals document integer encoding, byte order, and scaling for padded 8-bit data in 16-bit transfers: padding alone is **not** a WORD rejection reason or a promise of 16-bit acquisition resolution.

TDS2024B BMP capture receives the documented hardcopy stream through end-of-message, validates the BMP signature, and retains host artifact path/format semantics. Preserve the temporary 10-second timeout and restore it. Restore temporary format/port changes as well; requesting a host image must not leave the instrument's save format or destination changed. A background request reads INKSaver, temporarily selects black/white, and restores it even after failure. Explicit ink-saver and landscape/portrait layout options map to B1 controls; palette must be omitted because no independent palette control is documented. Do not transcode or silently change formats. Core `capture_screenshot_png` stays unsupported; explicit BMP `capture_screenshot` is supported.

For `save-image`, use the caller's validated instrument filename/path and current save settings, subject to storage/media preconditions. The action neither requires nor returns a particular encoding; a current Tek JPEG setting does not add JPEG to the public format-setter enum. Report completion only after successful *OPC? under the existing temporary 15-second timeout, restored in finally. B2 table 30 and B1 table 3-3 explicitly list file saves as operation-complete operations. The common save-image contract requires no additional RUI/operation-condition polling. A set-only format command plus echoed argument is not verified readback; use the documented TDS2024B alternative.

## Aggregate projections

These operations are read-only: do not select another source, enable channels, alter slots, change trigger mode/cursor units, or probe unsupported commands to discover support. Existing nullable/best-effort shapes determine availability, not current implementation model gates.

| Aggregate | TBS2074B projection | TDS2024B projection | TBS1052B projection |
| --- | --- | --- | --- |
| `channel-summary` | Channel, display, scale, offset, coupling, probe_ratio, bandwidth_limit, invert, label, probe_skew; V/A units on CH1/CH2. Range, impedance, vernier, CH3/CH4 units unavailable. | Channel, display, scale, coupling, probe_ratio, bandwidth_limit, invert, units. Offset, label, probe_skew, range, impedance, vernier unavailable. | Same as TDS2024B, CH1/CH2 only. |
| `live-data-snapshot` / `query_instrument_summary` | Channel display/scale/offset, CH1/CH2 units, timebase scale. Position unavailable in percentage mode; if delay is already ON, DELay:TIMe supplies seconds without mutation. Trigger type/sweep, edge source/slope, channel-qualified level and known source units. | Channel display/scale/units, timebase scale/position; channel offsets unavailable. Current analog edge-source MAIN:LEVEL is valid read-only snapshot data despite unsupported independent named-channel level control. Return edge source/slope/type/sweep. | Same as TDS2024B, bounded to two channels. |
| `system-information-snapshot` / `query_acquisition_readouts` | Identity, sample_rate, acquisition_points, record_length available: SUPPORTED. | Identity, acquisition_points, record_length available; sample_rate unavailable: PARTIAL AGGREGATE. | Same as TDS2024B: PARTIAL AGGREGATE. |
| `cursor-query` | Mode and native X positions/delta when time-based; Y positions/delta only when physical volts are established. Percent/Hz/dB/divisions/amps are not seconds/volts. Inactive/unestablished axes and dydx unavailable. | Mode and active VBARS seconds positions/delta, or active HBARS volts positions/delta. Other axis/dydx unavailable. FFT/amp/unknown-unit fields unavailable. | Same as TDS2024B. |
| `measure-results` | Enabled MEAS1-MEAS6 TYPE/SOURCE1/UNITS/VALUE, actual responses in raw, best-effort labeled current values. Historical/statistical fields unavailable. | Configured non-NONE MEAS1-MEAS5. VALUE updates require measurement menu/source display; do not open either. Omit unavailable numeric values or retain invalid results as nonnumeric/unavailable. Statistics unavailable. | Same as TDS2024B with MEAS1-MEAS6. |

`live-data-snapshot` is PARTIAL AGGREGATE on all models. Its acquisition.mode means real-time versus segmented, not normal/average/peak. Preserve existing unknown when no matching query exists; never place ACQuire:MODe there. Non-edge detail fields remain null. Line/external source_channel, channel units, and analog level are unavailable; Tek's artificial line-level zero is not an analog level.

CursorState permits null positions/deltas/dydx; OFF returns all null. Preserve the native mode or established manual/off interpretation without adding a public mode. B2 pp. 67-73 and B1 pp. 2-61-2-68 establish native queries. Query projection does not enable unsupported cursor-set variants. B1 setters accept time-based analog X-only or physical-volts Y-only positions within the graticule; do not change channel units to accept a volts request. Only the requested axis is configured; its positions must be real readbacks, not echoed input. Unrequested axes retain the aggregate's unavailable convention. Mixed X/Y requests and auto-vertical remain unsupported.

MeasurementResultsDump permits best-effort items and absent statistics_items; individual statistics fields are nullable. Missing current values use the existing string/unavailable representation or omission, not fictitious zero or null in nonnullable items[].value. Do not send undocumented statistics queries based on aggregate examples. B1 disabled-slot/off-source VALUE queries can raise errors and must be skipped. This dump is not a new direct measurement on a caller-selected channel.

The internal `doctor_snapshot` helper's readable acquisition type/count, channel display/scale/coupling/probe/bandwidth, timebase, and current edge state do not establish public doctor support. B1 offsets and B2 unconditional position are unavailable, and run_doctor still requires its error-queue preflight. Required-state results (reference-query, query_hardcopy_state, DVM/WGEN/DEMO queries) do not automatically become nullable projections. External-trigger and serial aggregates have no documented feature-specific fields to return, even where their parsers allow nulls.

## System, diagnostics, workflows, and host functions

| Existing operation | TBS2074B | TDS2024B | TBS1052B | Contract, subset, and manual evidence |
| --- | --- | --- | --- | --- |
| `live-data-snapshot` (aggregate) | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Field projection above; no unsupported atomic fallback. |
| `system-information-snapshot` (aggregate) | SUPPORTED | PARTIAL AGGREGATE | PARTIAL AGGREGATE | Identity/acquisition-readout projection above. |
| `system-status-byte`, `system-clear-status`, `system-opc`, `system-standard-event` | SUPPORTED | SUPPORTED | SUPPORTED | IEEE *STB?, *CLS, *OPC?, *ESR?, documented in both manuals. Preserve destructive-read semantics. |
| `system-operation-status` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek status/acquisition state is not the existing Operation Condition register/bit interpretation. |
| `system-options` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No installed-options query equivalent to public *OPT? results. Model assumptions are not option readback. |
| `check-error`; `query_system_error`, `drain_system_errors` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek Event Queue includes non-error events and destructive SESR/event sequencing, not normalized system-error queue/drain/clean-state semantics. B2 pp. 206-209; B1 chapter 3. |
| `doctor` (workflow) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Requires one normalized error preflight and prescribed preexisting-error outcome before snapshot. Partial fields do not remove that dependency. |
| `smoke` (workflow) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Requires error preflight, direct vpp/vrms, waveform capture, PNG screenshot. Disabling artifact saving does not remove instrument operations. |
| `acquisition-check` (workflow) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Mandatory error preflight even in check-only mode; full check also requires complete mode sweep/restoration, and B1 lacks high resolution. |
| `cleanup` (workflow) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Minimal cleanup requires display clear and normalized error-queue cleanup plus CLS/OPC. Safe cleanup adds unsupported controls. CLS alone is not completion. |
| `capture-batch`, `capture-until`, `capture-monitor` (workflows) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Require waveform capture. Host scheduling, waveform-derived predicates/metrics, and writers cannot replace the unsupported capture primitive. |
| `measure-log`, `measure-until` (workflows) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Require direct selected-channel values without changing measurement state. Periodic-slot results cannot substitute. |
| `triggered-measure-loop`, `triggered-capture-series` (workflows) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Require bounded trigger completion plus direct measurement or capture; partial iterations are not successful workflows. |
| `sequence` (workflow) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Always drains preexisting errors, even for wait-only sequences. wait/single/wait-trigger/measure/capture/screenshot/cleanup retain dependencies; explicit steps do not remove preflight. |
| `list-resources` (host) | SUPPORTED | SUPPORTED | SUPPORTED | Host VISA enumeration; only explicit live-only discovery opens enumerated resources for identity, still failing closed on unregistered models. |
| `capabilities`, `manifest`, `hardware-report` (host) | SUPPORTED | SUPPORTED | SUPPORTED | Profile/catalog reports and offline rendering of existing report JSON. Report rendering is not live diagnostics. |
| `worker`, `status`, `wait-ready`, `send-command`, `stop` (host) | SUPPORTED | SUPPORTED | SUPPORTED | Existing lifecycle/admission rules; submitted instrument operations retain matrix restrictions. stop stops the worker, stop-acquisition stops acquisition; send-command is not arbitrary SCPI. |

Host planners, schema parsers, identity/capability resolution, resource validation, artifact writers, progress/cancellation, session open/close, and `interruptible_wait` are infrastructure, not additional hardware features. Core plan_*/run_* pairs inherit workflow rows; dry-run/simulator output does not prove hardware support. Controller query/configure methods inherit their corresponding rows, including separately stated Core-only variants.

## Other existing feature families

Operations remain in the inventory even when a common mismatch permits grouping. Query forms are not useful partial aggregates when no feature-specific settings/results exist.

| Existing operation / adapter aliases | TBS2074B | TDS2024B | TBS1052B | Concrete contract mismatch |
| --- | --- | --- | --- | --- |
| `dvm-enable`, `dvm-source`, `dvm-mode`, `dvm-auto-range`, `dvm-current`, `dvm-query` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No integrated DVM state/reading contract; periodic RMS is not a DVM. |
| `wgen-output`, `wgen-function`, `wgen-frequency`, `wgen-voltage`, `wgen-offset`, `wgen-load`, `wgen-query` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No generator output/function/frequency/amplitude/offset/load command set. |
| `demo-output`, `demo-function`, `demo-phase`, `demo-query` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No programmable demo output/function/phase; probe compensation is not this feature. |
| `serial-mode`, `serial-display` (`serial-enable`, `serial-disable`), `serial-query` (`serial-status`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No bus-slot decode mode/display/state; RS232 interface commands are not waveform serial decoding. |
| `serial-uart` (`serial-uart-set`, `serial-uart-show`), `serial-i2c` (`serial-i2c-set`, `serial-i2c-show`), `serial-spi` (`serial-spi-set`, `serial-spi-show`), `serial-can` (`serial-can-set`, `serial-can-show`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No protocol signal/threshold/framing/address/rate decode configuration/readback. |
| `serial-trigger-uart` (`serial-trigger-uart-set`, `serial-trigger-uart-show`), `serial-trigger-i2c` (`serial-trigger-i2c-set`, `serial-trigger-i2c-show`), `serial-trigger-spi` (`serial-trigger-spi-set`, `serial-trigger-spi-show`), `serial-trigger-can` (`serial-trigger-can-set`, `serial-trigger-can-show`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No protocol/data/address/error trigger selectors/readbacks; edge/pulse cannot substitute. |
| `serial-lister-display`, `serial-lister-reference`, `serial-lister-query` (`serial-lister-status`), `serial-lister-export` (`serial-data`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No decoded-event lister visibility/reference/data/count/export source. |
| `search-state`, `search-mode`, `search-count`, `search-event` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No search enable/type/count/navigation contract; zoom/cursors are not event navigation. |
| `serial-search-uart`, `serial-search-i2c`, `serial-search-spi`, `serial-search-can` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No protocol-qualified search configuration/results. |
| `segmented-memory`, `segmented-capture` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | No segmented count/selection/time-tag/all-segment waveform contract; repeated acquisitions/reference slots do not substitute. |

## Tek post-command status boundary

Ordinary supported Tek operations receiving a transparent Keysight system-error post-check use one internal *ESR? after the business response completes. This preserves the established internal policy; it does not enable public check-error or workflows requiring queue semantics.

Only SESR bits 5-2 are errors: CME, EXE, DDE, QYE. PON/URQ/RQC/OPC alone do not fail operations. Do not issue EVENT?, EVMsg?, ALLEv?, EVQty? as ordinary post-checks, emulate a system-error queue, or populate top-level system_error. A nonzero mask follows the existing structured error path and retains raw SESR.

Because *ESR? is destructive, system-standard-event receives exactly its requested read. system-clear-status, system-status-byte, system-opc also receive no hidden SESR read. Post-checks do not replace completion waits or make unsupported operations supported.

## Manual ambiguities and excluded interpretations

- B1 p. 2-98 explicitly includes BMP in TBS1000B HARDCopy:FORMat syntax and applies it to USB-file/USBTMC output; p. 2-99 calls BMP non-TBS1000B only. TBS1052B BMP screenshot/verified format selection remain unsupported pending authoritative resolution. Format-independent save-image and separately documented INKSaver remain supported.
- B2 p. 64 restricts YUNit to CH1/CH2. Math mentions CH3/CH4 but lists only CH1/CH2 expressions. Neighboring commands do not establish these missing subsets.
- B2 FFT does not establish the full-span conversion/frequency reference needed by the atomic result. Do not synthesize Hz values from assumed display divisions.
- B2 references cursor source without its command entry; some trigger examples contradict syntax. Only independently documented controls and the explicit runt subset are admitted. Pulse-width has an independent retained-threshold mismatch regardless of spelling corrections.
- B2 periodic aggregate examples include statistics/indicator fields without corresponding defined controls. They do not establish measurement-statistics or marker visibility.

These boundaries authorize no new public operations, enums, waveform conversions, filesystem helpers, or contract changes. Preserve the distinction between a native hardware primitive, an admitted existing atomic operation, and a nullable read-only projection.
