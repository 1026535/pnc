"""Runner bootstrap: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import BaseAutomationTask, TaskId, TaskResult, require_no_params
from pnc_automation.app.pnc.domain.action_requests import WaitAction
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class RunnerBootstrapTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves runner bootstrap."""

    def test_bootstrap_owns_popup_recovery_inside_the_canonical_task_loop(self) -> None:
        """Keeps visual-X recovery in the executor-owned preflight boundary."""

        registry = TaskRegistry(tasks=(_LegacyPopupProbeTask(),))
        script = registry.prepare_script(
            RunScript(
                name="popup_guard",
                path=Path("popup_guard.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                    blocking_popup=True,
                ),
                make_observation(ScreenType.PNC_HOME_CITY),
                make_observation(ScreenType.PNC_HOME_CITY),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=_make_observed_action_executor(fake_session),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        result = runner.run(self.account, script)

        self.assertEqual(result.steps[0].status.value, "success")
        self.assertEqual(
            fake_observer.labels,
            [
                "ensure_game_running_before",
                "ensure_game_running_ensure_game_running_preflight_update_popup_1",
                "ensure_game_running_post_action_1",
            ],
        )
        self.assertEqual(fake_session.taps, [(5, 5)])

    def test_bootstrap_never_taps_the_same_popup_fingerprint_twice(self) -> None:
        """Fails closed when one visual bootstrap popup remains after its single X tap."""

        registry = TaskRegistry(tasks=(_LegacyPopupProbeTask(),))
        script = registry.prepare_script(
            RunScript(
                name="popup_fingerprint_guard",
                path=Path("popup_fingerprint_guard.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        popup = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="same-popup",
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=FakeObservationService(observations=[popup, popup]),
            action_executor=_make_observed_action_executor(fake_session),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        with self.assertRaisesRegex(SelectorResolutionError, "(?:already consumed|unchanged visual fingerprint)"):
            runner.run(self.account, script)

        self.assertEqual(fake_session.taps, [(5, 5)])

class _LegacyPopupProbeTask(BaseAutomationTask):
    """Purpose-specific legacy fixture retaining generic popup recovery coverage."""

    id = TaskId.ENSURE_GAME_RUNNING

    def parse_params(self, params):
        require_no_params(self.id, params)
        return None

    def is_applicable(self, context, observation):
        del context, observation
        return True

    def plan(self, context, observation):
        del context, observation
        return [WaitAction(milliseconds=0, reason="legacy_probe", observe_after=True)]

    def verify(self, context, before, after):
        del context, before, after
        return TaskResult.success("legacy probe complete")
