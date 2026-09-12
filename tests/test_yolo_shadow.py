"""Model boxes must not bypass canonical screen, popup, or frame ownership."""

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    Observation, SpatialObjectKind, SpatialSurfaceObservation, SpatialSurfaceType,
    SpatialViewport, SpatialViewportAddressingKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.yolo_shadow import YoloShadowObserver, evaluate_yolo_shadow
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.detection.yolo_onnx import YoloDetection
from pnc_automation.core.vision.image.models import Bounds


class FakeDetector:
    class_names = ("monster", "person")
    model_sha256 = "a" * 64

    def detect(self, image: Image.Image) -> tuple[YoloDetection, ...]:
        return (YoloDetection(0, "monster", .9, Bounds(20, 30, 40, 50)),)


class YoloShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        image = Image.new("RGB", (540, 960))
        self.capture = CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))
        self.observation = Observation(
            screen_type=ScreenType.PNC_WORLD_MAP, visible_elements={}, image_size=image.size,
            frame_fingerprint=hashlib.sha256(image.tobytes()).hexdigest(),
            spatial_surface=SpatialSurfaceObservation(
                SpatialSurfaceType.WORLD_MAP,
                SpatialViewport(SpatialViewportAddressingKind.COORDINATE_BAR, x=10, y=20),
            ),
        )

    def test_custom_mapping_produces_shadow_candidates_without_mutating_observation(self) -> None:
        mapping = {"monster": SpatialObjectKind.MONSTER}
        shadow = YoloShadowObserver(FakeDetector(), mapping)
        mapping.clear()
        report = shadow.observe(self.capture, self.observation)
        self.assertEqual(report.candidates[0].kind, SpatialObjectKind.MONSTER)
        self.assertIsNone(report.candidates[0].action_point)
        self.assertEqual(self.observation.spatial_surface.objects, ())
        self.assertEqual(self.observation.visible_elements, {})

    def test_no_implicit_coco_to_game_mapping(self) -> None:
        report = YoloShadowObserver(FakeDetector()).observe(self.capture, self.observation)
        self.assertEqual(len(report.detections), 1)
        self.assertEqual(report.candidates, ())
        self.assertEqual(report.candidate_gate, "no_pnc_class_mapping")

    def test_popup_unknown_and_wrong_surface_never_supply_candidates(self) -> None:
        shadow = YoloShadowObserver(FakeDetector(), {"monster": SpatialObjectKind.MONSTER})
        for observation in (
            replace(self.observation, blocking_popup=True),
            replace(self.observation, screen_type=ScreenType.UNKNOWN),
            replace(self.observation, screen_type=ScreenType.PNC_POPUP),
            replace(self.observation, screen_type=ScreenType.PNC_HOME_CITY),
            replace(self.observation, spatial_surface=None),
        ):
            self.assertEqual(shadow.observe(self.capture, observation).candidates, ())

    def test_mismatched_frame_and_class_map_fail_before_use(self) -> None:
        shadow = YoloShadowObserver(FakeDetector())
        with self.assertRaises(ValueError):
            shadow.observe(self.capture, replace(self.observation, frame_fingerprint="other"))
        with self.assertRaises(ValueError):
            shadow.observe(self.capture, replace(self.observation, image_size=(900, 1600)))
        with self.assertRaises(ValueError):
            YoloShadowObserver(FakeDetector(), {"missing": SpatialObjectKind.MONSTER})
        with self.assertRaises(ValueError):
            YoloShadowObserver(FakeDetector(), {"monster": "monster"})

    def test_evaluation_reports_generic_boxes_as_no_measured_improvement(self) -> None:
        report = YoloShadowObserver(FakeDetector()).observe(self.capture, self.observation)

        evaluation = evaluate_yolo_shadow((report, report))

        self.assertEqual(evaluation.frame_count, 2)
        self.assertEqual(evaluation.unique_frame_count, 1)
        self.assertEqual(evaluation.frames_with_detections, 2)
        self.assertEqual(evaluation.detection_count, 2)
        self.assertEqual(evaluation.candidate_count, 0)
        self.assertEqual(evaluation.detection_labels, (("monster", 2),))
        self.assertEqual(evaluation.assessment, "no_measured_pnc_improvement")
        self.assertFalse(evaluation.to_document()["authoritative_observation_changed"])

    def test_evaluation_requires_at_least_one_report(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one"):
            evaluate_yolo_shadow(())


if __name__ == "__main__":
    unittest.main()
