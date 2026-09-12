"""Login navigation."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.login_task import LoginTask
from pnc_automation.app.pnc.domain.castles import PncAccountCastleRosterConfig
from pnc_automation.app.pnc.domain.action_requests import InputTextAction, TapAction, WaitAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class LoginNavigationTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves login navigation."""

    def test_login_task_plans_username_and_password_entry(self) -> None:
        """Builds the expected credential-entry actions on the login screen."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_LOGIN,
            visible_ids=(
                UiElementId.PNC_LOGIN_USERNAME_FIELD,
                UiElementId.PNC_LOGIN_PASSWORD_FIELD,
                UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], InputTextAction)
        self.assertEqual(actions[0].text, "user@example.com")
        self.assertEqual(actions[1].text, "secret")

    def test_login_task_uses_change_account_when_switch_screen_shows_wrong_account(self) -> None:
        """Forces a clean relogin when account-switch OCR exposes a different remembered account."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_ACCOUNT_SWITCH,
            visible_ids=(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON,),
            current_pnc_account_id="other@example.com",
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON)

    def test_login_task_waits_when_loading_screen_has_no_reconnect_action(self) -> None:
        """Uses one canonical observed wait when bootstrap is still loading."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        actions = task.plan(context, make_observation(ScreenType.PNC_LOADING))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertTrue(actions[0].observe_after)

    def test_login_task_opens_castle_selection_when_home_city_is_unverified_but_roster_exists(self) -> None:
        """Uses the trusted roster cache to verify already-in-game sessions instead of silently succeeding."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(self.target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.LOGIN,
            castle_roster_provider=lambda: roster,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_login_task_opens_lord_info_when_home_city_is_unverified_and_no_roster_exists(self) -> None:
        """Uses the faster Lord Info shortcut when no trusted roster snapshot is available."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)

    def test_login_task_uses_manage_char_from_more_menu_when_verifying_in_game_account(self) -> None:
        """Continues the verification path from the More menu into Manage Char."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(self.target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.LOGIN,
            castle_roster_provider=lambda: roster,
        )
        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_login_task_does_not_interrupt_an_already_open_world_map_session(self) -> None:
        """Avoids redundant root navigation when login is invoked from another active in-game screen."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(actions, [])

    def test_login_task_does_not_interrupt_an_open_building_screen(self) -> None:
        """Treats an in-progress building screen as an already-open session instead of relogging through root."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        actions = task.plan(
            context,
            make_observation(ScreenType.PNC_INFANTRY_BARRACKS),
        )

        self.assertEqual(actions, [])
