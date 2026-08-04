# Scopes Worker Contract

Common schema version: `2`

Compatibility policy: `v2-only`

This is the Scopes worker contract only. It follows
[Common Worker Protocol](common-worker-protocol.md) for lifecycle concepts and
defines the Scopes-specific command model, queue behavior, and artifacts.

The current Scopes Worker implementation enforces Common schema 2. `/command`
requests are v2-only: missing schema versions, schema 1, and non-integer schema
values are rejected. Worker HTTP responses, status responses, JSONL events,
`request.json`, and `result.json` use schema 2. Scopes execution context remains
startup-bound; top-level `/command` `context` is forbidden, and the Worker does
not provide v1 fallback or version negotiation.

## Cross-Instrument Compatibility

Scopes uses Common `POST /command` as the shared worker command envelope.
Cross-instrument orchestrators should depend only on the Common lifecycle:
process start, stdout JSONL observation, `ready`, `GET /status`,
`POST /command`, `POST /stop`, common command response fields, process exit
codes, and structured artifacts. Scopes-specific command names, simulator/VISA
session behavior, SCPI side effects, and waveform/measurement artifacts belong
to this document.

## Runtime

Start the worker with:

```text
scopes-tool worker --host 127.0.0.1 --port 8765 --simulate --model keysight-dsox4024a
scopes-tool worker --host 127.0.0.1 --port 8765 --live --resource <RESOURCE> --model keysight-dsox4024a
```

Arguments:

- `--host`: bind address, default `127.0.0.1`.
- `--port`: bind port, default `8765`; `0` requests an available port.
- `--simulate` or `--live`: required run mode. Live mode requires
  `--resource`.
- `--model`: registered canonical physical model ID, default
  `keysight-dsox4024a`. In simulator mode it is the planning identity and
  selects the registered model's capability profile. In live mode it is the
  expected identity; the detected `*IDN?` identity remains authoritative.
  Unknown IDs, raw model names, and unregistered values are rejected during
  validation.
- `--resource`: live resource string, required with `--live`.
- `--artifact-root`: default `data/worker`.
- `--queue-max`: accepted queued-job limit, default `32`.
- `--format`: `jsonl` or `text`, default `jsonl`.

The worker fixes run context at startup. Every accepted job opens its own
simulator or VISA session. Live jobs always use the startup `--resource` and
`--model`; command arguments cannot override them. Request validation happens
before enqueue, artifact creation, session open, or SCPI.

## Startup-Bound Execution Context

Scopes uses a startup-bound execution context. For live workers, startup
`--model` maps to Common `expected_model_id`; for simulator workers, startup
`--model` maps to Common `planning_model_id`. Detected live identity remains
authoritative. Scopes does not send request-level `context` in `/command`
requests, and command arguments cannot override startup mode, model, or
resource.

## Endpoints

`GET /status` is non-mutating. It returns `run_id`, mode, model, resource,
queue summary, active job, last job, command/status/stop URLs, `fatal_error`,
and `timestamp_utc`. It must not create artifacts, mutate the queue, open VISA, or
send SCPI. It does not include `trigger_url`.

`POST /command` is the Scopes worker-specific implementation of the Common
command envelope. It accepts exactly this JSON object:

```json
{"schema_version": 2, "command": "identify", "arguments": {}, "job_id": "client-id"}
```

Allowed top-level fields are `schema_version`, `command`, `arguments`, and
`job_id`. `context` is not an allowed top-level `/command` request field for
Scopes. Mode, model, and resource are fixed at Worker startup. `command` must
be a known Scopes worker command, `arguments` must be omitted or an object,
and `job_id` must be omitted or a string. Unknown fields and malformed bodies
return HTTP `400` and are not enqueued.

`schema_version` is required and must be the exact JSON integer `2`. Missing
schema versions, `1`, `"2"`, `2.0`, and `true` are rejected. Scopes does not
support a v1 fallback.

Every `/command` response contains the Common fields `schema_version`,
`status`, `command`, and `job_id`. A safely identifiable client command string
and client job string are echoed even when validation fails, including unknown
commands and unknown top-level fields. Malformed JSON, non-object bodies,
missing commands, and non-string command identities use `command: null`; omitted
or non-string `job_id` values use `job_id: null`.

Accepted responses use HTTP `202` and contain:

```json
{
  "schema_version": 2,
  "status": "accepted",
  "command": "identify",
  "job_id": "client-id",
  "worker_job_id": "worker-generated-id",
  "artifact_path": "data/worker/<run_id>/<worker_job_id>"
}
```

`202 accepted` means the job was validated, assigned an artifact directory, and
enqueued. It does not mean the oscilloscope action succeeded.

Queue, stopping, rate, or other Scopes admission failures use
`status: "rejected"` and a Scopes-specific `reason`, for example:

```json
{
  "schema_version": 2,
  "status": "rejected",
  "command": "identify",
  "job_id": "client-id",
  "reason": "queue_full"
}
```

Validation failures use HTTP `400`, `status: "error"`, the Common
`command`/`job_id` echo rules, `error: "validation_error"`, and `message`:

```json
{
  "schema_version": 2,
  "status": "error",
  "command": "identify",
  "job_id": "client-id",
  "error": "validation_error",
  "message": "unknown request field: extra"
}
```

`POST /stop` does not enter the normal command queue. It sets cooperative stop,
rejects new commands, cancels queued jobs, writes terminal `result.json` for
cancelled jobs, and emits `job_finished` for each cancelled job. Running jobs
observe cancellation at worker checkpoints or after command return; a blocking
device read may not stop immediately.

The worker exposes no `/trigger`, `trigger_url`, or `soft-*` endpoints.

## Command Inventory

Worker `/command` supports the existing Scopes capability surface:

- `identify`, `check-error`, `doctor`
- `system-clear-status`, `system-opc`, `system-status-byte`,
  `system-standard-event`, `system-operation-status`, `system-options`
- `cleanup`
- `run`, `single`, `stop-acquisition`, `force-trigger`
- `acquisition`, `acquisition-check`, `sample-rate`, `acquisition-points`,
  `record-length`, `segmented-memory`, `segmented-capture`
- `capture`, `capture-batch`, `screenshot`, `smoke`
- `channel-summary`
- `measure`, `measure-results`, `measure-stats`, `measure-sweep`, `measure-log`,
  `measure-clear`, `measure-show`, `measure-source`, `measure-window`
- `dvm-enable`, `dvm-source`, `dvm-mode`, `dvm-auto-range`, `dvm-current`,
  `dvm-query`
- `demo-query`, `demo-output`, `demo-function`, `demo-phase`
- `wgen-query`, `wgen-output`, `wgen-function`, `wgen-frequency`,
  `wgen-voltage`, `wgen-offset`, `wgen-load`
- `serial-query`, `serial-mode`, `serial-display`, `serial-uart`,
  `serial-trigger-uart`, `serial-trigger-i2c`, `serial-trigger-spi`,
  `serial-trigger-can`, `serial-i2c`, `serial-spi`, `serial-can`,
  `serial-lister-query`, `serial-lister-display`,
  `serial-lister-reference`, `serial-lister-export`
- `search-state`, `search-mode`, `search-count`, `search-event`, `serial-search-uart`, `serial-search-i2c`, `serial-search-spi`, `serial-search-can`
- `save-pwd`, `save-filename`, `save-image-format`, `save-image-palette`,
  `save-image-ink-saver`, `save-image-factors`, `save-image`,
  `save-waveform-format`, `save-waveform-length`,
  `save-waveform-length-max`, `save-waveform`
- `reference-save`, `reference-display`, `reference-label`,
  `reference-clear`, `reference-query`
- `channel-display`, `channel-label`, `channel-scale`, `channel-offset`,
  `channel-coupling`, `channel-probe`, `channel-bandwidth-limit`,
  `channel-impedance`, `channel-invert`, `channel-range`, `channel-units`,
  `channel-vernier`, `channel-probe-skew`
- `display-label`, `display-clear`, `display-persistence`,
  `display-intensity`, `display-vectors`, `annotation`
- `timebase-scale`, `timebase-position`
- `trigger-edge`, `trigger-edge-source`, `trigger-edge-slope`, `trigger-edge-level`,
  `external-trigger-range`, `trigger-edge-external-level`,
  `external-trigger-probe`, `external-trigger-units`, `external-trigger-settings`,
  `trigger-edge-coupling`, `trigger-edge-reject`,
  `trigger-pulse-width`, `trigger-runt`, `trigger-transition`,
  `trigger-delay`, `trigger-setup-hold`, `trigger-edge-burst`, `trigger-tv`,
  `trigger-pattern`, `trigger-or`, `trigger-sweep`, `trigger-noise-reject`,
  `trigger-hf-reject`, `trigger-holdoff`, `cursor`, `autoscale`
- `setup-save`, `setup-recall`, `fft`, `math-display`, `math-vertical`,
  `math-operator`, `math-composite-source`, `math-transform`, `math-filter`,
  `math-visualization`, `math-clear`

`measure-results` reuses the CLI/Core read-only `:MEASure:RESults?` path and
may return `statistics_items`. It is unrelated to Counter or
`measure-counter`.

`channel-summary` reuses the CLI/Core read-only analog-channel query path with
empty arguments and returns the existing `result.channels` shape.

`cleanup` reuses the CLI/Core cleanup path. Worker arguments use the normal
`profile` CLI option and do not define a worker-specific cleanup schema.

`list-resources` remains an explicit discovery command outside live worker
flows. `hardware-report` remains a local report renderer. They are not accepted
by worker `/command`.

Unsupported command names include `snapshot`, `restore`, `diff`, generic
`math`, and domain `status`. Worker status is reserved for lifecycle
`GET /status` and `scopes-tool status`.

Arguments use the CLI option names without leading dashes and with underscores
accepted as JSON keys, for example:

```json
{
  "command": "capture",
  "arguments": {
    "channel": [1, 2],
    "points": 1000,
    "csv": "capture.csv",
    "plot": "plot.png"
  }
}
```

The existing `screenshot` worker command accepts only canonical `output`,
`background`, `format`, `ink_saver`, `palette`, `layout`, and
`query_hardcopy` keys. Screenshot format examples are:

```json
{
  "command": "screenshot",
  "arguments": {
    "format": "bmp8bit",
    "ink_saver": false,
    "palette": "grayscale",
    "layout": "landscape",
    "output": "screen-8bit.bmp"
  }
}
```

```json
{
  "command": "screenshot",
  "arguments": {
    "query_hardcopy": true
  }
}
```

Enum values must be canonical strings and `ink_saver` must be a JSON boolean.
`query_hardcopy` must be exactly `true` and cannot be combined with capture or
setting fields. Unknown keys, aliases, wrong JSON types, invalid values, and
mixed query/capture forms are rejected before enqueue, accepted counters,
artifact creation, backend open, or SCPI. The format is available only when
the worker's selected model has a 4000X capability profile.

