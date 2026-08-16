import pytest

from scopes_tool_core.trigger_holdoff import trigger_holdoff_command

from scopes_tool_core.errors import ParameterValidationError

@pytest.mark.parametrize("seconds", [39e-9, 10.1])
def test_trigger_holdoff_rejects_out_of_range(seconds):
    with pytest.raises(ParameterValidationError):
        trigger_holdoff_command(seconds)
