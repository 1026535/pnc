"""Runner replan budget."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.runner import AutomationRunner, StepExecutionPolicy
from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.core.errors import TaskVerificationError
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
from tests.support.automation.engine.always_replan_task import _AlwaysReplanTask
from tests.support.automation.engine.local_budget_replan_task import _LocalBudgetReplanTask
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class RunnerReplanBudgetTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves runner replan budget."""

    def test_runner_uses_task_local_replan_budget_instead_of_runner_wide_override(self) -> None:
        """Allows one task to own an extended bounded replan budget without broadening the global runner cap."""

        registry = TaskRegistry(tasks=(_LocalBudgetReplanTask(),))
        script = registry.prepare_script(
            RunScript(
                name="local_budget",
                path=Path("local_budget.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,))]
        )
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=_make_observed_action_executor(FakeSession()),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        result = runner.run(self.account, script)

        self.assertEqual(runner.policy.max_replans_per_step, 5)
        self.assertEqual(result.steps[0].status.value, "success")

    def test_runner_persists_failure_artifact_when_replan_limit_is_exhausted(self) -> None:
        """Captures one persisted failure artifact when a task exceeds its allowed replans in light-style observation flows."""

        registry = TaskRegistry(tasks=(_AlwaysReplanTask(),))
        script = registry.prepare_script(
            RunScript(
                name="replan_limit",
                path=Path("replan_limit.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,)),
                make_observation(ScreenType.PNC_HOME_CITY, artifact_path=Path("artifacts/replan_limit.png")),
            ]
        )
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=_make_observed_action_executor(FakeSession()),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
            policy=StepExecutionPolicy(max_replans_per_step=0),
        )

        with self.assertRaises(TaskVerificationError) as error_context:
            runner.run(self.account, script)

        self.assertEqual(
            fake_observer.labels,
            ["ensure_game_running_before", "ensure_game_running_failure_replan_limit"],
        )
        self.assertEqual(error_context.exception.details["artifact_path"], str(Path("artifacts/replan_limit.png")))
        self.assertEqual(error_context.exception.details["screen_type"], ScreenType.PNC_HOME_CITY)
        self.assertEqual(error_context.exception.details["replans"], 1)
