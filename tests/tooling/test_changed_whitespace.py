from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_changed_whitespace.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "tests.yml"
ZERO_SHA = "0" * 40


def _git(repo: Path, *args: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Whitespace Test")
    _git(repo, "config", "user.email", "whitespace@example.invalid")
    return repo


def _commit_file(repo: Path, name: str, content: str, message: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    _git(repo, "add", name)
    _git(repo, "commit", "--quiet", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _run_checker(repo: Path, **event: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(event)
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=repo,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_pull_request_range_detects_new_trailing_whitespace(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _commit_file(repo, "example.txt", "clean\n", "base")
    head = _commit_file(repo, "example.txt", "clean\nnew trailing   \n", "head")

    completed = _run_checker(
        repo,
        EVENT_NAME="pull_request",
        PR_BASE_SHA=base,
        PR_HEAD_SHA=head,
    )

    assert completed.returncode == 2
    assert "example.txt:2: trailing whitespace." in completed.stdout
    assert "PR merge-base range" in completed.stderr


def test_push_range_detects_new_trailing_whitespace(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    before = _commit_file(repo, "example.txt", "clean\n", "before")
    target = _commit_file(repo, "example.txt", "clean\nnew trailing   \n", "target")

    completed = _run_checker(
        repo,
        EVENT_NAME="push",
        PUSH_BEFORE=before,
        PUSH_SHA=target,
    )

    assert completed.returncode == 2
    assert "example.txt:2: trailing whitespace." in completed.stdout
    assert "push changed range" in completed.stderr


@pytest.mark.parametrize("before", [ZERO_SHA, "", "not-a-commit"])
def test_unavailable_push_base_checks_only_target_against_parent(
    tmp_path: Path,
    before: str,
) -> None:
    repo = _init_repo(tmp_path)
    _commit_file(repo, "legacy.txt", "historical trailing   \n", "historical")
    target = _commit_file(repo, "current.txt", "clean\n", "clean target")

    completed = _run_checker(
        repo,
        EVENT_NAME="push",
        PUSH_BEFORE=before,
        PUSH_SHA=target,
    )

    assert completed.returncode == 0
    assert "parent-to-target fallback" in completed.stderr
    assert "legacy.txt" not in completed.stdout


def test_unavailable_push_base_checks_root_commit_as_root_diff(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    root = _commit_file(repo, "root.txt", "root trailing   \n", "root")

    completed = _run_checker(
        repo,
        EVENT_NAME="push",
        PUSH_BEFORE=ZERO_SHA,
        PUSH_SHA=root,
    )

    assert completed.returncode == 2
    assert "root.txt:1: trailing whitespace." in completed.stdout
    assert "root-commit fallback" in completed.stderr


def test_invalid_push_target_fails_clearly(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_file(repo, "base.txt", "base\n", "base")

    completed = _run_checker(
        repo,
        EVENT_NAME="push",
        PUSH_BEFORE=ZERO_SHA,
        PUSH_SHA="not-a-commit",
    )

    assert completed.returncode == 1
    assert "push target SHA is unavailable or invalid" in completed.stderr


def test_invalid_pull_request_sha_fails_clearly(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _commit_file(repo, "base.txt", "base\n", "base")

    completed = _run_checker(
        repo,
        EVENT_NAME="pull_request",
        PR_BASE_SHA=base,
        PR_HEAD_SHA="not-a-commit",
    )

    assert completed.returncode == 1
    assert "PR head SHA is unavailable or invalid" in completed.stderr


def test_pull_request_without_merge_base_fails_clearly(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _commit_file(repo, "base.txt", "base\n", "base")
    tree = _git(repo, "write-tree")
    unrelated_head = _git(repo, "commit-tree", tree, input_text="unrelated head\n")

    completed = _run_checker(
        repo,
        EVENT_NAME="pull_request",
        PR_BASE_SHA=base,
        PR_HEAD_SHA=unrelated_head,
    )

    assert completed.returncode == 1
    assert "could not establish a trustworthy changed range" in completed.stderr
    assert "merge base" in completed.stderr
    assert "full tree" not in (completed.stdout + completed.stderr).lower()


def test_unsupported_event_fails_clearly(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    completed = _run_checker(repo, EVENT_NAME="workflow_dispatch")

    assert completed.returncode == 1
    assert "unsupported event: workflow_dispatch" in completed.stderr


def test_workflow_wires_event_range_with_full_history() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "fetch-depth: 0" in workflow
    assert "ref: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow
    assert "PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}" in workflow
    assert "PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in workflow
    assert "PUSH_BEFORE: ${{ github.event.before }}" in workflow
    assert "PUSH_SHA: ${{ github.sha }}" in workflow
    assert "python scripts/check_changed_whitespace.py" in workflow
    assert "hash-object -t tree" not in workflow
    assert "check_full_tree" not in workflow
