from pathlib import Path

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.planning import (
    AcquisitionCheckPlanRequest,
    CapturePlanRequest,
    MeasurePlanRequest,
    MeasureSweepPlanRequest,
    SmokePlanRequest,
    plan_acquisition_check,
    plan_capture,
    plan_doctor,
    plan_measure,
    plan_measure_sweep,
    plan_smoke,
)


def test_plan_capture_single_and_all_channels(tmp_path):
    caps = capabilities_for_model("DSOX4024A")
    csv_path = tmp_path / "capture.csv"

    single = plan_capture(CapturePlanRequest((1,), 1000, csv_path=csv_path), caps)
    assert single.files == (
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "metadata", "path": str(tmp_path / "capture_meta.json")},
    )
    assert single.planned_scpi[-1] == ":SYSTem:ERRor?"
    assert single.planned_scpi.count(":CHANnel1:UNITs?") == 1

    all_channels = plan_capture(CapturePlanRequest(("all",), 1000, "word"), caps)
    assert all_channels.result["channels"] == [1, 2, 3, 4]
    assert ":WAVeform:FORMat WORD" in all_channels.planned_scpi
    for channel in all_channels.result["channels"]:
        assert all_channels.planned_scpi.count(f":CHANnel{channel}:UNITs?") == 1


def test_plan_doctor_uses_capability_channel_count():
    first = plan_doctor(capabilities_for_model("DSOX2004A"))
    second = plan_doctor(capabilities_for_model("DSOX4034A"))

    assert ":CHANnel4:BWLimit?" in first.planned_scpi
    assert ":CHANnel5:BWLimit?" not in first.planned_scpi
    assert ":CHANnel4:BWLimit?" in second.planned_scpi


def test_plan_measure_single_and_pair():
    caps = capabilities_for_model("DSOX4034A")

    single = plan_measure(MeasurePlanRequest(item="vpp", channel=1), caps)
    pair = plan_measure(
        MeasurePlanRequest(item="phase", source_channel=1, reference_channel=2),
        caps,
    )

    assert single.planned_scpi == (":MEASure:VPP? CHANnel1", ":SYSTem:ERRor?")
    assert pair.result["reference_channel"] == 2
    assert pair.planned_scpi[-1] == ":SYSTem:ERRor?"


def test_plan_measure_sweep_ignores_unsupported_pair_command():
    caps = capabilities_for_model("DSOX2004A")

    plan = plan_measure_sweep(
        MeasureSweepPlanRequest(channels=(1,), items="vpp", pairs=("1:2",), pair_items="delay"),
        caps,
    )

    assert plan.result["channels"] == [1]
    assert all("DELay" not in command for command in plan.planned_scpi)


def test_plan_smoke_and_acquisition_check_files(tmp_path):
    smoke_dir = tmp_path / "smoke"
    acq_dir = tmp_path / "acq"

    smoke = plan_smoke(SmokePlanRequest(smoke_dir), capabilities_for_model("DSOX4024A"))
    acq = plan_acquisition_check(AcquisitionCheckPlanRequest(acq_dir, check_only=True))

    assert smoke.files[0] == {"kind": "report", "path": str(smoke_dir / "report.json")}
    assert not smoke_dir.exists()
    assert acq.planned_scpi == (
        "*IDN?",
        ":ACQuire:TYPE?",
        ":ACQuire:COUNt?",
        ":SYSTem:ERRor?",
    )
    assert acq.files[1] == {"kind": "scpi_log", "path": str(acq_dir / "scpi.log")}
    assert not acq_dir.exists()
