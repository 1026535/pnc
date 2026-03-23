"""Task contract and shared task helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from pnc_automation.errors import ScriptValidationError
from pnc_automation.pnc.action_requests import ActionRequest
from pnc_automation.pnc.observation import DetectedListEntry, Observation

TPriority = TypeVar("TPriority")
TCandidate = TypeVar("TCandidate")


class TaskId(StrEnum):
    """Canonical task identifiers loaded from run scripts."""

    ENSURE_GAME_RUNNING = "ensure_game_running"
    POPUP_RECOVERY = "popup_recovery"
    LOGIN = "login"
    SELECT_CASTLE = "select_castle"
    REFRESH_CASTLE_ROSTER = "refresh_castle_roster"
    SEND_ALLIANCE_CHAT_MESSAGE = "send_alliance_chat_message"
    SEND_WORLD_CHAT_MESSAGE = "send_world_chat_message"
    SEND_MAIL = "send_mail"
    COLLECT_MAIL = "collect_mail"
    BUILDING_UPGRADE = "building_upgrade"
    RESEARCH = "research"
    GATHERING = "gathering"
    CAMPAIGN = "campaign"


class CastleTargetPolicy(StrEnum):
    """Declares whether a task can consume one explicit step-level castle target."""

    DISALLOWED = "disallowed"
    OPTIONAL = "optional"
    REQUIRED = "required"


class TaskStatus(StrEnum):
    """High-level step execution outcomes."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    REPLAN = "replan"


@dataclass(frozen=True, slots=True)
class TaskResult:
    """Represents the result of one task verification pass."""

    status: TaskStatus
    message: str
    retryable: bool = False

    @property
    def succeeded(self) -> bool:
        """Returns whether the task finished successfully or as a no-op."""

        return self.status in {TaskStatus.SUCCESS, TaskStatus.SKIPPED}

    @classmethod
    def success(cls, message: str) -> "TaskResult":
        """Builds a success result."""

        return cls(status=TaskStatus.SUCCESS, message=message)

    @classmethod
    def skipped(cls, message: str) -> "TaskResult":
        """Builds a skipped/no-op success result."""

        return cls(status=TaskStatus.SKIPPED, message=message)

    @classmethod
    def replan(cls, message: str) -> "TaskResult":
        """Builds a result that asks the runner to observe and plan again."""

        return cls(status=TaskStatus.REPLAN, message=message)

    @classmethod
    def failure(cls, message: str, *, retryable: bool = False) -> "TaskResult":
        """Builds a failed result."""

        return cls(status=TaskStatus.FAILED, message=message, retryable=retryable)


class AutomationTask(Protocol):
    """Defines the canonical extension model for all automation tasks."""

    id: TaskId
    castle_target_policy: CastleTargetPolicy

    def parse_params(self, params: Mapping[str, Any]) -> Any:
        """Validates and converts raw script parameters."""

    def is_applicable(self, context: "TaskContext", observation: Observation) -> bool:
        """Returns whether the task can reason about the current state."""

    def plan(self, context: "TaskContext", observation: Observation) -> list[ActionRequest]:
        """Builds declarative actions for the next task increment."""

    def verify(self, context: "TaskContext", before: Observation, after: Observation) -> TaskResult:
        """Verifies the last task increment and decides whether to continue."""

    def max_replans_per_step(self, context: "TaskContext") -> int | None:
        """Returns an optional task-local replan cap override for unusually long but bounded workflows."""


class BaseAutomationTask(ABC):
    """Provides shared defaults for concrete task implementations."""

    id: TaskId
    castle_target_policy = CastleTargetPolicy.DISALLOWED

    @abstractmethod
    def parse_params(self, params: Mapping[str, Any]) -> Any:
        """Validates and converts raw params into the task's typed model."""

    @abstractmethod
    def is_applicable(self, context: "TaskContext", observation: Observation) -> bool:
        """Returns whether the task can reason about the current state."""

    @abstractmethod
    def plan(self, context: "TaskContext", observation: Observation) -> list[ActionRequest]:
        """Builds declarative actions for the next task increment."""

    @abstractmethod
    def verify(self, context: "TaskContext", before: Observation, after: Observation) -> TaskResult:
        """Verifies the last task increment and decides whether to continue."""

    def max_replans_per_step(self, context: "TaskContext") -> int | None:
        """Returns an optional task-local replan cap override when the default runner budget is too small."""

        del context
        return None

    def _require_no_params(self, params: Mapping[str, Any]) -> None:
        """Fails fast when a parameterless task receives script parameters."""

        if params:
            raise ScriptValidationError(
                f"Task '{self.id}' does not accept script parameters.",
                task_id=self.id,
            )


def choose_priority_candidate(
    candidates: Sequence[TCandidate],
    priorities: Sequence[TPriority],
    *,
    key_selector: Callable[[TCandidate], TPriority],
) -> TCandidate | None:
    """Returns the highest-priority candidate using one canonical ranking helper."""

    if not candidates:
        return None
    priority_rank = {priority: index for index, priority in enumerate(priorities)}
    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: priority_rank.get(key_selector(candidate), len(priority_rank)),
    )
    best_candidate = ranked_candidates[0]
    if key_selector(best_candidate) not in priority_rank:
        return None
    return best_candidate


def choose_priority_entry(
    entries: Sequence[DetectedListEntry],
    priorities: Sequence[TPriority],
    *,
    key_selector: Callable[[DetectedListEntry], TPriority],
) -> DetectedListEntry | None:
    """Returns the highest-priority dynamic entry using the shared candidate ranking helper."""

    return choose_priority_candidate(entries, priorities, key_selector=key_selector)
