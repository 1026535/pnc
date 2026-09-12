from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
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
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    PopupDismissCandidate,
    PopupEvidenceKind,
    PopupOverlayObservation,
    decide_popup_recovery,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from tests.test_support import FakeObservationService, FakeSession, build_logger, make_observation
from pnc_automation.core.vision.image.models import Bounds


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

    def test_popup_overlay_preserves_multiple_descriptive_candidates_without_authorizing_one(self) -> None:
        candidates = (
            PopupDismissCandidate(
                control_kind=PopupControlKind.CANCEL,
                bounds=Bounds(20, 60, 40, 20),
                action_point=(40, 70),
                confidence=0.95,
                evidence_kind=PopupEvidenceKind.OCR_TEXT,
                extracted_text="Cancel",
            ),
            PopupDismissCandidate(
                control_kind=PopupControlKind.CLOSE_X,
                bounds=Bounds(140, 10, 20, 20),
                action_point=(150, 20),
                confidence=0.8,
                evidence_kind=PopupEvidenceKind.GEOMETRY,
            ),
        )
        overlay = PopupOverlayObservation(image_size=(200, 100), candidates=candidates)
        self.assertEqual(tuple(candidate.control_kind for candidate in overlay.candidates), (
            PopupControlKind.CANCEL,
            PopupControlKind.CLOSE_X,
        ))

    def test_popup_overlay_rejects_out_of_image_or_duplicate_candidates(self) -> None:
        candidate = PopupDismissCandidate(
            control_kind=PopupControlKind.CLOSE_X,
            bounds=Bounds(190, 90, 20, 20),
            action_point=(195, 95),
            confidence=1.0,
            evidence_kind=PopupEvidenceKind.GEOMETRY,
        )
        with self.assertRaises(SelectorResolutionError):
            PopupOverlayObservation(image_size=(200, 100), candidates=(candidate,))
        valid = PopupDismissCandidate(
            control_kind=PopupControlKind.CLOSE_X,
            bounds=Bounds(150, 10, 20, 20),
            action_point=(160, 20),
            confidence=1.0,
            evidence_kind=PopupEvidenceKind.GEOMETRY,
        )
        with self.assertRaises(SelectorResolutionError):
            PopupOverlayObservation(image_size=(200, 100), candidates=(valid, valid))

    def test_generic_popup_overlay_requires_modal_ownership(self) -> None:
        candidate = PopupDismissCandidate(
            control_kind=PopupControlKind.CANCEL,
            bounds=Bounds(20, 60, 40, 20),
            action_point=(40, 70),
            confidence=0.95,
            evidence_kind=PopupEvidenceKind.OCR_TEXT,
        )

        with self.assertRaisesRegex(SelectorResolutionError, "measured modal ownership"):
            PopupOverlayObservation(
                image_size=(200, 100),
                layout_id="generic_modal_negative",
                candidates=(candidate,),
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

        with self.assertRaisesRegex(SelectorResolutionError, "unchanged visual fingerprint"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="repeated",
                observe=observer.observe,
            )

        self.assertEqual(len(self.session.taps), 1)
        self.assertEqual(self.session.key_events, [])

    def test_animated_typed_popup_identity_is_settled_without_a_second_tap(self) -> None:
        popup = self._typed_popup("savannah_offer", "popup-before")
        animated = self._typed_popup("savannah_offer", "popup-animated")
        observer = FakeObservationService([animated, make_observation(ScreenType.PNC_HOME_CITY)])

        recovered = self.executor.recover_interruption_if_required(
            popup,
            label_prefix="animated-typed",
            observe=observer.observe,
        )

        self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
        self.assertEqual(1, len(self.session.taps))

    def test_typed_popup_identity_ignores_jittered_geometry_and_ocr(self) -> None:
        popup = self._typed_popup("savannah_offer", "popup-before")
        animated = self._typed_popup("savannah_offer", "popup-animated", action_point=(120, 40))
        assert animated.popup_overlay is not None
        candidate = animated.popup_overlay.candidates[0]
        jittered_candidate = replace(
            candidate,
            bounds=Bounds(90, 25, 40, 30),
            action_point=(110, 40),
            extracted_text="Animated offer text",
        )
        animated = replace(
            animated,
            popup_overlay=replace(animated.popup_overlay, candidates=(jittered_candidate,)),
        )
        observer = FakeObservationService([animated, make_observation(ScreenType.PNC_HOME_CITY)])

        recovered = self.executor.recover_interruption_if_required(
            popup,
            label_prefix="jittered-typed",
            observe=observer.observe,
        )

        self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
        self.assertEqual(1, len(self.session.taps))

    def test_stale_typed_settle_observation_fails_closed_before_new_tap(self) -> None:
        popup = self._typed_popup("savannah_offer", "popup-before")
        base_time = popup.captured_at
        popup = replace(popup, captured_at=base_time)
        animated = replace(
            self._typed_popup("savannah_offer", "popup-animated"),
            captured_at=base_time + timedelta(seconds=1),
        )
        stale_stacked = replace(
            self._typed_popup("vip_reset", "popup-stale", action_point=(120, 35)),
            captured_at=base_time + timedelta(seconds=1),
        )
        home = replace(
            make_observation(ScreenType.PNC_HOME_CITY),
            captured_at=base_time + timedelta(seconds=2),
        )
        observer = FakeObservationService([animated, stale_stacked, home])

        with self.assertRaisesRegex(SelectorResolutionError, "semantic settle received a stale observation"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="stale-typed-settle",
                observe=observer.observe,
            )

        self.assertEqual(1, len(self.session.taps))

    def test_persistent_typed_popup_identity_fails_closed_after_one_tap(self) -> None:
        popup = self._typed_popup("savannah_offer", "popup-before")
        observer = FakeObservationService([
            self._typed_popup("savannah_offer", "popup-animated-1"),
            self._typed_popup("savannah_offer", "popup-animated-2"),
            self._typed_popup("savannah_offer", "popup-animated-3"),
            self._typed_popup("savannah_offer", "popup-animated-4"),
        ])

        with self.assertRaisesRegex(SelectorResolutionError, "same typed identity"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="persistent-typed",
                observe=observer.observe,
            )

        self.assertEqual(1, len(self.session.taps))

    def test_distinct_typed_popup_identities_may_be_dismissed_as_stacked(self) -> None:
        popup = self._typed_popup("savannah_offer", "popup-one")
        stacked = self._typed_popup("vip_reset", "popup-two", action_point=(120, 35))
        observer = FakeObservationService([stacked, make_observation(ScreenType.PNC_HOME_CITY)])

        recovered = self.executor.recover_interruption_if_required(
            popup,
            label_prefix="stacked-typed",
            observe=observer.observe,
        )

        self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
        self.assertEqual(2, len(self.session.taps))

    def test_post_update_animated_typed_popup_identity_is_settled_without_a_second_tap(self) -> None:
        update_candidate = PopupDismissCandidate(
            control_kind=PopupControlKind.UPDATE_CONFIRM,
            bounds=Bounds(70, 60, 50, 20),
            action_point=(95, 70),
            confidence=0.95,
            evidence_kind=PopupEvidenceKind.OCR_TEXT,
        )
        update = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="update-before",
            popup_overlay=PopupOverlayObservation(
                image_size=(200, 100),
                layout_id="required_update",
                candidates=(update_candidate,),
            ),
        )
        animated = self._typed_popup("savannah_offer", "popup-after-update-1")
        animated_later = self._typed_popup("savannah_offer", "popup-after-update-2")
        home = make_observation(ScreenType.PNC_HOME_CITY)
        base_time = update.captured_at
        update = replace(update, captured_at=base_time)
        animated = replace(animated, captured_at=base_time + timedelta(seconds=1))
        animated_later = replace(animated_later, captured_at=base_time + timedelta(seconds=2))
        home = replace(home, captured_at=base_time + timedelta(seconds=3))

        recovered = self.executor.recover_interruption_if_required(
            update,
            label_prefix="post-update-animated",
            observe=FakeObservationService([animated, animated_later, home]).observe,
        )

        self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
        self.assertEqual([(95, 70), (160, 35)], self.session.taps)

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

    def test_reconnect_selector_without_typed_evidence_is_not_authorized(self) -> None:
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_RECONNECT_CONFIRM_BUTTON,),
            blocking_popup=True,
        )

        with self.assertRaisesRegex(SelectorResolutionError, "safe close selector"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="untyped-reconnect",
                observe=lambda *_args, **_kwargs: self.fail("untyped reconnect must not be dispatched"),
            )

        self.assertEqual(self.session.taps, [])

    def test_selected_popup_candidate_action_point_is_dispatched(self) -> None:
        close_x = PopupDismissCandidate(
            control_kind=PopupControlKind.CLOSE_X,
            bounds=Bounds(140, 25, 20, 20),
            action_point=(150, 35),
            confidence=0.99,
            evidence_kind=PopupEvidenceKind.GEOMETRY,
        )
        cancel = PopupDismissCandidate(
            control_kind=PopupControlKind.CANCEL,
            bounds=Bounds(120, 60, 50, 20),
            action_point=(163, 71),
            confidence=0.96,
            evidence_kind=PopupEvidenceKind.OCR_TEXT,
            extracted_text="Cancel",
        )
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="candidate-point",
            popup_overlay=PopupOverlayObservation(
                image_size=(200, 100),
                modal_bounds=Bounds(20, 20, 160, 75),
                layout_id="generic_modal_negative",
                candidates=(close_x, cancel),
            ),
        )
        observer = FakeObservationService([make_observation(ScreenType.PNC_HOME_CITY)])

        self.executor.recover_interruption_if_required(
            popup,
            label_prefix="candidate-point",
            observe=observer.observe,
        )

        self.assertEqual(self.session.taps, [(163, 71)])

    def test_planner_and_executor_share_one_popup_recovery_decision(self) -> None:
        """Planning and dispatch consume the same typed authorization result."""

        cancel = PopupDismissCandidate(
            control_kind=PopupControlKind.CANCEL,
            bounds=Bounds(120, 60, 50, 20),
            action_point=(145, 70),
            confidence=0.96,
            evidence_kind=PopupEvidenceKind.OCR_TEXT,
            extracted_text="Cancel",
        )
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            popup_overlay=PopupOverlayObservation(
                image_size=(200, 100),
                modal_bounds=Bounds(20, 20, 160, 75),
                layout_id="generic_modal_negative",
                candidates=(cancel,),
            ),
        )
        decision = decide_popup_recovery(
            screen_type=popup.screen_type,
            blocking_popup=popup.blocking_popup,
            visible_selector_ids=frozenset(popup.visible_elements),
            popup_overlay=popup.popup_overlay,
        )
        action = ScreenFlowPlanner().close_blocking_popup(popup)[0]

        self.assertIsNotNone(decision)
        self.assertEqual(decision.selector_id, action.selector_id)
        self.assertEqual(decision.reason, action.reason)

    def test_screen_flow_planner_rejects_untyped_reconnect_confirm(self) -> None:
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_RECONNECT_CONFIRM_BUTTON,),
            blocking_popup=True,
        )

        with self.assertRaisesRegex(SelectorResolutionError, "Android Back is forbidden"):
            ScreenFlowPlanner().close_blocking_popup(popup)

    def test_screen_flow_planner_rejects_task_owned_control_beside_generic_close(self) -> None:
        close_x = PopupDismissCandidate(
            control_kind=PopupControlKind.CLOSE_X,
            bounds=Bounds(140, 10, 20, 20),
            action_point=(150, 20),
            confidence=0.95,
            evidence_kind=PopupEvidenceKind.GEOMETRY,
        )
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON,
            ),
            blocking_popup=True,
            popup_overlay=PopupOverlayObservation(
                image_size=(200, 100),
                layout_id="recognized_offer",
                candidates=(close_x,),
            ),
        )

        with self.assertRaisesRegex(SelectorResolutionError, "Task-owned popup controls"):
            ScreenFlowPlanner().close_blocking_popup(popup)

    def test_different_fingerprint_from_stale_capture_is_rejected(self) -> None:
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="popup-before",
        )
        stale = replace(
            make_observation(ScreenType.PNC_HOME_CITY, frame_fingerprint="different-old-frame"),
            captured_at=popup.captured_at - timedelta(seconds=1),
        )
        observer = FakeObservationService([stale])

        with self.assertRaisesRegex(SelectorResolutionError, "stale post-dispatch observation"):
            self.executor.recover_interruption_if_required(
                popup,
                label_prefix="stale-capture",
                observe=observer.observe,
            )

        self.assertEqual(len(self.session.taps), 1)

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

    @staticmethod
    def _typed_popup(
        layout_id: str,
        frame_fingerprint: str,
        *,
        action_point: tuple[int, int] = (160, 35),
    ) -> Observation:
        bounds = Bounds(action_point[0] - 10, action_point[1] - 10, 20, 20)
        candidate = PopupDismissCandidate(
            control_kind=PopupControlKind.CLOSE_X,
            bounds=bounds,
            action_point=action_point,
            confidence=0.95,
            evidence_kind=PopupEvidenceKind.GEOMETRY,
            reason=layout_id,
        )
        return make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint=frame_fingerprint,
            popup_overlay=PopupOverlayObservation(
                image_size=(200, 100),
                layout_id=layout_id,
                reason=layout_id,
                candidates=(candidate,),
            ),
        )


if __name__ == "__main__":
    unittest.main()
