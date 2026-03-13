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


class TaskId(StrEnum):
    """Canonical task identifiers loaded from run scripts."""

    ENSURE_GAME_RUNNING = "ensure_game_running"
    POPUP_RECOVERY = "popup_recovery"
    LOGIN = "login"
    SELECT_CASTLE = "select_castle"
    SEND_ALLIANCE_CHAT_MESSAGE = "send_alliance_chat_message"
    SEND_WORLD_CHAT_MESSAGE = "send_world_chat_message"
    BUILDING_UPGRADE = "building_upgrade"
    RESEARCH = "research"
    GATHERING = "gathering"
    CAMPAIGN = "campaign"


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

    def parse_params(self, params: Mapping[str, Any]) -> Any:
        """Validates and converts raw script parameters."""

    def is_applicable(self, context: "TaskContext", observation: Observation) -> bool:
        """Returns whether the task can reason about the current state."""

    def plan(self, context: "TaskContext", observation: Observation) -> list[ActionRequest]:
        """Builds declarative actions for the next task increment."""

    def verify(self, context: "TaskContext", before: Observation, after: Observation) -> TaskResult:
        """Verifies the last task increment and decides whether to continue."""


class BaseAutomationTask(ABC):
    """Provides shared defaults for concrete task implementations."""

    id: TaskId

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

    def _require_no_params(self, params: Mapping[str, Any]) -> None:
        """Fails fast when a parameterless task receives script parameters."""

        if params:
            raise ScriptValidationError(
                f"Task '{self.id}' does not accept script parameters.",
                task_id=self.id,
            )


def choose_priority_entry(
    entries: Sequence[DetectedListEntry],
    priorities: Sequence[TPriority],
    *,
    key_selector: Callable[[DetectedListEntry], TPriority],
) -> DetectedListEntry | None:
    """Returns the highest-priority entry using one canonical ranking helper."""

    if not entries:
        return None
    priority_rank = {priority: index for index, priority in enumerate(priorities)}
    ranked_entries = sorted(
        entries,
        key=lambda entry: priority_rank.get(key_selector(entry), len(priority_rank)),
    )
    best_entry = ranked_entries[0]
    if key_selector(best_entry) not in priority_rank:
        return None
    return best_entry
