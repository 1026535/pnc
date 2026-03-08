"""Automation-framework tests for Phase 3 behavior."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.runner import AutomationRunner
from pnc_automation.automation.scripts.models import RunScript, ScriptStep
from pnc_automation.automation.scripts.registry import TaskRegistry, build_default_task_registry
from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.config.models import AccountConfig, CredentialSource, DefaultsConfig, ResolvedCredentials, SelectedCastleConfig
from pnc_automation.errors import ScriptValidationError
from pnc_automation.pnc.action_requests import ActionRequest, TapAction
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from tests.test_support import FakeObservationService, FakeSession, build_logger, make_observation


class AutomationFrameworkTests(unittest.TestCase):
    """Validates the generic runner, registry, and retry framework."""

    def setUp(self) -> None:
        """Builds shared account and defaults inputs for framework tests."""

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

    def test_prepare_script_validates_task_parameters_before_execution(self) -> None:
        """Fails fast with step metadata when task-specific params are invalid."""

        registry = build_default_task_registry()
        script = RunScript(
            name="invalid",
            path=Path("invalid.yaml"),
            steps=(
                ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
                ScriptStep(task=TaskId.GATHERING, params={"preferred_resources": ["food"], "max_parallel_marches": 0}),
            ),
        )

        with self.assertRaises(ScriptValidationError) as error_context:
            registry.prepare_script(script)

        self.assertEqual(error_context.exception.details["step_index"], 1)
        self.assertEqual(error_context.exception.details["task"], TaskId.GATHERING)

    def test_task_registry_rejects_duplicate_task_ids(self) -> None:
        """Rejects duplicate task ids instead of silently shadowing one task."""

        with self.assertRaises(ValueError):
            TaskRegistry(tasks=(EnsureGameRunningTask(), EnsureGameRunningTask()))

    def test_runner_executes_observe_click_reobserve_verify_loop_for_trivial_task(self) -> None:
        """Exercises the minimal generic runner loop with one synthetic tap task."""

        registry = TaskRegistry(tasks=(_TrivialTapTask(),))
        script = registry.prepare_script(
            RunScript(
                name="trivial",
                path=Path("trivial.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,)),
                make_observation(ScreenType.PNC_BUILDING_DETAILS),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
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

        result = runner.run(self.account, script)

        self.assertEqual(result.steps[0].status.value, "success")
        self.assertEqual(fake_observer.labels, ["ensure_game_running_before", "ensure_game_running_post_action_1"])
        self.assertEqual(fake_session.taps, [(5, 5)])

    def test_popup_recovery_uses_the_same_retry_loop_as_normal_steps(self) -> None:
        """Routes popup recovery through the shared retry loop before continuing the step."""

        registry = build_default_task_registry()
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
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                    blocking_popup=True,
                ),
                make_observation(ScreenType.PNC_HOME_CITY),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
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

        result = runner.run(self.account, script)

        self.assertEqual(result.steps[0].status.value, "success")
        self.assertEqual(
            fake_observer.labels,
            [
                "ensure_game_running_before",
                "popup_recovery_post_action_1",
                "popup_recovery_retry_1",
            ],
        )
        self.assertEqual(fake_session.taps, [(5, 5)])


class _TrivialTapTask(BaseAutomationTask):
    """Synthetic task used to prove the framework loop independently of game logic."""

    id = TaskId.ENSURE_GAME_RUNNING

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Runs only when the synthetic target selector is visible."""

        del context
        return observation.has(UiElementId.PNC_HOME_BUILD_BUTTON)

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Requests one selector-backed tap followed by re-observation."""

        del context, observation
        return [
            TapAction(
                selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                reason="tap_synthetic_target",
                observe_after=True,
            )
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the follow-up observation reaches the synthetic destination screen."""

        del context, before
        if after.screen_type == ScreenType.PNC_BUILDING_DETAILS:
            return TaskResult.success("Synthetic tap reached the destination screen.")
        return TaskResult.failure("Synthetic tap did not reach the destination screen.", retryable=True)


if __name__ == "__main__":
    unittest.main()
