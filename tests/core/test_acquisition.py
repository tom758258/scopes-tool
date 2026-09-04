"""Tests for acquisition configuration."""

import math
import pytest

from scopes_tool_core.acquisition import (
    AcquisitionConfig,
    AcquisitionController,
    normalize_acquisition_type,
    parse_acquisition_type,
    validate_acquisition_count,
    parse_acquisition_count,
    acquisition_type_command,
    acquisition_type_query,
    acquisition_count_command,
    acquisition_count_query,
)
from scopes_tool_core.errors import ParameterValidationError, AcquisitionResponseError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope


class TestAcquisitionTypeNormalization:
    def test_normal_variants(self):
        assert normalize_acquisition_type("normal") == "NORMal"
        assert normalize_acquisition_type("norm") == "NORMal"
        assert normalize_acquisition_type("NORMAL") == "NORMal"
        assert normalize_acquisition_type("  Normal  ") == "NORMal"

    def test_average_variants(self):
        assert normalize_acquisition_type("average") == "AVERage"
        assert normalize_acquisition_type("aver") == "AVERage"
        assert normalize_acquisition_type("avg") == "AVERage"
        assert normalize_acquisition_type("AVERAGE") == "AVERage"

    def test_high_resolution_variants(self):
        assert normalize_acquisition_type("high_resolution") == "HRESolution"
        assert normalize_acquisition_type("high-resolution") == "HRESolution"
        assert normalize_acquisition_type("hresolution") == "HRESolution"
        assert normalize_acquisition_type("hres") == "HRESolution"

    def test_peak_variants(self):
        assert normalize_acquisition_type("peak") == "PEAK"
        assert normalize_acquisition_type("peak_detect") == "PEAK"
        assert normalize_acquisition_type("peak-detect") == "PEAK"

    def test_invalid_type_raises(self):
        with pytest.raises(ParameterValidationError, match="acquisition type must be one of"):
            normalize_acquisition_type("invalid")
        with pytest.raises(ParameterValidationError, match="acquisition type must be one of"):
            normalize_acquisition_type("")


class TestAcquisitionTypeParsing:
    def test_short_readbacks(self):
        assert parse_acquisition_type("NORM") == "normal"
        assert parse_acquisition_type("AVER") == "average"
        assert parse_acquisition_type("HRES") == "high_resolution"
        assert parse_acquisition_type("PEAK") == "peak"

    def test_long_readbacks(self):
        assert parse_acquisition_type("NORMAL") == "normal"
        assert parse_acquisition_type("AVERAGE") == "average"
        assert parse_acquisition_type("HRESOLUTION") == "high_resolution"

    def test_case_insensitive(self):
        assert parse_acquisition_type("norm") == "normal"
        assert parse_acquisition_type("Norm") == "normal"
        assert parse_acquisition_type("aver") == "average"
        assert parse_acquisition_type("Aver") == "average"

    def test_invalid_readback_raises(self):
        with pytest.raises(AcquisitionResponseError, match="Could not parse acquisition type"):
            parse_acquisition_type("INVALID")
        with pytest.raises(AcquisitionResponseError, match="Could not parse acquisition type"):
            parse_acquisition_type("")


class TestAcquisitionCountValidation:
    def test_valid_counts(self):
        assert validate_acquisition_count(2) == 2
        assert validate_acquisition_count(16) == 16
        assert validate_acquisition_count(65536) == 65536

    def test_count_below_minimum_raises(self):
        with pytest.raises(ParameterValidationError, match="between 2 and 65536"):
            validate_acquisition_count(1)
        with pytest.raises(ParameterValidationError, match="between 2 and 65536"):
            validate_acquisition_count(0)
        with pytest.raises(ParameterValidationError, match="between 2 and 65536"):
            validate_acquisition_count(-1)

    def test_count_above_maximum_raises(self):
        with pytest.raises(ParameterValidationError, match="between 2 and 65536"):
            validate_acquisition_count(65537)
        with pytest.raises(ParameterValidationError, match="between 2 and 65536"):
            validate_acquisition_count(100000)

    def test_non_integer_raises(self):
        with pytest.raises(ParameterValidationError, match="must be an integer"):
            validate_acquisition_count(1.5)
        with pytest.raises(ParameterValidationError, match="must be an integer"):
            validate_acquisition_count("16")
        with pytest.raises(ParameterValidationError, match="must be an integer"):
            validate_acquisition_count("abc")
        with pytest.raises(ParameterValidationError, match="must be an integer"):
            validate_acquisition_count(None)

    def test_non_finite_raises(self):
        with pytest.raises(ParameterValidationError, match="must be a finite number"):
            validate_acquisition_count(float("inf"))
        with pytest.raises(ParameterValidationError, match="must be a finite number"):
            validate_acquisition_count(float("-inf"))
        with pytest.raises(ParameterValidationError, match="must be a finite number"):
            validate_acquisition_count(float("nan"))


