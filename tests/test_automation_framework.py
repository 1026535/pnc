"""Automation-framework tests for Phase 3 behavior."""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from pathlib import Path

from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.observed_action_executor import ObservedActionExecutor, ObservedActionExecutionPolicy
from pnc_automation.automation.runner import AutomationRunner
from pnc_automation.automation.scripts.models import RunScript, ScriptStep
from pnc_automation.automation.scripts.registry import TaskRegistry, build_default_task_registry
from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.config.models import AccountConfig, CredentialSource, DefaultsConfig, ResolvedCredentials, SelectedCastleConfig
from pnc_automation.errors import ScriptValidationError, SelectorResolutionError
from pnc_automation.pnc.action_requests import ActionRequest, TapAction
from pnc_automation.pnc.observation import Observation, VisibleElementSourceKind
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.vision.selectors import (
    ClickDefinition,
    ClickOutcome,
    DetectionKind,
    SelectorDefinition,
    SelectorRegistry,
    SelectorStatus,
    build_default_selector_registry,
)
from tests.test_support import FakeObservationService, FakeSession, build_logger, make_observation, make_visible


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

    def _make_selector_registry(
        self,
        *,
        selector_id: UiElementId = UiElementId.PNC_BOTTOM_NAV_MORE,
        source_screen: ScreenType = ScreenType.PNC_HOME_CITY,
        target_screen: ScreenType = ScreenType.PNC_MORE_MENU,
        verification_selectors: Sequence[UiElementId] = (UiElementId.PNC_MORE_SETTINGS,),
        interaction_kind: SelectorInteractionKind = SelectorInteractionKind.NAVIGATION,
        safe_to_click: bool = True,
    ) -> SelectorRegistry:
        """Builds the minimal selector registry required for one observed-action test."""

        return SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=selector_id,
                    screens=(source_screen,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=interaction_kind,
                    click=ClickDefinition(),
                    click_outcomes=(
                        ClickOutcome(
                            target_screen=target_screen,
                            verification_selectors=tuple(verification_selectors),
                            safe_to_click=safe_to_click,
                        ),
                    ),
                ),
            )
        )

    def _execute_observed_tap(
        self,
        *,
        registry: SelectorRegistry,
        before: Observation,
        queued_observations: Sequence[Observation],
        selector_id: UiElementId = UiElementId.PNC_BOTTOM_NAV_MORE,
        policy: ObservedActionExecutionPolicy | None = None,
    ) -> tuple[object, FakeObservationService, FakeSession]:
        """Executes one selector-backed tap through the shared observed-action executor."""

        fake_observer = FakeObservationService(observations=list(queued_observations))
        fake_session = FakeSession()
        executor = _make_observed_action_executor(
            fake_session,
            registry=registry,
            policy=ObservedActionExecutionPolicy() if policy is None else policy,
        )
        execution = executor.execute_actions(
            (
                TapAction(
                    selector_id=selector_id,
                    reason="test_navigation_tap",
                    observe_after=True,
                ),
            ),
            before,
            observe=fake_observer.observe,
        )
        return execution, fake_observer, fake_session

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
            action_executor=_make_observed_action_executor(fake_session),
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
                "popup_recovery_post_action_1",
                "popup_recovery_retry_1",
            ],
        )
        self.assertEqual(fake_session.taps, [(5, 5)])

    def test_tap_actions_prefer_visible_element_action_points(self) -> None:
        """Uses selector-specific action points when OCR-derived bounds are not the real touch target."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = Observation(
            screen_type=ScreenType.PNC_HOME_CITY,
            visible_elements={
                UiElementId.PNC_BOTTOM_NAV_BAG: make_visible(
                    UiElementId.PNC_BOTTOM_NAV_BAG,
                    x=440,
                    y=1560,
                    width=54,
                    height=33,
                    action_point=(482, 1529),
                )
            },
        )

        executor.execute_action(
            TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_BAG),
            observation,
        )

        self.assertEqual(executor.session.taps, [(482, 1529)])

    def test_observed_action_executor_retries_geometry_navigation_taps_once_through_ocr(self) -> None:
        """Promotes one settled geometry miss to an OCR-backed retry using the narrow follow-up requests."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
                ),
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
                ),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertEqual(fake_observer.requests[0], ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes))
        self.assertEqual(fake_observer.requests[1], ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY))
        self.assertEqual(fake_observer.requests[2], ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes))
        self.assertTrue(execution.selector_interactions[0].fallback_attempted)
        self.assertTrue(execution.selector_interactions[0].fallback_used)
        self.assertEqual(execution.selector_interactions[0].fallback_source_kind, VisibleElementSourceKind.OCR)

    def test_observed_action_executor_settles_transitions_to_success_without_ocr_retry(self) -> None:
        """Waits through loading transitions before deciding whether the primary tap actually missed."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(ScreenType.PNC_LOADING),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertEqual(len(fake_observer.requests), 2)
        self.assertTrue(all(request == ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes) for request in fake_observer.requests))
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_stops_on_popup_without_ocr_retry(self) -> None:
        """Returns popup states to the shared popup path instead of double-tapping during recovery."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(ScreenType.PNC_LOADING),
                make_observation(
                    ScreenType.PNC_POPUP,
                    visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                    blocking_popup=True,
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_POPUP)
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_waits_for_a_settled_same_screen_miss_before_ocr_retry(self) -> None:
        """Avoids OCR retry while the post-tap state is still transitional and only promotes after it settles."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(ScreenType.PNC_LOADING),
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
                ),
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
                ),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])
        self.assertEqual(fake_observer.labels[:2], ["post_action_1", "post_action_1_settle_1"])
        self.assertEqual(fake_observer.requests[2], ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY))
        self.assertTrue(execution.selector_interactions[0].fallback_used)

    def test_observed_action_executor_skips_ocr_retry_when_retry_target_is_missing(self) -> None:
        """Does not issue a second tap when the selector still cannot be re-resolved from OCR after a miss."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, _, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
                ),
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertTrue(execution.selector_interactions[0].fallback_attempted)
        self.assertFalse(execution.selector_interactions[0].fallback_used)

    def test_observed_action_executor_skips_ocr_retry_for_non_geometry_sources(self) -> None:
        """Leaves OCR-backed or template-backed selectors on the normal single-tap path."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
        )
        execution, _, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(len(execution.selector_interactions), 1)
        self.assertEqual(execution.selector_interactions[0].initial_source_kind, VisibleElementSourceKind.OCR)
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_skips_ocr_retry_for_non_navigation_selectors(self) -> None:
        """Keeps non-navigation taps on the low-level path even when they were geometry-backed."""

        registry = self._make_selector_registry(interaction_kind=SelectorInteractionKind.ACTION)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, _, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(make_observation(ScreenType.PNC_HOME_CITY),),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertFalse(execution.selector_interactions)

    def test_observed_action_executor_rejects_geometry_navigation_without_safe_outcomes(self) -> None:
        """Fails fast when a geometry-backed navigation selector has no reviewed safe outcome contract."""

        registry = self._make_selector_registry(safe_to_click=False)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        fake_observer = FakeObservationService(observations=[])
        executor = _make_observed_action_executor(FakeSession(), registry=registry)

        with self.assertRaises(SelectorResolutionError):
            executor.execute_actions(
                (
                    TapAction(
                        selector_id=UiElementId.PNC_BOTTOM_NAV_MORE,
                        reason="unsafe_navigation_tap",
                        observe_after=True,
                    ),
                ),
                before,
                observe=fake_observer.observe,
            )

    def test_observed_action_executor_stops_when_settle_budget_is_exhausted(self) -> None:
        """Returns the latest transitional state without any OCR retry when settling never stabilizes."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(ScreenType.PNC_LOADING),
                make_observation(ScreenType.PNC_LOADING),
            ),
            policy=ObservedActionExecutionPolicy(max_settle_observations=1),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_LOADING)
        self.assertEqual(len(fake_observer.requests), 2)
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)


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


def _make_observed_action_executor(
    session: FakeSession,
    *,
    registry: SelectorRegistry | None = None,
    policy: ObservedActionExecutionPolicy | None = None,
) -> ObservedActionExecutor:
    """Builds the shared observed-action executor used by runner and executor tests."""

    return ObservedActionExecutor(
        selector_registry=build_default_selector_registry() if registry is None else registry,
        action_executor=ActionExecutor(
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        ),
        logger=build_logger(),
        policy=ObservedActionExecutionPolicy() if policy is None else policy,
        sleep=lambda _: None,
    )


if __name__ == "__main__":
    unittest.main()
