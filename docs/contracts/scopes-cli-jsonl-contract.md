# Scopes CLI JSON / JSONL Contract

Common schema version: `2`

Compatibility policy: `v2-only`

This document defines Scopes-specific CLI JSON and JSONL payloads. Shared
envelope rules are defined in
[Common CLI JSON / JSONL Contract](common-cli-jsonl-contract.md). Scopes worker
behavior and artifacts are defined in
[Scopes Worker Contract](scopes-worker-contract.md).

The current Scopes Worker JSONL events, lifecycle client machine JSON, and
general one-shot CLI machine JSON use Common schema 2. Lifecycle clients reject
non-v2 Worker responses, and Common-governed boundaries require exact integer
`schema_version: 2` without v1 fallback or version negotiation. Independently
versioned domain artifacts retain their existing schemas.

Common fields such as `event`, `schema_version`, `timestamp_utc`, `run_id`,
`ok`, `message`, `fatal_error`, and `exit_code` keep their Common meanings
when present. This document lists only the Scopes-specific event fields,
command result fields, client fields, and artifact fields currently emitted by
`scopes-tool`.

## Worker JSONL Events

`scopes-tool worker --format jsonl` writes one JSON object per stdout line.
Human diagnostics belong on stderr or in text mode. The worker emits:

- `ready`: emitted after `/command`, `/status`, and `/stop` are reachable.
- `job_started`: emitted when a queued job begins execution.
- `job_finished`: emitted after terminal `result.json` is written.
- `summary`: emitted when the worker process exits normally or fatally.

All runtime events include `schema_version: 2`, `timestamp_utc`, and the same
`run_id`. The Scopes `ready` event includes `service: "scopes-tool"`,
`host`, `port`, `mode`, `model`, `resource`, `command_url`, `status_url`, and
`stop_url`; it means `/command`, `/status`, and `/stop` are reachable. It does
not include `trigger_url`.

`job_started` includes `job_id`, `worker_job_id`, `command`, and
`artifact_path`. `job_finished` includes `job_id`, `worker_job_id`, `command`,
`artifact_path`, `result_path`, `state`, `ok`, `exit_code`, and `error`.
`state` is one of `succeeded`, `failed`, or `cancelled`; only `succeeded` may
use `ok: true`. `summary` includes `accepted`, `succeeded`, `failed`,
`cancelled`, `ok`, `fatal_error`, and `exit_code`.

## Worker Client JSON

`scopes-tool send-command`, `status`, `stop`, and `wait-ready` emit one
JSON object when called with `--json`.

All worker client JSON includes `schema_version: 2` and `timestamp_utc`.
`send-command` uses the worker command name in `command`; `status`, `stop`, and
`wait-ready` use the lifecycle CLI command name.

The Common client diagnostic fields from
[Common CLI JSON / JSONL Contract](common-cli-jsonl-contract.md) may appear
when knowable, including `client_command`, `method`, `url`, `endpoint`,
`timeout_ms`, `elapsed_ms`, `request_sent`, `reachable`, `http_status`, and
`error_phase`.

`send-command` sends the Common `/command` envelope with Scopes command names
from [Scopes Worker Contract](scopes-worker-contract.md). Successful responses
include the worker response fields, including `status`, `command`, `job_id`,
`worker_job_id`, and `artifact_path` when accepted. Validation and admission
failures merge the worker response envelope into client JSON, including
`command`, `job_id`, `reason`, `error`, and `message` when present.

`status` and `wait-ready` use the same status payload schema. Successful
responses include `service: "scopes-tool"`, `status`, `run_id`, `mode`,
`model`, `resource`, `queue`, `active_job`, `last_job`, `urls`,
`fatal_error`, and `timestamp_utc`. `run_id` must match the `ready` event from
the same worker session.

The URL fields for `status` and `wait-ready` are only in the nested `urls`
object. The `urls` object must contain `command_url`, `status_url`, and
`stop_url`. Top-level `command_url`, `status_url`, and `stop_url` fields are
not supported in `status` or `wait-ready` JSON. The `urls` object must not
include `trigger_url`; Scopes workers do not expose a trigger endpoint.

Worker HTTP `400` is a validation failure and exits `2`. Runtime errors,
connection errors, timeouts, invalid responses, HTTP request failures, worker
HTTP `409`/`429`, and fatal worker failures exit `3`.
Accepted `/command` responses exit `0`, but accepted does not mean the Scopes
job succeeded; read worker `result.json` for the terminal result.

Worker execution context is startup-bound. Startup `--model` maps to
`expected_model_id` in live mode and `planning_model_id` in simulate mode;
detected live identity remains authoritative. Scopes clients do not add a
request-level `context` to `/command`, and command arguments cannot override
startup mode, model, or resource.

## Single-Response JSON

Commands that accept `--json` write exactly one JSON object to stdout. SCPI
debug logs from `--log-scpi` go to stderr and are not part of the JSON
contract.

