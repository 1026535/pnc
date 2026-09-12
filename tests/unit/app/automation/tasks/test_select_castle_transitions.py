"""Select castle transitions."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.app.automation.tasks.active_castle_resolution import (
    remember_active_castle_identity,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.domain.action_requests import WaitAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class SelectCastleTransitionsTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves select castle transitions."""

    def test_remember_active_castle_identity_prefers_the_exact_lord_info_name_variant(self) -> None:
        """Preserves the exact Lord Info spelling when semantically equivalent roster entries coexist."""

        target_castle = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        exact_variant = CastleIdentity(kingdom="K226", castle_name="please bgentle", castle_level=12)
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                target_castle,
                exact_variant,
            ),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.COLLECT_KINGDOM_CHAT,
            castle_roster_provider=lambda: roster,
        )

        resolved = remember_active_castle_identity(
            context,
            make_observation(ScreenType.PNC_LORD_INFO, current_castle_name="please bgentle"),
        )

        self.assertEqual(resolved, exact_variant)

    def test_select_castle_replans_when_lord_info_name_is_ambiguous_across_kingdoms(self) -> None:
        """Does not accept Lord Info name-only evidence when the cached roster contains duplicate castle names."""

        task = SelectCastleTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                self.target_castle,
                CastleIdentity(kingdom="K999", castle_name="Main", castle_level=9),
            ),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
            castle_roster_provider=lambda: roster,
        )
        ambiguous_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="Main",
        )

        actions = task.plan(context, ambiguous_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), ambiguous_lord_info)

        self.assertTrue(actions)
        self.assertEqual(result.status.value, "replan")
        self.assertIn("ambiguous", result.message)

    def test_select_castle_waits_on_unknown_transition_after_switch(self) -> None:
        """Keeps unknown splash frames on the recoverable settle path after a castle switch."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )

        actions = task.plan(context, make_observation(ScreenType.UNKNOWN))
        result = task.verify(context, make_observation(ScreenType.PNC_LOADING), make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(result.status.value, "replan")

    def test_select_castle_replans_popup_after_switch_for_runner_recovery(self) -> None:
        """Hands post-switch popups back to the runner instead of failing the step outright."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_LOADING),
            make_observation(ScreenType.PNC_POPUP, blocking_popup=True),
        )

        self.assertEqual(result.status.value, "replan")
