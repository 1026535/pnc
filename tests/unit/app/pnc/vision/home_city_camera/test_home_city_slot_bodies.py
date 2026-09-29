"""Tests for slot-aware measured Home-city body publication.

The Blacksmith body is the first qualified appearance bound to a player-chosen
ordinary slot: its crop was authored while the building occupied slot 12 on the
reviewed 2026-09-22 157_farm views, so matching derives every eligible
candidate's predicted body rectangle from calibrated slot pivots and publishes
only unambiguous, projection-agreed hits tagged with the observed
``HomeCitySlotSelector``.  Native fixtures stay RGBA 900x1600 and publisher
tests pass ``source.copy()`` so no conversion hides the capture's real mode;
synthetic matcher/proof cases are labeled synthetic and never claimed as
native coverage.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityMapCoordinate,
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.domain.home_city_slots import (
    HomeCitySlotEligibility,
    HomeCitySlotKind,
    HomeCitySlotSelector,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject,
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialObjectSourceKind,
)
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    HOME_CITY_HUD_SAFE_MAX_X_RATIO,
    HOME_CITY_HUD_SAFE_MAX_Y_RATIO,
    HOME_CITY_HUD_SAFE_MIN_X_RATIO,
    HOME_CITY_HUD_SAFE_MIN_Y_RATIO,
)
from pnc_automation.app.pnc.vision.home_city_camera import (
    HomeCityCameraLocalizer,
    HomeCityCameraTarget,
    load_home_city_camera_catalog,
    merge_camera_target_objects,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

from tests.support.paths import TEST_DATA_ROOT


FIXTURES = TEST_DATA_ROOT / "home_city_slot_bodies"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def _fixture(name: str) -> Image.Image:
    """Load a native fixture at its authored RGBA mode for camera matching."""

    path = FIXTURES / name
    with Image.open(path) as source:
        assert source.mode == "RGBA" and source.size == (900, 1600)
        return source.copy()


def _catalog_target(object_id: HomeCityObjectId) -> HomeCityCameraTarget:
    catalog = load_home_city_camera_catalog()
    return next(target for target in catalog.targets if target.object_id == object_id)


def _localized_proof(
    translation: tuple[int, int],
    *,
    zoom: float = 1.0,
    frame_size: tuple[int, int] = (900, 1600),
) -> HomeCityCameraProof:
    """Build a localized proof for candidate matching over native evidence."""

    return HomeCityCameraProof(
        status=HomeCityCameraStatus.LOCALIZED,
        reason="synthetic_reviewed_transform",
        translation=translation,
        zoom=zoom,
        frame_size=frame_size,
    )


def _camera_object(
    object_id: HomeCityObjectId,
    bounds: Bounds,
    *,
    slot: int | None,
) -> DetectedSpatialObject:
    """Build a measured camera object with typed slot identity for merge tests."""

    return DetectedSpatialObject(
        kind=SpatialObjectKind.HOME_BUILDING,
        bounds=bounds,
        relationship=SpatialObjectRelationship.SELF,
        name_text="camera-name",
        action_point=bounds.center(),
        action_bounds=Bounds(
            bounds.x + 2, bounds.y + 2, bounds.width - 4, bounds.height - 4
        ),
        source_kind=SpatialObjectSourceKind.TEMPLATE,
        home_city_slot=None if slot is None else HomeCitySlotSelector(slot),
        metadata={"home_city_object_id": object_id.value},
    )


def _ocr_object(
    object_id: HomeCityObjectId | None,
    bounds: Bounds,
    *,
    slot: int | None = None,
    name: str = "ocr-name",
    level: int | None = 7,
) -> DetectedSpatialObject:
    """Build an OCR-derived object; ``slot`` models explicit label-slot evidence."""

    metadata = {"home_city_label": {"raw_text": name}}
    if object_id is not None:
        metadata["home_city_object_id"] = object_id.value
    return DetectedSpatialObject(
        kind=SpatialObjectKind.HOME_BUILDING,
        bounds=bounds,
        relationship=SpatialObjectRelationship.SELF,
        name_text=name,
        level=level,
        source_kind=SpatialObjectSourceKind.OCR,
        home_city_slot=None if slot is None else HomeCitySlotSelector(slot),
        metadata=metadata,
    )


def _synthetic_slot(index: int, pivot: tuple[int, int]) -> HomeCitySlotEligibility:
    """One synthetic eligible slot for ambiguity placement cases (not native data)."""

    return HomeCitySlotEligibility(
        slot_index=index,
        area_id=1,
        kind=HomeCitySlotKind.MULTI_TYPE,
        init_position=False,
        client_type_ids=frozenset({1008}),
        eligible_object_ids=frozenset({HomeCityObjectId.BLACKSMITH}),
        unlock_cost_item_id=None,
        unlock_cost_count=None,
        atlas_coordinate=HomeCityMapCoordinate(*pivot),
        coordinate_evidence="synthetic_placement_case",
        inferred_atlas_coordinate=None,
        inferred_coordinate_source=None,
    )


class _RegionScriptedMatcher:
    """Synthetic matcher returning hits for regions containing scripted centers.

    Each key is a predicted-body center; a region that contains it yields the
    scripted match.  Used only for deterministic placement cases -- never as
    native or account evidence.
    """

    def __init__(self, hits: dict[tuple[int, int], TemplateMatch]) -> None:
        self._hits = hits

    def prepare_frame(self, image: Image.Image, *, reference_size=None) -> PreparedFrame:
        del image
        return PreparedFrame(
            pixels=np.zeros((1600, 900, 3), dtype=np.uint8),
            original_size=(900, 1600),
            reference_size=(900, 1600),
        )

    def prepare_proposal_frame(self, frame: PreparedFrame) -> PreparedFrame:
        return frame

    def find_best_match(self, frame, template_path: Path, *, threshold: float, **kwargs):
        del frame, threshold
        region = kwargs.get("search_region")
        if region is None:
            return None
        for center, match in self._hits.items():
            if region.contains_point(center):
                return match
        return None


class HomeCitySlotSelectorTests(unittest.TestCase):
    """The typed selector accepts only explicit ordinary slot indexes."""

    def test_valid_indexes_are_accepted(self) -> None:
        for index in (1, 12, 54):
            self.assertEqual(index, HomeCitySlotSelector(index).slot_index)

    def test_invalid_indexes_are_rejected(self) -> None:
        for bad in (0, 55, -1, True, False, "12", 1.5, None):
            with self.subTest(value=bad):
                with self.assertRaises(SelectorResolutionError):
                    HomeCitySlotSelector(bad)


class DetectedSpatialObjectSlotTests(unittest.TestCase):
    """The additive slot field stays typed through construction and replace."""

    def test_typed_slot_is_retained(self) -> None:
        object_ = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(1, 1, 20, 20), slot=12)
        self.assertEqual(HomeCitySlotSelector(12), object_.home_city_slot)
        self.assertEqual(HomeCitySlotSelector(12), replace(object_, level=3).home_city_slot)

    def test_untyped_slot_is_rejected(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            DetectedSpatialObject(
                kind=SpatialObjectKind.HOME_BUILDING,
                bounds=Bounds(1, 1, 20, 20),
                relationship=SpatialObjectRelationship.SELF,
                home_city_slot=12,
            )

    def test_legacy_objects_default_to_no_slot(self) -> None:
        object_ = _camera_object(HomeCityObjectId.TOWER_OF_TRIAL, Bounds(1, 1, 20, 20), slot=None)
        self.assertIsNone(object_.home_city_slot)


class CameraTargetSlotContractTests(unittest.TestCase):
    """Reference-slot bindings and guarded atlas action geometry."""

    def test_blacksmith_binding_and_slot_action_points(self) -> None:
        target = _catalog_target(HomeCityObjectId.BLACKSMITH)
        self.assertEqual(HomeCitySlotSelector(12), target.reference_slot)
        self.assertEqual("blacksmith_structure.png", target.file_name)
        self.assertEqual(Bounds(640, 1845, 120, 130), target.reference_bounds)
        self.assertEqual((710, 1925), target.reference_action_point)
        # Atlas points from the calibrated pivots; slot 12 reproduces the
        # lead-measured native (712,829) under the f2 translation (-530,-874).
        self.assertEqual((1242, 1703), target.atlas_action_point(home_city_slot=HomeCitySlotSelector(12)))
        self.assertEqual((1524, 1577), target.atlas_action_point(home_city_slot=HomeCitySlotSelector(11)))
        self.assertEqual((1826, 1448), target.atlas_action_point(home_city_slot=HomeCitySlotSelector(13)))

    def test_movable_target_requires_explicit_slot_for_atlas_action(self) -> None:
        target = _catalog_target(HomeCityObjectId.BLACKSMITH)
        with self.assertRaises(SelectorResolutionError):
            target.atlas_action_point()
        with self.assertRaises(SelectorResolutionError):
            target.atlas_action_point(home_city_slot=HomeCitySlotSelector(9))
        with self.assertRaises(SelectorResolutionError):
            target.atlas_action_point(home_city_slot="12")

    def test_single_type_binding_keeps_authored_point(self) -> None:
        target = _catalog_target(HomeCityObjectId.INSTITUTE)
        self.assertEqual(HomeCitySlotSelector(9), target.reference_slot)
        self.assertEqual((1256, 1031), target.atlas_action_point())
        self.assertEqual(
            (1256, 1031),
            target.atlas_action_point(home_city_slot=HomeCitySlotSelector(9)),
        )
        with self.assertRaises(SelectorResolutionError):
            target.atlas_action_point(home_city_slot=HomeCitySlotSelector(12))

    def test_fixed_targets_reject_slot_arguments(self) -> None:
        target = _catalog_target(HomeCityObjectId.TOWER_OF_TRIAL)
        self.assertIsNone(target.reference_slot)
        self.assertEqual((831, 1492), target.atlas_action_point())
        with self.assertRaises(SelectorResolutionError):
            target.atlas_action_point(home_city_slot=HomeCitySlotSelector(12))

    def test_reference_slot_must_be_eligible_and_typed(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.BLACKSMITH,
                landmark_id="x",
                file_name="x.png",
                reference_bounds=Bounds(0, 0, 10, 10),
                reference_action_bounds=Bounds(0, 0, 4, 4),
                reference_action_point=(2, 2),
                min_score=0.9,
                max_projection_error=12,
                reference_slot=HomeCitySlotSelector(9),
            )
        with self.assertRaises(SelectorResolutionError):
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.BLACKSMITH,
                landmark_id="x",
                file_name="x.png",
                reference_bounds=Bounds(0, 0, 10, 10),
                reference_action_bounds=Bounds(0, 0, 4, 4),
                reference_action_point=(2, 2),
                min_score=0.9,
                max_projection_error=12,
                reference_slot=12,
            )


class NativeSlotBodyMatchTests(unittest.TestCase):
    """Real native frames produce slot-tagged measured bodies through the catalog."""

    def setUp(self) -> None:
        self.localizer = HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())
        self.blacksmith = _catalog_target(HomeCityObjectId.BLACKSMITH)

    def _proof_and_frame(self, name: str):
        image = _fixture(name)
        proof = self.localizer.localize(image.copy())
        self.assertTrue(proof.localized, f"{name} must localize on reviewed evidence")
        return proof, self.localizer.prepare_frame(image)

    def test_f2_publishes_blacksmith_at_slot_12_with_measured_action(self) -> None:
        proof, frame = self._proof_and_frame("home_city_blacksmith_slot12_f2_20260922.png")
        self.assertEqual((-530, -874), proof.translation)
        matches = self.localizer.match_target_candidates(frame, self.blacksmith, proof=proof)
        self.assertEqual(1, len(matches))
        match = matches[0]
        self.assertEqual(HomeCitySlotSelector(12), match.home_city_slot)
        self.assertEqual(Bounds(642, 749, 120, 130), match.bounds)
        self.assertGreaterEqual(match.score, 0.9)
        self.assertLessEqual(match.projection_error, 12)
        self.assertEqual((712, 829), match.action_point)
        self.assertEqual(Bounds(702, 819, 20, 20), match.action_bounds)
        self.assertTrue(match.bounds.contains_bounds(match.action_bounds))
        self.assertTrue(match.action_bounds.contains_point(match.action_point))
        self.assertEqual(match, self.localizer.match_target(frame, self.blacksmith, proof=proof))

        objects = self.localizer.matched_target_objects(frame, proof=proof)
        blacksmith = next(
            object_
            for object_ in objects
            if home_city_object_id_from_metadata(object_.metadata) is HomeCityObjectId.BLACKSMITH
        )
        self.assertEqual(HomeCitySlotSelector(12), blacksmith.home_city_slot)
        self.assertEqual(match.bounds, blacksmith.bounds)
        self.assertEqual(match.action_point, blacksmith.action_point)
        self.assertEqual(match.action_bounds, blacksmith.action_bounds)
        self.assertEqual(SpatialObjectSourceKind.TEMPLATE, blacksmith.source_kind)
        self.assertEqual("camera_template", blacksmith.metadata["detection_source"])
        self.assertEqual(12, blacksmith.metadata["home_city_slot_index"])

    def test_wall_holdout_and_goddess_publish_only_their_measured_slots(self) -> None:
        for name, identity, slot, point in (
            ("home_city_wall_slot2_f6_20260922.png", HomeCityObjectId.WALL, 2, (118, 983)),
            ("home_city_goddess_slot15_0066_20260923.png", HomeCityObjectId.GODDESS_STATUE, 15, (398, 200)),
        ):
            with self.subTest(identity=identity):
                proof, frame = self._proof_and_frame(name)
                target = _catalog_target(identity)
                matches = self.localizer.match_target_candidates(frame, target, proof=proof)
                self.assertEqual(1, len(matches))
                self.assertEqual(HomeCitySlotSelector(slot), matches[0].home_city_slot)
                self.assertEqual(point, matches[0].action_point)
                self.assertTrue(matches[0].bounds.contains_bounds(matches[0].action_bounds))

    def test_goddess_native_zoom_and_erased_body(self) -> None:
        path = TEST_DATA_ROOT / "home_city_camera" / "home_city_native_zoom_holdout_20260922.png"
        with Image.open(path) as source:
            image = source.copy()
        self.assertEqual("RGBA", image.mode)
        proof = self.localizer.localize(image)
        self.assertTrue(proof.localized)
        self.assertAlmostEqual(1.071989179, proof.zoom, delta=0.005)
        target = _catalog_target(HomeCityObjectId.GODDESS_STATUE)
        matches = self.localizer.match_target_candidates(
            self.localizer.prepare_frame(image), target, proof=proof,
        )
        self.assertEqual(1, len(matches))
        self.assertEqual(HomeCitySlotSelector(15), matches[0].home_city_slot)
        self.assertEqual((462, 1201), matches[0].action_point)
        self.assertTrue(matches[0].bounds.contains_bounds(matches[0].action_bounds))
        body = matches[0].bounds
        image.paste((0, 0, 0, 255), (body.x, body.y, body.x + body.width, body.y + body.height))
        self.assertEqual((), self.localizer.match_target_candidates(
            self.localizer.prepare_frame(image), target, proof=proof,
        ))

    def test_goddess_body_on_0066_lands_above_the_safe_tap_band(self) -> None:
        """The observed Goddess view measures the statue body but cannot tap it.

        Live005 frame 0066 (camera (-595,-847), zoom 1.0) shows the slot-15
        gold column at (368,145,60,78) with candidate action (398,200).  That
        point sits above the production HUD-safe band, so navigation may use
        this view for measurement only and must pan/reobserve before tapping;
        the earlier platform-trim target was never tap authority.
        """
        proof, frame = self._proof_and_frame("home_city_goddess_slot15_0066_20260923.png")
        self.assertEqual((-595, -847), proof.translation)
        self.assertAlmostEqual(1.0, proof.zoom)
        target = _catalog_target(HomeCityObjectId.GODDESS_STATUE)
        matches = self.localizer.match_target_candidates(frame, target, proof=proof)
        self.assertEqual(1, len(matches))
        match = matches[0]
        self.assertEqual(HomeCitySlotSelector(15), match.home_city_slot)
        self.assertEqual(Bounds(368, 145, 60, 78), match.bounds)
        self.assertEqual((398, 200), match.action_point)
        self.assertEqual(Bounds(388, 190, 20, 20), match.action_bounds)
        self.assertTrue(match.bounds.contains_bounds(match.action_bounds))
        self.assertLess(match.action_point[1], int(HOME_CITY_HUD_SAFE_MIN_Y_RATIO * 1600))

    def test_goddess_platform_without_body_never_publishes(self) -> None:
        """The surviving platform ring alone cannot produce a Goddess body."""
        image = _fixture("home_city_goddess_slot15_0066_20260923.png")
        proof = self.localizer.localize(image.copy())
        self.assertTrue(proof.localized)
        target = _catalog_target(HomeCityObjectId.GODDESS_STATUE)
        matches = self.localizer.match_target_candidates(
            self.localizer.prepare_frame(image), target, proof=proof,
        )
        self.assertEqual(1, len(matches))
        body = matches[0].bounds
        # Erase only the statue column/plinth; the platform ring trim below it
        # stays fully intact and still must not publish a body.
        image.paste((0, 0, 0, 255), (body.x, body.y, body.x + body.width, body.y + body.height))
        self.assertEqual((), self.localizer.match_target_candidates(
            self.localizer.prepare_frame(image), target, proof=proof,
        ))

    def test_goddess_banner_occluded_column_stays_unmatched(self) -> None:
        """The slot12_f2 coordinate banner covers the column: honest no-match."""
        proof, frame = self._proof_and_frame("home_city_blacksmith_slot12_f2_20260922.png")
        target = _catalog_target(HomeCityObjectId.GODDESS_STATUE)
        self.assertEqual((), self.localizer.match_target_candidates(frame, target, proof=proof))

    def test_f1_publishes_blacksmith_at_slot_12_independently(self) -> None:
        proof, frame = self._proof_and_frame("home_city_blacksmith_slot12_f1_20260922.png")
        self.assertEqual((-530, -391), proof.translation)
        matches = self.localizer.match_target_candidates(frame, self.blacksmith, proof=proof)
        self.assertEqual(1, len(matches))
        self.assertEqual(HomeCitySlotSelector(12), matches[0].home_city_slot)
        self.assertEqual(Bounds(642, 1232, 120, 130), matches[0].bounds)
        self.assertEqual((712, 1312), matches[0].action_point)

    def test_offscreen_candidates_publish_no_blacksmith(self) -> None:
        proof, frame = self._proof_and_frame("home_city_baseline_f0_20260922.png")
        self.assertEqual((-532, 222), proof.translation)
        self.assertEqual((), self.localizer.match_target_candidates(frame, self.blacksmith, proof=proof))
        self.assertIsNone(self.localizer.match_target(frame, self.blacksmith, proof=proof))
        objects = self.localizer.matched_target_objects(frame, proof=proof)
        self.assertFalse(any(
            home_city_object_id_from_metadata(object_.metadata) is HomeCityObjectId.BLACKSMITH
            for object_ in objects
        ))

    def test_wrong_slot_content_never_claims_the_candidate(self) -> None:
        proof, frame = self._proof_and_frame("home_city_pan2_f5_20260922.png")
        self.assertEqual((-1632, -718), proof.translation)
        self.assertEqual((), self.localizer.match_target_candidates(frame, self.blacksmith, proof=proof))

    def test_institute_publishes_with_slot_9_binding(self) -> None:
        proof, frame = self._proof_and_frame("home_city_baseline_f0_20260922.png")
        institute = _catalog_target(HomeCityObjectId.INSTITUTE)
        matches = self.localizer.match_target_candidates(frame, institute, proof=proof)
        self.assertEqual(1, len(matches))
        self.assertEqual(HomeCitySlotSelector(9), matches[0].home_city_slot)
        self.assertEqual(Bounds(700, 1240, 80, 75), matches[0].bounds)
        self.assertEqual((724, 1253), matches[0].action_point)

    def test_unlocalized_proofs_publish_nothing(self) -> None:
        for status in (
            HomeCityCameraStatus.INSUFFICIENT,
            HomeCityCameraStatus.AMBIGUOUS,
            HomeCityCameraStatus.UNSUPPORTED,
        ):
            with self.subTest(status=status):
                proof = HomeCityCameraProof(status=status, reason="synthetic")
                self.assertEqual(
                    (),
                    self.localizer.match_target_candidates(
                        _fixture("home_city_blacksmith_slot12_f2_20260922.png"),
                        self.blacksmith,
                        proof=proof,
                    ),
                )

    def test_warehouse_publishes_slot_3_on_source_and_holdout_views(self) -> None:
        warehouse = _catalog_target(HomeCityObjectId.WAREHOUSE)
        for name, translation, bounds, point in (
            (
                "home_city_warehouse_slot3_0047_20260929.png",
                (-777, 55),
                Bounds(282, 667, 83, 102),
                (330, 718),
            ),
            (
                "home_city_warehouse_slot3_0084_20260929.png",
                (-389, -427),
                Bounds(684, 197, 84, 104),
                (733, 249),
            ),
        ):
            with self.subTest(fixture=name):
                proof, frame = self._proof_and_frame(name)
                self.assertEqual(translation, proof.translation)
                matches = self.localizer.match_target_candidates(
                    frame, warehouse, proof=proof
                )
                self.assertEqual(1, len(matches))
                match = matches[0]
                self.assertEqual(HomeCitySlotSelector(3), match.home_city_slot)
                self.assertEqual(bounds, match.bounds)
                self.assertEqual(point, match.action_point)
                self.assertGreaterEqual(match.score, 0.9)
                self.assertLessEqual(match.projection_error, 12)
                self.assertTrue(match.bounds.contains_bounds(match.action_bounds))
                self.assertTrue(match.action_bounds.contains_point(match.action_point))
                self.assertEqual(
                    match,
                    self.localizer.match_target(frame, warehouse, proof=proof),
                )

                objects = self.localizer.matched_target_objects(frame, proof=proof)
                published = next(
                    object_
                    for object_ in objects
                    if home_city_object_id_from_metadata(object_.metadata)
                    is HomeCityObjectId.WAREHOUSE
                )
                self.assertEqual(HomeCitySlotSelector(3), published.home_city_slot)
                self.assertEqual(match.bounds, published.bounds)
                self.assertEqual(match.action_point, published.action_point)
                self.assertEqual("camera_template", published.metadata["detection_source"])
                self.assertEqual(3, published.metadata["home_city_slot_index"])

    def test_warehouse_0047_action_lies_inside_the_safe_tap_band(self) -> None:
        """The source view's measured body point stays inside the HUD-safe band."""

        proof, frame = self._proof_and_frame("home_city_warehouse_slot3_0047_20260929.png")
        match = self.localizer.match_target(
            frame, _catalog_target(HomeCityObjectId.WAREHOUSE), proof=proof
        )
        self.assertIsNotNone(match)
        x, y = match.action_point
        self.assertLessEqual(int(HOME_CITY_HUD_SAFE_MIN_X_RATIO * 900), x)
        self.assertLessEqual(x, int(HOME_CITY_HUD_SAFE_MAX_X_RATIO * 900))
        self.assertLessEqual(int(HOME_CITY_HUD_SAFE_MIN_Y_RATIO * 1600), y)
        self.assertLessEqual(y, int(HOME_CITY_HUD_SAFE_MAX_Y_RATIO * 1600))

    def test_warehouse_erased_or_occluded_body_never_publishes(self) -> None:
        warehouse = _catalog_target(HomeCityObjectId.WAREHOUSE)
        image = _fixture("home_city_warehouse_slot3_0047_20260929.png")
        proof = self.localizer.localize(image.copy())
        self.assertTrue(proof.localized)
        matches = self.localizer.match_target_candidates(
            self.localizer.prepare_frame(image), warehouse, proof=proof
        )
        self.assertEqual(1, len(matches))
        body = matches[0].bounds
        image.paste((0, 0, 0, 255), (body.x, body.y, body.x + body.width, body.y + body.height))
        self.assertEqual(
            (),
            self.localizer.match_target_candidates(
                self.localizer.prepare_frame(image), warehouse, proof=proof
            ),
        )

    def test_warehouse_never_publishes_on_unrelated_views(self) -> None:
        warehouse = _catalog_target(HomeCityObjectId.WAREHOUSE)
        for name in (
            "home_city_blacksmith_slot12_f1_20260922.png",
            "home_city_blacksmith_slot12_f2_20260922.png",
            "home_city_baseline_f0_20260922.png",
            "home_city_pan2_f5_20260922.png",
            "home_city_wall_slot2_f6_20260922.png",
            "home_city_goddess_slot15_0066_20260923.png",
            "home_city_bank_sys1_0022_20260929.png",
            "home_city_bank_sys1_0092_20260929.png",
        ):
            with self.subTest(fixture=name):
                proof, frame = self._proof_and_frame(name)
                self.assertEqual(
                    (),
                    self.localizer.match_target_candidates(
                        frame, warehouse, proof=proof
                    ),
                )

    def test_bank_publishes_fixed_body_on_source_and_holdout_views(self) -> None:
        bank = _catalog_target(HomeCityObjectId.BANK)
        for name, translation, bounds, point in (
            (
                "home_city_bank_sys1_0022_20260929.png",
                (-24, 45),
                Bounds(216, 1036, 120, 97),
                (275, 1070),
            ),
            (
                "home_city_bank_sys1_0092_20260929.png",
                (-152, -21),
                Bounds(88, 971, 120, 97),
                (147, 1006),
            ),
        ):
            with self.subTest(fixture=name):
                proof, frame = self._proof_and_frame(name)
                self.assertEqual(translation, proof.translation)
                matches = self.localizer.match_target_candidates(
                    frame, bank, proof=proof
                )
                self.assertEqual(1, len(matches))
                match = matches[0]
                # The fixed sys_1/5001 node owns no ordinary slot.
                self.assertIsNone(match.home_city_slot)
                self.assertEqual(bounds, match.bounds)
                self.assertEqual(point, match.action_point)
                self.assertGreaterEqual(match.score, 0.9)
                self.assertLessEqual(match.projection_error, 8)
                self.assertTrue(match.bounds.contains_bounds(match.action_bounds))
                self.assertTrue(match.action_bounds.contains_point(match.action_point))
                self.assertEqual(
                    match,
                    self.localizer.match_target(frame, bank, proof=proof),
                )

                objects = self.localizer.matched_target_objects(frame, proof=proof)
                published = next(
                    object_
                    for object_ in objects
                    if home_city_object_id_from_metadata(object_.metadata)
                    is HomeCityObjectId.BANK
                )
                self.assertIsNone(published.home_city_slot)
                self.assertNotIn("home_city_slot_index", published.metadata)

    def test_bank_action_stays_below_the_safe_tap_band(self) -> None:
        """Both Bank views measure the body under the HUD-safe band.

        The fixed node's projected action point lands below the conservative
        tap band (max ratio 0.58) on both views, so this package supplies
        perception/discovery evidence only; Bank still refuses open before
        input and no tap is authorized by these frames.
        """

        bank = _catalog_target(HomeCityObjectId.BANK)
        safe_max_y = int(HOME_CITY_HUD_SAFE_MAX_Y_RATIO * 1600)
        for name in (
            "home_city_bank_sys1_0022_20260929.png",
            "home_city_bank_sys1_0092_20260929.png",
        ):
            with self.subTest(fixture=name):
                proof, frame = self._proof_and_frame(name)
                match = self.localizer.match_target(frame, bank, proof=proof)
                self.assertIsNotNone(match)
                self.assertGreater(match.action_point[1], safe_max_y)

    def test_bank_erased_or_occluded_body_never_publishes(self) -> None:
        bank = _catalog_target(HomeCityObjectId.BANK)
        image = _fixture("home_city_bank_sys1_0022_20260929.png")
        proof = self.localizer.localize(image.copy())
        self.assertTrue(proof.localized)
        matches = self.localizer.match_target_candidates(
            self.localizer.prepare_frame(image), bank, proof=proof
        )
        self.assertEqual(1, len(matches))
        body = matches[0].bounds
        image.paste((0, 0, 0, 255), (body.x, body.y, body.x + body.width, body.y + body.height))
        self.assertEqual(
            (),
            self.localizer.match_target_candidates(
                self.localizer.prepare_frame(image), bank, proof=proof
            ),
        )

    def test_bank_never_publishes_on_unrelated_views(self) -> None:
        bank = _catalog_target(HomeCityObjectId.BANK)
        for name in (
            "home_city_blacksmith_slot12_f1_20260922.png",
            "home_city_blacksmith_slot12_f2_20260922.png",
            "home_city_baseline_f0_20260922.png",
            "home_city_pan2_f5_20260922.png",
            "home_city_wall_slot2_f6_20260922.png",
            "home_city_goddess_slot15_0066_20260923.png",
            "home_city_warehouse_slot3_0047_20260929.png",
            "home_city_warehouse_slot3_0084_20260929.png",
        ):
            with self.subTest(fixture=name):
                proof, frame = self._proof_and_frame(name)
                self.assertEqual(
                    (),
                    self.localizer.match_target_candidates(frame, bank, proof=proof),
                )

    def test_contradictory_camera_proofs_reject_both_new_bodies(self) -> None:
        """Wrong translations/zooms move predictions away from the bodies."""

        warehouse = _catalog_target(HomeCityObjectId.WAREHOUSE)
        bank = _catalog_target(HomeCityObjectId.BANK)
        image = _fixture("home_city_warehouse_slot3_0047_20260929.png")
        frame = self.localizer.prepare_frame(image)
        for proof in (
            _localized_proof((-1250, 139)),
            _localized_proof((-777, 55)),  # real translation, wrong 1.0 zoom
            _localized_proof((-200, 55), zoom=0.7387),
        ):
            self.assertEqual(
                (),
                self.localizer.match_target_candidates(frame, warehouse, proof=proof),
            )
        bank_image = _fixture("home_city_bank_sys1_0022_20260929.png")
        bank_frame = self.localizer.prepare_frame(bank_image)
        for proof in (
            _localized_proof((-532, 222)),
            _localized_proof((200, -1000), zoom=0.75),
            _localized_proof((-24, 45)),  # real translation, wrong 1.0 zoom
        ):
            self.assertEqual(
                (),
                self.localizer.match_target_candidates(
                    bank_frame, bank, proof=proof
                ),
            )

    def test_unlocalized_proofs_publish_neither_new_target(self) -> None:
        for status in (
            HomeCityCameraStatus.INSUFFICIENT,
            HomeCityCameraStatus.AMBIGUOUS,
            HomeCityCameraStatus.UNSUPPORTED,
        ):
            with self.subTest(status=status):
                proof = HomeCityCameraProof(status=status, reason="synthetic")
                frame = self.localizer.prepare_frame(
                    _fixture("home_city_bank_sys1_0022_20260929.png")
                )
                for target in (
                    _catalog_target(HomeCityObjectId.WAREHOUSE),
                    _catalog_target(HomeCityObjectId.BANK),
                ):
                    self.assertEqual(
                        (),
                        self.localizer.match_target_candidates(
                            frame, target, proof=proof
                        ),
                    )

    def test_smaller_resolution_frame_scales_action_geometry(self) -> None:
        """A 450x800 capture normalizes to reference space; measured geometry maps back."""

        half = _fixture("home_city_blacksmith_slot12_f2_20260922.png").resize((450, 800))
        proof = self.localizer.localize(half.copy())
        self.assertTrue(proof.localized)
        frame = self.localizer.prepare_frame(half)
        matches = self.localizer.match_target_candidates(frame, self.blacksmith, proof=proof)
        self.assertEqual(1, len(matches))
        self.assertEqual(HomeCitySlotSelector(12), matches[0].home_city_slot)
        self.assertLessEqual(abs(matches[0].action_point[0] - 356), 1)
        self.assertLessEqual(abs(matches[0].action_point[1] - 415), 1)


