"""Assign one validation owner to each collected Windows PowerShell test."""

import pytest

from tests.tooling._validation_grouping import GROUPS, owner_for_windows_case


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("windows_powershell") is None:
            continue
        name = getattr(item, "originalname", None) or item.name.split("[", 1)[0]
        parameters = getattr(getattr(item, "callspec", None), "params", {})
        try:
            owner = owner_for_windows_case(item.path.name, name, parameters)
        except ValueError as error:
            raise pytest.UsageError(f"{item.nodeid}: {error}") from error
        existing = [
            group for group in GROUPS
            if item.get_closest_marker(f"validation_{group}") is not None
        ]
        if existing and existing != [owner]:
            raise pytest.UsageError(
                f"{item.nodeid}: conflicting validation markers {existing}, expected {owner}"
            )
        if not existing:
            item.add_marker(getattr(pytest.mark, f"validation_{owner}"))
