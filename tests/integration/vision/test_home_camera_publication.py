"""Home-city camera proof and measured building targets through both publishers.

Qualifies the shared V02 path on real captured Home views: the packaged visual
recognizer accepts Home identity independently, the camera localizer measures
the atlas translation from scene landmarks, and both ``ObservationBuilder`` and
``NavigationPerception`` publish the same camera proof, template-qualified
Institute/Tower objects, preserved OCR facts, and full frame provenance —
without depending on correctly spelled building-name OCR.
"""

from __future__ import annotations

import hashlib
import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraStatus
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    SpatialObjectSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.home_city_camera import HomeCityCameraLocalizer
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    OcrLine,
    OcrResult,
    RapidOcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


FIXTURES = TEST_DATA_ROOT / "home_city_camera"
HOME_LAYOUT_ID = "home_city"
_CAMERA_TARGET_IDS = frozenset(
    {HomeCityObjectId.INSTITUTE, HomeCityObjectId.TOWER_OF_TRIAL, HomeCityObjectId.CAMPAIGN}
)

# Reviewed measured results for each tracked fixture: expected atlas-to-
# reference translation and the camera-qualified target objects with their
# measured action points in fixture pixels.
_EXPECTED = {
    "home_city_pan_07.png": {
        "translation": (-1000, -710),
        "targets": {HomeCityObjectId.INSTITUTE: (154, 193)},
    },
    "home_city_tower_pan_28.png": {
        "translation": (-532, -638),
        "targets": {
            HomeCityObjectId.INSTITUTE: (434, 236),
            HomeCityObjectId.TOWER_OF_TRIAL: (179, 512),
        },
    },
    "home_city_mega_castle.png": {
        "translation": (-822, -260),
        "targets": {HomeCityObjectId.INSTITUTE: (260, 463)},
    },
    "home_city_campaign_portal_20260915.png": {
        "translation": (-1881, -710),
        "targets": {HomeCityObjectId.CAMPAIGN: (121, 247)},
    },
    "home_city_bridge_t2_20260916.png": {
        "translation": (-1423, -843),
        "targets": {HomeCityObjectId.CAMPAIGN: (395, 167)},
    },
}


