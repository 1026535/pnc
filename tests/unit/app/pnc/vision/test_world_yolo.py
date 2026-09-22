"""The first World YOLO release uses full-frame inference and interior boxes only."""

from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    Observation,
    SpatialObjectKind,
    SpatialObjectActionQualification,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialObjectSourceKind,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldMapNavigator
from pnc_automation.app.pnc.vision.pnc_observation_enricher import _read_world_yolo_castle_name
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.world_yolo import (
    WorldYoloExclusion,
    WorldYoloProducer,
    world_yolo_roi_bounds,
)
from pnc_automation.app.pnc.vision.world_yolo_qualification import (
    WORLD_YOLO_QUALIFICATION,
    WorldYoloClassInteraction,
    WorldYoloInteractionQualification,
)
from pnc_automation.core.vision.detection.yolo_onnx import YoloDetection
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.errors import SelectorResolutionError
from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation


class FakeDetector:
    class_names = WORLD_YOLO_QUALIFICATION.class_names
    model_sha256 = WORLD_YOLO_QUALIFICATION.model_sha256

    def __init__(self, detections: tuple[YoloDetection, ...]) -> None:
        self.detections = detections
        self.seen_image: Image.Image | None = None

    def detect(self, image: Image.Image) -> tuple[YoloDetection, ...]:
        self.seen_image = image
        return self.detections


def _castle_qualification():
    return replace(WORLD_YOLO_QUALIFICATION, qualified_class_map={"castle": SpatialObjectKind.CASTLE})


