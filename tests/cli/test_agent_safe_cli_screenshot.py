import pytest

from scopes_tool_cli import cli, runtime
from tests.cli._agent_safe_cli_support import _json_stdout


def test_screenshot_simulate_json_reports_png_metadata(capsys, tmp_path):
    black_path = tmp_path / "screen-black.png"
    white_path = tmp_path / "screen-white.png"

    assert cli.main(["screenshot", "--simulate", "--json", "--output", str(black_path)]) == 0

    black_payload = _json_stdout(capsys)
    black_result = black_payload["result"]
    assert black_payload["files"] == [{"kind": "png", "path": str(black_path)}]
    assert black_result["format"] == "PNG"
    assert black_result["background"] == "black"
    assert black_result["byte_count"] > 1000
    assert black_result["png_path"] == str(black_path)
    assert black_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    assert (
        cli.main(
            [
                "screenshot",
                "--simulate",
                "--json",
                "--background",
                "white",
                "--output",
                str(white_path),
            ]
        )
        == 0
    )

    white_payload = _json_stdout(capsys)
    white_result = white_payload["result"]
    assert white_payload["files"] == [{"kind": "png", "path": str(white_path)}]
    assert white_result["background"] == "white"
    assert white_result["byte_count"] > 1000
    assert white_result["png_path"] == str(white_path)
    assert white_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert black_path.read_bytes() != white_path.read_bytes()


@pytest.mark.parametrize(
    ("format_name", "extension", "query", "signature"),
    [
        ("png", ".png", ":HCOPY:SDUMp:DATA? PNG", b"\x89PNG\r\n\x1a\n"),
        ("bmp", ".bmp", ":HCOPY:SDUMp:DATA? BMP", b"BM"),
        ("bmp8bit", ".bmp", ":HCOPY:SDUMp:DATA? BMP8bit", b"BM"),
    ],
)
def test_screenshot_hardcopy_controls_simulate_uses_explicit_screen_dump_query(
    capsys, tmp_path, format_name, extension, query, signature
):
    output_path = tmp_path / f"screen{extension}"

    assert (
        cli.main(
            [
                "screenshot",
                "--simulate",
                "--json",
                "--format",
                format_name,
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert query in payload["scpi"]["sent"]
    assert output_path.read_bytes().startswith(signature)


def test_screenshot_hardcopy_appearance_controls_and_query_state(capsys, tmp_path):
    output_path = tmp_path / "appearance.png"
    assert (
        cli.main(
            [
                "screenshot",
                "--simulate",
                "--json",
                "--format",
                "png",
                "--ink-saver",
                "true",
                "--palette",
                "grayscale",
                "--layout",
                "landscape",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["sent"][1:5] == [
        ":HARDcopy:INKSaver ON",
        ":HARDcopy:PALette GRAYscale",
        ":HARDcopy:LAYout LANDscape",
        ":HCOPY:SDUMp:DATA? PNG",
    ]

    assert cli.main(["screenshot", "--simulate", "--json", "--query-hardcopy"]) == 0
    query_payload = _json_stdout(capsys)
    assert query_payload["files"] == []
    assert query_payload["result"]["hardcopy"] == {
        "area": "screen",
        "ink_saver": False,
        "palette": "none",
        "layout": "portrait",
        "format": "png",
        "raw_area": "SCR",
        "raw_ink_saver": "0",
        "raw_palette": "NONE",
        "raw_layout": "PORT",
        "raw_format": "PNG",
    }


def test_screenshot_hardcopy_controls_dry_run_plans_without_backend(capsys, tmp_path):
    output_path = tmp_path / "screen.bmp"
    assert (
        cli.main(
            [
                "screenshot",
                "--dry-run",
                "--json",
                "--format",
                "bmp8bit",
                "--palette",
                "color",
                "--layout",
                "portrait",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["sent"] == []
    assert payload["scpi"]["planned"] == [
        ":HARDcopy:INKSaver?",
        ":HARDcopy:INKSaver OFF",
        ":HARDcopy:PALette COLor",
        ":HARDcopy:LAYout PORTrait",
        ":HCOPY:SDUMp:DATA? BMP8bit",
        ":SYSTem:ERRor?",
    ]
    assert not any(
        "restore queried state" in command
        for command in payload["scpi"]["planned"]
    )
    assert payload["result"]["ink_saver_plan"] == {
        "mode": "temporary_background",
        "target": False,
        "restore": "queried_state_if_changed",
    }
    assert not output_path.exists()


def test_screenshot_hardcopy_controls_dry_run_explicit_ink_saver_has_no_restore(capsys):
    assert (
        cli.main(
            [
                "screenshot",
                "--dry-run",
                "--json",
                "--format",
                "bmp",
                "--ink-saver",
                "false",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [
        ":HARDcopy:INKSaver OFF",
        ":HCOPY:SDUMp:DATA? BMP",
        ":SYSTem:ERRor?",
    ]
    assert ":HARDcopy:INKSaver?" not in payload["scpi"]["planned"]
    assert not any(
        "restore queried state" in command
        for command in payload["scpi"]["planned"]
    )
    assert payload["result"]["ink_saver_plan"] == {
        "mode": "explicit",
        "target": False,
        "restore": None,
    }


def test_screenshot_hardcopy_controls_reject_invalid_values_before_backend(monkeypatch):
    opened = False

    def fail_open(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("backend must not open")

    monkeypatch.setattr(runtime, "_open_scope", fail_open)
    with pytest.raises(SystemExit):
        cli.main(["screenshot", "--simulate", "--format", "jpeg"])
    assert opened is False


def test_screenshot_query_hardcopy_rejects_capture_options_before_backend(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        runtime, "_open_scope", lambda *args, **kwargs: pytest.fail("backend must not open")
    )
    assert (
        cli.main(
            ["screenshot", "--simulate", "--query-hardcopy", "--format", "png"]
        )
        == 1
    )
    assert "cannot be combined" in capsys.readouterr().err
