from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.channel import channel_summary_queries
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope


def test_query_channel_summary_returns_active_channels_and_parsed_fields():
    capabilities = capabilities_for_model("DSOX4034A")
    responses = {
        "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY1,07.20",
    }
    for channel in range(1, capabilities.analog_channels + 1):
        responses.update(
            {
                f":CHANnel{channel}:DISPlay?": "1",
                f":CHANnel{channel}:LABel?": f'"CH{channel}"',
                f":CHANnel{channel}:SCALe?": "5.0E-1",
                f":CHANnel{channel}:RANGe?": "4.0",
                f":CHANnel{channel}:OFFSet?": "0.0",
                f":CHANnel{channel}:COUPling?": "DC",
                f":CHANnel{channel}:IMPedance?": "ONEMeg",
                f":CHANnel{channel}:INVert?": "0",
                f":CHANnel{channel}:BWLimit?": "0",
                f":CHANnel{channel}:UNITs?": "VOLT",
                f":CHANnel{channel}:VERNier?": "0",
                f":CHANnel{channel}:PROBe?": "10.0",
                f":CHANnel{channel}:PROBe:SKEW?": "0.0",
            }
        )
    responses[":CHANnel1:BWLimit?"] = "unsupported"
    backend = FakeBackend(responses=responses)
    scope = Oscilloscope(backend)

    scope.query_idn()
    summary = scope.query_channel_summary()

    assert len(summary) == capabilities.analog_channels
    assert summary[0].to_json() == {
        "channel": 1,
        "display": True,
        "label": "CH1",
        "scale": 0.5,
        "range": 4.0,
        "offset": 0.0,
        "coupling": "dc",
        "impedance": "one_meg",
        "invert": False,
        "bandwidth_limit": None,
        "units": "volt",
        "vernier": False,
        "probe_ratio": 10.0,
        "probe_skew": 0.0,
    }
    assert backend.history == ["*IDN?", *channel_summary_queries(capabilities)]