class WorldYoloTests(unittest.TestCase):
    def test_castle_name_crop_accepts_one_text_label_and_ignores_level(self) -> None:
        image = Image.new("RGB", (900, 1600))
        context = Mock()
        context.read_result.return_value = OcrResult(
            lines=(
                OcrLine("19", Bounds(410, 906, 25, 20), 0.99),
                OcrLine("Remote Lord", Bounds(300, 930, 115, 24), 0.93),
            ),
            words=(),
        )

        name = _read_world_yolo_castle_name(
            image=image,
            bounds=Bounds(223, 727, 249, 188),
            ocr_context=context,
        )

        self.assertEqual(name, "Remote Lord")
        self.assertEqual(context.read_result.call_args.args[1], Bounds(199, 915, 297, 72))
        context.read_result.return_value = OcrResult(
            lines=(
                OcrLine("Remote Lord", Bounds(300, 930, 115, 24), 0.93),
                OcrLine("Other Lord", Bounds(320, 950, 105, 24), 0.91),
            ),
            words=(),
        )
        self.assertIsNone(_read_world_yolo_castle_name(
            image=image, bounds=Bounds(223, 727, 249, 188), ocr_context=context,
        ))

    def test_roi_is_interior_with_inward_rounding_at_supported_sizes(self) -> None:
        self.assertEqual(world_yolo_roi_bounds((540, 960)), Bounds(108, 212, 324, 479))
        self.assertEqual(world_yolo_roi_bounds((900, 1600)), Bounds(180, 352, 540, 800))

    def test_full_frame_inference_publishes_only_whole_qualified_unoccluded_boxes(self) -> None:
        image = Image.new("RGB", (540, 960))
        inside = YoloDetection(2, "castle", 0.91, Bounds(205, 350, 110, 105))
        clipped = YoloDetection(2, "castle", 0.90, Bounds(100, 350, 110, 105))
        other_class = YoloDetection(0, "monster", 0.89, Bounds(310, 380, 35, 35))
        hud_covered = YoloDetection(2, "castle", 0.88, Bounds(350, 500, 50, 50))
        detector = FakeDetector((inside, clipped, other_class, hud_covered))
        producer = WorldYoloProducer(detector, _castle_qualification())

        result = producer.observe(image, hud_bounds=(Bounds(365, 510, 10, 10),))

        self.assertIs(detector.seen_image, image)
        self.assertEqual(result.raw_detections, detector.detections)
        self.assertEqual(len(result.objects), 1)
        castle = result.objects[0]
        self.assertEqual(castle.kind, SpatialObjectKind.CASTLE)
        self.assertEqual(castle.source_kind, SpatialObjectSourceKind.YOLO)
        self.assertEqual(castle.bounds, inside.bounds)
        self.assertEqual(castle.relationship, SpatialObjectRelationship.UNKNOWN)
        self.assertIsNone(castle.level)
        self.assertIsNone(castle.estimated_world_coordinate)
        self.assertIsNone(castle.action_point)
        self.assertEqual(castle.metadata["class_id"], 2)
        self.assertEqual(castle.metadata["detection_index"], 0)
        self.assertEqual(castle.metadata["confidence_threshold"], 0.35)
        self.assertEqual(castle.metadata["qualification_review"], WORLD_YOLO_QUALIFICATION.review_ref)
        self.assertEqual(len(result.diagnostics.candidates), 4)
        self.assertEqual(sum(candidate.published for candidate in result.diagnostics.candidates), 1)
        self.assertEqual(
            tuple(rejection.reasons for rejection in result.rejected),
            (
                (WorldYoloExclusion.OUTSIDE_ROI,),
                (WorldYoloExclusion.UNQUALIFIED_CLASS,),
                (WorldYoloExclusion.HUD_OVERLAP,),
            ),
        )

    def test_roi_accepts_a_whole_box_on_its_boundary_and_rejects_one_pixel_outside(self) -> None:
        roi = world_yolo_roi_bounds((540, 960))
        exact = YoloDetection(2, "castle", 0.9, roi)
        outside = YoloDetection(2, "castle", 0.8, Bounds(roi.x, roi.y, roi.width + 1, roi.height))
        result = WorldYoloProducer(
            FakeDetector((exact, outside)), _castle_qualification(),
        ).observe(Image.new("RGB", (540, 960)))

        self.assertEqual([item.bounds for item in result.objects], [roi])
        self.assertEqual(result.rejected[0].reasons, (WorldYoloExclusion.OUTSIDE_ROI,))

    def test_no_class_qualification_keeps_all_boxes_diagnostic(self) -> None:
        detection = YoloDetection(2, "castle", 0.95, Bounds(205, 350, 110, 105))
        result = WorldYoloProducer(
            FakeDetector((detection,)),
            replace(WORLD_YOLO_QUALIFICATION, qualified_class_map={}),
        ).observe(Image.new("RGB", (540, 960)))
        self.assertEqual(result.objects, ())
        self.assertEqual(result.rejected[0].reasons, (WorldYoloExclusion.UNQUALIFIED_CLASS,))

    def test_reviewed_default_qualification_publishes_castle_without_tap_point(self) -> None:
        detection = YoloDetection(2, "castle", 0.95, Bounds(205, 350, 110, 105))
        result = WorldYoloProducer(FakeDetector((detection,))).observe(Image.new("RGB", (540, 960)))

        self.assertEqual(len(result.objects), 1)
        self.assertEqual(result.objects[0].kind, SpatialObjectKind.CASTLE)
        self.assertIsNone(result.objects[0].action_point)

    def test_producer_keeps_reviewed_confidence_floor_even_with_broad_detector(self) -> None:
        low = YoloDetection(2, "castle", 0.34, Bounds(205, 350, 110, 105))
        result = WorldYoloProducer(FakeDetector((low,))).observe(Image.new("RGB", (540, 960)))

        self.assertEqual(result.objects, ())
        self.assertEqual(result.rejected[0].reasons, (WorldYoloExclusion.BELOW_THRESHOLD,))

    def test_canonical_world_navigator_rejects_unproved_yolo_tap_point(self) -> None:
        detection = YoloDetection(2, "castle", 0.95, Bounds(205, 350, 110, 105))
        target = WorldYoloProducer(
            FakeDetector((detection,)),
            _castle_qualification(),
        ).observe(Image.new("RGB", (540, 960))).objects[0]
        observation = Observation(
            screen_type=ScreenType.PNC_WORLD_MAP,
            visible_elements={},
            image_size=(540, 960),
            frame_fingerprint="fixture",
            spatial_surface=SpatialSurfaceObservation(
                SpatialSurfaceType.WORLD_MAP,
                SpatialViewport(SpatialViewportAddressingKind.COORDINATE_BAR, x=485, y=73),
                objects=(target,),
            ),
        )
        with self.assertRaisesRegex(SelectorResolutionError, "qualified inspection point"):
            WorldMapNavigator().tap_visible_object(observation, target, reason="inspect_yolo_castle")

        test_point_target = replace(target, action_point=target.bounds.center())
        with_point = replace(
            observation,
            spatial_surface=replace(observation.spatial_surface, objects=(test_point_target,)),
        )
        with self.assertRaisesRegex(SelectorResolutionError, "qualified inspection point"):
            WorldMapNavigator().tap_visible_object(
                with_point, test_point_target, reason="inspect_yolo_castle",
            )

        qualified_target = replace(
            test_point_target,
            action_bounds=Bounds(*test_point_target.action_point, 1, 1),
            action_qualification=SpatialObjectActionQualification(
                geometry_policy="fixture_point",
                expected_screen=ScreenType.PNC_PLAYER_TERRITORY,
                review_ref="test_fixture",
            ),
        )
        qualified_observation = replace(
            observation,
            spatial_surface=replace(observation.spatial_surface, objects=(qualified_target,)),
        )
        actions = WorldMapNavigator().tap_visible_object(
            qualified_observation, qualified_target, reason="inspect_yolo_castle",
        )
        self.assertEqual(actions[0].target_point, target.bounds.center())

        edge_target = replace(
            qualified_target,
            bounds=Bounds(100, 350, 110, 105),
            action_point=(155, 402),
            action_bounds=Bounds(155, 402, 1, 1),
        )
        edge_observation = replace(
            observation,
            spatial_surface=replace(observation.spatial_surface, objects=(edge_target,)),
        )
        with self.assertRaisesRegex(SelectorResolutionError, "interior object box"):
            WorldMapNavigator().tap_visible_object(edge_observation, edge_target, reason="inspect_yolo_castle")

    def test_model_and_class_catalog_must_match_the_reviewed_export(self) -> None:
        wrong_hash = FakeDetector(())
        wrong_hash.model_sha256 = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            WorldYoloProducer(wrong_hash)
        wrong_names = FakeDetector(())
        wrong_names.class_names = tuple(reversed(WORLD_YOLO_QUALIFICATION.class_names))
        with self.assertRaisesRegex(ValueError, "class IDs"):
            WorldYoloProducer(wrong_names)
        with self.assertRaisesRegex(ValueError, "ROI version"):
            WorldYoloProducer(FakeDetector(()), replace(WORLD_YOLO_QUALIFICATION, roi_version="older"))

    def test_yolo_tap_keeps_the_exact_object_and_capture_frame(self) -> None:
        detector = FakeDetector((
            YoloDetection(2, "castle", 0.95, Bounds(205, 350, 60, 90)),
            YoloDetection(2, "castle", 0.91, Bounds(300, 350, 60, 90)),
        ))
        candidates = WorldYoloProducer(
            detector, _castle_qualification(),
        ).observe(Image.new("RGB", (540, 960))).objects
        base = make_observation(ScreenType.PNC_WORLD_MAP, image_size=(540, 960))
        targets = tuple(replace(
            candidate,
            name_text="Remote Lord",
            frame_ref=base.frame_ref,
            action_point=candidate.bounds.center(),
            action_bounds=Bounds(*candidate.bounds.center(), 1, 1),
            action_qualification=SpatialObjectActionQualification(
                geometry_policy="fixture_point",
                expected_screen=ScreenType.PNC_PLAYER_TERRITORY,
                review_ref="test_fixture",
            ),
        ) for candidate in candidates)
        observation = replace(base, spatial_surface=SpatialSurfaceObservation(
            SpatialSurfaceType.WORLD_MAP,
            SpatialViewport(SpatialViewportAddressingKind.COORDINATE_BAR, x=485, y=73),
            objects=targets,
        ))
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(), session=FakeSession(),
            stable_click_delay_ms=0, post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0, chat_post_action_observe_delay_ms=0,
            logger=build_logger(), sleep=lambda _: None,
        )
        action = WorldMapNavigator().tap_visible_object(observation, targets[1], reason="inspect")[0]
        self.assertEqual(action.expected_object, targets[1])

        changed = replace(observation, spatial_surface=replace(observation.spatial_surface, objects=(targets[0],)))
        with self.assertRaisesRegex(SelectorResolutionError, "not visible"):
            executor.execute_action(action, changed)
        fresh = make_observation(ScreenType.PNC_WORLD_MAP, image_size=(540, 960))
        fresh = replace(fresh, spatial_surface=replace(observation.spatial_surface, objects=tuple(
            replace(target, frame_ref=fresh.frame_ref) for target in targets
        )))
        with self.assertRaisesRegex(SelectorResolutionError, "different capture frame"):
            executor.execute_action(action, fresh)
        executor.execute_action(action, observation)
        self.assertEqual(executor.session.taps, [targets[1].action_point])

    def test_qualified_semantic_yolo_tap_uses_reviewed_point_even_without_action_point_flag(self) -> None:
        detection = YoloDetection(2, "castle", 0.95, Bounds(205, 350, 110, 105))
        interaction = WorldYoloInteractionQualification(
            model_sha256=WORLD_YOLO_QUALIFICATION.model_sha256,
            roi_version=WORLD_YOLO_QUALIFICATION.roi_version,
            classes={"castle": WorldYoloClassInteraction(
                point_ratio=(0.4, 0.3),
                expected_screen=ScreenType.PNC_PLAYER_TERRITORY,
                review_ref="test_fixture",
            )},
        )
        target = WorldYoloProducer(
            FakeDetector((detection,)), interaction_qualification=interaction,
        ).observe(Image.new("RGB", (540, 960))).objects[0]
        base = make_observation(ScreenType.PNC_WORLD_MAP, image_size=(540, 960))
        target = replace(target, frame_ref=base.frame_ref, name_text="Remote Lord")
        observation = replace(base, spatial_surface=SpatialSurfaceObservation(
            SpatialSurfaceType.WORLD_MAP,
            SpatialViewport(SpatialViewportAddressingKind.COORDINATE_BAR, x=485, y=73),
            objects=(target,),
        ))
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(), session=FakeSession(),
            stable_click_delay_ms=0, post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0, chat_post_action_observe_delay_ms=0,
            logger=build_logger(), sleep=lambda _: None,
        )
        query = SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.CASTLE)

        executor.execute_action(TapSpatialObjectAction(query=query), observation)

        self.assertNotEqual(target.action_point, target.bounds.center())
        self.assertEqual(executor.session.taps, [target.action_point])
        with self.assertRaisesRegex(SelectorResolutionError, "differs from its reviewed action geometry"):
            executor.execute_action(
                TapSpatialObjectAction(query=query, target_point=target.bounds.center()),
                observation,
            )
        second = replace(target, bounds=Bounds(310, 350, 110, 105), action_point=(354, 381),
                         action_bounds=Bounds(354, 381, 1, 1))
        ambiguous = replace(observation, spatial_surface=replace(
            observation.spatial_surface, objects=(target, second),
        ))
        with self.assertRaisesRegex(SelectorResolutionError, "ambiguous"):
            executor.execute_action(TapSpatialObjectAction(query=query), ambiguous)
        no_name = replace(observation, spatial_surface=replace(
            observation.spatial_surface, objects=(replace(target, name_text=None),),
        ))
        with self.assertRaisesRegex(SelectorResolutionError, "remote player name label"):
            executor.execute_action(TapSpatialObjectAction(query=query), no_name)
        self.assertEqual(executor.session.taps, [target.action_point])

    def test_semantic_and_concrete_spatial_actions_cannot_tap_yolo_castle(self) -> None:
        """The executor guards every spatial action path, including query fallback."""

        target = WorldYoloProducer(FakeDetector((
            YoloDetection(2, "castle", 0.95, Bounds(205, 350, 110, 105)),
        ))).observe(Image.new("RGB", (540, 960))).objects[0]
        base = make_observation(ScreenType.PNC_WORLD_MAP, image_size=(540, 960))
        observation = replace(base, spatial_surface=SpatialSurfaceObservation(
            SpatialSurfaceType.WORLD_MAP,
            SpatialViewport(SpatialViewportAddressingKind.COORDINATE_BAR, x=485, y=73),
            objects=(replace(target, frame_ref=base.frame_ref),),
        ))
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(), session=FakeSession(),
            stable_click_delay_ms=0, post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0, chat_post_action_observe_delay_ms=0,
            logger=build_logger(), sleep=lambda _: None,
        )
        query = SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.CASTLE)
        for action, message in (
            (TapSpatialObjectAction(query=query), "not qualified for spatial taps"),
            (TapSpatialObjectAction(query=query, target_point=target.bounds.center()), "not qualified for spatial taps"),
            (TapSpatialObjectAction(target_point=target.bounds.center()), "one exact semantic object"),
        ):
            with self.subTest(action=action), self.assertRaisesRegex(
                SelectorResolutionError, message,
            ):
                executor.execute_action(action, observation)
        self.assertEqual(executor.session.taps, [])


if __name__ == "__main__":
    unittest.main()
