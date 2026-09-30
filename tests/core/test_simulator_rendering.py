"""Tests pinning the deterministic simulated image rendering contract."""

import hashlib

from scopes_tool_core import simulator_rendering
from scopes_tool_core.simulator_backend import (
    _simulated_screenshot_bmp,
    _simulated_screenshot_png,
)
from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend


PNG_DIGESTS = {
    ("keysight-dsox4024a", False): (
        4668,
        "aa64e34284f0bfcfc27da67e5b3199b9695a288ae295e507d0bb94fd567b7be2",
    ),
    ("keysight-dsox4024a", True): (
        4770,
        "05166ef8ddea19a10f8f3b4abb3d9a9852d3febd09ae53c5dc4f08dfd7db8efe",
    ),
    ("tektronix-tds2024b", False): (
        4663,
        "c5847610e4b2877be8cabec71a86ececf110833caa0a8bb513ec94f811cd4042",
    ),
    ("tektronix-tds2024b", True): (
        4765,
        "0e40c0592987e0140d9ed562cf6afa43ccc4ae4df47aa0c8b89da540f912806b",
    ),
}

BMP_DIGESTS = {
    False: (58, "767ce7af8bd62d55234d07215e1f263f5dd0a93701fa1294a5642193ace309f4"),
    True: (1082, "191fb600c12645fd87e56d309f983f9b3fd4e8ce5c7b9d1f4a572ed0b6df6b54"),
}


def test_simulated_screenshot_png_bytes_are_stable():
    for (model, white_background), (length, digest) in PNG_DIGESTS.items():
        data = _simulated_screenshot_png(model, white_background=white_background)
        assert len(data) == length
        assert hashlib.sha256(data).hexdigest() == digest


def test_simulated_screenshot_bmp_bytes_are_stable():
    for eight_bit, (length, digest) in BMP_DIGESTS.items():
        data = _simulated_screenshot_bmp(eight_bit)
        assert len(data) == length
        assert hashlib.sha256(data).hexdigest() == digest


def test_simulator_backend_reexports_shared_rendering_helpers():
    assert _simulated_screenshot_png is simulator_rendering._simulated_screenshot_png
    assert _simulated_screenshot_bmp is simulator_rendering._simulated_screenshot_bmp


def test_tektronix_simulator_reuses_the_shared_rendering_helpers():
    backend = TektronixSimulatorBackend(physical_model_id="tektronix-tbs2074")
    backend.write('SAVE:IMAGE "shot.png"')
    backend.write('FILESystem:READFile "shot.png"')
    assert backend.read_raw() == _simulated_screenshot_png(
        "TBS2074", white_background=False
    )

    backend = TektronixSimulatorBackend(physical_model_id="tektronix-tds2024b")
    backend.write("HARDCopy:FORMat BMP")
    backend.write("HARDCopy:PORT FILE")
    backend.write("HARDCopy START")
    assert backend.read_raw() == _simulated_screenshot_bmp(False)
