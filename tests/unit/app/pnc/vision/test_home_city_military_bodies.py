"""Tests for the V44-4 military building-body camera targets.

Four fixed single-type military slots -- Infantry Barracks 5, Cavalry
Barracks 6, Ranged Barracks 7, Siege Factory 8 -- carry body crops authored
from the 2026-09-29 f1171ffa attempt1 baseline frame 0022 and corroborated
on the independent 0092 survey view plus the zoom-1.0 f0 baseline from the
separate 2026-09-22 session.  Hall of War (slot 14) has no qualified
native body evidence and publishes no target.  Distinct military bodies
must never cross-match, and occluded or erased bodies stay honest
no-matches.  Native fixtures stay RGBA 900x1600; measured frame literals
record the reviewed analytic predictions pending serialized validation.
"""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import SpatialObjectSourceKind
from pnc_automation.app.pnc.vision.home_city_camera import (
    HomeCityCameraLocalizer,
    HomeCityCameraTarget,
    load_home_city_camera_catalog,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
)

from tests.support.paths import TEST_DATA_ROOT


FIXTURES = TEST_DATA_ROOT / "home_city_slot_bodies"
BASELINE_0022 = "home_city_bank_sys1_0022_20260929.png"
SURVEY_0092 = "home_city_bank_sys1_0092_20260929.png"
BASELINE_F0 = "home_city_baseline_f0_20260922.png"

MILITARY_OBJECT_IDS = (
    HomeCityObjectId.INFANTRY_BARRACKS,
    HomeCityObjectId.CAVALRY_BARRACKS,
    HomeCityObjectId.RANGED_BARRACKS,
    HomeCityObjectId.SIEGE_FACTORY,
)


def _fixture(name: str) -> Image.Image:
    """Load a native fixture at its authored RGBA mode for camera matching."""

    path = FIXTURES / name
    with Image.open(path) as source:
        assert source.mode == "RGBA" and source.size == (900, 1600)
        return source.copy()


def _catalog_target(object_id: HomeCityObjectId) -> HomeCityCameraTarget:
    catalog = load_home_city_camera_catalog()
    return next(target for target in catalog.targets if target.object_id == object_id)


