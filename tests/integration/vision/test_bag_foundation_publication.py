"""Captured Bag foundation publication through both production observers.

Qualifies the shared V01 path on the supported Bag Resource layout: real
selector registry, packaged visual recognizer, production enricher and planner,
and the real RapidOCR backend. Both ``ObservationBuilder`` and
``NavigationPerception`` must agree on identity, measured controls, typed
Resource rows, and frame provenance, while content OCR stays demand-driven and
bounded.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
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
    ObservationOcrContext,
    OcrLine,
    OcrReadStatus,
    OcrResult,
    RapidOcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
MANUAL_ANNOTATIONS = FIXTURES / "manual_annotations.json"

# Independent visual identity published by the packaged "bag" profile.
_BAG_LAYOUT_ID = "bag"
_BAG_CONTROL_BOUNDS = {
    "bag.png": {
        UiElementId.PNC_BACK_BUTTON_TOP_LEFT: Bounds(25, 11, 52, 32),
        UiElementId.PNC_BAG_SUBTAB_RESOURCE: Bounds(0, 123, 107, 39),
    },
    "bag_current_testing.png": {
        UiElementId.PNC_BACK_BUTTON_TOP_LEFT: Bounds(42, 18, 86, 54),
        UiElementId.PNC_BAG_SUBTAB_RESOURCE: Bounds(0, 205, 178, 65),
    },
}

# Reviewed card content of the frozen reference capture bag.png. The fifth
# card ("10K Food (Safe)", Owned: 873) is visible but stays explicitly
# unresolved under real body OCR; no partial facts are invented for it.
_REFERENCE_BAG_ROWS: tuple[dict[str, Any] | None, ...] = (
    {"item_id": "food:1000:normal", "resource": "food", "amount": 1000, "owned": 35174, "action_point": (454, 208)},
    {"item_id": "food:2000:normal", "resource": "food", "amount": 2000, "owned": 1898, "action_point": (454, 339)},
    {"item_id": "food:5000:normal", "resource": "food", "amount": 5000, "owned": 228, "action_point": (454, 471)},
    {"item_id": "food:10000:normal", "resource": "food", "amount": 10000, "owned": 1131, "action_point": (454, 602)},
    None,
    {"item_id": "food:500000:normal", "resource": "food", "amount": 500000, "owned": 1, "action_point": (454, 891)},
)


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
            raise AssertionError("Bag content test reached RapidOCR without a strict crop")
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
) -> tuple[ObservationBuilder, NavigationPerception, list[ObservationOcrContext]]:
    """Wire both production publishers and retain each frame's OCR context."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(selector_registry=registry)
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )
    contexts: list[ObservationOcrContext] = []

    def tracked_context(screenshot: CapturedScreenshot) -> ObservationOcrContext:
        context = builder.create_ocr_context(screenshot)
        contexts.append(context)
        return context

    navigation = NavigationPerception(
        builder.visual_recognizer,
        enricher,
        ScreenClassifier(),
        tracked_context,
    )
    return builder, navigation, contexts


def _new_context(
    builder: ObservationBuilder,
    contexts: list[ObservationOcrContext],
    capture: CapturedScreenshot,
) -> ObservationOcrContext:
    """Create the frame-bound context through the builder factory and retain it."""

    context = builder.create_ocr_context(capture)
    contexts.append(context)
    return context


def _manual_rows(name: str) -> tuple[dict[str, Any], ...]:
    """Load the reviewed row annotations for one captured Bag image."""

    document = json.loads(MANUAL_ANNOTATIONS.read_text(encoding="utf-8"))
    sample = next(
        (entry for entry in document["samples"] if entry["image"] == name),
        None,
    )
    if sample is None or "rows" not in sample:
        raise AssertionError(f"manual_annotations.json has no reviewed rows for {name}")
    return tuple(sample["rows"])