Triggered capture is an explicit opt-in extension of `capture`; it is not a new
worker command:

```json
{
  "command": "capture",
  "arguments": {
    "channel": [1],
    "points": 1000,
    "wait_trigger": true,
    "trigger_timeout_ms": 5000,
    "trigger_poll_interval_ms": 100,
    "force_trigger_on_timeout": true
  }
}
```

`wait_trigger` sends `:SINGle`, then polls only
`:OPERegister:CONDition?` before waveform capture. `trigger_timeout_ms` is
required when `wait_trigger` is true. `trigger_poll_interval_ms` must be
positive and less than or equal to the timeout. `force_trigger_on_timeout` is
valid only with `wait_trigger`; it sends `:TRIGger:FORCe` only after the first
finite wait times out, then repeats the finite poll window. The worker does not
use `:TRIGger:STATus?` or `*OPC?`. For DSO-X 2000X/3000X/4000X models,
operation-condition classification uses the Operation Status Condition Run bit:
Run set indicates an acquisition in progress, and Run clear indicates
completion. Other live series remain unclassified for operation-condition
completion and do not authorize capture.

Query-only worker commands require the same explicit CLI query flag in JSON
form:

```json
{"command": "sample-rate", "arguments": {"query": true}}
```

```json
{"command": "sample-rate", "arguments": {"query": true, "maximum": true}}
```

```json
{"command": "acquisition-points", "arguments": {"query": true}}
```

```json
{"command": "record-length", "arguments": {"query": true}}
```

`segmented-memory` accepts only these exact arguments:

```json
{"command": "segmented-memory", "arguments": {"query": true}}
```

```json
{"command": "segmented-memory", "arguments": {"enable": true, "segments": 25}}
```

```json
{"command": "segmented-memory", "arguments": {"disable": true}}
```

Operation values must be the JSON boolean `true`. Enable requires an integer
`segments` value; query and disable reject `segments`. Missing, false,
non-boolean, float, string, extra, or unknown arguments are rejected before
enqueue, artifact creation, backend open, or SCPI. Worker validation uses the
startup-bound model capability: counts are 2-250 on 2000X and 2-1000 on
3000X/4000X. The worker does not accept resource, model, mode, path, capture,
or export arguments and does not create a domain artifact for this command.

`segmented-capture` accepts only this Common v2 request shape:

```json
{
  "schema_version": 2,
  "command": "segmented-capture",
  "arguments": {
    "channel": 1,
    "segments": 2,
    "points": 1000,
    "format": "byte",
    "timeout_ms": 30000,
    "poll_interval_ms": 100
  },
  "job_id": "client-job-id"
}
```

`channel` and `segments` are required. `points`, `format`, `timeout_ms`, and
`poll_interval_ms` are optional and default to `1000`, `byte`, `30000`, and
`100`, respectively. All numeric values must be JSON integers; booleans are
not integers. `format` must be exactly `byte` or `word`. Channel, segment
count, point count, and word-format support are validated against the
startup-bound model capability. Segment counts are 2-250 on 2000X and 2-1000
on 3000X/4000X. `timeout_ms` and `poll_interval_ms` must be positive. The worker
uses the same Core overall timeout, operation-condition-first polling, two-sample
RUN-clear and remote-interface-enabled readiness requirement, one post-readiness
acquired-count query, and segmented-capture read-timeout semantics; the request
schema and defaults remain unchanged. The worker does not accept `output_dir`,
`output`, `path`,
`resource`, `model`,
`firmware`, `simulate`, `live`, `dry_run`, `json`, `log_scpi`, operation flags,
or aliases. Unknown keys and invalid values are rejected before enqueue,
artifact creation, backend open, or SCPI.

The worker reuses the existing one-shot CLI/Core segmented-capture workflow.
Its job directory contains the original submitted `request.json` and the
terminal `result.json`; domain artifacts are written below the fixed child
directory `segmented_capture/`:

```text
data/worker/<run_id>/<worker_job_id>/
  request.json
  result.json
  segmented_capture/
    manifest.json
    scpi.log
    segment_0001.csv
```

The child directory is required because the job root already contains
`request.json`, while the Core workflow requires a new or empty output
directory. The domain status `completed` maps to Worker `succeeded`; domain
`partial` or `failed` maps to Worker `failed` while preserving existing files
and the domain status in `result.json`. Worker cancellation keeps the existing
cooperative queued/running semantics. The worker accepts no firmware argument;
Core uses the detected IDN firmware for waveform segmented command gating.

System and status commands use only these canonical request shapes:

```json
{"command": "system-clear-status", "arguments": {}}
```

```json
{"command": "system-opc", "arguments": {"query": true}}
```

The same exact `{"query": true}` arguments apply to `system-status-byte`,
`system-standard-event`, `system-operation-status`, and `system-options`.
`system-clear-status` rejects every non-empty argument object. Query-only
commands reject empty arguments, `query: false`, non-boolean query values,
extra or alias keys, and missing arguments. The command envelope rejects null,
arrays, strings, and numbers because `arguments` must be a JSON object. All
such failures occur before enqueue, accepted counters, artifact creation,
simulator/VISA session creation, or SCPI.

`system-standard-event` maps to the destructive `*ESR?` event-register read.
`system-operation-status` maps only to `:OPERegister:CONDition?`; `:RSTate?`
remains unsupported. `check-error` remains the command for reading or draining
`:SYSTem:ERRor?`.

`force-trigger` is accepted only as an explicit command:

```json
{"command": "force-trigger", "arguments": {}}
```

`trigger-edge` is accepted only as the canonical Edge trigger command. It uses
the underlying Keysight `:TRIGger:MODE EDGE` and `:TRIGger:EDGE:*` SCPI family:

```json
{"command": "trigger-edge", "arguments": {"query": true}}
```

```json
{
  "command": "trigger-edge",
  "arguments": {
    "source_channel": 1,
    "level": 0.5,
    "slope": "positive"
  }
}
```

Configure mode changes trigger settings and is DSO analog-channel-only. It
sends `:TRIGger:MODE EDGE`, `:TRIGger:EDGE:SOURce`,
`:TRIGger:EDGE:LEVel`, and `:TRIGger:EDGE:SLOPe`. Slopes are `positive`,
`negative`, `either`, and `alternate`; trigger level is a finite volts value.
External trigger sources, digital/MSO sources, trigger coupling/reject, and
broader trigger-tree expansion are not included.

The worker accepts only `query`, `source_channel`, `level`, and `slope` for
this command. Query mode must use `query: true` without configure keys.
Configure mode requires `source_channel`, `level`, and `slope`. The legacy
`edge-trigger` command name is not accepted. The worker rejects aliases and
unknown fields such as `channel`, `source`, `source_ch`, `trigger_source`,
`level_volts`, `trigger_level`, `edge_slope`, and `mode` before enqueue,
artifact creation, simulator/VISA open, or SCPI. The command configures or
queries DSO analog Edge trigger settings; it does not run acquisition or
broader trigger-tree operations.

`trigger-edge-source` is the canonical source-only Edge Trigger command. It
uses only `:TRIGger:EDGE:SOURce`: it never sends `:TRIGger:MODE EDGE` and does
not change Edge Trigger level, slope, coupling, reject, common trigger
settings, holdoff, or acquisition state. Accepted JSON forms are:

```json
{"command": "trigger-edge-source", "arguments": {"query": true}}
```

```json
{"command": "trigger-edge-source", "arguments": {"source_channel": 1}}
```

```json
{"command": "trigger-edge-source", "arguments": {"source": "external"}}
```

```json
{"command": "trigger-edge-source", "arguments": {"source": "line"}}
```

The worker maps these forms respectively to `trigger-edge-source --query`,
`trigger-edge-source --source-channel 1`,
`trigger-edge-source --source external`, and
`trigger-edge-source --source line`. The configure SCPI values are
`CHANnel<n>`, `EXTernal`, and `LINE`, common to the documented target
DSOX2004A, DSOX3024A, DSOX4024A, and DSOX4034A models. Analog channels are
validated against the selected profile.

Exactly one operation is required. `query` must be exactly JSON `true`;
`source` must be lowercase `external` or `line`; and `source_channel` must be a
non-boolean positive integer within the selected model. The worker rejects
empty arguments, query/configure mixes, source/channel mixes, unknown keys,
camelCase alternatives, uppercase or unsupported source values, and command
aliases such as `edge-trigger-source`, `trigger-source`, `edge-source`,
`trigger-edge-input`, and `trigger_edge_source`. Rejected source-key aliases
include `channel`, `channel_number`, `sourceChannel`,
`source_channel_number`, `input`, `input_source`, `trigger_source`,
`edge_source`, `type`, `kind`, `value`, `mode`, and `enabled`. All such
validation happens before enqueue, artifact creation, simulator/VISA open, or
SCPI. External level/range and WGEN, WMOD, digital/MSO source configuration
are not included.

Edge Trigger slope and analog level support provides two canonical,
independent worker commands. `trigger-edge-slope` accepts only:

```json
{"command": "trigger-edge-slope", "arguments": {"query": true}}
```

```json
{"command": "trigger-edge-slope", "arguments": {"slope": "positive"}}
```

The configure value is exactly one lowercase canonical value: `positive`,
`negative`, `either`, or `alternate`. These map to
`trigger-edge-slope --slope <value>` and the corresponding
`:TRIGger:EDGE:SLOPe` command; the query maps to `trigger-edge-slope --query`.
`query` must be exactly JSON `true`. Empty arguments, query/slope mixes,
unknown or alias keys, non-string, uppercase, mixed-case, abbreviated, or
undocumented slope values, and command aliases are rejected before enqueue,
artifact creation, simulator/VISA open, or SCPI.

`trigger-edge-level` accepts only:

```json
{"command": "trigger-edge-level", "arguments": {"query": true, "source_channel": 1}}
```

```json
{"command": "trigger-edge-level", "arguments": {"source_channel": 1, "level_volts": 0.5}}
```

These map respectively to `trigger-edge-level --query --source-channel 1` and
`trigger-edge-level --source-channel 1 --level-volts 0.5`. `source_channel`
is required, must be a non-boolean positive integer available in the worker's
selected model profile, and `level_volts` must be a finite JSON number (not a
boolean, string, null, NaN, or infinity). Query cannot be combined with
`level_volts`; unknown or alias keys and command aliases are rejected. Both
commands validate before enqueue, accepted counters, job/artifact creation,
simulator/VISA open, or SCPI. They use only Edge slope or source-qualified
analog level SCPI, do not switch trigger mode or source, and do not support
Line, WaveGen, WMOD, or digital/MSO levels. Source channels are validated
against the selected model profile.

External-input support provides two canonical commands. `external-trigger-range`
accepts only:

```json
{"command": "external-trigger-range", "arguments": {"query": true}}
```

