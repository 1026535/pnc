"""Reusable P&C navigation planning built on typed observations."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.config.models import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import (
    ActionRequest,
    ActionTimingProfile,
    InputTextAction,
    KeyEventAction,
    LaunchAppAction,
    SelectChatChannelAction,
    SwipeAction,
    TapAction,
    TapListEntryAction,
    WaitAction,
)
from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.observation import (
    ListEntryKind,
    Observation,
    castle_entry_identity_matches,
    castle_identities_match,
)
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest
from pnc_automation.vision.selectors import ClickOutcome


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
        if observation.screen_type == ScreenType.PNC_MORE_MENU:
            if observation.has(UiElementId.PNC_MORE_SETTINGS) and observation.has(UiElementId.PNC_BOTTOM_NAV_MORE):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_BOTTOM_NAV_MORE,
                        reason="close_more_menu",
                        observe_after=True,
                    )
                ]
            if observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        reason="leave_more_submenu",
                        observe_after=True,
                    )
                ]
            if observation.has(UiElementId.PNC_MORE_MANAGE_CHAR):
                return [KeyEventAction(key_code="KEYCODE_BACK", reason="leave_settings_menu", observe_after=True)]
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
            ScreenType.PNC_LORD_INFO,
            ScreenType.PNC_VIP,
            ScreenType.PNC_IMPROVE_MIGHT,
            ScreenType.PNC_ACADEMY,
            ScreenType.PNC_RESEARCH_TREE,
            ScreenType.PNC_DAILY_TO_DO,
            ScreenType.PNC_GATHER_NODE,
            ScreenType.PNC_MARCH_CONFIRM,
            ScreenType.PNC_CAMPAIGN,
            ScreenType.PNC_CAMPAIGN_STAGE,
            ScreenType.PNC_BATTLE_PREP,
            ScreenType.PNC_CHAT,
            ScreenType.PNC_CASTLE_SELECTION,
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

    def open_more_menu(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home city to the More-menu overlay."""

        if observation.screen_type == ScreenType.PNC_MORE_MENU:
            return []
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            return [TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_MORE, reason="open_more_menu", observe_after=True)]
        raise SelectorResolutionError(
            "Opening the More menu requires the home city or the More-menu overlay.",
            screen_type=observation.screen_type,
        )

    def open_lord_info(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home-adjacent screens to the Lord Info profile screen."""

        if observation.screen_type == ScreenType.PNC_LORD_INFO:
            return []
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            if not observation.has(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT):
                raise SelectorResolutionError(
                    "Home city is visible but the Lord Info shortcut is not available.",
                    screen_type=observation.screen_type,
                )
            return [
                TapAction(
                    selector_id=UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,
                    reason="open_lord_info",
                    observe_after=True,
                )
            ]
        if observation.screen_type != ScreenType.PNC_MORE_MENU:
            raise SelectorResolutionError(
                "Lord Info navigation requires home city, the More overlay, or the Lord Info screen itself.",
                screen_type=observation.screen_type,
            )
        if observation.has(UiElementId.PNC_MORE_SETTINGS):
            return [
                TapAction(
                    selector_id=UiElementId.PNC_BOTTOM_NAV_MORE,
                    reason="close_more_menu",
                    observe_after=True,
                ),
                TapAction(
                    selector_id=UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,
                    reason="open_lord_info",
                    observe_after=True,
                ),
            ]
        if observation.has(UiElementId.PNC_MORE_MANAGE_CHAR):
            return [
                KeyEventAction(key_code="KEYCODE_BACK", reason="leave_settings_menu", observe_after=True),
                TapAction(
                    selector_id=UiElementId.PNC_BOTTOM_NAV_MORE,
                    reason="close_more_menu",
                    observe_after=True,
                ),
                TapAction(
                    selector_id=UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,
                    reason="open_lord_info",
                    observe_after=True,
                ),
            ]
        raise SelectorResolutionError(
            "More-menu navigation cannot locate a safe path back to the home-city Lord Info shortcut.",
            screen_type=observation.screen_type,
        )

    def open_castle_selection(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home-adjacent screens to the Manage Char roster."""

        if observation.screen_type == ScreenType.PNC_CASTLE_SELECTION:
            return []
        if observation.screen_type == ScreenType.PNC_MORE_MENU:
            if observation.has(UiElementId.PNC_MORE_MANAGE_CHAR):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_MORE_MANAGE_CHAR,
                        reason="open_castle_selection",
                        observe_after=True,
                    )
                ]
            if observation.has(UiElementId.PNC_MORE_SETTINGS):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_MORE_SETTINGS,
                        reason="open_settings_menu",
                        observe_after=True,
                    ),
                    TapAction(
                        selector_id=UiElementId.PNC_MORE_MANAGE_CHAR,
                        reason="open_castle_selection",
                        observe_after=True,
                    ),
                ]
            raise SelectorResolutionError(
                "More menu is open but neither Settings nor Manage Char is visible.",
                screen_type=observation.screen_type,
            )
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            if not observation.has(UiElementId.PNC_BOTTOM_NAV_MORE):
                raise SelectorResolutionError(
                    "Home city is visible but the More navigation button is not available.",
                    screen_type=observation.screen_type,
                )
            return [
                TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_MORE, reason="open_more_menu", observe_after=True),
                TapAction(selector_id=UiElementId.PNC_MORE_SETTINGS, reason="open_settings_menu", observe_after=True),
                TapAction(selector_id=UiElementId.PNC_MORE_MANAGE_CHAR, reason="open_castle_selection", observe_after=True),
            ]
        if observation.screen_type in {
            ScreenType.PNC_LORD_INFO,
            ScreenType.PNC_VIP,
            ScreenType.PNC_IMPROVE_MIGHT,
        }:
            return self.return_to_safe_root_screen(observation) + [
                TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_MORE, reason="open_more_menu", observe_after=True),
                TapAction(selector_id=UiElementId.PNC_MORE_SETTINGS, reason="open_settings_menu", observe_after=True),
                TapAction(selector_id=UiElementId.PNC_MORE_MANAGE_CHAR, reason="open_castle_selection", observe_after=True),
            ]
        raise SelectorResolutionError(
            "Castle selection flow requires home city, the More menu, or the Manage Char roster.",
            screen_type=observation.screen_type,
        )

    def open_world_map(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home city to world map."""

        if observation.screen_type == ScreenType.PNC_WORLD_MAP:
            return []
        actions = self.ensure_home_city(observation)
        actions.append(TapAction(selector_id=UiElementId.PNC_HOME_WORLD_SWITCH, reason="open_world_map", observe_after=True))
        return actions

    def open_chat(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home- or world-adjacent screens to the shared chat overlay."""

        if observation.screen_type == ScreenType.PNC_CHAT:
            return []
        if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP}:
            return [
                TapAction(
                    selector_id=UiElementId.PNC_CHAT_SHORTCUT,
                    reason="open_chat",
                    observe_after=True,
                    follow_up_request=ObservationRequest.navigation_follow_up(
                        (self._chat_navigation_outcome(),)
                    ),
                )
            ]
        actions = self.ensure_home_city(observation)
        actions.append(
            TapAction(
                selector_id=UiElementId.PNC_CHAT_SHORTCUT,
                reason="open_chat",
                observe_after=True,
                follow_up_request=ObservationRequest.navigation_follow_up((self._chat_navigation_outcome(),)),
            )
        )
        return actions

    def send_chat_message(
        self,
        observation: Observation,
        *,
        message: str,
        channel: ChatChannel,
    ) -> list[ActionRequest]:
        """Plans chat opening, channel selection, draft entry, and send in one canonical helper."""

        if message.strip() == "":
            raise ValueError("Chat messages must contain at least one non-whitespace character.")
        actions = self.open_chat(observation)
        actions.extend(
            (
                SelectChatChannelAction(
                    channel=channel,
                    reason=f"select_chat_channel_{channel.value}",
                    observe_after=True,
                    follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
                    timing_profile=ActionTimingProfile.CHAT,
                ),
                InputTextAction(
                    selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                    text=message,
                    reason="type_chat_message",
                    replace_existing=True,
                    timing_profile=ActionTimingProfile.CHAT,
                ),
                TapAction(
                    selector_id=UiElementId.PNC_CHAT_SEND_BUTTON,
                    reason="send_chat_message",
                    observe_after=True,
                    follow_up_request=ObservationRequest.chat_send_follow_up(),
                    timing_profile=ActionTimingProfile.CHAT,
                ),
            )
        )
        return actions

    def _chat_navigation_outcome(self) -> ClickOutcome:
        """Returns the reviewed destination used by the shared chat-opening flow."""

        return ClickOutcome(target_screen=ScreenType.PNC_CHAT)

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
        target_castle: CastleIdentity,
        castle_roster: PncAccountCastleRosterConfig | None = None,
    ) -> list[ActionRequest]:
        """Plans selection of the requested castle when it is not already active."""

        if observation.matches_current_castle(target_castle):
            return []
        selected_entry = observation.find_castle_entry(target_castle)
        if selected_entry is not None and selected_entry.selected:
            return []
        actions: list[ActionRequest] = []
        if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}:
            return self.open_castle_selection(observation)
        elif observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            raise SelectorResolutionError(
                "Castle selection flow requires home city or castle selection screen.",
                screen_type=observation.screen_type,
            )
        if selected_entry is not None:
            actions.extend(
                (
                    TapListEntryAction(
                        entry_kind=ListEntryKind.CASTLE,
                        title_text=target_castle.castle_name,
                        metadata_key="kingdom",
                        metadata_value=target_castle.kingdom,
                        use_action_point=True,
                        reason="select_target_castle",
                    ),
                    WaitAction(
                        milliseconds=1800,
                        reason="wait_for_castle_switch_transition",
                        observe_after=True,
                    ),
                )
            )
            return actions
        actions.append(
            _plan_castle_roster_scroll(
                observation=observation,
                target_castle=target_castle,
                castle_roster=castle_roster,
            )
        )
        return actions


