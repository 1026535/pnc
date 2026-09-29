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
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    HOME_CITY_HUD_SAFE_MAX_Y_RATIO,
)
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
    OcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


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

    def test_wall_and_native_zoom_goddess_reach_both_publishers(self) -> None:
        for sequence, (root, name, identity, slot, translation, point) in enumerate((
            (TEST_DATA_ROOT / "home_city_slot_bodies", "home_city_wall_slot2_f6_20260922.png",
             HomeCityObjectId.WALL, 2, (-1635, -718), (118, 983)),
            (FIXTURES, "home_city_native_zoom_holdout_20260922.png",
             HomeCityObjectId.GODDESS_STATUE, 15, (-603, 78), (462, 1201)),
        )):
            with self.subTest(identity=identity):
                backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
                builder, navigation = _wire(backend)
                capture = _capture(name, session_id="v44-ordinary-bodies",
                                   capture_sequence=sequence, fixture_root=root)
                self.assertEqual(("RGBA", (900, 1600)), (capture.image.mode, capture.image.size))
                observations = self._build_both(builder, navigation, backend, capture)
                for observation in observations:
                    self._assert_camera_publication(observation, capture, translation, {identity: point})
                    bodies = [item for item in observation.spatial_surface.objects
                              if home_city_object_id_from_metadata(item.metadata) == identity]
                    self.assertEqual(1, len(bodies))
                    self.assertEqual(slot, bodies[0].home_city_slot.slot_index)
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
        (456,1057) with full provenance, and invent no other target.
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
                    {HomeCityObjectId.WALL},
                    {
                        home_city_object_id_from_metadata(item.metadata)
                        for item in surface.objects
                        if item.source_kind is SpatialObjectSourceKind.TEMPLATE
                    },
                    "the corridor view must not invent any other camera target",
                )
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
