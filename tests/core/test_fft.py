from dataclasses import replace

import pytest

from scopes_tool_core.fft import (
    fft_configure_commands,
    fft_query_commands,
)

from scopes_tool_core.capabilities import capabilities_for_model

from scopes_tool_core.errors import (
    ChannelResponseError,
    ParameterValidationError,
)

from scopes_tool_core.scope import Oscilloscope

from scopes_tool_core.simulator_backend import SimulatorBackend

@pytest.mark.parametrize(
    ("model", "prefix"),
    [
        ("DSOX2004A", ":FUNCtion"),
        ("DSOX3024A", ":FUNCtion"),
        ("DSOX4024A", ":FUNCtion1"),
    ],
)
def test_fft_commands_use_series_appropriate_function_prefix(model, prefix):
    capabilities = capabilities_for_model(model)

    assert fft_configure_commands(
        1,
        1,
        units="decibel",
        window="hanning",
        center_hz=1000,
        span_hz=10000,
        display=True,
        capabilities=capabilities,
    ) == [
        f"{prefix}:OPERation FFT",
        f"{prefix}:SOURce1 CHANnel1",
        f"{prefix}:FFT:VTYPe DECibel",
        f"{prefix}:FFT:WINDow HANNing",
        f"{prefix}:FFT:CENTer 1000",
        f"{prefix}:FFT:SPAN 10000",
        f"{prefix}:DISPlay ON",
    ]
    assert fft_query_commands(1, capabilities=capabilities) == [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
        f"{prefix}:FFT:VTYPe?",
        f"{prefix}:FFT:WINDow?",
        f"{prefix}:FFT:CENTer?",
        f"{prefix}:FFT:SPAN?",
        f"{prefix}:DISPlay?",
    ]

def test_fft_function_validation_uses_profile_function_count():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4024A")
    unsupported = replace(four_functions, math_function_count=0)

    with pytest.raises(
        ParameterValidationError,
        match="Math functions are not supported by this capability profile",
    ):
        fft_configure_commands(1, 1, capabilities=unsupported)

    with pytest.raises(ParameterValidationError, match="between 1 and 1"):
        fft_configure_commands(2, 1, capabilities=single_function)

    assert fft_configure_commands(4, 1, capabilities=four_functions)[:2] == [
        ":FUNCtion4:OPERation FFT",
        ":FUNCtion4:SOURce1 CHANnel1",
    ]

def test_fft_phase_and_advanced_4000x_commands():
    capabilities = capabilities_for_model("DSOX4024A")

    assert fft_configure_commands(
        2,
        3,
        fft_operation="fft-phase",
        phase_reference="display",
        capabilities=capabilities,
    ) == [
        ":FUNCtion2:OPERation FFTPhase",
        ":FUNCtion2:SOURce1 CHANnel3",
        ":FUNCtion2:PHASe:REFerence DISPlay",
    ]
    assert fft_configure_commands(
        1,
        1,
        start_hz=100,
        stop_hz=1000,
        gate="zoom",
        detection_type="positive-peak",
        detection_points=2048,
        capabilities=capabilities,
    ) == [
        ":FUNCtion1:OPERation FFT",
        ":FUNCtion1:SOURce1 CHANnel1",
        ":FUNCtion1:FREQuency:STARt 100",
        ":FUNCtion1:FREQuency:STOP 1000",
        ":FUNCtion1:GATE ZOOM",
        ":FUNCtion1:DETection:TYPE PPOSitive",
        ":FUNCtion1:DETection:POINts 2048",
    ]

def test_fft_phase_rejects_magnitude_units():
    with pytest.raises(
        ParameterValidationError,
        match="units.*fft-phase",
    ):
        fft_configure_commands(
            1,
            1,
            fft_operation="fft-phase",
            units="decibel",
            capabilities=capabilities_for_model("DSOX4024A"),
        )

def test_fft_advanced_validation_uses_profile_and_range_mode():
    basic = capabilities_for_model("DSOX3024A")
    advanced = capabilities_for_model("DSOX4024A")

    with pytest.raises(ParameterValidationError, match="4000X"):
        fft_configure_commands(
            1,
            1,
            gate="zoom",
            capabilities=basic,
        )
    with pytest.raises(ParameterValidationError, match="cannot be combined"):
        fft_configure_commands(
            1,
            1,
            center_hz=1000,
            start_hz=100,
            capabilities=advanced,
        )

def test_fft_4000x_aggregate_query_parses_advanced_state():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    scope.configure_fft(
        2,
        1,
        fft_operation="fft-phase",
        start_hz=100,
        stop_hz=1000,
        gate="zoom",
        phase_reference="trigger",
        detection_type="average",
        detection_points=4096,
    )
    backend.fft_functions[2]["operation"] = "fFtP"
    backend.fft_functions[2]["gate"] = "zOoM"
    backend.fft_functions[2]["phase_reference"] = "dIsP"
    backend.fft_functions[2]["detection_type"] = "pNeG"

    state = scope.query_fft(2)

    assert state.operation == "fFtP"
    assert state.operation_canonical == "fft-phase"
    assert state.start_hz == pytest.approx(100)
    assert state.stop_hz == pytest.approx(1000)
    assert state.gate == "zoom"
    assert state.phase_reference == "display"
    assert state.detection_type == "negative-peak"
    assert state.detection_points == 4096
    assert state.bin_size_hz == pytest.approx(1000)
    assert state.sample_rate_hz == pytest.approx(1e9)
    assert state.resolution_bandwidth_hz == pytest.approx(1500)
    assert backend.history[-1] == ":FUNCtion2:PHASe:REFerence?"

def test_fft_fractional_detection_points_readback_is_rejected():
    class FractionalDetectionPointsBackend(SimulatorBackend):
        def query(self, command):
            if command == ":FUNCtion1:DETection:POINts?":
                self.history.append(command)
                return "640.5"
            return super().query(command)

    backend = FractionalDetectionPointsBackend(
        physical_model_id="keysight-dsox4024a"
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    with pytest.raises(ChannelResponseError, match="detection points"):
        scope.query_fft(1)
