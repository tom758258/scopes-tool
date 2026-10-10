"""Explicit image formats drive screenshot admission and PNG workflows."""

from dataclasses import replace

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY
from scopes_tool_core.screenshot import ScreenshotOptions, validate_screenshot_capability
from scopes_tool_core.errors import ParameterValidationError


@pytest.mark.parametrize("model", PHYSICAL_MODEL_REGISTRY, ids=lambda model: model.model_id)
def test_screenshot_format_predicates_agree(model):
    caps = capabilities_for_model_id(model.model_id)
    assert caps.supports_png_screenshot == ("png" in caps.screenshot_formats)
    assert caps.supports_any_screenshot == bool(caps.screenshot_formats)
    if caps.supported_sequence_actions is not None:
        assert ("screenshot" in caps.supported_sequence_actions) == caps.supports_png_screenshot


def test_screenshot_formats_define_capture_support():
    caps = capabilities_for_model_id("tektronix-tds2024b")
    bmp = caps
    assert bmp.supports_any_screenshot and not bmp.supports_png_screenshot
    validate_screenshot_capability(bmp, ScreenshotOptions(format="bmp"))
    with pytest.raises(ParameterValidationError):
        validate_screenshot_capability(bmp, ScreenshotOptions())
    png = replace(caps, screenshot_formats=("png",))
    assert png.supports_png_screenshot
    validate_screenshot_capability(png, ScreenshotOptions())


@pytest.mark.parametrize("format_name", ["png", "bmp", "bmp8bit"])
def test_keysight_capture_checks_declared_formats(format_name):
    caps = replace(capabilities_for_model_id("keysight-dsox4024a"), screenshot_formats=())
    with pytest.raises(ParameterValidationError, match="unsupported"):
        validate_screenshot_capability(caps, ScreenshotOptions(format=format_name))
