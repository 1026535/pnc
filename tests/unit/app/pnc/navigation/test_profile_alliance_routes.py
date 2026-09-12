"""Profile alliance routes."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import (
    KeyEventAction,
    SwipeAction,
    TapAction,
    TapPointAction,
)
from pnc_automation.app.pnc.domain.mail import PlayerProfileRoute, PlayerProfileRouteKind
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class ProfileAllianceRoutesTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves profile alliance routes."""

    def test_open_player_profile_from_alliance_member_uses_manage_then_personal_info(self) -> None:
        """Uses one manage-popup increment from the member list so the popup origin can be re-observed."""

        observation = make_observation(
            ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            list_entries=(make_entry(ListEntryKind.ALLIANCE_MEMBER, title="Enemy Bob", action_point=(170, 70)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP))

    def test_open_player_profile_from_alliance_member_requires_exact_case_before_tapping(self) -> None:
        """Keeps alliance-member route matching case-sensitive and continues the shared search when casing differs."""

        observation = make_observation(
            ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            list_entries=(make_entry(ListEntryKind.ALLIANCE_MEMBER, title="LadiesLoveCake", action_point=(170, 70)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="ladieslovecake",
            ),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "search_alliance_member_reset_to_top")

    def test_open_player_profile_from_home_with_chat_route_first_opens_chat(self) -> None:
        """Lets the shared route flow acquire chat from home instead of requiring caller-side setup."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.CHAT_MESSAGE,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_SHORTCUT)

    def test_open_player_profile_from_chat_popup_taps_profile_button(self) -> None:
        """Continues the chat-message route from its intermediate popup without restarting navigation."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP,
                visible_ids=(UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.CHAT_MESSAGE,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.player_profile_follow_up())

    def test_open_player_profile_from_home_with_alliance_member_route_first_opens_alliance_home(self) -> None:
        """Lets the shared route flow acquire alliance navigation from home before member-list entry."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_ALLIANCE,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_ALLIANCE)

    def test_open_alliance_home_from_unknown_only_uses_in_game_recovery_first(self) -> None:
        """Keeps alliance-home navigation incremental when starting from an unknown screen."""

        actions = self.flows.open_alliance_home(make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_open_alliance_home_uses_visible_bottom_nav_from_world_map(self) -> None:
        """Uses the visible Alliance bottom nav directly when world-adjacent screens already expose it."""

        actions = self.flows.open_alliance_home(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_ALLIANCE,),
            )
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_ALLIANCE)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(
                ScreenType.PNC_ALLIANCE_HOME,
                ScreenType.PNC_ALLIANCE_JOIN,
            ),
        )

    def test_open_player_profile_from_alliance_home_with_alliance_member_route_opens_member_list(self) -> None:
        """Owns alliance-member list acquisition once the shared route flow is already on alliance home."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_ALLIANCE_HOME,
                visible_ids=(UiElementId.PNC_ALLIANCE_TILE_MEMBER,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_ALLIANCE_TILE_MEMBER)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(
                ScreenType.PNC_ALLIANCE_MEMBER_LIST,
                ScreenType.PNC_ALLIANCE_HOME,
            ),
        )

    def test_open_player_profile_from_member_manage_popup_taps_personal_info(self) -> None:
        """Continues the alliance-member route from its intermediate manage popup without backing out."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
                visible_ids=(UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.player_profile_follow_up())
