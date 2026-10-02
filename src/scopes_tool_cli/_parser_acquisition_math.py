"""CLI parsers for acquisition, setup, FFT, and Math commands."""

from __future__ import annotations

from scopes_tool_core.fft import (
    FFT_DETECTION_TYPES,
    FFT_GATES,
    FFT_OPERATIONS,
    FFT_PHASE_REFERENCES,
)
from scopes_tool_core.math import (
    MATH_COMPOSITE_OPERATIONS,
    MATH_FILTER_OPERATIONS,
    MATH_OPERATIONS,
    MATH_SOURCES,
    MATH_TRANSFORM_SOURCES,
    MATH_TRANSFORMS,
    MATH_TREND_MEASUREMENTS,
    MATH_VISUALIZATION_OPERATIONS,
)

from ._parser_common import (
    _add_function_arg,
    _add_scope_connection_args,
    _add_waveform_transfer_args,
    _measurement_finite_float,
    _nonnegative_finite_float,
    _positive_int,
    _positive_plain_float,
    _setup_slot_arg,
)


def _register_acquisition_math_parsers(subparsers) -> None:
    sample_rate_parser = subparsers.add_parser(
        "sample-rate",
        help="query the current analog acquisition sample rate",
    )
    _add_scope_connection_args(sample_rate_parser)
    sample_rate_parser.add_argument(
        "--query",
        dest="sample_rate_query",
        action="store_true",
        required=True,
        help="query the current analog acquisition sample rate",
    )
    sample_rate_parser.add_argument(
        "--maximum",
        dest="sample_rate_maximum",
        action="store_true",
        help="query the maximum analog acquisition sample rate",
    )

    acquisition_points_parser = subparsers.add_parser(
        "acquisition-points",
        help="query the current analog acquisition points",
    )
    _add_scope_connection_args(acquisition_points_parser)
    acquisition_points_parser.add_argument(
        "--query",
        dest="acquisition_points_query_flag",
        action="store_true",
        required=True,
        help="query the current analog acquisition points",
    )

    record_length_parser = subparsers.add_parser(
        "record-length",
        help="query the current analog acquisition record length",
    )
    _add_scope_connection_args(record_length_parser)
    record_length_parser.add_argument(
        "--query",
        dest="record_length_query_flag",
        action="store_true",
        required=True,
        help="query the current analog acquisition record length",
    )

    segmented_memory_parser = subparsers.add_parser(
        "segmented-memory",
        allow_abbrev=False,
        help="query or configure segmented-memory acquisition",
    )
    _add_scope_connection_args(segmented_memory_parser)
    segmented_operation_group = segmented_memory_parser.add_mutually_exclusive_group(
        required=True
    )
    segmented_operation_group.add_argument(
        "--query",
        action="store_true",
        help="query segmented-memory state",
    )
    segmented_operation_group.add_argument(
        "--enable",
        action="store_true",
        help="enable segmented-memory acquisition",
    )
    segmented_operation_group.add_argument(
        "--disable",
        action="store_true",
        help="disable segmented-memory acquisition",
    )
    segmented_memory_parser.add_argument(
        "--segments",
        type=int,
        default=None,
        help="configured segmented-memory count when enabling",
    )

    segmented_capture_parser = subparsers.add_parser(
        "segmented-capture",
        allow_abbrev=False,
        help="capture finite segmented waveforms to per-segment CSV files",
    )
    _add_scope_connection_args(segmented_capture_parser)
    segmented_capture_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="single analog channel number",
    )
    segmented_capture_parser.add_argument(
        "--segments",
        type=int,
        required=True,
        help="requested segmented acquisition count",
    )
    _add_waveform_transfer_args(segmented_capture_parser)
    segmented_capture_parser.add_argument(
        "--timeout-ms",
        type=_positive_int,
        default=30000,
        help="finite segmented acquisition timeout in milliseconds",
    )
    segmented_capture_parser.add_argument(
        "--poll-interval-ms",
        type=_positive_int,
        default=100,
        help="operation-condition readiness polling interval in milliseconds",
    )
    segmented_capture_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "output directory; defaults to data/segmented_captures/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )

    acquisition_parser = subparsers.add_parser(
        "acquisition",
        help="configure or query acquisition type and average count",
    )
    _add_scope_connection_args(acquisition_parser)
    acquisition_parser.add_argument(
        "--query",
        dest="acq_query",
        action="store_true",
        help="query acquisition type and average count",
    )
    acquisition_parser.add_argument(
        "--type",
        dest="acq_type",
        default=None,
        help=(
            "acquisition type: normal/norm, average/aver/avg, "
            "high_resolution/high-resolution/hresolution/hres, peak/peak_detect/peak-detect"
        ),
    )
    acquisition_parser.add_argument(
        "--count",
        dest="acq_count",
        type=_positive_int,
        default=None,
        help="average count (only valid with --type average)",
    )

    autoscale_parser = subparsers.add_parser("autoscale", help="run oscilloscope autoscale")
    _add_scope_connection_args(autoscale_parser)
    autoscale_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        action="append",
        default=None,
        help="analog channel source; repeat to autoscale selected sources",
    )
    autoscale_parser.add_argument(
        "--acquire-mode",
        choices=("normal", "current"),
        default=None,
    )
    autoscale_parser.add_argument(
        "--channels",
        choices=("all", "displayed"),
        default=None,
    )

    setup_save_parser = subparsers.add_parser("setup-save", help="save setup to slot or file")
    _add_scope_connection_args(setup_save_parser)
    save_target = setup_save_parser.add_mutually_exclusive_group(required=True)
    save_target.add_argument("--slot", type=_setup_slot_arg, default=None)
    save_target.add_argument("--file", dest="setup_file", default=None)

    setup_recall_parser = subparsers.add_parser("setup-recall", help="recall setup from slot or file")
    _add_scope_connection_args(setup_recall_parser)
    recall_target = setup_recall_parser.add_mutually_exclusive_group(required=True)
    recall_target.add_argument("--slot", type=_setup_slot_arg, default=None)
    recall_target.add_argument("--file", dest="setup_file", default=None)

    fft_parser = subparsers.add_parser("fft", help="configure or query FFT math function")
    _add_scope_connection_args(fft_parser)
    fft_parser.add_argument("--query", dest="fft_query", action="store_true")
    _add_function_arg(fft_parser)
    fft_parser.add_argument("--source-channel", type=_positive_int, default=None)
    fft_parser.add_argument("--units", choices=("decibel", "vrms"), default=None)
    fft_parser.add_argument(
        "--window",
        choices=("rectangular", "hanning", "flattop", "bharris", "bartlett"),
        default=None,
    )
    fft_parser.add_argument("--center-hz", type=_nonnegative_finite_float, default=None)
    fft_parser.add_argument("--span-hz", type=_positive_plain_float, default=None)
    fft_parser.add_argument("--fft-operation", choices=FFT_OPERATIONS, default=None)
    fft_parser.add_argument("--start-hz", type=_measurement_finite_float, default=None)
    fft_parser.add_argument("--stop-hz", type=_measurement_finite_float, default=None)
    fft_parser.add_argument("--gate", choices=FFT_GATES, default=None)
    fft_parser.add_argument(
        "--phase-reference", choices=FFT_PHASE_REFERENCES, default=None
    )
    fft_parser.add_argument(
        "--detection-type", choices=FFT_DETECTION_TYPES, default=None
    )
    fft_parser.add_argument("--detection-points", type=_positive_int, default=None)
    fft_parser.add_argument("--display", choices=("on", "off"), default=None)

    math_display_parser = subparsers.add_parser(
        "math-display",
        allow_abbrev=False,
        help="enable, disable, or query one instrument-side Math waveform display",
    )
    _add_scope_connection_args(math_display_parser)
    _add_function_arg(math_display_parser)
    math_display_action = math_display_parser.add_mutually_exclusive_group(
        required=True
    )
    math_display_action.add_argument(
        "--on", dest="math_display_action", action="store_const", const="on"
    )
    math_display_action.add_argument(
        "--off", dest="math_display_action", action="store_const", const="off"
    )
    math_display_action.add_argument(
        "--query", dest="math_display_action", action="store_const", const="query"
    )

    math_vertical_parser = subparsers.add_parser(
        "math-vertical",
        allow_abbrev=False,
        help="configure or query instrument-side Math waveform vertical controls",
    )
    _add_scope_connection_args(math_vertical_parser)
    _add_function_arg(math_vertical_parser)
    math_vertical_parser.add_argument(
        "--query", dest="math_vertical_query", action="store_true"
    )
    math_vertical_size = math_vertical_parser.add_mutually_exclusive_group()
    math_vertical_size.add_argument(
        "--scale", type=_positive_plain_float, default=None
    )
    math_vertical_size.add_argument(
        "--range", dest="range_value", type=_positive_plain_float, default=None
    )
    math_vertical_parser.add_argument(
        "--offset", type=_measurement_finite_float, default=None
    )

    math_operator_parser = subparsers.add_parser(
        "math-operator",
        allow_abbrev=False,
        help="configure or query an instrument-side dual-source Math operator",
    )
    _add_scope_connection_args(math_operator_parser)
    _add_function_arg(math_operator_parser)
    math_operator_parser.add_argument(
        "--query", dest="math_operator_query", action="store_true"
    )
    math_operator_parser.add_argument(
        "--operation", dest="math_operation", choices=MATH_OPERATIONS, default=None
    )
    math_operator_parser.add_argument("--source1", choices=MATH_SOURCES, default=None)
    math_operator_parser.add_argument("--source2", choices=MATH_SOURCES, default=None)

    math_composite_parser = subparsers.add_parser(
        "math-composite-source",
        allow_abbrev=False,
        help="configure or query the 2000X/3000X global Math composite source",
    )
    _add_scope_connection_args(math_composite_parser)
    math_composite_parser.add_argument(
        "--query", dest="math_composite_query", action="store_true"
    )
    math_composite_parser.add_argument(
        "--operation",
        dest="math_composite_operation",
        choices=MATH_COMPOSITE_OPERATIONS,
        default=None,
    )
    math_composite_parser.add_argument("--source1", choices=MATH_SOURCES, default=None)
    math_composite_parser.add_argument("--source2", choices=MATH_SOURCES, default=None)

    math_transform_parser = subparsers.add_parser(
        "math-transform",
        allow_abbrev=False,
        help="configure or query an instrument-side single-source Math transform",
    )
    _add_scope_connection_args(math_transform_parser)
    _add_function_arg(math_transform_parser)
    math_transform_parser.add_argument(
        "--query", dest="math_transform_query", action="store_true"
    )
    math_transform_parser.add_argument(
        "--operation",
        dest="math_transform_operation",
        choices=MATH_TRANSFORMS,
        default=None,
    )
    math_transform_parser.add_argument(
        "--source", choices=MATH_TRANSFORM_SOURCES, default=None
    )
    math_transform_parser.add_argument(
        "--input-offset", type=_measurement_finite_float, default=None
    )
    math_transform_parser.add_argument(
        "--gain", type=_measurement_finite_float, default=None
    )
    math_transform_parser.add_argument(
        "--linear-offset", type=_measurement_finite_float, default=None
    )

    math_filter_parser = subparsers.add_parser(
        "math-filter",
        allow_abbrev=False,
        help="configure or query an instrument-side single-source Math filter",
    )
    _add_scope_connection_args(math_filter_parser)
    _add_function_arg(math_filter_parser)
    math_filter_parser.add_argument(
        "--query", dest="math_filter_query", action="store_true"
    )
    math_filter_parser.add_argument(
        "--operation",
        dest="math_filter_operation",
        choices=MATH_FILTER_OPERATIONS,
        default=None,
    )
    math_filter_parser.add_argument(
        "--source", choices=MATH_TRANSFORM_SOURCES, default=None
    )
    math_filter_parser.add_argument(
        "--cutoff-hz", type=_positive_plain_float, default=None
    )
    math_filter_parser.add_argument("--average-count", type=_positive_int, default=None)
    math_filter_parser.add_argument("--smooth-points", type=_positive_int, default=None)

    math_visualization_parser = subparsers.add_parser(
        "math-visualization",
        allow_abbrev=False,
        help="configure or query an instrument-side Math visualization",
    )
    _add_scope_connection_args(math_visualization_parser)
    _add_function_arg(math_visualization_parser)
    math_visualization_parser.add_argument(
        "--query", dest="math_visualization_query", action="store_true"
    )
    math_visualization_parser.add_argument(
        "--operation",
        dest="math_visualization_operation",
        choices=MATH_VISUALIZATION_OPERATIONS,
        default=None,
    )
    math_visualization_parser.add_argument(
        "--source", choices=MATH_TRANSFORM_SOURCES, default=None
    )
    math_visualization_parser.add_argument(
        "--source2", choices=MATH_SOURCES, default=None
    )
    math_visualization_parser.add_argument(
        "--measurement", choices=MATH_TREND_MEASUREMENTS, default=None
    )
    math_visualization_parser.add_argument(
        "--measurement-slot", type=_positive_int, default=None
    )

    math_clear_parser = subparsers.add_parser(
        "math-clear",
        allow_abbrev=False,
        help="clear one supported instrument-side Math accumulation",
    )
    _add_scope_connection_args(math_clear_parser)
    _add_function_arg(math_clear_parser)

    acquisition_check_parser = subparsers.add_parser(
        "acquisition-check",
        help="run the acquisition configuration hardware validation workflow",
    )
    _add_scope_connection_args(acquisition_check_parser)
    acquisition_check_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "output directory; defaults to data/hardware_acquisition/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )
    acquisition_check_parser.add_argument(
        "--average-count",
        type=_positive_int,
        default=16,
        help="average acquisition count to validate; defaults to 16",
    )
    acquisition_check_parser.add_argument(
        "--check-only",
        action="store_true",
        help="only query the current acquisition configuration and system error",
    )
    acquisition_check_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="stop the workflow after the first acquisition step with a system error",
    )
    acquisition_check_parser.add_argument(
        "--restore-type",
        action="store_true",
        help="restore the initial acquisition type after the workflow completes",
    )