class NativeMilitaryBodyMatchTests(unittest.TestCase):
    """Real native frames publish slot-tagged military bodies through the catalog."""

    def setUp(self) -> None:
        self.matcher = OpenCvTemplateMatcher()
        self.localizer = HomeCityCameraLocalizer(matcher=self.matcher)
        self.catalog = load_home_city_camera_catalog()

    def _proof_and_frame(self, name: str):
        image = _fixture(name)
        proof = self.localizer.localize(image.copy())
        self.assertTrue(proof.localized, f"{name} must localize on reviewed evidence")
        return proof, self.localizer.prepare_frame(image), image

    def test_baseline_0022_publishes_all_four_bodies(self) -> None:
        """Template-source frame: camera (-24,45), zoom 0.75, chat band masked."""
        proof, frame, _ = self._proof_and_frame(BASELINE_0022)
        self.assertEqual((-24, 45), proof.translation)
        self.assertAlmostEqual(0.75, proof.zoom, delta=0.01)
        for object_id, slot, bounds, action_point in (
            (HomeCityObjectId.INFANTRY_BARRACKS, 5, Bounds(415, 625, 83, 78), (450, 666)),
            (HomeCityObjectId.CAVALRY_BARRACKS, 6, Bounds(252, 690, 100, 42), (308, 722)),
            (HomeCityObjectId.RANGED_BARRACKS, 7, Bounds(390, 800, 120, 34), (445, 818)),
            (HomeCityObjectId.SIEGE_FACTORY, 8, Bounds(212, 806, 72, 84), (245, 855)),
        ):
            with self.subTest(object_id=object_id):
                target = _catalog_target(object_id)
                matches = self.localizer.match_target_candidates(frame, target, proof=proof)
                self.assertEqual(1, len(matches))
                match = matches[0]
                self.assertEqual(HomeCitySlotSelector(slot), match.home_city_slot)
                self.assertEqual(bounds, match.bounds)
                self.assertGreaterEqual(match.score, 0.9)
                self.assertLessEqual(match.projection_error, 12)
                self.assertEqual(action_point, match.action_point)
                self.assertTrue(match.bounds.contains_bounds(match.action_bounds))
                self.assertTrue(match.action_bounds.contains_point(match.action_point))
                self.assertEqual(match, self.localizer.match_target(frame, target, proof=proof))

    def test_baseline_0022_publishes_typed_military_objects(self) -> None:
        """The publisher carries typed slot identity and camera provenance."""
        proof, frame, _ = self._proof_and_frame(BASELINE_0022)
        objects = self.localizer.matched_target_objects(frame, proof=proof)
        for object_id, slot in (
            (HomeCityObjectId.INFANTRY_BARRACKS, 5),
            (HomeCityObjectId.CAVALRY_BARRACKS, 6),
            (HomeCityObjectId.RANGED_BARRACKS, 7),
            (HomeCityObjectId.SIEGE_FACTORY, 8),
        ):
            with self.subTest(object_id=object_id):
                object_ = next(
                    item
                    for item in objects
                    if home_city_object_id_from_metadata(item.metadata) is object_id
                )
                self.assertEqual(HomeCitySlotSelector(slot), object_.home_city_slot)
                self.assertEqual(slot, object_.metadata["home_city_slot_index"])
                self.assertEqual(SpatialObjectSourceKind.TEMPLATE, object_.source_kind)
                self.assertEqual("camera_template", object_.metadata["detection_source"])
                self.assertTrue(object_.bounds.contains_bounds(object_.action_bounds))
                self.assertTrue(object_.action_bounds.contains_point(object_.action_point))

    def test_survey_0092_independently_publishes_all_four(self) -> None:
        """Independent same-session holdout: camera (-152,-21), zoom 0.75.

        The siege action point lands at x<140, inside the declared left-HUD
        exclusion band of this view; that is a view-specific limitation, not
        evidence the authored target is invalid.
        """
        proof, frame, _ = self._proof_and_frame(SURVEY_0092)
        self.assertEqual((-152, -21), proof.translation)
        self.assertAlmostEqual(0.75, proof.zoom, delta=0.01)
        for object_id, slot, bounds, action_point in (
            (HomeCityObjectId.INFANTRY_BARRACKS, 5, Bounds(287, 559, 83, 78), (322, 600)),
            (HomeCityObjectId.CAVALRY_BARRACKS, 6, Bounds(124, 624, 100, 42), (180, 656)),
            (HomeCityObjectId.RANGED_BARRACKS, 7, Bounds(262, 734, 120, 34), (317, 752)),
            (HomeCityObjectId.SIEGE_FACTORY, 8, Bounds(84, 740, 72, 84), (117, 789)),
        ):
            with self.subTest(object_id=object_id):
                target = _catalog_target(object_id)
                matches = self.localizer.match_target_candidates(frame, target, proof=proof)
                self.assertEqual(1, len(matches))
                match = matches[0]
                self.assertEqual(HomeCitySlotSelector(slot), match.home_city_slot)
                self.assertEqual(bounds, match.bounds)
                self.assertGreaterEqual(match.score, 0.9)
                self.assertLessEqual(match.projection_error, 12)
                self.assertEqual(action_point, match.action_point)
                self.assertTrue(match.bounds.contains_bounds(match.action_bounds))

    def test_f0_baseline_publishes_infantry_at_native_zoom_one(self) -> None:
        """Second independent infantry holdout: 2026-09-22 session, zoom 1.0."""
        proof, frame, _ = self._proof_and_frame(BASELINE_F0)
        self.assertEqual((-532, 222), proof.translation)
        self.assertAlmostEqual(1.0, proof.zoom, delta=0.01)
        target = _catalog_target(HomeCityObjectId.INFANTRY_BARRACKS)
        matches = self.localizer.match_target_candidates(frame, target, proof=proof)
        self.assertEqual(1, len(matches))
        match = matches[0]
        self.assertEqual(HomeCitySlotSelector(5), match.home_city_slot)
        self.assertEqual(Bounds(53, 995, 111, 104), match.bounds)
        self.assertEqual((100, 1049), match.action_point)
        self.assertGreaterEqual(match.score, 0.9)
        self.assertLessEqual(match.projection_error, 12)

    def test_f0_baseline_never_publishes_occluded_or_offscreen_bodies(self) -> None:
        """Cavalry/siege predictions leave the f0 viewport; ranged is banner-occluded."""
        proof, frame, _ = self._proof_and_frame(BASELINE_F0)
        for object_id in (
            HomeCityObjectId.CAVALRY_BARRACKS,
            HomeCityObjectId.RANGED_BARRACKS,
            HomeCityObjectId.SIEGE_FACTORY,
        ):
            with self.subTest(object_id=object_id):
                target = _catalog_target(object_id)
                self.assertEqual(
                    (),
                    self.localizer.match_target_candidates(frame, target, proof=proof),
                )

    def test_sibling_military_templates_never_cross_match(self) -> None:
        """Each military template searched at a sibling body stays below .90."""
        _, frame, _ = self._proof_and_frame(BASELINE_0022)
        sibling_regions = {
            HomeCityObjectId.INFANTRY_BARRACKS: Bounds(375, 585, 163, 158),
            HomeCityObjectId.CAVALRY_BARRACKS: Bounds(212, 650, 180, 122),
            HomeCityObjectId.RANGED_BARRACKS: Bounds(350, 760, 200, 114),
            HomeCityObjectId.SIEGE_FACTORY: Bounds(172, 766, 152, 164),
        }
        for object_id in MILITARY_OBJECT_IDS:
            target = _catalog_target(object_id)
            for sibling_id, padded in sibling_regions.items():
                if sibling_id is object_id:
                    continue
                with self.subTest(template=object_id, searched=sibling_id):
                    self.assertIsNone(
                        self.matcher.find_best_match(
                            frame,
                            self.catalog.template_path(target.file_name),
                            threshold=target.min_score,
                            search_region=padded,
                            template_scale=0.75,
                        )
                    )

    def test_erased_military_body_never_publishes(self) -> None:
        """A blacked-out body region cannot produce a body match."""
        proof, frame, image = self._proof_and_frame(BASELINE_0022)
        for object_id, bounds in (
            (HomeCityObjectId.INFANTRY_BARRACKS, Bounds(415, 625, 83, 78)),
            (HomeCityObjectId.CAVALRY_BARRACKS, Bounds(252, 690, 100, 42)),
            (HomeCityObjectId.RANGED_BARRACKS, Bounds(390, 800, 120, 34)),
            (HomeCityObjectId.SIEGE_FACTORY, Bounds(212, 806, 72, 84)),
        ):
            with self.subTest(object_id=object_id):
                erased = image.copy()
                erased.paste(
                    (0, 0, 0, 255),
                    (bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height),
                )
                target = _catalog_target(object_id)
                self.assertEqual(
                    (),
                    self.localizer.match_target_candidates(
                        self.localizer.prepare_frame(erased), target, proof=proof
                    ),
                )

    def test_hall_of_war_publishes_no_camera_target(self) -> None:
        """Slot 14 has no qualified native body evidence in this package."""
        catalog = load_home_city_camera_catalog()
        self.assertIsNone(catalog.target_for(HomeCityObjectId.HALL_OF_WAR))


if __name__ == "__main__":
    unittest.main()