```json
{"command": "external-trigger-range", "arguments": {"range_volts": 8.0}}
```

It maps to `external-trigger-range --query` or
`external-trigger-range --range-volts 8.0`, then sends only
`:EXTernal:RANGe?` or `:EXTernal:RANGe <range>`. `range_volts` must be a
non-boolean finite positive JSON number. Empty arguments, `query: false`,
query/range mixes, zero or negative values, non-numeric/non-finite values, and
unknown or alias keys are rejected before enqueue, counters, artifacts,
simulator/VISA open, or SCPI. No probe attenuation is queried; 1:1 manual
observations are 8 V for 2000X/3000X and 1.6 V or 8 V for 4000X, but actual
probe/model/firmware acceptance remains instrument/error-queue authority.

`trigger-edge-external-level` accepts only:

```json
{"command": "trigger-edge-external-level", "arguments": {"query": true}}
```

```json
{"command": "trigger-edge-external-level", "arguments": {"level_volts": 0.5}}
```

It maps to `trigger-edge-external-level --query` or
`trigger-edge-external-level --level-volts 0.5`, and uses only
`:TRIGger:EDGE:LEVel? EXTernal` or
`:TRIGger:EDGE:LEVel <level>,EXTernal`. `level_volts` must be a non-boolean
finite JSON number and may be positive, negative, or zero. Empty arguments,
`query: false`, query/level mixes, unknown or alias keys, booleans, strings,
null, NaN, and infinity are rejected before any worker side effect. This
command neither changes nor queries range, source, or trigger mode; it does
not clamp to the dynamic External range.

External trigger input support provides three canonical commands. The only
accepted forms are:

```json
{"command": "external-trigger-probe", "arguments": {"query": true}}
```

```json
{"command": "external-trigger-probe", "arguments": {"attenuation": 10}}
```

```json
{"command": "external-trigger-units", "arguments": {"query": true}}
```

```json
{"command": "external-trigger-units", "arguments": {"units": "volts"}}
```

```json
{"command": "external-trigger-settings", "arguments": {"query": true}}
```

They map respectively to `external-trigger-probe --query` or
`--attenuation 10`, `external-trigger-units --query` or `--units volts`, and
the query-only `external-trigger-settings --query`. Probe attenuation must be
a non-boolean finite positive JSON number; units configure accepts only exact
lowercase `volts` or `amps`; aggregate settings accepts exactly `query: true`.
All aliases, empty arguments, `query: false`, operation mixes, unknown keys,
wrong types, non-finite values, and oversized numeric values are rejected
before enqueue, accepted counters, artifacts, simulator/VISA open, or SCPI.
The SCPI surface is only `:EXTernal:PROBe`, `:EXTernal:UNITs`, and one
`:EXTernal?` aggregate query. No External BWLimit setter, AutoProbe discovery,
range/level conversion, trigger mode/source modification, or additional
External trigger behavior is included.

`trigger-sweep`, `trigger-noise-reject`, and `trigger-hf-reject` are accepted
only as canonical common trigger general setting commands:

```json
{"command": "trigger-sweep", "arguments": {"query": true}}
```

```json
{"command": "trigger-sweep", "arguments": {"mode": "auto"}}
```

```json
{"command": "trigger-sweep", "arguments": {"mode": "normal"}}
```

```json
{"command": "trigger-noise-reject", "arguments": {"query": true}}
```

```json
{"command": "trigger-noise-reject", "arguments": {"enabled": true}}
```

```json
{"command": "trigger-noise-reject", "arguments": {"enabled": false}}
```

```json
{"command": "trigger-hf-reject", "arguments": {"query": true}}
```

```json
{"command": "trigger-hf-reject", "arguments": {"enabled": true}}
```

```json
{"command": "trigger-hf-reject", "arguments": {"enabled": false}}
```

`trigger-sweep` uses `:TRIGger:SWEep` and accepts only `query` or `mode`.
`mode` is `auto` or `normal`. `trigger-noise-reject` uses
`:TRIGger:NREJect`; `trigger-hf-reject` uses `:TRIGger:HFReject`. Both reject
filter commands accept only `query` or `enabled`; `enabled` must be JSON
boolean `true` or `false`.

For all three commands, `query` must be exactly JSON `true`, not `false`,
`"true"`, or `1`. Query mode cannot be combined with configure keys. Unknown
keys, missing configure keys, partial configure, aliases, and invalid values
are rejected before enqueue, artifact creation, simulator/VISA open, or SCPI.
Rejected `trigger-sweep` alias keys include `sweep`, `sweep_mode`, and
`trigger_sweep`. Rejected `trigger-noise-reject` alias keys include
`noise_reject`, `nreject`, `nrej`, `state`, `on`, and `enable`. Rejected
`trigger-hf-reject` alias keys include `hf_reject`, `hfreject`,
`high_frequency_reject`, `state`, `on`, and `enable`.


`trigger-edge-coupling` and `trigger-edge-reject` are accepted only as canonical Edge trigger coupling and reject commands:

```json
{"command": "trigger-edge-coupling", "arguments": {"query": true}}
```

```json
{"command": "trigger-edge-coupling", "arguments": {"coupling": "ac"}}
```

```json
{"command": "trigger-edge-coupling", "arguments": {"coupling": "dc"}}
```

```json
{"command": "trigger-edge-coupling", "arguments": {"coupling": "lf-reject"}}
```

```json
{"command": "trigger-edge-reject", "arguments": {"query": true}}
```

```json
{"command": "trigger-edge-reject", "arguments": {"reject": "off"}}
```

```json
{"command": "trigger-edge-reject", "arguments": {"reject": "lf-reject"}}
```

```json
{"command": "trigger-edge-reject", "arguments": {"reject": "hf-reject"}}
```

`trigger-edge-coupling` uses `:TRIGger:EDGE:COUPling` and accepts only `query` or `coupling`. `coupling` must be one of `ac`, `dc`, or `lf-reject`. `trigger-edge-reject` uses `:TRIGger:EDGE:REJect` and accepts only `query` or `reject`. `reject` must be one of `off`, `lf-reject`, or `hf-reject`.

For both commands, `query` must be exactly JSON `true`, not `false`, `"true"`, or `1`. Query mode cannot be combined with configure keys. Unknown keys, missing configure keys, partial configure, aliases, and invalid values are rejected before enqueue, artifact creation, simulator/VISA open, or SCPI.

Rejected `trigger-edge-coupling` alias keys include `mode`, `value`, `state`, `enabled`, `enable`, `on`, `off`, `couple`, `trigger_coupling`, `edge_coupling`, `coupling_mode`, `filter`, and `reject`. Alias values such as `lfr`, `lfreject`, `lf_reject`, `low-frequency-reject`, and `low_frequency_reject` are rejected.

Rejected `trigger-edge-reject` alias keys include `mode`, `value`, `state`, `enabled`, `enable`, `on`, `off`, `filter`, `filter_mode`, `trigger_reject`, `edge_reject`, `reject_mode`, `coupling`, `hf_reject`, and `lf_reject`. Alias values such as `lfr`, `hfr`, `lfreject`, `hfreject`, `lf_reject`, `hf_reject`, `low-frequency-reject`, and `high-frequency-reject` are rejected.

`trigger-holdoff` is the canonical worker command for fixed trigger holdoff
time. Query mode accepts only this shape:

```json
{"command": "trigger-holdoff", "arguments": {"query": true}}
```

Configure mode accepts only this shape:

```json
{"command": "trigger-holdoff", "arguments": {"seconds": 0.000001}}
```

Configure mode disables random holdoff and sets a fixed holdoff time by sending:

```text
:TRIGger:HOLDoff:RANDom OFF
:TRIGger:HOLDoff <seconds>
```

Query mode sends:

```text
:TRIGger:HOLDoff?
```

`seconds` must be a finite JSON number from `40e-9` through `10.0`. Worker JSON
accepts only `query` and `seconds`; `query` must be exactly JSON `true`. Empty
arguments, `query: false`, query plus configure keys, string seconds, boolean
seconds, null seconds, unknown keys, and aliases are rejected before enqueue,
artifact creation, simulator/VISA open, or SCPI. Rejected alias keys include
`holdoff`, `holdoff_seconds`, `time_seconds`, `duration_seconds`, `value`,
`enabled`, `state`, `mode`, `random`, `minimum`, `maximum`, `min`, `max`,
`min_seconds`, `max_seconds`, `auto`, `on`, and `off`. Non-canonical command
aliases such as `holdoff`, `trigger-hold-off`, `trigger_holdoff`,
`trigger-holdoff-random`, `trigger-holdoff-minimum`, and
`trigger-holdoff-maximum` are not accepted.

Random holdoff and minimum/maximum holdoff commands are outside this
fixed-holdoff worker contract.

`trigger-pulse-width` is accepted only as the canonical Pulse Width trigger
command. It uses the underlying Keysight `:TRIGger:GLITch...` SCPI family:

```json
{"command": "trigger-pulse-width", "arguments": {"query": true}}
```

```json
{
  "command": "trigger-pulse-width",
  "arguments": {
    "channel": 1,
    "polarity": "positive",
    "qualifier": "less_than",
    "time_seconds": 0.000001
  }
}
```

```json
{
  "command": "trigger-pulse-width",
  "arguments": {
    "channel": 1,
    "polarity": "negative",
    "qualifier": "greater_than",
    "time_seconds": 0.000005,
    "level_volts": 0.5
  }
}
```

```json
{
  "command": "trigger-pulse-width",
  "arguments": {
    "channel": 1,
    "polarity": "positive",
    "qualifier": "range",
    "min_time_seconds": 0.000001,
    "max_time_seconds": 0.00001
  }
}
```

Worker JSON may use `greater_than` and `less_than` qualifier values; they are
converted to the CLI `greater-than` and `less-than` values before parsing.
Configure mode is analog-channel-only and changes trigger settings. Query mode
must use `query: true` without configure keys. The worker does not accept
aliases such as `trigger-glitch`, `trigger-pulse`, `pulse-width`,
`glitch-trigger`, or `trigger-width`.

`trigger-runt` is accepted only as the canonical Runt trigger command. It uses
the underlying Keysight `:TRIGger:RUNT...` SCPI family plus shared
`:TRIGger:LEVel:LOW/HIGH` thresholds:

```json
{"command": "trigger-runt", "arguments": {"query": true}}
```

```json
{
  "command": "trigger-runt",
  "arguments": {
    "channel": 1,
    "polarity": "either",
    "qualifier": "none",
    "low_level_volts": -0.5,
    "high_level_volts": 0.5
  }
}
```

```json
{
  "command": "trigger-runt",
  "arguments": {
    "channel": 1,
    "polarity": "positive",
    "qualifier": "greater_than",
    "time_seconds": 0.000005,
    "low_level_volts": -0.25,
    "high_level_volts": 0.75
  }
}
```

