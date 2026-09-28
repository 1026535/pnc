"""Home camera surface tests."""

from __future__ import annotations

from dataclasses import replace
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    SpatialObjectKind,
    SpatialObjectSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.home_city_camera import merge_camera_target_objects
from pnc_automation.app.pnc.vision.observation_provenance import bind_spatial_surface
from pnc_automation.app.pnc.vision.spatial_surfaces import (
    build_home_city_spatial_surface,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.capture_vision.home_camera_fixtures import (
    _CAMERA_FIXTURES,
    _fixture,
    _frame_ref,
    _localizer,
)


class HomeCityCameraSurfaceTests(unittest.TestCase):
    """The shared surface carries the proof and merges measured targets with OCR."""

    def test_surface_publishes_proof_and_template_objects_without_labels(self) -> None:
        image = _fixture(_CAMERA_FIXTURES / "home_city_tower_pan_28.png")

        surface = build_home_city_spatial_surface(
            image=image,
            lines=(),
            selector_registry=None,
            camera=_localizer(),
        )

        self.assertIsNotNone(surface.camera_proof)
        self.assertTrue(surface.camera_proof.localized)
        objects = {
            home_city_object_id_from_metadata(item.metadata): item
            for item in surface.objects
        }
        tower = objects[HomeCityObjectId.TOWER_OF_TRIAL]
        institute = objects[HomeCityObjectId.INSTITUTE]
        for object_ in (tower, institute):
            self.assertEqual(SpatialObjectKind.HOME_BUILDING, object_.kind)
            self.assertEqual(SpatialObjectSourceKind.TEMPLATE, object_.source_kind)
            self.assertIsNotNone(object_.action_point)
            self.assertIsNotNone(object_.action_bounds)
            self.assertTrue(object_.action_bounds.contains_point(object_.action_point))
            self.assertEqual("camera_template", object_.metadata["detection_source"])
        self.assertEqual("Tower of Trial", tower.name_text)
        self.assertEqual("Institute", institute.name_text)

    def test_surface_without_camera_keeps_existing_ocr_objects(self) -> None:
        from tests.support.pnc.capture_vision.ocr_line import _ocr_line

        surface = build_home_city_spatial_surface(
            image=Image.new("RGB", (900, 1600), (74, 104, 34)),
            lines=(_ocr_line("Institute", x=400, y=900, width=120, height=24),),
            selector_registry=None,
        )

        self.assertIsNone(surface.camera_proof)
        institute = next(
            item
            for item in surface.objects
            if home_city_object_id_from_metadata(item.metadata) == HomeCityObjectId.INSTITUTE
        )
        self.assertEqual(SpatialObjectSourceKind.OCR, institute.source_kind)

    def test_camera_merge_preserves_ocr_label_and_level_on_the_measured_object(self) -> None:
        from pnc_automation.app.pnc.domain.observation import DetectedSpatialObject, SpatialObjectRelationship

        ocr_object = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(100, 100, 80, 60),
            relationship=SpatialObjectRelationship.SELF,
            name_text="Insitute",
            level=12,
            action_point=(140, 130),
            metadata={"home_city_object_id": "institute", "home_city_label": "Insitute"},
        )
        camera_object = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(139, 185, 48, 45),
            relationship=SpatialObjectRelationship.SELF,
            name_text="Institute",
            action_point=(154, 193),
            action_bounds=Bounds(146, 187, 18, 11),
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={"home_city_object_id": "institute", "detection_source": "camera_template"},
        )

        merged = merge_camera_target_objects((ocr_object,), (camera_object,))

        self.assertEqual(1, len(merged))
        merged_object = merged[0]
        self.assertEqual(SpatialObjectSourceKind.TEMPLATE, merged_object.source_kind)
        self.assertEqual(Bounds(139, 185, 48, 45), merged_object.bounds)
        self.assertEqual((154, 193), merged_object.action_point)
        self.assertEqual("Insitute", merged_object.name_text)
        self.assertEqual(12, merged_object.level)
        self.assertEqual("Insitute", merged_object.metadata["home_city_label"])

    def test_camera_merge_keeps_unmatched_objects_and_adds_new_targets(self) -> None:
        from pnc_automation.app.pnc.domain.observation import DetectedSpatialObject, SpatialObjectRelationship

        goddess = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(10, 10, 50, 40),
            relationship=SpatialObjectRelationship.SELF,
            name_text="Goddess Statue",
            action_point=(35, 30),
            source_kind=SpatialObjectSourceKind.OCR,
            metadata={"home_city_object_id": "goddess_statue"},
        )
        tower = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(144, 456, 78, 84),
            relationship=SpatialObjectRelationship.SELF,
            name_text="Tower of Trial",
            action_point=(179, 512),
            action_bounds=Bounds(163, 492, 34, 30),
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={"home_city_object_id": "tower_of_trial"},
        )

        merged = merge_camera_target_objects((goddess,), (tower,))

        self.assertEqual(2, len(merged))
        ids = [home_city_object_id_from_metadata(item.metadata) for item in merged]
        self.assertEqual(
            [HomeCityObjectId.GODDESS_STATUE, HomeCityObjectId.TOWER_OF_TRIAL], ids
        )

    def test_provenance_binding_stamps_and_rejects_contradictory_spatial_facts(self) -> None:
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        surface = build_home_city_spatial_surface(
            image=image,
            lines=(),
            selector_registry=None,
            camera=_localizer(),
        )
        frame_ref = _frame_ref("camera-proof")

        bound = bind_spatial_surface(
            surface,
            frame_ref=frame_ref,
            source_screen=ScreenType.PNC_HOME_CITY,
            source_layout_id="layout-a",
        )

        self.assertEqual(frame_ref, bound.camera_proof.frame_ref)
        self.assertEqual(ScreenType.PNC_HOME_CITY, bound.camera_proof.source_screen)
        self.assertEqual("layout-a", bound.camera_proof.source_layout_id)
        self.assertTrue(all(item.frame_ref == frame_ref for item in bound.objects))
        self.assertTrue(
            all(item.source_screen == ScreenType.PNC_HOME_CITY for item in bound.objects)
        )

        foreign = replace(
            bound,
            camera_proof=replace(bound.camera_proof, frame_ref=_frame_ref("stale")),
        )
        with self.assertRaises(SelectorResolutionError):
            bind_spatial_surface(
                foreign,
                frame_ref=frame_ref,
                source_screen=ScreenType.PNC_HOME_CITY,
                source_layout_id="layout-a",
            )

    def test_provenance_binding_rejects_wrong_screen_on_objects(self) -> None:
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        surface = build_home_city_spatial_surface(
            image=image,
            lines=(),
            selector_registry=None,
            camera=_localizer(),
        )
        bound = bind_spatial_surface(
            surface,
            frame_ref=_frame_ref("proof"),
            source_screen=ScreenType.PNC_HOME_CITY,
            source_layout_id="layout-a",
        )
        foreign = replace(
            bound,
            objects=(replace(bound.objects[0], source_screen=ScreenType.PNC_WORLD_MAP),)
            + bound.objects[1:],
        )
        with self.assertRaises(SelectorResolutionError):
            bind_spatial_surface(
                foreign,
                frame_ref=_frame_ref("proof"),
                source_screen=ScreenType.PNC_HOME_CITY,
                source_layout_id="layout-a",
            )
