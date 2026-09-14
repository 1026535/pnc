"""Tests for the frame-local bounded OCR policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
import unittest

from PIL import Image

from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadPurpose,
    OcrReadStatus,
    OcrResult,
)


def _frame_ref(sequence: int = 1) -> FrameRef:
    """Build deterministic capture provenance for one context."""

    return FrameRef(
        session_id="bounded-test-session",
        session_epoch=1,
        capture_sequence=sequence,
        input_sequence=0,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@dataclass(slots=True)
class _RecordingBackend:
    """Records backend work and returns a configured OCR result."""

    factory: Callable[[Image.Image, Bounds | None], OcrResult] = (
        lambda _image, _region: OcrResult(lines=(), words=())
    )
    calls: list[tuple[tuple[int, int], Bounds | None]] | None = None

    def __post_init__(self) -> None:
        """Initialize the mutable call log without sharing it between tests."""

        self.calls = []

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Record one request and return its configured result."""

        assert self.calls is not None
        self.calls.append((image.size, region))
        return self.factory(image, region)


class BoundedObservationOcrContextTests(unittest.TestCase):
    """Validate the one-way policy at every context OCR entry point."""

    def test_legacy_context_keeps_full_frame_api_until_policy_is_enabled(self) -> None:
        """Generic callers can retain the existing full-frame API before opting in."""

        image = Image.new("RGB", (80, 60))
        backend = _RecordingBackend()
        context = ObservationOcrContext(image, backend, _frame_ref(), "bounded-test")

        context.read_result(image)

        self.assertFalse(context.bounded_regions_required)
        self.assertEqual(backend.calls, [((80, 60), None)])

    def test_policy_rejects_missing_and_whole_regions_without_backend_or_cache_work(self) -> None:
        """Raw, line, text, and preprocessed APIs reject unbounded requests first."""

        image = Image.new("RGB", (80, 60))
        backend = _RecordingBackend()
        context = ObservationOcrContext(image, backend, _frame_ref(), "bounded-test")
        context.require_bounded_regions()
        whole = Bounds(0, 0, 80, 60)

        calls = (
            lambda: context.read_result(image),
            lambda: context.read_result(image, whole),
            lambda: context.read_lines(image),
            lambda: context.read_lines(image, whole),
            lambda: context.read_text(image, whole),
            lambda: context.read_preprocessed_result(
                image,
                None,  # type: ignore[arg-type]
                preprocessing_id="bounded-test-filter",
                prepare=lambda full_image, _region: full_image,
            ),
            lambda: context.read_preprocessed_result(
                image,
                whole,
                preprocessing_id="bounded-test-filter",
                prepare=lambda full_image, _region: full_image,
            ),
        )

        for call in calls:
            with self.subTest(call=call), self.assertRaisesRegex(ValueError, "Bounded OCR policy"):
                call()

        self.assertEqual(backend.calls, [])
        self.assertEqual(context.metrics.engine_calls, 0)
        self.assertEqual(context.read_diagnostics, ())

    def test_bounded_reads_keep_cache_and_native_region_contract(self) -> None:
        """A strict crop still supports successful empty results and cache reuse."""

        image = Image.new("RGB", (80, 60))
        region = Bounds(10, 10, 20, 15)
        backend = _RecordingBackend(
            factory=lambda _image, _region: OcrResult(
                lines=(OcrLine("bounded", Bounds(12, 12, 8, 5), 0.9),),
                words=(),
            )
        )
        context = ObservationOcrContext(image, backend, _frame_ref(), "bounded-test")
        context.require_bounded_regions()

        first = context.read_result(image, region)
        second = context.read_result(image, region)

        self.assertIs(first, second)
        self.assertEqual(backend.calls, [((80, 60), region)])
        self.assertEqual(context.metrics.engine_calls, 1)
        self.assertEqual(context.metrics.cache_hits, 1)
        self.assertEqual(
            [read.status for read in context.read_diagnostics],
            [OcrReadStatus.ENGINE, OcrReadStatus.CACHE_HIT],
        )

    def test_policy_rejects_preexisting_full_frame_evidence_but_allows_missing_diagnostic(self) -> None:
        """Only acquired full-frame evidence blocks the one-way policy transition."""

        image = Image.new("RGB", (80, 60))
        acquired_backend = _RecordingBackend()
        acquired_context = ObservationOcrContext(image, acquired_backend, _frame_ref(), "bounded-test")
        acquired_context.read_result(image)

        with self.assertRaisesRegex(ValueError, "full-frame OCR evidence"):
            acquired_context.require_bounded_regions()
        self.assertFalse(acquired_context.bounded_regions_required)

        missing_backend = _RecordingBackend()
        missing_context = ObservationOcrContext(image, missing_backend, _frame_ref(), "bounded-test")
        missing_context.record_diagnostic(
            purpose=OcrReadPurpose.CONTENT,
            status=OcrReadStatus.MISSING,
            region=None,
            detail="optional_full_frame_probe_not_applicable",
        )
        missing_context.require_bounded_regions()
        missing_context.read_result(image, Bounds(0, 0, 20, 20))

        self.assertTrue(missing_context.bounded_regions_required)
        self.assertEqual(missing_backend.calls, [((80, 60), Bounds(0, 0, 20, 20))])

    def test_explicit_whole_viewport_evidence_rejects_policy_activation(self) -> None:
        """Raw and preprocessed whole-viewport results count as acquired full-frame evidence."""

        image = Image.new("RGB", (80, 60))
        whole = Bounds(0, 0, 80, 60)
        for mode in ("raw", "preprocessed"):
            with self.subTest(mode=mode):
                backend = _RecordingBackend()
                context = ObservationOcrContext(image, backend, _frame_ref(), "bounded-test")
                if mode == "raw":
                    context.read_result(image, whole)
                else:
                    context.read_preprocessed_result(
                        image,
                        whole,
                        preprocessing_id="whole-viewport-test",
                        prepare=lambda full_image, _region: full_image,
                    )

                with self.assertRaisesRegex(ValueError, "full-frame OCR evidence"):
                    context.require_bounded_regions()

                self.assertFalse(context.bounded_regions_required)
                self.assertEqual(len(backend.calls), 1)

    def test_foreign_capture_or_frame_is_rejected_before_bounded_policy(self) -> None:
        """Capture provenance remains the first validation even for unbounded requests."""

        image = Image.new("RGB", (80, 60))
        backend = _RecordingBackend()
        context = ObservationOcrContext(image, backend, _frame_ref(), "bounded-test")
        context.require_bounded_regions()
        foreign_image = Image.new("RGB", image.size)

        with self.assertRaisesRegex(ValueError, "different from its captured frame"):
            context.read_result(foreign_image)
        with self.assertRaisesRegex(ValueError, "different frame provenance"):
            context.validate_capture(image, _frame_ref(2))

        self.assertEqual(backend.calls, [])
        self.assertEqual(context.metrics.engine_calls, 0)

    def test_preprocessing_cannot_return_full_capture_as_a_bounded_source(self) -> None:
        """A bounded request cannot bypass policy by returning the full source image."""

        image = Image.new("RGB", (80, 60))
        backend = _RecordingBackend()
        context = ObservationOcrContext(image, backend, _frame_ref(), "bounded-test")
        context.require_bounded_regions()
        prepare_calls = 0

        def prepare(full_image: Image.Image, _region: Bounds) -> Image.Image:
            nonlocal prepare_calls
            prepare_calls += 1
            return full_image

        with self.assertRaisesRegex(ValueError, "full-capture dimensions"):
            context.read_preprocessed_result(
                image,
                Bounds(10, 10, 20, 15),
                preprocessing_id="bounded-test-filter",
                prepare=prepare,
            )

        self.assertEqual(prepare_calls, 1)
        self.assertEqual(backend.calls, [])
        self.assertEqual(context.metrics.engine_calls, 0)


if __name__ == "__main__":
    unittest.main()