Worker JSON may use `greater_than` and `less_than` qualifier values; they are
converted to the CLI `greater-than` and `less-than` values before parsing.
Configure mode is analog-channel-only and changes trigger settings. Query mode
must use `query: true` without configure keys. `qualifier: "none"` rejects
`time_seconds`; timed qualifiers require it. The worker does not accept aliases
such as `runt-trigger` or `trigger-runt-width`.

`trigger-transition` is accepted only as the canonical Transition trigger
command. It uses the underlying Keysight `:TRIGger:TRANsition...` SCPI family
plus shared `:TRIGger:LEVel:LOW/HIGH` thresholds:

```json
{"command": "trigger-transition", "arguments": {"query": true}}
```

```json
{
  "command": "trigger-transition",
  "arguments": {
    "channel": 1,
    "slope": "positive",
    "qualifier": "greater_than",
    "time_seconds": 0.000005,
    "low_level_volts": -0.5,
    "high_level_volts": 0.5
  }
}
```

```json
{
  "command": "trigger-transition",
  "arguments": {
    "channel": 1,
    "slope": "negative",
    "qualifier": "less_than",
    "time_seconds": 0.000002,
    "low_level_volts": -0.25,
    "high_level_volts": 0.75
  }
}
```

Worker JSON may use `greater_than` and `less_than` qualifier values; they are
converted to the CLI `greater-than` and `less-than` values before parsing.
Configure mode is analog-channel-only and changes trigger settings. Query mode
must use `query: true` without configure keys. Configure mode requires
`channel`, `slope`, `qualifier`, `time_seconds`, `low_level_volts`, and
`high_level_volts`; slope is `positive` or `negative`, qualifier is
`greater-than` or `less-than`, `time_seconds` must be positive finite, and low
level must be less than high level. The worker does not accept digital/MSO or
external source configuration, and it does not accept aliases such as
`transition-trigger`, `trigger-rise-fall`, or `trigger-rise-time`.

`trigger-delay` is accepted only as the canonical Edge Then Edge / Delay
trigger command. It uses the Keysight `:TRIGger:DELay...` SCPI family:

```json
{"command": "trigger-delay", "arguments": {"query": true}}
```

```json
{
  "command": "trigger-delay",
  "arguments": {
    "arm_channel": 1,
    "arm_slope": "positive",
    "trigger_channel": 2,
    "trigger_slope": "negative",
    "time_seconds": 0.000001,
    "count": 2
  }
}
```

Configure mode changes trigger settings and is DSO analog-channel-only. It
sends `:TRIGger:MODE DELay`, arm source/slope, delay time, Nth trigger edge
count, trigger source, and trigger slope. Slopes are `positive` or `negative`;
`time_seconds` must be from `4e-9` through `10.0`; `count` must be an integer
at least `1`. Query mode must use `query: true` without configure keys and
reads mode, arm source/slope, delay time, count, trigger source, and trigger
slope. Query result JSON preserves raw readbacks and tolerates digital or
unknown source state.

The worker accepts only `query`, `arm_channel`, `arm_slope`,
`trigger_channel`, `trigger_slope`, `time_seconds`, and `count` for this
command. It rejects `arm_source`, `trigger_source`, `digital`, `level_volts`,
`arm_level_volts`, `trigger_level_volts`, digital/MSO threshold fields,
external source configuration, aliases such as `edge-then-edge`, and generic
trigger-tree arguments. The command is DSO analog-channel-only and does not
run acquisition or capture workflows.

`trigger-setup-hold` is accepted only as the canonical Setup and Hold trigger
command. It uses the Keysight `:TRIGger:SHOLd...` SCPI family:

```json
{"command": "trigger-setup-hold", "arguments": {"query": true}}
```

```json
{
  "command": "trigger-setup-hold",
  "arguments": {
    "clock_channel": 1,
    "data_channel": 2,
    "slope": "positive",
    "setup_time": 0.000000001,
    "hold_time": 0.000000001
  }
}
```

Configure mode changes trigger settings and is DSO analog-channel-only. It
sends `:TRIGger:MODE SHOLd`, clock source, data source, clock slope, setup
time, and hold time. Slopes are `positive` or `negative`; `setup_time` and
`hold_time` are seconds values and must be positive finite numbers. Query mode
must use `query: true` without configure keys and reads mode, clock source,
data source, slope, setup time, and hold time. Query result JSON preserves raw
readbacks and tolerates digital or unknown source state, but configure rejects
digital/MSO, external, and unknown source inputs.

The worker accepts only `query`, `clock_channel`, `data_channel`, `slope`,
`setup_time`, and `hold_time` for this command. The canonical timing keys
are `setup_time` and `hold_time`, matching CLI `--setup-time` and
`--hold-time`; `setup_time_seconds` and `hold_time_seconds` are not accepted.
It rejects partial configure, `query` values other than exactly `true`,
`query` combined with configure keys, unknown keys even when false or null,
source aliases, threshold/level fields, digital/MSO or external source
configuration, aliases such as `setup-hold-trigger`, and generic trigger-tree
arguments before enqueue, artifact creation, VISA open, or SCPI. The command
does not run acquisition or capture workflows.

`trigger-edge-burst` is accepted only as the canonical Nth Edge Burst trigger
command. It uses the Keysight `:TRIGger:EBURst...` SCPI family plus optional
source-qualified analog `:TRIGger:EDGE:LEVel`:

```json
{"command": "trigger-edge-burst", "arguments": {"query": true}}
```

```json
{
  "command": "trigger-edge-burst",
  "arguments": {
    "source_channel": 1,
    "slope": "positive",
    "count": 3,
    "idle_time": 0.000001
  }
}
```

```json
{
  "command": "trigger-edge-burst",
  "arguments": {
    "source_channel": 1,
    "slope": "positive",
    "count": 3,
    "idle_time": 0.000001,
    "level_volts": 0.5
  }
}
```

Configure mode changes trigger settings and is DSO analog-channel-only. It
sends `:TRIGger:MODE EBURst`, `:TRIGger:EBURst:SOURce`,
`:TRIGger:EBURst:SLOPe`, `:TRIGger:EBURst:COUNt`, and
`:TRIGger:EBURst:IDLE`. When `level_volts` is supplied, it then sends
`:TRIGger:EDGE:LEVel <level>, CHANnel<n>` for the selected analog source.
Slopes are `positive` or `negative`; `count` must be an integer at least `1`;
`idle_time` must be finite and from `1e-8` through `10.0` seconds.

Query mode must use `query: true` without configure keys and reads mode,
source, slope, count, and idle time. It reads analog edge level only when the
source readback safely parses as analog. Query result JSON preserves raw
readbacks and tolerates digital, `NONE`, or unknown source state.

The worker accepts only `query`, `source_channel`, `slope`, `count`,
`idle_time`, and `level_volts` for this command. It rejects partial
configure, `query` values other than exactly `true`, `query` combined with
configure keys, unknown keys even when false or null, `channel`, `source`,
`edge_count`, `idle_time_seconds`, `time_seconds`, `trigger_level`, `level`,
digital/MSO or external source configuration, and generic trigger-tree
arguments before enqueue, artifact creation, VISA open, or SCPI. The command
does not run acquisition or capture/wait-trigger/run/stop/single workflows.

`trigger-tv` is accepted only as the canonical basic TV / Video trigger
command. It uses the Keysight `:TRIGger:TV...` SCPI family:

```json
{"command": "trigger-tv", "arguments": {"query": true}}
```

```json
{
  "command": "trigger-tv",
  "arguments": {
    "source_channel": 1,
    "standard": "ntsc",
    "mode": "field1",
    "polarity": "negative"
  }
}
```

```json
{
  "command": "trigger-tv",
  "arguments": {
    "source_channel": 1,
    "standard": "ntsc",
    "mode": "line-field1",
    "line": 20,
    "polarity": "negative"
  }
}
```

Configure mode changes trigger settings and is DSO analog-channel-only. It
sends `:TRIGger:MODE TV`, `:TRIGger:TV:SOURce`,
`:TRIGger:TV:STANdard`, `:TRIGger:TV:MODE`, optional
`:TRIGger:TV:LINE` for line modes, and `:TRIGger:TV:POLarity`.
Standards are `ntsc`, `pal`, `palm`, and `secam`; modes are `field1`,
`field2`, `all-fields`, `all-lines`, `line-field1`, `line-field2`, and
`line-alternate`; polarity is `positive` or `negative`. `line` is required for
line modes and rejected for non-line modes.

Query mode must use `query: true` without configure keys and reads mode,
source, standard, TV mode, line, and polarity. Result JSON preserves raw
readbacks and tolerates digital, external, extended-standard, unsupported TV
mode, non-integer line, and unknown polarity states.

The worker accepts only `query`, `source_channel`, `standard`, `mode`, `line`,
and `polarity` for this command. It rejects partial configure, `query`
values other than exactly `true`, `query` combined with configure keys, unknown
keys even when false or null, and aliases such as `channel`, `source`,
`tv_source`, `tv_standard`, `trigger_standard`, `tv_mode`, `trigger_mode`,
`line_number`, `field`, `pol`, `trigger_polarity`, `polarity_raw`,
`sourceChannel`, and `source_channel_number` before enqueue, artifact
creation, VISA open, or SCPI. Extended video standards, UDTV commands, 3000X/
4000X-only `LINE` mode, USB, NFC, serial/bus, zone trigger, MSO/digital source,
and external source are out of scope. The command does not run acquisition or
run/stop/single/force/wait/capture workflows.

`trigger-pattern` is accepted only as the canonical Pattern trigger command.
It uses the DSO analog ASCII entered-pattern `:TRIGger:PATTern...` SCPI
surface:

```json
{"command": "trigger-pattern", "arguments": {"query": true}}
```

```json
{"command": "trigger-pattern", "arguments": {"pattern": "XXX1"}}
```

Configure mode changes trigger settings and sends `:TRIGger:MODE PATTern`,
`:TRIGger:PATTern:FORMat ASCii`, `:TRIGger:PATTern "<pattern>"`, and
`:TRIGger:PATTern:QUALifier ENTered`. The pattern is a raw string using only
`0`, `1`, and `X`; lowercase input is normalized by the CLI/Core path. Empty
strings, whitespace, commas, quotes, `R`, `F`, `0x...`, and other characters
are rejected before enqueue, artifact creation, VISA open, or SCPI. Pattern
length must match the selected model profile analog channel count.

Query mode must use `query: true` without configure keys and reads
`:TRIGger:MODE?`, `:TRIGger:PATTern:FORMat?`, `:TRIGger:PATTern?`, and
`:TRIGger:PATTern:QUALifier?`. Result JSON normalizes common ASCII/HEX format
and entered qualifier readbacks while preserving raw pattern response,
edge-source, and edge fields.