class BagFoundationPublicationTests(unittest.TestCase):
    """Replayed Bag captures qualify the shared observation contract on both paths."""

    def _assert_bag_identity_and_controls(
        self,
        observation: Observation,
        capture: CapturedScreenshot,
        expected_controls: dict[UiElementId, Bounds],
    ) -> None:
        """Require independent Bag identity, a clear decision, and measured controls."""

        self.assertEqual(ScreenType.PNC_BAG, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertTrue(observation.decision.action_eligible)
        self.assertEqual(_BAG_LAYOUT_ID, observation.decision.layout_id)
        self.assertEqual(capture.frame_ref, observation.frame_ref)
        self.assertEqual(
            hashlib.sha256(capture.image.tobytes()).hexdigest(),
            observation.frame_fingerprint,
        )
        self.assertTrue(
            any(
                evidence.screen_type == ScreenType.PNC_BAG and evidence.layout_id == _BAG_LAYOUT_ID
                for evidence in observation.decision.evidence
            ),
            "independent visual anchor evidence must own the bag layout",
        )
        self.assertEqual(set(expected_controls), set(observation.visible_elements))
        for selector_id, bounds in expected_controls.items():
            element = observation.require(selector_id)
            self.assertEqual(bounds, element.bounds)
            self.assertEqual(bounds.center(), element.action_point)
            self.assertEqual(capture.frame_ref, element.frame_ref)
            self.assertEqual(ScreenType.PNC_BAG, element.source_screen)
            self.assertEqual(_BAG_LAYOUT_ID, element.source_layout_id)

    def _assert_complete_row(self, row: DetectedListEntry) -> None:
        """Require a COMPLETE row to carry measured, row-contained action geometry."""

        self.assertEqual(RowRecognitionStatus.COMPLETE, row.row_status)
        self.assertEqual(ListEntryKind.RESOURCE_ITEM, row.kind)
        self.assertTrue(row.title_text)
        self.assertIsNotNone(row.action_point)
        self.assertIsNotNone(row.action_bounds)
        assert row.action_bounds is not None and row.action_point is not None
        self.assertTrue(row.bounds.contains_bounds(row.action_bounds))
        self.assertTrue(row.action_bounds.contains_point(row.action_point))
        self.assertEqual(row.action_bounds.center(), row.action_point)

    def _assert_row_provenance(self, row: DetectedListEntry, capture: CapturedScreenshot) -> None:
        self.assertEqual(capture.frame_ref, row.frame_ref)
        self.assertEqual(ScreenType.PNC_BAG, row.source_screen)
        self.assertEqual(_BAG_LAYOUT_ID, row.source_layout_id)

    def test_reference_bag_capture_publishes_typed_inventory_on_both_paths(self) -> None:
        """The frozen bag.png reference yields the same reviewed rows on both publishers."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation, contexts = _wire(backend)
        capture = _capture("bag.png", session_id="v01-bag-foundation", capture_sequence=1)

        builder_context = _new_context(builder, contexts, capture)
        backend.bind(capture.image.size)
        observations = (
            builder.build(
                capture,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
                ocr_context=builder_context,
            ),
            navigation.build(capture, include_content=True),
        )
        builder_observation, navigation_observation = observations
        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_bag_identity_and_controls(
                    observation, capture, _BAG_CONTROL_BOUNDS["bag.png"],
                )
                rows = observation.list_entries
                self.assertEqual(len(_REFERENCE_BAG_ROWS), len(rows))
                for row, expected in zip(rows, _REFERENCE_BAG_ROWS, strict=True):
                    self._assert_row_provenance(row, capture)
                    if expected is None:
                        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, row.kind)
                        self.assertEqual(RowRecognitionStatus.UNREADABLE, row.row_status)
                        self.assertIsNone(row.action_point)
                        self.assertIsNone(row.action_bounds)
                        self.assertEqual(
                            "missing_or_ambiguous_title_or_count",
                            row.metadata["unresolved_reason"],
                        )
                        continue
                    self._assert_complete_row(row)
                    self.assertEqual(expected["item_id"], row.metadata["item_id"])
                    self.assertEqual(expected["resource"], row.metadata["resource"])
                    self.assertEqual(expected["amount"], row.metadata["amount"])
                    self.assertEqual(expected["owned"], row.metadata["owned"])
                    self.assertEqual(expected["action_point"], row.action_point)
        # Both publishers expose identical typed rows on the same frame.
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_validation_bag_capture_matches_reviewed_annotations_on_both_paths(self) -> None:
        """The independent 900x1600 validation capture matches manual_annotations rows."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation, contexts = _wire(backend)
        capture = _capture(
            "bag_current_testing.png",
            session_id="v01-bag-foundation-validation",
            capture_sequence=1,
        )
        annotated_rows = _manual_rows("bag_current_testing.png")

        builder_context = _new_context(builder, contexts, capture)
        backend.bind(capture.image.size)
        observations = (
            builder.build(
                capture,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
                ocr_context=builder_context,
            ),
            navigation.build(capture, include_content=True),
        )
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_bag_identity_and_controls(
                    observation, capture, _BAG_CONTROL_BOUNDS["bag_current_testing.png"],
                )
                rows = observation.list_entries
                self.assertEqual(len(annotated_rows), len(rows))
                for row, annotated in zip(rows, annotated_rows, strict=True):
                    with self.subTest(title=annotated["title"]):
                        self._assert_row_provenance(row, capture)
                        self._assert_complete_row(row)
                        self.assertEqual("resource_item", row.kind.value)
                        metadata = annotated["expected_metadata"]
                        self.assertEqual(metadata["item_id"], row.metadata["item_id"])
                        self.assertEqual(metadata["resource"], row.metadata["resource"])
                        self.assertEqual(metadata["amount"], row.metadata["amount"])
                        self.assertEqual(metadata["owned"], row.metadata["owned"])
                        card = Bounds(*annotated["card"])
                        use = Bounds(*annotated["Use"])
                        # The measured card and single-Use geometry stay inside
                        # the reviewed manual boxes within two pixels.
                        self.assertLessEqual(abs(row.bounds.x - card.x), 2)
                        self.assertLessEqual(abs(row.bounds.y - card.y), 2)
                        self.assertLessEqual(abs(row.bounds.width - card.width), 2)
                        self.assertLessEqual(abs(row.bounds.height - card.height), 2)
                        self.assertTrue(use.contains_point(row.action_point))
        self.assertEqual(observations[0].list_entries, observations[1].list_entries)

    def test_bag_content_is_demand_driven_and_frame_bounded(self) -> None:
        """Resource rows appear only when requested; every read is bounded once."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation, contexts = _wire(backend)
        capture = _capture("bag.png", session_id="v01-bag-demand", capture_sequence=1)

        # Unrequested observations keep Bag identity but skip body OCR entirely.
        backend.bind(capture.image.size)
        builder_context = _new_context(builder, contexts, capture)
        unrequested = (
            builder.build(capture, request=ObservationRequest.base(), ocr_context=builder_context),
            navigation.build(capture, include_content=False),
        )
        navigation_context = contexts[-1]
        for name, observation, context in (
            ("observation_builder", unrequested[0], builder_context),
            ("navigation_perception", unrequested[1], navigation_context),
        ):
            with self.subTest(publisher=name):
                self.assertEqual(ScreenType.PNC_BAG, observation.screen_type)
                self.assertEqual(_BAG_LAYOUT_ID, observation.decision.layout_id)
                self.assertEqual((), observation.list_entries)
                metrics = context.metrics
                self.assertEqual(0, metrics.requests)
                self.assertEqual(0, metrics.engine_calls)
                self.assertEqual((), context.read_diagnostics)
        self.assertEqual([], backend.calls)

        # Requested content performs real bounded content/body reads once per key.
        request = ObservationRequest.source_screen_retry(ScreenType.PNC_BAG)
        requested_observations: list[Observation] = []
        backend.bind(capture.image.size)
        builder_context = _new_context(builder, contexts, capture)
        requested_observations.append(
            builder.build(capture, request=request, ocr_context=builder_context)
        )
        builder_backend_calls = list(backend.calls)
        backend.bind(capture.image.size)
        requested_observations.append(navigation.build(capture, include_content=True))
        navigation_context = contexts[-1]
        navigation_backend_calls = list(backend.calls)

        for name, observation, context, backend_calls in (
            ("observation_builder", requested_observations[0], builder_context, builder_backend_calls),
            ("navigation_perception", requested_observations[1], navigation_context, navigation_backend_calls),
        ):
            with self.subTest(publisher=name):
                self.assertTrue(observation.list_entries)
                self.assertTrue(context.bounded_regions_required)
                self.assertIs(capture.image, context.image)
                self.assertEqual(capture.frame_ref, context.frame_ref)
                metrics = context.metrics
                diagnostics = context.read_diagnostics
                self.assertEqual(metrics.requests, len(diagnostics))
                self.assertEqual(metrics.engine_calls, len(backend_calls))
                self.assertEqual(0, metrics.fullframe_reuses)
                self.assertLess(metrics.processed_pixel_area, capture.image.width * capture.image.height)
                whole = Bounds(0, 0, *capture.image.size)
                for diagnostic in diagnostics:
                    self.assertIsNotNone(diagnostic.region)
                    self.assertNotEqual(whole, diagnostic.region)
                self.assertTrue(
                    any(
                        diagnostic.required_fact == "resource_inventory_rows"
                        and diagnostic.status == OcrReadStatus.ENGINE
                        for diagnostic in diagnostics
                    ),
                    "requested Bag content must include the planned body read",
                )
                # The backend sees each exact region/preprocessing key at most
                # once; repeats are served from the frame cache instead.
                self.assertEqual(len(backend_calls), len(set(backend_calls)))

        # A second build on the same frame context reuses cached reads.
        initial_metrics = builder_context.metrics
        backend.bind(capture.image.size)
        repeat = builder.build(capture, request=request, ocr_context=builder_context)
        metrics = builder_context.metrics
        self.assertEqual(initial_metrics.engine_calls, metrics.engine_calls)
        self.assertEqual([], backend.calls)
        self.assertGreater(metrics.cache_hits, initial_metrics.cache_hits)
        self.assertEqual(requested_observations[0].list_entries, repeat.list_entries)
        self.assertEqual(
            dict(requested_observations[0].visible_elements),
            dict(repeat.visible_elements),
        )

    def test_unrelated_home_frame_publishes_no_bag_controls_or_rows(self) -> None:
        """A real Home frame after Bag work acquires no stale Bag facts."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation, contexts = _wire(backend)
        session = "v01-bag-foundation"
        bag_capture = _capture("bag_current_testing.png", session_id=session, capture_sequence=1)
        backend.bind(bag_capture.image.size)
        builder.build(
            bag_capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
            ocr_context=_new_context(builder, contexts, bag_capture),
        )
        navigation.build(bag_capture, include_content=True)

        home_capture = _capture("home_city_core.png", session_id=session, capture_sequence=2)
        backend.bind(home_capture.image.size)
        home_builder_context = _new_context(builder, contexts, home_capture)
        home_observations = (
            builder.build(
                home_capture,
                request=ObservationRequest.full_runtime_default(),
                ocr_context=home_builder_context,
            ),
            navigation.build(home_capture, include_content=True),
        )
        home_navigation_context = contexts[-1]
        for name, observation, context in (
            ("observation_builder", home_observations[0], home_builder_context),
            ("navigation_perception", home_observations[1], home_navigation_context),
        ):
            with self.subTest(publisher=name):
                self.assertEqual(ScreenType.PNC_HOME_CITY, observation.screen_type)
                self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                self.assertEqual("home_city", observation.decision.layout_id)
                self.assertEqual(home_capture.frame_ref, observation.frame_ref)
                self.assertNotEqual(
                    hashlib.sha256(bag_capture.image.tobytes()).hexdigest(),
                    observation.frame_fingerprint,
                )
                self.assertFalse(
                    any(
                        selector_id.value.startswith("PNC_BAG_")
                        for selector_id in observation.visible_elements
                    ),
                    "no Bag-owned selector may surface on the Home frame",
                )
                self.assertEqual((), observation.list_entries)
                for element in observation.visible_elements.values():
                    self.assertEqual(home_capture.frame_ref, element.frame_ref)
                    self.assertEqual(ScreenType.PNC_HOME_CITY, element.source_screen)
                self.assertFalse(
                    any(
                        diagnostic.required_fact == "resource_inventory_rows"
                        for diagnostic in context.read_diagnostics
                    ),
                    "the Bag body read must not run on an unrelated frame",
                )


if __name__ == "__main__":
    unittest.main()
