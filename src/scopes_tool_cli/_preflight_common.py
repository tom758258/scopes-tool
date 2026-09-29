"""Shared CLI pre-open validation helpers."""

from __future__ import annotations

import argparse

from scopes_tool_core.capabilities import (
    ScopeCapabilities,
    capabilities_for_model_id,
)


def _pre_open_capabilities(
    args: argparse.Namespace,
) -> ScopeCapabilities | None:
    if (
        bool(getattr(args, "simulate", False))
        or bool(getattr(args, "dry_run", False))
        or bool(getattr(args, "_worker_live_validation", False))
    ):
        return capabilities_for_model_id(args.model)
    return None