The worker does not accept `source`, `level`, `format`, `edge`, `edge_source`,
`qualifier`, `time_seconds`, `greater_than_seconds`, `less_than_seconds`,
`range_min_seconds`, or `range_max_seconds` for this command. It does not
support HEX configure mode, digital/MSO pattern configuration, `R`/`F`,
optional edge parameters, duration qualifiers, pattern range commands,
source/level commands, aliases such as `pattern-trigger`, or generic
trigger-tree behavior. The command is limited to the analog ASCII pattern
surface and does not run acquisition or capture workflows.

`trigger-or` is accepted only as the canonical OR trigger command. It uses the
DSO analog-only `:TRIGger:OR` SCPI surface:

```json
{"command": "trigger-or", "arguments": {"query": true}}
```

```json
{"command": "trigger-or", "arguments": {"pattern": "XXXR"}}
```

Configure mode changes trigger settings and sends `:TRIGger:MODE OR` and
`:TRIGger:OR "<pattern>"`. The pattern is a raw edge string using only `R`,
`F`, `E`, and `X`; lowercase input is normalized by the CLI/Core path. Empty
strings, whitespace, commas, quotes, digits `0`/`1`, `0x...`, and other
characters are rejected before enqueue, artifact creation, VISA open, or SCPI.
Pattern length must match the selected model profile analog channel count.

For DSO analog-only mapping, string order follows Keysight OR trigger bit
assignment: CH4, CH3, CH2, CH1 on 4-channel DSO models and CH2, CH1 on
2-channel DSO models. Examples: `XXXR` means CH1 rising only on a 4-channel
DSO, `XXFR` means CH1 rising OR CH2 falling on a 4-channel DSO, `EEEE` means
any analog channel either edge on a 4-channel DSO, and `XR` means CH1 rising
only on a 2-channel DSO.

Query mode must use `query: true` without configure keys and reads
`:TRIGger:MODE?` and `:TRIGger:OR?`. Result JSON preserves raw mode and raw OR
readbacks, normalizes common quoted or unquoted valid OR patterns, and does not
fail solely because the current trigger mode is not OR.

The worker does not accept `mask`, `channels`, alias fields, source/level,
format, edge, qualifier, timing, digital/MSO, or generic trigger-tree arguments
for this command. It does not accept aliases such as `or-trigger` or
`trigger-or-mask`. The command is limited to DSO analog channels and does not
run acquisition or capture workflows.

### Advanced Channel Commands

The worker supports the same one-shot advanced analog channel commands as the
CLI:

- `channel-impedance`
- `channel-invert`
- `channel-range`
- `channel-units`
- `channel-vernier`
- `channel-probe-skew`

Arguments use CLI option names without leading dashes:

```json
{"command": "channel-impedance", "arguments": {"channel": 1, "query": true}}
```

```json
{
  "command": "channel-impedance",
  "arguments": {"channel": 1, "impedance": "fifty", "allow_50_ohm": true}
}
```

```json
{"command": "channel-invert", "arguments": {"channel": 1, "on": true}}
```

```json
{"command": "channel-range", "arguments": {"channel": 1, "volts_full_scale": 4}}
```

```json
{"command": "channel-units", "arguments": {"channel": 1, "units": "amp"}}
```

```json
{"command": "channel-vernier", "arguments": {"channel": 1, "off": true}}
```

```json
{"command": "channel-probe-skew", "arguments": {"channel": 1, "seconds": 1e-9}}
```

`channel-range` uses `volts_full_scale`, matching CLI
`--volts-full-scale`. Worker-only aliases such as `volts` and `range_volts`
are not supported. `channel-offset` still uses its existing `volts` argument.

Setting `channel-impedance` to `fifty` requires `allow_50_ohm: true`.
Requests without that opt-in are rejected before enqueue, artifact creation,
VISA open, or SCPI. The model capability guard remains in force after opt-in:
DSO-X 2000X profiles reject `fifty` before `:CHANnel<n>:IMPedance FIFTy` can
be sent.

### Common Display Commands

The worker supports four shared display one-shot commands:

- `display-clear`
- `display-persistence`
- `display-intensity`
- `display-vectors`

Arguments use CLI option names without leading dashes:

```json
{"command": "display-clear", "arguments": {}}
```

```json
{"command": "display-persistence", "arguments": {"query": true}}
```

```json
{"command": "display-persistence", "arguments": {"mode": "minimum"}}
```

```json
{"command": "display-persistence", "arguments": {"seconds": 1.0}}
```

```json
{"command": "display-intensity", "arguments": {"query": true}}
```

```json
{"command": "display-intensity", "arguments": {"value": 75}}
```

```json
{"command": "display-vectors", "arguments": {"query": true}}
```

```json
{"command": "display-vectors", "arguments": {"on": true}}
```

`display-clear` accepts no argument keys. `display-persistence` accepts only
`query`, `mode`, and `seconds`; `mode` is `minimum` or `infinite`, and
`seconds` must be from `0.1` through `60.0`. Persistence result JSON uses
`mode: "minimum"` or `mode: "infinite"` for enum states and `mode: null` with
numeric `seconds` for finite seconds. `display-intensity` accepts only `query`
and `value`, with integer `value` from `0` through `100`, and uses the shared
`:DISPlay:INTensity:WAVeform` SCPI path.
`display-vectors` accepts only `query` and `on`; setting OFF is unsupported in
this common command surface.

For these commands, unknown keys are rejected before enqueue, artifact
creation, VISA open, or SCPI. Boolean `query` and `on` keys must be exactly
`true`; false or null values are rejected instead of being ignored.
`display-persistence-clear` is not a common worker command.

### Measurement Control And Reference Waveform Commands

The worker accepts the common measurement control commands:

```json
{"command": "measure-clear", "arguments": {}}
```

```json
{"command": "measure-show", "arguments": {"on": true}}
```

```json
{"command": "measure-source", "arguments": {"source_channel": 1, "source2_channel": 2}}
```

```json
{"command": "measure-window", "arguments": {"window": "main"}}
```

Query forms use `{"query": true}`. Measurement marker OFF is not accepted.
Measurement sources are limited to one or two analog channels, and measurement
windows are `main`, `zoom`, `auto`, or `gate`. A `source_channel`-only command
sets source1 but does not require the instrument to clear an existing source2.
A subsequent query may preserve and report source2; source1 matching with a
clean instrument error queue is a successful result. Supply both
`source_channel` and `source2_channel` when an explicit two-source default is
required. Source2 is mainly meaningful for two-source measurements such as
delay and phase.

The `zoom` window is conditional on the oscilloscope already displaying the
zoomed timebase. On DSO-X 4034A firmware 07.20, selecting it without that
display state may return `-221,"Settings conflict"`. Callers that do not know
the current zoom state should prefer `auto`.

The worker also accepts the common reference waveform commands:

```json
{"command": "reference-save", "arguments": {"slot": 1, "source_channel": 1}}
```

```json
{"command": "reference-display", "arguments": {"slot": 1, "state": "on"}}
```

```json
{"command": "reference-label", "arguments": {"slot": 1, "text": "BASELINE"}}
```

```json
{"command": "reference-clear", "arguments": {"slot": 1}}
```

```json
{"command": "reference-query", "arguments": {"slot": 1}}
```

Reference display and label also support query forms with `query: true`.
Slots are limited to 1 and 2; save sources are analog channels only; labels
are 1-10 printable ASCII characters without double quotes. Unknown keys and
invalid values are rejected before enqueue and artifact creation. On DSO-X
4034A, enabling one reference slot for display may turn off display for the
other slot. Clients must treat that instrument-managed display interaction as
normal behavior rather than failure.

### DVM Commands

The worker accepts only the canonical DVM commands and argument shapes:

```json
{"command": "dvm-enable", "arguments": {"query": true}}
```

```json
{"command": "dvm-enable", "arguments": {"enabled": true}}
```

```json
{"command": "dvm-source", "arguments": {"channel": 1}}
```

```json
{"command": "dvm-mode", "arguments": {"mode": "dc-rms"}}
```

```json
{"command": "dvm-auto-range", "arguments": {"enabled": false}}
```

```json
{"command": "dvm-current", "arguments": {"query": true}}
```

```json
{"command": "dvm-query", "arguments": {"query": true}}
```

Configure/query commands also accept their exact `{"query": true}` form.
Modes are only `dc`, `dc-rms`, and `ac-rms`; sources are analog channels within
the startup model profile. Empty arguments, `query: false`, query/configure
mixes, aliases, unknown keys, non-boolean `enabled`, and non-integer or invalid
channels are rejected before enqueue, accepted counters, artifacts,
simulator/VISA open, or SCPI.

DVM may be option/license dependent on live instruments. DVM does not accept
`dvm-frequency`, Counter command names, DVM frequency mode, `:COUNter`
commands, or `:MEASure:COUNter`.

### Demo Output Commands

The worker accepts only these exact argument schemas:

```json
{"command": "demo-query", "arguments": {}}
```

```json
{"command": "demo-output", "arguments": {"query": true}}
```

```json
{"command": "demo-output", "arguments": {"enabled": true}}
```

```json
{"command": "demo-function", "arguments": {"query": true}}
```

```json
{"command": "demo-function", "arguments": {"function": "runt"}}
```

```json
{"command": "demo-phase", "arguments": {"query": true}}
```

```json
{"command": "demo-phase", "arguments": {"degrees": 90}}
```

`demo-query` accepts only `{}`. The other commands accept exactly one shown
query or configure form. `enabled` is a JSON boolean, `function` is a supported
canonical lowercase string for the startup model profile, and `degrees` is a
finite JSON number in the inclusive range 0 through 360. Canonical field names
are exactly `query`, `enabled`, `function`, and `degrees`.

Empty configure arguments, `query: false`, query/configure mixes, strings for
booleans or numbers, JSON booleans for `degrees`, nulls, non-finite values,
out-of-range phase values, uppercase SCPI tokens, unknown keys, and aliases
such as `output`, `on`, `state`, `value`, `signal`, `type`, `demo`, `mode`,
`angle`, `phase`, and `degree` are rejected before enqueue, accepted counters,
artifact creation, simulator/VISA open, or SCPI.

DEMO is option-/hardware-dependent, and missing-option or missing-hardware
errors use the existing instrument error path. It remains separate from WGEN
and does not include WebUI runtime behavior or the additional 4000X-only DEMO
functions.

### Waveform Generator Commands

The worker accepts only explicit canonical query or configure shapes:

```jsonl
{"command": "wgen-query", "arguments": {"query": true}}
{"command": "wgen-output", "arguments": {"query": true}}
{"command": "wgen-output", "arguments": {"enabled": true}}
{"command": "wgen-function", "arguments": {"function": "sine"}}
{"command": "wgen-frequency", "arguments": {"hz": 1000}}
{"command": "wgen-voltage", "arguments": {"amplitude": 0.5}}
{"command": "wgen-offset", "arguments": {"volts": 0}}
{"command": "wgen-load", "arguments": {"load": "one-meg"}}
```

