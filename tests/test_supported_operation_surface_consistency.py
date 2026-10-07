"""Keep explicit operation profiles connected to their applicable adapters.

Cases also run on legacy profiles where WebUI exposes the same operation.
Existing domain matrices cover their remaining CLI-only commands and options.
"""

import argparse
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from scopes_tool_cli import cli
from scopes_tool_cli.parser import _build_parser
from scopes_tool_cli.worker_commands import (
    DOMAIN_COMMANDS, WORKER_SCHEMA_VERSION, arguments_to_argv,
    parse_domain_command, validate_command_request,
)
from scopes_tool_core.capabilities import capabilities_for_model_id, operation_supported
from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY
from scopes_tool_webui.command_catalog import command_catalog
from scopes_tool_webui.command_execution import execute_command
from scopes_tool_webui.command_validation import _validate_parameters


# Each case contains valid CLI/Worker arguments and WebUI parameters.
CASES = {name: ({"query": True}, {"action": "query"}) for name in (
    "acquisition", "display-persistence", "display-vectors", "timebase-position",
    "timebase-scale", "trigger-edge", "trigger-edge-coupling", "trigger-edge-slope",
    "trigger-edge-source", "trigger-holdoff", "trigger-mode", "trigger-pulse-width",
    "trigger-runt", "trigger-sweep", "trigger-tv", "save-image-format",
    "save-image-ink-saver", "save-pwd", "save-waveform-format",
)}
CASES.update({name: ({"query": True, "channel": 1}, {"action": "query", "channel": 1}) for name in (
    "channel-bandwidth-limit", "channel-coupling", "channel-display", "channel-invert",
    "channel-label", "channel-offset", "channel-probe", "channel-probe-skew",
    "channel-scale", "channel-units",
)})
CASES.update({name: ({}, {}) for name in (
    "acquisition-check", "acquisition-points", "autoscale", "channel-summary", "cleanup",
    "doctor", "force-trigger", "identify", "live-data-snapshot", "math-display",
    "measure-clear", "record-length", "run", "sample-rate", "screenshot", "sequence",
    "single", "single-wait", "smoke", "stop-acquisition", "system-clear-status",
    "system-information-snapshot", "system-opc", "system-standard-event", "system-status-byte",
)})
CASES.update({
    "system-opc": ({"query": True}, {}),
    "system-standard-event": ({"query": True}, {}),
    "system-status-byte": ({"query": True}, {}),
    "acquisition-points": ({"query": True}, {}),
    "record-length": ({"query": True}, {}),
    "sample-rate": ({"query": True}, {}),
    "capture": ({"channel": [1], "points": 1000}, {"channels": [1], "points": 1000}),
    "capture-batch": ({"channel": [1], "count": 1}, {"channels": [1], "count": 1}),
    "capture-monitor": ({"channel": [1], "count": 1}, {"channels": [1], "count": 1}),
    "capture-until": (
        {"channel": [1], "condition_channel": 1, "metric": "max", "operator": "gt", "threshold": 0, "timeout_seconds": 1},
        {"channels": [1], "condition_channel": 1, "metric": "max", "operator": "gt", "threshold": 0, "timeout_seconds": 1}),
    "cursor": ({"query": True}, {}),
    "cursor-query": ({"query": True}, {}),
    "cursor-off": ({"off": True}, {}),
    "cursor-set": ({"source_channel": 1, "x1": 0, "x2": 0.001}, {"source_channel": 1, "x1": 0, "x2": 0.001}),
    "math-display": ({"function": 1, "query": True}, {"function": 1, "action": "query"}),
    "math-operator": (
        {"function": 1, "operation": "add", "source1": "channel1", "source2": "channel2"},
        {"function": 1, "action": "set", "operation": "add", "source1": "channel1", "source2": "channel2"}),
    "measure": ({"channel": 1, "item": "vpp"}, {"channel": 1, "item": "vpp"}),
    "measure-install": ({"source_channel": 1, "item": "vpp"}, {"source_channel": 1, "item": "vpp"}),
    "measure-sweep": ({"channel": [1], "items": "vpp", "pair_items": "phase"}, {"channels": [1], "items": ["vpp"], "pair_items": "phase"}),
    "measure-log": ({"channel": [1], "items": "vpp", "count": 1}, {"channels": [1], "items": ["vpp"], "count": 1}),
    "measure-until": (
        {"channel": 1, "item": "vpp", "operator": "gt", "threshold": 0, "timeout_seconds": 1},
        {"channel": 1, "item": "vpp", "operator": "gt", "threshold": 0, "timeout_seconds": 1}),
    "reference-display": ({"slot": 1, "query": True}, {"slot": 1, "action": "query"}),
    "reference-query": ({"slot": 1}, {"slot": 1}),
    "reference-save": ({"slot": 1, "source_channel": 1}, {"slot": 1, "source_channel": 1}),
    "save-image": ({"filename": "screen.png"}, {"filename": "screen.png"}),
    "save-waveform": ({"filename": "wave.csv"}, {"filename": "wave.csv"}),
    "setup-save": ({"slot": 1}, {"target": "slot", "slot": 1}),
    "setup-recall": ({"slot": 1}, {"target": "slot", "slot": 1}),
    "trigger-edge-level": ({"source_channel": 1, "query": True}, {"source_channel": 1, "action": "query"}),
    "triggered-capture-series": (
        {"channel": [1], "count": 1, "trigger_timeout_seconds": 1},
        {"channels": [1], "count": 1, "trigger_timeout_seconds": 1}),
    "triggered-measure-loop": (
        {"channel": [1], "items": "vpp", "count": 1, "trigger_timeout_seconds": 1},
        {"channels": [1], "items": ["vpp"], "count": 1, "trigger_timeout_seconds": 1}),
})

