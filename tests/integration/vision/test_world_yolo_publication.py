"""Saved World frame reaches one request-scoped YOLO producer from both publishers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import unittest

from PIL import Image

from pnc_automation.app.entrypoints.app import build_observation_builder
from pnc_automation.app.pnc.domain.observation import Bounds, SpatialObjectKind, SpatialObjectSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.world_yolo import (
    WorldYoloProducer,
)
from pnc_automation.app.pnc.vision.world_yolo_qualification import WORLD_YOLO_QUALIFICATION
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.detection.yolo_onnx import YoloDetection


_FIXTURE = Path(__file__).resolve().parents[2] / "data/screen_recognition/world_map_core.png"


class FakeDetector:
    class_names = WORLD_YOLO_QUALIFICATION.class_names
    model_sha256 = WORLD_YOLO_QUALIFICATION.model_sha256

    def __init__(self) -> None:
        self.calls = 0

    def detect(self, image: Image.Image) -> tuple[YoloDetection, ...]:
        self.calls += 1
        return (YoloDetection(2, "castle", 0.91, Bounds(205, 380, 125, 100)),)


def _castle_qualification():
    return replace(WORLD_YOLO_QUALIFICATION, qualified_class_map={"castle": SpatialObjectKind.CASTLE})


class WorldYoloPublicationTests(unittest.TestCase):
    def test_both_publishers_use_explicit_world_yolo_request(self) -> None:
        detector = FakeDetector()
        producer = WorldYoloProducer(detector, _castle_qualification())
        builder = build_observation_builder(
            build_default_selector_registry(),
            world_yolo_producer=producer,
        )
        perception = NavigationPerception(
            builder.visual_recognizer,
            builder.enricher,
            builder.screen_classifier,
            builder.create_ocr_context,
        )
        with Image.open(_FIXTURE) as source:
            image = source.convert("RGB")
        captured_at = datetime.now(UTC)
        frame_ref = FrameRef("world-yolo-fixture", 1, 1, 0, captured_at)
        capture = CapturedScreenshot(
            None, image, "PNG", ephemeral_captured_at=captured_at, frame_ref=frame_ref,
        )
        request = ObservationRequest.world_map_yolo_object_analysis()

        observations = (
            builder.build(capture, request=request),
            perception.build(capture, include_content=True, request=request),
        )

        self.assertEqual(detector.calls, 2)
        for observation in observations:
            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (485, 73))
            self.assertEqual(len(observation.spatial_surface.objects), 1)
            castle = observation.spatial_surface.objects[0]
            self.assertEqual(castle.kind, SpatialObjectKind.CASTLE)
            self.assertEqual(castle.source_kind, SpatialObjectSourceKind.YOLO)
            self.assertEqual(castle.source_screen, ScreenType.PNC_WORLD_MAP)
            self.assertEqual(castle.frame_ref, frame_ref)
            self.assertIsNone(castle.level)
            self.assertIsNone(castle.confirmed_world_coordinate)

        ordinary_request = ObservationRequest.world_map_checkpoint_analysis(expected_coordinate=(485, 73))
        builder.build(capture, request=ordinary_request)
        perception.build(capture, include_content=True, request=ordinary_request)
        self.assertEqual(detector.calls, 2)

        coordinate_only = replace(
            ObservationRequest.world_map_movement_proof_follow_up(),
            include_world_yolo_objects=True,
        )
        movement = builder.build(capture, request=coordinate_only)
        self.assertIsNotNone(movement.spatial_surface)
        assert movement.spatial_surface is not None
        self.assertEqual(movement.spatial_surface.objects, ())
        self.assertEqual(detector.calls, 2)

    def test_explicit_request_requires_a_configured_producer(self) -> None:
        builder = build_observation_builder(build_default_selector_registry())
        with Image.open(_FIXTURE) as source:
            image = source.convert("RGB")
        capture = CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))
        with self.assertRaisesRegex(RuntimeError, "configured producer"):
            builder.build(
                capture,
                request=ObservationRequest.world_map_yolo_object_analysis(),
            )

    def test_blocking_popup_does_not_invoke_world_detector(self) -> None:
        detector = FakeDetector()
        producer = WorldYoloProducer(detector, _castle_qualification())
        builder = build_observation_builder(
            build_default_selector_registry(),
            world_yolo_producer=producer,
        )
        popup_fixture = _FIXTURE.with_name("alliance_invitation.png")
        with Image.open(popup_fixture) as source:
            image = source.convert("RGB")
        capture = CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))

        observation = builder.build(
            capture,
            request=ObservationRequest.world_map_yolo_object_analysis(),
        )

        self.assertNotEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(detector.calls, 0)


if __name__ == "__main__":
    unittest.main()
