"""Home camera localization tests."""

from __future__ import annotations

from dataclasses import replace
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.vision.home_city_camera import (
    HomeCityCameraLocalizer,
    load_home_city_camera_catalog,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.home_camera_fixtures import (
    _CAMERA_FIXTURES,
    _SCREEN_RECOGNITION,
    _fixture,
    _localizer,
)


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
        """The live offer rail hides Institute; independent regions still locate Home."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(_fixture(_CAMERA_FIXTURES / "home_city_hud_occluded_20260916.png"))
        proof = localizer.localize(prepared)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, 222), proof.translation)
        self.assertEqual(
            frozenset(
                {
                    "plaza_low",
                    "garden_terrace",
                    "barracks_roofs",
                    "castle_structure",
                    "courtyard_garden",
                }
            ),
            proof.matched_group_ids,
        )
        objects = localizer.matched_target_objects(prepared, proof=proof)
        # The offer rail hides Institute, while the Castle body remains visible.
        self.assertEqual(
            [HomeCityObjectId.CASTLE.value],
            [item.metadata["home_city_object_id"] for item in objects],
        )
        self.assertIsNone(localizer.match_target(
            prepared, localizer.catalog.target_for(HomeCityObjectId.INSTITUTE), proof=proof,
        ))

    def test_live_tower_pan_localizes_after_northern_landmarks_leave_view(self) -> None:
        """The qualified Tower body extends camera proof beyond the Institute region."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(_fixture(_CAMERA_FIXTURES / "home_city_tower_lower_20260916.png"))
        proof = localizer.localize(prepared)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, -843), proof.translation)
        self.assertIn("tower_structure", proof.matched_group_ids)
        target = localizer.catalog.target_for(HomeCityObjectId.TOWER_OF_TRIAL)
        match = localizer.match_target(prepared, target, proof=proof)
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

    def test_west_live_holdout_localizes_at_both_supported_sizes(self) -> None:
        """Independent west capture retains three votes from two actual structures."""
        native = _fixture(_CAMERA_FIXTURES / "home_city_west_holdout_20260916.png")
        for size in ((900, 1600), (540, 960)):
            with self.subTest(size=size):
                proof = _localizer().localize(native.resize(size, Image.Resampling.LANCZOS))
                self.assertTrue(proof.localized)
                # Projecting integer 540px matches back to the 900px atlas
                # quantizes the vertical offset by one reference pixel.
                for actual, expected in zip(proof.translation, (-74, -812), strict=True):
                    self.assertLessEqual(abs(actual - expected), 1)
                self.assertEqual(frozenset({"tower_structure", "sanctum_structure"}), proof.matched_group_ids)
                self.assertEqual(3, len(proof.evidence))
                self.assertTrue(all(item.residual <= 1 for item in proof.evidence))

    def test_west_tower_crops_alone_do_not_supply_independent_scene_proof(self) -> None:
        """Two correlated Tower crops cannot replace the missing Sanctum evidence."""
        image = _fixture(_CAMERA_FIXTURES / "home_city_west_holdout_20260916.png")
        image.paste((0, 0, 0), (500, 960, 595, 1085))
        proof = _localizer().localize(image)
        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)

    def test_tower_view_localizes_at_the_measured_image_translation(self) -> None:
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_tower_pan_28.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, -638), proof.translation)
        self.assertIn("barracks_roofs", proof.matched_group_ids)

    def test_different_castle_appearance_still_localizes(self) -> None:
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_mega_castle.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-822, -260), proof.translation)

    def test_live_castle_holdout_localizes_through_three_courtyard_groups(self) -> None:
        """The 2026-09-21 panned castle view agrees on three independent regions."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(
            _fixture(_CAMERA_FIXTURES / "home_city_castle_holdout_20260921.png")
        )
        proof = localizer.localize(prepared)

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-545, 149), proof.translation)
        self.assertEqual(1.0, proof.zoom)
        self.assertTrue(
            {"castle_structure", "plaza_low", "courtyard_garden"}
            <= proof.matched_group_ids
        )
        objects = localizer.matched_target_objects(prepared, proof=proof)
        self.assertEqual(
            [HomeCityObjectId.CASTLE.value],
            [item.metadata["home_city_object_id"] for item in objects],
        )
        self.assertEqual(1, objects[0].home_city_slot.slot_index)
        self.assertEqual((337, 408), objects[0].action_point)

    def test_live_castle_default_view_localizes_at_the_reference_camera(self) -> None:
        """A different account's castle at the authored camera position localizes."""
        proof = _localizer().localize(
            _fixture(_CAMERA_FIXTURES / "home_city_castle_default_20260921.png")
        )

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, 222), proof.translation)
        self.assertTrue(
            {"castle_structure", "plaza_low"} <= proof.matched_group_ids
        )

    def test_live_institute_pretap_frame_localizes_past_the_false_zoom_conflict(self) -> None:
        """The live010 Institute pre-tap frame refused a false scale conflict.

        Weak 0.95/1.05 matches of the same scene features disagreed with
        one another by over the 10px rival bound under top-left
        correspondences; center correspondences converge on the measured
        image translation (-5,-624), atlas (-537,-402).
        """
        proof = _localizer().localize(
            _fixture(_CAMERA_FIXTURES / "home_city_institute_pretap_20260922.png")
        )

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(1.0, proof.zoom, delta=0.02)
        for actual, expected in zip(proof.translation, (-537, -402), strict=True):
            self.assertLessEqual(abs(actual - expected), 4)
        self.assertTrue(
            {"institute_structure", "plaza_low", "barracks_roofs"}
            <= proof.matched_group_ids
        )
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_live_tower_pretap_frame_localizes_past_the_false_zoom_conflict(self) -> None:
        """The live008 Tower pre-tap frame carried the same false conflict.

        Center correspondences converge on image translation (-2,-594),
        atlas (-534,-372), at the measured zoom 1.0.
        """
        proof = _localizer().localize(
            _fixture(_CAMERA_FIXTURES / "home_city_tower_pretap_20260922.png")
        )

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(1.0, proof.zoom, delta=0.02)
        for actual, expected in zip(proof.translation, (-534, -372), strict=True):
            self.assertLessEqual(abs(actual - expected), 4)
        self.assertTrue(
            {"tower_structure", "plaza_low", "barracks_roofs"}
            <= proof.matched_group_ids
        )
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_castle_structure_crops_alone_do_not_supply_independent_scene_proof(self) -> None:
        """Correlated Castle patches still require an independent region."""
        image = _fixture(_CAMERA_FIXTURES / "home_city_castle_holdout_20260921.png")
        image.paste((0, 0, 0), (100, 560, 540, 960))
        proof = _localizer().localize(image)

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)

    def test_statue_and_base_cannot_supply_independent_scene_proof(self) -> None:
        """Real statue and plaza matches cannot pretend to be separate structures."""
        catalog = load_home_city_camera_catalog()
        catalog = replace(
            catalog,
            landmarks=tuple(
                item for item in catalog.landmarks
                if item.id in {"statue_wings", "plaza_ring", "p5_plaza_low", "t6_plaza_south"}
            ),
        )
        localizer = HomeCityCameraLocalizer(
            matcher=OpenCvTemplateMatcher(), catalog=catalog,
        )
        proof = localizer.localize(
            _fixture(_CAMERA_FIXTURES / "home_city_hud_occluded_20260916.png")
        )
        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_independent_landmark_groups", proof.reason)
        self.assertGreaterEqual(len(proof.evidence), 3)
        self.assertIsNone(proof.translation)

    def test_tracked_panned_fixture_localizes_at_its_measured_translation(self) -> None:
        proof = _localizer().localize(_fixture(_SCREEN_RECOGNITION / "home_city_panned_core.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-822, -260), proof.translation)

    def test_bridge_t1_localizes_through_southern_corridor_landmarks(self) -> None:
        """The first live bridge pan lands on the measured corridor camera."""
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_bridge_t1_20260916.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-1009, -843), proof.translation)
        self.assertIn("blacksmith_structure", proof.matched_group_ids)
        self.assertIn("southern_courtyard", proof.matched_group_ids)

    def test_bridge_t2_localizes_through_eastern_landmarks(self) -> None:
        """The second live bridge pan lands on the eastern landmark groups."""
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_bridge_t2_20260916.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-1423, -843), proof.translation)
        self.assertTrue({"east_fortification", "east_cliff"} <= proof.matched_group_ids)

    def test_campaign_post_pan_hud_occlusion_localizes_through_fixed_groups(self) -> None:
        """The HUD-covered eastern view keeps two independent fixed groups.

        East-fortification aqueduct/ridge-wall and the scene-fixed Campaign
        portal body survive the HUD occlusion. Alliance Hall also matches but
        is a player-chosen slot occupant: it corroborates the fitted transform
        as attached evidence without counting toward the qualifying groups.
        """
        localizer = _localizer()
        frame = localizer.prepare_frame(
            _fixture(_CAMERA_FIXTURES / "home_city_campaign_hud_occluded_20260916.png")
        )
        proof = localizer.localize(frame)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-1423, -485), proof.translation)
        self.assertEqual(1.0, proof.zoom)
        fixed_groups = {
            evidence.group_id
            for evidence in proof.evidence
            if evidence.landmark_id != "alliance_hall_structure"
        }
        self.assertTrue({"east_fortification", "campaign_portal"} <= fixed_groups)
        self.assertIn("alliance_hall_structure", proof.matched_group_ids)
        match = localizer.match_target(
            frame,
            localizer.catalog.target_for(HomeCityObjectId.CAMPAIGN),
            proof=proof,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual((395, 382), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))

    def test_campaign_view_localizes_at_the_globally_calibrated_translation(self) -> None:
        """The c45 portal view resolves through the bridge-calibrated eastern crops."""
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_campaign_portal_20260915.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Accepted measurement is (-1882,-709); the 540x960 fixture rounds to (-1881,-710).
        self.assertEqual((-1881, -710), proof.translation)
        self.assertEqual(
            frozenset({"east_fortification", "east_cliff", "campaign_portal"}),
            proof.matched_group_ids,
        )

    def test_manor_view_localizes_through_its_structure_parts(self) -> None:
        """The PW02 Home frame localizes only once the Manor structure is authored."""
        proof = _localizer().localize(
            _fixture(
                _SCREEN_RECOGNITION
                / "building_routes"
                / "home_city_illusory_beast_manor_20260921.png"
            )
        )

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Accepted PW02 measurement; the same frame was INSUFFICIENT before the
        # two Manor regions were authored because no second group was present.
        self.assertEqual((-521, -1346), proof.translation)
        self.assertIn("illusory_beast_manor_structure", proof.matched_group_ids)

    def test_manor_masked_body_cannot_supply_independent_scene_proof(self) -> None:
        """Masking the Manor structure leaves two votes that cannot localize."""
        image = _fixture(
            _SCREEN_RECOGNITION
            / "building_routes"
            / "home_city_illusory_beast_manor_20260921.png"
        )
        image.paste((0, 0, 0), (440, 630, 590, 760))
        proof = _localizer().localize(image)
        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)

    def test_manor_structure_alone_cannot_establish_the_camera(self) -> None:
        """The PW006 hopium_growth view keeps Manor plus Blacksmith insufficient.

        Both Manor landmarks score well but share one structure group, and the
        movable Blacksmith is excluded from independent votes, so the native
        RGBA frame publishes no translation or zoom.  This is the reviewed
        ``insufficient_independent_landmark_groups`` outcome; it must never be
        turned positive by lowering the group requirement.
        """
        proof = _localizer().localize(
            _fixture(_CAMERA_FIXTURES / "home_city_pw_manor_negative_20260922.png")
        )

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_independent_landmark_groups", proof.reason)
        self.assertIsNone(proof.translation)
        self.assertIsNone(proof.zoom)
        self.assertEqual(
            {"illusory_beast_manor_owl_head", "illusory_beast_manor_right_tower"},
            {item.landmark_id for item in proof.evidence},
        )
        self.assertEqual(
            frozenset({"illusory_beast_manor_structure"}),
            {item.group_id for item in proof.evidence},
        )

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
            zoom=1.0,
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
        with self.assertRaises(SelectorResolutionError):
            HomeCityCameraProof(
                status=HomeCityCameraStatus.LOCALIZED,
                reason="missing zoom",
                translation=(-532, 222),
                frame_size=(540, 960),
            )
