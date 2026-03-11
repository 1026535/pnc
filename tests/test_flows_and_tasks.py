"""Flow-planner and task unit tests."""

from __future__ import annotations

import unittest

from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.automation.tasks.gathering_task import GatheringTask
from pnc_automation.automation.tasks.login_task import LoginTask
from pnc_automation.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.config.models import (
    AccountConfig,
    CastleRosterOrdering,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
    SelectedCastleConfig,
)
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import InputTextAction, KeyEventAction, SwipeAction, TapAction, TapListEntryAction, WaitAction
from pnc_automation.pnc.observation import ListEntryKind
from pnc_automation.pnc.policy_models import BuildingUpgradePolicy, GatheringPolicy
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from tests.test_support import build_logger, make_entry, make_observation


class FlowAndTaskTests(unittest.TestCase):
    """Validates reusable flows and direct task behavior."""

    def setUp(self) -> None:
        """Builds shared task context inputs."""

        self.account = AccountConfig(
            id="account_a",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
            selected_castle=SelectedCastleConfig(kingdom="K230", castle_name="Main", castle_level=8),
            credentials=ResolvedCredentials(
                username="user@example.com",
                password="secret",
                source=CredentialSource.INLINE,
            ),
        )
        self.defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        self.flows = ScreenFlowPlanner()
        self.logger = build_logger()

    def test_ensure_home_city_from_world_map_uses_world_home_nav(self) -> None:
        """Ensures the reusable flow maps world map back to city with one canonical selector."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_SEARCH_BUTTON),
        )

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_WORLD_HOME_NAV)

    def test_ensure_home_city_from_alliance_join_uses_back_navigation(self) -> None:
        """Treats the join-alliance landing as a back-navigable root-adjacent screen."""

        observation = make_observation(ScreenType.PNC_ALLIANCE_JOIN)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_ensure_home_city_from_castle_selection_uses_back_navigation(self) -> None:
        """Treats the Manage Char roster as a back-navigable root-adjacent screen."""

        observation = make_observation(ScreenType.PNC_CASTLE_SELECTION)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_login_task_plans_username_and_password_entry(self) -> None:
        """Builds the expected credential-entry actions on the login screen."""

        task = LoginTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )
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
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )
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
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )

        actions = task.plan(context, make_observation(ScreenType.PNC_LOADING))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertTrue(actions[0].observe_after)

    def test_login_task_opens_castle_selection_when_home_city_is_unverified_but_roster_exists(self) -> None:
        """Uses the trusted roster cache to verify already-in-game sessions instead of silently succeeding."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(self.account.selected_castle,),
        )
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: roster,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
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

    def test_login_task_uses_manage_char_from_more_menu_when_verifying_in_game_account(self) -> None:
        """Continues the verification path from the More menu into Manage Char."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(self.account.selected_castle,),
        )
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: roster,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
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

    def test_login_task_verifies_castle_selection_against_pre_observation_roster_snapshot(self) -> None:
        """Accepts a castle-selection state only when the trusted pre-observation snapshot matches."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                self.account.selected_castle,
                SelectedCastleConfig(kingdom="K229", castle_name="Farm", castle_level=4),
            ),
        )
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )
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

    def test_login_task_replans_wrong_account_on_recoverable_login_states(self) -> None:
        """Keeps wrong-account login and account-switch states on the task's replan path."""

        task = LoginTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )

        for screen_type in (ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH):
            with self.subTest(screen_type=screen_type):
                result = task.verify(
                    context,
                    make_observation(screen_type),
                    make_observation(screen_type, current_pnc_account_id="other@example.com"),
                )

                self.assertEqual(result.status.value, "replan")

    def test_open_castle_selection_uses_more_then_settings_then_manage_char(self) -> None:
        """Uses the live More-overlay path through Settings before entering Manage Char."""

        home_observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
        )
        more_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
        )
        settings_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,),
        )

        home_actions = self.flows.open_castle_selection(home_observation)
        more_actions = self.flows.open_castle_selection(more_observation)
        settings_actions = self.flows.open_castle_selection(settings_observation)

        self.assertEqual(len(home_actions), 3)
        self.assertIsInstance(home_actions[0], TapAction)
        self.assertEqual(home_actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(home_actions[1], TapAction)
        self.assertEqual(home_actions[1].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(home_actions[2], TapAction)
        self.assertEqual(home_actions[2].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)
        self.assertEqual(len(more_actions), 2)
        self.assertIsInstance(more_actions[0], TapAction)
        self.assertEqual(more_actions[0].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(more_actions[1], TapAction)
        self.assertEqual(more_actions[1].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)
        self.assertEqual(len(settings_actions), 1)
        self.assertIsInstance(settings_actions[0], TapAction)
        self.assertEqual(settings_actions[0].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_open_lord_info_uses_home_shortcut_after_closing_more_overlay(self) -> None:
        """Uses the direct home shortcut and only closes overlays when the task starts from More."""

        home_observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )
        more_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS),
        )
        settings_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,),
        )

        home_actions = self.flows.open_lord_info(home_observation)
        more_actions = self.flows.open_lord_info(more_observation)
        settings_actions = self.flows.open_lord_info(settings_observation)

        self.assertEqual(len(home_actions), 1)
        self.assertIsInstance(home_actions[0], TapAction)
        self.assertEqual(home_actions[0].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)
        self.assertEqual(len(more_actions), 2)
        self.assertIsInstance(more_actions[0], TapAction)
        self.assertEqual(more_actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(more_actions[1], TapAction)
        self.assertEqual(more_actions[1].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)
        self.assertEqual(len(settings_actions), 3)
        self.assertIsInstance(settings_actions[0], KeyEventAction)
        self.assertIsInstance(settings_actions[1], TapAction)
        self.assertEqual(settings_actions[1].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(settings_actions[2], TapAction)
        self.assertEqual(settings_actions[2].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)

    def test_select_castle_opens_lord_info_before_switch_when_current_castle_is_unknown(self) -> None:
        """Validates the origin castle from Lord Info before entering Manage Char."""

        task = SelectCastleTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)

    def test_select_castle_switches_from_lord_info_when_origin_castle_is_wrong(self) -> None:
        """Leaves Lord Info and continues straight into Manage Char when the origin castle is not the target."""

        task = SelectCastleTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )
        observation = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="Wrong",
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 4)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[3], TapAction)
        self.assertEqual(actions[3].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_return_to_safe_root_screen_closes_more_overlay_without_triggering_exit_popup(self) -> None:
        """Closes the live More overlay with its own toggle instead of using Android back."""

        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)

    def test_return_to_safe_root_screen_closes_more_settings_submenu_with_toggle(self) -> None:
        """Uses the More toggle to exit the live submenu state that back turns into a popup loop."""

        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS, UiElementId.PNC_MORE_MANAGE_CHAR),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)

    def test_return_to_safe_root_screen_uses_top_left_back_for_fullscreen_more_settings(self) -> None:
        """Uses the visible top-left back target when the full-screen Settings page hides the More toggle."""

        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_MORE_MANAGE_CHAR),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BACK_BUTTON_TOP_LEFT)

    def test_select_castle_succeeds_on_lord_info_confirmation_for_target(self) -> None:
        """Treats the post-switch Lord Info confirmation as a terminal success condition."""

        task = SelectCastleTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="Main",
        )

        actions = task.plan(context, matching_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertEqual(actions, [])
        self.assertTrue(result.succeeded)

    def test_select_castle_waits_on_unknown_transition_after_switch(self) -> None:
        """Keeps unknown splash frames on the recoverable settle path after a castle switch."""

        task = SelectCastleTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )

        actions = task.plan(context, make_observation(ScreenType.UNKNOWN))
        result = task.verify(context, make_observation(ScreenType.PNC_LOADING), make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(result.status.value, "replan")

    def test_select_castle_replans_popup_after_switch_for_runner_recovery(self) -> None:
        """Hands post-switch popups back to the runner instead of failing the step outright."""

        task = SelectCastleTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=None,
            flows=self.flows,
            logger=self.logger,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_LOADING),
            make_observation(ScreenType.PNC_POPUP, blocking_popup=True),
        )

        self.assertEqual(result.status.value, "replan")

    def test_ensure_correct_castle_selected_scrolls_toward_target_using_cached_roster_order(self) -> None:
        """Plans a deterministic swipe when the target castle is outside the visible roster window."""

        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                SelectedCastleConfig(kingdom="K226", castle_name="Alpha", castle_level=3),
                SelectedCastleConfig(kingdom="K227", castle_name="Bravo", castle_level=4),
                self.account.selected_castle,
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

        actions = self.flows.ensure_correct_castle_selected(observation, self.account.selected_castle, roster)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")

    def test_ensure_correct_castle_selected_rejects_untrusted_cached_roster_order(self) -> None:
        """Fails fast instead of guessing a scroll direction from a partial cached roster."""

        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                SelectedCastleConfig(kingdom="K226", castle_name="Alpha", castle_level=3),
                self.account.selected_castle,
            ),
            ordering=CastleRosterOrdering.UNKNOWN,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(make_entry(ListEntryKind.CASTLE, title="Alpha", metadata={"kingdom": "K226", "castle_level": 3}),),
        )

        with self.assertRaises(SelectorResolutionError):
            self.flows.ensure_correct_castle_selected(observation, self.account.selected_castle, roster)

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

        actions = self.flows.ensure_correct_castle_selected(observation, self.account.selected_castle, None)

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapListEntryAction)
        self.assertIsInstance(actions[1], WaitAction)
        self.assertTrue(actions[1].observe_after)

    def test_building_upgrade_task_chooses_highest_priority_candidate(self) -> None:
        """Selects the configured highest-priority building candidate from visible entries."""

        task = BuildingUpgradeTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=BuildingUpgradePolicy(),
            flows=self.flows,
            logger=self.logger,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(
                UiElementId.PNC_HOME_WORLD_SWITCH,
                UiElementId.PNC_HOME_CHARACTER_PANEL,
                UiElementId.PNC_HOME_BUILD_BUTTON,
            ),
            list_entries=(
                make_entry(ListEntryKind.BUILDING, title="Academy", metadata={"category": "academy"}),
                make_entry(ListEntryKind.BUILDING, title="Castle", metadata={"category": "castle"}),
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapListEntryAction)
        self.assertEqual(actions[0].title_text, "Castle")

    def test_gathering_task_skips_when_no_march_slots_remain(self) -> None:
        """Treats zero available march slots as a safe no-op."""

        task = GatheringTask()
        context = TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": None, "params": {}})(),
            params=GatheringPolicy(),
            flows=self.flows,
            logger=self.logger,
        )
        before = make_observation(ScreenType.PNC_WORLD_MAP, available_march_slots=0)
        after = before

        result = task.verify(context, before, after)

        self.assertTrue(result.succeeded)
        self.assertIn("No march slots", result.message)


if __name__ == "__main__":
    unittest.main()
