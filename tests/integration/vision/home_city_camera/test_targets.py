"""Home-camera homecameratargetpublicationtests publication cases."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectSourceKind
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    HOME_CITY_HUD_SAFE_MAX_Y_RATIO,
)
from pnc_automation.core.infra.capture.screenshot_service import (
    CapturedScreenshot,
    FrameRef,
)
from tests.support.pnc.home_city_camera.publication import (
    _CAMERA_TARGET_IDS,
    _BoundedRapidOcrService,
    _EXPECTED,
    HomeCameraPublicationAssertions,
    _capture,
    _wire,
)
from tests.support.pnc.capture_vision.require_rapid_ocr_service import (
    _require_rapid_ocr_service,
)
from tests.support.paths import TEST_DATA_ROOT


class HomeCameraTargetPublicationTests(HomeCameraPublicationAssertions, unittest.TestCase):
    """Retained captured assertions at the real two-publisher boundary."""

    def test_wall_slot2_reaches_both_publishers(self) -> None:
        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_wall_slot2_f6_20260922.png",
            session_id="v44-ordinary-bodies",
            capture_sequence=0,
            fixture_root=TEST_DATA_ROOT / "home_city_slot_bodies",
        )
        self.assertEqual(("RGBA", (900, 1600)), (capture.image.mode, capture.image.size))
        observations = self._build_both(builder, navigation, backend, capture)
        for observation in observations:
            self._assert_camera_publication(
                observation,
                capture,
                (-1635, -718),
                {HomeCityObjectId.WALL: (118, 983)},
            )
            bodies = [
                item
                for item in observation.spatial_surface.objects
                if home_city_object_id_from_metadata(item.metadata) is HomeCityObjectId.WALL
            ]
            self.assertEqual(1, len(bodies))
            self.assertEqual(2, bodies[0].home_city_slot.slot_index)
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_west_holdout_publishes_camera_and_tower_through_both_paths(self) -> None:
        """A current west view localizes without inventing the offscreen Institute."""
        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_west_holdout_20260916.png", session_id="v02-west-camera", capture_sequence=1,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        for path, observation in enumerate(observations):
            with self.subTest(publisher=path):
                self._assert_camera_publication(
                    observation, capture, (-74, -812), {HomeCityObjectId.TOWER_OF_TRIAL: (757, 680)},
                )
                self.assertFalse(any(
                    home_city_object_id_from_metadata(item.metadata) is HomeCityObjectId.INSTITUTE
                    and item.source_kind is SpatialObjectSourceKind.TEMPLATE
                    for item in observation.spatial_surface.objects
                ))
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_pan_capture_publishes_institute_without_a_spelled_label(self) -> None:
        """pan_07 localizes and opens the verified tap point; OCR never spells Institute."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("home_city_pan_07.png", session_id="v02-home-camera", capture_sequence=1)

        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_pan_07.png"]
        fingerprint = hashlib.sha256(capture.image.tobytes()).hexdigest()
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_camera_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
                self.assertEqual(capture.frame_ref, observation.frame_ref)
                self.assertEqual(fingerprint, observation.frame_fingerprint)
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_tower_capture_publishes_both_measured_targets_on_both_paths(self) -> None:
        """tpan_28 localizes at its own translation and exposes Tower's verified point."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("home_city_tower_pan_28.png", session_id="v02-home-camera", capture_sequence=2)

        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_tower_pan_28.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_camera_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_mega_castle_appearance_still_publishes_measured_institute(self) -> None:
        """A different castle appearance does not defeat landmark consensus or body matching."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("home_city_mega_castle.png", session_id="v02-home-camera", capture_sequence=3)

        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_mega_castle.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_camera_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_campaign_capture_publishes_portal_body_without_a_spelled_label(self) -> None:
        """The bridge-calibrated c45 view localizes and exposes the verified portal tap."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_campaign_portal_20260915.png",
            session_id="v02-home-camera",
            capture_sequence=6,
        )

        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_campaign_portal_20260915.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_camera_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_bridge_t2_capture_publishes_the_same_portal_body(self) -> None:
        """The independent mega-castle bridge frame agrees on the same measured body."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_bridge_t2_20260916.png",
            session_id="v02-home-camera",
            capture_sequence=7,
        )

        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_bridge_t2_20260916.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_camera_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_campaign_post_pan_hud_occlusion_publishes_measured_body(self) -> None:
        """HUD occlusion must not hide qualified fixed evidence on the V02 route.

        The HUD-covered eastern view still carries two independent fixed groups:
        east-fortification aqueduct/ridge-wall and the scene-fixed Campaign
        portal body. Alliance Hall also matches but stays a movable corroborator
        and does not establish the camera. Both publishers must localize at the
        measured atlas translation and expose the Campaign body tap.
        """
        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_campaign_hud_occluded_20260916.png",
            session_id="v02-campaign-occlusion",
            capture_sequence=8,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_campaign_hud_occluded_20260916.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_camera_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
                surface = observation.spatial_surface
                assert surface is not None and surface.camera_proof is not None
                self.assertIn(
                    "campaign_portal",
                    surface.camera_proof.matched_group_ids,
                    "the fixed Campaign portal group must corroborate the camera",
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_castle_views_publish_camera_proof_and_only_the_observed_castle(self) -> None:
        """The 2026-09-21 castle captures localize through independent courtyard groups.

        The default-camera view localizes on castle structure plus plaza floor,
        and the panned holdout agrees on castle structure, the Goddess Statue
        monument, and the west garden -- three genuinely independent regions.
        The qualified Castle tower supplies slot 1 and its measured interior
        point in both views; no other building body may be invented.
        """
        for name, expected_translation in (
            ("home_city_castle_default_20260921.png", (-532, 222)),
            ("home_city_castle_holdout_20260921.png", (-545, 149)),
        ):
            backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
            builder, navigation = _wire(backend)
            capture = _capture(name, session_id="v44-castle-camera", capture_sequence=9)

            observations = self._build_both(builder, navigation, backend, capture)
            expected = _EXPECTED[name]
            for publisher, observation in (
                ("observation_builder", observations[0]),
                ("navigation_perception", observations[1]),
            ):
                with self.subTest(fixture=name, publisher=publisher):
                    self._assert_camera_publication(
                        observation,
                        capture,
                        expected_translation,
                        expected["targets"],
                    )
                    surface = observation.spatial_surface
                    assert surface is not None and surface.camera_proof is not None
                    self.assertIn(
                        "castle_structure",
                        surface.camera_proof.matched_group_ids,
                        "the castle keep group must corroborate the camera",
                    )
                    bodies = [
                        item for item in surface.objects
                        if item.source_kind is SpatialObjectSourceKind.TEMPLATE
                    ]
                    self.assertEqual(
                        [HomeCityObjectId.CASTLE],
                        [home_city_object_id_from_metadata(item.metadata) for item in bodies],
                    )
                    self.assertEqual(1, bodies[0].home_city_slot.slot_index)
            self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_northeast_holdout_publishes_camera_without_authorizing_buildings(self) -> None:
        """The 2026-09-23 northeast view localizes but authorizes no tap.

        The 157_farm baseline frame shows the northeast district that had zero
        landmark correspondences before the Sauroi pier and moat fortification
        crops were authored. Both publishers must localize at zoom ~1.0 near
        atlas translation (-1251, +139) through at least three fixed
        correspondences in two genuinely independent groups. The slot-3
        Warehouse body is genuinely visible and publishes measured perception
        evidence, but its action point lands below the HUD-safe tap band, so
        this view still authorizes no building interaction.
        """
        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        name = "home_city_northeast_holdout_20260923.png"
        capture = _capture(name, session_id="v44-northeast-camera", capture_sequence=1)
        self.assertEqual(("RGBA", (900, 1600)), (capture.image.mode, capture.image.size))

        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED[name]
        safe_max_y = int(HOME_CITY_HUD_SAFE_MAX_Y_RATIO * 1600)
        for publisher, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=publisher):
                self._assert_camera_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
                surface = observation.spatial_surface
                assert surface is not None and surface.camera_proof is not None
                proof = surface.camera_proof
                self.assertAlmostEqual(expected["zoom"], proof.zoom, delta=0.005)
                self.assertGreaterEqual(len(proof.evidence), 3)
                self.assertTrue(
                    {"sauroi_lair_structure", "east_fortification"}
                    <= proof.matched_group_ids,
                    "the northeast view must localize on the new fixed groups",
                )
                template_objects = [
                    item
                    for item in surface.objects
                    if item.source_kind is SpatialObjectSourceKind.TEMPLATE
                ]
                self.assertEqual(
                    {HomeCityObjectId.WAREHOUSE},
                    {
                        home_city_object_id_from_metadata(item.metadata)
                        for item in template_objects
                    },
                    "only the genuinely visible Warehouse may publish",
                )
                warehouse = template_objects[0]
                self.assertEqual(3, warehouse.home_city_slot.slot_index)
                assert warehouse.action_point is not None
                self.assertGreater(
                    warehouse.action_point[1],
                    safe_max_y,
                    "the Warehouse action lies below the tap band: evidence only",
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_wall_corridor_publishes_wall_slot2_through_both_paths(self) -> None:
        """The 2026-09-23 wall-corridor regression frame qualifies Wall slot 2.

        V44 final live turn003 panned to a clear Wall view where only
        east_fortification could previously establish the camera; the new
        fixed campaign_left_pedestal landmark (shared campaign_portal group)
        supplies the second group while the movable Alliance Hall
        corroborates only. Both publishers must localize at zoom 1.0 near
        atlas (-1298,-645), publish the existing Wall slot-2 body at
        (456,1057) with full provenance, and publish the genuinely present
        Alliance Hall slot-13 body at (507,810) and the source Market slot-11
        body at (213,949), without inventing any other target.
        """
        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        name = "home_city_wall_corridor_regression_20260923.png"
        capture = _capture(name, session_id="v44-wall-corridor", capture_sequence=1)
        self.assertEqual(("RGBA", (900, 1600)), (capture.image.mode, capture.image.size))

        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED[name]
        for publisher, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=publisher):
                self._assert_camera_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
                surface = observation.spatial_surface
                assert surface is not None and surface.camera_proof is not None
                proof = surface.camera_proof
                self.assertAlmostEqual(expected["zoom"], proof.zoom, delta=0.005)
                self.assertTrue(
                    {"campaign_portal", "east_fortification"}
                    <= proof.matched_group_ids,
                    "the wall corridor must localize on the two fixed groups",
                )
                walls = [
                    item
                    for item in surface.objects
                    if home_city_object_id_from_metadata(item.metadata)
                    is HomeCityObjectId.WALL
                ]
                self.assertEqual(1, len(walls))
                self.assertEqual(2, walls[0].home_city_slot.slot_index)
                self.assertEqual(
                    {HomeCityObjectId.WALL, HomeCityObjectId.ALLIANCE_HALL, HomeCityObjectId.MARKET},
                    {
                        home_city_object_id_from_metadata(item.metadata)
                        for item in surface.objects
                        if item.source_kind is SpatialObjectSourceKind.TEMPLATE
                    },
                    "the corridor view must not invent any other camera target",
                )
                market = next(
                    item for item in surface.objects
                    if home_city_object_id_from_metadata(item.metadata) is HomeCityObjectId.MARKET
                    and item.source_kind is SpatialObjectSourceKind.TEMPLATE
                )
                self.assertEqual(11, market.home_city_slot.slot_index)
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_manor_capture_publishes_measured_body_through_both_paths(self) -> None:
        """The native PW02 view localizes through the Manor structure and exposes its tap."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        manor_frame = (
            TEST_DATA_ROOT
            / "screen_recognition"
            / "building_routes"
            / "home_city_illusory_beast_manor_20260921.png"
        )
        with Image.open(manor_frame) as source:
            image = source.copy()
        self.assertEqual(("RGBA", (900, 1600)), (image.mode, image.size))
        captured_at = datetime.now(UTC)
        capture = CapturedScreenshot(
            None,
            image,
            "PNG",
            frame_ref=FrameRef(
                session_id="pw07-manor-camera",
                session_epoch=1,
                capture_sequence=1,
                input_sequence=0,
                captured_at=captured_at,
            ),
            ephemeral_captured_at=captured_at,
        )

        observations = self._build_both(builder, navigation, backend, capture)
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_camera_publication(
                    observation,
                    capture,
                    (-521, -1346),
                    {HomeCityObjectId.ILLUSORY_BEAST_MANOR: (511, 722)},
                )
                # The generic Manor label and the other camera targets must not
                # be invented on this frame.
                self.assertFalse(
                    any(
                        item.source_kind is SpatialObjectSourceKind.TEMPLATE
                        and home_city_object_id_from_metadata(item.metadata)
                        in _CAMERA_TARGET_IDS - {HomeCityObjectId.ILLUSORY_BEAST_MANOR}
                        for item in observation.spatial_surface.objects
                    )
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)
