"""OCR diagnostic snapshots preserve bounded read outcomes without new work."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
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
    OcrRequiredFieldStatus,
    OcrResult,
    OcrWord,
)


def _frame_ref() -> FrameRef:
    """Build one deterministic frame binding for the context under test."""

    return FrameRef(
        session_id="ocr-diagnostic-test",
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _result(text: str, *, bounds: Bounds) -> OcrResult:
    """Build one result with a line and word that can be compared by identity."""

    word = OcrWord(text, bounds, 0.9)
    return OcrResult(
        lines=(OcrLine(text, bounds, 0.9, words=(word,)),),
        words=(word,),
    )


class _RecordingBackend:
    """Return configured results while recording every bounded backend call."""

    def __init__(
        self,
        factory: Callable[[Image.Image, Bounds | None], OcrResult] | None = None,
        failures: list[Exception] | None = None,
    ) -> None:
        self.factory = factory or (lambda image, region: OcrResult(lines=(), words=()))
        self.failures = list(failures or ())
        self.calls: list[Image.Image] = []
        self.regions: list[Bounds | None] = []

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Record the owned backend input and return or raise its next outcome."""

        self.calls.append(image.copy())
        self.regions.append(region)
        if self.failures:
            raise self.failures.pop(0)
        return self.factory(image, region)