class SyntheticCandidatePlacementTests(unittest.TestCase):
    """Deterministic synthetic placements prove multi-slot and ambiguity rules."""

    def setUp(self) -> None:
        self.blacksmith = _catalog_target(HomeCityObjectId.BLACKSMITH)

    def _localizer(self, hits: dict[tuple[int, int], TemplateMatch]) -> HomeCityCameraLocalizer:
        return HomeCityCameraLocalizer(matcher=_RegionScriptedMatcher(hits))

    def test_distinct_bodies_at_two_eligible_slots_stay_separate(self) -> None:
        """Synthetic: two projection-agreed bodies publish as two slot observations."""

        # img_translation (-400,-900): slot 11 predicts (522,819), slot 12
        # (240,945); slot 13's prediction is partially clipped and skipped.
        proof = _localized_proof((-932, -678))
        hits = {
            (582, 884): TemplateMatch(bounds=Bounds(522, 819, 120, 130), confidence=0.95),
            (300, 1010): TemplateMatch(bounds=Bounds(240, 945, 120, 130), confidence=0.94),
        }
        frame = HomeCityCameraLocalizer(matcher=_RegionScriptedMatcher({})).prepare_frame(
            Image.new("RGB", (900, 1600))
        )
        matches = self._localizer(hits).match_target_candidates(frame, self.blacksmith, proof=proof)
        by_slot = {match.home_city_slot.slot_index: match for match in matches}
        self.assertEqual({11, 12}, set(by_slot))
        self.assertEqual(Bounds(522, 819, 120, 130), by_slot[11].bounds)
        self.assertEqual(Bounds(240, 945, 120, 130), by_slot[12].bounds)
        self.assertEqual((592, 899), by_slot[11].action_point)
        self.assertTrue(by_slot[12].action_bounds.contains_point(by_slot[12].action_point))

    def test_overlapping_claims_reject_every_ambiguous_slot(self) -> None:
        """Synthetic: hits claiming the same body for two slots publish neither."""

        near_twins = {
            11: _synthetic_slot(11, (1228, 1736)),
            12: _synthetic_slot(12, (1224, 1732)),
        }
        proof = _localized_proof((-932, -678))
        # img_translation (-400,-900): the twin pivots predict overlapping
        # bodies at (244,949) and (240,945); the scripted hit satisfies both
        # projections yet describes one physical body, so every claim drops.
        hits = {
            (304, 1014): TemplateMatch(bounds=Bounds(241, 946, 120, 130), confidence=0.95),
            (300, 1010): TemplateMatch(bounds=Bounds(241, 946, 120, 130), confidence=0.95),
        }
        frame = HomeCityCameraLocalizer(matcher=_RegionScriptedMatcher({})).prepare_frame(
            Image.new("RGB", (900, 1600))
        )
        with mock.patch.object(
            HomeCityCameraTarget, "_eligible_slots", lambda self: near_twins
        ):
            matches = self._localizer(hits).match_target_candidates(
                frame, self.blacksmith, proof=proof
            )
        self.assertEqual((), matches)

    def test_partially_clipped_candidate_is_skipped(self) -> None:
        """Synthetic: a candidate whose predicted body leaves the frame is not searched."""

        # img_translation (0,-300): slot 12 predicts (640,1545) so the body
        # would extend past the viewport bottom; every eligible candidate is
        # clipped or offscreen and nothing may publish.
        proof = _localized_proof((-532, -78))
        hits = {
            (700, 1610): TemplateMatch(bounds=Bounds(640, 1545, 120, 130), confidence=0.95),
        }
        frame = HomeCityCameraLocalizer(matcher=_RegionScriptedMatcher({})).prepare_frame(
            Image.new("RGB", (900, 1600))
        )
        self.assertEqual(
            (), self._localizer(hits).match_target_candidates(frame, self.blacksmith, proof=proof)
        )