Top-level fields currently used by Scopes:

- `schema_version`: exact integer schema version `2`.
- `timestamp_utc`: UTC ISO 8601 timestamp with offset.
- `ok`: boolean result. `false` means the command failed or reported an
  instrument/system-error condition.
- `command`: CLI command name.
- `mode`: `dry_run`, `simulate`, or `live`.
- `resource`: VISA resource, simulator resource, dry-run resource, or
  environment-derived resource.
- `backend`: backend display name when known.
- `idn`: parsed `*IDN?` object when known.
- `capabilities`: model capability object when known. This object describes
  the runtime-supported and guarded feature surface for the detected model; it
  does not report live hardware validation status.
- `scpi`: object with `planned` and `sent` command lists.
- `result`: command-specific structured result.
- `files`: list of artifact descriptors with `kind` and `path`.
- `system_error`: latest system error object when queried.
- `error`: structured error object with `type` and `message`, or `null`.

Single-response one-shot JSON does not include worker-only fields such as
`event`, `run_id`, `message`, `fatal_error`, or `exit_code` unless a future
command explicitly documents them. Consumers should use process return code
plus `ok` and command-specific status fields.

## One-Shot Live Selection

For one-shot commands, an explicit `--resource` or
`SCOPES_TOOL_RESOURCE` selects and opts in to that single live instrument.
The `--live` flag remains accepted for one-shot compatibility but is not
required. It must not be combined with `--simulate` or `--dry-run`.

`list-resources --live-only` is the separate discovery path that may open each
enumerated resource and query `*IDN?`. Live worker startup is governed by the
Scopes Worker Contract and still requires `--live --resource`.

## Command Result Fields

Discovery and identification:

- `list-resources`: `backend`, `resources`, `live_only`, `live_resources`.
- `identify`: `idn`, `capabilities`, `backend`, `timeout_ms`.
- `check-error`: `drain`, `max_reads`, `entries`; top-level `system_error`
  records the latest queried entry.
- `system-clear-status`: `operation: "clear"`, `command: "*CLS"`, and
  `cleared: true`.
- `system-opc`: `operation: "query"`, `command: "*OPC?"`, `complete: true`,
  and preserved `raw`.
- `system-status-byte`, `system-standard-event`, and
  `system-operation-status`: `operation: "query"`, exact `command`, bounded
  integer `value`, preserved `raw`, and low-to-high integer `set_bits`.
  `system-standard-event` is the destructive `*ESR?` read;
  `system-operation-status` uses `:OPERegister:CONDition?`, not `:RSTate?`.
- `system-options`: `operation: "query"`, `command: "*OPT?"`, preserved
  `raw`, and trimmed comma-separated `options`. A raw `0` remains visible and
  produces `options: ["0"]`.
- `cleanup`: `profile`, ordered `actions`, reported `skipped` actions with
  reasons, and `final_error_queue_clean`. Dry-run reports planned actions and
  uses `null` for the final error state. `errors` is present only when the final
  error check reports an instrument error.
- `doctor`: `backend`, `timeout_ms`, `acquisition`, `channels`, `timebase`,
  and `edge_trigger`.

Control and setup:

- `run`, `stop-acquisition`, `single`: `action`, `command`.
- `force-trigger`: `operation`, `forced`, `scpi_command`, and
  `human_output`.
- `channel-*`: `channel`, `operation`, `command`, and the setting value such as
  `display`, `text`, `volts_per_division`, `volts`, `coupling`,
  `probe_ratio`, or `bandwidth_limit`.
- `channel-summary`: `channels`, with one read-only analog-channel entry
  containing `channel`, `display`, `label`, `scale`, `range`, `offset`,
  `coupling`, `impedance`, `invert`, `bandwidth_limit`, `units`, `vernier`,
  `probe_ratio`, and `probe_skew`. An unparseable optional field is `null`.
- `display-label`: `operation`, `command`, and `display_label`.
- `display-clear`: `operation: "display-clear"` and target-only `command`
  `:DISPlay:CLEar`.
- `display-persistence`: `operation: "display-persistence"`, target-only
  `command`, `mode`, and `seconds`; query results also include `raw_value`.
  `mode` is `minimum`, `infinite`, or `null`; `seconds` is a number or `null`.
  Numeric finite persistence uses `mode: null` and `seconds: <number>`.
- `display-intensity`: `operation: "display-intensity"`, target-only
  `command`, and integer `value`; query results also include `raw_value`.
  The shared 2000X/3000X/4000X waveform intensity SCPI path is
  `:DISPlay:INTensity:WAVeform`.
- `display-vectors`: `operation: "display-vectors"`, target-only `command`,
  and boolean `value`; query results also include `raw_value`. Setting OFF is
  unsupported in the common display surface.
