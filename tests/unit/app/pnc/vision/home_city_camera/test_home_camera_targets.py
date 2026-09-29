"""Home camera targets tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.vision.home_city_camera.catalog import (
    load_home_city_camera_catalog,
)

from tests.support.pnc.home_city_camera.fixtures import (
    _CAMERA_FIXTURES,
    _SCREEN_RECOGNITION,
    _fixture,
    _localizer,
)


class HomeCityCameraTargetTests(unittest.TestCase):
    """Body targets only publish when they agree with the localized projection."""

    def test_castle_body_matches_native_source_and_distinct_holdout(self) -> None:
        """Reuses measured poses; localization has its own native-view tests."""

        localizer = _localizer()
        target = load_home_city_camera_catalog().target_for(HomeCityObjectId.CASTLE)
        for name, translation in (
            ("home_city_castle_default_20260921.png", (-532, 222)),
            ("home_city_castle_holdout_20260921.png", (-545, 149)),
        ):
            with self.subTest(fixture=name):
                image = _fixture(_CAMERA_FIXTURES / name)
                frame = localizer.prepare_frame(image)
                proof = HomeCityCameraProof(
                    status=HomeCityCameraStatus.LOCALIZED,
                    reason="pose verified by native Castle localization regression",
                    translation=translation,
                    zoom=1.0,
                    frame_size=image.size,
                )

                match = localizer.match_target(frame, target, proof=proof)

                self.assertIsNotNone(match)
                self.assertEqual(HomeCitySlotSelector(1), match.home_city_slot)
                self.assertGreaterEqual(match.score, target.min_score)
                self.assertLessEqual(match.projection_error, target.max_projection_error)
                self.assertTrue(match.bounds.contains_bounds(match.action_bounds))
                self.assertTrue(match.action_bounds.contains_point(match.action_point))
                wrong_pose = replace(
                    proof, translation=(translation[0] + 300, translation[1])
                )
                self.assertIsNone(localizer.match_target(frame, target, proof=wrong_pose))
                # Camera/slot geometry alone cannot authorize a missing body.
                obscured = image.copy()
                bounds = match.bounds
                obscured.paste((0, 0, 0), (
                    bounds.x, bounds.y,
                    bounds.x + bounds.width, bounds.y + bounds.height,
                ))
                self.assertIsNone(localizer.match_target(obscured, target, proof=proof))

    def test_institute_body_matches_pan_view_with_verified_action_geometry(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)

        match = localizer.match_target(frame, target, proof=proof)

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
                match = localizer.match_target(frame, target, proof=proof)
                self.assertIsNotNone(match)
                self.assertGreaterEqual(match.score, 0.9)

    def test_institute_body_rejects_when_projection_disagrees(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        frame = localizer.prepare_frame(image)
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)

        # A contradictory camera hypothesis must not publish a body target.
        foreign_proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="contradictory hypothesis",
            translation=(-532, 222),
            zoom=1.0,
            frame_size=(900, 1600),
        )
        match = localizer.match_target(frame, target, proof=foreign_proof)

        self.assertIsNone(match)

    def test_tower_body_matches_only_its_qualified_view(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.TOWER_OF_TRIAL)

        image = _fixture(_CAMERA_FIXTURES / "home_city_tower_pan_28.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, proof=proof)

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
                    localizer.match_target(other, target, proof=other_proof)
                )

    def test_campaign_body_matches_portal_view_with_verified_action_geometry(self) -> None:
        """The portal body carries the verified c45 tap, not a label anchor."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.CAMPAIGN)

        image = _fixture(_CAMERA_FIXTURES / "home_city_campaign_portal_20260915.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        self.assertLessEqual(match.projection_error, 8.0)
        self.assertGreaterEqual(match.score, 0.93)
        # Verified Campaign tap (201,412) at 900x1600 scales to (121,247) at 540x960.
        self.assertEqual((121, 247), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))
        self.assertTrue(match.bounds.contains_bounds(match.action_bounds))

    def test_campaign_body_matches_bridge_view_above_the_safe_band(self) -> None:
        """The T2 bridge view matches the same body slightly above the tap band."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.CAMPAIGN)

        image = _fixture(_CAMERA_FIXTURES / "home_city_bridge_t2_20260916.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        self.assertGreaterEqual(match.score, 0.93)
        # Live-qualified point (660,278) at 900x1600 scales to (395,167) at 540x960;
        # 167 is above the HUD-safe minimum, so the route must pan before tapping.
        self.assertEqual((395, 167), match.action_point)

    def test_campaign_body_is_nonactionable_when_absent_or_unlocalized(self) -> None:
        """No body may be invented on views that cannot see the portal."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.CAMPAIGN)

        for name in (
            _SCREEN_RECOGNITION / "home_city_core.png",
            _CAMERA_FIXTURES / "home_city_pan_07.png",
            _CAMERA_FIXTURES / "home_city_tower_pan_28.png",
            _CAMERA_FIXTURES / "home_city_mega_castle.png",
            _CAMERA_FIXTURES / "home_city_bridge_t1_20260916.png",
        ):
            with self.subTest(fixture=name.name):
                other = localizer.prepare_frame(_fixture(name))
                other_proof = localizer.localize(other)
                self.assertIsNone(
                    localizer.match_target(other, target, proof=other_proof)
                )

    def test_manor_body_matches_native_view_with_verified_action_geometry(self) -> None:
        """The Manor body carries the verified 17:52:15 body tap, not a label anchor."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.ILLUSORY_BEAST_MANOR)

        image = _fixture(
            _SCREEN_RECOGNITION
            / "building_routes"
            / "home_city_illusory_beast_manor_20260921.png"
        )
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        self.assertLessEqual(match.projection_error, 8.0)
        self.assertGreaterEqual(match.score, 0.9)
        # The verified PW tap (511,722) is already at the native 900x1600 size.
        self.assertEqual((511, 722), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))
        self.assertTrue(match.bounds.contains_bounds(match.action_bounds))

    def test_manor_body_rejects_when_projection_disagrees(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        image = _fixture(
            _SCREEN_RECOGNITION
            / "building_routes"
            / "home_city_illusory_beast_manor_20260921.png"
        )
        frame = localizer.prepare_frame(image)
        target = catalog.target_for(HomeCityObjectId.ILLUSORY_BEAST_MANOR)

        # A contradictory camera hypothesis must not publish a body target.
        foreign_proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="contradictory hypothesis",
            translation=(-532, 222),
            zoom=1.0,
            frame_size=(900, 1600),
        )
        match = localizer.match_target(frame, target, proof=foreign_proof)

        self.assertIsNone(match)

    def test_manor_body_is_nonactionable_when_absent_or_unlocalized(self) -> None:
        """No Manor body may be invented on views that cannot see the structure."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.ILLUSORY_BEAST_MANOR)

        for name in (
            _SCREEN_RECOGNITION / "home_city_core.png",
            _CAMERA_FIXTURES / "home_city_pan_07.png",
            _CAMERA_FIXTURES / "home_city_tower_pan_28.png",
            _CAMERA_FIXTURES / "home_city_mega_castle.png",
            _CAMERA_FIXTURES / "home_city_bridge_t1_20260916.png",
        ):
            with self.subTest(fixture=name.name):
                other = localizer.prepare_frame(_fixture(name))
                other_proof = localizer.localize(other)
                self.assertIsNone(
                    localizer.match_target(other, target, proof=other_proof)
                )
