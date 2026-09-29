"""Home-camera homecameranegativeprovenancetests publication cases."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import home_city_object_id_from_metadata
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraStatus
from pnc_automation.app.pnc.domain.observation import SpatialObjectSourceKind
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from tests.support.pnc.home_city_camera.publication import (
    _CAMERA_TARGET_IDS,
    _BoundedRapidOcrService,
    HomeCameraPublicationAssertions,
    _capture,
    _wire,
)
from tests.support.pnc.capture_vision.require_rapid_ocr_service import (
    _require_rapid_ocr_service,
)
from tests.support.paths import TEST_DATA_ROOT


class HomeCameraNegativeProvenanceTests(HomeCameraPublicationAssertions, unittest.TestCase):
    """Retained captured assertions at the real two-publisher boundary."""

    def test_world_map_is_a_camera_negative_on_both_paths(self) -> None:
        """The World fixture shares HUD chrome but must never carry a localized proof."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        world = TEST_DATA_ROOT / "screen_recognition" / "world_map_core.png"
        with Image.open(world) as source:
            image = source.convert("RGB")
        captured_at = datetime.now(UTC)
        capture = CapturedScreenshot(
            None,
            image,
            "PNG",
            frame_ref=FrameRef(
                session_id="v02-home-camera",
                session_epoch=1,
                capture_sequence=4,
                input_sequence=0,
                captured_at=captured_at,
            ),
            ephemeral_captured_at=captured_at,
        )

        backend.bind(capture.image.size)
        navigation_observation = navigation.build(capture, include_content=True)
        surface = navigation_observation.spatial_surface
        if surface is not None:
            proof = surface.camera_proof
            self.assertTrue(
                proof is None or proof.status is not HomeCityCameraStatus.LOCALIZED,
                "a World frame must not localize as the Home camera",
            )
            self.assertFalse(
                any(
                    item.source_kind == SpatialObjectSourceKind.TEMPLATE
                    and home_city_object_id_from_metadata(item.metadata)
                    in _CAMERA_TARGET_IDS
                    for item in surface.objects
                ),
                "a World frame must not publish camera-qualified Home targets",
            )

    def test_frame_fingerprint_and_provenance_match_the_capture(self) -> None:
        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("home_city_pan_07.png", session_id="v02-home-camera", capture_sequence=5)

        observations = self._build_both(builder, navigation, backend, capture)
        fingerprint = hashlib.sha256(capture.image.tobytes()).hexdigest()
        for observation in observations:
            self.assertEqual(capture.frame_ref, observation.frame_ref)
            self.assertEqual(fingerprint, observation.frame_fingerprint)


if __name__ == "__main__":
    unittest.main()