- `annotation`: `operation`, `commands`, `slot`, `enabled`, `text`, `color`,
  `background`, `x`, and `y`. Query results always include `x` and `y`; they
  are `null` for models without annotation position support. Annotation query
  results preserve instrument semantics using canonical SCPI enum values, not
  raw readback strings or CLI input aliases. Value forms are distinct:
  CLI input aliases include `white`, `marker`, and `transparent`; SCPI command
  tokens include `WHITE`, `MARKer`, and `OPAQ`; query canonical enums include
  `WHITE`, `MARK`, `DIG`, `OPAQ`, and `TRAN`. Color readback abbreviations
  such as `WHIT` are accepted and normalized to stable canonical values such as
  `WHITE`; background readback canonical values remain `OPAQ`, `INV`, and
  `TRAN`.
- `timebase-*`: `operation`, `command`, and `seconds_per_division` or
  `position_seconds`.
- `trigger-edge`: `operation`, `commands`, `source_channel`, `level_volts`,
  `slope`.
- `trigger-edge-source`: `operation`, `command`, `source`, and
  `source_channel`. Configure results use `operation: "set"`; `source` is
  `analog-channel`, `external`, or `line`, and `source_channel` is null for
  external/line. Query results use `operation: "query"` and additionally
  preserve stripped `raw_source`; unsupported, digital, WaveGen, `NONE`, and
  unknown readbacks use null `source` and null `source_channel`.
- `trigger-edge-slope`: `operation` and `command`. Configure results include
  canonical `slope` (`positive`, `negative`, `either`, or `alternate`). Query
  results include normalized nullable `slope` plus stripped `raw_slope`; an
  unknown readback preserves `raw_slope` and has null `slope`.
- `trigger-edge-level`: `operation`, `command`, and `source_channel`.
  Configure results include finite `level_volts`. Query results include finite
  parsed `level_volts` and stripped `raw_level`. The command always names the
  analog source channel and does not use an active-source implicit level form.
- `external-trigger-range`: `operation` and `command`. Configure results
  include finite positive `range_volts`. Query results include finite parsed
  `range_volts` and stripped `raw_range` from `:EXTernal:RANGe?`.
- `trigger-edge-external-level`: `operation` and `command`. Configure results
  include finite `level_volts`. Query results include finite parsed
  `level_volts` and stripped `raw_level`; all SCPI is External-qualified and
  does not use an active-source implicit level form.
- `external-trigger-probe`: `operation` and `command`. Configure results
  include finite positive `attenuation`. Query results include finite parsed
  `attenuation` and stripped `raw_attenuation` from `:EXTernal:PROBe?`.
- `external-trigger-units`: `operation` and `command`. Configure results
  include canonical `units` (`volts` or `amps`). Query results include nullable
  normalized `units` and stripped `raw_units`; unknown future readbacks remain
  raw with null normalized units.
- `external-trigger-settings`: query-only `operation: "query"` and `command:
  ":EXTernal?"`; results include nullable `probe_attenuation`, `range_value`,
  `units`, `bandwidth_limit_enabled`, and stripped `raw_response`.
- `trigger-sweep`: `operation` and `command`. Configure results include
  normalized `mode` (`auto` or `normal`) and `state_changing: true`. Query
  results include normalized `mode` and preserved `raw_value`.
- `trigger-noise-reject`: `operation` and `command`. Configure results include
  boolean `enabled` and `state_changing: true`. Query results include
  normalized boolean `enabled` and preserved `raw_value`.
- `trigger-hf-reject`: `operation` and `command`. Configure results include
  boolean `enabled` and `state_changing: true`. Query results include
  normalized boolean `enabled` and preserved `raw_value`.
- WGEN commands return `operation` and concrete `command`.
  Configure results include the canonical configured field and
  `state_changing: true`; query results include normalized values and raw
  readbacks. `wgen-query` returns ordered `commands`, `enabled`/`output_raw`,
  nullable `function` plus `function_raw`, `frequency_hz`/`frequency_raw`,
  `amplitude_volts`/`voltage_raw`, `offset_volts`/`offset_raw`, and
  `load`/`load_raw`. Unknown function readbacks use `function: null`.
- `serial-query`: `operation: "query"`, `command`, integer `bus`, and the
  trimmed raw aggregate subsystem response in `raw`. It does not derive mode
  or display fields.
- `serial-mode`: `operation`, `command`, integer `bus`, nullable canonical
  `mode`, and nullable `raw_mode`. Configure results use the configured mode,
  `raw_mode: null`, and `state_changing: true`; query results preserve
  `raw_mode`. A `NONE` readback uses `mode: null`.
- `serial-display`: `operation`, `command`, integer `bus`, boolean `enabled`,
  and nullable `raw_state`. Configure results use `raw_state: null` and
  `state_changing: true`; query results preserve `raw_state`.
