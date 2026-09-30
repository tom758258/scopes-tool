"""Generic plans dispatch through registered drivers, including new series."""

from dataclasses import replace

import pytest

from scopes_tool_core import drivers, identity
from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.errors import UnsupportedModelError
from scopes_tool_core.planning import CapturePlanRequest, MeasurePlanRequest, plan_capture, plan_measure
from scopes_tool_core.scope import Oscilloscope


@pytest.mark.parametrize("workflow", [False, True])
def test_new_series_uses_registered_driver_for_capture_and_measure(monkeypatch, workflow):
    class NewSeriesDriver(Oscilloscope):
        @classmethod
        def plan_capture_scpi(cls, channels, points, waveform_format, capabilities):
            assert channels == (1,) and points == 1000 and waveform_format == "byte"
            return ["MODEL:CAPTURE?"]

        @classmethod
        def plan_measure_scpi(cls, item, channel, reference_channel, capabilities, **parameters):
            assert item == "vpp" and channel == 1 and reference_channel is None
            return ["MODEL:MEASURE?"]

        @classmethod
        def plan_workflow_step(cls, action, capabilities, **parameters):
            return [f"MODEL:{action}?"]

    original = identity.physical_model_for_id("tektronix-tbs2074")
    added = replace(original, model_id="tektronix-test-model", series="TEST-SERIES", driver_id="test-driver")
    monkeypatch.setitem(identity._PHYSICAL_MODEL_BY_ID, added.model_id, added)
    monkeypatch.setitem(drivers.DRIVER_REGISTRY, added.driver_id, NewSeriesDriver)
    caps = replace(capabilities_for_model_id(original.model_id), physical_model_id=added.model_id, series=added.series)
    status = "MODEL:status?" if workflow else "MODEL:command-status?"
    assert plan_capture(CapturePlanRequest((1,), 1000), caps, workflow=workflow).planned_scpi == ("MODEL:CAPTURE?", status)
    assert plan_measure(MeasurePlanRequest("vpp", 1), caps, workflow=workflow).planned_scpi == ("MODEL:MEASURE?", status)


@pytest.mark.parametrize("planner,plan_request", [
    (plan_capture, CapturePlanRequest((1,), 1000)),
    (plan_measure, MeasurePlanRequest("vpp", 1)),
])
def test_unregistered_planning_identity_cannot_fall_back(planner, plan_request):
    caps = replace(capabilities_for_model_id("tektronix-tbs2074"), series="TEST-SERIES", physical_model_id="unregistered")
    with pytest.raises(UnsupportedModelError):
        planner(plan_request, caps)


@pytest.mark.parametrize("model_id", [model.model_id for model in identity.PHYSICAL_MODEL_REGISTRY if model.vendor_id == "tektronix"])
def test_setup_recall_plan_does_not_require_simulated_saved_slot(model_id):
    from scopes_tool_core.errors import OscilloscopeError
    from scopes_tool_core.tektronix import TektronixOscilloscope, _PlanningBackend
    from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend

    backend = _PlanningBackend(capabilities_for_model_id(model_id))
    scope = TektronixOscilloscope(backend)
    scope.recall_setup(slot=1)
    assert backend.commands == ["RECAll:SETUp 1"]
    with pytest.raises(OscilloscopeError, match="not been saved"):
        TektronixOscilloscope(TektronixSimulatorBackend(physical_model_id=model_id)).recall_setup(slot=1)
