"""Runtime model capability profiles."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import UnsupportedModelError
from .identity import physical_model_for_id, resolve_registered_model_name


@dataclass(frozen=True)
class ScopeCapabilities:
    """Runtime-supported capability profile for an oscilloscope model."""

    series: str
    analog_channels: int
    default_waveform_points: int
    safe_max_waveform_points: int
    supports_word_format: bool
    supports_raw_points_mode: bool
    supports_measurements: bool
    supports_delay_measurement: bool
    supports_screenshot: bool
    supports_segmented_memory: bool
    supports_serial_decode: bool
    supports_screenshot_hardcopy_controls: bool = False
    reference_waveforms: int = 0
    supports_channel_label: bool = False
    channel_label_max_length: int = 0
    supports_display_label: bool = False
    supports_annotation: bool = False
    supports_annotation_position: bool = False
    annotation_slots: int = 0
    supports_indexed_annotation: bool = False
    supports_50_ohm_impedance: bool = False
    supports_search_basic: bool = False
    supports_search_event_navigation: bool = False
    search_modes: frozenset[str] = frozenset()
    supports_demo: bool = False
    demo_functions: frozenset[str] = frozenset()
    supports_wgen: bool = False
    wgen_scpi_root: str = ""
    math_function_count: int = 0
    supports_math_goft: bool = False
    supports_math_cascade: bool = False
    math_filter_operations: frozenset[str] = frozenset()
    math_visualization_operations: frozenset[str] = frozenset()
    supports_advanced_fft: bool = False
    supports_measure_results_dump: bool = False
    serial_bus_count: int = 0
    serial_modes: frozenset[str] = frozenset()
    segmented_max_segments: int = 0
    supports_segmented_waveform_all: bool = False


_DEMO_COMMON_FUNCTIONS = frozenset(
    {
        "sine", "noisy", "phase", "lf-sine", "am", "rf-burst", "fm-burst",
        "harmonics", "coupling", "ringing", "single", "clock", "runt",
        "transition", "setup-hold", "mso", "burst", "glitch",
        "edge-then-edge", "i2c", "uart", "spi", "can", "lin",
    }
)
_DEMO_3000X_EXTENSIONS = frozenset(
    {"i2s", "can-lin", "flexray", "arinc", "mil", "mil2"}
)


_CAPABILITY_PROFILES = {
    "keysight-infiniivision-2000x": ScopeCapabilities(
        series="2000X",
        analog_channels=4,
        default_waveform_points=1000,
        safe_max_waveform_points=10000,
        supports_word_format=True,
        supports_raw_points_mode=False,
        supports_measurements=True,
        supports_delay_measurement=False,
        supports_screenshot=True,
        supports_segmented_memory=True,
        supports_serial_decode=True,
        serial_bus_count=1,
        serial_modes=frozenset({"can", "i2c", "lin", "spi", "uart"}),
        math_function_count=1,
        supports_math_goft=True,
        math_filter_operations=frozenset({"low-pass", "high-pass"}),
        math_visualization_operations=frozenset({"magnify", "trend"}),
        reference_waveforms=2,
        supports_channel_label=True,
        channel_label_max_length=10,
        supports_display_label=True,
        supports_annotation=True,
        supports_annotation_position=False,
        annotation_slots=1,
        supports_indexed_annotation=False,
        supports_50_ohm_impedance=False,
        supports_search_basic=True,
        search_modes=frozenset({"serial1"}),
        supports_demo=True,
        demo_functions=_DEMO_COMMON_FUNCTIONS,
        supports_wgen=True,
        wgen_scpi_root=":WGEN",
        segmented_max_segments=250,
    ),
    "keysight-infiniivision-3000x": ScopeCapabilities(
        series="3000X",
        analog_channels=4,
        default_waveform_points=1000,
        safe_max_waveform_points=10000,
        supports_word_format=True,
        supports_raw_points_mode=False,
        supports_measurements=True,
        supports_delay_measurement=False,
        supports_measure_results_dump=True,
        supports_screenshot=True,
        supports_segmented_memory=True,
        supports_serial_decode=True,
        serial_bus_count=2,
        serial_modes=frozenset(
            {"a429", "flexray", "can", "i2s", "i2c", "lin", "m1553", "spi", "uart"}
        ),
        math_function_count=1,
        supports_math_goft=True,
        math_filter_operations=frozenset({"low-pass", "high-pass"}),
        math_visualization_operations=frozenset({"magnify", "trend"}),
        reference_waveforms=2,
        supports_channel_label=True,
        channel_label_max_length=10,
        supports_display_label=True,
        supports_annotation=True,
        supports_annotation_position=False,
        annotation_slots=1,
        supports_indexed_annotation=False,
        supports_50_ohm_impedance=True,
        supports_search_basic=True,
        search_modes=frozenset(
            {"edge", "glitch", "runt", "transition", "serial1", "serial2"}
        ),
        supports_demo=True,
        demo_functions=_DEMO_COMMON_FUNCTIONS | _DEMO_3000X_EXTENSIONS,
        supports_wgen=True,
        wgen_scpi_root=":WGEN",
        segmented_max_segments=1000,
    ),
    "keysight-infiniivision-4000x": ScopeCapabilities(
        series="4000X",
        analog_channels=4,
        default_waveform_points=1000,
        safe_max_waveform_points=10000,
        supports_word_format=True,
        supports_raw_points_mode=False,
        supports_measurements=True,
        supports_delay_measurement=True,
        supports_measure_results_dump=True,
        supports_screenshot=True,
        supports_segmented_memory=True,
        supports_serial_decode=True,
        serial_bus_count=2,
        serial_modes=frozenset(
            {
                "a429",
                "flexray",
                "can",
                "cxpi",
                "i2s",
                "i2c",
                "lin",
                "m1553",
                "manchester",
                "nrz",
                "sent",
                "spi",
                "uart",
                "usb",
                "usb-pd",
            }
        ),
        math_function_count=4,
        supports_math_cascade=True,
        supports_advanced_fft=True,
        math_filter_operations=frozenset(
            {"low-pass", "high-pass", "average", "smooth", "envelope"}
        ),
        math_visualization_operations=frozenset(
            {
                "magnify",
                "trend",
                "maximum",
                "minimum",
                "peak",
                "max-hold",
                "min-hold",
            }
        ),
        supports_screenshot_hardcopy_controls=True,
        reference_waveforms=2,
        supports_channel_label=True,
        channel_label_max_length=32,
        supports_display_label=True,
        supports_annotation=True,
        supports_annotation_position=True,
        annotation_slots=10,
        supports_indexed_annotation=True,
        supports_50_ohm_impedance=True,
        supports_search_basic=True,
        supports_search_event_navigation=True,
        search_modes=frozenset(
            {
                "edge",
                "glitch",
                "runt",
                "transition",
                "serial1",
                "serial2",
                "peak",
            }
        ),
        supports_demo=True,
        demo_functions=_DEMO_COMMON_FUNCTIONS | _DEMO_3000X_EXTENSIONS,
        supports_wgen=True,
        wgen_scpi_root=":WGEN1",
        segmented_max_segments=1000,
        supports_segmented_waveform_all=True,
    ),
}


def capabilities_for_model_id(model_id: str) -> ScopeCapabilities:
    """Return capabilities for a registered canonical physical model ID."""

    physical_model = physical_model_for_id(model_id)
    profile = _CAPABILITY_PROFILES.get(physical_model.capability_profile_id)
    if profile is None:
        raise UnsupportedModelError(
            f"Physical model {model_id} references missing capability profile: "
            f"{physical_model.capability_profile_id}"
        )
    return profile


def capabilities_for_model(model: str) -> ScopeCapabilities:
    """Return capabilities for an unambiguous registered model-only name."""

    physical_model = resolve_registered_model_name(model)
    return capabilities_for_model_id(physical_model.model_id)
