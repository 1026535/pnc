"""Task that advances one configured campaign stage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult, choose_priority_entry
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import TaskVerificationError
from pnc_automation.pnc.action_requests import ActionRequest, TapAction, TapListEntryAction
from pnc_automation.pnc.observation import ListEntryKind, Observation
from pnc_automation.pnc.policy_models import CampaignMode, CampaignPolicy
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


class CampaignTask(BaseAutomationTask):
    """Opens one campaign stage and advances to battle preparation."""

    id = TaskId.CAMPAIGN

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

        if observation.screen_type not in {ScreenType.PNC_CAMPAIGN, ScreenType.PNC_CAMPAIGN_STAGE, ScreenType.PNC_BATTLE_PREP}:
            actions = context.flows.ensure_home_city(observation)
            actions.append(
                TapAction(
                    selector_id=UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                    reason="open_campaign",
                    observe_after=True,
                )
            )
            return actions
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

        candidates = observation.entries(ListEntryKind.CAMPAIGN_STAGE)
        target = choose_priority_entry(
            candidates,
            context.params.enabled_modes,
            key_selector=lambda entry: CampaignMode(str(entry.require_metadata("mode"))),
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

        if before.screen_type not in {ScreenType.PNC_CAMPAIGN, ScreenType.PNC_CAMPAIGN_STAGE, ScreenType.PNC_BATTLE_PREP}:
            if after.screen_type in {ScreenType.PNC_CAMPAIGN, ScreenType.PNC_CAMPAIGN_STAGE}:
                return TaskResult.replan("Reached campaign flow for stage planning.")
            return TaskResult.failure("Campaign task could not reach the campaign flow.", retryable=True)
        if before.screen_type == ScreenType.PNC_BATTLE_PREP:
            return TaskResult.skipped("Campaign battle preparation was already open.")
        if before.screen_type == ScreenType.PNC_CAMPAIGN and not before.entries(ListEntryKind.CAMPAIGN_STAGE):
            return TaskResult.skipped("No eligible campaign stages were visible.")
        if after.screen_type == ScreenType.PNC_BATTLE_PREP:
            return TaskResult.success("Campaign advanced to battle preparation.")
        if before.screen_type == ScreenType.PNC_CAMPAIGN and after.screen_type == ScreenType.PNC_CAMPAIGN_STAGE:
            return TaskResult.replan("Opened campaign stage details.")
        return TaskResult.failure("Campaign did not produce a verified state change.", retryable=True)


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
