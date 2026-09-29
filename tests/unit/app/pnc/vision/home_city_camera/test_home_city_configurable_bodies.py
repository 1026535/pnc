"""Configurable-slot body data; native appearance checks run when CPU is released."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraProof, HomeCityCameraStatus
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector, home_city_slots_for_object
from pnc_automation.app.pnc.vision.home_city_camera import (
    HomeCityCameraLocalizer,
    load_home_city_camera_catalog,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.support.paths import TEST_DATA_ROOT


_FIXTURES = TEST_DATA_ROOT / "home_city_slot_bodies"
_SOURCE = "home_city_pan2_f5_20260922.png"
_HOLDOUT = "home_city_wall_slot2_f6_20260922.png"


class ConfigurableBodyDataTests(unittest.TestCase):
    """Light checks do not invoke a matcher or infer current occupancy."""

    def test_reference_slot_geometry_requires_selected_slot(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.ALLIANCE_HALL)
        self.assertIsNotNone(target)
        self.assertEqual(HomeCitySlotSelector(13), target.reference_slot)
        self.assertEqual((1804, 1454), target.atlas_action_point(home_city_slot=HomeCitySlotSelector(13)))
        slots = {slot.slot_index: slot for slot in home_city_slots_for_object(HomeCityObjectId.ALLIANCE_HALL)}
        self.assertEqual({11, 12, 13}, set(slots))
        for index in (11, 12):
            pivot = slots[index].atlas_coordinate
            reference = slots[13].atlas_coordinate
            self.assertEqual(
                (1804 + pivot.x - reference.x, 1454 + pivot.y - reference.y),
                target.atlas_action_point(home_city_slot=HomeCitySlotSelector(index)),
            )
        with self.assertRaisesRegex(SelectorResolutionError, "explicit selected slot"):
            target.atlas_action_point()
        self.assertTrue(next(item for item in catalog.landmarks if item.id == "alliance_hall_structure").movable)
        self.assertIsNone(catalog.target_for(HomeCityObjectId.MARKET))

    def test_template_preserves_native_body_pixels_and_action_geometry(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.ALLIANCE_HALL)
        with Image.open(_FIXTURES / _SOURCE) as source, Image.open(catalog.template_path(target.file_name)) as body:
            self.assertEqual((900, 1600), source.size)
            self.assertEqual("RGBA", source.mode)
            self.assertEqual(source.mode, body.mode)
            self.assertEqual((162, 180), body.size)
            self.assertEqual(source.crop((106, 610, 268, 790)).tobytes(), body.tobytes())
        self.assertTrue(target.reference_bounds.contains_bounds(target.reference_action_bounds))
        self.assertTrue(target.reference_action_bounds.contains_point(target.reference_action_point))


class ConfigurableNativeBodyTests(unittest.TestCase):
    """Saved native source/holdout tests; no live permutation proof is implied."""

    def test_alliance_hall_body_matches_slot13_on_source_and_separate_capture(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.ALLIANCE_HALL)
        localizer = HomeCityCameraLocalizer(catalog=catalog, matcher=OpenCvTemplateMatcher())
        # Fixed-landmark pose recorded in the native fixture manifest. This
        # controlled proof tests body matching, not independent localization.
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="saved_fixture_manifest_pose",
            translation=(-1632, -718), zoom=1.0, frame_size=(900, 1600),
        )
        for name in (_SOURCE, _HOLDOUT):
            with self.subTest(fixture=name), Image.open(_FIXTURES / name) as source:
                matches = localizer.match_target_candidates(source.copy(), target, proof=proof)
                self.assertEqual(1, len(matches))
                self.assertEqual(HomeCitySlotSelector(13), matches[0].home_city_slot)
                self.assertLessEqual(abs(matches[0].action_point[0] - 172), 2)
                self.assertLessEqual(abs(matches[0].action_point[1] - 736), 2)

    def test_erased_native_body_does_not_publish_projected_slot_identity(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.ALLIANCE_HALL)
        localizer = HomeCityCameraLocalizer(catalog=catalog, matcher=OpenCvTemplateMatcher())
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="saved_fixture_manifest_pose_with_synthetic_erasure",
            translation=(-1632, -718), zoom=1.0, frame_size=(900, 1600),
        )
        with Image.open(_FIXTURES / _SOURCE) as source:
            erased = source.copy()
        erased.paste((0, 0, 0, 255), (94, 598, 280, 802))
        self.assertEqual((), localizer.match_target_candidates(erased, target, proof=proof))
