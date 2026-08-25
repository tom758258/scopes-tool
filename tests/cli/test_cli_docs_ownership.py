from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_ROOT = REPO_ROOT / "docs" / "cli"


def read_doc(*parts: str) -> str:
    return DOC_ROOT.joinpath(*parts).read_text(encoding="utf-8")


def read_contract(*parts: str) -> str:
    return REPO_ROOT.joinpath("docs", "contracts", *parts).read_text(
        encoding="utf-8"
    )


def assert_headings(text: str, *headings: str) -> None:
    for heading in headings:
        assert heading in text


def test_cli_docs_are_root_level_and_contracts_are_root_level():
    assert (DOC_ROOT / "README.md").exists()
    assert (REPO_ROOT / "CHANGELOG.md").exists()
    assert (DOC_ROOT / "cli-integration.md").exists()
    assert (REPO_ROOT / "AGENTS.md").exists()
    assert (REPO_ROOT / "README.md").exists()
    assert (REPO_ROOT / "docs" / "architecture" / "monorepo-layout.md").exists()

    for contract in (
        "common-worker-protocol.md",
        "common-cli-jsonl-contract.md",
        "scopes-cli-jsonl-contract.md",
        "common-orchestrator-workflows.md",
        "scopes-orchestrator-workflows.md",
        "scopes-worker-contract.md",
    ):
        assert (REPO_ROOT / "docs" / "contracts" / contract).exists()
        assert not (DOC_ROOT / contract).exists()


def test_cli_integration_keeps_cli_fields_out_of_core_schema():
    text = read_doc("cli-integration.md")

    assert "measurement_cli_name" in text
    assert "argparse.Namespace" in text
    assert "scopes-tool = scopes_tool_cli.cli:main" in text


def test_root_readme_discovers_cli_and_agent_docs():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "AGENTS.md" in text
    assert "docs/cli/README.md" in text
    assert "docs/cli/cli-integration.md" in text


def test_cli_command_guide_links_root_contracts_and_safe_modes():
    text = read_doc("README.md")

    assert "--dry-run --json" in text
    assert "--simulate --json" in text
    assert "--live --resource" in text
    assert "scopes-cli-jsonl-contract.md" in text
    assert "common-cli-jsonl-contract.md" in text
    assert "scopes-tool.exe sequence" in text
    assert "integration.md" in text


def test_common_contracts_stay_instrument_neutral():
    text = "\n".join(
        read_contract(path)
        for path in (
            "common-worker-protocol.md",
            "common-cli-jsonl-contract.md",
            "common-orchestrator-workflows.md",
        )
    )

    for forbidden in ("Scopes", "Keysight", "DSOX", "VISA", "SCPI", "oscilloscope"):
        assert forbidden not in text


def test_scopes_contracts_link_common_contracts_and_keep_public_structure():
    cli_contract = read_contract("scopes-cli-jsonl-contract.md")
    workflow_contract = read_contract("scopes-orchestrator-workflows.md")
    worker_contract = read_contract("scopes-worker-contract.md")

    assert "common-cli-jsonl-contract.md" in cli_contract
    assert "common-orchestrator-workflows.md" in workflow_contract
    assert "common-worker-protocol.md" in worker_contract
    assert_headings(
        cli_contract,
        "## Worker JSONL Events",
        "## Worker Client JSON",
        "## Command Result Fields",
        "## Compatibility Rules",
    )
    assert_headings(
        workflow_contract,
        "## Worker Workflow",
        "## Live Capture Workflow",
        "## Cleanup Rule",
    )
    assert_headings(
        worker_contract,
        "## Endpoints",
        "## Command Inventory",
        "## Artifacts",
        "## Safety",
    )


def test_scopes_contracts_keep_public_commands_and_schema_fields():
    text = "\n".join(
        read_contract(path)
        for path in (
            "scopes-cli-jsonl-contract.md",
            "scopes-worker-contract.md",
            "scopes-orchestrator-workflows.md",
        )
    )

    for command in (
        "scopes-tool worker",
        "scopes-tool send-command",
        "scopes-tool status",
        "scopes-tool stop",
        "scopes-tool wait-ready",
    ):
        assert command in text

    for field in (
        "event",
        "run_id",
        "job_id",
        "worker_job_id",
        "command_url",
        "status_url",
        "stop_url",
        "job_finished",
        "last_job",
        "result",
        "files",
        "output_dir",
        "csv",
        "meta",
        "ok",
        "failed",
        "cancelled",
    ):
        assert field in text
