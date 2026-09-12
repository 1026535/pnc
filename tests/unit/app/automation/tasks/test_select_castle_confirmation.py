"""Select castle confirmation."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.domain.observation import CurrentCastleEvidenceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class SelectCastleConfirmationTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves select castle confirmation."""

    def test_select_castle_succeeds_on_lord_info_confirmation_for_target(self) -> None:
        """Treats the post-switch Lord Info confirmation as a terminal success condition."""

        task = SelectCastleTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(self.target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
            castle_roster_provider=lambda: roster,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="Main",
        )

        actions = task.plan(context, matching_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertEqual(actions, [])
        self.assertTrue(result.succeeded)

    def test_select_castle_succeeds_on_lord_info_confirmation_for_live_target_name(self) -> None:
        """Keeps the terminal Lord Info success path working for the live pine cobaye target."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
            castle_roster_provider=lambda: roster,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="pine cobaye 1",
        )

        actions = task.plan(context, matching_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertEqual(actions, [])
        self.assertTrue(result.succeeded)

    def test_select_castle_succeeds_after_returning_home_from_selected_manage_char_without_roster(self) -> None:
        """Treats exact Manage Char selection as sufficient once home city inherits the validated target."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
        )
        selected_manage_char = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            current_castle=target_castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        )
        returned_home = make_observation(
            ScreenType.PNC_HOME_CITY,
            current_castle=target_castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        )

        actions = task.plan(context, selected_manage_char)
        result = task.verify(context, selected_manage_char, returned_home)

        self.assertEqual(len(actions), 1)
        self.assertTrue(result.succeeded)

    def test_select_castle_succeeds_on_lord_info_confirmation_despite_spacing_only_ocr_drift(self) -> None:
        """Treats spacing-only Lord Info OCR drift as the same configured target castle."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
            castle_roster_provider=lambda: roster,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="please bgentle",
        )

        actions = task.plan(context, matching_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertEqual(actions, [])
        self.assertTrue(result.succeeded)

    def test_select_castle_succeeds_on_lord_info_confirmation_with_duplicate_semantic_roster_variants(self) -> None:
        """Does not treat OCR-variant duplicate roster rows as ambiguous Lord Info evidence."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                target_castle,
                CastleIdentity(kingdom="K226", castle_name="please bgentle", castle_level=12),
            ),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
            castle_roster_provider=lambda: roster,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="please b gentle",
        )

        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertTrue(result.succeeded)
