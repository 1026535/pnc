"""Automation-framework tests for Phase 3 behavior."""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from pathlib import Path

from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.observed_action_executor import ObservedActionExecutor, ObservedActionExecutionPolicy
from pnc_automation.automation.runner import AutomationRunner, StepExecutionPolicy
from pnc_automation.scripts.models import RunScript, ScriptStep
from pnc_automation.scripts.registry import TaskRegistry, build_default_task_registry
from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.config.models import AccountConfig, CastleIdentity, CredentialSource, DefaultsConfig, ResolvedCredentials
from pnc_automation.errors import ScriptValidationError, SelectorResolutionError, TaskVerificationError
from pnc_automation.pnc.action_requests import (
    ActionRequest,
    InputTextAction,
    SelectChatChannelAction,
    TapAction,
    TapSpatialObjectAction,
)
from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.observation import (
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
    VisibleElementSourceKind,
)
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
from tests.test_support import (
    FakeObservationService,
    FakeSession,
    build_logger,
    make_observation,
    make_spatial_object,
    make_spatial_surface,
    make_visible,
)


class AutomationFrameworkTests(unittest.TestCase):
    """Validates the generic runner, registry, and retry framework."""

    def setUp(self) -> None:
        """Builds shared account and defaults inputs for framework tests."""

        self.account = AccountConfig(
            id="account_a",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
            credentials=ResolvedCredentials(
                username="user@example.com",
                password="secret",
                source=CredentialSource.INLINE,
            ),
        )
        self.target_castle = CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8)
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

    def test_default_task_registry_includes_chat_tasks(self) -> None:
        """Exposes both chat send tasks and the Kingdom Chat monitor through the standard registry."""

        registry = build_default_task_registry()

        self.assertEqual(registry.require(TaskId.SEND_ALLIANCE_CHAT_MESSAGE).id, TaskId.SEND_ALLIANCE_CHAT_MESSAGE)
        self.assertEqual(registry.require(TaskId.SEND_WORLD_CHAT_MESSAGE).id, TaskId.SEND_WORLD_CHAT_MESSAGE)
        self.assertEqual(registry.require(TaskId.COLLECT_KINGDOM_CHAT).id, TaskId.COLLECT_KINGDOM_CHAT)

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

    def test_ensure_game_running_waits_through_unknown_launch_splash_without_relaunching(self) -> None:
        """Keeps one app launch in flight while the splash is still classified as unknown."""

        registry = build_default_task_registry()
        script = registry.prepare_script(
            RunScript(
                name="ensure_game_running_splash",
                path=Path("ensure_game_running_splash.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.ANDROID_HOME, visible_ids=(UiElementId.ANDROID_HOME_PNC_ICON,)),
                make_observation(ScreenType.UNKNOWN),
                make_observation(ScreenType.UNKNOWN),
                make_observation(
                    ScreenType.PNC_LOGIN,
                    visible_ids=(
                        UiElementId.PNC_LOGIN_USERNAME_FIELD,
                        UiElementId.PNC_LOGIN_PASSWORD_FIELD,
                        UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                    ),
                ),
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
        self.assertEqual(fake_session.launches, 1)
        self.assertEqual(fake_session.key_events, [])

    def test_tap_actions_prefer_visible_element_action_points(self) -> None:
        """Uses selector-specific action points when OCR-derived bounds are not the real touch target."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
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

    def test_tap_spatial_object_actions_use_current_viewport_action_points(self) -> None:
        """Uses the live spatial-object action point from the current viewport instead of any fixed building coordinate."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata={"category": "castle"},
                        action_point=(167, 241),
                    ),
                ),
            ),
        )

        executor.execute_action(
            TapSpatialObjectAction(
                query=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    name_text="Castle",
                    metadata_key="category",
                    metadata_value="castle",
                )
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(167, 241)])

    def test_tap_spatial_object_actions_preserve_duplicate_target_points(self) -> None:
        """Uses the concrete target point captured during planning instead of re-resolving duplicate semantic matches."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=253,
                y=447,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                        action_point=(55, 66),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                        action_point=(155, 166),
                    ),
                ),
            ),
        )

        executor.execute_action(
            TapSpatialObjectAction(
                query=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                    name_text="Food Farm",
                    metadata_key="resource_type",
                    metadata_value="food",
                ),
                target_point=(155, 166),
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(155, 166)])

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

    def test_input_text_actions_use_selector_action_points_for_focus(self) -> None:
        """Focuses selector-backed text entry through the canonical action point instead of the bounds center."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_CHAT,
            visible_ids=(UiElementId.PNC_CHAT_INPUT_FIELD,),
            chat_draft_empty=True,
        )
        observation = Observation(
            screen_type=observation.screen_type,
            visible_elements={
                UiElementId.PNC_CHAT_INPUT_FIELD: make_visible(
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    x=20,
                    y=40,
                    width=90,
                    height=22,
                    action_point=(81, 55),
                )
            },
            image_size=observation.image_size,
            active_chat_channel=observation.active_chat_channel,
            chat_draft_empty=observation.chat_draft_empty,
            chat_draft_text=observation.chat_draft_text,
        )

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                text="hello",
                replace_existing=True,
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(81, 55)])
        self.assertEqual(executor.session.texts, ["hello"])

    def test_observed_action_executor_uses_action_scoped_follow_up_requests_for_non_navigation_actions(self) -> None:
        """Uses the action-provided follow-up request for observe-after actions that stay on the same screen."""

        fake_observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_CHAT)])
        fake_session = FakeSession()
        executor = _make_observed_action_executor(fake_session)

        execution = executor.execute_actions(
            (
                TapAction(
                    selector_id=UiElementId.PNC_CHAT_SEND_BUTTON,
                    reason="send_chat_message",
                    observe_after=True,
                    follow_up_request=ObservationRequest.chat_send_follow_up(),
                ),
            ),
            make_observation(ScreenType.PNC_CHAT, visible_ids=(UiElementId.PNC_CHAT_SEND_BUTTON,)),
            observe=fake_observer.observe,
        )

        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(fake_observer.requests, [ObservationRequest.chat_send_follow_up()])

    def test_select_chat_channel_action_skips_the_tap_when_the_requested_tab_is_already_active(self) -> None:
        """Avoids redundant chat-tab taps when the current observation already proves the active channel."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        action_executed = executor.execute_action(
            SelectChatChannelAction(channel=ChatChannel.ALLIANCE),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_TAB_ALLIANCE,),
                active_chat_channel=ChatChannel.ALLIANCE,
            ),
        )

        self.assertFalse(action_executed)
        self.assertEqual(executor.session.taps, [])

    def test_action_executor_skips_chat_channel_follow_up_when_the_requested_tab_is_already_active(self) -> None:
        """Skips both the tap and the observe-after follow-up when chat is already on the requested channel."""

        fake_observer = FakeObservationService(observations=[])
        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        result = executor.execute_actions(
            (
                SelectChatChannelAction(
                    channel=ChatChannel.ALLIANCE,
                    observe_after=True,
                    follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
                ),
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_TAB_ALLIANCE,),
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=True,
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertEqual(fake_observer.requests, [])

    def test_send_chat_message_stops_when_the_chat_tab_follow_up_stays_on_the_wrong_channel(self) -> None:
        """Refuses to type or send when the observed post-tap chat state still shows the previous channel."""

        fake_session = FakeSession()
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_CHAT,
                    visible_ids=(
                        UiElementId.PNC_CHAT_TAB_KINGDOM,
                        UiElementId.PNC_CHAT_TAB_ALLIANCE,
                        UiElementId.PNC_CHAT_INPUT_FIELD,
                        UiElementId.PNC_CHAT_SEND_BUTTON,
                    ),
                    active_chat_channel=ChatChannel.WORLD,
                    chat_draft_empty=True,
                )
            ]
        )
        executor = ActionExecutor(
            session=fake_session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        actions = ScreenFlowPlanner().send_chat_message(
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        result = executor.execute_actions(
            actions,
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.active_chat_channel, ChatChannel.WORLD)
        self.assertEqual(fake_observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT)])
        self.assertEqual(fake_session.texts, [])

    def test_send_chat_message_stops_when_the_chat_tab_follow_up_is_still_loading(self) -> None:
        """Stops before typing when the post-switch observation is still in a transient settling state."""

        fake_session = FakeSession()
        fake_observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_LOADING)])
        executor = ActionExecutor(
            session=fake_session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        actions = ScreenFlowPlanner().send_chat_message(
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        result = executor.execute_actions(
            actions,
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_LOADING)
        self.assertEqual(fake_observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT)])
        self.assertEqual(fake_session.texts, [])

    def test_send_chat_message_uses_the_post_switch_channel_draft_state_before_typing(self) -> None:
        """Refreshes chat state after a tab change and only types on the next chat-ready increment."""

        fake_session = FakeSession()
        executor = ActionExecutor(
            session=fake_session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        first_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_CHAT,
                    visible_ids=(
                        UiElementId.PNC_CHAT_TAB_KINGDOM,
                        UiElementId.PNC_CHAT_TAB_ALLIANCE,
                        UiElementId.PNC_CHAT_INPUT_FIELD,
                        UiElementId.PNC_CHAT_SEND_BUTTON,
                    ),
                    active_chat_channel=ChatChannel.ALLIANCE,
                    chat_draft_empty=False,
                    chat_draft_text="ally draft text here",
                )
            ]
        )
        first_actions = ScreenFlowPlanner().send_chat_message(
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=False,
                chat_draft_text="world draft text that should not be reused after switching tabs",
            ),
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        first_result = executor.execute_actions(
            first_actions,
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=False,
                chat_draft_text="world draft text that should not be reused after switching tabs",
            ),
            observe=first_observer.observe,
        )
        second_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_CHAT,
                    visible_ids=(
                        UiElementId.PNC_CHAT_TAB_KINGDOM,
                        UiElementId.PNC_CHAT_TAB_ALLIANCE,
                        UiElementId.PNC_CHAT_INPUT_FIELD,
                        UiElementId.PNC_CHAT_SEND_BUTTON,
                    ),
                    active_chat_channel=ChatChannel.ALLIANCE,
                    chat_draft_empty=True,
                )
            ]
        )
        second_actions = ScreenFlowPlanner().send_chat_message(
            first_result,
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        executor.execute_actions(
            second_actions,
            first_result,
            observe=second_observer.observe,
        )

        self.assertEqual(first_observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT)])
        self.assertEqual(second_observer.requests, [ObservationRequest.chat_send_follow_up()])
        self.assertEqual(fake_session.key_events[0], "KEYCODE_MOVE_END")
        self.assertEqual(fake_session.key_events.count("KEYCODE_DEL"), 28)
        self.assertEqual(fake_session.texts, ["hello"])

    def test_input_text_action_clears_an_existing_chat_draft_before_typing(self) -> None:
        """Uses the shared clear-and-replace policy instead of appending onto a stale chat draft."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                text="hello",
                replace_existing=True,
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_INPUT_FIELD,),
                chat_draft_empty=False,
                chat_draft_text="existing",
            ),
        )

        self.assertEqual(executor.session.key_events[0], "KEYCODE_MOVE_END")
        self.assertTrue(all(key_code == "KEYCODE_DEL" for key_code in executor.session.key_events[1:]))
        self.assertGreaterEqual(len(executor.session.key_events), 25)

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

    def test_observed_action_executor_settles_retry_destination_before_returning(self) -> None:
        """Waits through transient retry follow-up frames before returning the final OCR-retry destination."""

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
                make_observation(ScreenType.PNC_LOADING),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertEqual(
            fake_observer.labels,
            [
                "post_action_1",
                "post_action_1_ocr_retry_source",
                "post_action_1_ocr_retry_after",
                "post_action_1_ocr_retry_after_settle_1",
            ],
        )
        self.assertTrue(execution.selector_interactions[0].fallback_used)

    def test_observed_action_executor_hands_retry_popup_back_without_extra_settle(self) -> None:
        """Stops immediately when the OCR retry lands on a blocking popup so popup recovery can take over."""

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
                    ScreenType.PNC_POPUP,
                    visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                    blocking_popup=True,
                ),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_POPUP)
        self.assertEqual(
            fake_observer.labels,
            [
                "post_action_1",
                "post_action_1_ocr_retry_source",
                "post_action_1_ocr_retry_after",
            ],
        )

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

    def test_observed_action_executor_escalates_unknown_navigation_destination_to_full_runtime_observation(self) -> None:
        """Promotes settled unknown navigation results to one broad runtime observation before returning."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(ScreenType.UNKNOWN),
                make_observation(ScreenType.PNC_MORE_MENU, visible_ids=(UiElementId.PNC_MORE_SETTINGS,)),
            ),
            policy=ObservedActionExecutionPolicy(max_settle_observations=0),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertEqual(
            fake_observer.requests,
            [
                ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes),
                ObservationRequest.full_runtime_default(),
            ],
        )
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_preserves_same_screen_status_banner_without_settle_retry(self) -> None:
        """Keeps a same-screen status-banner frame as the final result so tasks can surface the live rejection reason."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_STATUS_BANNER),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(execution.observation.has(UiElementId.PNC_STATUS_BANNER))
        self.assertEqual(fake_observer.labels, ["post_action_1"])
        self.assertEqual(fake_observer.requests, [ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes)])
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_preserves_unknown_status_banner_without_runtime_retry(self) -> None:
        """Keeps transient status-banner observations even when the coarse follow-up screen is still unknown."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(make_observation(ScreenType.UNKNOWN, visible_ids=(UiElementId.PNC_STATUS_BANNER,)),),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.UNKNOWN)
        self.assertTrue(execution.observation.has(UiElementId.PNC_STATUS_BANNER))
        self.assertEqual(fake_observer.labels, ["post_action_1"])
        self.assertEqual(fake_observer.requests, [ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes)])
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


class _LocalBudgetReplanTask(BaseAutomationTask):
    """Synthetic task used to prove task-local replan budgets without changing the runner default."""

    id = TaskId.ENSURE_GAME_RUNNING

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Runs only when the shared synthetic selector is visible."""

        del context
        return observation.has(UiElementId.PNC_HOME_BUILD_BUTTON)

    def max_replans_per_step(self, context: TaskContext) -> int | None:
        """Allows exactly six replans for this one synthetic task."""

        del context
        return 6

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Does not emit actions because this test only exercises runner-side replan budgeting."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Replans six times and then succeeds without requiring new observations."""

        del before, after
        attempts = context.runtime_state.get("replan_attempts", 0)
        if not isinstance(attempts, int):
            raise AssertionError("Expected integer replan_attempts test state.")
        context.runtime_state["replan_attempts"] = attempts + 1
        if attempts >= 6:
            return TaskResult.success("Synthetic local-budget task exhausted its bounded replans cleanly.")
        return TaskResult.replan("Synthetic local-budget task is still exercising its private replan budget.")


class _AlwaysReplanTask(BaseAutomationTask):
    """Synthetic task used to prove replan-limit failures route through shared runner diagnostics."""

    id = TaskId.ENSURE_GAME_RUNNING

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Runs only when the shared synthetic selector is visible."""

        del context
        return observation.has(UiElementId.PNC_HOME_BUILD_BUTTON)

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Does not emit actions because this test exercises runner-side replan failure handling only."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Always requests another replan so the runner eventually hits its configured limit."""

        del context, before, after
        return TaskResult.replan("Synthetic replan-only task is still waiting for progress.")


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
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        ),
        logger=build_logger(),
        policy=ObservedActionExecutionPolicy() if policy is None else policy,
        sleep=lambda _: None,
    )


if __name__ == "__main__":
    unittest.main()

