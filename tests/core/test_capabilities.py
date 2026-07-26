import pytest
import scopes_tool_core.capabilities as capabilities_module
import scopes_tool_core.identity as identity_module

from scopes_tool_core import PHYSICAL_MODEL_REGISTRY
from scopes_tool_core.capabilities import (
    ScopeCapabilities,
    capabilities_for_model,
    capabilities_for_model_id,
)
from scopes_tool_core.errors import UnsupportedModelError
from scopes_tool_core.identity import PhysicalModelInfo


def test_scope_capabilities_preserves_existing_optional_positional_order():
    capabilities = ScopeCapabilities(
        "TEST",
        4,
        1000,
        10000,
        True,
        False,
        True,
        False,
        True,
        False,
        False,
        True,
        2,
    )

    assert capabilities.supports_screenshot_format_pack is True
    assert capabilities.reference_waveforms == 2
    assert capabilities.math_function_count == 0
    assert capabilities.math_visualization_operations == frozenset()


@pytest.mark.parametrize(
    ("model", "series", "channels"),
    [
        ("DSOX2004A", "2000X", 4),
        ("DSO-X 2004A", "2000X", 4),
        ("DSOX3024A", "3000X", 4),
        ("DSO-X 3024A", "3000X", 4),
        ("DSOX4024A", "4000X", 4),
        ("DSO-X 4024A", "4000X", 4),
        ("DSOX4034A", "4000X", 4),
    ],
)
def test_capabilities_for_supported_models(model, series, channels):
    capabilities = capabilities_for_model(model)

    assert capabilities.series == series
    assert capabilities.analog_channels == channels
    assert capabilities.default_waveform_points == 1000
    assert capabilities.safe_max_waveform_points == 10000
    assert capabilities.supports_screenshot is True


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("DSOX2004A", False),
        ("DSOX3024A", True),
        ("DSOX4024A", True),
    ],
)
def test_impedance_50_ohm_support_comes_from_capability_profile(model, expected):
    assert capabilities_for_model(model).supports_50_ohm_impedance is expected


@pytest.mark.parametrize(
    "model, modes",
    [
        ("DSOX2004A", {"serial1"}),
        ("DSOX3024A", {"edge", "glitch", "runt", "transition", "serial1", "serial2"}),
        ("DSOX4034A", {"edge", "glitch", "runt", "transition", "serial1", "serial2", "peak"}),
    ],
)
def test_search_basic_support_comes_from_capability_profile(model, modes):
    capabilities = capabilities_for_model(model)
    assert capabilities.supports_search_basic is True
    assert capabilities.search_modes == frozenset(modes)


@pytest.mark.parametrize("model", ["DSOX2004A", "DSOX3024A", "DSOX4024A"])
def test_runtime_capabilities_enable_word_and_measurements(model):
    capabilities = capabilities_for_model(model)

    assert capabilities.supports_word_format is True
    assert capabilities.supports_measurements is True


def test_capabilities_keep_unsupported_future_surfaces_disabled():
    capabilities = capabilities_for_model("DSOX4024A")

    assert capabilities.supports_raw_points_mode is False
    assert capabilities.supports_segmented_memory is False
    assert capabilities.supports_serial_decode is False


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("DSOX2004A", False),
        ("DSOX3024A", False),
        ("DSOX4024A", True),
    ],
)
def test_delay_measurement_support_comes_from_capability_profile(model, expected):
    assert capabilities_for_model(model).supports_delay_measurement is expected


def test_capabilities_reject_unknown_model():
    with pytest.raises(UnsupportedModelError):
        capabilities_for_model("DSO-X-UNKNOWN")


@pytest.mark.parametrize(
    ("model_id", "profile_id", "series"),
    [
        (
            "keysight-dsox2004a",
            "keysight-infiniivision-2000x",
            "2000X",
        ),
        (
            "keysight-dsox3024a",
            "keysight-infiniivision-3000x",
            "3000X",
        ),
        (
            "keysight-dsox4024a",
            "keysight-infiniivision-4000x",
            "4000X",
        ),
        (
            "keysight-dsox4034a",
            "keysight-infiniivision-4000x",
            "4000X",
        ),
    ],
)
def test_registered_models_resolve_declared_capability_profile(
    model_id, profile_id, series
):
    physical_model = next(
        model for model in PHYSICAL_MODEL_REGISTRY if model.model_id == model_id
    )

    assert physical_model.capability_profile_id == profile_id
    assert capabilities_for_model_id(model_id).series == series


def test_4000x_registered_models_share_capability_profile():
    assert capabilities_for_model_id(
        "keysight-dsox4024a"
    ) is capabilities_for_model_id("keysight-dsox4034a")


def test_capabilities_reject_unknown_canonical_model_id():
    with pytest.raises(UnsupportedModelError, match="model ID"):
        capabilities_for_model_id("keysight-dsox9999a")


def test_capabilities_reject_unregistered_series_shaped_model():
    with pytest.raises(UnsupportedModelError):
        capabilities_for_model("DSOX4054A")


def test_model_only_capabilities_reject_ambiguous_vendor_match(monkeypatch):
    first = PhysicalModelInfo(
        model_id="vendor-a-model100",
        vendor_id="vendor-a",
        canonical_model="MODEL100",
        display_name="Vendor A Model 100",
        series="SYNTHETIC",
        capability_profile_id="synthetic-profile",
        driver_id="synthetic-driver",
    )
    second = PhysicalModelInfo(
        model_id="vendor-b-model100",
        vendor_id="vendor-b",
        canonical_model="MODEL100",
        display_name="Vendor B Model 100",
        series="SYNTHETIC",
        capability_profile_id="synthetic-profile",
        driver_id="synthetic-driver",
    )
    monkeypatch.setattr(
        identity_module,
        "_PHYSICAL_MODELS_BY_MODEL_NAME",
        {"MODEL100": (first, second)},
    )

    with pytest.raises(UnsupportedModelError, match="ambiguous"):
        capabilities_for_model("MODEL100")


def test_registered_model_missing_capability_profile_fails_clearly(monkeypatch):
    monkeypatch.setattr(capabilities_module, "_CAPABILITY_PROFILES", {})

    with pytest.raises(UnsupportedModelError, match="missing capability profile"):
        capabilities_for_model_id("keysight-dsox4024a")
