"""Reusable P&C navigation planning built on typed observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
    TapPointAction,
    WaitAction,
)
from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.mail import (
    MailRecipientKind,
    MailboxType,
    PlayerProfileRoute,
    PlayerProfileRouteKind,
    SendMailParams,
    mailbox_category_selector_id,
)
from pnc_automation.pnc.observation import (
    DetectedSpatialObject,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
    castle_entry_identity_matches,
    castle_identities_match,
)
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.spatial_navigation import HomeCityNavigator, WorldCoordinate, WorldMapNavigator
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest
from pnc_automation.vision.selectors import ClickOutcome

_PLAYER_PROFILE_ROUTE_SEARCH_STATE_KEY = "player_profile_route_search"
_PLAYER_PROFILE_ROUTE_RESET_STEPS = 5
_PLAYER_PROFILE_ROUTE_SCAN_STEPS = 8


@dataclass(slots=True)
class ScreenFlowPlanner:
    """Centralizes reusable navigation plans shared across tasks."""

    world_map_navigator: WorldMapNavigator = field(default_factory=WorldMapNavigator)
    home_city_navigator: HomeCityNavigator = field(default_factory=HomeCityNavigator)

    def recover_unknown_game_screen(self, observation: Observation, *, reason: str) -> list[ActionRequest]:
        """Returns one conservative in-game recovery increment for an unclassified live screen."""

        if observation.screen_type != ScreenType.UNKNOWN:
            return []
        return [KeyEventAction(key_code="KEYCODE_BACK", reason=reason, observe_after=True)]

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
            return [
                TapAction(
                    selector_id=UiElementId.PNC_WORLD_HOME_NAV,
                    reason="return_to_city",
                    observe_after=True,
                    follow_up_request=ObservationRequest.home_city_follow_up(ScreenType.PNC_WORLD_MAP),
                )
            ]
        if observation.screen_type == ScreenType.PNC_POPUP or observation.blocking_popup:
            return self.close_blocking_popup(observation)
        if observation.screen_type == ScreenType.PNC_MORE_MENU:
            if observation.has(UiElementId.PNC_MORE_SETTINGS) and observation.has(UiElementId.PNC_BOTTOM_NAV_MORE):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_BOTTOM_NAV_MORE,
                        reason="close_more_menu",
                        observe_after=True,
                        follow_up_request=ObservationRequest.home_city_follow_up(ScreenType.PNC_MORE_MENU),
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
                return [
                    KeyEventAction(
                        key_code="KEYCODE_BACK",
                        reason="leave_settings_menu",
                        observe_after=True,
                        follow_up_request=ObservationRequest.home_city_follow_up(ScreenType.PNC_MORE_MENU),
                    )
                ]
        if observation.screen_type in {
            ScreenType.PNC_BAG,
            ScreenType.PNC_QUEST_DAILY,
            ScreenType.PNC_HERO_LIST,
            ScreenType.PNC_HERO_DETAIL_UPGRADE,
            ScreenType.PNC_HERO_DETAIL_ENHANCE,
            ScreenType.PNC_MAIL_HUB,
            ScreenType.PNC_MAILBOX_LIST,
            ScreenType.PNC_MAIL_THREAD,
            ScreenType.PNC_MAIL_COMPOSE_POPUP,
            ScreenType.PNC_ALLIANCE_HOME,
            ScreenType.PNC_ALLIANCE_JOIN,
            ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
            ScreenType.PNC_CASH_MALL,
            ScreenType.PNC_GIFT_CENTER,
            ScreenType.PNC_EVENT_CENTER,
            ScreenType.PNC_BUILDING_DETAILS,
            ScreenType.PNC_LORD_INFO,
            ScreenType.PNC_PLAYER_TERRITORY,
            ScreenType.PNC_PLAYER_PROFILE,
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
            ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_MIGHT_RANK,
        }:
            if observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        reason="navigate_back_to_root",
                        observe_after=True,
                        follow_up_request=ObservationRequest.home_city_follow_up(observation.screen_type),
                    )
                ]
            return [
                KeyEventAction(
                    key_code="KEYCODE_BACK",
                    reason="navigate_back_to_root",
                    observe_after=True,
                    follow_up_request=ObservationRequest.home_city_follow_up(observation.screen_type),
                )
            ]
        raise SelectorResolutionError(
            f"Cannot derive a safe root-screen return path from screen '{observation.screen_type}'.",
            screen_type=observation.screen_type,
        )

    def ensure_home_city(self, observation: Observation) -> list[ActionRequest]:
        """Plans a transition to the home-city root screen."""

        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            return []
        if observation.screen_type == ScreenType.PNC_WORLD_MAP:
            return [
                TapAction(
                    selector_id=UiElementId.PNC_WORLD_HOME_NAV,
                    reason="world_to_city",
                    observe_after=True,
                    follow_up_request=ObservationRequest.home_city_follow_up(ScreenType.PNC_WORLD_MAP),
                )
            ]
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

    def ensure_world_map_ready(self, observation: Observation) -> list[ActionRequest]:
        """Plans entry to world map and fails fast if the resulting world surface lacks a readable viewport."""

        if observation.screen_type != ScreenType.PNC_WORLD_MAP:
            return self.open_world_map(observation)
        self.world_map_navigator.require_surface(observation)
        return []

    def focus_world_coordinate(
        self,
        observation: Observation,
        target: WorldCoordinate,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans one canonical coordinate-driven world-map navigation increment."""

        if observation.screen_type != ScreenType.PNC_WORLD_MAP:
            return self.open_world_map(observation)
        return self.world_map_navigator.plan_focus_coordinate(
            observation,
            target,
            runtime_state=runtime_state,
        )

    def find_visible_world_object(self, observation: Observation, query: SpatialObjectQuery) -> DetectedSpatialObject | None:
        """Returns one visible world-map spatial object matching the semantic query when present."""

        self.world_map_navigator.require_surface(observation)
        return observation.find_spatial_object(query)

    def open_visible_world_object(
        self,
        observation: Observation,
        target: DetectedSpatialObject,
        *,
        reason: str,
        observe_after: bool = True,
    ) -> list[ActionRequest]:
        """Plans one tap against one exact visible world-map spatial object."""

        if observation.screen_type != ScreenType.PNC_WORLD_MAP:
            return self.open_world_map(observation)
        return self.world_map_navigator.tap_visible_object(
            observation,
            target,
            reason=reason,
            observe_after=observe_after,
        )

    def return_home_city_from_world_map(self, observation: Observation) -> list[ActionRequest]:
        """Plans the canonical return path from world map back to home city."""

        if observation.screen_type != ScreenType.PNC_WORLD_MAP:
            return self.ensure_home_city(observation)
        return self.ensure_home_city(observation)

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

    def open_alliance_home(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home-adjacent screens to the alliance home screen."""

        if observation.screen_type == ScreenType.PNC_ALLIANCE_HOME:
            return []
        if observation.screen_type == ScreenType.PNC_ALLIANCE_JOIN:
            raise SelectorResolutionError(
                "Alliance-home navigation cannot proceed while the account is on the join-alliance screen.",
                screen_type=observation.screen_type,
            )
        if observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE):
            return [
                TapAction(
                    selector_id=UiElementId.PNC_BOTTOM_NAV_ALLIANCE,
                    reason="open_alliance_home",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_navigation_follow_up(
                        ScreenType.PNC_ALLIANCE_HOME,
                        ScreenType.PNC_ALLIANCE_JOIN,
                    ),
                )
            ]
        return self.ensure_home_city(observation)

    def open_mail_hub(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation to the shared mail category hub."""

        if observation.screen_type == ScreenType.PNC_MAIL_HUB:
            return []
        if observation.has(UiElementId.PNC_BOTTOM_NAV_MAIL):
            return [
                TapAction(
                    selector_id=UiElementId.PNC_BOTTOM_NAV_MAIL,
                    reason="open_mail_hub",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_navigation_follow_up(
                        ScreenType.PNC_MAIL_HUB,
                        ScreenType.PNC_MAILBOX_LIST,
                    ),
                )
            ]
        return self.ensure_home_city(observation)

    def open_mailbox(self, observation: Observation, mailbox: MailboxType) -> list[ActionRequest]:
        """Plans navigation from the mail hub into one specific mailbox list."""

        if observation.screen_type == ScreenType.PNC_MAILBOX_LIST and observation.mailbox_type == mailbox:
            return []
        if observation.screen_type == ScreenType.PNC_MAILBOX_LIST and observation.mailbox_type is not None:
            return [
                KeyEventAction(
                    key_code="KEYCODE_BACK",
                    reason="return_to_mail_hub",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB),
                )
            ]
        if observation.screen_type != ScreenType.PNC_MAIL_HUB:
            return self.open_mail_hub(observation)
        return [
            TapAction(
                selector_id=mailbox_category_selector_id(mailbox),
                reason=f"open_{mailbox.value}_mailbox",
                observe_after=True,
                follow_up_request=ObservationRequest.mail_navigation_follow_up(
                    ScreenType.PNC_MAILBOX_LIST,
                    ScreenType.PNC_MAIL_HUB,
                ),
            )
        ]

    def open_alliance_member_list(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home- or alliance-adjacent screens to the alliance member list."""

        if observation.screen_type == ScreenType.PNC_ALLIANCE_MEMBER_LIST:
            return []
        if observation.screen_type != ScreenType.PNC_ALLIANCE_HOME:
            return self.open_alliance_home(observation)
        return [
            TapAction(
                selector_id=UiElementId.PNC_ALLIANCE_TILE_MEMBER,
                reason="open_alliance_member_list",
                observe_after=True,
                follow_up_request=ObservationRequest.mail_navigation_follow_up(
                    ScreenType.PNC_ALLIANCE_MEMBER_LIST,
                    ScreenType.PNC_ALLIANCE_HOME,
                ),
            )
        ]

    def open_might_rank(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home- or alliance-adjacent screens to the alliance Might Rank screen."""

        if observation.screen_type == ScreenType.PNC_MIGHT_RANK:
            return []
        if observation.screen_type != ScreenType.PNC_ALLIANCE_HOME:
            return self.open_alliance_home(observation)
        return [
            TapAction(
                selector_id=UiElementId.PNC_ALLIANCE_TILE_RANK,
                reason="open_might_rank",
                observe_after=True,
                follow_up_request=ObservationRequest.mail_navigation_follow_up(
                    ScreenType.PNC_MIGHT_RANK,
                    ScreenType.PNC_ALLIANCE_HOME,
                ),
            )
        ]

    def open_player_profile(
        self,
        observation: Observation,
        route: PlayerProfileRoute,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans exactly one remote-profile increment, including bounded shared list-search when configured."""

        if observation.screen_type == ScreenType.PNC_PLAYER_PROFILE:
            _clear_player_profile_route_search_state(runtime_state)
            return []
        if route.kind == PlayerProfileRouteKind.PLAYER_TERRITORY:
            _clear_player_profile_route_search_state(runtime_state)
            if observation.screen_type != ScreenType.PNC_PLAYER_TERRITORY:
                raise SelectorResolutionError(
                    "The player_territory profile route requires the Player Territory screen to already be open.",
                    screen_type=observation.screen_type,
                    route_kind=route.kind.value,
                )
            return [
                TapAction(
                    selector_id=UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                    reason="open_player_profile_from_territory",
                    observe_after=True,
                    follow_up_request=ObservationRequest.player_profile_follow_up(),
                )
            ]
        if route.kind == PlayerProfileRouteKind.CHAT_MESSAGE:
            _clear_player_profile_route_search_state(runtime_state)
            if observation.screen_type == ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP:
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON,
                        reason="open_player_profile_from_chat_popup",
                        observe_after=True,
                        follow_up_request=ObservationRequest.player_profile_follow_up(),
                    )
                ]
            if observation.screen_type != ScreenType.PNC_CHAT:
                return self.open_chat(observation)
            entry = _require_named_entry(observation, kind=ListEntryKind.CHAT_MESSAGE, title_text=route.player_name)
            target = entry.action_point if entry.action_point is not None else entry.bounds.center()
            return [
                TapPointAction(
                    x=target[0],
                    y=target[1],
                    reason="open_chat_player_actions",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP),
                ),
            ]
        if route.kind == PlayerProfileRouteKind.ALLIANCE_MEMBER:
            if observation.screen_type == ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP:
                _clear_player_profile_route_search_state(runtime_state)
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON,
                        reason="open_player_profile_from_member_manage",
                        observe_after=True,
                        follow_up_request=ObservationRequest.player_profile_follow_up(),
                    )
                ]
            if observation.screen_type != ScreenType.PNC_ALLIANCE_MEMBER_LIST:
                _clear_player_profile_route_search_state(runtime_state)
                return self.open_alliance_member_list(observation)
            entry = _find_named_entry(observation, kind=ListEntryKind.ALLIANCE_MEMBER, title_text=route.player_name)
            if entry is None:
                return _plan_player_profile_route_search(
                    observation,
                    route=route,
                    runtime_state=runtime_state,
                )
            _clear_player_profile_route_search_state(runtime_state)
            target = entry.action_point if entry.action_point is not None else entry.bounds.center()
            return [
                TapPointAction(
                    x=target[0],
                    y=target[1],
                    reason="open_alliance_member_manage_popup",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP),
                ),
            ]
        if route.kind == PlayerProfileRouteKind.MIGHT_RANK:
            if observation.screen_type != ScreenType.PNC_MIGHT_RANK:
                _clear_player_profile_route_search_state(runtime_state)
                return self.open_might_rank(observation)
            entry = _find_named_entry(observation, kind=ListEntryKind.RANKED_PLAYER, title_text=route.player_name)
            if entry is None:
                return _plan_player_profile_route_search(
                    observation,
                    route=route,
                    runtime_state=runtime_state,
                )
            _clear_player_profile_route_search_state(runtime_state)
            target = entry.action_point if entry.action_point is not None else entry.bounds.center()
            return [
                TapPointAction(
                    x=target[0],
                    y=target[1],
                    reason="open_player_profile_from_might_rank",
                    observe_after=True,
                    follow_up_request=ObservationRequest.player_profile_follow_up(),
                )
            ]
        raise SelectorResolutionError(
            "Unsupported player-profile route kind.",
            route_kind=route.kind.value,
        )

    def open_mail_compose(
        self,
        observation: Observation,
        params: SendMailParams,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans exactly one compose-entry increment from the currently observed origin."""

        if observation.screen_type == ScreenType.PNC_MAIL_COMPOSE_POPUP:
            return []
        if params.recipient_kind == MailRecipientKind.ALLIANCE:
            if observation.screen_type != ScreenType.PNC_ALLIANCE_HOME:
                return self.open_alliance_home(observation)
            return [
                TapAction(
                    selector_id=UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL,
                    reason="open_alliance_mail_compose",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_compose_follow_up(),
                )
            ]
        if params.player_name is not None:
            if observation.screen_type != ScreenType.PNC_MAILBOX_LIST or observation.mailbox_type != MailboxType.PLAYER:
                return self.open_mailbox(observation, MailboxType.PLAYER)
            return [
                TapAction(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_BUTTON,
                    reason="open_player_mail_compose",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_compose_follow_up(),
                ),
            ]
        if params.profile_route is None:
            raise SelectorResolutionError("Player mail compose requires either player_name or profile_route.")
        if observation.screen_type != ScreenType.PNC_PLAYER_PROFILE:
            return self.open_player_profile(
                observation,
                params.profile_route,
                runtime_state=runtime_state,
            )
        return [
            TapAction(
                selector_id=UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON,
                reason="open_profile_mail_compose",
                observe_after=True,
                follow_up_request=ObservationRequest.mail_compose_follow_up(),
            )
        ]

    def send_mail(self, observation: Observation, params: SendMailParams) -> list[ActionRequest]:
        """Plans subject/body entry plus send from an already-open compose popup."""

        if observation.screen_type != ScreenType.PNC_MAIL_COMPOSE_POPUP:
            raise SelectorResolutionError(
                "send_mail requires the compose popup to already be open.",
                screen_type=observation.screen_type,
            )
        return [
            InputTextAction(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,
                text=params.subject,
                replace_existing=True,
                reason="type_mail_subject",
            ),
            InputTextAction(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
                text=params.body,
                replace_existing=True,
                reason="type_mail_body",
            ),
            TapAction(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON,
                reason="send_mail",
                observe_after=True,
                follow_up_request=ObservationRequest.mail_navigation_follow_up(
                    ScreenType.PNC_MAILBOX_LIST,
                    ScreenType.PNC_MAIL_HUB,
                    ScreenType.PNC_ALLIANCE_HOME,
                    ScreenType.PNC_PLAYER_PROFILE,
                ),
            ),
        ]

    def send_chat_message(
        self,
        observation: Observation,
        *,
        message: str,
        channel: ChatChannel,
    ) -> list[ActionRequest]:
        """Plans only the actions valid for the currently observed chat-send origin."""

        if message.strip() == "":
            raise ValueError("Chat messages must contain at least one non-whitespace character.")
        if observation.screen_type != ScreenType.PNC_CHAT:
            return self.open_chat(observation)
        if observation.active_chat_channel != channel:
            return [
                SelectChatChannelAction(
                    channel=channel,
                    reason=f"select_chat_channel_{channel.value}",
                    observe_after=True,
                    follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
                    timing_profile=ActionTimingProfile.CHAT,
                )
            ]
        return [
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
        ]

    def _chat_navigation_outcome(self) -> ClickOutcome:
        """Returns the reviewed destination used by the shared chat-opening flow."""

        return ClickOutcome(target_screen=ScreenType.PNC_CHAT)

    def open_academy(self, observation: Observation) -> list[ActionRequest]:
        """Plans navigation from home city to the academy or research tree."""

        if observation.screen_type in {ScreenType.PNC_ACADEMY, ScreenType.PNC_RESEARCH_TREE}:
            return []
        if observation.screen_type != ScreenType.PNC_HOME_CITY:
            return self.ensure_home_city(observation)
        if observation.has(UiElementId.PNC_HOME_RESEARCH_BUTTON):
            return [TapAction(selector_id=UiElementId.PNC_HOME_RESEARCH_BUTTON, reason="open_academy", observe_after=True)]
        academy_query = SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_BUILDING,
            metadata_key="category",
            metadata_value="academy",
        )
        academy = observation.find_spatial_object(academy_query)
        if academy is not None:
            return self.home_city_navigator.tap_visible_object(
                observation,
                academy,
                reason="open_academy",
            )
        return self.home_city_navigator.plan_focus_object(observation, academy_query)

    def open_visible_home_city_object(
        self,
        observation: Observation,
        target: DetectedSpatialObject,
        *,
        reason: str,
        runtime_state: dict[str, Any] | None = None,
        observe_after: bool = True,
    ) -> list[ActionRequest]:
        """Plans one tap against one exact visible home-city spatial object."""

        if observation.screen_type != ScreenType.PNC_HOME_CITY:
            return self.ensure_home_city(observation)
        return self.home_city_navigator.tap_visible_object(
            observation,
            target,
            reason=reason,
            runtime_state=runtime_state,
            observe_after=observe_after,
        )

    def focus_home_city_object(
        self,
        observation: Observation,
        query: SpatialObjectQuery,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans one camera-relative home-city navigation increment toward the requested scene object."""

        if observation.screen_type != ScreenType.PNC_HOME_CITY:
            return self.ensure_home_city(observation)
        return self.home_city_navigator.plan_focus_object(
            observation,
            query,
            runtime_state=runtime_state,
        )

    def open_home_city_object(
        self,
        observation: Observation,
        query: SpatialObjectQuery,
        *,
        reason: str,
        runtime_state: dict[str, Any] | None = None,
        observe_after: bool = True,
    ) -> list[ActionRequest]:
        """Plans one home-city camera step or a tap when the requested object is already visible."""

        if observation.screen_type != ScreenType.PNC_HOME_CITY:
            return self.ensure_home_city(observation)
        target = observation.find_spatial_object(query)
        if target is not None:
            return self.home_city_navigator.tap_visible_object(
                observation,
                target,
                reason=reason,
                runtime_state=runtime_state,
                observe_after=observe_after,
            )
        return self.home_city_navigator.plan_focus_object(
            observation,
            query,
            runtime_state=runtime_state,
        )

    def open_home_city_empty_slot(
        self,
        observation: Observation,
        query: SpatialObjectQuery,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans one bounded empty-slot tap or home-city camera step for the requested build slot."""

        if query.kind != SpatialObjectKind.HOME_EMPTY_SLOT:
            raise SelectorResolutionError(
                "open_home_city_empty_slot requires a HOME_EMPTY_SLOT spatial-object query.",
                object_kind=query.kind,
            )
        return self.open_home_city_object(
            observation,
            query,
            reason="open_home_city_empty_slot",
            runtime_state=runtime_state,
        )

    def ensure_correct_castle_selected(
        self,
        observation: Observation,
        target_castle: CastleIdentity,
        castle_roster: PncAccountCastleRosterConfig | None = None,
    ) -> list[ActionRequest]:
        """Plans selection of the requested castle when it is not already active."""

        if observation.matches_current_castle(target_castle, roster=castle_roster):
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


def _require_named_entry(
    observation: Observation,
    *,
    kind: ListEntryKind,
    title_text: str | None,
) -> DetectedListEntry:
    """Returns one required named dynamic entry or fails fast when it is not visible."""

    entry = _find_named_entry(observation, kind=kind, title_text=title_text)
    if entry is not None:
        return entry
    raise SelectorResolutionError(
        "The requested target row is not currently visible for the selected route.",
        entry_kind=kind,
        title_text=title_text,
        screen_type=observation.screen_type,
    )


def _find_named_entry(
    observation: Observation,
    *,
    kind: ListEntryKind,
    title_text: str | None,
) -> DetectedListEntry | None:
    """Returns one visible named dynamic entry when it is currently present."""

    if title_text is None:
        raise SelectorResolutionError(
            "This route requires a visible named target entry.",
            entry_kind=kind,
            screen_type=observation.screen_type,
        )
    for entry in observation.entries(kind):
        if entry.title_text == title_text:
            return entry
    return None


def _plan_player_profile_route_search(
    observation: Observation,
    *,
    route: PlayerProfileRoute,
    runtime_state: dict[str, Any] | None,
) -> list[ActionRequest]:
    """Returns the next one-swipe search increment for list-backed profile routes or fails fast without state."""

    if runtime_state is None or route.player_name is None:
        _raise_missing_route_target(observation, route)
    state = _require_player_profile_route_search_state(
        runtime_state,
        route_kind=route.kind,
        player_name=route.player_name,
    )
    phase = state["phase"]
    steps_completed = state["steps_completed"]
    if phase == "reset_to_top" and steps_completed >= _PLAYER_PROFILE_ROUTE_RESET_STEPS:
        state["phase"] = "scan_forward"
        state["steps_completed"] = 0
        phase = "scan_forward"
        steps_completed = 0
    if phase == "scan_forward" and steps_completed >= _PLAYER_PROFILE_ROUTE_SCAN_STEPS:
        _clear_player_profile_route_search_state(runtime_state)
        raise SelectorResolutionError(
            "The requested target row could not be found after searching the selected profile-route list.",
            route_kind=route.kind.value,
            player_name=route.player_name,
            screen_type=observation.screen_type,
        )
    state["steps_completed"] = steps_completed + 1
    return [_make_player_profile_route_search_swipe(observation, route_kind=route.kind, phase=phase)]


def _require_player_profile_route_search_state(
    runtime_state: dict[str, Any],
    *,
    route_kind: PlayerProfileRouteKind,
    player_name: str,
) -> dict[str, object]:
    """Returns the active list-search state for one route target, resetting it when the target changed."""

    state = runtime_state.get(_PLAYER_PROFILE_ROUTE_SEARCH_STATE_KEY)
    if (
        isinstance(state, dict)
        and state.get("route_kind") == route_kind.value
        and state.get("player_name") == player_name
        and state.get("phase") in {"reset_to_top", "scan_forward"}
        and isinstance(state.get("steps_completed"), int)
    ):
        return state
    new_state: dict[str, object] = {
        "route_kind": route_kind.value,
        "player_name": player_name,
        "phase": "reset_to_top",
        "steps_completed": 0,
    }
    runtime_state[_PLAYER_PROFILE_ROUTE_SEARCH_STATE_KEY] = new_state
    return new_state


def _clear_player_profile_route_search_state(runtime_state: dict[str, Any] | None) -> None:
    """Clears any active list-search state once the shared route flow no longer needs it."""

    if runtime_state is None:
        return
    runtime_state.pop(_PLAYER_PROFILE_ROUTE_SEARCH_STATE_KEY, None)


def _make_player_profile_route_search_swipe(
    observation: Observation,
    *,
    route_kind: PlayerProfileRouteKind,
    phase: str,
) -> SwipeAction:
    """Builds the calibrated one-swipe search increment for alliance-member and rank route lists."""

    reason = f"search_{route_kind.value}_{phase}"
    if phase == "reset_to_top":
        return SwipeAction(
            direction="down",
            distance_ratio=0.72,
            reason=reason,
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(observation.screen_type),
            start_x_ratio=0.5,
            start_y_ratio=0.40625,
            end_x_ratio=0.5,
            end_y_ratio=0.78125,
            duration_ms=500,
        )
    if phase == "scan_forward":
        return SwipeAction(
            direction="up",
            distance_ratio=0.72,
            reason=reason,
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(observation.screen_type),
            start_x_ratio=0.5,
            start_y_ratio=0.78125,
            end_x_ratio=0.5,
            end_y_ratio=0.28125,
            duration_ms=500,
        )
    raise SelectorResolutionError("Unsupported profile-route search phase.", phase=phase, screen_type=observation.screen_type)


def _raise_missing_route_target(observation: Observation, route: PlayerProfileRoute) -> None:
    """Raises the canonical fail-fast error when a caller did not opt into shared route searching."""

    raise SelectorResolutionError(
        "The requested target row is not currently visible for the selected route.",
        route_kind=route.kind.value,
        title_text=route.player_name,
        screen_type=observation.screen_type,
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