class MergeCameraTargetObjectsTests(unittest.TestCase):
    """Identity is semantic id plus slot; OCR facts merge only unambiguously."""

    def test_two_same_type_bodies_keep_distinct_slots(self) -> None:
        body11 = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(522, 819, 120, 130), slot=11)
        body12 = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(240, 945, 120, 130), slot=12)
        merged = merge_camera_target_objects((), (body11, body12))
        self.assertEqual({11, 12}, {o.home_city_slot.slot_index for o in merged})
        self.assertEqual(2, len(merged))

    def test_unambiguous_label_merges_name_level_and_slot(self) -> None:
        body = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(642, 749, 120, 130), slot=12)
        label = _ocr_object(HomeCityObjectId.BLACKSMITH, Bounds(640, 700, 90, 24), name="Blacksmith", level=5)
        merged = merge_camera_target_objects((label,), (body,))
        self.assertEqual(1, len(merged))
        item = merged[0]
        self.assertEqual(body.bounds, item.bounds)
        self.assertEqual(body.action_point, item.action_point)
        self.assertEqual(HomeCitySlotSelector(12), item.home_city_slot)
        self.assertEqual("Blacksmith", item.name_text)
        self.assertEqual(5, item.level)
        self.assertIn("home_city_label", item.metadata)

    def test_one_label_never_fans_out_to_two_bodies(self) -> None:
        body11 = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(522, 819, 120, 130), slot=11)
        body12 = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(240, 945, 120, 130), slot=12)
        label = _ocr_object(HomeCityObjectId.BLACKSMITH, Bounds(600, 700, 90, 24), name="Blacksmith")
        merged = merge_camera_target_objects((label,), (body11, body12))
        self.assertEqual(2, len(merged))
        bodies = [o for o in merged if o.source_kind is SpatialObjectSourceKind.TEMPLATE]
        self.assertEqual({11, 12}, {o.home_city_slot.slot_index for o in bodies})
        self.assertTrue(all(o.name_text == "camera-name" for o in bodies))
        self.assertTrue(all(o.level is None for o in bodies))
        labels = [o for o in merged if o.source_kind is SpatialObjectSourceKind.OCR]
        self.assertEqual(0, len(labels))

    def test_label_with_explicit_slot_merges_only_that_body(self) -> None:
        body11 = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(522, 819, 120, 130), slot=11)
        body12 = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(240, 945, 120, 130), slot=12)
        label = _ocr_object(
            HomeCityObjectId.BLACKSMITH, Bounds(240, 900, 90, 24), slot=12, name="Blacksmith", level=9
        )
        merged = merge_camera_target_objects((label,), (body11, body12))
        self.assertEqual(2, len(merged))
        merged12 = next(o for o in merged if o.home_city_slot.slot_index == 12)
        self.assertEqual("Blacksmith", merged12.name_text)
        self.assertEqual(9, merged12.level)
        self.assertEqual(body12.bounds, merged12.bounds)
        merged11 = next(o for o in merged if o.home_city_slot.slot_index == 11)
        self.assertEqual("camera-name", merged11.name_text)
        self.assertIsNone(merged11.level)

    def test_ambiguous_labels_neither_duplicate_nor_enrich_the_body(self) -> None:
        body = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(642, 749, 120, 130), slot=12)
        first = _ocr_object(HomeCityObjectId.BLACKSMITH, Bounds(640, 700, 90, 24), name="Blacksmith", level=5)
        second = _ocr_object(HomeCityObjectId.BLACKSMITH, Bounds(641, 701, 90, 24), name="Blacksmith", level=6)
        for labels in ((first, second), (second, first)):
            with self.subTest(levels=[label.level for label in labels]):
                self.assertEqual((body,), merge_camera_target_objects(labels, (body,)))

    def test_incompatible_slot_label_does_not_create_an_unmeasured_instance(self) -> None:
        body = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(642, 749, 120, 130), slot=12)
        label = _ocr_object(HomeCityObjectId.BLACKSMITH, Bounds(640, 700, 90, 24), slot=11)
        self.assertEqual((body,), merge_camera_target_objects((label,), (body,)))

    def test_fixed_targets_merge_without_slots_unchanged(self) -> None:
        body = _camera_object(HomeCityObjectId.CAMPAIGN, Bounds(380, 367, 150, 70), slot=None)
        label = _ocr_object(HomeCityObjectId.CAMPAIGN, Bounds(390, 340, 90, 24), name="Campaign")
        merged = merge_camera_target_objects((label,), (body,))
        self.assertEqual(1, len(merged))
        self.assertEqual("Campaign", merged[0].name_text)
        self.assertIsNone(merged[0].home_city_slot)

    def test_unmatched_and_unkeyed_objects_are_preserved(self) -> None:
        body = _camera_object(HomeCityObjectId.BLACKSMITH, Bounds(642, 749, 120, 130), slot=12)
        unkeyed = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(1, 1, 10, 10),
            relationship=SpatialObjectRelationship.SELF,
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={},
        )
        other_ocr = _ocr_object(HomeCityObjectId.WAREHOUSE, Bounds(5, 5, 10, 10), name="Warehouse")
        merged = merge_camera_target_objects((other_ocr,), (body, unkeyed))
        self.assertEqual(3, len(merged))
        self.assertIn(unkeyed, merged)
        self.assertIn(other_ocr, merged)

    def test_empty_camera_objects_returns_input(self) -> None:
        label = _ocr_object(HomeCityObjectId.BLACKSMITH, Bounds(640, 700, 90, 24))
        self.assertEqual((label,), merge_camera_target_objects((label,), ()))


