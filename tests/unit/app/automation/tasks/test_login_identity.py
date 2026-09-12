"""Login identity."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.login_task import LoginTask
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class LoginIdentityTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves login identity."""

    def test_login_task_verifies_castle_selection_against_pre_observation_roster_snapshot(self) -> None:
        """Accepts a castle-selection state only when the trusted pre-observation snapshot matches."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                self.target_castle,
                CastleIdentity(kingdom="K229", castle_name="Farm", castle_level=4),
            ),
        )
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        before = make_observation(ScreenType.PNC_HOME_CITY)
        after = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(ListEntryKind.CASTLE, title="Main", metadata={"kingdom": "K230", "castle_level": 8}),
                make_entry(ListEntryKind.CASTLE, title="Farm", metadata={"kingdom": "K229", "castle_level": 4}),
            ),
            castle_roster_snapshot=roster,
        )

        result = task.verify(context, before, after)

        self.assertTrue(result.succeeded)
        self.assertIn("trusted cached castle roster", result.message)

    def test_login_task_verifies_lord_info_without_trusted_roster_snapshot(self) -> None:
        """Accepts Lord Info as usable session proof when no cached roster is available."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(ScreenType.PNC_LORD_INFO, current_castle_name="Main"),
        )

        self.assertTrue(result.succeeded)
        self.assertIn("Lord Info", result.message)

    def test_login_task_verifies_manage_char_without_trusted_roster_snapshot(self) -> None:
        """Accepts Manage Char as usable session proof even when the roster cache is missing or stale."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_MORE_MENU),
            make_observation(
                ScreenType.PNC_CASTLE_SELECTION,
                list_entries=(make_entry(ListEntryKind.CASTLE, title="Main", metadata={"kingdom": "K230"}),),
            ),
        )

        self.assertTrue(result.succeeded)
        self.assertIn("Manage Char", result.message)

    def test_login_task_falls_back_to_manage_char_when_snapshot_membership_is_stale(self) -> None:
        """Accepts Manage Char session proof even when a trusted snapshot no longer matches exactly."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(CastleIdentity(kingdom="K230", castle_name="Main"),),
        )
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_MORE_MENU),
            make_observation(
                ScreenType.PNC_CASTLE_SELECTION,
                list_entries=(make_entry(ListEntryKind.CASTLE, title="Renamed Main", metadata={"kingdom": "K230"}),),
                castle_roster_snapshot=roster,
            ),
        )

        self.assertTrue(result.succeeded)
        self.assertIn("Manage Char", result.message)

    def test_login_task_replans_wrong_account_on_recoverable_login_states(self) -> None:
        """Keeps wrong-account login and account-switch states on the task's replan path."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        for screen_type in (ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH):
            with self.subTest(screen_type=screen_type):
                result = task.verify(
                    context,
                    make_observation(screen_type),
                    make_observation(screen_type, current_pnc_account_id="other@example.com"),
                )

                self.assertEqual(result.status.value, "replan")
