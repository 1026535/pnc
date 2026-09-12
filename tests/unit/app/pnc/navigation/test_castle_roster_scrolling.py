"""Castle roster scrolling."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.castles import (
    CastleIdentity,
    CastleRosterOrdering,
    PncAccountCastleRosterConfig,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeAction,
    TapListEntryAction,
    WaitAction,
)
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class CastleRosterScrollingTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves castle roster scrolling."""

    def test_ensure_correct_castle_selected_scrolls_toward_target_using_cached_roster_order(self) -> None:
        """Plans a deterministic swipe when the target castle is outside the visible roster window."""

        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4),
                self.target_castle,
            ),
            ordering=CastleRosterOrdering.FULL_SCAN,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(ListEntryKind.CASTLE, title="Alpha", metadata={"kingdom": "K226", "castle_level": 3}),
                make_entry(ListEntryKind.CASTLE, title="Bravo", metadata={"kingdom": "K227", "castle_level": 4}),
            ),
        )

        actions = self.flows.ensure_correct_castle_selected(observation, self.target_castle, roster)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")

    def test_ensure_correct_castle_selected_rejects_untrusted_cached_roster_order(self) -> None:
        """Fails fast instead of guessing a scroll direction from a partial cached roster."""

        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                self.target_castle,
            ),
            ordering=CastleRosterOrdering.UNKNOWN,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(make_entry(ListEntryKind.CASTLE, title="Alpha", metadata={"kingdom": "K226", "castle_level": 3}),),
        )

        with self.assertRaises(SelectorResolutionError):
            self.flows.ensure_correct_castle_selected(observation, self.target_castle, roster)

    def test_ensure_correct_castle_selected_waits_after_tapping_visible_target(self) -> None:
        """Plans a post-tap stabilization wait so live castle switching can pass through loading safely."""

        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="Main",
                    metadata={"kingdom": "K230", "castle_level": 8},
                ),
            ),
        )

        actions = self.flows.ensure_correct_castle_selected(observation, self.target_castle, None)

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapListEntryAction)
        self.assertIsInstance(actions[1], WaitAction)
        self.assertTrue(actions[1].observe_after)