# These differences describe public adapter surfaces, never model policies.
CLI_ALIASES = {name: "cursor" for name in ("cursor-query", "cursor-off", "cursor-set")}
WEB_ALIASES = {"cursor": "cursor-query"}
WEB_ONLY = {"live-data-snapshot", "system-information-snapshot"}
CLI_ONLY = {"acquisition-check", "acquisition-points", "record-length", "sample-rate", "cleanup"}
NO_WORKER = WEB_ONLY | {"measure-install", "sequence", "trigger-mode"}
# Resource discovery is model-independent and has dedicated no-hardware tests.
DISCOVERY = {"list-resources"}
CATALOG = {entry["id"]: entry for entry in command_catalog(include_hidden=True)}
PARSERS = next(a.choices for a in _build_parser()._actions if isinstance(a, argparse._SubParsersAction))


@pytest.mark.parametrize("model", PHYSICAL_MODEL_REGISTRY, ids=lambda model: model.model_id)
def test_declared_operations_have_acceptance_cases_and_adapter_routes(model):
    caps = capabilities_for_model_id(model.model_id)
    for operation in caps.supported_operations or ():
        assert operation in CASES or operation in DISCOVERY, f"Add an acceptance case for {operation}"
        if operation not in WEB_ONLY:
            assert CLI_ALIASES.get(operation, operation) in PARSERS
        if operation not in CLI_ONLY:
            entry = CATALOG[WEB_ALIASES.get(operation, operation)]
            assert entry["presentation"]["models"][model.model_id]["supported"], operation
        if operation not in NO_WORKER | DISCOVERY:
            assert CLI_ALIASES.get(operation, operation) in DOMAIN_COMMANDS


def _admitted_cases():
    for model in PHYSICAL_MODEL_REGISTRY:
        caps = capabilities_for_model_id(model.model_id)
        for operation in sorted(CASES):
            if not operation_supported(caps, operation):
                continue
            entry = CATALOG.get(WEB_ALIASES.get(operation, operation))
            if caps.supported_operations is None:
                if entry is None or not entry["presentation"]["models"][model.model_id]["supported"]:
                    continue
            yield pytest.param(model.model_id, operation, id=f"{model.model_id}-{operation}")