class TestAcquisitionCountParsing:
    def test_valid_count_readbacks(self):
        assert parse_acquisition_count("16") == 16
        assert parse_acquisition_count("  16  ") == 16
        assert parse_acquisition_count("65536") == 65536

    def test_invalid_count_readback_raises(self):
        with pytest.raises(AcquisitionResponseError, match="Could not parse acquisition count"):
            parse_acquisition_count("abc")
        with pytest.raises(AcquisitionResponseError, match="Could not parse acquisition count"):
            parse_acquisition_count("")
        with pytest.raises(AcquisitionResponseError, match="Could not parse acquisition count"):
            parse_acquisition_count("1.5")


class TestAcquisitionCommandBuilders:
    def test_type_command(self):
        assert acquisition_type_command("NORMal") == ":ACQuire:TYPE NORMal"
        assert acquisition_type_command("AVERage") == ":ACQuire:TYPE AVERage"
        assert acquisition_type_command("HRESolution") == ":ACQuire:TYPE HRESolution"
        assert acquisition_type_command("PEAK") == ":ACQuire:TYPE PEAK"

    def test_type_query(self):
        assert acquisition_type_query() == ":ACQuire:TYPE?"

    def test_count_command(self):
        assert acquisition_count_command(2) == ":ACQuire:COUNt 2"
        assert acquisition_count_command(16) == ":ACQuire:COUNt 16"
        assert acquisition_count_command(65536) == ":ACQuire:COUNt 65536"

    def test_count_query(self):
        assert acquisition_count_query() == ":ACQuire:COUNt?"


class TestAcquisitionConfigDataclass:
    def test_creation_and_repr(self):
        config = AcquisitionConfig(type="normal", count=16)
        assert config.type == "normal"
        assert config.count == 16
        assert repr(config) == "AcquisitionConfig(type='normal', count=16)"

    def test_equality(self):
        config1 = AcquisitionConfig(type="normal", count=16)
        config2 = AcquisitionConfig(type="normal", count=16)
        config3 = AcquisitionConfig(type="average", count=16)
        config4 = AcquisitionConfig(type="normal", count=32)

        assert config1 == config2
        assert config1 != config3
        assert config1 != config4
        assert config1 != "not a config"


class TestAcquisitionControllerWithFakeBackend:
    def test_set_type_writes_correct_scpi(self):
        backend = FakeBackend()
        from scopes_tool_core.scpi import SCPIClient
        scpi = SCPIClient(backend)
        controller = AcquisitionController(scpi)

        controller.set_type("average")

        assert backend.history == [":ACQuire:TYPE AVERage"]

    def test_query_type_reads_and_parses_response(self):
        backend = FakeBackend(responses={":ACQuire:TYPE?": "AVER"})
        from scopes_tool_core.scpi import SCPIClient
        scpi = SCPIClient(backend)
        controller = AcquisitionController(scpi)

        result = controller.query_type()

        assert result == "average"
        assert backend.history == [":ACQuire:TYPE?"]

    def test_set_count_writes_correct_scpi(self):
        backend = FakeBackend()
        from scopes_tool_core.scpi import SCPIClient
        scpi = SCPIClient(backend)
        controller = AcquisitionController(scpi)

        controller.set_count(32)

        assert backend.history == [":ACQuire:COUNt 32"]

    def test_query_count_reads_and_parses_response(self):
        backend = FakeBackend(responses={":ACQuire:COUNt?": "32"})
        from scopes_tool_core.scpi import SCPIClient
        scpi = SCPIClient(backend)
        controller = AcquisitionController(scpi)

        result = controller.query_count()

        assert result == 32
        assert backend.history == [":ACQuire:COUNt?"]

    def test_query_config_queries_type_then_count(self):
        backend = FakeBackend(
            responses={
                ":ACQuire:TYPE?": "HRES",
                ":ACQuire:COUNt?": "64",
            }
        )
        from scopes_tool_core.scpi import SCPIClient
        scpi = SCPIClient(backend)
        controller = AcquisitionController(scpi)

        config = controller.query_config()

        assert config.type == "high_resolution"
        assert config.count == 64
        assert backend.history == [":ACQuire:TYPE?", ":ACQuire:COUNt?"]


