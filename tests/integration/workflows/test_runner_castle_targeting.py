"""Runner castle targeting: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from pathlib import Path
import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.popup_recovery_task import PopupRecoveryTask
from pnc_automation.app.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_entry, make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.entrypoints.castle_targeting.runtime_castle_targeting_fixtures import (
    RuntimeCastleTargetingFixtures,
)
from tests.support.entrypoints.castle_targeting.optional_castle_task import _OptionalCastleTask


class RunnerCastleTargetingTests(RuntimeCastleTargetingFixtures, unittest.TestCase):
    """Proves runner castle targeting."""

    def test_runner_auto_selects_explicit_castle_before_optional_task(self) -> None:
        """Runs the canonical select-castle pre-step before an optional castle-targeted task."""

        registry = TaskRegistry(tasks=(PopupRecoveryTask(), SelectCastleTask(), _OptionalCastleTask()))
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    current_castle=CastleIdentity(kingdom="K229", castle_name="Wrong"),
                ),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                    current_castle_name="Wrong",
                ),
                make_observation(
                    ScreenType.PNC_SETTINGS,
                    visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,),
                    current_castle_name="Wrong",
                ),
                make_observation(
                    ScreenType.PNC_CASTLE_SELECTION,
                    list_entries=(
                        make_entry(
                            ListEntryKind.CASTLE,
                            title="Main",
                            metadata={"kingdom": "K230", "castle_level": 8},
                        ),
                    ),
                ),
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    current_castle_name="Main",
                ),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=fake_session,
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
        prepared = registry.prepare_script(
            RunScript(
                name="auto_select",
                path=Path("auto_select.yaml"),
                steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE, castle=self.target_castle),),
            )
        )

        result = runner.run(
            self.account,
            prepared,
            castle_roster_provider=lambda: PncAccountCastleRosterConfig(
                pnc_account_id=self.account.pnc_account_id,
                castles=(self.target_castle,),
            ),
        )

        self.assertEqual(result.steps[0].requested_castle, self.target_castle)
        self.assertTrue(any(label.startswith("select_castle_") for label in fake_observer.labels))
        self.assertGreaterEqual(len(fake_session.taps), 4)

    def test_runner_does_not_select_castle_when_optional_task_has_no_target(self) -> None:
        """Leaves optional tasks on current-castle semantics when the step omits `castle`."""

        registry = TaskRegistry(tasks=(PopupRecoveryTask(), SelectCastleTask(), _OptionalCastleTask()))
        fake_observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_HOME_CITY)])
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=FakeSession(),
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
        prepared = registry.prepare_script(
            RunScript(
                name="no_target",
                path=Path("no_target.yaml"),
                steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE),),
            )
        )

        runner.run(self.account, prepared)

        self.assertEqual(fake_observer.labels, ["building_upgrade_before"])
