"""Slot-tagged measured building bodies through both production publishers.

Replays the authored RGBA 900x1600 slot-body fixtures through
``ObservationBuilder`` and ``NavigationPerception`` exactly as captured: the
image is handed to the builders as ``source.copy()`` at its native RGBA mode --
no RGB pre-conversion -- and both publishers must localize the camera proof,
publish the Blacksmith body tagged with the observed slot 12 and its measured
candidate action geometry, preserve OCR facts, and agree object-for-object.
Unsupported views must never invent the movable body.  Only declared
private-chat HUD rows are masked in the fixtures; every other pixel is
source-identical.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraStatus
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
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


FIXTURES = TEST_DATA_ROOT / "home_city_slot_bodies"

# Reviewed measured results for each authored fixture: expected atlas-to-
# reference translation and the camera-qualified targets with their observed
# slot and measured action point in fixture pixels.
_EXPECTED = {
    "home_city_blacksmith_slot12_f1_20260922.png": {
        "translation": (-530, -391),
        "targets": {
            HomeCityObjectId.INSTITUTE: (HomeCitySlotSelector(9), (726, 640)),
            HomeCityObjectId.TOWER_OF_TRIAL: (None, (301, 1101)),
            HomeCityObjectId.BLACKSMITH: (HomeCitySlotSelector(12), (712, 1312)),
        },
    },
    "home_city_blacksmith_slot12_f2_20260922.png": {
        "translation": (-530, -874),
        "targets": {
            HomeCityObjectId.TOWER_OF_TRIAL: (None, (301, 618)),
            HomeCityObjectId.BLACKSMITH: (HomeCitySlotSelector(12), (712, 829)),
        },
    },
    "home_city_baseline_f0_20260922.png": {
        "translation": (-532, 222),
        "targets": {
            HomeCityObjectId.INSTITUTE: (HomeCitySlotSelector(9), (724, 1253)),
        },
    },
    "home_city_pan2_f5_20260922.png": {
        "translation": (-1632, -718),
        "targets": {
            HomeCityObjectId.CAMPAIGN: (None, (451, 404)),
        },
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
            raise AssertionError("Slot-body test reached RapidOCR without a strict crop")
        return self.delegate.read_result(image, region)

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _capture(name: str, *, session_id: str, capture_sequence: int) -> CapturedScreenshot:
    """Load an authored fixture at native RGBA -- a copy, never an RGB conversion."""

    with Image.open(FIXTURES / name) as source:
        if source.mode != "RGBA" or source.size != (900, 1600):
            raise AssertionError(
                f"slot-body fixture {name} must stay authored RGBA 900x1600, "
                f"got {source.mode} {source.size}"
            )
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


class HomeCitySlotBodyPublisherTests(unittest.TestCase):
    """Both publishers emit identical slot-tagged bodies from the same frame."""

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

    def _assert_slot_body_publication(
        self,
        observation: Observation,
        capture: CapturedScreenshot,
        expected_translation: tuple[int, int],
        expected_targets: dict[HomeCityObjectId, tuple[HomeCitySlotSelector | None, tuple[int, int]]],
        *,
        merged_label_target: HomeCityObjectId | None = None,
    ) -> None:
        """Require localized proof plus slot-tagged, provenance-bound objects."""

        self.assertEqual("RGBA", capture.image.mode)
        self.assertEqual((900, 1600), capture.image.size)
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

        published = tuple(
            item
            for item in surface.objects
            if home_city_object_id_from_metadata(item.metadata) is not None
            and item.source_kind is SpatialObjectSourceKind.TEMPLATE
        )
        by_target: dict[HomeCityObjectId, list] = {}
        for item in published:
            by_target.setdefault(home_city_object_id_from_metadata(item.metadata), []).append(item)
        for target, (slot, action_point) in expected_targets.items():
            with self.subTest(target=target.value):
                candidates = [
                    item for item in by_target.get(target, []) if item.home_city_slot == slot
                ]
                self.assertEqual(1, len(candidates), f"{target.value} must publish once at slot {slot}")
                item = candidates[0]
                self.assertEqual(action_point, item.action_point)
                self.assertIsNotNone(item.action_bounds)
                assert item.action_bounds is not None
                self.assertTrue(item.bounds.contains_bounds(item.action_bounds))
                self.assertTrue(item.action_bounds.contains_point(item.action_point))
                self.assertEqual("camera_template", item.metadata["detection_source"])
                if slot is not None:
                    self.assertEqual(slot.slot_index, item.metadata["home_city_slot_index"])
                self.assertEqual(capture.frame_ref, item.frame_ref)
                self.assertEqual(ScreenType.PNC_HOME_CITY, item.source_screen)
                self.assertEqual(observation.decision.layout_id, item.source_layout_id)
        if merged_label_target is not None:
            merged = [
                item
                for item in by_target.get(merged_label_target, [])
                if "home_city_label" in item.metadata
            ]
            self.assertEqual(
                1,
                len(merged),
                f"{merged_label_target.value} must carry its unambiguously merged OCR label",
            )
        self.assertTrue(
            any(item.source_kind == SpatialObjectSourceKind.OCR for item in surface.objects)
            or any("home_city_label" in item.metadata for item in published),
            "useful OCR facts must survive alongside camera-qualified objects",
        )

    def test_f2_publishes_blacksmith_slot_12_body_on_both_paths(self) -> None:
        """The post-Tower view localizes and both publishers tag slot 12."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_blacksmith_slot12_f2_20260922.png",
            session_id="v44-slot-body-f2",
            capture_sequence=62,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_blacksmith_slot12_f2_20260922.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_slot_body_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                    merged_label_target=HomeCityObjectId.BLACKSMITH,
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_f1_publishes_the_same_slot_12_binding_independently(self) -> None:
        """The independent post-Institute view agrees on the slot-12 measurement."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_blacksmith_slot12_f1_20260922.png",
            session_id="v44-slot-body-f1",
            capture_sequence=47,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_blacksmith_slot12_f1_20260922.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_slot_body_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_baseline_localizes_without_inventing_the_movable_body(self) -> None:
        """f0 localizes through fixed groups but every Blacksmith candidate is offscreen."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_baseline_f0_20260922.png",
            session_id="v44-slot-body-f0",
            capture_sequence=30,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_baseline_f0_20260922.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_slot_body_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
                surface = observation.spatial_surface
                assert surface is not None
                self.assertFalse(any(
                    home_city_object_id_from_metadata(item.metadata) is HomeCityObjectId.BLACKSMITH
                    and item.source_kind is SpatialObjectSourceKind.TEMPLATE
                    for item in surface.objects
                ), "offscreen movable candidates must never publish")
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)

    def test_panned_view_never_claims_another_occupants_body(self) -> None:
        """f5 localizes while slot 13 holds Alliance Hall; the crop must not claim it."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_pan2_f5_20260922.png",
            session_id="v44-slot-body-f5",
            capture_sequence=69,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        expected = _EXPECTED["home_city_pan2_f5_20260922.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_slot_body_publication(
                    observation,
                    capture,
                    expected["translation"],
                    expected["targets"],
                )
                surface = observation.spatial_surface
                assert surface is not None
                self.assertFalse(any(
                    home_city_object_id_from_metadata(item.metadata) is HomeCityObjectId.BLACKSMITH
                    and item.source_kind is SpatialObjectSourceKind.TEMPLATE
                    for item in surface.objects
                ), "wrong-slot content must never claim the Blacksmith target")
        self.assertEqual(observations[0].spatial_surface, observations[1].spatial_surface)


if __name__ == "__main__":
    unittest.main()
