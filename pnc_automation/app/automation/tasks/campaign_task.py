"""Task that advances one configured campaign stage."""

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
from pnc_automation.app.pnc.domain.campaign import CampaignMode
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.policy_models import CampaignPolicy
from pnc_automation.app.pnc.domain.screen_contracts import campaign_flow_screen_types
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


class CampaignTask(BaseAutomationTask):
    """Opens one campaign stage and advances to battle preparation."""

    id = TaskId.CAMPAIGN
    castle_target_policy = CastleTargetPolicy.OPTIONAL
    preflight = TaskPreflight.HOME_CITY
    required_recognition_selectors = (UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,)

    def parse_params(self, params: Mapping[str, Any]) -> CampaignPolicy:
        """Builds the typed campaign policy."""

        return CampaignPolicy.from_params(params)

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
        """Plans one campaign increment from the current screen."""

        if observation.screen_type not in campaign_flow_screen_types():
            return context.flows.open_campaign_map(observation, runtime_state=context.runtime_state)
        if observation.screen_type == ScreenType.PNC_BATTLE_PREP:
            return []
        if observation.screen_type == ScreenType.PNC_CAMPAIGN_STAGE:
            return [
                TapAction(
                    selector_id=UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
                    reason="open_battle_prep",
                    observe_after=True,
                )
            ]

        candidates = _eligible_stages(observation, context.params.enabled_modes)
        target = choose_priority_entry(
            candidates,
            context.params.enabled_modes,
            key_selector=lambda entry: entry.campaign_node.mode if entry.campaign_node is not None else None,
        )
        if target is None:
            return []
        return [
            _tap_entry(target, kind=ListEntryKind.CAMPAIGN_STAGE, reason="open_campaign_stage"),
            TapAction(
                selector_id=UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
                reason="open_battle_prep",
                observe_after=True,
            ),
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies either navigation to campaign or a prepared battle."""

        if before.screen_type not in campaign_flow_screen_types():
            if after.screen_type == ScreenType.PNC_BATTLE_PREP:
                return TaskResult.success("Campaign battle preparation was already open after entry.")
            if after.screen_type in campaign_flow_screen_types():
                return TaskResult.replan("Reached campaign flow for stage planning.")
            return TaskResult.failure("Campaign task could not reach the campaign flow.", retryable=True)
        if before.screen_type == ScreenType.PNC_BATTLE_PREP:
            return TaskResult.skipped("Campaign battle preparation was already open.")
        if before.screen_type in {
            ScreenType.PNC_CAMPAIGN_MAP,
            ScreenType.PNC_CAMPAIGN_CHAPTER,
        } and not _eligible_stages(before, context.params.enabled_modes):
            return TaskResult.skipped("No eligible campaign stages were visible.")
        if after.screen_type == ScreenType.PNC_BATTLE_PREP:
            return TaskResult.success("Campaign advanced to battle preparation.")
        if before.screen_type == ScreenType.PNC_CAMPAIGN_MAP and after.screen_type == ScreenType.PNC_CAMPAIGN_STAGE:
            return TaskResult.replan("Opened campaign stage details.")
        return TaskResult.failure("Campaign did not produce a verified state change.", retryable=True)


def _eligible_stages(
    observation: Observation, enabled_modes: tuple[CampaignMode, ...]
) -> tuple[DetectedListEntry, ...]:
    """Stage rows safe to plan or verify against on either campaign surface.

    Eligibility requires a COMPLETE row (which already proves measured action
    geometry), typed node facts with an observed positive stage number,
    ``locked is False``, and an observed mode configured for this run. Unknown
    or unsupported evidence is skipped rather than converted to a default.
    """

    return tuple(
        entry
        for entry in observation.entries(ListEntryKind.CAMPAIGN_STAGE)
        if entry.row_status == RowRecognitionStatus.COMPLETE
        and entry.campaign_node is not None
        and entry.campaign_node.stage_number is not None
        and entry.campaign_node.locked is False
        and entry.campaign_node.mode in enabled_modes
        and entry.action_point is not None
        and entry.action_bounds is not None
    )


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
