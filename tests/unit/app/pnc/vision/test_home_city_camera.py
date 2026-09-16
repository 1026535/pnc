"""Home-city camera localization from authored scene landmarks."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    SpatialObjectKind,
    SpatialObjectSourceKind,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.vision.home_city_camera import (
    HomeCityCameraCatalog,
    HomeCityCameraLandmark,
    HomeCityCameraLocalizer,
    load_home_city_camera_catalog,
    merge_camera_target_objects,
)
from pnc_automation.app.pnc.vision.observation_provenance import bind_spatial_surface
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import TemplateMatch
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)
from datetime import UTC, datetime

from tests.support.paths import TEST_DATA_ROOT


_SCREEN_RECOGNITION = TEST_DATA_ROOT / "screen_recognition"
_CAMERA_FIXTURES = TEST_DATA_ROOT / "home_city_camera"


def _fixture(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def _localizer() -> HomeCityCameraLocalizer:
    return HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())


class _ScriptedMatcher:
    """Matcher stub that returns scripted correspondences per landmark file name."""

    def __init__(self, matches: dict[str, TemplateMatch | None]) -> None:
        self._matches = matches

    def prepare_frame(self, image: Image.Image, *, reference_size=None) -> PreparedFrame:
        del image
        return PreparedFrame(
            pixels=np.zeros((1600, 900, 3), dtype=np.uint8),
            original_size=(900, 1600),
            reference_size=(900, 1600),
        )

    def find_best_match(self, frame, template_path: Path, *, threshold: float, **kwargs):
        del frame, threshold, kwargs
        return self._matches.get(template_path.name)


def _scripted_localizer(
    placements: dict[str, tuple[int, int] | None],
    *,
    score: float = 0.95,
) -> HomeCityCameraLocalizer:
    """Builds a localizer whose landmarks land at reference position + offset."""

    catalog = load_home_city_camera_catalog()
    matches: dict[str, TemplateMatch | None] = {}
    for landmark in catalog.landmarks:
        offset = placements.get(landmark.id)
        if offset is None:
            matches[landmark.file_name] = None
            continue
        matches[landmark.file_name] = TemplateMatch(
            bounds=replace(
                landmark.reference_bounds,
                x=landmark.reference_bounds.x + offset[0],
                y=landmark.reference_bounds.y + offset[1],
            ),
            confidence=score,
        )
    return HomeCityCameraLocalizer(matcher=_ScriptedMatcher(matches), catalog=catalog)


def _frame_ref(label: str) -> FrameRef:
    return FrameRef(
        session_id=label,
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime.now(tz=UTC),
    )


class HomeCityCameraCatalogTests(unittest.TestCase):
    """The packaged landmark catalog must stay self-consistent and small."""

    def test_catalog_loads_reviewed_landmarks_targets_and_anchor_basis(self) -> None:
        catalog = load_home_city_camera_catalog()

        self.assertEqual((900, 1600), catalog.reference_size)
        self.assertEqual((-532, 222), catalog.atlas_to_reference_offset)
        self.assertEqual(
            (HomeCityObjectId.CASTLE, HomeCityObjectId.INFANTRY_BARRACKS),
            catalog.anchor_object_ids,
        )
        self.assertEqual(8, len(catalog.landmarks))
        self.assertEqual(2, len(catalog.targets))
        groups = {landmark.group_id for landmark in catalog.landmarks}
        self.assertEqual(
            {"institute_structure", "garden_terrace", "plaza_low", "barracks_roofs", "tower_structure"},
            groups,
        )
        # Institute-correlated crops share one group so they cannot outvote
        # independent contradictory evidence.
        institute_votes = [
            landmark.id
            for landmark in catalog.landmarks
            if landmark.group_id == "institute_structure"
        ]
        self.assertEqual(
            {"p2_institute_facade", "p3_institute_base_left", "p6_path_right"},
            set(institute_votes),
        )
        for item in (*catalog.landmarks, *catalog.targets):
            self.assertTrue(catalog.template_path(item.file_name).is_file())
        self.assertIs(
            catalog.target_for(HomeCityObjectId.INSTITUTE),
            catalog.targets[0],
        )
        self.assertIsNone(catalog.target_for(HomeCityObjectId.CASTLE))


class HomeCityCameraLocalizationTests(unittest.TestCase):
    """Measured translations must reproduce the calibrated tour evidence."""

    def test_reference_layout_localizes_at_the_authored_origin(self) -> None:
        proof = _localizer().localize(_fixture(_SCREEN_RECOGNITION / "home_city_core.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, 222), proof.translation)
        self.assertEqual((540, 960), proof.frame_size)
        self.assertEqual((900, 1600), proof.reference_size)
        self.assertGreaterEqual(len(proof.evidence), 5)
        self.assertGreaterEqual(len(proof.matched_group_ids), 3)
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_live_hud_occlusion_keeps_camera_but_does_not_invent_institute_body(self) -> None:
        """The live offer rail hides Institute; three other scene regions still locate Home."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(_fixture(_CAMERA_FIXTURES / "home_city_hud_occluded_20260916.png"))
        proof = localizer.localize(prepared)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, 222), proof.translation)
        self.assertEqual(
            frozenset({"plaza_low", "garden_terrace", "barracks_roofs"}),
            proof.matched_group_ids,
        )
        self.assertFalse(localizer.matched_target_objects(prepared, proof=proof))

    def test_live_tower_pan_localizes_after_northern_landmarks_leave_view(self) -> None:
        """The qualified Tower body extends camera proof beyond the Institute region."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(_fixture(_CAMERA_FIXTURES / "home_city_tower_lower_20260916.png"))
        proof = localizer.localize(prepared)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, -843), proof.translation)
        self.assertIn("tower_structure", proof.matched_group_ids)
        target = localizer.catalog.target_for(HomeCityObjectId.TOWER_OF_TRIAL)
        match = localizer.match_target(prepared, target, translation=proof.translation)
        self.assertIsNotNone(match)
        self.assertEqual((179, 389), match.action_point)

    def test_pan_pair_localizes_at_the_measured_image_translation(self) -> None:
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_pan_07.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Image translation -468,-931 relative to the authored reference view,
        # combined with the -532,+222 atlas offset.
        self.assertEqual((-1000, -710), proof.translation)
        self.assertIn("institute_structure", proof.matched_group_ids)
        self.assertIn("plaza_low", proof.matched_group_ids)

    def test_tower_view_localizes_at_the_measured_image_translation(self) -> None:
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_tower_pan_28.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, -638), proof.translation)
        self.assertIn("barracks_roofs", proof.matched_group_ids)

    def test_different_castle_appearance_still_localizes(self) -> None:
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_mega_castle.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-822, -260), proof.translation)

    def test_tracked_panned_fixture_localizes_at_its_measured_translation(self) -> None:
        proof = _localizer().localize(_fixture(_SCREEN_RECOGNITION / "home_city_panned_core.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-822, -260), proof.translation)

    def test_world_map_is_the_true_camera_negative(self) -> None:
        proof = _localizer().localize(_fixture(_SCREEN_RECOGNITION / "world_map_core.png"))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)
        self.assertEqual("no_landmark_correspondences", proof.reason)

    def test_unsupported_aspect_returns_unsupported_not_a_guess(self) -> None:
        image = Image.new("RGB", (640, 960), (30, 40, 20))

        proof = _localizer().localize(image)

        self.assertEqual(HomeCityCameraStatus.UNSUPPORTED, proof.status)
        self.assertIsNone(proof.translation)
        self.assertEqual((640, 960), proof.frame_size)

    def test_projection_is_scale_normalized_into_frame_pixels(self) -> None:
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="test",
            translation=(-532, 222),
            frame_size=(540, 960),
        )

        # Castle nameplate anchor: atlas (991,625) + T -> reference (459,847)
        # -> 540x960 frame pixels (275,508).
        self.assertEqual((275, 508), proof.project_to_frame((991, 625)))
        # The same proof at the reference size projects without scaling.
        at_reference = replace(proof, frame_size=(900, 1600))
        self.assertEqual((459, 847), at_reference.project_to_frame((991, 625)))

    def test_projection_requires_localization(self) -> None:
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.INSUFFICIENT,
            reason="test",
            frame_size=(540, 960),
        )

        with self.assertRaises(SelectorResolutionError):
            proof.project_to_frame((991, 625))

    def test_proof_validation_rejects_inconsistent_transforms(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            HomeCityCameraProof(
                status=HomeCityCameraStatus.LOCALIZED,
                reason="missing translation",
                frame_size=(540, 960),
            )
        with self.assertRaises(SelectorResolutionError):
            HomeCityCameraProof(
                status=HomeCityCameraStatus.INSUFFICIENT,
                reason="carries translation",
                translation=(0, 0),
                frame_size=(540, 960),
            )


class HomeCityCameraConsensusTests(unittest.TestCase):
    """Consensus fitting must qualify independent groups and reject conflicts."""

    def test_no_correspondences_is_insufficient(self) -> None:
        localizer = _scripted_localizer({})

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("no_landmark_correspondences", proof.reason)

    def test_single_group_cannot_localize_even_with_three_votes(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_independent_landmark_groups", proof.reason)
        self.assertIsNone(proof.translation)

    def test_two_groups_with_too_few_votes_is_insufficient(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "t5_barracks_roofs": (10, -20),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_landmark_correspondences", proof.reason)

    def test_agreeing_groups_fit_the_consensus_translation(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
                "p4_garden_terrace": (11, -20),
                "t5_barracks_roofs": (9, -21),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Consensus image translation (10,-20) plus the (-532,+222) atlas offset.
        self.assertEqual((-522, 202), proof.translation)
        self.assertEqual(5, len(proof.evidence))
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_outlier_votes_do_not_pollute_the_consensus_cluster(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
                "p4_garden_terrace": (10, -19),
                "t5_barracks_roofs": (400, 500),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-522, 202), proof.translation)
        self.assertNotIn("t5_barracks_roofs", {item.landmark_id for item in proof.evidence})

    def test_two_qualifying_contradictory_clusters_are_ambiguous(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p4_garden_terrace": (10, -20),
                "t5_barracks_roofs": (10, -20),
                "p3_institute_base_left": (300, 400),
                "p6_path_right": (300, 400),
                "p5_plaza_low": (300, 400),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.AMBIGUOUS, proof.status)
        self.assertIsNone(proof.translation)


class HomeCityCameraTargetTests(unittest.TestCase):
    """Body targets only publish when they agree with the localized projection."""

    def test_institute_body_matches_pan_view_with_verified_action_geometry(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)

        match = localizer.match_target(frame, target, translation=proof.translation)

        self.assertIsNotNone(match)
        self.assertLessEqual(match.projection_error, 8.0)
        self.assertGreaterEqual(match.score, 0.9)
        # The verified 07 tap (256,322) at 900x1600 scales to (154,193) at 540x960.
        self.assertEqual((154, 193), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))
        self.assertTrue(match.bounds.contains_bounds(match.action_bounds))

    def test_institute_body_matches_reference_and_mega_views(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)
        for name in (
            _SCREEN_RECOGNITION / "home_city_core.png",
            _SCREEN_RECOGNITION / "home_city_panned_core.png",
            _CAMERA_FIXTURES / "home_city_mega_castle.png",
        ):
            with self.subTest(fixture=name.name):
                image = _fixture(name)
                frame = localizer.prepare_frame(image)
                proof = localizer.localize(frame)
                match = localizer.match_target(frame, target, translation=proof.translation)
                self.assertIsNotNone(match)
                self.assertGreaterEqual(match.score, 0.9)

    def test_institute_body_rejects_when_projection_disagrees(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        frame = localizer.prepare_frame(image)
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)

        # A contradictory camera hypothesis must not publish a body target.
        match = localizer.match_target(frame, target, translation=(-532, 222))

        self.assertIsNone(match)

    def test_tower_body_matches_only_its_qualified_view(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.TOWER_OF_TRIAL)

        image = _fixture(_CAMERA_FIXTURES / "home_city_tower_pan_28.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, translation=proof.translation)

        self.assertIsNotNone(match)
        # Verified tower tap (299,854) at 900x1600 scales to (179,512) at 540x960.
        self.assertEqual((179, 512), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))

        for name in (
            _SCREEN_RECOGNITION / "home_city_core.png",
            _CAMERA_FIXTURES / "home_city_pan_07.png",
            _CAMERA_FIXTURES / "home_city_mega_castle.png",
        ):
            with self.subTest(fixture=name.name):
                other = localizer.prepare_frame(_fixture(name))
                other_proof = localizer.localize(other)
                self.assertIsNone(
                    localizer.match_target(other, target, translation=other_proof.translation)
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


if __name__ == "__main__":
    unittest.main()
