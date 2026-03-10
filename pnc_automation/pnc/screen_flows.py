"""Reusable P&C navigation planning built on typed observations."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.config.models import SelectedCastleConfig
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import (
    ActionRequest,
    KeyEventAction,
    LaunchAppAction,
    TapAction,
    TapListEntryAction,
)
from pnc_automation.pnc.observation import ListEntryKind, Observation
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


@dataclass(slots=True)
class ScreenFlowPlanner:
    """Centralizes reusable navigation plans shared across tasks."""

    def ensure_android_home(self, observation: Observation) -> list[ActionRequest]:
        """Plans a transition to Android home when needed."""

        if observation.screen_type == ScreenType.ANDROID_HOME:
            return []
        return [KeyEventAction(key_code="KEYCODE_HOME", reason="return_to_android_home", observe_after=True)]

    def ensure_pnc_foreground(self, observation: Observation) -> list[ActionRequest]:
        """Plans a transition that foregrounds P&C from Android or unknown state."""

        if observation.screen_type not in {ScreenType.ANDROID_HOME, ScreenType.UNKNOWN}:
            return []
        actions: list[ActionRequest] = []
        if observation.screen_type == ScreenType.UNKNOWN:
            actions.extend(self.ensure_android_home(observation))
        actions.append(LaunchAppAction(reason="launch_pnc", observe_after=True))
        return actions

    def close_blocking_popup(self, observation: Observation) -> list[ActionRequest]:
        """Plans one popup dismissal action."""

        if not observation.blocking_popup and observation.screen_type != ScreenType.PNC_POPUP:
            return []
        if observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON):
            return [TapAction(selector_id=UiElementId.PNC_POPUP_CLOSE_BUTTON, reason="close_popup", observe_after=True)]
        return [KeyEventAction(key_code="KEYCODE_BACK", reason="dismiss_popup_with_back", observe_after=True)]

    def return_to_safe_root_screen(self, observation: Observation) -> list[ActionRequest]:
        """Plans a conservative return path to a stable non-popup game root."""

        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            return []
        if observation.screen_type == ScreenType.PNC_WORLD_MAP:
            return [TapAction(selector_id=UiElementId.PNC_WORLD_HOME_NAV, reason="return_to_city", observe_after=True)]
        if observation.screen_type == ScreenType.PNC_POPUP or observation.blocking_popup:
            return self.close_blocking_popup(observation)
        if observation.screen_type in {
            ScreenType.PNC_BAG,
            ScreenType.PNC_QUEST_DAILY,
            ScreenType.PNC_HERO_LIST,
            ScreenType.PNC_HERO_DETAIL_UPGRADE,
            ScreenType.PNC_HERO_DETAIL_ENHANCE,
            ScreenType.PNC_MAIL_LIST,
            ScreenType.PNC_SYSTEM_MESSAGE,
            ScreenType.PNC_ALLIANCE_HOME,
            ScreenType.PNC_ALLIANCE_JOIN,
            ScreenType.PNC_CASH_MALL,
            ScreenType.PNC_GIFT_CENTER,
            ScreenType.PNC_EVENT_CENTER,
            ScreenType.PNC_BUILDING_DETAILS,
            ScreenType.PNC_ACADEMY,
            ScreenType.PNC_RESEARCH_TREE,
            ScreenType.PNC_GATHER_NODE,
            ScreenType.PNC_MARCH_CONFIRM,
            ScreenType.PNC_CAMPAIGN,
            ScreenType.PNC_CAMPAIGN_STAGE,
            ScreenType.PNC_BATTLE_PREP,
        }:
            if observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        reason="navigate_back_to_root",
                        observe_after=True,
                    )
                ]
            return [KeyEventAction(key_code="KEYCODE_BACK", reason="navigate_back_to_root", observe_after=True)]
        raise SelectorResolutionError(
            f"Cannot derive a safe root-screen return path from screen '{observation.screen_type}'.",
            screen_type=observation.screen_type,
        )

    def ensure_home_city(self, observation: Observation) -> list[ActionRequest]:
        """Plans a transition to the home-city root screen."""

        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            return []
        if observation.screen_type == ScreenType.PNC_WORLD_MAP:
            return [TapAction(selector_id=UiElementId.PNC_WORLD_HOME_NAV, reason="world_to_city", observe_after=True)]
        if observation.screen_type in {ScreenType.ANDROID_HOME, ScreenType.UNKNOWN}:
            return self.ensure_pnc_foreground(observation)
        return self.return_to_safe_root_screen(observation)

    def open_world_map(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home city to world map."""

        if observation.screen_type == ScreenType.PNC_WORLD_MAP:
            return []
        actions = self.ensure_home_city(observation)
        actions.append(TapAction(selector_id=UiElementId.PNC_HOME_WORLD_SWITCH, reason="open_world_map", observe_after=True))
        return actions

    def open_academy(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home city to the academy or research tree."""

        if observation.screen_type in {ScreenType.PNC_ACADEMY, ScreenType.PNC_RESEARCH_TREE}:
            return []
        actions = self.ensure_home_city(observation)
        selector = (
            UiElementId.PNC_HOME_RESEARCH_BUTTON
            if observation.has(UiElementId.PNC_HOME_RESEARCH_BUTTON)
            else UiElementId.PNC_HOME_ACADEMY_BUILDING
        )
        actions.append(TapAction(selector_id=selector, reason="open_academy", observe_after=True))
        return actions

    def ensure_correct_castle_selected(
        self,
        observation: Observation,
        selected_castle: SelectedCastleConfig,
    ) -> list[ActionRequest]:
        """Plans selection of the configured castle when it is not already active."""

        if observation.current_castle_name == selected_castle.castle_name:
            return []
        actions: list[ActionRequest] = []
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            actions.append(
                TapAction(
                    selector_id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                    reason="open_castle_selection",
                    observe_after=True,
                )
            )
        elif observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            raise SelectorResolutionError(
                "Castle selection flow requires home city or castle selection screen.",
                screen_type=observation.screen_type,
            )
        actions.append(
            TapListEntryAction(
                entry_kind=ListEntryKind.CASTLE,
                title_text=selected_castle.castle_name,
                use_action_point=True,
                reason="select_configured_castle",
                observe_after=True,
            )
        )
        return actions
