"""Conservative cleanup profiles built from existing Core operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .capabilities import ScopeCapabilities, operation_supported
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
    def final_error_queue_clean(self) -> bool | None:
        if not getattr(self.final_error, "is_system_error_queue", True):
            return None
        return not self.final_error.is_error

    def to_json(self) -> dict[str, object]:
        result: dict[str, object] = {
            "profile": self.profile,
            "actions": list(self.actions),
            "skipped": [item.to_json() for item in self.skipped],
            "final_error_queue_clean": self.final_error_queue_clean,
        }
        if not getattr(self.final_error, "is_system_error_queue", True):
            result["post_command_status"] = self.final_error.to_json()
            return result
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

    actions = ["clear_status"]
    commands = [system_clear_status_command()]
    skipped = [
        CleanupSkip(
            "clear_display_persistence",
            "display_persistence_clear_not_implemented",
        )
    ]

    if operation_supported(capabilities, "display-clear"):
        actions.append("clear_display")
        commands.append(display_clear_command())
    else:
        skipped.append(CleanupSkip("clear_display", "display_clear_not_supported"))

    if profile == "safe":
        if operation_supported(capabilities, "dvm"):
            actions.append("disable_dvm")
            commands.append(dvm_enable_command(False))
        else:
            skipped.append(CleanupSkip("disable_dvm", "dvm_not_supported"))

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
    from .planning import workflow_step_scpi
    commands.append(system_opc_query())
    commands.extend(workflow_step_scpi(capabilities, "status"))
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
    if "clear_display" in plan.actions:
        scope.clear_display()

    if profile == "safe":
        if "disable_dvm" in plan.actions:
            scope.configure_dvm_enable(False)
        if scope.capabilities.supports_search_basic:
            scope.configure_search_state(False)
        if scope.capabilities.supports_annotation:
            scope.clear_annotation(slot=1)
        if scope.capabilities.supports_demo:
            scope.configure_demo_output(False)

    scope.query_operation_complete()
    final_error = scope.workflow_status()
    return CleanupResult(
        profile=plan.profile,
        actions=plan.actions,
        skipped=plan.skipped,
        final_error=final_error,
    )
