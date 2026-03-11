"""Flow-planner and task unit tests."""

from __future__ import annotations

import unittest

from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.automation.tasks.gathering_task import GatheringTask
from pnc_automation.automation.tasks.login_task import LoginTask
from pnc_automation.config.models import (
    AccountConfig,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
    SelectedCastleConfig,
)
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

    def test_ensure_correct_castle_selected_scrolls_toward_target_using_cached_roster_order(self) -> None:
        """Plans a deterministic swipe when the target castle is outside the visible roster window."""

        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                SelectedCastleConfig(kingdom="K226", castle_name="Alpha", castle_level=3),
                SelectedCastleConfig(kingdom="K227", castle_name="Bravo", castle_level=4),
                self.account.selected_castle,
            ),
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
