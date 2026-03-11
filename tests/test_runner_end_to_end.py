"""End-to-end runner test using fake observations and a fake session."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.runner import AutomationRunner
from pnc_automation.automation.scripts.models import RunScript, ScriptStep
from pnc_automation.automation.scripts.registry import build_default_task_registry
from pnc_automation.automation.task import TaskId
from pnc_automation.config.models import AccountConfig, CredentialSource, DefaultsConfig, ResolvedCredentials, SelectedCastleConfig
from pnc_automation.pnc.observation import ListEntryKind
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from tests.test_support import FakeObservationService, FakeSession, build_logger, make_entry, make_observation


class RunnerEndToEndTests(unittest.TestCase):
    """Exercises the full runner loop across all implemented task types."""

    def test_runner_executes_full_daily_flow_with_replans_and_popup_recovery(self) -> None:
        """Runs the scripted daily flow against fake observations and fake device actions."""

        defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        account = AccountConfig(
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
        script = RunScript(
            name="daily_castle_maintenance",
            path=Path("daily.yaml"),
            steps=(
                ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
                ScriptStep(task=TaskId.LOGIN),
                ScriptStep(task=TaskId.SELECT_CASTLE),
                ScriptStep(task=TaskId.BUILDING_UPGRADE, params={"priority": ["castle", "academy"], "allow_speedups": False}),
                ScriptStep(task=TaskId.RESEARCH, params={"priority": ["economy", "development"]}),
                ScriptStep(task=TaskId.GATHERING, params={"preferred_resources": ["food", "wood"], "max_parallel_marches": 2}),
                ScriptStep(task=TaskId.CAMPAIGN, params={"enabled_modes": ["standard"]}),
            ),
        )

        observations = [
            make_observation(ScreenType.ANDROID_HOME, visible_ids=(UiElementId.ANDROID_HOME_PNC_ICON,)),
            make_observation(
                ScreenType.PNC_LOGIN,
                visible_ids=(
                    UiElementId.PNC_LOGIN_USERNAME_FIELD,
                    UiElementId.PNC_LOGIN_PASSWORD_FIELD,
                    UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                ),
            ),
            make_observation(
                ScreenType.PNC_LOGIN,
                visible_ids=(
                    UiElementId.PNC_LOGIN_USERNAME_FIELD,
                    UiElementId.PNC_LOGIN_PASSWORD_FIELD,
                    UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                ),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_HOME_CHARACTER_PANEL,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Wrong",
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_HOME_CHARACTER_PANEL,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Wrong",
            ),
            make_observation(
                ScreenType.PNC_CASTLE_SELECTION,
                list_entries=(
                    make_entry(
                        ListEntryKind.CASTLE,
                        title="Main",
                        selected=False,
                        metadata={"kingdom": "K230", "castle_level": 8},
                    ),
                ),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_HOME_CHARACTER_PANEL,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_HOME_CHARACTER_PANEL,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                list_entries=(
                    make_entry(ListEntryKind.BUILDING, title="Castle", metadata={"category": "castle"}),
                    make_entry(ListEntryKind.BUILDING, title="Academy", metadata={"category": "academy"}),
                ),
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_BUILDING_DETAILS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(ScreenType.PNC_BUILDING_DETAILS),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                blocking_popup=True,
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_HOME_CHARACTER_PANEL,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Main",
            ),
            make_observation(ScreenType.PNC_ACADEMY, visible_ids=(UiElementId.PNC_RESEARCH_AVAILABLE_BADGE,)),
            make_observation(
                ScreenType.PNC_RESEARCH_TREE,
                visible_ids=(UiElementId.PNC_RESEARCH_START_BUTTON,),
                list_entries=(
                    make_entry(ListEntryKind.RESEARCH, title="Economy I", metadata={"category": "economy"}),
                    make_entry(ListEntryKind.RESEARCH, title="Development I", metadata={"category": "development"}),
                ),
            ),
            make_observation(ScreenType.PNC_RESEARCH_TREE, visible_ids=(UiElementId.PNC_RESEARCH_START_BUTTON,)),
            make_observation(ScreenType.PNC_RESEARCH_TREE),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_HOME_CHARACTER_PANEL,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_SEARCH_BUTTON),
                list_entries=(
                    make_entry(ListEntryKind.GATHER_NODE, title="Food Node", metadata={"resource_type": "food"}),
                    make_entry(ListEntryKind.GATHER_NODE, title="Wood Node", metadata={"resource_type": "wood"}),
                ),
                available_march_slots=2,
            ),
            make_observation(
                ScreenType.PNC_GATHER_NODE,
                visible_ids=(UiElementId.PNC_GATHER_BUTTON,),
                available_march_slots=2,
            ),
            make_observation(
                ScreenType.PNC_MARCH_CONFIRM,
                visible_ids=(UiElementId.PNC_MARCH_CONFIRM_BUTTON,),
                available_march_slots=2,
            ),
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_SEARCH_BUTTON),
                available_march_slots=1,
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_HOME_CHARACTER_PANEL,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_CAMPAIGN,
                list_entries=(make_entry(ListEntryKind.CAMPAIGN_STAGE, title="Stage 1", metadata={"mode": "standard"}),),
            ),
            make_observation(
                ScreenType.PNC_CAMPAIGN_STAGE,
                visible_ids=(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,),
            ),
            make_observation(ScreenType.PNC_BATTLE_PREP),
        ]

        fake_observer = FakeObservationService(observations=observations)
        fake_session = FakeSession()
        registry = build_default_task_registry()
        runner = AutomationRunner(
            defaults=defaults,
            observation_service=fake_observer,
            action_executor=ActionExecutor(
                session=fake_session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        result = runner.run(account, registry.prepare_script(script))

        self.assertEqual(len(result.steps), 7)
        self.assertEqual(result.steps[-1].status.value, "success")
        self.assertEqual(fake_session.launches, 1)
        self.assertIn("user@example.com", fake_session.texts)
        self.assertIn("secret", fake_session.texts)
        self.assertGreaterEqual(len(fake_session.taps), 8)


if __name__ == "__main__":
    unittest.main()