All query forms require exactly `{"query": true}`; `{}`, `query: false`, and
query/configure mixtures are rejected. Configure forms require exactly their
shown value field. Output can be enabled only by the explicit JSON boolean
`{"enabled": true}` form; no aggregate or batch request enables it. Functions
are limited to `sine`, `square`, `ramp`, `pulse`, `noise`, and `dc`; loads are
`one-meg` and `fifty`. Frequency must be finite and positive, amplitude must
satisfy `0 < amplitude <= 5.0`, and offset must satisfy
`-2.5 <= offset <= 2.5`. Invalid requests are rejected before enqueue,
artifact creation, backend open, or SCPI.

The 2000X and 3000X route to `:WGEN`; the 4000X routes only to generator 1
through `:WGEN1`. Multi-generator selection, modulation, arbitrary waveforms,
and automatic configure-and-enable batches are outside this command set.

### Math Display And Vertical Commands

Math display and vertical commands control instrument-side Math waveform display
and vertical settings. They preserve the existing `fft` command and add these
worker request shapes:

```json
{"command": "math-display", "arguments": {"function": 1, "on": true}}
```

```json
{"command": "math-display", "arguments": {"function": 1, "query": true}}
```

```json
{"command": "math-vertical", "arguments": {"function": 1, "scale": 2.0, "offset": 0.5}}
```

```json
{"command": "math-vertical", "arguments": {"function": 1, "query": true}}
```

`math-display` requires exactly one of `on: true`, `off: true`, or
`query: true`. `math-vertical` query cannot include setters. Configure requires
at least one finite numeric `scale`, `range`, or `offset`; scale and range must
be positive and are mutually exclusive, while either may be combined with
offset. Booleans are not numeric values. Unknown keys and noncanonical boolean
forms are rejected.

The worker startup model profile validates `function` before enqueue,
artifacts, backend open, or SCPI. 2000X/3000X accept only function 1 and use
unindexed `:FUNCtion`; 4000X accepts functions 1 through 4 and uses indexed
`:FUNCtion<n>`. Vertical configuration does not automatically enable display,
and the worker does not run autoscale. Instrument firmware may recalculate
vertical scaling when Math display changes from OFF to ON. Clients that require
explicit vertical settings should submit `math-display` with `on: true` before
submitting the desired `math-vertical` setters. The worker does not disable
other 4000X slots; instrument display behavior remains instrument-managed. The
commands do not configure Math operations or sources, probe licenses, or
calculate host-side Math, and add no artifacts.

### Math Dual-Source Operator Command

The worker accepts one instrument-side dual-source Math command:

```json
{"command": "math-operator", "arguments": {"function": 1, "operation": "subtract", "source1": "channel1", "source2": "channel2"}}
```

```json
{"command": "math-operator", "arguments": {"function": 1, "query": true}}
```

Configure requires canonical `operation`, `source1`, and `source2` arguments.
Supported operations are `add`, `subtract`, `multiply`, and `divide`. Both
source1 and source2 are limited to canonical analog `channel1` through
`channel4` values supported by the worker startup model. Query requires
exactly `query: true` and cannot include configure arguments. Unknown
arguments and incomplete configure requests are rejected before enqueue,
artifacts, backend open, or SCPI.

The command reuses the existing Math function capability and dialect:
2000X/3000X accept only function 1 and use unindexed `:FUNCtion`; 4000X accepts
functions 1 through 4 and uses indexed `:FUNCtion<n>`. Configure writes only
operation, source1, and source2 in that order. It does not enable Math display,
change vertical state, run autoscale, probe licenses, or calculate host-side
waveforms. Math function sources are not accepted by `math-operator` on any
series. Reference, bus, digital, external, and expression sources are not
supported. This command adds no artifacts.

### Math Single-Source Transform Command

The worker accepts one instrument-side single-source Math command:

```json
{"command": "math-transform", "arguments": {"function": 1, "operation": "integrate", "source": "channel1", "input_offset": 0}}
```

```json
{"command": "math-transform", "arguments": {"function": 2, "operation": "linear", "source": "channel1", "gain": 2, "linear_offset": -1}}
```

```json
{"command": "math-transform", "arguments": {"function": 1, "query": true}}
```

Configure requires canonical `operation` and `source` arguments. Supported
operations are `differentiate`, `integrate`, `sqrt`, `absolute`, `square`,
`ln`, `log10`, `exp`, `exp10`, and `linear`. Sources include canonical analog
`channel1` through `channel4` values supported by the worker startup model.
2000X/3000X additionally accept `composite`; 4000X accepts a canonical
lower-numbered `math1` through `math3` source. `input_offset` is a finite JSON
number accepted only for `integrate`.
Finite JSON numbers `gain` and `linear_offset` are accepted only for `linear`;
either or both may be omitted to preserve the current instrument values.

Query requires exactly `query: true` and cannot include configure arguments.
Empty arguments, `query: false`, incomplete configure requests, aliases,
unknown keys or values, boolean or non-finite numeric parameters, and
operation-specific options used with another operation are rejected before
enqueue, artifacts, backend open, or SCPI.

The command reuses the existing Math function capability and dialect:
2000X/3000X accept only function 1 and use unindexed `:FUNCtion`; 4000X accepts
functions 1 through 4 and uses indexed `:FUNCtion<n>`. Configure writes
operation, source1, and then any applicable integrate or linear parameters. It
does not enable Math display, change vertical state, run autoscale, probe
licenses, or calculate host-side waveforms. Reference waveform sources, bus
sources, and waveform export are not supported. License availability remains
subject to the live instrument error queue. The command adds no artifacts.

### Math Composite And Cascade Sources

The worker accepts the global 2000X/3000X GOFT command:

```json
{"command": "math-composite-source", "arguments": {"operation": "subtract", "source1": "channel1", "source2": "channel2"}}
```

```json
{"command": "math-composite-source", "arguments": {"query": true}}
```

Configure requires canonical `operation`, `source1`, and `source2`. Operations
are limited to `add`, `subtract`, and `multiply`; both sources are supported
analog channels. Query requires exactly `query: true` and is exclusive with
configure fields. The command takes no `function` argument and is rejected for
4000X startup profiles.

The existing single-source worker schemas accept canonical `composite` only on
2000X/3000X. On 4000X, supported transform, filter, and visualization
operations accept `math1` through `math3` only when the source function is
lower-numbered than the destination function. `math-operator` remains
analog-channel-only. Math function sources and `composite` are never accepted
as source2. Unknown fields, partial configure requests, query/configure mixes,
aliases, uppercase values, and unsupported model/source combinations fail
before enqueue, artifacts, backend open, or SCPI.

This command configures instrument-side Math only. It does not calculate or export
waveforms, enable display, change vertical state, run autoscale, or probe
licenses. It adds no artifacts.

### Math Filter And Clear Commands

The worker accepts instrument-side filter configuration and query:

```json
{"command": "math-filter", "arguments": {"function": 1, "operation": "low-pass", "source": "channel1", "cutoff_hz": 1000000}}
```

```json
{"command": "math-filter", "arguments": {"function": 2, "operation": "average", "source": "math1", "average_count": 64}}
```

```json
{"command": "math-filter", "arguments": {"function": 1, "query": true}}
```

All registered series support canonical `low-pass` and `high-pass`; 4000X
also supports `average`, `smooth`, and `envelope`. Configure requires
`operation` and `source`. Optional `cutoff_hz` is positive and finite and is
valid only for low/high-pass. Optional `average_count` is a non-boolean
power-of-two integer from 2 through 65536. Optional `smooth_points` is a
non-boolean odd integer of at least 3. Query requires exactly `query: true`
and cannot include configure arguments. Oversized integers that cannot be
safely serialized are rejected before enqueue.

Filter sources reuse the single-source rules: supported analog channels on
all series, `composite` only on 2000X/3000X, and only a lower-numbered Math
function on 4000X. The `math-operator` source contract remains
analog-channel-only. Unknown fields, irrelevant parameters, unsupported
operations, functions, or sources, and invalid numeric types fail before
enqueue, artifacts, backend open, or SCPI.

The worker also accepts 4000X-only accumulation clear:

```json
{"command": "math-clear", "arguments": {"function": 1}}
```

`math-clear` is accepted only for capability profiles that support Math
`average`, `max-hold`, or `min-hold` accumulation and sends indexed
`:FUNCtion<n>:CLEar` without querying the current operation, waiting for
completion, or clearing acquisition or display state.
Neither command enables Math display, changes vertical or acquisition state,
runs autoscale, probes licenses, calculates waveform samples, or creates domain
artifacts.

### Math Visualization And Trend Command

The worker accepts instrument-side visualization configuration and query:

```json
{"command": "math-visualization", "arguments": {"function": 1, "operation": "magnify", "source": "composite"}}
```

```json
{"command": "math-visualization", "arguments": {"function": 1, "operation": "trend", "source": "channel1", "source2": "channel2", "measurement": "vratio"}}
```

```json
{"command": "math-visualization", "arguments": {"function": 2, "operation": "trend", "measurement_slot": 3}}
```

```json
{"command": "math-visualization", "arguments": {"function": 2, "query": true}}
```

All registered series support canonical `magnify` and `trend`; 4000X also
supports `maximum`, `minimum`, `peak`, `max-hold`, and `min-hold`. Non-Trend
operations require `source` and reuse the existing single-source rules.
2000X/3000X Trend requires one analog `source` and canonical `measurement`;
only `vratio` requires analog `source2`. 4000X Trend instead requires
non-boolean integer `measurement_slot` from 1 through 10 and rejects `source`,
`source2`, and `measurement`. The selected 4000X measurement slot must already
contain a compatible installed measurement.

Query requires exactly `query: true` with `function` and rejects configure
arguments. Unknown fields, wrong JSON types, aliases, uppercase values,
unsupported operations or sources, invalid slots, and operation-specific
argument conflicts fail before enqueue, artifacts, backend open, or SCPI. This
command does not enable Math display, change vertical or acquisition state, run
autoscale, install measurements, probe licenses, calculate waveform samples, or
export waveform data.

### Math FFT Command

The worker preserves the existing `fft` command and basic request:

```json
{"command": "fft", "arguments": {"function": 1, "source_channel": 1}}
```

4000X additionally accepts canonical advanced requests such as:

```json
{"command": "fft", "arguments": {"function": 2, "source_channel": 1, "fft_operation": "fft-phase", "start_hz": 100, "stop_hz": 1000000, "gate": "zoom", "phase_reference": "display", "detection_type": "average", "detection_points": 4096}}
```

Query remains:

```json
{"command": "fft", "arguments": {"function": 1, "query": true}}
```

