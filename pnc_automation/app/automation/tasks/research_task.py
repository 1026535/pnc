"""Task that starts one eligible institute research item."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.app.automation.engine.task import (
    BaseAutomationTask,
    CastleTargetPolicy,
    TaskId,
    TaskPreflight,
    TaskResult,
    choose_priority_entry,
)
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, TapAction, TapListEntryAction
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory, ResearchPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


class ResearchTask(BaseAutomationTask):
    """Starts one institute research item using the configured priority policy."""

    id = TaskId.RESEARCH
    castle_target_policy = CastleTargetPolicy.OPTIONAL
    preflight = TaskPreflight.HOME_CITY

    def parse_params(self, params: Mapping[str, Any]) -> ResearchPolicy:
        """Builds the typed research policy."""

        return ResearchPolicy.from_params(params)

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Rejects unsupported bootstrap and login states."""

        return observation.screen_type not in {
            ScreenType.UNKNOWN,
            ScreenType.ANDROID_HOME,
            ScreenType.PNC_LOGIN,
            ScreenType.PNC_ACCOUNT_SWITCH,
            ScreenType.PNC_CASTLE_SELECTION,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans one research-start increment from the current screen."""

        if observation.screen_type not in {ScreenType.PNC_INSTITUTE, ScreenType.PNC_RESEARCH_TREE}:
            return context.flows.open_institute(observation)
        if observation.screen_type == ScreenType.PNC_INSTITUTE:
            selector_id = _choose_institute_category_selector(observation, context.params.priority)
            if selector_id is not None:
                return [
                    TapAction(
                        selector_id=selector_id,
                        reason="open_research_tree",
                        observe_after=True,
                    )
                ]
            if observation.has(UiElementId.PNC_RESEARCH_AVAILABLE_BADGE):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_RESEARCH_AVAILABLE_BADGE,
                        reason="open_research_tree",
                        observe_after=True,
                    )
                ]
            return []

        candidates = observation.entries(ListEntryKind.RESEARCH)
        target = choose_priority_entry(
            candidates,
            context.params.priority,
            key_selector=lambda entry: ResearchCategory(str(entry.require_metadata("category"))),
        )
        if target is None:
            return []
        return [
            _tap_entry(target, kind=ListEntryKind.RESEARCH, reason="open_research_candidate"),
            TapAction(
                selector_id=UiElementId.PNC_RESEARCH_START_BUTTON,
                reason="start_research",
                observe_after=True,
            ),
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies either navigation to the research tree or a started research item."""

        if before.screen_type not in {ScreenType.PNC_INSTITUTE, ScreenType.PNC_RESEARCH_TREE}:
            if after.screen_type in {ScreenType.PNC_INSTITUTE, ScreenType.PNC_RESEARCH_TREE}:
                return TaskResult.replan("Reached institute flow for research planning.")
            return TaskResult.failure("Research task could not reach the institute flow.", retryable=True)
        if before.screen_type == ScreenType.PNC_INSTITUTE:
            if _choose_institute_category_selector(before, context.params.priority) is None and not before.has(
                UiElementId.PNC_RESEARCH_AVAILABLE_BADGE
            ):
                return TaskResult.skipped("No research category button was visible in the institute.")
            if after.screen_type == ScreenType.PNC_RESEARCH_TREE:
                return TaskResult.replan("Opened the research tree.")
        if before.screen_type == ScreenType.PNC_RESEARCH_TREE and not before.entries(ListEntryKind.RESEARCH):
            return TaskResult.skipped("No eligible research items were visible.")
        if after.screen_type == ScreenType.PNC_RESEARCH_TREE and not after.has(UiElementId.PNC_RESEARCH_START_BUTTON):
            return TaskResult.success("Research started and the start button is no longer visible.")
        if after.screen_type == ScreenType.PNC_RESEARCH_TREE and len(after.entries(ListEntryKind.RESEARCH)) < len(before.entries(ListEntryKind.RESEARCH)):
            return TaskResult.success("Research started and one visible candidate disappeared.")
        return TaskResult.failure("Research did not produce a verified state change.", retryable=True)


def _tap_entry(entry: object, *, kind: ListEntryKind, reason: str) -> TapListEntryAction:
    """Builds a list-entry tap action using the most stable available key."""

    if entry.title_text is None:
        raise TaskVerificationError("Dynamic entry is missing a title and cannot be reselected safely.", entry_kind=kind)
    return TapListEntryAction(
        entry_kind=kind,
        title_text=entry.title_text,
        use_action_point=True,
        reason=reason,
        observe_after=True,
    )


_INSTITUTE_CATEGORY_SELECTOR_BY_RESEARCH_CATEGORY = {
    ResearchCategory.DEVELOPMENT: UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
    ResearchCategory.ECONOMY: UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON,
    ResearchCategory.MILITARY: UiElementId.PNC_INSTITUTE_MILITARY_BUTTON,
    ResearchCategory.FORTIFICATION: UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON,
}


def _choose_institute_category_selector(
    observation: Observation,
    priority: tuple[ResearchCategory, ...],
) -> UiElementId | None:
    """Returns the highest-priority visible institute category selector."""

    for category in priority:
        selector_id = _INSTITUTE_CATEGORY_SELECTOR_BY_RESEARCH_CATEGORY.get(category)
        if selector_id is not None and observation.has(selector_id):
            return selector_id
    return None
