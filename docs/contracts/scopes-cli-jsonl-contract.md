# Scopes CLI JSON / JSONL Contract

Schema version: `1`

This document defines Scopes-specific CLI JSON and JSONL payloads. Shared
envelope rules are defined in
[Common CLI JSON / JSONL Contract](common-cli-jsonl-contract.md). Scopes worker
behavior and artifacts are defined in
[Scopes Worker Contract](scopes-worker-contract.md).

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

All runtime events include `schema_version: 1`, `timestamp_utc`, and the same
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

All worker client JSON includes `schema_version: 1` and `timestamp_utc`.
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

## Single-Response JSON

Commands that accept `--json` write exactly one JSON object to stdout. SCPI
debug logs from `--log-scpi` go to stderr and are not part of the JSON
contract.

Top-level fields currently used by Scopes:

- `schema_version`: integer schema version, currently `1`.
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
- `doctor`: `backend`, `timeout_ms`, `acquisition`, `channels`, `timebase`,
  and `edge_trigger`.

Control and setup:

- `run`, `stop-acquisition`, `single`: `action`, `command`.
- `force-trigger`: `operation`, `forced`, `scpi_command`, and
  `human_output`.
- `channel-*`: `channel`, `operation`, `command`, and the setting value such as
  `display`, `text`, `volts_per_division`, `volts`, `coupling`,
  `probe_ratio`, or `bandwidth_limit`.
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
  unsupported in the v1 common display surface.
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
- Save/Export Pack v1 setting queries include `instrument_side: true`,
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
  setup/hold time raw and parsed fields, and preserved `raw` readbacks. The v1
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
  failing solely because they are outside the v1 configure surface.
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
  The v1 mapping is DSO analog-only: pattern positions are CH4, CH3, CH2, CH1
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
- `autoscale`: `operation`, `commands`, `source_channels`, optional
  `fallback`.
- `setup-save` and `setup-recall`: `operation`, `command`, `slot`, `file`.
- `fft`: `operation`, `commands` or query fields, `function`,
  `source_channel`, `units`, `window`, `center_hz`, `span_hz`, `display`.
  `fft --query` reports the CLI action as `operation: "query"` and the
  instrument math operation as `fft_operation`.
- `math-display`: configure results include `operation: "set"`, `function`,
  boolean `enabled`, and executed `command`. Query results include
  `operation: "query"`, `function`, boolean `enabled`, and stripped `raw`.
- `math-vertical`: configure results include `operation: "set"`, `function`,
  nullable `scale`, `range`, and `offset`, plus ordered executed `commands`.
  Query results include `operation: "query"`, `function`, and numeric `scale`,
  `range`, and `offset`.

Measurement and artifact-producing flows:

- `measure`: `item`, `channel`, optional `reference_channel`, `value`, `unit`,
  `valid`, `raw_value`, `reason`, `parameters`, and `command`.
- `measure-stats`: `channel`, `items`, `mode`, `reset`, `max_count`,
  `settle_seconds`, and `records`.
- `measure-sweep`: `channels`, `items`, `pairs`, `pair_items`,
  `measurements`, and `summary`.
- `measure-log`: `status`, `channels`, `items`, `pairs`, `pair_items`,
  `interval_seconds`, `requested_count`, `requested_duration_seconds`,
  `completed_rows`, `csv_path`, `manifest_path`, `scpi_log_path`, and compact
  row records. Measurement values are written to CSV.
- `capture`: `channels`, `requested_points`, `actual_points`, `format`,
  `files`, compact per-channel waveform summaries, optional
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
  entries.
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

Dry-run payloads include concrete planned SCPI commands and queries in
`scpi.planned`, plus planned artifact paths. Conditional intent that cannot be
resolved without instrument state is represented in structured result fields;
for example, screenshot temporary ink saver restoration is described by
`result.ink_saver_plan` rather than a non-SCPI placeholder in `scpi.planned`.
Simulate and live payloads include sent SCPI history when available. Raw
waveform sample arrays are intentionally omitted from top-level JSON; use
artifact files for raw data.

Capability JSON currently includes `series`, `analog_channels`,
`default_waveform_points`, `safe_max_waveform_points`,
`supports_word_format`, `supports_raw_points_mode`, `supports_measurements`,
`supports_delay_measurement`, `supports_screenshot`,
`supports_screenshot_format_pack`,
`supports_segmented_memory`, `supports_serial_decode`,
`supports_channel_label`, `channel_label_max_length`,
`supports_display_label`, `supports_annotation`,
`supports_annotation_position`, `annotation_slots`, and
`supports_indexed_annotation`. Consumers must ignore unknown future capability
fields under schema version `1`. Search Basic Pack v1 additionally reports
`supports_search_basic` and ordered canonical `search_modes`.

## Artifact JSON

Scopes artifact JSON is machine-readable and should be preferred over human
text:

- Capture metadata JSON records resource, IDN, waveform format, preamble, point
  counts, per-channel summaries, and optional time-axis tolerance.
- Capture-batch `manifest.json` uses `schema_version: 1` and records run
  status, resource, backend, IDN, channels, format, requested count, completed
  captures, artifact paths, and per-capture system error.
- Measure-log `manifest.json` uses `schema_version: 1` and records status,
  resource, backend, IDN, requested row constraints, completed rows, row
  metadata, and system errors.
- Smoke `report.json` uses `schema_version: 1` and records status, resource,
  backend, IDN, doctor data, measurement records, capture metadata, screenshot
  metadata, warnings, files, and errors.
- Acquisition-check `report.json` uses `schema_version: 1` and records status,
  resource, backend, IDN, initial/final acquisition state, restore metadata,
  step records, system errors, files, and errors.

## Compatibility Rules

Consumers must ignore unknown fields. New optional fields may be added under
schema version `1`. Removing required fields or changing required field types
requires a major schema version bump.

Human-readable stdout, stderr, Markdown summaries, and SCPI log text are
diagnostic output, not the agent contract.
