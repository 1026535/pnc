"""Market body evidence uses the shared configurable-slot matcher."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.domain.home_city_slots import (
    HomeCitySlotSelector,
    home_city_slots_for_object,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.home_city_camera import (
    HomeCityCameraLocalizer,
    load_home_city_camera_catalog,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.navigation.core_frames import observation


_FIXTURES = TEST_DATA_ROOT / "home_city_camera"
_SOURCE = "home_city_wall_corridor_regression_20260923.png"
_SOURCE_BODY = (130, 875, 285, 985)
_SOURCE_POINT = (213, 949)
_HOLDOUT = TEST_DATA_ROOT / "home_city_slot_bodies" / "home_city_warehouse_slot3_0084_20260929.png"


def _source_proof() -> HomeCityCameraProof:
    """Reuse the independently localized source pose from the fixture manifest."""
    return HomeCityCameraProof(
        status=HomeCityCameraStatus.LOCALIZED,
        reason="market_source_manifest_pose",
        translation=(-1298, -645),
        zoom=1.0,
        frame_size=(900, 1600),
    )


class MarketBodyDataTests(unittest.TestCase):
    """Geometry and scope checks do not execute native matching."""

    def test_template_preserves_native_body_pixels_and_clear_action_region(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.MARKET)
        self.assertIsNotNone(target)
        with (
            Image.open(_FIXTURES / _SOURCE) as source,
            Image.open(catalog.template_path(target.file_name)) as body,
        ):
            self.assertEqual((900, 1600), source.size)
            self.assertEqual("RGBA", source.mode)
            self.assertEqual(source.mode, body.mode)
            self.assertEqual((155, 110), body.size)
            self.assertEqual(source.crop(_SOURCE_BODY).tobytes(), body.tobytes())
        self.assertTrue(target.reference_bounds.contains_bounds(target.reference_action_bounds))
        self.assertTrue(target.reference_action_bounds.contains_point(target.reference_action_point))
        self.assertNotIn(target.landmark_id, {item.id for item in catalog.landmarks})

    def test_reference_placement_does_not_fix_the_current_occupant(self) -> None:
        target = load_home_city_camera_catalog().target_for(HomeCityObjectId.MARKET)
        self.assertEqual(HomeCitySlotSelector(11), target.reference_slot)
        slots = {slot.slot_index: slot for slot in home_city_slots_for_object(HomeCityObjectId.MARKET)}
        self.assertEqual({11, 12, 13}, set(slots))
        reference = slots[11].atlas_coordinate
        for index, slot in slots.items():
            with self.subTest(slot=index):
                self.assertEqual(
                    (1511 + slot.atlas_coordinate.x - reference.x,
                     1594 + slot.atlas_coordinate.y - reference.y),
                    target.atlas_action_point(home_city_slot=HomeCitySlotSelector(index)),
                )
        with self.assertRaisesRegex(SelectorResolutionError, "explicit selected slot"):
            target.atlas_action_point()
        with self.assertRaisesRegex(SelectorResolutionError, "cannot host"):
            target.atlas_action_point(home_city_slot=HomeCitySlotSelector(9))

    def test_reviewed_market_entry_requires_a_fresh_home_surface(self) -> None:
        for method in ("open_building", "open_visible_building"):
            with self.subTest(method=method):
                actuator = Mock()
                capture = Mock(return_value=observation(ScreenType.UNKNOWN))
                core = NavigationCore(actuator, capture, reviewed_navigation_edges())
                with self.assertRaisesRegex(RuntimeError, "unblocked city surface"):
                    getattr(core, method)(
                        HomeCityObjectId.MARKET,
                        observe_content=capture,
                        home_city_slot=HomeCitySlotSelector(11),
                    )
                capture.assert_called_once()
                actuator.execute_action.assert_not_called()


class MarketBodyMatchTests(unittest.TestCase):
    """Native matching is serialized with the coordinator's vision checks."""

    def test_source_body_matches_market_at_slot11(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.MARKET)
        localizer = HomeCityCameraLocalizer(catalog=catalog, matcher=OpenCvTemplateMatcher())
        with Image.open(_FIXTURES / _SOURCE) as source:
            matches = localizer.match_target_candidates(source.copy(), target, proof=_source_proof())
        self.assertEqual(1, len(matches))
        self.assertEqual(HomeCitySlotSelector(11), matches[0].home_city_slot)
        for observed, expected in zip(matches[0].action_point, _SOURCE_POINT):
            self.assertLessEqual(abs(observed - expected), 2)

    def test_missing_body_cannot_be_inferred_from_slot_geometry(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.MARKET)
        localizer = HomeCityCameraLocalizer(catalog=catalog, matcher=OpenCvTemplateMatcher())
        with Image.open(_FIXTURES / _SOURCE) as source:
            erased = source.copy()
        erased.paste((0, 0, 0, 255), (118, 863, 297, 997))
        self.assertEqual((), localizer.match_target_candidates(erased, target, proof=_source_proof()))

    def test_market_matches_separate_native_session_and_pose(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.MARKET)
        localizer = HomeCityCameraLocalizer(catalog=catalog, matcher=OpenCvTemplateMatcher())
        # The Warehouse fixture contains a labeled Market in slot 11. Its
        # independently recorded fixed-landmark pose differs from the source.
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="separate_session_fixture_manifest_pose",
            translation=(-389, -427),
            zoom=0.75,
            frame_size=(900, 1600),
        )
        with Image.open(_HOLDOUT) as source:
            self.assertEqual((900, 1600), source.size)
            self.assertEqual("RGBA", source.mode)
            matches = localizer.match_target_candidates(source.copy(), target, proof=proof)
        self.assertEqual(1, len(matches))
        self.assertEqual(HomeCitySlotSelector(11), matches[0].home_city_slot)
        # Native match: score .9704, projection error 6.40px. Use the measured
        # body location, not the camera-only prediction (744, 769).
        for observed, expected in zip(matches[0].action_point, (740, 764)):
            self.assertLessEqual(abs(observed - expected), 2)

    def test_empty_slot_between_blacksmith_and_hall_is_not_market(self) -> None:
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.MARKET)
        localizer = HomeCityCameraLocalizer(catalog=catalog, matcher=OpenCvTemplateMatcher())
        # A real older layout has an empty slot 11, Blacksmith at 12 and Hall
        # at 13. Eligibility and a projected position cannot establish Market.
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="saved_empty_slot_fixture_pose",
            translation=(-1000, -710),
            zoom=1.0,
            frame_size=(540, 960),
        )
        with Image.open(_FIXTURES / "home_city_pan_07.png") as source:
            self.assertEqual((), localizer.match_target_candidates(source.copy(), target, proof=proof))