- `serial-uart`, `serial-i2c`, `serial-spi`, and `serial-can`: `operation`,
  `commands`, integer `bus`, canonical protocol fields, and corresponding
  nullable `raw_*` readbacks. Configure results preserve supplied canonical
  values, set raw fields to `null`, and include `state_changing: true`; query
  results query `MODE?` first, preserve raw values, and fail before protocol
  fields when the current mode does not match. Sources are `channelN` or
  `external`; I2C is represented by the instrument `IIC` token, and CAN uses
  `difl` as the canonical differential signal value.
- `serial-trigger-uart`: `operation`, `protocol: "uart"`, integer `bus`,
  `mode`/`raw_mode`, `selected`, `trigger_mode`/`raw_trigger_mode`, and
  UART trigger `type`/`raw_type`. Data trigger results also include
  `data`/`raw_data` and `qualifier`/`raw_qualifier`; these fields are null for
  non-data types or when the bus is not currently in UART mode, and
  `selected` is false for a non-UART bus. Query returns
  the current bus and global trigger modes first and does not send
  UART-specific queries for a non-UART bus. Configure results include
  `state_changing: true`, write all criteria before the final
  `:TRIGger:MODE SBUS<n>` selection, and preserve actual raw readbacks. The
  user must configure the UART bus through Serial configuration first; this
  command does not modify decode settings or run, single, wait, or capture.
  The supported UART trigger subset excludes burst, idle-time, 9-bit,
  pattern-sequence, and other protocol triggers.
- `serial-trigger-i2c`, `serial-trigger-spi`, and `serial-trigger-can`:
  `operation`, protocol, integer `bus`, `mode`/`raw_mode`, `selected`,
  `trigger_mode`/`raw_trigger_mode`, canonical `type`/`raw_type`, and
  protocol-specific canonical/raw fields. Configure results include
  `state_changing: true`; criteria writes precede the final
  `:TRIGger:MODE SBUS<n>` write. Query returns `null` protocol-specific fields
  and `selected: false` for a nonmatching Bus mode without sending
  protocol-specific queries. Dry-run query `commands` contain only
  `:SBUS<n>:MODE?` and `:TRIGger:MODE?`. These commands require Serial
  configuration first, do not change decode settings or display, and do not
  run, single, wait, or capture.
- `serial-lister-query`: `operation: "query"`, ordered `commands`, canonical
  `display` and `reference`, and preserved `raw_display` and `raw_reference`.
  The aggregate query does not request `:LISTer:DATA?`.
- `serial-lister-display`: `operation`, `command`, canonical `display`, and
  nullable `raw_display`. Configure results include `state_changing: true`.
- `serial-lister-reference`: `operation`, `command`, canonical `reference`,
  and nullable `raw_reference`. Configure results include
  `state_changing: true`.
- `serial-lister-export`: `operation: "export"`, `command: ":LISTer:DATA?"`,
  `output_path`, and `bytes_written`. The host CSV is listed in the existing
  top-level `files` artifact list; CSV bytes are not embedded in JSON. Dry-run
  results do not claim transferred bytes and use the existing null/omitted
  dry-run convention.
- `search-state`: `operation` and `command`. Configure results include boolean
  `enabled`, `raw_state: null`, and `state_changing: true`. Query results
  include normalized boolean `enabled` and preserve `raw_state`.
- `search-mode`: configure results include `operation: "configure"`, ordered
  `commands` with `:SEARch:STATe 1` before `:SEARch:MODE`, canonical `mode`,
  `enabled: true`, `raw_mode: null`, and `state_changing: true`. Query results
  include `operation: "query"`, `command`, nullable canonical `mode`, boolean
  `enabled`, and preserved `raw_mode`; an `OFF` readback uses `mode: null` and
  `enabled: false`.
- `search-count`: query-only results include `operation: "query"`, `command`,
  integer `count`, and preserved `raw_count`.
- `search-event`: results include `operation`, `command`, `event`, and optional
  `raw` for queries or `state_changing: true` for configuration.
- `serial-search-uart`, `serial-search-i2c`, `serial-search-spi`, `serial-search-can`: configure results include `operation: "configure"`, `protocol`, `bus`, `mode`, canonical ordered business `commands`, and `state_changing: true`; configure `commands` exclude session-level `*IDN?` and `:SYSTem:ERRor?`. Query results include `operation: "query"`, `protocol`, `bus`, `search_enabled`, trimmed `raw_search_state`, `search_mode`, trimmed `raw_search_mode`, `selected`, `mode`, `raw_mode`, plus protocol-specific canonical/raw fields. The only successful nullable protocol modes are the documented 4000X-only I2C/CAN readbacks; other malformed readbacks fail with `SearchResponseError`.
- Save/export setting queries include `instrument_side: true`,
  `operation: "query"`, the target `command`, a canonical lowercase or boolean
  value, and preserved `raw_response`. Configure results use
  `operation: "configure"`, the canonical input value, and
  `state_changing: true`.
  `save-image` and `save-waveform` results use `instrument_side: true`, their
  command name as `operation`, explicit `filename`, executed `command`,
  `operation_complete: true`, and preserved `raw_operation_complete`. These
  commands create no host-side command files.