def _plan_castle_roster_scroll(
    *,
    observation: Observation,
    target_castle: CastleIdentity,
    castle_roster: PncAccountCastleRosterConfig | None,
) -> ActionRequest:
    """Plans one roster scroll toward the requested castle when it is currently off-screen."""

    visible_entries = observation.entries(ListEntryKind.CASTLE)
    if not visible_entries:
        raise SelectorResolutionError(
            "Castle-selection scrolling requires at least one visible castle entry.",
            screen_type=observation.screen_type,
        )
    if castle_roster is None:
        raise SelectorResolutionError(
            "Castle-selection scrolling requires a cached roster ordering for off-screen targets.",
            castle_name=target_castle.castle_name,
            kingdom=target_castle.kingdom,
        )
    if not castle_roster.has_trusted_ordering:
        raise SelectorResolutionError(
            "Castle-selection scrolling requires a full-scan roster ordering for off-screen targets; run refresh_castle_roster first.",
            castle_name=target_castle.castle_name,
            kingdom=target_castle.kingdom,
        )

    target_index = _find_castle_index(castle_roster.castles, target_castle)
    if target_index is None:
        raise SelectorResolutionError(
            "Target castle is missing from the cached roster ordering.",
            castle_name=target_castle.castle_name,
            kingdom=target_castle.kingdom,
        )

    visible_indexes = [
        index
        for index, castle in enumerate(castle_roster.castles)
        if any(castle_entry_identity_matches(entry, castle) for entry in visible_entries)
    ]
    if not visible_indexes:
        raise SelectorResolutionError(
            "Visible castle rows do not match the cached roster ordering.",
            castle_name=target_castle.castle_name,
            kingdom=target_castle.kingdom,
        )
    if target_index < min(visible_indexes):
        return SwipeAction(
            direction="down",
            distance_ratio=0.55,
            duration_ms=350,
            reason="scroll_castle_roster_toward_target",
            observe_after=True,
        )
    if target_index > max(visible_indexes):
        return SwipeAction(
            direction="up",
            distance_ratio=0.55,
            duration_ms=350,
            reason="scroll_castle_roster_toward_target",
            observe_after=True,
        )
    raise SelectorResolutionError(
        "Target castle should be visible but could not be resolved in the current roster view.",
        castle_name=target_castle.castle_name,
        kingdom=target_castle.kingdom,
    )


def _find_castle_index(
    castles: tuple[CastleIdentity, ...],
    target: CastleIdentity,
) -> int | None:
    """Returns the index of one castle identity inside the cached roster ordering."""

    for index, castle in enumerate(castles):
        if castle_identities_match(castle, target):
            return index
    return None