class FixtureIntegrityTests(unittest.TestCase):
    """Authored fixtures preserve source RGBA, size, and pixels outside the mask."""

    def test_manifest_entries_match_authored_files(self) -> None:
        samples = {sample["image"]: sample for sample in MANIFEST["samples"]}
        self.assertEqual(
            {
                "home_city_blacksmith_slot12_f1_20260922.png",
                "home_city_blacksmith_slot12_f2_20260922.png",
                "home_city_baseline_f0_20260922.png",
                "home_city_pan2_f5_20260922.png",
                "home_city_wall_slot2_f6_20260922.png",
                "home_city_goddess_slot15_0066_20260923.png",
                "home_city_warehouse_slot3_0047_20260929.png",
                "home_city_warehouse_slot3_0084_20260929.png",
                "home_city_bank_sys1_0022_20260929.png",
                "home_city_bank_sys1_0092_20260929.png",
            },
            set(samples),
        )
        for name, sample in samples.items():
            with self.subTest(image=name):
                self.assertEqual([900, 1600], sample["size"])
                self.assertEqual("RGBA", sample["mode"])
                self.assertEqual([1390, 1484], sample["masked_rows"])
                path = FIXTURES / name
                raw = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(sample["raw_sha256"], raw)
                with Image.open(path) as image:
                    self.assertEqual("RGBA", image.mode)
                    self.assertEqual((900, 1600), image.size)
                    decoded = hashlib.sha256(
                        image.width.to_bytes(8, "big")
                        + image.height.to_bytes(8, "big")
                        + image.convert("RGB").tobytes()
                    ).hexdigest()
                    self.assertEqual(sample["sha256"], decoded)
                    self.assertEqual(64, len(sample["source_sha256"]))
                    self.assertTrue(sample["source_artifact"])
                    self.assertTrue(sample["annotation"])

    def test_pixels_outside_the_declared_mask_match_authored_digests(self) -> None:
        for sample in MANIFEST["samples"]:
            with self.subTest(image=sample["image"]):
                top, bottom = sample["masked_rows"]
                with Image.open(FIXTURES / sample["image"]) as image:
                    array = np.array(image)
                outside = np.concatenate([array[:top], array[bottom + 1 :]], axis=0)
                digest = hashlib.sha256(outside.tobytes()).hexdigest()
                self.assertEqual(sample["outside_mask_sha256"], digest)
                # Declared rows are the authored black mask; RGBA is preserved.
                self.assertTrue(np.all(array[top : bottom + 1] == np.array([0, 0, 0, 255])))


if __name__ == "__main__":
    unittest.main()
