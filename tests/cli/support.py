from scopes_tool_cli import runtime
from scopes_tool_core.waveform import (
    WaveformCapture,
    WaveformPreamble,
)


def byte_waveform_capture(
    channel, points=1000, raw_samples=(128, 129), vertical_values=(-2.56, -2.54)
):
    preamble = WaveformPreamble(
        raw="0,0,2,1,1.0E-6,0,0,2.0E-2,-2.56,128",
        format_code=0,
        type_code=0,
        points=2,
        count=1,
        x_increment=1e-6,
        x_origin=0.0,
        x_reference=0,
        y_increment=0.02,
        y_origin=-2.56,
        y_reference=128,
    )
    return WaveformCapture(
        channel=channel,
        requested_points=points,
        format_name="BYTE",
        preamble=preamble,
        raw_samples=raw_samples,
        time_s=(0.0, 1e-6),
        vertical_values=vertical_values,
        vertical_unit="V",
    )


def word_waveform_capture(channel, points=1000):
    preamble = WaveformPreamble(
        raw="1,0,2,1,1.0E-6,0,0,1.0E-4,0,32768",
        format_code=1,
        type_code=0,
        points=2,
        count=1,
        x_increment=1e-6,
        x_origin=0.0,
        x_reference=0,
        y_increment=0.0001,
        y_origin=0.0,
        y_reference=32768,
    )
    return WaveformCapture(
        channel=channel,
        requested_points=points,
        format_name="WORD",
        preamble=preamble,
        raw_samples=(32768, 32769),
        time_s=(0.0, 1e-6),
        vertical_values=(0.0, 0.1),
        vertical_unit="V",
    )


def install_scope(monkeypatch, scope):
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: scope),
    )
    return scope