- `trigger-edge-coupling`: `operation` and `command`. Configure results include
  `coupling` (`ac`, `dc`, or `lf-reject`). Query results include normalized
  `coupling` and preserved `raw_value`.
- `trigger-edge-reject`: `operation` and `command`. Configure results include
  `reject` (`off`, `lf-reject`, or `hf-reject`). Query results include normalized
  `reject` and preserved `raw_value`.
- `trigger-pulse-width`: `operation` and `commands`. Configure results include
  `channel`, `source`, `polarity`, `qualifier`, optional `time_seconds`,
  optional `min_time_seconds`/`max_time_seconds`, optional `level_volts`, and
  `state_changing: true`. Query results include normalized `mode`, `source`,
  `source_kind`, `channel`, `digital`, `polarity`, `qualifier`,
  `greater_than_seconds`, `less_than_seconds`, `range_min_seconds`,
  `range_max_seconds`, `level_volts`, and preserved `raw` readbacks.
- `trigger-runt`: `operation` and `commands`. Configure results include
  `channel`, `source`, `polarity`, `qualifier`, `time_seconds`,
  `low_level_volts`, `high_level_volts`, and `state_changing: true`.
  `time_seconds` is `null` for `qualifier: "none"`. Query results include
  normalized `mode`, `source`, `source_kind`, `channel`, `polarity`,
  `qualifier`, `time_seconds`, `low_level_volts`, `high_level_volts`, and
  preserved `raw` readbacks. Query mode reads LOW/HIGH levels only when the
  source readback safely parses as an analog channel.
- `trigger-transition`: `operation` and `commands`. Configure results include
  `channel`, `source`, `slope`, `qualifier`, `time_seconds`,
  `low_level_volts`, `high_level_volts`, and `state_changing: true`.
  Query results include normalized `mode`, `source`, `source_kind`, `channel`,
  `slope`, `qualifier`, `time_seconds`, `low_level_volts`,
  `high_level_volts`, and preserved `raw` readbacks. Query mode reads LOW/HIGH
  levels only when the source readback safely parses as an analog channel.
- `trigger-setup-hold`: `operation` and `commands`. Configure results include
  `mode: "setup-hold"`, `clock_source`, `clock_channel`,
  `clock_source_kind`, `data_source`, `data_channel`, `data_source_kind`,
  `slope`, `setup_time_seconds`, `hold_time_seconds`, and
  `state_changing: true`. Query results include normalized `mode`, `raw_mode`,
  clock/data source raw and parsed fields, slope raw and parsed fields,
  setup/hold time raw and parsed fields, and preserved `raw` readbacks. The
  configure surface is DSO analog-channel-only; query tolerates digital or
  unknown source readback by leaving parsed analog channels null.
- `trigger-edge-burst`: `operation` and `commands`. Configure results include
  `mode: "edge-burst"`, `source_channel`, `source`, `slope`, `count`,
  `idle_time`, optional `level_volts`, and `state_changing: true`. Query
  results include normalized `mode`, nullable `source_channel`, nullable
  `slope`, nullable `count`, nullable `idle_time`, nullable `level_volts`, and
  preserved `raw_mode`, `raw_source`, `raw_slope`, `raw_count`,
  `raw_idle_time`, and `raw_level` readbacks. Query mode reads analog edge
  level only when the source readback safely parses as an analog channel.
- `trigger-tv`: `operation` and `commands`. Configure results include
  `mode: "tv"`, `source_raw`, `source_channel`, `standard_raw`, normalized
  `standard`, `tv_mode_raw`, normalized `tv_mode`, `line_raw`, nullable
  `line`, `polarity_raw`, normalized `polarity`, and
  `state_changing: true`. Query results include the same normalized and raw
  readback fields. Query preserves digital, external, extended-standard,
  unsupported TV mode, non-integer line, and unknown polarity readbacks without
  failing solely because they are outside the configure surface.
- `trigger-pattern`: `operation` and `commands`. Configure results include
  `mode: "pattern"`, `format: "ascii"`, `pattern`, `qualifier: "entered"`, and
  `state_changing: true`. Query results include normalized `mode`, `format`,
  `pattern`, `qualifier`, optional `edge_source_raw`, optional `edge_raw`,
  `raw_pattern_response`, and preserved `raw` readbacks.
- `trigger-or`: `operation` and `commands`. Configure results include
  `mode: "or"`, uppercase `pattern`, `raw_pattern`, and
  `state_changing: true`. Query results include normalized `mode`, `raw_mode`,
  normalized uppercase `pattern` when the OR readback is a common valid quoted
  or unquoted `R/F/E/X` string, `raw_pattern`, and preserved `raw` readbacks.
  The mapping is DSO analog-only: pattern positions are CH4, CH3, CH2, CH1
  on 4-channel DSO models and CH2, CH1 on 2-channel DSO models. MSO/digital OR
  trigger mapping is not implemented.