`fft_operation` is `fft` by default and also accepts `fft-phase` on 4000X.
The 4000X-only fields are `start_hz`, `stop_hz`, `gate`, `phase_reference`,
`detection_type`, and `detection_points`. Center/span cannot be mixed with
start/stop, start must not exceed stop when both are present, and phase
reference is valid only with FFT Phase. Detection points must be a
non-boolean integer from 640 through 65536. Worker arguments use only the
shown canonical snake_case keys and lowercase canonical enum values.

2000X/3000X retain basic magnitude FFT and reject FFT Phase or advanced fields.
All capability, type, enum, range, and conflicting-option failures occur before
enqueue, counters, artifacts, backend open, or SCPI. A 4000X query adds
start/stop, gate, detector settings, bin size, FFT sample rate, resolution
bandwidth, and phase reference when the current operation is FFT Phase.
Advanced controls do not enable Math display, configure Zoom or timebase, run
autoscale, or change acquisition state. Query-only derived fields are
instrument readbacks, not host-side FFT results.

### Math Command Rules

The public Math commands are `fft`, `math-display`, `math-vertical`,
`math-operator`, `math-composite-source`, `math-transform`, `math-filter`,
`math-visualization`, and `math-clear`.

2000X/3000X use one unnumbered Math function, accept the global composite/GOFT
source where documented, and reject Math cascade sources. 4000X uses four
indexed functions, rejects composite/GOFT sources, and accepts only
lower-numbered Math cascade sources. Self-reference, forward-reference,
inapplicable operation parameters, invalid integers, non-finite numeric
values, unsupported capabilities, and schema mismatches are rejected before
enqueue or backend access.

Math remains instrument-side only. Bus timing and bus state are not part of
`DOMAIN_COMMANDS` or the strict schemas because MSO/digital-channel support is
outside the supported capability set. No empty Worker request shape is
reserved for them.

### Serial Query And Display Commands

The worker accepts only these canonical argument shapes:

```json
{"command": "serial-query", "arguments": {"bus": 1}}
```

```json
{"command": "serial-mode", "arguments": {"bus": 1, "query": true}}
```

```json
{"command": "serial-mode", "arguments": {"bus": 1, "mode": "uart"}}
```

```json
{"command": "serial-display", "arguments": {"bus": 1, "query": true}}
```

```json
{"command": "serial-display", "arguments": {"bus": 1, "enabled": true}}
```

Bus is a non-boolean integer validated against the startup model profile:
2000X accepts bus 1, while 3000X and 4000X accept buses 1 and 2. Configure
mode values are lowercase canonical names validated against that profile.
Display configuration requires a JSON boolean. Query/configure mixes, unknown
fields, wrong types, unavailable buses, and unsupported configure modes fail
before enqueue, artifacts, backend open, or SCPI.

`serial-query` sends only `:SBUS<n>?` and preserves the trimmed raw subsystem
response. Mode and display configuration each send only their target write.
The worker reuses the CLI/Core result without worker-only business behavior.
This command set does not configure protocol parameters, sources, triggers,
Search, Lister, or export. It does not probe licenses; unavailable serial
decode options remain normal instrument errors.

### Serial Protocol Configuration Commands

The worker also accepts `serial-uart`, `serial-i2c`, `serial-spi`, and
`serial-can`. Each request requires an integer `bus` and either
`{"query": true}` or one or more protocol-specific configure fields. The
canonical fields are the CLI names in snake_case: UART uses `rx_source`,
`tx_source`, `baud_rate`, `data_bits`, `parity`, `polarity`, and `bit_order`;
I2C uses `clock_source`, `data_source`, and `address_size`; SPI uses
`clock_source`, `mosi_source`, `miso_source`, `frame_source`, `clock_slope`,
`bit_order`, `word_width`, `framing`, and `clock_timeout`; CAN uses `source`,
`baud_rate`, `signal_definition`, and `sample_point`.

Sources are canonical `channelN` or `external`, bounded by the selected model's
analog-channel capability. CAN signal definitions use `canh`, `canl`, `rx`,
`tx`, `difl`, and `difh`. Worker validation reuses the CLI/Core path and
rejects invalid bus, mode, source, or parameter values using the startup model
before enqueue, artifact creation, backend open, or SCPI. This command set does
not configure serial trigger, Search, Lister, export, or advanced protocol
parameters; Serial Search is provided by the separate commands below.
Instrument license errors remain normal instrument errors.

### Serial UART Trigger Command

The worker accepts only these canonical UART trigger request shapes:

```json
{"command": "serial-trigger-uart", "arguments": {"bus": 1, "type": "rx-data", "data": 85, "qualifier": "equal"}}
```

```json
{"command": "serial-trigger-uart", "arguments": {"bus": 1, "query": true}}
```

The canonical types are `rx-start`, `rx-stop`, `rx-data`, `tx-start`,
`tx-stop`, `tx-data`, and `parity-error`. Data types require both `data` in
the range 0 through 255 and one of `equal`, `not-equal`, `greater-than`, or
`less-than`. Non-data types reject both fields. Unknown fields, non-canonical
values, query/configure mixes, unavailable buses, and models without UART
decode support fail before enqueue, artifact creation, backend open, or SCPI.
The worker uses the shared Core request validator and creates no artifact.

The user must configure the target UART bus through the Serial protocol
configuration command first. Configure mode queries the current bus mode,
writes UART trigger criteria only when that mode
is UART, and selects the corresponding `SBUS<n>` as the global Trigger Mode
last. Query returns the current bus mode and global Trigger Mode; for a
non-UART bus it returns null UART-specific fields without sending
UART-specific queries and does not treat the mode mismatch as command failure.
This command does not modify UART decode settings, enable Serial display, run,
single, wait, or capture. This command excludes UART burst, idle time, 9-bit
trigger comparison, pattern sequence, and LIN/I2C/SPI/CAN or other protocol
triggers.

### Serial I2C, SPI, And CAN Trigger Commands

The worker accepts these strict canonical request shapes:

```json
{"command": "serial-trigger-i2c", "arguments": {"bus": 1, "type": "read-eeprom", "address": 80, "data": 16, "qualifier": "equal"}}
```

```json
{"command": "serial-trigger-spi", "arguments": {"bus": 1, "type": "mosi", "width": 8, "data": "1010XX01"}}
```

```json
{"command": "serial-trigger-can", "arguments": {"bus": 1, "type": "start-of-frame"}}
```

Each command also accepts exactly `{"bus": 1, "query": true}` for query.
Unknown fields, non-canonical values, query/configure mixes, unavailable
buses, unsupported protocol modes, and invalid cross-field combinations fail
before enqueue, artifact creation, backend open, or SCPI. I2C address/data
values are unsigned integer or hexadecimal values; SPI and CAN patterns use
binary or `0x` hexadecimal syntax with `X` don't-care characters. Configure
results include `state_changing: true` and create no artifact.

The target Bus must already be configured through the Serial protocol
configuration command. Configure queries
the current Bus mode, writes protocol criteria in documented order, and selects
the corresponding `SBUS<n>` global Trigger Mode last. Query checks both Bus
mode and trigger type before requesting only active protocol fields. A mode
mismatch is successful with `selected: false` and null protocol-specific
fields, without protocol-specific queries. These commands do not change decode
settings or display and do not run, single, wait, or capture. This command set
includes only the common I2C/SPI/CAN trigger subset; UART and Serial Search
remain separate commands.

### Serial Lister Commands

The worker accepts these exact Lister request shapes:

```json
{"command": "serial-lister-query", "arguments": {}}
```

```json
{"command": "serial-lister-display", "arguments": {"query": true}}
```

```json
{"command": "serial-lister-display", "arguments": {"selection": "bus1"}}
```

```json
{"command": "serial-lister-reference", "arguments": {"query": true}}
```

```json
{"command": "serial-lister-reference", "arguments": {"reference": "previous"}}
```

```json
{"command": "serial-lister-export", "arguments": {"output": "lister.csv"}}
```

Display selections are canonical `off`, `bus1`, `bus2`, and `all`; references
are canonical `trigger` and `previous`. Query/configure mixes, unknown fields,
wrong types, and unsupported 2000X `bus2` selection fail before enqueue,
artifact creation, backend open, or SCPI. Lister query sends only the display
and reference queries. Lister export sends `:LISTer:DATA?`, writes the raw CSV
payload as a host artifact, and does not use instrument-side `:SAVE:LISTer` or
parse protocol rows. Serial decode and decoded Lister data must already exist;
the worker does not acquire traffic or enable Serial/SBUS displays.

### Waveform Search Commands

The worker accepts only these canonical argument shapes:

```json
{"command": "search-state", "arguments": {"query": true}}
```

```json
{"command": "search-state", "arguments": {"enabled": false}}
```

```json
{"command": "search-mode", "arguments": {"query": true}}
```

```json
{"command": "search-mode", "arguments": {"mode": "edge"}}
```

```json
{"command": "search-count", "arguments": {"query": true}}
```

```json
{"command": "search-event", "arguments": {"query": true}}
```

```json
{"command": "search-event", "arguments": {"event": 1}}
```

`search-state` accepts exactly `query: true` or one JSON boolean `enabled`.
`search-mode` accepts exactly `query: true` or one lowercase canonical mode:
`serial1`, `serial2`, `edge`, `glitch`, `runt`, `transition`, or `peak`.
`search-count` is query-only. Configuring `search-mode` sends
`:SEARch:STATe 1` before `:SEARch:MODE`.

The startup model profile guards mode support before enqueue, accepted
counters, job or artifact creation, simulator/VISA session open, or SCPI.
DSO-X 2000X accepts only `serial1`; 3000X accepts `edge`, `glitch`, `runt`,
`transition`, `serial1`, and `serial2`; 4000X additionally accepts `peak`.
Empty arguments, `query: false`, query/configure mixes, unknown keys, wrong
types, aliases, uppercase values, and unsupported profile modes are rejected.

### Serial Search Commands

The worker accepts `serial-search-uart`, `serial-search-i2c`,
`serial-search-spi`, and `serial-search-can`. Each request requires a valid
`bus` and either `{"query": true}` or the canonical protocol-specific Search
fields. The matching Serial bus must already be configured with the related
Serial protocol configuration command. Serial Search does not query, modify, or
force validation of the current SBUS protocol configuration.

Query results preserve canonical protocol values and trimmed raw values,
including `raw_search_state` and `raw_search_mode`. The I2C readbacks `ADDR`
and `ADDRESS`, and the CAN readbacks `ACK`, `ACKERROR`, `FORM`, `FORMERROR`,
`STUF`, `STUFF`, `STUFERROR`, `STUFFERROR`, `CRC`, `CRCERROR`, `MESS`,
`MESSAGE`, `MSIG`, and `MSIGNAL` are known 4000X-only modes and return
`mode: null` with the original trimmed `raw_mode`. Other unknown or malformed
readbacks fail with `SearchResponseError`.