@dataclass(slots=True)
class _BoundedRapidOcrService:
    """Use shared RapidOCR while recording calls and rejecting whole-frame reads."""

    delegate: RapidOcrService
    capture_size: tuple[int, int] | None = None
    calls: list[tuple[Bounds | None, tuple[int, int]]] = field(default_factory=list)

    def bind(self, image_size: tuple[int, int]) -> None:
        """Bind a fresh frame and reset native-call accounting."""

        self.capture_size = image_size
        self.calls.clear()

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Reject ``None`` on the full image and explicit whole-frame bounds."""

        self.calls.append((region, image.size))
        whole = None if self.capture_size is None else Bounds(0, 0, *self.capture_size)
        if region == whole or (region is None and self.capture_size == image.size):
            raise AssertionError("Home camera test reached RapidOCR without a strict crop")
        return self.delegate.read_result(image, region)

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _capture(name: str, *, session_id: str, capture_sequence: int) -> CapturedScreenshot:
    """Load a tracked capture with explicit frame provenance and no payload shortcut."""

    with Image.open(FIXTURES / name) as source:
        image = source.convert("RGB")
    captured_at = datetime.now(UTC)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        frame_ref=FrameRef(
            session_id=session_id,
            session_epoch=1,
            capture_sequence=capture_sequence,
            input_sequence=0,
            captured_at=captured_at,
        ),
        ephemeral_captured_at=captured_at,
    )


def _wire(
    ocr_service: _BoundedRapidOcrService,
) -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both production publishers with the shared camera localizer."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(
        selector_registry=registry,
        home_city_camera=HomeCityCameraLocalizer(matcher=matcher),
    )
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )

    def context(screenshot: CapturedScreenshot):
        return builder.create_ocr_context(screenshot)

    navigation = NavigationPerception(
        builder.visual_recognizer,
        enricher,
        ScreenClassifier(),
        context,
    )
    return builder, navigation


class HomeCameraPublicationTests(unittest.TestCase):
    """Replayed Home captures qualify the camera contract on both publishers."""

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

    def _build_both(
        self,
        builder: ObservationBuilder,
        navigation: NavigationPerception,
        backend: _BoundedRapidOcrService,
        capture: CapturedScreenshot,
    ) -> tuple[Observation, Observation]:
        backend.bind(capture.image.size)
        builder_observation = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            ocr_context=builder.create_ocr_context(capture),
        )
        backend.bind(capture.image.size)
        navigation_observation = navigation.build(capture, include_content=True)
        return builder_observation, navigation_observation

    def _assert_camera_publication(
        self,
        observation: Observation,
        capture: CapturedScreenshot,
        expected_translation: tuple[int, int],
        expected_targets: dict[HomeCityObjectId, tuple[int, int]],
    ) -> None:
        """Require localized proof, measured targets, and honest provenance."""

        self.assertEqual(ScreenType.PNC_HOME_CITY, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        surface = observation.spatial_surface
        self.assertIsNotNone(surface, "accepted Home identity must publish the spatial surface")
        assert surface is not None
        proof = surface.camera_proof
        self.assertIsNotNone(proof, "accepted Home identity must publish a camera proof")
        assert proof is not None
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        assert proof.translation is not None
        self.assertLessEqual(abs(proof.translation[0] - expected_translation[0]), 1)
        self.assertLessEqual(abs(proof.translation[1] - expected_translation[1]), 1)
        self.assertEqual((900, 1600), proof.reference_size)
        self.assertEqual(capture.image.size, proof.frame_size)
        self.assertEqual(capture.frame_ref, proof.frame_ref)
        self.assertEqual(ScreenType.PNC_HOME_CITY, proof.source_screen)
        self.assertEqual(observation.decision.layout_id, proof.source_layout_id)
        by_target = {
            home_city_object_id_from_metadata(item.metadata): item
            for item in surface.objects
            if home_city_object_id_from_metadata(item.metadata) is not None
        }
        for target, action_point in expected_targets.items():
            with self.subTest(target=target.value):
                item = by_target.get(target)
                self.assertIsNotNone(item, f"{target.value} must publish from the current frame")
                assert item is not None
                self.assertEqual(SpatialObjectSourceKind.TEMPLATE, item.source_kind)
                self.assertEqual(action_point, item.action_point)
                self.assertIsNotNone(item.action_bounds)
                assert item.action_bounds is not None
                self.assertTrue(item.bounds.contains_bounds(item.action_bounds))
                self.assertTrue(item.action_bounds.contains_point(item.action_point))
                self.assertEqual(capture.frame_ref, item.frame_ref)
                self.assertEqual(ScreenType.PNC_HOME_CITY, item.source_screen)
                self.assertEqual(observation.decision.layout_id, item.source_layout_id)
        self.assertTrue(
            any(item.source_kind == SpatialObjectSourceKind.OCR for item in surface.objects),
            "useful OCR facts must survive alongside camera-qualified objects",
        )

    def test_pan_capture_publishes_institute_without_a_spelled_label(self) -> None:
        """pan_07 localizes and opens the verified tap point; OCR never spells Institute."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("home_city_pan_07.png", session_id="v02-home-camera", capture_sequence=1)

        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_pan_07.png"]
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

    def test_campaign_post_pan_hud_occlusion_keeps_fresh_actionable_body(self) -> None:
        """Actual HUD occlusion does not erase the independent camera proof."""
        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_campaign_hud_occluded_20260916.png",
            session_id="v02-campaign-occlusion",
            capture_sequence=8,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        for observation in observations:
            self._assert_camera_publication(
                observation, capture, (-1423, -484),
                {HomeCityObjectId.CAMPAIGN: (395, 382)},
            )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

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