class OcrDiagnosticSnapshotTests(unittest.TestCase):
    """Validate immutable read history for bounded raw and preprocessed OCR."""

    def test_optional_required_fact_is_retained_on_each_context_read_path(self) -> None:
        """Carries semantic ownership into immutable raw and transformed read evidence."""

        image = Image.new("RGB", (120, 100), (1, 2, 3))
        regions = (
            Bounds(0, 0, 20, 20),
            Bounds(20, 0, 20, 20),
            Bounds(40, 0, 20, 20),
            Bounds(60, 0, 20, 20),
        )
        context = ObservationOcrContext(image, _RecordingBackend(), _frame_ref(), "rapid-v1")

        context.read_result(image, regions[0], required_fact="raw_fact")
        context.read_lines(image, regions[1], required_fact="line_fact")
        context.read_text(image, regions[2], required_fact="text_fact")
        context.read_preprocessed_result(
            image,
            regions[3],
            preprocessing_id="rgb-v1",
            prepare=lambda full_image, region: full_image.crop(
                (region.x, region.y, region.x + region.width, region.y + region.height)
            ),
            required_fact="preprocessed_fact",
        )

        self.assertEqual(
            [diagnostic.required_fact for diagnostic in context.read_diagnostics],
            ["raw_fact", "line_fact", "text_fact", "preprocessed_fact"],
        )

    def test_bounded_raw_result_identity_and_diagnostic_reads_do_no_work(self) -> None:
        image = Image.new("RGB", (80, 60), (15, 28, 68))
        region = Bounds(10, 12, 30, 20)
        expected = _result("bounded", bounds=Bounds(12, 14, 8, 6))
        backend = _RecordingBackend(factory=lambda _image, _region: expected)
        context = ObservationOcrContext(image, backend, _frame_ref(), "rapid-v1", max_entries=2)

        first = context.read_result(
            image,
            region,
            reuse_full_frame=False,
            purpose=OcrReadPurpose.CONTENT,
            detail="bounded-field",
        )
        before = context.metrics
        diagnostics = context.read_diagnostics
        after = context.metrics
        repeated = context.read_result(image, region, reuse_full_frame=False)

        self.assertIs(first, expected)
        self.assertIs(repeated, first)
        self.assertEqual(backend.regions, [region])
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(diagnostics[0].status, OcrReadStatus.ENGINE)
        self.assertEqual(diagnostics[0].region, region)
        self.assertIs(diagnostics[0].result, first)
        self.assertEqual(before.requests, 1)
        self.assertEqual(after, before)
        self.assertEqual(context.metrics.requests, 2)
        self.assertEqual(context.metrics.engine_calls, 1)
        self.assertEqual(context.read_diagnostics[1].status, OcrReadStatus.CACHE_HIT)
        self.assertIs(context.read_diagnostics[1].result, first)
        with self.assertRaises(FrozenInstanceError):
            diagnostics[0].result = None  # type: ignore[misc]

    def test_evicted_bounded_result_remains_in_diagnostic_history(self) -> None:
        image = Image.new("RGB", (100, 80))
        regions = (
            Bounds(0, 0, 20, 20),
            Bounds(20, 0, 20, 20),
            Bounds(40, 0, 20, 20),
        )
        results = iter(_result(f"read-{index}", bounds=Bounds(index, 1, 5, 5)) for index in range(1, 5))
        backend = _RecordingBackend(factory=lambda _image, _region: next(results))
        context = ObservationOcrContext(image, backend, _frame_ref(), "rapid-v1", max_entries=2)

        first = context.read_result(image, regions[0], reuse_full_frame=False)
        second = context.read_result(image, regions[1], reuse_full_frame=False)
        third = context.read_result(image, regions[2], reuse_full_frame=False)
        retried_first = context.read_result(image, regions[0], reuse_full_frame=False)
        before = context.metrics
        snapshots = context.read_diagnostics
        after = context.metrics

        self.assertIsNot(first, retried_first)
        self.assertEqual([item.result for item in snapshots], [first, second, third, retried_first])
        self.assertIs(snapshots[0].result, first)
        self.assertEqual([item.status for item in snapshots], [OcrReadStatus.ENGINE] * 4)
        self.assertEqual(len(backend.calls), 4)
        self.assertEqual(context.metrics.engine_calls, 4)
        self.assertEqual(after, before)

    def test_preprocessed_bounded_result_projects_once_and_reuses_snapshot(self) -> None:
        image = Image.new("RGB", (100, 80), (1, 2, 3))
        region = Bounds(20, 10, 30, 20)
        transformed_bounds = Bounds(10, 8, 20, 10)
        expected_bounds = Bounds(25, 14, 10, 5)
        raw_result = _result("scaled", bounds=transformed_bounds)
        backend = _RecordingBackend(factory=lambda _image, _region: raw_result)
        prepare_calls: list[tuple[Image.Image, Bounds]] = []

        def prepare(full_image: Image.Image, source_region: Bounds) -> Image.Image:
            prepare_calls.append((full_image, source_region))
            crop = full_image.crop(
                (
                    source_region.x,
                    source_region.y,
                    source_region.x + source_region.width,
                    source_region.y + source_region.height,
                )
            )
            return crop.resize((60, 40), resample=Image.Resampling.NEAREST)

        context = ObservationOcrContext(image, backend, _frame_ref(), "rapid-v1", max_entries=2)
        first = context.read_preprocessed_result(
            image,
            region,
            preprocessing_id="bounded-scale-v1",
            prepare=prepare,
            purpose=OcrReadPurpose.CONTENT,
            detail="scaled-field",
        )
        repeated = context.read_preprocessed_result(
            image,
            region,
            preprocessing_id="bounded-scale-v1",
            prepare=prepare,
        )
        self.assertIsNotNone(first)
        assert first is not None

        self.assertIsNot(first, raw_result)
        self.assertIs(repeated, first)
        self.assertEqual(len(prepare_calls), 1)
        self.assertIsNot(prepare_calls[0][0], image)
        self.assertEqual(prepare_calls[0][1], region)
        self.assertEqual([call.size for call in backend.calls], [(60, 40)])
        self.assertEqual(backend.regions, [None])
        self.assertEqual(first.lines[0].bounds, expected_bounds)
        self.assertEqual(first.words[0].bounds, expected_bounds)
        self.assertEqual(context.metrics.processed_pixel_area, 60 * 40)
        self.assertEqual(context.metrics.engine_calls, 1)
        self.assertEqual(
            [item.status for item in context.read_diagnostics],
            [OcrReadStatus.ENGINE, OcrReadStatus.CACHE_HIT],
        )
        self.assertTrue(all(item.result is first for item in context.read_diagnostics))

    def test_error_and_missing_diagnostics_have_no_result_and_retry_keeps_latest_result(self) -> None:
        image = Image.new("RGB", (80, 60))
        region = Bounds(5, 5, 20, 20)
        recovered = _result("recovered", bounds=Bounds(6, 6, 8, 6))
        failing_backend = _RecordingBackend(
            factory=lambda _image, _region: recovered,
            failures=[RuntimeError("temporary OCR failure")],
        )
        context = ObservationOcrContext(image, failing_backend, _frame_ref(), "rapid-v1", max_entries=2)

        with self.assertRaisesRegex(RuntimeError, "temporary OCR failure"):
            context.read_result(image, region, reuse_full_frame=False, purpose=OcrReadPurpose.GUARD)
        result = context.read_result(image, region, reuse_full_frame=False, purpose=OcrReadPurpose.GUARD)

        missing_backend = _RecordingBackend()
        missing_context = ObservationOcrContext(image, missing_backend, _frame_ref(), "rapid-v1", max_entries=2)
        missing = missing_context.read_preprocessed_result(
            image,
            region,
            preprocessing_id="optional-filter-v1",
            prepare=lambda _full_image, _region: None,
        )
        missing_repeat = missing_context.read_preprocessed_result(
            image,
            region,
            preprocessing_id="optional-filter-v1",
            prepare=lambda _full_image, _region: None,
        )
        before = missing_context.metrics
        diagnostics = missing_context.read_diagnostics
        after = missing_context.metrics

        self.assertIs(result, recovered)
        self.assertEqual(len(failing_backend.calls), 2)
        self.assertIsNone(context.read_diagnostics[0].result)
        self.assertEqual(context.read_diagnostics[0].status, OcrReadStatus.ERROR)
        self.assertIs(context.read_diagnostics[1].result, result)
        self.assertEqual(context.read_diagnostics[1].status, OcrReadStatus.ENGINE)
        self.assertIsNone(missing)
        self.assertIsNone(missing_repeat)
        self.assertEqual(len(missing_backend.calls), 0)
        self.assertEqual([item.status for item in diagnostics], [OcrReadStatus.MISSING, OcrReadStatus.MISSING])
        self.assertTrue(all(item.result is None for item in diagnostics))
        self.assertEqual(after, before)

    def test_required_field_parser_diagnostics_are_frame_scoped_and_do_no_ocr(self) -> None:
        """Records parser misses separately when the bounded OCR crop had text."""

        image = Image.new("RGB", (80, 60))
        region = Bounds(5, 5, 20, 20)
        backend = _RecordingBackend()
        context = ObservationOcrContext(image, backend, _frame_ref(), "rapid-v1")

        context.record_required_field_diagnostic(
            required_fact="world_coordinate_pair",
            status=OcrRequiredFieldStatus.INVALID,
            region=region,
            reason="invalid_value",
            detail="parser:world_coordinate_dialog_field",
        )

        self.assertEqual(backend.calls, [])
        diagnostics = context.required_field_diagnostics
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].required_fact, "world_coordinate_pair")
        self.assertEqual(diagnostics[0].status, OcrRequiredFieldStatus.INVALID)
        self.assertEqual(diagnostics[0].region, region)
        self.assertEqual(diagnostics[0].reason, "invalid_value")
        self.assertEqual(context.metrics.engine_calls, 0)

    def test_required_field_parser_retry_keeps_latest_outcome(self) -> None:
        """Allows a successful parser retry to clear an earlier parser miss."""

        image = Image.new("RGB", (80, 60))
        region = Bounds(5, 5, 20, 20)
        context = ObservationOcrContext(image, _RecordingBackend(), _frame_ref(), "rapid-v1")

        context.record_required_field_diagnostic(
            required_fact="world_coordinate_pair",
            status=OcrRequiredFieldStatus.INVALID,
            region=region,
            reason="invalid_value",
        )
        context.record_required_field_diagnostic(
            required_fact="world_coordinate_pair",
            status=OcrRequiredFieldStatus.PRESENT,
            region=region,
            reason="parsed",
        )

        self.assertEqual(
            [diagnostic.status for diagnostic in context.required_field_diagnostics],
            [OcrRequiredFieldStatus.INVALID, OcrRequiredFieldStatus.PRESENT],
        )


if __name__ == "__main__":
    unittest.main()
