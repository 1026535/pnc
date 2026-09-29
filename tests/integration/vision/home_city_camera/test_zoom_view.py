"""Home-camera homecamerazoompublicationtests publication cases."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityZoomStatus
from pnc_automation.app.pnc.domain.observation import SpatialObjectSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from tests.support.pnc.home_city_camera.publication import (
    _BoundedRapidOcrService,
    _EXPECTED,
    HomeCameraPublicationAssertions,
    _capture,
    _wire,
)
from tests.support.pnc.capture_vision.require_rapid_ocr_service import (
    _require_rapid_ocr_service,
)


class HomeCameraZoomPublicationTests(HomeCameraPublicationAssertions, unittest.TestCase):
    """Retained captured assertions at the real two-publisher boundary."""

    def test_native_zoom_frames_publish_measured_scale_through_both_paths(self) -> None:
        """The 2026-09-22 native wheel-zoom captures pin both publishers.

        These are the game's own rendered zoom states at native 900x1600 —
        distinct from the cross-resolution and resampled-zoom regressions —
        captured on 157_farm under client 5.0.204/235. Wheel -1 sampled
        scale ~1.072 at atlas (-603, 78); the inverse wheel +1 restored
        scale 1.0 at a different translation (-532, 73), so scale recovery
        is never pose recovery. At the zoomed pose the Institute body crop
        stays unmatched, while the independently measured Goddess statue body
        supplies a slot-15 body. Preserve the Institute negative without
        suppressing this qualified body. Only the sampled scales are qualified.
        """
        for sequence, name in enumerate(
            (
                "home_city_native_zoom_baseline_20260922.png",
                "home_city_native_zoom_holdout_20260922.png",
                "home_city_native_zoom_restored_20260922.png",
            )
        ):
            backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
            builder, navigation = _wire(backend)
            capture = _capture(
                name, session_id="v44-native-zoom", capture_sequence=sequence,
            )
            self.assertEqual(("RGBA", (900, 1600)), (capture.image.mode, capture.image.size))

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
                        expected["translation"],
                        expected["targets"],
                    )
                    surface = observation.spatial_surface
                    assert surface is not None and surface.camera_proof is not None
                    proof = surface.camera_proof
                    self.assertAlmostEqual(expected["zoom"], proof.zoom, delta=0.005)
                    self.assertEqual((900, 1600), proof.frame_size)
                    self.assertGreaterEqual(len(proof.evidence), 3)
                    self.assertGreaterEqual(len(proof.matched_group_ids), 2)
                    if name == "home_city_native_zoom_holdout_20260922.png":
                        self.assertFalse(
                            any(
                                item.source_kind is SpatialObjectSourceKind.TEMPLATE
                                and home_city_object_id_from_metadata(item.metadata)
                                is HomeCityObjectId.INSTITUTE
                                for item in surface.objects
                            ),
                            "the zoomed frame does not qualify the Institute body",
                        )
                        goddess_bodies = [
                            item
                            for item in surface.objects
                            if home_city_object_id_from_metadata(item.metadata)
                            is HomeCityObjectId.GODDESS_STATUE
                        ]
                        self.assertEqual(1, len(goddess_bodies))
                        self.assertEqual(15, goddess_bodies[0].home_city_slot.slot_index)
            self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_zoom_view_evidence_publishes_identically_through_both_paths(self) -> None:
        """Both publishers carry the measured zoom verdict and qualified anchor.

        The 2026-09-25 endpoint repeat frame publishes the calibrated endpoint
        class and the northeast moat lane anchor; the nearest non-endpoint
        rung -- publishing the same snapped 0.75 consensus zoom -- must
        classify NOT_AT_ENDPOINT and publishes the castle-fountain wheel
        anchor that is visible at that pose; the 2026-09-27 default-start
        frame publishes the same fountain anchor at its measured position.
        Both publishers consume the single shared surface, so the view
        evidence, frame size, and frame provenance are identical on each path.
        """
        for sequence, (name, translation, status, reason, anchor_id, anchor_point, targets) in enumerate((
            (
                "home_city_zoom_endpoint_20260925.png",
                (-1084, 50),
                HomeCityZoomStatus.AT_ENDPOINT,
                "measured_zoom_at_endpoint",
                "northeast_moat_slope_wheel_20260925",
                (270, 704),
                {},
            ),
            (
                "home_city_zoom_rung_20260925.png",
                (-287, 52),
                HomeCityZoomStatus.NOT_AT_ENDPOINT,
                "measured_zoom_closer_than_endpoint",
                "castle_fountain_wheel_20260927",
                (450, 558),
                # The slot-3 Warehouse body is genuinely visible in this view.
                {HomeCityObjectId.WAREHOUSE: (838, 725)},
            ),
            (
                "home_city_default_start_20260927.png",
                (-532, 222),
                HomeCityZoomStatus.NOT_AT_ENDPOINT,
                "measured_zoom_closer_than_endpoint",
                "castle_fountain_wheel_20260927",
                (450, 895),
                {},
            ),
            (
                "home_city_fountain_935_20260927.png",
                (-468, 69),
                HomeCityZoomStatus.NOT_AT_ENDPOINT,
                "measured_zoom_closer_than_endpoint",
                "castle_fountain_wheel_20260927",
                (450, 699),
                {},
            ),
            (
                "home_city_fountain_879_20260927.png",
                (-414, 65),
                HomeCityZoomStatus.NOT_AT_ENDPOINT,
                "measured_zoom_closer_than_endpoint",
                "castle_fountain_wheel_20260927",
                (450, 657),
                {},
            ),
        )):
            backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
            builder, navigation = _wire(backend)
            capture = _capture(
                name, session_id="v44-zoom-view", capture_sequence=sequence,
            )
            self.assertEqual(("RGBA", (900, 1600)), (capture.image.mode, capture.image.size))

            observations = self._build_both(builder, navigation, backend, capture)
            for publisher, observation in (
                ("observation_builder", observations[0]),
                ("navigation_perception", observations[1]),
            ):
                with self.subTest(fixture=name, publisher=publisher):
                    self._assert_camera_publication(
                        observation, capture, translation, targets,
                    )
                    surface = observation.spatial_surface
                    assert surface is not None
                    view = surface.home_city_view
                    self.assertIsNotNone(view)
                    assert view is not None
                    self.assertEqual(status, view.zoom_status)
                    self.assertEqual(reason, view.reason)
                    self.assertEqual("home_zoom_endpoint_20260925", view.calibration_id)
                    self.assertEqual(capture.image.size, view.frame_size)
                    self.assertEqual(capture.frame_ref, view.frame_ref)
                    self.assertEqual(ScreenType.PNC_HOME_CITY, view.source_screen)
                    self.assertEqual(
                        observation.decision.layout_id, view.source_layout_id
                    )
                    anchor = view.zoom_anchor
                    if anchor_point is None:
                        self.assertIsNone(anchor)
                    else:
                        self.assertIsNotNone(anchor)
                        assert anchor is not None
                        self.assertEqual(anchor_id, anchor.qualification_id)
                        self.assertEqual(anchor_point, anchor.point)
                        self.assertTrue(anchor.bounds.contains_point(anchor.point))
            self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)