- `trigger-holdoff`: query results include `operation: "query"`, `command:
  ":TRIGger:HOLDoff?"`, and `seconds`. Configure results include `operation:
  "set"`, final fixed-holdoff `command`, `commands` with
  `:TRIGger:HOLDoff:RANDom OFF` followed by `:TRIGger:HOLDoff <seconds>`, and
  `seconds`.
- `cursor`: `operation`, `commands`, `source_channel`, `x1_seconds`,
  `x2_seconds`, optional `y1_volts`, `y2_volts`, `auto_timebase`,
  `auto_vertical`, and `diagnostic`.
- `acquisition`: `operation`, `commands`, `type`, `scpi_type`, `count`.
- `sample-rate`: `operation`, `sample_rate_hz` for current-rate queries,
  `query_kind` and `maximum_sample_rate_hz` for maximum-rate queries,
  `raw_value`, `unit`, `scpi_command`, and `human_output`.
- `acquisition-points`: `operation`, `acquisition_points`, `raw_value`,
  `unit`, `scpi_command`, and `human_output`.
- `record-length`: `operation`, `record_length_points`, `raw_value`, `unit`,
  `scpi_command`, and `human_output`.
- `segmented-memory`: query results retain `operation: "query"`, normalized
  `mode`, nullable `configured_segments`, `acquired_segments`,
  `selected_segment`, and `time_tag_s`, plus preserved raw readbacks.
  Configure results are minimal: enable reports `operation: "enable"`,
  `mode: "segmented"`, and `configured_segments`; disable reports
  `operation: "disable"`, `mode: "realtime"`, and nullable
  `configured_segments`. Query realtime mode leaves segmented-specific fields
  null, and zero acquired segments leaves selected segment and time tag null.
  Configuration does not start acquisition, capture data, or export artifacts.
- `segmented-capture`: results include `operation: "segmented-capture"`,
  `status` (`completed`, `partial`, `failed`, or dry-run `planned`),
  `output_dir`, `manifest_path`, `scpi_log_path`, `channel`,
  `requested_segments`, `configured_segments`, `acquired_segments`,
  `exported_segments`, `points`, `format`, `initial_mode`, `final_mode`,
  `vertical_unit`, and polling metadata. The top-level `files` list contains the
  manifest, SCPI log,
  and successfully written per-segment CSV files. Samples are not embedded in
  JSON; partial or failed runs preserve already written CSV artifacts.
- `autoscale`: `operation`, `commands`, `source_channels`, optional
  `fallback`.
- `setup-save` and `setup-recall`: `operation`, `command`, `slot`, `file`.
- `fft`: `operation`, `commands` or query fields, `function`,
  `source_channel`, `units`, `window`, `center_hz`, `span_hz`, `display`.
  `fft --query` reports the CLI action as `operation: "query"` and the
  raw instrument math operation as `fft_operation`. It additionally reports
  canonical `fft_operation_canonical`. Configure results add canonical
  `fft_operation_canonical`; on 4000X they can also include `start_hz`,
  `stop_hz`, `gate`, `phase_reference`, `detection_type`, and
  `detection_points`. Query results
  add `start_hz`, `stop_hz`, `gate`, `detection_type`, `detection_points`,
  `bin_size_hz`, `sample_rate_hz`, `resolution_bandwidth_hz`, and nullable
  `phase_reference`. The 4000X-only fields are null for basic-series queries.
- `math-display`: configure results include `operation: "set"`, `function`,
  boolean `enabled`, and executed `command`. Query results include
  `operation: "query"`, `function`, boolean `enabled`, and stripped `raw`.
- `math-vertical`: configure results include `operation: "set"`, `function`,
  nullable `scale`, `range`, and `offset`, plus ordered executed `commands`.
  Query results include `operation: "query"`, `function`, and numeric `scale`,
  `range`, and `offset`.
- `math-operator`: configure results include `operation: "set"`, `function`,
  canonical `math_operation`, canonical analog-channel `source1` and `source2`,
  and ordered executed `commands`. Query results include `operation: "query"`,
  `function`, canonical `math_operation`, `source1`, and `source2`, plus
  stripped `operation_raw`, `source1_raw`, and `source2_raw` readbacks.
- `math-composite-source`: configure results include `operation: "set"`,
  canonical `math_operation`, canonical analog `source1` and `source2`, and
  ordered executed `commands`. Query results include `operation: "query"`,
  canonical `math_operation`, `source1`, and `source2`, plus stripped
  `operation_raw`, `source1_raw`, and `source2_raw` readbacks. This global
  2000X/3000X command has no `function` field.
