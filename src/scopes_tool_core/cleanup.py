"""Conservative cleanup profiles built from existing Core operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .capabilities import ScopeCapabilities
from .demo import demo_output_command
from .display import annotation_clear_command, display_clear_command
from .dvm import dvm_enable_command
from .errors import ParameterValidationError
from .search import search_state_command
from .status import system_clear_status_command, system_opc_query

if TYPE_CHECKING:
    from .scope import Oscilloscope
    from .status import SystemErrorEntry


CLEANUP_PROFILES = ("minimal", "safe")


@dataclass(frozen=True)
class CleanupSkip:
    action: str
    reason: str

    def to_json(self) -> dict[str, str]:
        return {"action": self.action, "reason": self.reason}


@dataclass(frozen=True)
class CleanupPlan:
    profile: str
    actions: tuple[str, ...]
    skipped: tuple[CleanupSkip, ...]
    commands: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "actions": list(self.actions),
            "skipped": [item.to_json() for item in self.skipped],
            "final_error_queue_clean": None,
        }


@dataclass(frozen=True)
class CleanupResult:
    profile: str
    actions: tuple[str, ...]
    skipped: tuple[CleanupSkip, ...]
    final_error: SystemErrorEntry

    @property
    def final_error_queue_clean(self) -> bool:
        return not self.final_error.is_error

    def to_json(self) -> dict[str, object]:
        result: dict[str, object] = {
            "profile": self.profile,
            "actions": list(self.actions),
            "skipped": [item.to_json() for item in self.skipped],
            "final_error_queue_clean": self.final_error_queue_clean,
        }
        if self.final_error.is_error:
            result["errors"] = [
                {
                    "code": self.final_error.code,
                    "message": self.final_error.message,
                    "raw": self.final_error.raw,
                }
            ]
        return result


def plan_cleanup(profile: str, capabilities: ScopeCapabilities) -> CleanupPlan:
    """Build one explicit cleanup sequence for a known capability profile."""

    if profile not in CLEANUP_PROFILES:
        raise ParameterValidationError(
            f"cleanup profile must be one of: {', '.join(CLEANUP_PROFILES)}."
        )

    actions = ["clear_status", "clear_display"]
    commands = [system_clear_status_command(), display_clear_command()]
    skipped = [
        CleanupSkip(
            "clear_display_persistence",
            "display_persistence_clear_not_implemented",
        )
    ]

    if profile == "safe":
        actions.append("disable_dvm")
        commands.append(dvm_enable_command(False))

        if capabilities.supports_search_basic:
            actions.append("disable_search")
            commands.append(search_state_command(False))
        else:
            skipped.append(CleanupSkip("disable_search", "search_not_supported"))

        if capabilities.supports_annotation:
            actions.append("clear_annotation")
            commands.append(
                annotation_clear_command(slot=1, capabilities=capabilities)
            )
        else:
            skipped.append(CleanupSkip("clear_annotation", "annotation_not_supported"))

        if capabilities.supports_demo:
            actions.append("disable_demo_output")
            commands.append(demo_output_command(False))
        else:
            skipped.append(CleanupSkip("disable_demo_output", "demo_not_supported"))

        skipped.append(CleanupSkip("disable_wgen", "wgen_not_implemented"))

    actions.extend(("wait_operation_complete", "final_error_check"))
    commands.extend((system_opc_query(), ":SYSTem:ERRor?"))
    return CleanupPlan(
        profile=profile,
        actions=tuple(actions),
        skipped=tuple(skipped),
        commands=tuple(commands),
    )


def execute_cleanup(scope: Oscilloscope, profile: str) -> CleanupResult:
    """Execute a cleanup plan using only existing facade helpers."""

    if scope.capabilities is None:
        raise ParameterValidationError(
            "Cleanup requires known capabilities; call query_idn() first."
        )

    plan = plan_cleanup(profile, scope.capabilities)
    scope.clear_status()
    scope.clear_display()

    if profile == "safe":
        scope.configure_dvm_enable(False)
        if scope.capabilities.supports_search_basic:
            scope.configure_search_state(False)
        if scope.capabilities.supports_annotation:
            scope.clear_annotation(slot=1)
        if scope.capabilities.supports_demo:
            scope.configure_demo_output(False)

    scope.query_operation_complete()
    final_error = scope.query_system_error()
    return CleanupResult(
        profile=plan.profile,
        actions=plan.actions,
        skipped=plan.skipped,
        final_error=final_error,
    )