class TestScopeAcquisitionMethods:
    def test_acquisition_operations_require_idn_first(self):
        scope = Oscilloscope(FakeBackend())

        with pytest.raises(ParameterValidationError, match="query_idn"):
            scope.set_acquisition_type("normal")
        with pytest.raises(ParameterValidationError, match="query_idn"):
            scope.query_acquisition_type()
        with pytest.raises(ParameterValidationError, match="query_idn"):
            scope.set_acquisition_count(16)
        with pytest.raises(ParameterValidationError, match="query_idn"):
            scope.query_acquisition_count()
        with pytest.raises(ParameterValidationError, match="query_idn"):
            scope.query_acquisition_config()

    def test_set_acquisition_type_writes_only_type_command(self):
        backend = FakeBackend(
            responses={"*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20"}
        )
        scope = Oscilloscope(backend)

        scope.query_idn()
        scope.set_acquisition_type("average")

        assert backend.history == ["*IDN?", ":ACQuire:TYPE AVERage"]

    def test_set_acquisition_count_writes_only_count_command(self):
        backend = FakeBackend(
            responses={"*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20"}
        )
        scope = Oscilloscope(backend)

        scope.query_idn()
        scope.set_acquisition_count(32)

        assert backend.history == ["*IDN?", ":ACQuire:COUNt 32"]

    def test_query_acquisition_type_reads_and_parses(self):
        backend = FakeBackend(
            responses={
                "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
                ":ACQuire:TYPE?": "PEAK",
            }
        )
        scope = Oscilloscope(backend)

        scope.query_idn()
        result = scope.query_acquisition_type()

        assert result == "peak"
        assert backend.history == ["*IDN?", ":ACQuire:TYPE?"]

    def test_query_acquisition_count_reads_and_parses(self):
        backend = FakeBackend(
            responses={
                "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
                ":ACQuire:COUNt?": "128",
            }
        )
        scope = Oscilloscope(backend)

        scope.query_idn()
        result = scope.query_acquisition_count()

        assert result == 128
        assert backend.history == ["*IDN?", ":ACQuire:COUNt?"]

    def test_query_acquisition_config_queries_type_then_count(self):
        backend = FakeBackend(
            responses={
                "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
                ":ACQuire:TYPE?": "NORM",
                ":ACQuire:COUNt?": "16",
            }
        )
        scope = Oscilloscope(backend)

        scope.query_idn()
        config = scope.query_acquisition_config()

        assert config.type == "normal"
        assert config.count == 16
        assert backend.history == ["*IDN?", ":ACQuire:TYPE?", ":ACQuire:COUNt?"]


from scopes_tool_core.operations import query_acquisition_readouts


def test_query_acquisition_readouts_2000X_no_record_length() -> None:
    """2000X profile: record_length unsupported (None); sample_rate and points queried."""
    # 2000X model: DSOX2004A
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX2004A,MY1,07.20",
            ":ACQuire:SRATe?": "5.0E+09",
            ":ACQuire:POINts?": "4000000",
        },
    )
    scope = Oscilloscope(backend)
    scope.query_idn()
    readouts = query_acquisition_readouts(scope)
    assert readouts["sample_rate"] == 5.0e9
    assert readouts["acquisition_points"] == 4000000
    assert readouts["record_length"] is None
    assert ":ACQuire:RLENgth?" not in backend.history


def test_query_acquisition_readouts_4000X_record_length_supported() -> None:
    """4000X profile: record_length queried and parsed."""
    # 4000X model: DSOX4024A
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":ACQuire:SRATe?": "2.5E+09",
            ":ACQuire:POINts?": "2000000",
            ":ACQuire:RLENgth?": "2000000",
        },
    )
    scope = Oscilloscope(backend)
    scope.query_idn()
    readouts = query_acquisition_readouts(scope)
    assert readouts["record_length"] == 2000000
    assert ":ACQuire:RLENgth?" in backend.history


def test_query_acquisition_readouts_parser_failure_propagates() -> None:
    """Malformed acquisition response propagates as AcquisitionResponseError, not masked as None."""
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":ACQuire:SRATe?": "BAD",
        },
    )
    scope = Oscilloscope(backend)
    scope.query_idn()
    with pytest.raises(AcquisitionResponseError):
        query_acquisition_readouts(scope)
