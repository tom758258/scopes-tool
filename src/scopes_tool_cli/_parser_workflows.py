"""CLI parsers for measurement, capture, and finite workflow commands."""

from __future__ import annotations

from scopes_tool_core.measurements import MEASUREMENT_ITEM_CHOICES

from ._parser_common import (
    _add_capture_channels_arg,
    _add_scope_connection_args,
    _add_waveform_transfer_args,
    _capture_channel_arg,
    _capture_until_count,
    _measurement_finite_float,
    _nonnegative_finite_float,
    _positive_int,
    _positive_plain_float,
    _strict_bool_arg,
)


def _register_workflow_parsers(subparsers) -> None:
    measure_parser = subparsers.add_parser(
        "measure",
        help="query one read-only measurement item for one or two analog channels",
    )
    _add_scope_connection_args(measure_parser)
    measure_parser.add_argument(
        "--channel",
        type=_positive_int,
        default=None,
        help="analog channel number, validated against the detected scope model",
    )
    measure_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        default=None,
        help="source analog channel number; --channel is a compatibility alias",
    )
    measure_parser.add_argument(
        "--reference-channel",
        type=_positive_int,
        default=None,
        help="reference analog channel number for phase or delay measurements",
    )
    measure_parser.add_argument(
        "--item",
        choices=MEASUREMENT_ITEM_CHOICES,
        required=True,
        help="measurement item to query",
    )
    measure_parser.add_argument(
        "--time",
        dest="time_s",
        type=_measurement_finite_float,
        default=None,
        help="trigger-relative time in seconds for y_at_x",
    )
    measure_parser.add_argument(
        "--level",
        type=_measurement_finite_float,
        default=None,
        help="voltage level for time_at_value",
    )
    measure_parser.add_argument(
        "--slope",
        choices=("positive", "negative"),
        default=None,
        help="edge or crossing slope for time_at_edge and time_at_value",
    )
    measure_parser.add_argument(
        "--occurrence",
        type=_positive_int,
        default=None,
        help="positive edge or crossing occurrence for time_at_edge and time_at_value",
    )

    measure_results_parser = subparsers.add_parser(
        "measure-results",
        help="query currently displayed front-panel measurement results",
    )
    _add_scope_connection_args(measure_results_parser)

    measure_stats_parser = subparsers.add_parser(
        "measure-stats",
        help="rebuild front-panel measurements and query statistics",
    )
    _add_scope_connection_args(measure_stats_parser)
    measure_stats_parser.add_argument("--channel", type=_positive_int, required=True)
    measure_stats_parser.add_argument("--items", required=True)
    measure_stats_parser.add_argument(
        "--mode",
        choices=("all", "current", "min", "max", "mean", "stddev", "count"),
        default="all",
    )
    measure_stats_parser.add_argument("--reset", action="store_true")
    measure_stats_parser.add_argument("--max-count", type=_positive_int, default=None)
    measure_stats_parser.add_argument(
        "--settle-seconds",
        type=_nonnegative_finite_float,
        default=None,
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="collect a read-only scope configuration snapshot for diagnostics",
    )
    _add_scope_connection_args(doctor_parser)

    measure_sweep_parser = subparsers.add_parser(
        "measure-sweep",
        help="query multiple read-only measurements and summarize failures",
    )
    _add_scope_connection_args(measure_sweep_parser)
    measure_sweep_parser.add_argument(
        "--channel",
        type=_capture_channel_arg,
        action="append",
        default=None,
        help="analog channel number; repeat or use all. Defaults to all channels",
    )
    measure_sweep_parser.add_argument(
        "--items",
        default="vpp,frequency,period,vrms",
        help="comma-separated single-channel measurement items",
    )
    measure_sweep_parser.add_argument(
        "--pair",
        action="append",
        default=[],
        metavar="SRC:REF",
        help="source/reference channel pair such as 1:2; repeatable",
    )
    measure_sweep_parser.add_argument(
        "--pair-items",
        default="phase,delay",
        help="comma-separated pair measurement items; only used with --pair",
    )

    capture_parser = subparsers.add_parser(
        "capture",
        help="capture one or more analog channel waveforms to CSV and metadata JSON",
    )
    _add_scope_connection_args(capture_parser)
    _add_capture_channels_arg(capture_parser)
    _add_waveform_transfer_args(capture_parser)
    capture_parser.add_argument(
        "--csv",
        dest="csv_path",
        default=None,
        help="output CSV path; defaults to data/<UTC+8 timestamp>.csv",
    )
    capture_parser.add_argument(
        "--meta",
        dest="meta_path",
        default=None,
        help="output metadata JSON path; defaults to <csv stem>_meta.json",
    )
    capture_parser.add_argument(
        "--plot",
        dest="plot_path",
        default=None,
        help="optional output PNG plot path",
    )
    capture_parser.add_argument(
        "--allow-time-axis-tolerance",
        action="store_true",
        help=(
            "allow small multi-channel time-axis drift up to half the first "
            "channel sample interval"
        ),
    )
    capture_parser.add_argument(
        "--wait-trigger",
        action="store_true",
        help="arm a single acquisition and poll for trigger completion before capture",
    )
    capture_parser.add_argument(
        "--trigger-timeout-ms",
        type=_positive_int,
        default=None,
        help="finite trigger wait timeout in milliseconds; required with --wait-trigger",
    )
    capture_parser.add_argument(
        "--trigger-poll-interval-ms",
        type=_positive_int,
        default=100,
        help="trigger wait polling interval in milliseconds; defaults to 100",
    )
    capture_parser.add_argument(
        "--force-trigger-on-timeout",
        action="store_true",
        help="after trigger wait timeout, send :TRIGger:FORCe and continue finite polling",
    )

    capture_batch_parser = subparsers.add_parser(
        "capture-batch",
        help="capture a finite batch of analog waveforms into one output directory",
    )
    _add_scope_connection_args(capture_batch_parser)
    _add_capture_channels_arg(capture_batch_parser)
    _add_waveform_transfer_args(capture_batch_parser)
    capture_batch_parser.add_argument(
        "--count",
        type=_positive_int,
        required=True,
        help="finite number of waveform captures to run",
    )
    capture_batch_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=0.0,
        help="seconds to sleep between captures; defaults to 0",
    )
    capture_batch_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "output directory; defaults to data/captures/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )

    capture_until_parser = subparsers.add_parser(
        "capture-until",
        allow_abbrev=False,
        help="capture matching waveform acquisitions until a finite count or timeout",
    )
    _add_scope_connection_args(capture_until_parser)
    _add_capture_channels_arg(capture_until_parser)
    capture_until_parser.add_argument(
        "--condition-channel", type=_positive_int, required=True
    )
    _add_waveform_transfer_args(capture_until_parser)
    capture_until_parser.add_argument(
        "--metric",
        choices=("max", "min", "peak-to-peak", "abs-max"),
        required=True,
    )
    capture_until_parser.add_argument(
        "--operator", choices=("gt", "gte", "lt", "lte"), required=True
    )
    capture_until_parser.add_argument(
        "--threshold", type=_measurement_finite_float, required=True
    )
    capture_until_parser.add_argument(
        "--count",
        type=_capture_until_count,
        default=1,
        help="matching acquisitions to save; defaults to 1, maximum 255",
    )
    capture_until_parser.add_argument(
        "--timeout-seconds", type=_positive_plain_float, required=True
    )
    capture_until_parser.add_argument(
        "--interval-seconds", type=_nonnegative_finite_float, default=0.0
    )
    capture_until_parser.add_argument("--output-dir", default=None)

    capture_monitor_parser = subparsers.add_parser(
        "capture-monitor",
        allow_abbrev=False,
        help="monitor a finite waveform series with bounded retained history",
    )
    _add_scope_connection_args(capture_monitor_parser)
    _add_capture_channels_arg(capture_monitor_parser)
    _add_waveform_transfer_args(capture_monitor_parser)
    capture_monitor_parser.add_argument("--count", type=_positive_int, required=True)
    capture_monitor_parser.add_argument(
        "--interval-seconds", type=_nonnegative_finite_float, default=0.0
    )
    capture_monitor_parser.add_argument(
        "--retention-points", type=_positive_int, default=250000
    )
    capture_monitor_parser.add_argument("--output-dir", default=None)
    capture_monitor_parser.add_argument(
        "--no-save",
        action="store_true",
        help="run without creating retained waveform result files",
    )

    measure_log_parser = subparsers.add_parser(
        "measure-log",
        help="log a finite batch of single-channel and channel-pair measurements to CSV",
    )
    _add_scope_connection_args(measure_log_parser)
    measure_log_parser.add_argument(
        "--channel",
        "--source-channel",
        dest="channel",
        type=_capture_channel_arg,
        action="append",
        default=None,
        help="analog channel number to log; repeat for multiple channels, or use all",
    )
    measure_log_parser.add_argument(
        "--items",
        default="vpp,frequency",
        help="comma-separated single-channel measurements; defaults to vpp,frequency",
    )
    measure_log_parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="repeatable source/reference channel pairs (SRC:REF)",
    )
    measure_log_parser.add_argument(
        "--pair-items",
        default="phase,delay",
        help="comma-separated pair measurements; defaults to phase,delay",
    )
    measure_log_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=1.0,
        help="seconds to sleep between log rows; defaults to 1.0",
    )
    measure_log_parser.add_argument(
        "--count",
        type=_positive_int,
        default=None,
        help="total number of log rows to capture; required unless --duration-seconds is set",
    )
    measure_log_parser.add_argument(
        "--duration-seconds",
        type=_positive_plain_float,
        default=None,
        help="maximum duration in seconds; required unless --count is set",
    )
    measure_log_parser.add_argument(
        "--output-dir",
        default=None,
        help="output directory; if provided, it must not exist or must be empty",
    )
    measure_log_parser.add_argument(
        "--no-save",
        action="store_true",
        help="run without creating measurement result files",
    )
    measure_log_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="abort logging immediately if an instrument system error is detected",
    )

    measure_until_parser = subparsers.add_parser(
        "measure-until",
        allow_abbrev=False,
        help="query one measurement until a numeric condition matches or times out",
    )
    _add_scope_connection_args(measure_until_parser)
    measure_until_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="one analog channel number",
    )
    measure_until_parser.add_argument(
        "--item",
        required=True,
        help="one non-parameterized single-channel measurement item",
    )
    measure_until_parser.add_argument(
        "--operator",
        choices=("gt", "gte", "lt", "lte"),
        required=True,
        help="numeric comparison operator",
    )
    measure_until_parser.add_argument(
        "--threshold",
        type=_measurement_finite_float,
        required=True,
        help="finite threshold in the measurement item's native unit",
    )
    measure_until_parser.add_argument(
        "--timeout-seconds",
        type=_positive_plain_float,
        required=True,
        help="positive finite workflow timeout",
    )
    measure_until_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=1.0,
        help="interruptible wait after a completed non-matching sample; defaults to 1.0",
    )
    measure_until_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "workflow run directory; defaults to "
            "data/measure_until/<UTC+8 timestamp>"
        ),
    )
    measure_until_parser.add_argument(
        "--no-save",
        action="store_true",
        help="run without creating measurement result files",
    )

    triggered_measure_loop_parser = subparsers.add_parser(
        "triggered-measure-loop",
        allow_abbrev=False,
        help="run a finite Single, trigger-wait, and measurement loop",
    )
    _add_scope_connection_args(triggered_measure_loop_parser)
    triggered_measure_loop_parser.add_argument(
        "--channel",
        "--source-channel",
        dest="channel",
        type=_capture_channel_arg,
        action="append",
        default=None,
        help="analog channel to measure; repeat for multiple channels, or use all",
    )
    triggered_measure_loop_parser.add_argument(
        "--items",
        default="vpp,frequency",
        help="comma-separated single-channel measurements; defaults to vpp,frequency",
    )
    triggered_measure_loop_parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="repeatable source/reference channel pairs (SRC:REF)",
    )
    triggered_measure_loop_parser.add_argument(
        "--pair-items",
        default="phase,delay",
        help="comma-separated pair measurements; defaults to phase,delay",
    )
    triggered_measure_loop_parser.add_argument(
        "--count",
        type=_positive_int,
        required=True,
        help="finite number of trigger and measurement cycles",
    )
    triggered_measure_loop_parser.add_argument(
        "--trigger-timeout-seconds",
        type=_positive_plain_float,
        required=True,
        help="positive finite timeout for each trigger wait",
    )
    triggered_measure_loop_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=0.0,
        help="interruptible wait after a completed cycle; defaults to 0",
    )
    triggered_measure_loop_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "workflow run directory; defaults to "
            "data/triggered_measure_loops/<UTC+8 timestamp>"
        ),
    )
    triggered_measure_loop_parser.add_argument(
        "--no-save",
        action="store_true",
        help="run without creating measurement result files",
    )

    triggered_capture_series_parser = subparsers.add_parser(
        "triggered-capture-series",
        allow_abbrev=False,
        help="run a finite Single, trigger-wait, and waveform capture series",
    )
    _add_scope_connection_args(triggered_capture_series_parser)
    _add_capture_channels_arg(triggered_capture_series_parser)
    _add_waveform_transfer_args(triggered_capture_series_parser)
    triggered_capture_series_parser.add_argument(
        "--count",
        type=_positive_int,
        required=True,
        help="finite number of triggered waveform capture cycles",
    )
    triggered_capture_series_parser.add_argument(
        "--trigger-timeout-seconds",
        type=_positive_plain_float,
        required=True,
        help="positive finite timeout for each trigger wait",
    )
    triggered_capture_series_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=0.0,
        help="interruptible wait after a persisted cycle; defaults to 0",
    )
    triggered_capture_series_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "workflow run directory; defaults to "
            "data/triggered_capture_series/<UTC+8 timestamp>"
        ),
    )

    sequence_parser = subparsers.add_parser(
        "sequence",
        allow_abbrev=False,
        help="run a finite ordered Generic Sequence v1 JSON document",
    )
    _add_scope_connection_args(sequence_parser)
    sequence_parser.add_argument(
        "--file",
        dest="sequence_file",
        required=True,
        help="Generic Sequence v1 JSON document path",
    )
    sequence_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "sequence run directory; defaults to data/sequences/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )
    sequence_parser.add_argument(
        "--no-save",
        action="store_true",
        help="disable host-side sequence result files (manifest, scpi.log); not compatible with capture or screenshot steps",
    )

    screenshot_parser = subparsers.add_parser(
        "screenshot",
        help="capture the current oscilloscope screen to an image file",
    )
    _add_scope_connection_args(screenshot_parser)
    screenshot_parser.add_argument(
        "--output",
        dest="output_path",
        default=None,
        help="output image path; defaults to data/<UTC+8 timestamp>.<format>",
    )
    screenshot_parser.add_argument(
        "--background",
        choices=("black", "white"),
        default=None,
        help="screenshot background color; defaults to black",
    )
    screenshot_parser.add_argument("--format", choices=("png", "bmp", "bmp8bit"))
    screenshot_parser.add_argument("--ink-saver", type=_strict_bool_arg)
    screenshot_parser.add_argument(
        "--palette", choices=("color", "grayscale", "none")
    )
    screenshot_parser.add_argument(
        "--layout", choices=("landscape", "portrait")
    )
    screenshot_parser.add_argument(
        "--query-hardcopy",
        action="store_true",
        help="query hardcopy state without capturing image bytes",
    )

    smoke_parser = subparsers.add_parser(
        "smoke",
        help="run a capture-safe diagnostic smoke test and write a report directory",
    )
    _add_scope_connection_args(smoke_parser)
    smoke_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "output directory; defaults to data/hardware_smoke/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )
