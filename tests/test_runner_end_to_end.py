"""End-to-end runner test using fake observations and a fake session."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.scripts.registry import build_default_task_registry
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CastleIdentity,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId, build_home_city_object_metadata
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import ListEntryKind, SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from tests.test_support import (
    FakeObservationService,
    FakeSession,
    build_logger,
    make_entry,
    make_observation,
    make_spatial_object,
    make_spatial_surface,
)


class RunnerEndToEndTests(unittest.TestCase):
    """Exercises the full runner loop across all implemented task types."""

    def test_runner_executes_full_daily_flow_with_replans_and_popup_recovery(self) -> None:
        """Runs the scripted daily flow against fake observations and fake device actions."""

        defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        target_castle = CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8)
        account = AccountConfig(
            id="account_a",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
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
                ScriptStep(task=TaskId.SELECT_CASTLE, castle=target_castle),
                ScriptStep(task=TaskId.BUILDING_UPGRADE, params={"priority": ["castle", "institute"], "allow_speedups": False}),
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
                current_pnc_account_id="user@example.com",
            ),
            make_observation(
                ScreenType.PNC_LOGIN,
                visible_ids=(
                    UiElementId.PNC_LOGIN_USERNAME_FIELD,
                    UiElementId.PNC_LOGIN_PASSWORD_FIELD,
                    UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                ),
                current_pnc_account_id="user@example.com",
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_BOTTOM_NAV_MORE,
                    UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
            ),
            make_observation(
                ScreenType.PNC_MORE_MENU,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS),
            ),
            make_observation(
                ScreenType.PNC_MORE_MENU,
                visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,),
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
                    UiElementId.PNC_BOTTOM_NAV_MORE,
                    UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Castle",
                            metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        ),
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Institute",
                            metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                        ),
                    ),
                ),
                current_castle=target_castle,
            ),
            make_observation(
                ScreenType.PNC_CASTLE,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(ScreenType.PNC_CASTLE),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                blocking_popup=True,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(
                    UiElementId.PNC_HOME_WORLD_SWITCH,
                    UiElementId.PNC_BOTTOM_NAV_MORE,
                    UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_INSTITUTE,
                visible_ids=(UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON, UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON),
            ),
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
                    UiElementId.PNC_BOTTOM_NAV_MORE,
                    UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_SEARCH_BUTTON),
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.WORLD_MAP,
                    x=253,
                    y=447,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.RESOURCE_NODE,
                            name_text="Food Node",
                            metadata={"resource_type": "food"},
                        ),
                        make_spatial_object(
                            SpatialObjectKind.RESOURCE_NODE,
                            name_text="Wood Node",
                            metadata={"resource_type": "wood"},
                        ),
                    ),
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
                    UiElementId.PNC_BOTTOM_NAV_MORE,
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
                ),
                current_castle_name="Main",
            ),
            make_observation(
                ScreenType.PNC_CAMPAIGN_MAP,
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
        runner = _make_runner(
            defaults=defaults,
            observation_service=fake_observer,
            session=fake_session,
            registry=registry,
        )

        result = runner.run(
            account,
            registry.prepare_script(script),
            castle_roster_provider=lambda: PncAccountCastleRosterConfig(
                pnc_account_id=account.pnc_account_id,
                castles=(target_castle,),
            ),
        )

        self.assertEqual(len(result.steps), 7)
        self.assertEqual(result.steps[-1].status.value, "success")
        self.assertEqual(fake_session.launches, 1)
        self.assertIn("user@example.com", fake_session.texts)
        self.assertIn("secret", fake_session.texts)
        self.assertGreaterEqual(len(fake_session.taps), 8)

    def test_runner_executes_world_chat_task_through_registered_task_loop(self) -> None:
        """Runs a direct chat-send task through runner replans and the shared observed-action executor."""

        message = "runner parity chat"
        defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        account = AccountConfig(
            id="account_a",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
        )
        script = RunScript(
            name="chat_send",
            path=Path("chat.yaml"),
            steps=(ScriptStep(task=TaskId.SEND_WORLD_CHAT_MESSAGE, params={"message": message}),),
        )
        chat_controls = (
            UiElementId.PNC_CHAT_TAB_KINGDOM,
            UiElementId.PNC_CHAT_TAB_ALLIANCE,
            UiElementId.PNC_CHAT_INPUT_FIELD,
            UiElementId.PNC_CHAT_SEND_BUTTON,
        )
        observations = [
            make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,)),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=chat_controls,
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=True,
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=chat_controls,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=chat_controls,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
        ]
        fake_observer = FakeObservationService(observations=observations)
        fake_session = FakeSession()
        registry = build_default_task_registry()
        runner = _make_runner(
            defaults=defaults,
            observation_service=fake_observer,
            session=fake_session,
            registry=registry,
        )

        result = runner.run(account, registry.prepare_script(script))

        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].status.value, "success")
        self.assertEqual(result.steps[0].attempts, 3)
        self.assertIn(message, fake_session.texts)


def _make_runner(
    *,
    defaults: DefaultsConfig,
    observation_service: FakeObservationService,
    session: FakeSession,
    registry: object,
) -> AutomationRunner:
    """Builds the fake-device production runner used by end-to-end parity scenarios."""

    return AutomationRunner(
        defaults=defaults,
        observation_service=observation_service,
        action_executor=ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=ActionExecutor(
                session=session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                chat_stable_click_delay_ms=0,
                chat_post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            logger=build_logger(),
            sleep=lambda _: None,
        ),
        task_registry=registry,
        flow_planner=ScreenFlowPlanner(),
        logger=build_logger(),
    )


if __name__ == "__main__":
    unittest.main()