- `math-transform`: configure results include `operation: "set"`, `function`,
  canonical `math_operation`, canonical `source`, nullable
  `input_offset`, `gain`, and `linear_offset`, plus ordered executed
  `commands`. Query results include `operation: "query"`, `function`,
  canonical `math_operation` and `source`, stripped `operation_raw` and
  `source_raw`, and the same nullable operation-specific numeric fields.
- `math-filter`: configure results include `operation: "set"`, `function`,
  canonical `math_operation` and `source`, nullable `cutoff_hz`,
  `average_count`, and `smooth_points`, plus ordered executed `commands`.
  Query results include `operation: "query"`, `function`, canonical
  `math_operation` and `source`, stripped `operation_raw` and `source_raw`,
  and the same nullable operation-specific numeric fields.
- `math-visualization`: configure results include `operation: "set"`,
  `function`, canonical `math_operation`, nullable canonical `source`,
  `source2`, `measurement`, and integer `measurement_slot`, plus ordered
  executed `commands`. Query results include `operation: "query"`, `function`,
  canonical `math_operation`, nullable canonical `source`, `source2`,
  `measurement`, and `measurement_slot`, plus nullable stripped
  `operation_raw`, `source_raw`, `source2_raw`, and `measurement_raw`
  readbacks. Non-applicable fields are `null`.
- `math-clear`: results include `operation: "clear"`, `function`,
  `cleared: true`, and executed `command`.
  It applies to 4000X `average`, `max-hold`, and `min-hold` accumulations.
  Visualization source may be `composite` on 2000X/3000X or a lower-numbered
  canonical `math1` through `math3` on 4000X.

These Math result shapes are instrument-side contracts. No bus-operation result
shape, host-side Math execution mode, waveform Math artifact, or generic
expression result is defined.

Measurement and artifact-producing flows:

- `measure`: `item`, `channel`, optional `reference_channel`, `value`, `unit`,
  `valid`, `raw_value`, `reason`, `parameters`, and `command`.
- `measure-results`: `operation: "query"`, `command` set to
  `":MEASure:RESults?"`, preserved `raw`, and best-effort `items` containing
  `label` and numeric-or-string `value`. Recognized
  `label,current,min,max,mean,stddev,count` responses additionally populate
  `statistics_items` with numeric statistics and an integer `count`.
- `measure-stats`: `channel`, `items`, `mode`, `reset`, `max_count`,
  `settle_seconds`, and `records`.
- `measure-sweep`: `channels`, `items`, `pairs`, `pair_items`,
  `measurements`, and `summary`.
- `measure-log`: `status`, `channels`, `items`, `pairs`, `pair_items`,
  `interval_seconds`, `requested_count`, `requested_duration_seconds`,
  `completed_rows`, `csv_path`, `manifest_path`, `scpi_log_path`, and compact
  row records. Measurement values are written to CSV.
- `capture`: `channels`, `requested_points`, `actual_points`, `format`,
  `files`, compact per-channel waveform summaries including each capture's
  `vertical_unit` (`"V"` or `"A"`), optional
  `time_axis_tolerance`, and optional `trigger` when `--wait-trigger` is used.
  Trigger metadata includes `wait_enabled`, `arm_command`, `poll_source`,
  `poll_command`, `timeout_ms`, `poll_interval_ms`, `force_on_timeout`,
  `force_command`, `outcome`, `forced`, `timed_out`, `poll_count`,
  `elapsed_ms`, `condition_values`, `raw_values`, `capture_allowed`,
  `capture_block_reason`, and `error`. Runtime `outcome` is one of
  `natural`, `forced`, `timeout`, or `unknown`; dry-run payloads may use the
  same schema with `outcome: "unknown"` and `capture_block_reason: "dry_run"`.
  `timeout` and `unknown` outcomes do not write waveform artifacts.
- `capture-batch`: `status`, `channels`, `format`, `requested_count`,
  `completed_count`, `manifest_path`, `scpi_log_path`, and compact capture
  entries, plus nullable `error`.
- `sequence`: `status`, document `version`, `loop_count`, `step_count`,
  `total_step_executions`, `completed_loops`,
  `completed_step_executions`, nullable `failed_step`, bounded per-document
  `steps` summaries, `files`, `output_dir`, `manifest_path`, `scpi_log_path`,
  and nullable `error`. `failed_step` identifies the one-based loop and step,
  action, and a structured error. Repeated execution records remain in the
  sequence manifest rather than expanding the one-shot result.
- `screenshot` capture: `format`, `palette`, `background`, `ink_saver`,
  `layout`, canonical `options`, `byte_count`, `timeout_ms`, `image_path`,
  optional `png_path`, and `files`. Query-only `--query-hardcopy` instead
  returns `operation: "query"`
  and `hardcopy` with canonical and raw area, ink saver, palette, layout, and
  format fields; it returns no files.
- `smoke`: `status`, `output_dir`, `report_path`, `scpi_log_path`, `files`,
  `doctor`, `measurements`, `capture`, `screenshot`, `warnings`, and optional
  `error`.
