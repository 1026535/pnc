"""Task contract and shared task helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from pnc_automation.core.errors import ScriptValidationError
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, Observation
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

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
    COLLECT_KINGDOM_CHAT = "collect_kingdom_chat"
    OPEN_BUILDING = "open_building"
    BUILDING_CONSTRUCT = "building_construct"
    BUILDING_UPGRADE = "building_upgrade"
    RESEARCH = "research"
    GATHERING = "gathering"
    CAMPAIGN = "campaign"
    DAILY_MAINTENANCE = "daily_maintenance"
    HERO_ARENA = "hero_arena"
    USE_RESOURCE_ITEM = "use_resource_item"
    HERO_HALL = "hero_hall"
    UPGRADE_HERO = "upgrade_hero"
    GATHER_ALLIANCE_MINE = "gather_alliance_mine"
    RESOURCE_BUILDING_BOOST = "resource_building_boost"
    TRIAL_SHOP = "trial_shop"
    RARE_EARTH_SHOP = "rare_earth_shop"
    ALLIANCE_SHOP = "alliance_shop"
    PRAISE = "praise"
    SUMMON_SAURGIL = "summon_saurgil"
    ENHANCE_GEM = "enhance_gem"
    ENHANCE_SAURGEM = "enhance_saurgem"
    ENHANCE_GEAR = "enhance_gear"
    WISHES = "wishes"
    LAND_OF_TRIAL = "land_of_trial"
    LOST_LAND = "lost_land"
    ALLIANCE_DONATIONS = "alliance_donations"
    ALLIANCE_GIFT = "alliance_gift"


class CastleTargetPolicy(StrEnum):
    """Declares whether a task can consume one explicit step-level castle target."""

    DISALLOWED = "disallowed"
    OPTIONAL = "optional"
    REQUIRED = "required"


class TaskPreflight(StrEnum):
    """Declares the runner-owned entry state one task requires before its body executes."""

    NONE = "none"
    HOME_CITY = "home_city"
    WORLD_MAP = "world_map"


class TaskStatus(StrEnum):
    """High-level step execution outcomes."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    REPLAN = "replan"


def require_no_params(task_id: TaskId, params: Mapping[str, Any]) -> None:
    """Validates the canonical parameterless task contract for script definitions."""

    if not isinstance(params, Mapping):
        raise ScriptValidationError(
            f"Task '{task_id}' parameters must be a mapping.",
            task_id=task_id,
        )
    if params:
        raise ScriptValidationError(
            f"Task '{task_id}' does not accept script parameters.",
            task_id=task_id,
        )


class TaskDefinition(Protocol):
    """Common metadata contract shared by legacy and typed task definitions."""

    id: TaskId
    castle_target_policy: CastleTargetPolicy

    def parse_params(self, params: Mapping[str, Any]) -> Any:
        """Validates and converts raw script parameters."""


@dataclass(frozen=True, slots=True)
class CoreWorkflowTaskDefinition:
    """Immutable metadata for a task dispatched through the replacement core."""

    id: TaskId
    castle_target_policy: CastleTargetPolicy
    parameter_parser: Callable[[Mapping[str, Any]], Any]

    def __post_init__(self) -> None:
        """Rejects malformed typed task metadata before scripts can be prepared."""

        if not isinstance(self.id, TaskId):
            raise TypeError("CoreWorkflowTaskDefinition.id must be a TaskId.")
        if not isinstance(self.castle_target_policy, CastleTargetPolicy):
            raise TypeError(
                "CoreWorkflowTaskDefinition.castle_target_policy must be a CastleTargetPolicy."
            )
        if not callable(self.parameter_parser):
            raise TypeError("CoreWorkflowTaskDefinition.parameter_parser must be callable.")

    def parse_params(self, params: Mapping[str, Any]) -> Any:
        """Parses one typed definition through its canonical parameter parser."""

        return self.parameter_parser(params)


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
    preflight: TaskPreflight
    required_recognition_selectors: tuple[UiElementId, ...]

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
    preflight = TaskPreflight.NONE
    required_recognition_selectors: tuple[UiElementId, ...] = ()

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

        require_no_params(self.id, params)


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
