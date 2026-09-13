"""Gathering and march-confirm visual identity and control coverage."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import DetectionKind, build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
GATHER_BUTTON_BOX = Bounds(281, 523, 187, 59)
DISPATCH_BUTTON_BOX = Bounds(295, 1457, 310, 90)


def _image(name: str) -> Image.Image:
    """Load one committed frame as an independent RGB image."""

    with Image.open(FIXTURES / name) as source:
        return source.convert("RGB")


def _capture(image: Image.Image) -> CapturedScreenshot:
    """Wrap one fixture in the canonical capture model."""

    frame = make_captured_frame(_encode_png(image), session_id="gathering-march-visual-test")
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _builder(ocr_lines: tuple[OcrLine, ...] = ()) -> ObservationBuilder:
    """Wire the production builder to deterministic OCR and the real registry."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        ocr_service=_RecordingOcrService(lines=ocr_lines),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )


def _navigation_perception() -> NavigationPerception:
    """Wire the replacement navigation perception path to deterministic OCR."""

    ocr = _FakeOcrService(lines=())
    return NavigationPerception(
        load_visual_screen_recognizer(),
        PncObservationEnricher(),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "gathering-march-visual-test",
        ),
    )


class GatheringMarchVisualProfileTests(unittest.TestCase):
    """Keep node and formation controls tied to reviewed visual evidence."""

    def test_recognizer_identities_and_exact_supported_controls(self) -> None:
        recognizer = load_visual_screen_recognizer()
        expected = {
            "gather_node.png": (
                "gather_node_selected_resource",
                ScreenType.PNC_GATHER_NODE,
                {UiElementId.PNC_GATHER_BUTTON},
            ),
            "march_confirm.png": (
                "march_confirm_gather",
                ScreenType.PNC_MARCH_CONFIRM,
                {UiElementId.PNC_MARCH_CONFIRM_BUTTON},
            ),
            "march_confirm_empty.png": (
                "march_confirm_gather",
                ScreenType.PNC_MARCH_CONFIRM,
                set(),
            ),
        }
        for name, (profile_id, screen, controls) in expected.items():
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name))
                self.assertEqual(result.profile_ids, (profile_id,))
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
                self.assertEqual({item.selector_id for item in result.controls}, controls)
                self.assertTrue(
                    all(
                        item.source_kind is VisibleElementSourceKind.TEMPLATE
                        for item in result.controls
                    )
                )

    def test_positive_control_geometry_is_contained_in_measured_gold_controls(self) -> None:
        recognizer = load_visual_screen_recognizer()
        for name, selector_id, expected_bounds in (
            ("gather_node.png", UiElementId.PNC_GATHER_BUTTON, GATHER_BUTTON_BOX),
            ("march_confirm.png", UiElementId.PNC_MARCH_CONFIRM_BUTTON, DISPATCH_BUTTON_BOX),
        ):
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name))
                control = next(item for item in result.controls if item.selector_id is selector_id)
                self.assertEqual(control.bounds, expected_bounds)
                left, top = expected_bounds.x, expected_bounds.y
                right = left + expected_bounds.width
                bottom = top + expected_bounds.height
                point_x, point_y = control.action_point or control.bounds.center()
                self.assertTrue(left <= point_x <= right)
                self.assertTrue(top <= point_y <= bottom)

    def test_recognizer_scales_both_supported_controls_and_empty_identity(self) -> None:
        recognizer = load_visual_screen_recognizer()
        scaled_gather = recognizer.recognize(_image("gather_node.png").resize((900, 1600)))
        gather = next(
            item
            for item in scaled_gather.controls
            if item.selector_id is UiElementId.PNC_GATHER_BUTTON
        )
        self.assertEqual(gather.bounds, Bounds(468, 872, 312, 98))
        scaled_dispatch = recognizer.recognize(_image("march_confirm.png").resize((540, 960)))
        dispatch = next(
            item for item in scaled_dispatch.controls if item.selector_id is UiElementId.PNC_MARCH_CONFIRM_BUTTON
        )
        self.assertEqual(dispatch.bounds, Bounds(177, 874, 186, 54))
        empty_scaled = recognizer.recognize(_image("march_confirm_empty.png").resize((900, 1600)))
        self.assertEqual(empty_scaled.profile_ids, ("march_confirm_gather",))
        self.assertFalse(empty_scaled.controls)

    def test_missing_control_keeps_identity_without_fabricating_a_control(self) -> None:
        recognizer = load_visual_screen_recognizer()
        gather_without_button = _image("gather_node.png")
        gather_without_button.paste((0, 0, 0), (281, 523, 468, 582))
        result = recognizer.recognize(gather_without_button)
        self.assertEqual(result.profile_ids, ("gather_node_selected_resource",))
        self.assertFalse(result.controls)

        empty = recognizer.recognize(_image("march_confirm_empty.png"))
        self.assertEqual(empty.profile_ids, ("march_confirm_gather",))
        self.assertNotIn(
            UiElementId.PNC_MARCH_CONFIRM_BUTTON,
            {item.selector_id for item in empty.controls},
        )

    def test_independent_identity_anchor_gates_fail_closed(self) -> None:
        recognizer = load_visual_screen_recognizer()
        for name, boxes, profile_id in (
            (
                "gather_node.png",
                ((50, 278, 488, 412), (50, 412, 488, 511)),
                "gather_node_selected_resource",
            ),
            (
                "march_confirm_empty.png",
                ((12, 2, 212, 50), (12, 87, 520, 257)),
                "march_confirm_gather",
            ),
        ):
            for box in boxes:
                with self.subTest(name=name, box=box):
                    image = _image(name)
                    image.paste((0, 0, 0), box)
                    result = recognizer.recognize(image)
                    self.assertNotIn(profile_id, result.profile_ids)
                    self.assertFalse(result.controls)

    def test_real_observation_builder_publishes_only_supported_controls(self) -> None:
        expected = {
            "gather_node.png": (ScreenType.PNC_GATHER_NODE, UiElementId.PNC_GATHER_BUTTON),
            "march_confirm.png": (ScreenType.PNC_MARCH_CONFIRM, UiElementId.PNC_MARCH_CONFIRM_BUTTON),
        }
        for name, (screen, selector_id) in expected.items():
            with self.subTest(name=name):
                capture = _capture(_image(name))
                observation = _builder().build(capture, request=ObservationRequest.base())
                layout_id = (
                    "gather_node_selected_resource"
                    if screen is ScreenType.PNC_GATHER_NODE
                    else "march_confirm_gather"
                )
                self.assertEqual(observation.screen_type, screen)
                self.assertEqual(observation.decision.layout_id, layout_id)
                self.assertEqual(observation.frame_ref, capture.frame_ref)
                self.assertTrue(observation.has(selector_id))
                self.assertEqual(
                    {item.selector_id for item in observation.visible_elements.values()},
                    {selector_id},
                )
                control = observation.visible_elements[selector_id]
                self.assertTrue(control.identity_evidence)
                self.assertEqual(control.source_screen, screen)
                self.assertEqual(control.source_layout_id, layout_id)
                self.assertEqual(control.frame_ref, capture.frame_ref)

        empty_capture = _capture(_image("march_confirm_empty.png"))
        empty = _builder().build(empty_capture, request=ObservationRequest.base())
        self.assertEqual(empty.screen_type, ScreenType.PNC_MARCH_CONFIRM)
        self.assertEqual(empty.decision.layout_id, "march_confirm_gather")
        self.assertEqual(empty.frame_ref, empty_capture.frame_ref)
        self.assertFalse(empty.visible_elements)

    def test_navigation_perception_receives_the_same_supported_controls(self) -> None:
        perception = _navigation_perception()
        expected = {
            "gather_node.png": (ScreenType.PNC_GATHER_NODE, UiElementId.PNC_GATHER_BUTTON),
            "march_confirm.png": (ScreenType.PNC_MARCH_CONFIRM, UiElementId.PNC_MARCH_CONFIRM_BUTTON),
            "march_confirm_empty.png": (ScreenType.PNC_MARCH_CONFIRM, None),
        }
        for name, (screen, selector_id) in expected.items():
            with self.subTest(name=name):
                capture = _capture(_image(name))
                observation = perception.build(capture)
                self.assertEqual(observation.screen_type, screen)
                expected_layout = (
                    "march_confirm_gather"
                    if screen is ScreenType.PNC_MARCH_CONFIRM
                    else "gather_node_selected_resource"
                )
                self.assertEqual(observation.decision.layout_id, expected_layout)
                self.assertEqual(observation.frame_ref, capture.frame_ref)
                self.assertEqual(
                    set(observation.visible_elements),
                    set() if selector_id is None else {selector_id},
                )
                if selector_id is not None:
                    control = observation.visible_elements[selector_id]
                    self.assertEqual(control.source_screen, screen)
                    self.assertEqual(control.source_layout_id, observation.decision.layout_id)
                    self.assertEqual(control.frame_ref, capture.frame_ref)

    def test_wrong_screen_and_blocking_overlay_suppress_gathering_controls(self) -> None:
        wrong_screen = _builder().build(
            _capture(_image("campaign_stage_10_3.png")),
            request=ObservationRequest.base(),
        )
        self.assertNotIn(
            wrong_screen.screen_type,
            {ScreenType.PNC_GATHER_NODE, ScreenType.PNC_MARCH_CONFIRM},
        )
        self.assertFalse(wrong_screen.has(UiElementId.PNC_GATHER_BUTTON))
        self.assertFalse(wrong_screen.has(UiElementId.PNC_MARCH_CONFIRM_BUTTON))

        popup_lines = (
            OcrLine(
                "New version detected. Tap Confirm to update.",
                Bounds(58, 380, 420, 28),
                1.0,
            ),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        blocked = _builder(popup_lines).build(
            _capture(_image("gather_node.png")),
            request=ObservationRequest.base(),
        )
        self.assertEqual(blocked.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(blocked.blocking_popup)
        self.assertTrue(blocked.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
        self.assertFalse(blocked.has(UiElementId.PNC_GATHER_BUTTON))

    def test_selector_dispositions_and_fixture_provenance_are_explicit(self) -> None:
        registry = build_default_selector_registry()
        for selector_id in (
            UiElementId.PNC_GATHER_BUTTON,
            UiElementId.PNC_MARCH_CONFIRM_BUTTON,
        ):
            with self.subTest(selector=selector_id):
                definition = registry.require(selector_id)
                self.assertEqual(definition.status.value, "planned")
                self.assertEqual(definition.detection_kind, DetectionKind.SEMANTIC)
                self.assertTrue(any("visual profile" in note.lower() for note in definition.notes))

        manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        samples = {sample["image"]: sample for sample in manifest["samples"]}
        recognizer = load_visual_screen_recognizer()
        for profile in recognizer.profiles:
            if profile.id not in {"gather_node_selected_resource", "march_confirm_gather"}:
                continue
            with self.subTest(profile=profile.id):
                sample = samples[Path(profile.source.fixture).name]
                self.assertEqual(sample["sha256"], profile.source.decoded_sha256)
                self.assertEqual(sample["group"], profile.source.capture_group)
                self.assertEqual(sample["split"], "reference")
                self.assertEqual(profile.review.reference_manifest, "tests/data/screen_recognition/manifest.json")


if __name__ == "__main__":
    unittest.main()
