from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import (
    ObservedActionExecutionPolicy,
    ObservedActionExecutor,
)
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.automation.engine.task import TaskPreflight
from pnc_automation.app.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.domain.action_requests import WaitAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from tests.test_support import FakeObservationService, FakeSession, build_logger, make_observation


class PopupRecoveryTests(unittest.TestCase):
    """Proves executor-owned transient interruption recovery invariants."""

    def setUp(self) -> None:
        self.session = FakeSession()
        self.executor = ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=ActionExecutor(
                session=self.session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                chat_stable_click_delay_ms=0,
                chat_post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            logger=build_logger(),
            policy=ObservedActionExecutionPolicy(update_max_popup_dismissals=2),
            sleep=lambda _: None,
        )

    def test_two_distinct_transient_popups_close_in_one_episode(self) -> None:
        popup_one = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="popup-one",
        )
        popup_two = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="popup-two",
        )
        home = make_observation(ScreenType.PNC_HOME_CITY)
        observer = FakeObservationService([popup_two, home])

        recovered = self.executor.recover_interruption_if_required(
            popup_one,
            label_prefix="transient",
            observe=observer.observe,
        )

        self.assertEqual(recovered, home)
        self.assertEqual(len(self.session.taps), 2)
        self.assertEqual(observer.requests, [ObservationRequest.full_runtime_default()] * 2)

    def test_repeated_fingerprint_is_not_tapped_twice_and_never_uses_back(self) -> None:
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="same-popup",
        )
        observer = FakeObservationService([popup])

        with self.assertRaisesRegex(SelectorResolutionError, "already consumed"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="repeated",
                observe=observer.observe,
            )

        self.assertEqual(len(self.session.taps), 1)
        self.assertEqual(self.session.key_events, [])

    def test_missing_safe_selector_fails_without_back(self) -> None:
        popup = make_observation(ScreenType.PNC_POPUP, blocking_popup=True)

        with self.assertRaisesRegex(SelectorResolutionError, "safe close selector"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="missing-selector",
                observe=lambda *_args, **_kwargs: self.fail("missing selector must not observe again"),
            )

        self.assertEqual(self.session.taps, [])
        self.assertEqual(self.session.key_events, [])

    def test_missing_fingerprint_fails_before_dispatch(self) -> None:
        popup = replace(
            make_observation(
                ScreenType.PNC_POPUP,
                visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                blocking_popup=True,
            ),
            frame_fingerprint=None,
        )

        with self.assertRaisesRegex(SelectorResolutionError, "frame fingerprint"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="missing-fingerprint",
                observe=lambda *_args, **_kwargs: self.fail("missing fingerprint must not observe again"),
            )

        self.assertEqual(self.session.taps, [])

    def test_task_owned_confirm_control_is_not_swallowed(self) -> None:
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON,
            ),
            blocking_popup=True,
        )

        with self.assertRaisesRegex(SelectorResolutionError, "safe close selector"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="task-owned",
                observe=lambda *_args, **_kwargs: self.fail("task-owned popup must not be dismissed"),
            )

        self.assertEqual(self.session.taps, [])

    def test_screen_flow_planner_rejects_untyped_popup_instead_of_using_back(self) -> None:
        popup = make_observation(ScreenType.PNC_POPUP, blocking_popup=True)

        with self.assertRaisesRegex(SelectorResolutionError, "Android Back is forbidden"):
            ScreenFlowPlanner().close_blocking_popup(popup)

    def test_screen_flow_planner_accepts_typed_vip_close_without_blocking_flag(self) -> None:
        """Keeps the typed VIP close action available when the classifier omitted the blocking bit."""

        vip = make_observation(
            ScreenType.PNC_VIP_DAILY_RESET,
            visible_ids=(UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,),
        )

        actions = ScreenFlowPlanner().close_blocking_popup(vip)

        self.assertEqual(actions[0].selector_id, UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON)

    def test_post_action_popup_is_recovered_before_result_is_returned(self) -> None:
        initial = make_observation(ScreenType.PNC_HOME_CITY)
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="post-action-popup",
        )
        home = make_observation(ScreenType.PNC_HOME_CITY)
        observer = FakeObservationService([popup, home])

        result = self.executor.execute_actions(
            [WaitAction(milliseconds=0, reason="test_post_action", observe_after=True)],
            initial,
            observe=observer.observe,
        )

        self.assertEqual(result.observation, home)
        self.assertFalse(result.update_recovered)
        self.assertEqual(len(self.session.taps), 1)

    def test_preflight_popup_recovery_does_not_consume_navigation_budget(self) -> None:
        """Closes one safe preflight offer before a zero-step Home proof is evaluated."""

        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="preflight-popup",
        )
        home = make_observation(ScreenType.PNC_HOME_CITY)
        observer = FakeObservationService([home])
        runner = AutomationRunner(
            defaults=SimpleNamespace(),
            observation_service=observer,
            action_executor=self.executor,
            task_registry=SimpleNamespace(),
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        recovered = runner.prove_preflight_state(
            account=SimpleNamespace(),
            requirement=TaskPreflight.HOME_CITY,
            label_prefix="preflight",
            start_observation=popup,
            max_steps=0,
        )

        self.assertEqual(recovered, home)
        self.assertEqual(len(self.session.taps), 1)
        self.assertEqual(observer.requests, [ObservationRequest.full_runtime_default()])

    def test_castle_switch_join_alliance_landing_replans_to_home(self) -> None:
        target = CastleIdentity("K157", "NPC 2", 22)
        context = SimpleNamespace(require_target_castle=lambda: target, castle_roster=None)
        before = make_observation(ScreenType.PNC_CASTLE_SELECTION)
        after = make_observation(ScreenType.PNC_ALLIANCE_JOIN)

        result = SelectCastleTask().verify(context, before, after)

        self.assertEqual(result.status.value, "replan")
        self.assertIn("returning to Home", result.message)


if __name__ == "__main__":
    unittest.main()
