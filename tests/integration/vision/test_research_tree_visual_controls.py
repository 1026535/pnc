"""Development Research Tree identity and safe Back-control coverage."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import (
    DetectionKind,
    SelectorResolutionError,
    build_default_selector_registry,
)
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, ObservationOcrContext

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame


FIXTURE_PATH = TEST_DATA_ROOT / "screen_recognition" / "research_tree_development.png"
TITLE_BOX = (108, 10, 303, 43)
ICON_BOX = (463, 80, 530, 120)
BACK_BOX = (25, 11, 77, 43)


def _load_fixture() -> Image.Image:
    """Load the reviewed Development tree fixture as an independent RGB image."""

    with Image.open(FIXTURE_PATH) as source:
        return source.convert("RGB")


def _capture(image: Image.Image) -> CapturedScreenshot:
    """Attach frame provenance to one deterministic fixture capture."""

    frame = make_captured_frame(_encode_png(image), session_id="research-tree-visual-controls")
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _perception(lines: tuple[OcrLine, ...] = ()) -> NavigationPerception:
    """Wire the production perception path with deterministic OCR lines."""

    ocr = _FakeOcrService(lines=lines)
    return NavigationPerception(
        load_visual_screen_recognizer(),
        PncObservationEnricher(),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "research-tree-visual-controls-test",
        ),
    )


class ResearchTreeVisualControlTests(unittest.TestCase):
    """Keep the Development tree identity and measured Back bounded."""

    def test_development_profile_exposes_only_measured_back(self) -> None:
        """Recognizes the reviewed identity and publishes its template Back control."""

        recognition = load_visual_screen_recognizer().recognize(_load_fixture())

        self.assertEqual(recognition.profile_ids, ("research_tree_development",))
        self.assertEqual(
            {item.screen_type for item in recognition.evidence},
            {ScreenType.PNC_RESEARCH_TREE},
        )
        self.assertEqual(
            {item.selector_id for item in recognition.controls},
            {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
        )
        back = recognition.controls[0]
        self.assertEqual(back.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(back.bounds, Bounds(25, 11, 52, 32))
        self.assertEqual(back.action_point, (51, 27))

        scaled = load_visual_screen_recognizer().recognize(_load_fixture().resize((900, 1600)))
        self.assertEqual(scaled.profile_ids, ("research_tree_development",))
        scaled_back = scaled.controls[0]
        self.assertEqual(scaled_back.bounds, Bounds(42, 18, 86, 54))

    def test_missing_identity_anchor_abstains(self) -> None:
        """Removing either independent identity anchor prevents the profile match."""

        recognizer = load_visual_screen_recognizer()
        for box in (TITLE_BOX, ICON_BOX):
            with self.subTest(box=box):
                image = _load_fixture()
                image.paste((0, 0, 0), box)
                recognition = recognizer.recognize(image)
                self.assertNotIn("research_tree_development", recognition.profile_ids)
                self.assertFalse(recognition.controls)

    def test_missing_back_anchor_keeps_identity_but_blocks_back(self) -> None:
        """A recognized tree without the measured Back match publishes no Back target."""

        image = _load_fixture()
        image.paste((0, 0, 0), BACK_BOX)

        recognition = load_visual_screen_recognizer().recognize(image)

        self.assertEqual(recognition.profile_ids, ("research_tree_development",))
        self.assertFalse(recognition.controls)

    def test_institute_fixture_does_not_match_development_tree_profile(self) -> None:
        """Keeps the Development tree profile scoped away from its Institute source."""

        with Image.open(TEST_DATA_ROOT / "screen_recognition" / "institute_audit.png") as source:
            recognition = load_visual_screen_recognizer().recognize(source.convert("RGB"))

        self.assertNotIn("research_tree_development", recognition.profile_ids)

    def test_blocking_popup_suppresses_research_tree_back(self) -> None:
        """A blocking update prompt owns the frame even when tree anchors remain visible."""

        popup_lines = (
            OcrLine(
                "New version detected. Tap Confirm to update.",
                Bounds(58, 380, 420, 28),
                1.0,
            ),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        observation = _perception(popup_lines).build(_capture(_load_fixture()))

        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))

    def test_back_dispatch_is_bound_to_the_current_research_tree_frame(self) -> None:
        """Dispatches Back only from the current visually matched frame."""

        observation = _perception().build(_capture(_load_fixture()))
        self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)
        back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
        self.assertEqual(back.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(back.source_screen, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(back.source_layout_id, "research_tree_development")
        self.assertEqual(back.frame_ref, observation.frame_ref)

        session = FakeSession()
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        self.assertTrue(
            executor.execute_action(
                TapAction(selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
                observation,
            )
        )
        self.assertEqual(session.taps, [(51, 27)])

    def test_foreign_frame_back_geometry_is_rejected(self) -> None:
        """Rejects a Back target rebound to a different captured frame."""

        capture = _capture(_load_fixture())
        observation = _perception().build(capture)
        back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
        foreign = _capture(_load_fixture())
        observation.visible_elements[UiElementId.PNC_BACK_BUTTON_TOP_LEFT] = replace(
            back,
            frame_ref=foreign.frame_ref,
        )

        session = FakeSession()
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        with self.assertRaises(SelectorResolutionError):
            executor.execute_action(
                TapAction(selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
                observation,
            )
        self.assertEqual(session.taps, [])

    def test_research_start_remains_explicitly_unsupported(self) -> None:
        """The Development identity profile does not authorize research-start input."""

        definition = build_default_selector_registry().require(UiElementId.PNC_RESEARCH_START_BUTTON)
        self.assertEqual(definition.detection_kind, DetectionKind.UNSUPPORTED)
        with self.assertRaises(SelectorResolutionError):
            build_default_selector_registry().require_supported(UiElementId.PNC_RESEARCH_START_BUTTON)
        self.assertNotIn(
            UiElementId.PNC_RESEARCH_START_BUTTON,
            {
                item.selector_id
                for item in load_visual_screen_recognizer().recognize(_load_fixture()).controls
            },
        )


if __name__ == "__main__":
    unittest.main()
