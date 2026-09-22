"""Captured known-popup and generic visual fallback acceptance coverage."""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import replace
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import VisibleElement
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    PopupDismissCandidate,
    PopupEvidenceKind,
    PopupOverlayObservation,
    decide_popup_recovery,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationAdditions,
    ObservationBuilder,
    reconcile_visual_modal_guard,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.automation.engine.make_observed_action_executor import _make_observed_action_executor
from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService


FIXTURES = TEST_DATA_ROOT / "screen_recognition"


def _capture(name: str) -> CapturedScreenshot:
    with Image.open(FIXTURES / name) as source:
        image = source.convert("RGB")
    captured_at = datetime.now(UTC)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        frame_ref=FrameRef(
            session_id=f"known-popup:{name}",
            session_epoch=1,
            capture_sequence=1,
            input_sequence=0,
            captured_at=captured_at,
        ),
        ephemeral_captured_at=captured_at,
    )


def _native_capture(name: str, *, session: str, capture_sequence: int) -> CapturedScreenshot:
    with Image.open(FIXTURES / name) as source:
        image = source.copy()
    captured_at = datetime.now(UTC)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        frame_ref=FrameRef(
            session_id=session,
            session_epoch=1,
            capture_sequence=capture_sequence,
            input_sequence=0,
            captured_at=captured_at,
        ),
        ephemeral_captured_at=captured_at,
    )


def _wire() -> tuple[ObservationBuilder, NavigationPerception]:
    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(selector_registry=registry)
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        ocr_service=_RecordingOcrService(lines=()),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )
    return builder, NavigationPerception(
        builder.visual_recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )


class KnownPopupRecognitionTests(unittest.TestCase):
    """Require both production publication paths to agree on captured popups."""

    def test_known_profiles_publish_typed_controls_through_builder_and_navigation(self) -> None:
        builder, navigation = _wire()
        expected = {
            "king_return_welcome.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_KING_RETURN_GET_STARTED_BUTTON,
                PopupControlKind.KING_RETURN_GET_STARTED,
                "king_return_welcome",
            ),
            "savannah_hero_offer.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                PopupControlKind.CLOSE_X,
                "hero_offer_full_height",
            ),
            "savannah_hero_offer_fresh_900.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                PopupControlKind.CLOSE_X,
                "hero_offer_full_height",
            ),
            "savannah_hero_offer_holdout_900_second.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                PopupControlKind.CLOSE_X,
                "hero_offer_full_height",
            ),
            "savannah_hero_offer_serious_stuff_holdout.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                PopupControlKind.CLOSE_X,
                "hero_offer_full_height",
            ),
            "savannah_hero_offer_mega_old_acc_holdout_900.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                PopupControlKind.CLOSE_X,
                "hero_offer_full_height",
            ),
            "lucifer_special_offer.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                PopupControlKind.POPUP_BACK,
                "lucifer_special_offer_full_height",
            ),
            "growth_boost_weekly_pass.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                PopupControlKind.POPUP_BACK,
                "growth_boost_weekly_pass_full_height",
            ),
            "vip_daily_reset.png": (
                ScreenType.PNC_VIP_DAILY_RESET,
                UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
                PopupControlKind.CLOSE_TEXT,
                "vip_daily_reset",
            ),
            "valiant_conquest.png": (
                ScreenType.PNC_POPUP,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                PopupControlKind.CLOSE_X,
                "valiant_conquest",
            ),
        }
        for name, (screen, selector, control_kind, layout_id) in expected.items():
            with self.subTest(name=name):
                capture = _capture(name)
                observations = (builder.build(capture), navigation.build(capture))
                for observation in observations:
                    self.assertEqual(observation.screen_type, screen)
                    self.assertEqual(observation.decision.guard.value, "blocked")
                    self.assertTrue(observation.has(selector))
                    self.assertEqual(observation.popup_overlay.layout_id, layout_id)
                    candidate = observation.popup_overlay.candidate(control_kind)
                    self.assertIsNotNone(candidate)
                    close = observation.require(selector)
                    self.assertEqual(candidate.action_point, close.action_point)
                    self.assertEqual(candidate.bounds, close.bounds)
                    self.assertEqual(close.frame_ref, capture.frame_ref)
                    self.assertEqual(close.source_screen, screen)
                    self.assertEqual(close.source_layout_id, layout_id)

    def test_delayed_lucifer_offer_after_brief_home_frame_publishes_on_both_paths(self) -> None:
        """The captured Home then delayed-Lucifer sequence stays demand-driven in one session."""

        builder, navigation = _wire()
        home = _native_capture(
            "home_city_startup_gap_20260922.png", session="startup-gap:2026-09-22", capture_sequence=11
        )
        lucifer = _native_capture(
            "lucifer_special_offer_startup_gap_20260922.png",
            session="startup-gap:2026-09-22",
            capture_sequence=26,
        )
        for captured in (home, lucifer):
            self.assertEqual(("RGBA", (900, 1600)), (captured.image.mode, captured.image.size))

        for observation in (builder.build(home), navigation.build(home)):
            self.assertEqual(ScreenType.PNC_HOME_CITY, observation.screen_type)

        for observation in (builder.build(lucifer), navigation.build(lucifer)):
            self.assertEqual(ScreenType.PNC_POPUP, observation.screen_type)
            self.assertEqual("blocked", observation.decision.guard.value)
            self.assertEqual("lucifer_special_offer_full_height", observation.decision.layout_id)
            self.assertTrue(observation.blocking_popup)
            self.assertEqual({UiElementId.PNC_POPUP_CLOSE_BUTTON}, set(observation.visible_elements))
            overlay = observation.popup_overlay
            self.assertIsNotNone(overlay)
            self.assertEqual("lucifer_special_offer_full_height", overlay.layout_id)
            candidate = overlay.candidate(PopupControlKind.POPUP_BACK)
            self.assertIsNotNone(candidate)
            self.assertEqual(Bounds(30, 13, 100, 95), candidate.bounds)
            self.assertEqual((80, 60), candidate.action_point)
            close = observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON)
            self.assertEqual(candidate.bounds, close.bounds)
            self.assertEqual(candidate.action_point, close.action_point)
            self.assertEqual(close.frame_ref, lucifer.frame_ref)
            self.assertEqual(ScreenType.PNC_POPUP, close.source_screen)
            self.assertEqual("lucifer_special_offer_full_height", close.source_layout_id)
            decision = decide_popup_recovery(
                screen_type=observation.screen_type,
                blocking_popup=observation.blocking_popup,
                visible_selector_ids=frozenset(observation.visible_elements),
                popup_overlay=overlay,
            )
            self.assertEqual(UiElementId.PNC_POPUP_CLOSE_BUTTON, decision.selector_id)

        session = FakeSession()
        observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_HOME_CITY)])
        recovered = _make_observed_action_executor(session).recover_interruption_if_required(
            builder.build(lucifer),
            label_prefix="delayed_lucifer",
            observe=observer.observe,
        )
        self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
        self.assertEqual([(80, 60)], session.taps)
        self.assertEqual([], session.key_events)

    def test_growth_boost_weekly_pass_after_home_frame_publishes_on_both_paths(self) -> None:
        """The captured Home then Growth Boost Weekly Pass sequence stays demand-driven in one session."""

        builder, navigation = _wire()
        home = _native_capture(
            "home_city_before_growth_boost_20260922.png",
            session="hopium-gap:2026-09-22",
            capture_sequence=56,
        )
        offer = _native_capture(
            "growth_boost_weekly_pass.png", session="hopium-gap:2026-09-22", capture_sequence=71
        )
        for captured in (home, offer):
            self.assertEqual(("RGBA", (900, 1600)), (captured.image.mode, captured.image.size))

        for observation in (builder.build(home), navigation.build(home)):
            self.assertEqual(ScreenType.PNC_HOME_CITY, observation.screen_type)

        for observation in (builder.build(offer), navigation.build(offer)):
            self.assertEqual(ScreenType.PNC_POPUP, observation.screen_type)
            self.assertEqual("blocked", observation.decision.guard.value)
            self.assertEqual("growth_boost_weekly_pass_full_height", observation.decision.layout_id)
            self.assertTrue(observation.blocking_popup)
            self.assertEqual({UiElementId.PNC_POPUP_CLOSE_BUTTON}, set(observation.visible_elements))
            overlay = observation.popup_overlay
            self.assertIsNotNone(overlay)
            self.assertEqual("growth_boost_weekly_pass_full_height", overlay.layout_id)
            candidate = overlay.candidate(PopupControlKind.POPUP_BACK)
            self.assertIsNotNone(candidate)
            self.assertEqual(Bounds(30, 7, 110, 96), candidate.bounds)
            self.assertEqual((85, 55), candidate.action_point)
            close = observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON)
            self.assertEqual(candidate.bounds, close.bounds)
            self.assertEqual(candidate.action_point, close.action_point)
            self.assertEqual(close.frame_ref, offer.frame_ref)
            self.assertEqual(ScreenType.PNC_POPUP, close.source_screen)
            self.assertEqual("growth_boost_weekly_pass_full_height", close.source_layout_id)
            decision = decide_popup_recovery(
                screen_type=observation.screen_type,
                blocking_popup=observation.blocking_popup,
                visible_selector_ids=frozenset(observation.visible_elements),
                popup_overlay=overlay,
            )
            self.assertEqual(UiElementId.PNC_POPUP_CLOSE_BUTTON, decision.selector_id)

        session = FakeSession()
        observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_HOME_CITY)])
        recovered = _make_observed_action_executor(session).recover_interruption_if_required(
            builder.build(offer),
            label_prefix="growth_boost_weekly_pass",
            observe=observer.observe,
        )
        self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
        self.assertEqual([(85, 55)], session.taps)
        self.assertEqual([], session.key_events)

    def test_growth_boost_requires_independent_identity_regions_and_measured_back(self) -> None:
        """Each static identity region is required, and the back control alone cannot be invented."""

        builder, navigation = _wire()
        source = _capture("growth_boost_weekly_pass.png")

        for missing, box in (
            ("title", (160, 5, 775, 95)),
            ("center_art", (260, 135, 775, 320)),
        ):
            with self.subTest(missing=missing):
                missing_identity = source.image.copy()
                ImageDraw.Draw(missing_identity).rectangle(box, fill=(18, 24, 38))
                identity_capture = replace(source, image=missing_identity)
                for observation in (
                    builder.build(identity_capture),
                    navigation.build(identity_capture),
                ):
                    self.assertNotEqual(
                        "growth_boost_weekly_pass_full_height", observation.decision.layout_id
                    )
                    self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

        missing_control = source.image.copy()
        ImageDraw.Draw(missing_control).rectangle((20, 0, 150, 115), fill=(10, 30, 60))
        control_capture = replace(source, image=missing_control)
        for observation in (builder.build(control_capture), navigation.build(control_capture)):
            self.assertEqual(ScreenType.PNC_POPUP, observation.screen_type)
            self.assertEqual("growth_boost_weekly_pass_full_height", observation.decision.layout_id)
            self.assertTrue(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
            self.assertEqual((), observation.popup_overlay.candidates)

    def test_king_return_welcome_uses_one_measured_get_started_tap(self) -> None:
        """Both publishers can dismiss the exact welcome and recapture Home."""

        builder, navigation = _wire()
        capture = _capture("king_return_welcome.png")
        for observation in (builder.build(capture), navigation.build(capture)):
            with self.subTest(publisher=type(observation).__name__):
                selector = UiElementId.PNC_KING_RETURN_GET_STARTED_BUTTON
                decision = decide_popup_recovery(
                    screen_type=observation.screen_type,
                    blocking_popup=observation.blocking_popup,
                    visible_selector_ids=frozenset(observation.visible_elements),
                    popup_overlay=observation.popup_overlay,
                )
                self.assertEqual(selector, decision.selector_id)
                session = FakeSession()
                observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_HOME_CITY)])
                recovered = _make_observed_action_executor(session).recover_interruption_if_required(
                    observation, label_prefix="king_return_welcome", observe=observer.observe,
                )
                self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
                self.assertEqual([observation.require(selector).action_point], session.taps)
                self.assertEqual([], session.key_events)

    def test_king_return_welcome_needs_identity_and_button(self) -> None:
        """The button alone and unrelated offers cannot authorize this action."""

        builder, navigation = _wire()
        source = _capture("king_return_welcome.png")
        without_staff = source.image.copy()
        ImageDraw.Draw(without_staff).rectangle((575, 215, 780, 415), fill=(18, 24, 38))
        without_button = source.image.copy()
        ImageDraw.Draw(without_button).rectangle((355, 825, 590, 920), fill=(18, 24, 38))
        for image, keeps_identity in ((without_staff, False), (without_button, True)):
            for observation in (
                builder.build(replace(source, image=image)),
                navigation.build(replace(source, image=image)),
            ):
                with self.subTest(keeps_identity=keeps_identity):
                    self.assertEqual(
                        keeps_identity,
                        observation.decision.layout_id == "king_return_welcome",
                    )
                    self.assertFalse(observation.has(UiElementId.PNC_KING_RETURN_GET_STARTED_BUTTON))
        for name in ("savannah_hero_offer.png", "lucifer_special_offer.png", "home_city_popup_x_regression.png"):
            with self.subTest(unrelated=name):
                observation = builder.build(_capture(name))
                self.assertFalse(observation.has(UiElementId.PNC_KING_RETURN_GET_STARTED_BUTTON))

        observation = builder.build(source)
        wrong_layout = replace(observation.popup_overlay, layout_id="unrelated_get_started")
        decision = decide_popup_recovery(
            screen_type=observation.screen_type,
            blocking_popup=observation.blocking_popup,
            visible_selector_ids=frozenset(observation.visible_elements),
            popup_overlay=wrong_layout,
        )
        self.assertIsNone(decision.selector_id)
        for kind, selector in (
            (PopupControlKind.UPDATE_CONFIRM, UiElementId.PNC_UPDATE_CONFIRM_BUTTON),
            (PopupControlKind.RECONNECT_CONFIRM, UiElementId.PNC_RECONNECT_CONFIRM_BUTTON),
        ):
            with self.subTest(priority=kind):
                start = observation.popup_overlay.candidate(PopupControlKind.KING_RETURN_GET_STARTED)
                self.assertIsNotNone(start)
                competing = replace(start, control_kind=kind)
                overlay = replace(
                    observation.popup_overlay,
                    candidates=(competing, *observation.popup_overlay.candidates),
                )
                decision = decide_popup_recovery(
                    screen_type=observation.screen_type,
                    blocking_popup=observation.blocking_popup,
                    visible_selector_ids=frozenset((*observation.visible_elements, selector)),
                    popup_overlay=overlay,
                )
                self.assertEqual(selector, decision.selector_id)

    def test_generic_fallback_owns_raw_savannah_when_named_profiles_are_filtered(self) -> None:
        builder, navigation = _wire()
        recognizer = builder.visual_recognizer
        assert recognizer is not None
        builder.visual_recognizer = replace(
            recognizer,
            profiles=tuple(
                profile
                for profile in recognizer.profiles
                if not profile.id.startswith("savannah_hero_offer")
            ),
        )
        navigation = replace(navigation, recognizer=builder.visual_recognizer)
        for name in (
            "savannah_hero_offer.png",
            "savannah_hero_offer_fresh_900.png",
            "savannah_hero_offer_holdout_900_second.png",
            "savannah_hero_offer_serious_stuff_holdout.png",
            "savannah_hero_offer_mega_old_acc_holdout_900.png",
        ):
            capture = _capture(name)
            for observation in (builder.build(capture), navigation.build(capture)):
                with self.subTest(name=name, path=type(observation).__name__):
                    self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                    self.assertEqual(observation.decision.guard.value, "blocked")
                    self.assertEqual(observation.popup_overlay.layout_id, "visual_modal_close_x")
                    self.assertIsNotNone(observation.popup_overlay.modal_bounds)
                    candidate = observation.popup_overlay.candidate(PopupControlKind.CLOSE_X)
                    self.assertIsNotNone(candidate)
                    point = observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON).action_point
                    self.assertEqual(observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON).frame_ref, capture.frame_ref)
                    self.assertEqual(observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON).source_layout_id, "visual_modal_close_x")
                    self.assertLessEqual(abs(point[0] - round(503 * capture.image.width / 540)), 2)
                    self.assertLessEqual(abs(point[1] - round(79 * capture.image.height / 960)), 2)

    def test_known_identity_without_control_blocks_without_action(self) -> None:
        builder, navigation = _wire()
        image = _capture("savannah_hero_offer.png").image
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((475, 45, 530, 110), fill=(20, 25, 35))
        capture = CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))
        for observation in (builder.build(capture), navigation.build(capture)):
            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
            self.assertEqual(observation.popup_overlay.candidates, ())

    def test_lucifer_requires_independent_artwork_and_separate_popup_back(self) -> None:
        builder, navigation = _wire()
        source = _capture("lucifer_special_offer.png")

        missing_identity = source.image.copy()
        ImageDraw.Draw(missing_identity).rectangle((360, 125, 605, 475), fill=(18, 24, 38))
        identity_capture = replace(source, image=missing_identity)
        for observation in (builder.build(identity_capture), navigation.build(identity_capture)):
            self.assertNotEqual(observation.decision.layout_id, "lucifer_special_offer_full_height")
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

        missing_control = source.image.copy()
        ImageDraw.Draw(missing_control).rectangle((20, 5, 140, 120), fill=(93, 81, 82))
        control_capture = replace(source, image=missing_control)
        for observation in (builder.build(control_capture), navigation.build(control_capture)):
            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertEqual(observation.decision.layout_id, "lucifer_special_offer_full_height")
            self.assertTrue(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
            self.assertEqual((), observation.popup_overlay.candidates)

    def test_exact_update_and_reconnect_guards_win_over_same_family_visual_profiles(self) -> None:
        """Exact OCR actions stay authoritative over a coincident popup profile."""

        builder, _navigation = _wire()
        capture = _capture("savannah_hero_offer.png")
        visual = builder.visual_recognizer.recognize(capture.image)
        for kind, selector, layout_id in (
            (
                PopupControlKind.UPDATE_CONFIRM,
                UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
                "required_game_update",
            ),
            (
                PopupControlKind.RECONNECT_CONFIRM,
                UiElementId.PNC_RECONNECT_CONFIRM_BUTTON,
                "disconnect_reconnect",
            ),
        ):
            with self.subTest(kind=kind):
                bounds = Bounds(200, 600, 140, 60)
                control = VisibleElement(selector, bounds, 1.0)
                overlay = PopupOverlayObservation(
                    image_size=capture.image.size,
                    layout_id=layout_id,
                    candidates=(PopupDismissCandidate(
                        control_kind=kind,
                        bounds=bounds,
                        action_point=bounds.center(),
                        confidence=1.0,
                        evidence_kind=PopupEvidenceKind.OCR_TEXT,
                    ),),
                    confidence=1.0,
                    evidence_kind=PopupEvidenceKind.OCR_TEXT,
                )
                guard = ObservationAdditions(
                    visible_elements={selector: control},
                    screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, layout_id),),
                    popup_overlay=overlay,
                    guard_verdict=GuardVerdict.BLOCKED,
                )
                reconciled = reconcile_visual_modal_guard(visual, guard)
                self.assertEqual(reconciled, guard)

    def test_vip_independent_holdouts_publish_blocking_close_on_both_paths(self) -> None:
        """Independent VIP captures prove static identity and current-frame Close geometry."""

        builder, navigation = _wire()
        for name in (
            "vip_daily_reset_holdout_900.png",
            "vip_daily_reset_serious_stuff_holdout_1.png",
            "vip_daily_reset_serious_stuff_holdout_2.png",
        ):
            capture = _capture(name)
            for observation in (builder.build(capture), navigation.build(capture)):
                with self.subTest(name=name, path=type(observation).__name__):
                    self.assertEqual(observation.screen_type, ScreenType.PNC_VIP_DAILY_RESET)
                    self.assertEqual(observation.decision.guard.value, "blocked")
                    close = observation.require(UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON)
                    self.assertEqual(close.frame_ref, capture.frame_ref)
                    self.assertEqual(close.source_layout_id, "vip_daily_reset")
                    overlay = observation.popup_overlay
                    self.assertIsNotNone(overlay)
                    assert overlay is not None
                    self.assertEqual(overlay.layout_id, "vip_daily_reset")
                    candidate = overlay.candidate(PopupControlKind.CLOSE_TEXT)
                    self.assertIsNotNone(candidate)
                    assert candidate is not None
                    self.assertEqual(candidate.action_point, close.action_point)

    def test_vip_identity_without_close_blocks_without_action_on_both_paths(self) -> None:
        """VIP identity remains blocking when its independently measured Close is absent."""

        source = _capture("vip_daily_reset_serious_stuff_holdout_1.png")
        image = source.image.copy()
        ImageDraw.Draw(image).rectangle((160, 525, 390, 615), fill=(18, 31, 68))
        capture = replace(source, image=image)
        builder, navigation = _wire()
        for observation in (builder.build(capture), navigation.build(capture)):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.screen_type, ScreenType.PNC_VIP_DAILY_RESET)
                self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
                self.assertFalse(observation.has(UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON))
                self.assertIsNotNone(observation.popup_overlay)
                assert observation.popup_overlay is not None
                self.assertEqual(observation.popup_overlay.candidates, ())

    def test_recognized_home_keeps_ownership_over_generic_like_hud_x_on_both_paths(self) -> None:
        image_path = FIXTURES / "home_city_popup_x_regression.png"
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        capture = CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))
        builder, navigation = _wire()
        for observation in (builder.build(capture), navigation.build(capture)):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
                self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                self.assertFalse(observation.blocking_popup)
                self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
                self.assertIsNone(observation.popup_overlay)

    def test_generic_partial_visual_evidence_is_unresolved_on_both_paths(self) -> None:
        builder, navigation = _wire()
        recognizer = builder.visual_recognizer
        assert recognizer is not None
        profiles = tuple(
            profile for profile in recognizer.profiles if not profile.id.startswith("savannah_hero_offer")
        )
        builder.visual_recognizer = replace(recognizer, profiles=profiles)
        navigation = replace(navigation, recognizer=builder.visual_recognizer)

        def assert_unresolved(capture: CapturedScreenshot) -> None:
            for observation in (builder.build(capture), navigation.build(capture)):
                with self.subTest(path=type(observation).__name__):
                    self.assertEqual(observation.decision.guard, GuardVerdict.UNRESOLVED)
                    self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
                    if observation.popup_overlay is not None:
                        self.assertEqual((), observation.popup_overlay.candidates)

        broken = _capture("savannah_hero_offer.png").image
        broken.paste((0, 0, 0), (0, 0, broken.width, 740))
        drawing = ImageDraw.Draw(broken)
        drawing.line((480, 60, 518, 98), fill=(255, 247, 218), width=8)
        drawing.line((518, 60, 480, 98), fill=(255, 247, 218), width=8)
        broken_capture = CapturedScreenshot(None, broken, "PNG", ephemeral_captured_at=datetime.now(UTC))
        assert_unresolved(broken_capture)

        multiple = _capture("savannah_hero_offer.png").image
        drawing = ImageDraw.Draw(multiple)
        drawing.line((430, 55, 466, 91), fill=(255, 247, 218), width=6)
        drawing.line((466, 55, 430, 91), fill=(255, 247, 218), width=6)
        multiple_capture = CapturedScreenshot(None, multiple, "PNG", ephemeral_captured_at=datetime.now(UTC))
        assert_unresolved(multiple_capture)

        outside = Image.new("RGB", (540, 960), (15, 28, 68))
        drawing = ImageDraw.Draw(outside)
        drawing.rectangle((20, 200, 400, 700), fill=(25, 33, 50), outline=(65, 82, 110), width=4)
        drawing.line((480, 60, 518, 98), fill=(255, 247, 218), width=8)
        drawing.line((518, 60, 480, 98), fill=(255, 247, 218), width=8)
        assert_unresolved(CapturedScreenshot(None, outside, "PNG", ephemeral_captured_at=datetime.now(UTC)))

        isolated = Image.new("RGB", (540, 960), (15, 28, 68))
        drawing = ImageDraw.Draw(isolated)
        drawing.line((480, 60, 518, 98), fill=(255, 247, 218), width=8)
        drawing.line((518, 60, 480, 98), fill=(255, 247, 218), width=8)
        assert_unresolved(CapturedScreenshot(None, isolated, "PNG", ephemeral_captured_at=datetime.now(UTC)))


if __name__ == "__main__":
    unittest.main()
