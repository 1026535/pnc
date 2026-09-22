"""Visual identity, scope independence, and topmost-overlay regression coverage."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageEnhance

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService


FIXTURES = TEST_DATA_ROOT / "screen_recognition"


def _capture(name: str) -> CapturedScreenshot:
    """Load a committed frame into the canonical ephemeral capture model."""
    with Image.open(FIXTURES / name) as source:
        image = source.convert("RGB")
    return CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))


def _builder(ocr: _RecordingOcrService) -> ObservationBuilder:
    """Wire deterministic OCR into the existing observation and visual components."""
    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        ocr_service=ocr,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )


def _capture_with_ref(name: str, *, session_id: str, session_epoch: int) -> CapturedScreenshot:
    """Load a fixture with explicit session provenance for lifecycle tests."""

    capture = _capture(name)
    return replace(
        capture,
        frame_ref=FrameRef(
            session_id=session_id,
            session_epoch=session_epoch,
            capture_sequence=1,
            input_sequence=0,
            captured_at=capture.captured_at,
        ),
    )


class VisualScreenRecognizerTests(unittest.TestCase):
    """Require distinct tabs, conservative matches, and intact global guard ordering."""

    def test_reviewed_reference_profiles_and_separate_day_positives(self) -> None:
        recognizer = load_visual_screen_recognizer()
        manifest = json.loads((FIXTURES / "manifest.json").read_text())
        excluded = {"home_negative.png", "store_negative.png", "disconnect_negative.png", "update_over_bag.png"}
        for sample in manifest["samples"]:
            if sample["image"] in excluded:
                continue
            with self.subTest(image=sample["image"]):
                result = recognizer.recognize(_capture(sample["image"]).image)
                expected_visual_screens = sample.get("expected_visual_screens")
                self.assertIsInstance(expected_visual_screens, list)
                self.assertEqual(
                    {item.screen_type.name for item in result.evidence},
                    set(expected_visual_screens),
                )

    def test_base_identity_skips_popup_anchor_work_and_session_progress_disarms_login_families(self) -> None:
        """Popup templates are demand-driven and a stable post-login frame closes startup eligibility."""

        delegate = OpenCvTemplateMatcher()
        calls: list[Path] = []

        class _RecordingMatcher:
            def prepare_frame(self, image, *, reference_size):
                return delegate.prepare_frame(image, reference_size=reference_size)

            def find_best_match(self, image, template_path, *, threshold, search_region):
                calls.append(template_path)
                return delegate.find_best_match(
                    image,
                    template_path,
                    threshold=threshold,
                    search_region=search_region,
                )

        recognizer = load_visual_screen_recognizer(matcher=_RecordingMatcher())
        home = _capture("home_city_core.png").image
        savannah = _capture("savannah_hero_offer.png").image
        base = recognizer.recognize(home, include_blocking_profiles=False, session_key=("session", 1))
        self.assertTrue(base.evidence)
        self.assertFalse(any("/popup/" in path.as_posix() for path in calls))

        for expired_name, marker in (
            ("savannah_hero_offer.png", "savannah_offer"),
            ("vip_daily_reset.png", "vip_daily_reset"),
            ("alliance_invitation.png", "alliance_invitation"),
            ("king_return_welcome.png", "king_return"),
            ("valiant_conquest.png", "valiant_conquest"),
        ):
            with self.subTest(expired=expired_name):
                calls.clear()
                blocked = recognizer.recognize(
                    _capture(expired_name).image,
                    blocking_profiles_only=True,
                    session_key=("session", 1),
                )
                self.assertEqual((), blocked.profile_ids)
                self.assertFalse(any(marker in path.name for path in calls))

        with Image.open(FIXTURES / "lucifer_special_offer_startup_gap_20260922.png") as source:
            delayed_image = source.copy()
        self.assertEqual(("RGBA", (900, 1600)), (delayed_image.mode, delayed_image.size))
        calls.clear()
        delayed = recognizer.recognize(
            delayed_image,
            blocking_profiles_only=True,
            session_key=("session", 1),
        )
        self.assertEqual(("lucifer_special_offer",), delayed.profile_ids)

        calls.clear()
        eligible = recognizer.recognize(savannah, blocking_profiles_only=True, session_key=("new-session", 1))
        self.assertIn("savannah_hero_offer", eligible.profile_ids)
        self.assertTrue(any("/popup/" in path.as_posix() for path in calls))

    def test_production_paths_skip_expired_popup_preparation_and_rearm_on_new_epoch(self) -> None:
        """Base-first production flows avoid popup work until a new session epoch."""

        class _RecordingMatcher:
            def __init__(self) -> None:
                self.delegate = OpenCvTemplateMatcher()
                self.prepare_calls = 0
                self.template_paths: list[Path] = []

            def prepare_frame(self, image, *, reference_size):
                self.prepare_calls += 1
                return self.delegate.prepare_frame(image, reference_size=reference_size)

            def find_best_match(self, image, template_path, *, threshold, search_region):
                self.template_paths.append(template_path)
                return self.delegate.find_best_match(
                    image,
                    template_path,
                    threshold=threshold,
                    search_region=search_region,
                )

        class _NoopSelectorEngine:
            def detect(self, image, registry, *, selector_ids=None, ocr_context=None):
                del image, registry, selector_ids, ocr_context
                return ()

        def build_path(path: str):
            matcher = _RecordingMatcher()
            recognizer = load_visual_screen_recognizer(matcher=matcher)
            registry = build_default_selector_registry()
            enricher = PncObservationEnricher(selector_registry=registry)
            ocr = _RecordingOcrService(lines=())
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=_NoopSelectorEngine(),
                screen_classifier=ScreenClassifier(),
                enricher=enricher,
                ocr_service=ocr,
                visual_recognizer=recognizer,
            )
            if path == "builder":
                return builder, matcher, ocr
            return NavigationPerception(
                recognizer,
                enricher,
                ScreenClassifier(),
                builder.create_ocr_context,
            ), matcher, ocr

        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                production_path, matcher, ocr = build_path(path)
                home = _capture_with_ref(
                    "home_city_core.png", session_id=f"{path}-session", session_epoch=1,
                )
                savannah = _capture_with_ref(
                    "savannah_hero_offer.png", session_id=f"{path}-session", session_epoch=1,
                )
                production_path.build(home)
                self.assertEqual(matcher.prepare_calls, 1)
                self.assertFalse(any("/popup/" in path.as_posix() for path in matcher.template_paths))
                matcher.prepare_calls = 0
                matcher.template_paths.clear()
                ocr.read_result_calls = 0

                # The base pass still prepares its ordinary profiles, and the
                # post-login probe only evaluates popup families that remain
                # eligible; expired startup-only assets are never matched.
                production_path.build(savannah)
                self.assertEqual(matcher.prepare_calls, 2)
                evaluated = {path.name for path in matcher.template_paths}
                self.assertFalse(
                    any(
                        marker in name
                        for name in evaluated
                        for marker in (
                            "savannah_offer", "vip_daily_reset", "alliance_invitation",
                            "king_return", "valiant_conquest",
                        )
                    )
                )
                self.assertTrue(any("lucifer_offer" in name for name in evaluated))
                self.assertTrue(any("growth_boost" in name for name in evaluated))
                self.assertGreater(ocr.read_result_calls, 0)

                # A reconnect/new epoch re-arms the conservative popup phase.
                next_epoch = _capture_with_ref(
                    "savannah_hero_offer.png", session_id=f"{path}-session", session_epoch=2,
                )
                matcher.prepare_calls = 0
                matcher.template_paths.clear()
                result = production_path.build(next_epoch)
                self.assertEqual(result.screen_type, ScreenType.PNC_POPUP)
                self.assertGreaterEqual(matcher.prepare_calls, 2)
                self.assertTrue(any("/popup/" in path.as_posix() for path in matcher.template_paths))

    def test_pre_login_sequence_keeps_startup_popup_families_eligible(self) -> None:
        """Android/login/castle-selection frames do not prove the city session passed login."""

        recognizer = load_visual_screen_recognizer()
        state = recognizer.popup_state
        home_profile = next(profile for profile in recognizer.profiles if profile.id == "home_city")
        startup_profiles = tuple(
            next(profile for profile in recognizer.profiles if profile.id == profile_id)
            for profile_id in (
                "savannah_hero_offer", "vip_daily_reset", "alliance_invitation",
                "king_return_welcome", "valiant_conquest",
            )
        )
        delayed_profiles = tuple(
            next(profile for profile in recognizer.profiles if profile.id == profile_id)
            for profile_id in ("lucifer_special_offer", "growth_boost_weekly_pass")
        )
        pre_login_screens = (
            ScreenType.ANDROID_HOME,
            ScreenType.PNC_LOADING,
            ScreenType.PNC_LOGIN,
            ScreenType.PNC_ACCOUNT_SWITCH,
            ScreenType.PNC_CASTLE_SELECTION,
        )
        for screen in pre_login_screens:
            with self.subTest(screen=screen):
                state.observe_base_identity(
                    (replace(home_profile, screen_type=screen),),
                    session_key=("sequence", 1),
                )
                self.assertFalse(state.post_login_proven)
                for profile in (*startup_profiles, *delayed_profiles):
                    self.assertTrue(state.allow(profile))

        state.observe_base_identity(
            (home_profile, replace(home_profile, screen_type=ScreenType.PNC_LOGIN)),
            session_key=("ambiguous-sequence", 1),
        )
        self.assertFalse(state.post_login_proven)
        for profile in (*startup_profiles, *delayed_profiles):
            self.assertTrue(state.allow(profile))

        state.observe_base_identity((home_profile,), session_key=("sequence", 1))
        self.assertTrue(state.post_login_proven)
        for profile in startup_profiles:
            self.assertFalse(state.allow(profile))
        for profile in delayed_profiles:
            self.assertTrue(state.allow(profile))

    def test_collect_mail_profiles_expose_only_measured_controls(self) -> None:
        """Recognizes the four mail frames and keeps navigation controls template-backed."""

        recognizer = load_visual_screen_recognizer()
        expected = {
            "collect_mail_home.png": (ScreenType.PNC_HOME_CITY, {UiElementId.PNC_BOTTOM_NAV_MAIL}),
            "collect_mail_hub.png": (
                ScreenType.PNC_MAIL_HUB,
                {
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                    UiElementId.PNC_MAIL_ROW_PLAYER_MAIL,
                    UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL,
                },
            ),
            "collect_mail_system_list.png": (ScreenType.PNC_MAILBOX_LIST, {UiElementId.PNC_BACK_BUTTON_TOP_LEFT}),
            "collect_mail_system_thread.png": (ScreenType.PNC_MAIL_THREAD, {UiElementId.PNC_BACK_BUTTON_TOP_LEFT}),
        }
        for name, (screen, controls) in expected.items():
            with self.subTest(name=name):
                result = recognizer.recognize(_capture(name).image)
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
                observed_controls = {item.selector_id for item in result.controls}
                if screen == ScreenType.PNC_HOME_CITY:
                    self.assertTrue(controls <= observed_controls)
                else:
                    self.assertEqual(observed_controls, controls)
                self.assertTrue(all(item.source_kind.name == "TEMPLATE" for item in result.controls))
                scaled = recognizer.recognize(_capture(name).image.resize((900, 1600)))
                self.assertEqual({item.screen_type for item in scaled.evidence}, {screen})

    def test_chat_profiles_expose_measured_back_and_channel_controls(self) -> None:
        """Recognizes both live Chat tab variants and exposes their measured controls."""

        expected = {
            "chat_alliance.png": {
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                UiElementId.PNC_CHAT_TAB_KINGDOM,
                UiElementId.PNC_CHAT_TAB_ALLIANCE,
                UiElementId.PNC_CHAT_INPUT_FIELD,
            },
            "chat_kingdom.png": {
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                UiElementId.PNC_CHAT_TAB_KINGDOM,
                UiElementId.PNC_CHAT_TAB_ALLIANCE,
                UiElementId.PNC_CHAT_INPUT_FIELD,
            },
        }
        recognizer = load_visual_screen_recognizer()
        for name, selectors in expected.items():
            with self.subTest(name=name):
                result = recognizer.recognize(_capture(name).image)
                self.assertEqual({item.screen_type for item in result.evidence}, {ScreenType.PNC_CHAT})
                self.assertEqual({item.selector_id for item in result.controls}, selectors)
                self.assertTrue(all(item.source_kind.name == "TEMPLATE" for item in result.controls))

    def test_home_chat_shortcut_profiles_cover_both_channel_icon_variants(self) -> None:
        """Keeps Home identity anchors required while recognizing both measured shortcut icons."""

        recognizer = load_visual_screen_recognizer()
        shortcut_definition = build_default_selector_registry().require(UiElementId.PNC_CHAT_SHORTCUT)
        self.assertIsNotNone(shortcut_definition.relative_bounds)
        shortcut_geometry = shortcut_definition.relative_bounds.materialize(
            selector_id=UiElementId.PNC_CHAT_SHORTCUT,
            image_size=(540, 960),
        )
        self.assertEqual(shortcut_geometry.bounds, Bounds(4, 849, 45, 40))
        self.assertEqual(shortcut_geometry.action_point, (26, 869))
        self.assertTrue(4 <= shortcut_geometry.action_point[0] <= 49)
        self.assertTrue(849 <= shortcut_geometry.action_point[1] <= 889)
        self.assertGreater(shortcut_geometry.action_point[1], 840)
        for name, profile_id in (
            ("chat_home_alliance.png", "home_city_chat_alliance"),
            ("chat_home_kingdom.png", "home_city_chat_kingdom"),
        ):
            with self.subTest(name=name):
                result = recognizer.recognize(_capture(name).image)
                self.assertEqual({item.screen_type for item in result.evidence}, {ScreenType.PNC_HOME_CITY})
                self.assertIn(profile_id, result.profile_ids)
                shortcut = next(
                    item for item in result.controls if item.selector_id == UiElementId.PNC_CHAT_SHORTCUT
                )
                self.assertEqual(shortcut.source_kind.name, "TEMPLATE")
                self.assertEqual(shortcut.bounds, Bounds(4, 849, 45, 40))
                center_x, center_y = shortcut.bounds.center()
                self.assertTrue(4 <= center_x <= 49)
                self.assertTrue(849 <= center_y <= 889)
                self.assertNotEqual(center_y, 840)
                scaled = recognizer.recognize(_capture(name).image.resize((900, 1600)))
                scaled_shortcut = next(
                    item for item in scaled.controls if item.selector_id == UiElementId.PNC_CHAT_SHORTCUT
                )
                scaled_center_x, scaled_center_y = scaled_shortcut.bounds.center()
                self.assertTrue(round(4 * 900 / 540) <= scaled_center_x <= round(49 * 900 / 540))
                self.assertTrue(round(849 * 1600 / 960) <= scaled_center_y <= round(889 * 1600 / 960))
                self.assertNotEqual(scaled_center_y, round(840 * 1600 / 960))
                scaled_geometry = shortcut_definition.relative_bounds.materialize(
                    selector_id=UiElementId.PNC_CHAT_SHORTCUT,
                    image_size=(900, 1600),
                )
                scaled_action_x, scaled_action_y = scaled_geometry.action_point
                self.assertTrue(round(4 * 900 / 540) <= scaled_action_x <= round(49 * 900 / 540))
                self.assertTrue(round(849 * 1600 / 960) <= scaled_action_y <= round(889 * 1600 / 960))
                self.assertNotEqual(scaled_action_y, round(840 * 1600 / 960))

    def test_collect_mail_list_and_thread_profiles_are_mutually_exclusive(self) -> None:
        """Requires footer-versus-detail chrome to keep the dynamic mail screens distinct."""

        recognizer = load_visual_screen_recognizer()
        with Image.open(FIXTURES / "collect_mail_system_list.png") as source:
            list_result = recognizer.recognize(source.convert("RGB"))
        with Image.open(FIXTURES / "collect_mail_system_thread.png") as source:
            thread_result = recognizer.recognize(source.convert("RGB"))
        self.assertEqual({item.screen_type for item in list_result.evidence}, {ScreenType.PNC_MAILBOX_LIST})
        self.assertEqual({item.screen_type for item in thread_result.evidence}, {ScreenType.PNC_MAIL_THREAD})
        self.assertNotEqual(list_result.profile_ids, thread_result.profile_ids)
        self.assertEqual({item.selector_id for item in list_result.controls}, {UiElementId.PNC_BACK_BUTTON_TOP_LEFT})
        self.assertEqual({item.selector_id for item in thread_result.controls}, {UiElementId.PNC_BACK_BUTTON_TOP_LEFT})

    def test_unknown_blank_dimmed_and_wrong_aspect_frames_abstain(self) -> None:
        recognizer = load_visual_screen_recognizer()
        hero = _capture("hero_hall.png").image
        for image in (
            Image.new("RGB", (540, 960)),
            ImageEnhance.Brightness(hero).enhance(0.45),
            hero.resize((700, 960)),
            _capture("store_negative.png").image,
            _capture("disconnect_negative.png").image,
        ):
            self.assertEqual(recognizer.recognize(image).evidence, ())

    def test_city_profiles_scale_and_require_description_as_well_as_header(self) -> None:
        recognizer = load_visual_screen_recognizer()
        for name, screen in (
            ("institute", ScreenType.PNC_INSTITUTE),
            ("goddess_statue", ScreenType.PNC_GODDESS_STATUE),
            ("warehouse", ScreenType.PNC_WAREHOUSE),
            ("castle", ScreenType.PNC_CASTLE),
        ):
            with self.subTest(screen=screen):
                source = _capture(f"{name}_audit.png").image
                for size in ((540, 960), (900, 1600)):
                    recognition = recognizer.recognize(source.resize(size))
                    self.assertEqual({item.screen_type for item in recognition.evidence}, {screen})
                obscured = source.copy()
                obscured.paste((0, 0, 0), (280, 140, 535, 187))
                self.assertEqual(recognizer.recognize(obscured).evidence, ())

    def test_castle_profile_requires_title_and_body_and_exposes_only_template_back(self) -> None:
        """Requires both independent Castle anchors and exposes only its reviewed Back control."""

        recognizer = load_visual_screen_recognizer()
        source = _capture("castle_audit.png").image
        result = recognizer.recognize(source)
        self.assertEqual({item.screen_type for item in result.evidence}, {ScreenType.PNC_CASTLE})
        self.assertEqual({item.selector_id for item in result.controls}, {UiElementId.PNC_BACK_BUTTON_TOP_LEFT})
        control = result.controls[0]
        self.assertEqual(VisibleElementSourceKind.TEMPLATE, control.source_kind)
        self.assertTrue(22 <= control.bounds.center()[0] <= 80)
        self.assertTrue(8 <= control.bounds.center()[1] <= 46)

        title_only = source.copy()
        title_only.paste((0, 0, 0), (98, 3, 297, 46))
        self.assertEqual(recognizer.recognize(title_only).evidence, ())
        body_only = source.copy()
        body_only.paste((0, 0, 0), (278, 142, 518, 182))
        self.assertEqual(recognizer.recognize(body_only).evidence, ())

    def test_scope_cannot_hide_hero_hall_and_identity_does_not_invent_recruit(self) -> None:
        ocr = _RecordingOcrService(lines=())
        observation = _builder(ocr).build(_capture("hero_hall.png"), request=ObservationRequest.daily_quest_follow_up())
        self.assertEqual(observation.screen_type, ScreenType.PNC_HERO_HALL)
        self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
        self.assertFalse(observation.has(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON))
        self.assertEqual(ocr.read_result_calls, 0, "Recognized base identity must skip popup guard OCR.")

    def test_hero_hall_back_click_is_inside_manually_reviewed_arrow(self) -> None:
        # At 540x960 the gold arrow occupies x=20..80, y=5..47.
        # Use its interior, not the selector's own bounds, as the click oracle.
        for width, height in ((540, 960), (900, 1600)):
            capture = _capture("hero_hall.png")
            capture = replace(capture, image=capture.image.resize((width, height)))
            observation = _builder(_RecordingOcrService(lines=())).build(capture)
            bounds = observation.visible_elements[UiElementId.PNC_BACK_BUTTON_TOP_LEFT].bounds
            center_x = (bounds.x + bounds.width / 2) * 540 / width
            center_y = (bounds.y + bounds.height / 2) * 960 / height
            self.assertTrue(20 <= center_x <= 80 and 5 <= center_y <= 47)

    def test_update_over_bag_overrides_header_and_removes_bag_controls(self) -> None:
        ocr = _RecordingOcrService(lines=(
            OcrLine("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28), 1.0),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        ))
        builder = _builder(ocr)
        capture = _capture("update_over_bag.png")
        self.assertEqual(builder.visual_recognizer.recognize(capture.image).evidence[0].screen_type, ScreenType.PNC_BAG)
        observation = builder.build(capture, request=ObservationRequest.base())
        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_BAG_USE_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))

    def test_invitation_never_exposes_underlying_home_controls(self) -> None:
        observation = _builder(_RecordingOcrService(lines=())).build(_capture("alliance_invitation.png"))
        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_competing_visual_screens_abstain_without_actionable_geometry(self) -> None:
        builder = _builder(_RecordingOcrService(lines=()))
        recognizer = builder.visual_recognizer
        original = recognizer.profiles[0]
        builder.visual_recognizer = replace(
            recognizer,
            profiles=(original, replace(original, id="conflict", screen_type=ScreenType.PNC_BAG)),
        )
        observation = builder.build(_capture("hero_hall.png"))
        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(observation.visible_elements, {})

    def test_movement_proof_never_calls_global_visual_recognition(self) -> None:
        builder = _builder(_RecordingOcrService(lines=()))
        class ForbiddenRecognizer:
            def recognize(self, image: Image.Image) -> None:
                raise AssertionError("Coordinate-only proof must retain its dedicated fast path.")
        builder.visual_recognizer = ForbiddenRecognizer()
        builder.build(_capture("hero_hall.png"), request=ObservationRequest.world_map_movement_proof_follow_up())

    def test_invalid_catalog_fails_before_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            for document in (
                {},
                {"version": 2, "reference_size": [540, 960], "profiles": []},
                {"version": 1, "reference_size": [0, 960], "profiles": []},
                {"version": 1, "reference_size": [540, 960], "profiles": [{"id": "bad", "screen": "PNC_BAG", "anchors": []}]},
            ):
                path.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    load_visual_screen_recognizer(path)


if __name__ == "__main__":
    unittest.main()