- `acquisition-check`: `status`, `output_dir`, `report_path`, `scpi_log_path`,
  `average_count`, `check_only`, `stopped_on_error`, `initial_acquisition`,
  `restore`, `termination_reason`, `steps`, `final_acquisition`, and `files`.

For `measure-log`, `capture-batch`, and `sequence`, cooperative cancellation uses
`status: "cancelled"`, `error: null`, and one-shot Core/CLI exit code `130`.
Already persisted rows or captures remain in the result and artifacts; an
uncommitted partial measurement row is omitted. Finite termination precedence
is `instrument_error > completed > cancelled`: cancellation is reported only
while work remains, and a stop request observed after count or duration
completion does not replace `completed`. `KeyboardInterrupt` remains distinct
as `status: "interrupted"`, `error: "KeyboardInterrupt"`, and exit code `130`.
A Worker maps cooperative cancellation to its existing terminal
`state: "cancelled"`, exit code `3`, and top-level cancelled error.

A workflow `scpi.log` records SCPI activity produced while its Core operation
is executing. Adapter-level resource opening, live identity validation, driver
selection, and other CLI or Worker preflight are outside this boundary and are
not guaranteed to appear. It is not a complete process or session trace.

Dry-run payloads include concrete planned SCPI commands and queries in
`scpi.planned`, plus planned artifact paths. Conditional intent that cannot be
resolved without instrument state is represented in structured result fields;
for example, screenshot temporary ink saver restoration is described by
`result.ink_saver_plan` rather than a non-SCPI placeholder in `scpi.planned`.
Simulate and live payloads include sent SCPI history when available. Live JSON
output with `--log-scpi` includes the recorded sent SCPI history. Raw waveform
sample arrays are intentionally omitted from top-level JSON; use artifact files
for raw data.

Capability JSON currently includes `series`, `analog_channels`,
`default_waveform_points`, `safe_max_waveform_points`,
`supports_word_format`, `supports_raw_points_mode`, `supports_measurements`,
`supports_delay_measurement`, `supports_measure_results_dump`,
`supports_screenshot`,
`supports_screenshot_format_pack`,
  `supports_segmented_memory`, `segmented_max_segments`, `supports_serial_decode`, `serial_bus_count`,
and ordered canonical `serial_modes`,
`supports_channel_label`, `channel_label_max_length`,
`supports_display_label`, `supports_annotation`,
`supports_annotation_position`, `annotation_slots`, and
`supports_indexed_annotation`. Consumers must ignore unknown future capability
fields under schema version `2`. Search additionally reports
`supports_search_basic` and ordered canonical `search_modes`.

## Artifact JSON

Scopes artifact JSON is machine-readable and should be preferred over human
text:

- Worker job `request.json` and terminal `result.json` are Common Worker
  artifacts targeting exact integer `schema_version: 2`; their Common envelope
  and request fields remain unchanged, while command result fields follow the
  corresponding domain contract.
- Capture metadata JSON records resource, IDN, waveform format, preamble, point
  counts, and `vertical_unit`; multi-channel metadata records the unit in each
  ordered channel entry. CSV waveform columns use `ch<n>_v` for volts and
  `ch<n>_a` for amps, and multi-channel files may contain mixed units.
- Segmented-capture `manifest.json` is independently versioned at
  `schema_version: 2` and records the run's top-level `vertical_unit`.
- Capture-batch `manifest.json` remains independently versioned at
  `schema_version: 1` and records run
  status, resource, backend, IDN, channels, format, requested count, completed
  captures, artifact paths, per-capture system error, and nullable error.
- Sequence `manifest.json` is independently versioned at `schema_version: 1`
  and records the normalized version-1 document, detected execution context,
  total and completed counts, completed step records, deterministic artifact
  paths, nullable failed-step details, terminal status, and nullable error.
- Measure-log `manifest.json` remains independently versioned at
  `schema_version: 1` and records status,
  resource, backend, IDN, requested row constraints, completed rows, row
  metadata, system errors, and nullable error. Both schema-1 workflow manifests
  use `cancelled` for cooperative cancellation and `interrupted` for
  `KeyboardInterrupt` without changing their schema version.
- Smoke `report.json` is independently versioned at `schema_version: 2` and
  records status, resource, backend, IDN, doctor data, measurement records,
  capture metadata including `vertical_unit`, screenshot metadata, warnings,
  files, and errors.
- Acquisition-check `report.json` remains independently versioned at
  `schema_version: 1` and records status,
  resource, backend, IDN, initial/final acquisition state, restore metadata,
  step records, system errors, files, and errors.

## Compatibility Rules

Consumers must ignore unknown fields. New optional fields may be added under
Common schema version `2`; independently versioned Scopes domain artifacts
retain their documented versioning. Removing required fields or changing
required field types requires a major schema version bump.

Human-readable stdout, stderr, Markdown summaries, and SCPI log text are
diagnostic output, not the agent contract.
