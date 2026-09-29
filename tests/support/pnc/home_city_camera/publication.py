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
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraStatus,
    HomeCityZoomStatus,
)
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    SpatialObjectSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.home_city_camera import HomeCityCameraLocalizer
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    OcrLine,
    OcrResult,
    OcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.pnc.publication import make_publication_pair



FIXTURES = TEST_DATA_ROOT / "home_city_camera"
HOME_LAYOUT_ID = "home_city"
_CAMERA_TARGET_IDS = frozenset(
    {
        HomeCityObjectId.INSTITUTE,
        HomeCityObjectId.TOWER_OF_TRIAL,
        HomeCityObjectId.CAMPAIGN,
        HomeCityObjectId.ILLUSORY_BEAST_MANOR,
        HomeCityObjectId.GODDESS_STATUE,
    }
)

# Reviewed measured results for each tracked fixture: expected atlas-to-
# reference translation and the camera-qualified target objects with their
# measured action points in fixture pixels.
_EXPECTED = {
    "home_city_pan_07.png": {
        "translation": (-1000, -710),
        "targets": {
            HomeCityObjectId.INSTITUTE: (154, 193),
            HomeCityObjectId.WAREHOUSE: (301, 113),
        },
    },
    "home_city_tower_pan_28.png": {
        "translation": (-532, -638),
        "targets": {
            HomeCityObjectId.INSTITUTE: (434, 236),
            HomeCityObjectId.TOWER_OF_TRIAL: (179, 512),
            HomeCityObjectId.GODDESS_STATUE: (277, 245),
        },
    },
    "home_city_mega_castle.png": {
        "translation": (-822, -260),
        "targets": {
            HomeCityObjectId.INSTITUTE: (260, 463),
            HomeCityObjectId.GODDESS_STATUE: (103, 473),
            HomeCityObjectId.WAREHOUSE: (407, 382),
        },
    },
    "home_city_campaign_portal_20260915.png": {
        "translation": (-1881, -710),
        "targets": {HomeCityObjectId.CAMPAIGN: (121, 247)},
    },
    "home_city_bridge_t2_20260916.png": {
        "translation": (-1423, -843),
        "targets": {HomeCityObjectId.CAMPAIGN: (395, 167)},
    },
    "home_city_campaign_hud_occluded_20260916.png": {
        "translation": (-1423, -485),
        "targets": {HomeCityObjectId.CAMPAIGN: (395, 382)},
    },
    "home_city_castle_default_20260921.png": {
        "translation": (-532, 222),
        "targets": {HomeCityObjectId.CASTLE: (344, 452)},
    },
    "home_city_castle_holdout_20260921.png": {
        "translation": (-545, 149),
        "targets": {HomeCityObjectId.CASTLE: (337, 408)},
    },
    # 2026-09-22 157_farm native wheel-zoom captures (client 5.0.204/235):
    # sampled scene scales 1.0 and ~1.072 at unchanged 900x1600. The zoomed
    # holdout does not qualify the Institute body; the corrected Goddess
    # statue body does. The baseline renders that column uniformly darker and
    # honestly stays unmatched, while the restored frame proves scale 1.0
    # returns the body without restoring the baseline camera pose.
    "home_city_native_zoom_baseline_20260922.png": {
        "translation": (-532, 222),
        "targets": {HomeCityObjectId.INSTITUTE: (724, 1253)},
        "zoom": 1.0,
    },
    "home_city_native_zoom_holdout_20260922.png": {
        "translation": (-603, 78),
        "targets": {HomeCityObjectId.GODDESS_STATUE: (462, 1201)},
        "zoom": 1.071989179,
    },
    "home_city_native_zoom_restored_20260922.png": {
        "translation": (-532, 73),
        "targets": {HomeCityObjectId.INSTITUTE: (724, 1104), HomeCityObjectId.GODDESS_STATUE: (461, 1120)},
        "zoom": 1.0,
    },
    # 2026-09-23 157_farm northeast baseline frame: the new fixed Sauroi pier
    # and moat fortification crops localize the previously landmark-free view.
    # The slot-3 Warehouse body is genuinely visible and now qualifies, but its
    # measured action point sits below the HUD-safe band, so this view remains
    # perception evidence only and authorizes no tap.
    "home_city_northeast_holdout_20260923.png": {
        "translation": (-1251, 139),
        "targets": {HomeCityObjectId.WAREHOUSE: (250, 1038)},
        "zoom": 1.0,
    },
    # 2026-09-23 157_farm wall-corridor regression frame (turn003 c3c post-pan
    # view, frame 0064): the new campaign_left_pedestal landmark supplies the
    # second independent fixed group and the existing Wall slot-2 body
    # qualifies. Diagnosis-derived live regression sample, not a holdout.
    "home_city_wall_corridor_regression_20260923.png": {
        "translation": (-1298, -645),
        "targets": {HomeCityObjectId.WALL: (456, 1057)},
        "zoom": 1.0,
    },
}



@dataclass(slots=True)
class _BoundedRapidOcrService:
    """Use shared RapidOCR while recording calls and rejecting whole-frame reads."""

    delegate: OcrService
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



def _capture(
    name: str, *, session_id: str, capture_sequence: int, fixture_root: Path = FIXTURES,
) -> CapturedScreenshot:
    """Load a tracked capture with explicit frame provenance and no payload shortcut."""

    with Image.open(fixture_root / name) as source:
        image = source.copy()
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
    return make_publication_pair(
        selector_registry=registry,
        matcher=matcher,
        enricher=enricher,
        ocr_service=ocr_service,
    )




class HomeCameraPublicationAssertions:
    """Shared two-publisher construction and provenance assertions."""

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
            any(item.source_kind == SpatialObjectSourceKind.OCR for item in surface.objects)
            or any("home_city_label" in item.metadata for item in by_target.values()),
            "useful OCR facts must survive alongside camera-qualified objects",
        )
