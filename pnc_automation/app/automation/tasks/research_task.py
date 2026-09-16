"""Task that starts one eligible institute research item."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
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
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, TapAction, TapListEntryAction
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory, ResearchPolicy
from pnc_automation.app.pnc.domain.research import ResearchDetail, ResearchNodeId
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


@dataclass(frozen=True, slots=True)
class _ResearchNodeSelection:
    """One task-scoped node selection awaiting detail confirmation and one Start.

    Stored on the per-step ``TaskContext.runtime_state`` so independent task
    contexts never inherit a previous selection. ``confirmed`` is promoted only
    by ``verify`` after the open tap produces a newer clear matching detail in
    the same capture session; ``start_planned`` consumes the one Start tap so a
    failed or uncertain start is never planned again blindly.
    """

    node_id: ResearchNodeId
    category: ResearchCategory
    title_text: str | None
    selected_frame: FrameRef | None
    selected_at: datetime
    confirmed: bool = False
    start_planned: bool = False


_SELECTION_STATE_KEY = "research_task_selected_node"


class ResearchTask(BaseAutomationTask):
    """Starts one institute research item using the configured priority policy."""

    id = TaskId.RESEARCH
    castle_target_policy = CastleTargetPolicy.OPTIONAL
    preflight = TaskPreflight.HOME_CITY
    required_recognition_selectors = (UiElementId.PNC_RESEARCH_START_BUTTON,)

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
        """Plans one research increment; Start requires the confirmed selected detail."""

        if observation.screen_type not in {ScreenType.PNC_INSTITUTE, ScreenType.PNC_RESEARCH_TREE}:
            _clear_selection(context)
            return context.flows.open_institute(observation)
        if observation.screen_type == ScreenType.PNC_INSTITUTE:
            _clear_selection(context)
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

        detail = observation.research_detail
        if detail is not None:
            # Only the detail this task opened and verified can authorize its
            # single Start tap; pre-opened, active, or mismatched panels stay
            # read-only inspection.
            selection = _pending_selection(context)
            if selection is not None and not _detail_matches_selection(detail, selection):
                _clear_selection(context)
                return []
            if (
                selection is None
                or not selection.confirmed
                or selection.start_planned
                or not _has_template_start(observation)
            ):
                return []
            _store_selection(context, replace(selection, start_planned=True))
            return [
                TapAction(
                    selector_id=UiElementId.PNC_RESEARCH_START_BUTTON,
                    reason="start_research",
                    observe_after=True,
                )
            ]

        _clear_selection(context)
        candidates = tuple(
            entry
            for entry in observation.entries(ListEntryKind.RESEARCH)
            if entry.research_facts is not None
            and entry.research_facts.category is not None
            and entry.row_status == RowRecognitionStatus.COMPLETE
        )
        target = choose_priority_entry(
            candidates,
            context.params.priority,
            key_selector=lambda entry: entry.research_facts.category,
        )
        if target is None:
            return []
        selected = tuple(
            entry
            for entry in candidates
            if entry.research_facts is not None
            and entry.research_facts.node_id == target.research_facts.node_id
        )
        if (
            len(selected) != 1
            or target.research_facts is None
            or target.research_facts.node_id is None
        ):
            raise TaskVerificationError(
                "Research candidate is ambiguous or unidentified; no node was opened or started.",
                candidate_count=len(selected),
            )
        _store_selection(
            context,
            _ResearchNodeSelection(
                node_id=target.research_facts.node_id,
                category=target.research_facts.category,
                title_text=target.title_text,
                selected_frame=observation.frame_ref,
                selected_at=observation.captured_at,
            ),
        )
        return [
            _tap_entry(target, kind=ListEntryKind.RESEARCH, reason="open_research_candidate"),
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies either navigation to the research tree or a started research item."""

        selection = _pending_selection(context)
        if selection is not None and selection.start_planned:
            _clear_selection(context)
            if (
                _is_active_research_detail(after)
                and after.research_detail is not None
                and _detail_matches_selection(after.research_detail, selection)
                and _is_newer_same_session(after, selection)
                and not after.has(UiElementId.PNC_RESEARCH_START_BUTTON)
            ):
                return TaskResult.success("Research started and the active detail has no start button.")
            return TaskResult.failure(
                "Research start did not reach a fresh matching active detail.", retryable=True,
            )
        if selection is not None and not selection.confirmed:
            detail = after.research_detail
            if (
                detail is not None
                and after.decision.guard == GuardVerdict.CLEAR
                and _detail_matches_selection(detail, selection)
                and _is_newer_same_session(after, selection)
            ):
                _store_selection(context, replace(selection, confirmed=True))
                return TaskResult.replan("Opened the selected research detail.")
            _clear_selection(context)
            return TaskResult.failure(
                "The opened research detail did not match the selected node.", retryable=True,
            )
        if selection is not None:
            # A confirmed selection whose Start was never planned only survives
            # while the current frame still shows its matching detail.
            if after.research_detail is None or not _detail_matches_selection(after.research_detail, selection):
                _clear_selection(context)
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
        if before.screen_type == ScreenType.PNC_RESEARCH_TREE:
            if before.entries(ListEntryKind.RESEARCH) and after.research_detail is not None:
                return TaskResult.replan("Opened the selected research detail.")
            if not before.entries(ListEntryKind.RESEARCH) and before.research_detail is None:
                return TaskResult.skipped("No eligible research items were visible.")
        return TaskResult.failure("Research did not produce a verified state change.", retryable=True)