def _arguments(operation, caps, path):
    cli_args, web_args = deepcopy(CASES[operation])
    if operation in {"capture-batch", "capture-monitor", "capture-until", "measure-log", "measure-until", "triggered-capture-series", "triggered-measure-loop", "acquisition-check", "smoke"}:
        cli_args["output_dir"] = str(path / "output")
    if operation == "capture":
        cli_args.update(csv=str(path / "wave.csv"), meta=str(path / "wave.json"))
    if operation == "screenshot":
        image_format = caps.supported_screenshot_formats[0]
        cli_args.update(output=str(path / f"screen.{image_format}"))
        if image_format != "png":
            cli_args["format"] = image_format
    if operation == "save-waveform" and caps.save_waveform_requires_source:
        cli_args["source_channel"] = web_args["source_channel"] = 1
    if operation == "sequence":
        document = {"version": 1, "steps": [{"action": "measure", "parameters": {"item": "vpp", "channel": 1}}]}
        path.mkdir(parents=True, exist_ok=True)
        sequence_file = path / "sequence.json"
        sequence_file.write_text(json.dumps(document), encoding="utf-8")
        cli_args.update(file=str(sequence_file), save_results=False)
        web_args.update(document=document, save_results=False)
    return cli_args, web_args


@pytest.mark.parametrize("model_id,operation", list(_admitted_cases()))
def test_supported_operation_plans_executes_and_accepts_adapter_requests(model_id, operation, tmp_path, capsys, monkeypatch):
    if model_id == "tektronix-tbs2074" and operation in {
        "timebase-position", "doctor", "live-data-snapshot", "smoke"
    }:
        from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend
        initialize = TektronixSimulatorBackend.__post_init__

        def initialize_with_delay_mode_on(backend):
            initialize(backend)
            backend.tek_settings["HORIZONTAL:DELAY:MODE"] = "ON"

        # These operations read timebase position, whose TBS2074 support
        # explicitly requires Delay Mode ON. The simulator itself still defaults OFF.
        monkeypatch.setattr(
            TektronixSimulatorBackend, "__post_init__", initialize_with_delay_mode_on
        )
    if operation == "setup-recall":
        from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend
        initialize = TektronixSimulatorBackend.__post_init__

        def initialize_with_saved_setup(backend):
            initialize(backend)
            backend.write("SAVe:SETUp 1")
            backend.history.clear()

        # Recall requires a previously saved slot in the simulated instrument.
        monkeypatch.setattr(TektronixSimulatorBackend, "__post_init__", initialize_with_saved_setup)
    caps = capabilities_for_model_id(model_id)
    cli_command = CLI_ALIASES.get(operation, operation)
    web_command = WEB_ALIASES.get(operation, operation)
    cli_args, web_args = _arguments(operation, caps, tmp_path)
    if operation not in WEB_ONLY:
        for mode in ("--dry-run", "--simulate"):
            code = cli.main([cli_command, *arguments_to_argv(cli_args), mode, "--model", model_id, "--json"])
            output = capsys.readouterr()
            assert code == 0, output.out + output.err
            payload = json.loads(output.out)
            assert payload["ok"]
            assert payload["scpi"]["planned" if mode == "--dry-run" else "sent"]
        if operation not in NO_WORKER:
            command, arguments, _ = validate_command_request({
                "schema_version": WORKER_SCHEMA_VERSION, "command": cli_command, "arguments": cli_args,
            })
            parsed = parse_domain_command(command, arguments, SimpleNamespace(mode="simulate", model=model_id, resource=None))
            assert parsed.command == cli_command
    if operation not in CLI_ONLY:
        entry = CATALOG[web_command]
        assert entry["presentation"]["models"][model_id]["supported"]
        for mode in (mode for mode in entry["modes"] if mode != "live"):
            normalized = deepcopy(web_args)
            _validate_parameters(web_command, normalized, mode, model_id)
            result = execute_command(web_command, mode=mode, resource=None, model_id=model_id,
                                     parameters=normalized, artifact_dir=tmp_path / f"web-{mode}")
            assert result["exit_code"] == 0, result
