"""Profile chat rank routes."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapAction, TapPointAction
from pnc_automation.app.pnc.domain.mail import PlayerProfileRoute, PlayerProfileRouteKind
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class ProfileChatRankRoutesTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves profile chat rank routes."""

    def test_open_player_profile_from_chat_message_uses_player_popup_then_profile_button(self) -> None:
        """Uses one popup-opening increment from chat so the popup origin is re-observed before profile navigation."""

        observation = make_observation(
            ScreenType.PNC_CHAT,
            list_entries=(make_entry(ListEntryKind.CHAT_MESSAGE, title="Enemy Bob", action_point=(170, 70)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.CHAT_MESSAGE,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP))

    def test_open_player_profile_from_might_rank_uses_visible_rank_entry(self) -> None:
        """Uses the visible ranked-player row action point instead of duplicating rank-screen tap logic."""

        observation = make_observation(
            ScreenType.PNC_MIGHT_RANK,
            list_entries=(make_entry(ListEntryKind.RANKED_PLAYER, title="Enemy Bob", action_point=(190, 80)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.MIGHT_RANK,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.player_profile_follow_up())

    def test_open_player_profile_from_might_rank_requires_exact_case_before_tapping(self) -> None:
        """Keeps Might Rank route matching case-sensitive and continues the shared search when casing differs."""

        observation = make_observation(
            ScreenType.PNC_MIGHT_RANK,
            list_entries=(make_entry(ListEntryKind.RANKED_PLAYER, title="LadiesLoveCake", action_point=(190, 80)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.MIGHT_RANK,
                player_name="ladieslovecake",
            ),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "search_might_rank_reset_to_top")

    def test_open_player_profile_from_home_with_might_rank_route_first_opens_alliance_home(self) -> None:
        """Lets the shared route flow acquire alliance home before opening the Might Rank route screen."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_ALLIANCE,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.MIGHT_RANK,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_ALLIANCE)

    def test_open_player_profile_from_alliance_home_with_might_rank_route_opens_rank_screen(self) -> None:
        """Owns Might Rank screen acquisition once the shared route flow reaches alliance home."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_ALLIANCE_HOME,
                visible_ids=(UiElementId.PNC_ALLIANCE_TILE_RANK,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.MIGHT_RANK,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_ALLIANCE_TILE_RANK)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(
                ScreenType.PNC_MIGHT_RANK,
                ScreenType.PNC_ALLIANCE_HOME,
            ),
        )