def _pending_selection(context: TaskContext) -> _ResearchNodeSelection | None:
    """Return the stored selection for this step context, if any."""

    value = context.runtime_state.get(_SELECTION_STATE_KEY)
    return value if isinstance(value, _ResearchNodeSelection) else None


def _store_selection(context: TaskContext, selection: _ResearchNodeSelection) -> None:
    """Persist the selection on the per-step runtime state."""

    context.runtime_state[_SELECTION_STATE_KEY] = selection


def _clear_selection(context: TaskContext) -> None:
    """Drop the remembered selection whenever the task loses its detail proof."""

    context.runtime_state.pop(_SELECTION_STATE_KEY, None)


def _detail_matches_selection(detail: ResearchDetail, selection: _ResearchNodeSelection) -> bool:
    """Match a measured detail to the verified source selection.

    A hidden detail category relies on the freshly verified source category; a
    visible conflicting category always fails.
    """

    if detail.node_id is None or detail.node_id != selection.node_id:
        return False
    return detail.category is None or detail.category == selection.category


def _is_newer_same_session(observation: Observation, selection: _ResearchNodeSelection) -> bool:
    """Require a fresher capture from the same session epoch as the selection frame."""

    if observation.captured_at <= selection.selected_at:
        return False
    frame = observation.frame_ref
    selected = selection.selected_frame
    if frame is None or selected is None:
        return True
    return (
        frame.session_id == selected.session_id
        and frame.session_epoch == selected.session_epoch
        and frame.capture_sequence > selected.capture_sequence
    )


def _has_template_start(observation: Observation) -> bool:
    """Return whether the ordinary Start control was template-matched on this frame."""

    element = observation.get(UiElementId.PNC_RESEARCH_START_BUTTON)
    return element is not None and element.source_kind == VisibleElementSourceKind.TEMPLATE


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


def _is_active_research_detail(observation: Observation) -> bool:
    """Return whether the postcondition proves the guarded active research detail."""

    return (
        observation.screen_type == ScreenType.PNC_RESEARCH_TREE
        and observation.decision.guard == GuardVerdict.CLEAR
        and any(
            evidence.screen_type == ScreenType.PNC_RESEARCH_TREE
            and evidence.reason == "visual_anchor:research_tree_node_detail_active"
            for evidence in observation.decision.evidence
        )
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
