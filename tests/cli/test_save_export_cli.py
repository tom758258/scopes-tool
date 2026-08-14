import json

import pytest

from scopes_tool_cli import cli, runtime


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize(
    "args, target",
    [
        (["save-pwd", "--query"], ":SAVE:PWD?"),
        (["save-pwd", "--path", r"USB:\captures"], ':SAVE:PWD "USB:\\captures"'),
        (["save-filename", "--name", "scope_01"], ':SAVE:FILename "scope_01"'),
        (["save-image-format", "--format", "bmp8"], ":SAVE:IMAGe:FORMat BMP8bit"),
        (["save-image-palette", "--palette", "grayscale"], ":SAVE:IMAGe:PALette GRAYscale"),
        (["save-image-ink-saver", "--enabled", "false"], ":SAVE:IMAGe:INKSaver 0"),
        (["save-image-factors", "--enabled", "true"], ":SAVE:IMAGe:FACTors 1"),
        (["save-waveform-format", "--format", "binary"], ":SAVE:WAVeform:FORMat BINary"),
        (["save-waveform-length", "--points", "100"], ":SAVE:WAVeform:LENGth 100"),
        (["save-waveform-length-max", "--query"], ":SAVE:WAVeform:LENGth:MAX?"),
    ],
)
def test_save_export_dry_run_preview_never_opens_scope(monkeypatch, capsys, args, target):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main([*args, "--dry-run", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["result"]["instrument_side"] is True
    assert payload["scpi"]["planned"] == ["*IDN?", target, ":SYSTem:ERRor?"]


def test_save_image_dry_run_includes_opc(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main(
        ["save-image", "--filename", "USB:/screen.png", "--dry-run", "--json"]
    ) == 0
    payload = _payload(capsys)
    assert payload["scpi"]["planned"] == [
        "*IDN?",
        ':SAVE:IMAGe "USB:/screen.png"',
        "*OPC?",
        ":SYSTem:ERRor?",
    ]
    assert payload["result"]["instrument_side"] is True


def test_4000x_save_waveform_dry_run_includes_rui_readiness(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main(
        ["save-waveform", "--filename", "USB:/wave.csv", "--dry-run", "--json"]
    ) == 0
    payload = _payload(capsys)
    assert payload["scpi"]["planned"] == [
        "*IDN?",
        ':SAVE:WAVeform "USB:/wave.csv"',
        "*OPC?",
        ":OPERegister:CONDition?",
        ":SYSTem:ERRor?",
    ]
    assert payload["result"]["instrument_side"] is True


def test_save_image_simulate_json_is_instrument_side_and_creates_no_command_file(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert cli.main(
        ["save-image", "--filename", "USB:/screen.png", "--simulate", "--json"]
    ) == 0
    payload = _payload(capsys)
    assert payload["result"]["operation"] == "save-image"
    assert payload["result"]["instrument_side"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ':SAVE:IMAGe "USB:/screen.png"',
        "*OPC?",
        ":SYSTem:ERRor?",
    ]
    assert list(tmp_path.iterdir()) == []


def test_save_format_simulate_query_returns_canonical_value_and_raw(capsys):
    assert cli.main(["save-image-format", "--query", "--simulate", "--json"]) == 0
    result = _payload(capsys)["result"]
    assert result["format"] == "png"
    assert result["raw_response"] == "PNG"
    assert result["instrument_side"] is True


@pytest.mark.parametrize(
    "args",
    [
        ["save-pwd", "--path", "bad;path"],
        ["save-filename", "--name", "folder/name"],
        ["save-image", "--filename", 'bad"name'],
        ["save-waveform", "--filename", "   "],
        ["save-waveform-length", "--points", "99"],
    ],
)
def test_save_export_invalid_values_fail_before_open(monkeypatch, capsys, args):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main([*args, "--simulate", "--json"]) == 1
    assert _payload(capsys)["ok"] is False


@pytest.mark.parametrize(
    "args",
    [
        ["save-pwd"],
        ["save-pwd", "--query", "--path", "USB:/"],
        ["save-image-format", "--format", "BMP"],
        ["save-image-format", "--format", "none"],
        ["save-image-ink-saver", "--enabled", "1"],
        ["save-image"],
        ["save-waveform-length-max"],
        ["save-waveform-format", "--format", "none"],
    ],
)
def test_save_export_parser_rejects_ambiguous_or_noncanonical_forms(capsys, args):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(args)
    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""