Unknown fields, wrong types, query/configure mixes, unavailable buses, and
unsupported configure values fail before enqueue, artifact creation, backend
open, or SCPI. These commands create no command artifacts. Serial Search does
not support LIN, advanced protocols, symbolic CAN, or Search export.

### Instrument-Side Save Commands

Instrument-side save commands send `:SAVE...` SCPI
so the oscilloscope writes to its current save directory, internal storage, or
attached USB storage. It does not create host-side image or waveform files,
does not resolve instrument filenames under the worker job directory, and does
not replace the PC-side `capture`, `capture-batch`, or `screenshot` workflows.

The only accepted request shapes are:

```json
{"command": "save-pwd", "arguments": {"query": true}}
```

```json
{"command": "save-pwd", "arguments": {"path": "USB:\\captures"}}
```

`save-filename` accepts exactly `{"query": true}` or `{"name": "scope_01"}`.
`save-image-format` accepts exactly `{"query": true}` or one canonical
`format`: `png`, `bmp`, `bmp8`, or `bmp24`. `save-image-palette`
accepts exactly `{"query": true}` or one canonical `palette`: `color` or
`grayscale`. `save-image-ink-saver` and `save-image-factors` accept exactly
`{"query": true}` or `{"enabled": true|false}` with a JSON boolean.

Start commands require an explicit filename:

```json
{"command": "save-image", "arguments": {"filename": "USB:/captures/screen.png"}}
```

```json
{"command": "save-waveform", "arguments": {"filename": "USB:/captures/wave.csv"}}
```

`save-waveform-format` accepts exactly `{"query": true}` or one canonical
`format`: `ascii-xy`, `csv`, or `binary`. Format query readbacks may use the
instrument sentinel `NONE`, which result JSON normalizes to canonical `none`.
`save-waveform-length` accepts exactly `{"query": true}` or integer `points`
of at least 100. The
actual maximum is instrument/model dependent. `save-waveform-length-max`
accepts only `{"query": true}` and queries the instrument's maximum-length
mode setting.

Every quoted string must be a non-empty printable ASCII JSON string without
double quotes, control characters, CR/LF, or semicolons. Paths and explicit
start filenames may contain `/`, `\`, and `:`. `save-filename` is base-name
only and additionally rejects path and drive separators. The worker never
trims, sanitizes, escapes, or appends an extension. Start commands send
`*OPC?` after the SAVE command before reporting success. `save-image`
temporarily uses a bounded 15-second timeout for that completion query and then
restores the prior session timeout. `save-waveform` retains the current session
timeout.

Unknown keys, aliases, empty arguments, `query: false`, query/configure mixes,
string or numeric booleans, wrong string types, non-integer points, and values
below 100 are rejected before enqueue, accepted counters, artifact creation,
simulator/VISA session open, or SCPI. Results, lister, mask, multi, power,
arbitrary, compliance, segmented, setup changes, and WMEMory export are not
included.

### Label And Annotation Commands

The worker supports the same one-shot label and annotation commands as the CLI:

- `channel-label`
- `display-label`
- `annotation`

Arguments use CLI option names without leading dashes:

```json
{"command": "channel-label", "arguments": {"channel": 1, "text": "Input A"}}
```

```json
{"command": "channel-label", "arguments": {"channel": 1, "query": true}}
```

```json
{"command": "display-label", "arguments": {"on": true}}
```

```json
{"command": "display-label", "arguments": {"off": true}}
```

```json
{"command": "display-label", "arguments": {"query": true}}
```

```json
{
  "command": "annotation",
  "arguments": {
    "slot": 1,
    "on": true,
    "text": "Run note",
    "color": "white",
    "background": "opaque"
  }
}
```

```json
{
  "command": "annotation",
  "arguments": {
    "slot": 2,
    "text": "Run note",
    "x": 10,
    "y": 20
  }
}
```

```json
{"command": "annotation", "arguments": {"slot": 2, "query": true}}
```

These are one-shot worker commands and may change front-panel display state.
They do not add digital labels, bus labels, `:DISPlay:LABList`
import/export, label position, or annotation batch operations.

`annotation` follows the CLI validation rules: `query` is mutually exclusive
with setters, `on` and `off` are mutually exclusive, `clear` and `text` are
mutually exclusive, and non-query requests require at least one setter/action.
4000X models support indexed annotation slots 1 through 10 and X/Y position.
2000X/3000X models use unindexed annotation slot 1 and do not support X/Y.
Annotation text accepts printable ASCII text up to 254 characters and must not
contain double quotes or control characters.

Validation errors must reject before enqueue and before any artifact, VISA, or
SCPI side effect.

Triggered capture `result.json.result.trigger` records raw operation-condition
poll values and the classified outcome. Only `natural` and `forced` outcomes
write capture artifacts. `timeout` and `unknown` outcomes return non-zero and
write no command artifacts. Unsupported live operation-condition values remain
unclassified and do not allow capture.

## Artifacts

Each accepted job creates:

```text
data/worker/<run_id>/<worker_job_id>/request.json
data/worker/<run_id>/<worker_job_id>/result.json
```

Worker job `request.json` and terminal `result.json` are Common Worker machine
artifacts and target exact integer `schema_version: 2`. Their Scopes-specific
fields and result layout remain unchanged.

`request.json` is written before the `202` response. `result.json` is written
only for terminal states using a temp file and atomic replace.

`result.json` contains:

- `schema_version`
- `run_id`
- `worker_job_id`
- client `job_id`
- `command`
- terminal `state`: `succeeded`, `failed`, or `cancelled`
- `ok`
- accepted/started/finished timestamps
- command `result`
- `files`
- `error`
- `exit_code`

Command artifacts keep existing Scopes meanings: CSV waveform data, PNG plots
or screenshots, metadata JSON, manifests, reports, and `scpi.log` files.
Worker `result.json` is the orchestrator machine source of truth; human output
is diagnostic only.

Worker path resolution applies only inside worker job execution. Direct
one-shot CLI commands keep their normal path semantics. For worker jobs,
relative output paths are resolved under
`data/worker/<run_id>/<worker_job_id>/`; absolute output paths are allowed and
recorded as absolute paths. Default worker outputs are:

- `capture`: `capture.csv` and `capture_meta.json` in the job directory; a
  plot is created only when a path string is supplied. With `wait_trigger`,
  these artifacts are written only when the trigger outcome allows capture.
- `screenshot`: `screen.png` in the job directory for default or PNG capture,
  and `screen.bmp` for BMP or BMP8bit capture. Query-only `query_hardcopy`
  creates no screenshot artifact.
- `capture-batch`, `measure-log`, `smoke`, and `acquisition-check`: the job
  directory is the default `output_dir`.
- `segmented-capture`: the fixed `segmented_capture` child directory below the
  job directory is the `output_dir`; its manifest, SCPI log, and successfully
  written per-segment CSV files are domain artifacts.

`sample-rate`, `acquisition-points`, `record-length`, `force-trigger`,
`system-clear-status`, `system-opc`, `system-status-byte`,
`system-standard-event`, `system-operation-status`, `system-options`,
`trigger-edge`, `trigger-edge-source`, `trigger-edge-slope`, `trigger-edge-level`,
`external-trigger-range`, `trigger-edge-external-level`,
`external-trigger-probe`, `external-trigger-units`, `external-trigger-settings`,
`trigger-edge-coupling`, `trigger-edge-reject`, `trigger-pulse-width`, `trigger-runt`, `trigger-transition`,
`trigger-delay`, `trigger-setup-hold`, `trigger-edge-burst`, `trigger-tv`,
`trigger-pattern`, `trigger-or`, `trigger-sweep`, `trigger-noise-reject`,
`trigger-hf-reject`, `display-clear`, `display-persistence`,
`display-intensity`, and `display-vectors` do not create command artifacts.
The `measure-clear`, `measure-show`, `measure-source`, `measure-window`,
`reference-save`, `reference-display`, `reference-label`, `reference-clear`,
`reference-query`, `dvm-enable`, `dvm-source`, `dvm-mode`, `dvm-auto-range`,
`dvm-current`, `dvm-query`, `demo-query`, `demo-output`, `demo-function`,
`demo-phase`, `wgen-query`, `wgen-output`, `wgen-function`, `wgen-frequency`,
`wgen-voltage`, `wgen-offset`, `wgen-load`, `serial-query`, `serial-mode`,
`serial-display`, `serial-uart`, `serial-i2c`, `serial-spi`, `serial-can`,
`serial-lister-query`, `serial-lister-display`, `serial-lister-reference`,
`search-state`, `search-mode`, `search-count`, `search-event`,
`serial-search-uart`, `serial-search-i2c`, `serial-search-spi`, and
`serial-search-can`
commands also do not create command artifacts.
`serial-lister-export` creates one CSV command artifact at the requested output
path and otherwise uses the standard worker `request.json` and `result.json`.
The `save-pwd`, `save-filename`, `save-image-format`, `save-image-palette`,
`save-image-ink-saver`, `save-image-factors`, `save-image`,
`save-waveform-format`, `save-waveform-length`,
`save-waveform-length-max`, and `save-waveform` commands likewise create no
command artifacts; standard worker `request.json` and terminal `result.json`
still apply.
Their terminal `result.json.result` contains the existing one-shot structured
`result` fields for that command. For `sample-rate` maximum queries, that
includes `query_kind: "maximum"` and `maximum_sample_rate_hz`.

Directory-output commands may use the worker job directory even though
`request.json` already exists there. Other pre-existing command artifact paths
are rejected before simulator/VISA open or SCPI execution. `result.json.files`
lists only command artifact paths that actually exist.

Live worker jobs validate identity before command-specific SCPI. The worker
opens the startup `resource`, sets a fixed `2000 ms` timeout, queries `*IDN?`,
resolves its manufacturer and model to a canonical physical model ID, and
compares that ID with the startup `model`. A mismatch
fails the job with structured `error.type: "identity_mismatch"`,
`expected_model`, and `actual_idn`; the worker control plane remains alive.

## Client Commands

Lifecycle clients:

- `scopes-tool send-command --host 127.0.0.1 --port 8765 --command identify --arguments-json {}`
- `scopes-tool status --host 127.0.0.1 --port 8765`
- `scopes-tool stop --host 127.0.0.1 --port 8765`
- `scopes-tool wait-ready --host 127.0.0.1 --port 8765`

Client exit codes are `0` for accepted/lifecycle success/dry-run success, `2`
for usage, local validation, or HTTP `400`, and `3` for runtime error,
connection error, timeout, invalid response, HTTP request failure, HTTP
`409`/`429`, or fatal worker failure.

## Safety

Live worker startup requires explicit `--resource`. Discovery is separate and
must not happen inside active live workflows. The worker does not guess,
rotate, or scan resources. This worker requirement is stricter than one-shot
CLI live selection, where an explicit resource is sufficient and `--live` is
only a compatibility flag.
