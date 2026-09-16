"""OCR context tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Callable
import unittest
from unittest import mock

from PIL import Image

from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    OcrLine,
    OcrResult,
    OcrTextOrientation,
    OcrWord,
    ObservationOcrContext,
    RapidOcrService,
)


def _frame_ref(sequence: int = 1) -> FrameRef:
    """Builds deterministic provenance for one offline context test."""

    return FrameRef(
        session_id="test-session",
        session_epoch=1,
        capture_sequence=sequence,
        input_sequence=0,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _line(
    text: str,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    words: tuple[OcrWord, ...] = (),
) -> OcrLine:
    """Builds one concise OCR line fixture."""

    return OcrLine(text=text, bounds=Bounds(x, y, width, height), confidence=0.9, words=words)


class _RecordingOcrBackend:
    """Records owned backend images and optionally raises deterministic failures."""

    def __init__(
        self,
        factory: Callable[[Image.Image, Bounds | None], OcrResult] | None = None,
        failures: list[Exception] | None = None,
    ) -> None:
        self.factory = factory or (lambda image, region: OcrResult(lines=(), words=()))
        self.failures = list(failures or [])
        self.calls: list[Image.Image] = []
        self.regions: list[Bounds | None] = []
        self.orientations: list[OcrTextOrientation] = []

    def read_result(
        self, image: Image.Image, region: Bounds | None = None,
        *, orientation: OcrTextOrientation = OcrTextOrientation.AUTO,
    ) -> OcrResult:
        """Records one backend invocation and returns its configured result."""

        self.calls.append(image.copy())
        self.regions.append(region)
        self.orientations.append(orientation)
        if self.failures:
            raise self.failures.pop(0)
        return self.factory(image, region)


class ObservationOcrContextTests(unittest.TestCase):
    """Validates frame ownership, cache semantics, projection and metrics."""

    def test_a_b_a_reuses_only_the_matching_region_and_pins_full_frame(self) -> None:
        image = Image.new("RGB", (100, 80), (15, 28, 68))
        backend = _RecordingOcrBackend(
            factory=lambda image, region: OcrResult(
                lines=(_line(f"{image.width}x{image.height}", x=1, y=2, width=5, height=6),),
                words=(),
            )
        )
        context = ObservationOcrContext(image, backend, _frame_ref(), "rapid-v1", max_entries=3)
        first_region = Bounds(0, 0, 20, 20)
        second_region = Bounds(10, 10, 20, 20)

        first = context.read_result(image, first_region, reuse_full_frame=False)
        context.read_result(image, second_region, reuse_full_frame=False)
        repeated = context.read_result(image, first_region, reuse_full_frame=False)

        self.assertIs(first, repeated)
        self.assertEqual([call.size for call in backend.calls], [(100, 80), (100, 80)])
        self.assertEqual(backend.regions, [first_region, second_region])
        self.assertEqual(context.metrics.engine_calls, 2)

    def test_orientation_separates_raw_preprocessed_and_full_frame_cache(self) -> None:
        image = Image.new("RGB", (100, 80))
        backend = _RecordingOcrBackend(factory=lambda image, region: OcrResult(
            lines=(_line("Output I", x=2, y=2, width=8, height=6),), words=(),
        ))
        context = ObservationOcrContext(image, backend, _frame_ref(), "rapid-v3")
        region = Bounds(10, 20, 40, 30)
        context.read_result(image)
        upright = context.read_result(image, region, orientation=OcrTextOrientation.UPRIGHT)
        self.assertIs(upright.lines, context.read_lines(
            image, region, orientation=OcrTextOrientation.UPRIGHT,
        ))
        # The default full-frame result cannot answer an upright request.
        self.assertEqual(2, len(backend.calls))
        context.read_result(image, region)
        self.assertEqual(2, len(backend.calls))
        for orientation in OcrTextOrientation:
            prepared = context.read_preprocessed_result(
                image, region, preprocessing_id="double",
                prepare=lambda image, roi: image.crop((
                    roi.x, roi.y, roi.x + roi.width, roi.y + roi.height,
                )).resize((80, 60)), orientation=orientation,
            )
            self.assertEqual(Bounds(11, 21, 4, 3), prepared.lines[0].bounds)
            self.assertIs(prepared, context.read_preprocessed_result(
                image, region, preprocessing_id="double",
                prepare=lambda image, roi: self.fail("cached preparation repeated"),
                orientation=orientation,
            ))
        self.assertEqual([
            OcrTextOrientation.AUTO, OcrTextOrientation.UPRIGHT,
            OcrTextOrientation.AUTO, OcrTextOrientation.UPRIGHT,
        ], backend.orientations)

    def test_valid_empty_result_is_cached(self) -> None:
        image = Image.new("RGB", (20, 20))
        backend = _RecordingOcrBackend()
        context = ObservationOcrContext(image, backend, None, "rapid-v1")

        first = context.read_result(image)
        second = context.read_result(image)

        self.assertIs(first, second)
        self.assertEqual(first, OcrResult(lines=(), words=()))
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(context.metrics.cache_hits, 1)

    def test_backend_failures_are_retried_and_not_cached(self) -> None:
        image = Image.new("RGB", (20, 20))
        backend = _RecordingOcrBackend(failures=[RuntimeError("temporary")])
        context = ObservationOcrContext(image, backend, None, "rapid-v1")

        with self.assertRaisesRegex(RuntimeError, "temporary"):
            context.read_result(image)
        result = context.read_result(image)

        self.assertEqual(result, OcrResult(lines=(), words=()))
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(context.metrics.engine_calls, 2)
        self.assertEqual(context.metrics.cache_hits, 0)

    def test_contexts_do_not_reuse_same_sized_captures_and_validate_identity(self) -> None:
        first_image = Image.new("RGB", (20, 20), (1, 2, 3))
        second_image = Image.new("RGB", (20, 20), (4, 5, 6))
        first_backend = _RecordingOcrBackend()
        second_backend = _RecordingOcrBackend()
        first_context = ObservationOcrContext(first_image, first_backend, _frame_ref(1), "rapid-v1")
        second_context = ObservationOcrContext(
            second_image,
            second_backend,
            _frame_ref(2),
            "rapid-v1",
        )

        first_context.read_result(first_image)
        second_context.read_result(second_image)

        with self.assertRaises(ValueError):
            first_context.read_result(second_image)
        with self.assertRaises(ValueError):
            first_context.validate_capture(first_image, _frame_ref(2))
        with self.assertRaises(ValueError):
            first_context.validate_capture(None, None)
        self.assertEqual(len(first_backend.calls), 1)
        self.assertEqual(len(second_backend.calls), 1)

    def test_context_bindings_are_read_only_after_construction(self) -> None:
        image = Image.new("RGB", (20, 20))
        backend = _RecordingOcrBackend()
        context = ObservationOcrContext(image, backend, _frame_ref(), "rapid-v1", max_entries=3)

        with self.assertRaises(AttributeError):
            context.backend = _RecordingOcrBackend()  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            context.frame_ref = None  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            context.backend_revision = "changed"  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            context.max_entries = 1  # type: ignore[misc]

        self.assertIs(context.backend, backend)
        self.assertEqual(context.frame_ref, _frame_ref())
        self.assertEqual(context.backend_revision, "rapid-v1")
        self.assertEqual(context.max_entries, 3)

    def test_rejects_reserved_raw_preprocessing_id_without_poisoning_raw_cache(self) -> None:
        image = Image.new("RGB", (20, 20))
        backend = _RecordingOcrBackend()
        context = ObservationOcrContext(image, backend, None, "rapid-v1")

        with self.assertRaisesRegex(ValueError, "reserved"):
            context.read_preprocessed_result(
                image,
                Bounds(0, 0, 10, 10),
                preprocessing_id="__raw__",
                prepare=lambda full_image, region: full_image,
            )

        context.read_result(image)
        self.assertEqual(len(backend.calls), 1)

    def test_rejects_empty_images_and_non_integer_or_invalid_regions(self) -> None:
        backend = _RecordingOcrBackend()
        for size in ((0, 20), (20, 0)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                ObservationOcrContext(Image.new("RGB", size), backend, None, "rapid-v1")

        image = Image.new("RGB", (20, 20))
        context = ObservationOcrContext(image, backend, None, "rapid-v1")
        for region in (
            Bounds(0.0, 0, 10, 10),  # type: ignore[arg-type]
            Bounds(0, 0, True, 10),  # type: ignore[arg-type]
            Bounds(0, 0, 0, 10),
            Bounds(15, 15, 10, 10),
        ):
            with self.subTest(region=region), self.assertRaises((TypeError, ValueError)):
                context.read_result(image, region)

    def test_owned_snapshot_is_stable_when_original_pixels_change(self) -> None:
        image = Image.new("RGB", (20, 20), (1, 2, 3))
        backend = _RecordingOcrBackend(
            factory=lambda image, region: OcrResult(
                lines=(_line(str(image.getpixel((0, 0))), x=0, y=0, width=3, height=3),),
                words=(),
            )
        )
        context = ObservationOcrContext(image, backend, None, "rapid-v1")
        image.putpixel((0, 0), (9, 8, 7))

        result = context.read_result(image)

        self.assertEqual(result.lines[0].text, "(1, 2, 3)")
        self.assertEqual(backend.calls[0].getpixel((0, 0)), (1, 2, 3))

    def test_full_frame_reuse_keeps_only_whole_lines_and_words_with_global_bounds(self) -> None:
        image = Image.new("RGB", (100, 100))
        whole_word = OcrWord("inside", Bounds(15, 15, 8, 5), 0.9)
        clipped_word = OcrWord("clipped", Bounds(35, 15, 10, 5), 0.9)
        backend = _RecordingOcrBackend(
            factory=lambda image, region: OcrResult(
                lines=(
                    _line("inside", x=12, y=12, width=20, height=12, words=(whole_word,)),
                    _line("clipped", x=35, y=12, width=15, height=12, words=(clipped_word,)),
                ),
                words=(whole_word, clipped_word),
            )
        )
        context = ObservationOcrContext(image, backend, None, "rapid-v1")
        context.read_result(image)

        result = context.read_result(image, Bounds(10, 10, 30, 30))

        self.assertEqual(tuple(line.text for line in result.lines), ("inside",))
        self.assertEqual(tuple(word.text for word in result.words), ("inside",))
        self.assertEqual(result.lines[0].bounds, Bounds(12, 12, 20, 12))
        self.assertEqual(context.metrics.fullframe_reuses, 1)
        self.assertEqual(context.metrics.engine_calls, 1)

    def test_raw_roi_preserves_backend_region_contract_and_global_coordinates(self) -> None:
        image = Image.new("RGB", (100, 100))
        region = Bounds(40, 50, 20, 20)
        global_word = OcrWord("crop", Bounds(42, 53, 5, 4), 0.8)
        backend = _RecordingOcrBackend(
            factory=lambda image, region: OcrResult(
                lines=(_line("crop", x=42, y=53, width=8, height=6, words=(global_word,)),),
                words=(global_word,),
            )
        )
        context = ObservationOcrContext(image, backend, None, "rapid-v1")

        result = context.read_result(image, region, reuse_full_frame=False)

        self.assertEqual(backend.calls[0].size, (100, 100))
        self.assertEqual(backend.regions, [region])
        self.assertEqual(result.lines[0].bounds, Bounds(42, 53, 8, 6))
        self.assertEqual(result.words[0].bounds, Bounds(42, 53, 5, 4))
        self.assertEqual(context.metrics.processed_pixel_area, region.width * region.height)

    def test_preprocessed_variant_projects_once_and_prepare_gets_fresh_copy(self) -> None:
        image = Image.new("RGB", (100, 100), (1, 2, 3))
        callback_images: list[Image.Image] = []
        local_word = OcrWord("scaled", Bounds(6, 9, 12, 15), 0.8)
        backend = _RecordingOcrBackend(
            factory=lambda image, region: OcrResult(
                lines=(_line("scaled", x=6, y=9, width=12, height=15, words=(local_word,)),),
                words=(local_word,),
            )
        )

        def prepare(full_image: Image.Image, region: Bounds) -> Image.Image:
            callback_images.append(full_image)
            self.assertEqual(full_image.size, (100, 100))
            crop = full_image.crop(
                (region.x, region.y, region.x + region.width, region.y + region.height)
            )
            crop.putpixel((0, 0), (255, 0, 0))
            return crop.resize((60, 90), resample=Image.Resampling.NEAREST)

        context = ObservationOcrContext(image, backend, None, "rapid-v1")
        result = context.read_preprocessed_result(
            image,
            Bounds(40, 50, 20, 30),
            preprocessing_id="world-blue-3x",
            prepare=prepare,
        )

        assert result is not None
        self.assertEqual(len(callback_images), 1)
        self.assertIsNot(callback_images[0], image)
        self.assertEqual(backend.calls[0].size, (60, 90))
        self.assertEqual(result.lines[0].bounds, Bounds(42, 53, 4, 5))
        self.assertEqual(result.words[0].bounds, Bounds(42, 53, 4, 5))
        self.assertEqual(context.metrics.processed_pixel_area, 60 * 90)

    def test_preprocessed_tiny_word_keeps_a_positive_box_inside_source_roi(self) -> None:
        image = Image.new("RGB", (100, 100))
        tiny_word = OcrWord("tiny", Bounds(1, 1, 1, 1), 0.8)
        backend = _RecordingOcrBackend(
            factory=lambda image, region: OcrResult(
                lines=(_line("tiny", x=1, y=1, width=1, height=1, words=(tiny_word,)),),
                words=(tiny_word,),
            )
        )
        context = ObservationOcrContext(image, backend, None, "rapid-v1")
        source_region = Bounds(40, 50, 20, 30)

        result = context.read_preprocessed_result(
            image,
            source_region,
            preprocessing_id="tiny-box-3x",
            prepare=lambda full_image, region: full_image.crop(
                (region.x, region.y, region.x + region.width, region.y + region.height)
            ).resize((60, 90), resample=Image.Resampling.NEAREST),
        )

        assert result is not None
        projected = result.words[0].bounds
        self.assertEqual(projected, Bounds(40, 50, 1, 1))
        self.assertGreater(projected.width, 0)
        self.assertGreater(projected.height, 0)
        self.assertLessEqual(projected.x + projected.width, source_region.x + source_region.width)
        self.assertLessEqual(projected.y + projected.height, source_region.y + source_region.height)

    def test_preprocess_none_is_cached_without_engine_work(self) -> None:
        image = Image.new("RGB", (20, 20))
        backend = _RecordingOcrBackend()
        context = ObservationOcrContext(image, backend, None, "rapid-v1")
        prepare = lambda crop, region: None

        first = context.read_preprocessed_result(
            image,
            Bounds(0, 0, 10, 10),
            preprocessing_id="optional-filter",
            prepare=prepare,
        )
        second = context.read_preprocessed_result(
            image,
            Bounds(0, 0, 10, 10),
            preprocessing_id="optional-filter",
            prepare=prepare,
        )

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(backend.calls), 0)
        self.assertEqual(context.metrics.engine_calls, 0)
        self.assertEqual(context.metrics.cache_hits, 1)

    def test_prepare_failures_are_retried_and_not_cached(self) -> None:
        image = Image.new("RGB", (20, 20))
        backend = _RecordingOcrBackend()
        context = ObservationOcrContext(image, backend, None, "rapid-v1")
        attempts = 0

        def prepare(full_image: Image.Image, region: Bounds) -> Image.Image:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("prepare failed")
            return full_image.crop(
                (region.x, region.y, region.x + region.width, region.y + region.height)
            )

        with self.assertRaisesRegex(RuntimeError, "prepare failed"):
            context.read_preprocessed_result(
                image,
                Bounds(0, 0, 10, 10),
                preprocessing_id="retryable",
                prepare=prepare,
            )
        context.read_preprocessed_result(
            image,
            Bounds(0, 0, 10, 10),
            preprocessing_id="retryable",
            prepare=prepare,
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(context.metrics.engine_calls, 1)
        self.assertEqual(context.metrics.cache_hits, 0)

    def test_cache_bound_keeps_full_frame_and_evicts_oldest_crop(self) -> None:
        image = Image.new("RGB", (100, 100))
        backend = _RecordingOcrBackend()
        context = ObservationOcrContext(image, backend, None, "rapid-v1", max_entries=3)
        regions = [Bounds(0, 0, 10, 10), Bounds(10, 0, 10, 10), Bounds(20, 0, 10, 10)]

        context.read_result(image)
        for region in regions:
            context.read_result(image, region, reuse_full_frame=False)
        context.read_result(image)
        context.read_result(image, regions[0], reuse_full_frame=False)

        self.assertEqual(len(backend.calls), 5)
        self.assertEqual(context.metrics.engine_calls, 5)

    def test_max_one_may_leave_crops_uncached_but_full_frame_remains_pinned(self) -> None:
        image = Image.new("RGB", (30, 30))
        backend = _RecordingOcrBackend()
        context = ObservationOcrContext(image, backend, None, "rapid-v1", max_entries=1)
        region = Bounds(0, 0, 10, 10)

        context.read_result(image)
        context.read_result(image, region, reuse_full_frame=False)
        context.read_result(image, region, reuse_full_frame=False)
        context.read_result(image)

        self.assertEqual(len(backend.calls), 3)
        self.assertEqual(context.metrics.cache_hits, 1)

    def test_max_one_caches_a_crop_until_full_frame_is_pinned(self) -> None:
        image = Image.new("RGB", (30, 30))
        backend = _RecordingOcrBackend()
        context = ObservationOcrContext(image, backend, None, "rapid-v1", max_entries=1)
        region = Bounds(0, 0, 10, 10)

        context.read_result(image, region, reuse_full_frame=False)
        context.read_result(image, region, reuse_full_frame=False)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(context.metrics.cache_hits, 1)

        context.read_result(image)
        context.read_result(image, region, reuse_full_frame=False)

        self.assertEqual(len(backend.calls), 3)

    def test_metrics_snapshot_is_immutable(self) -> None:
        image = Image.new("RGB", (10, 10))
        context = ObservationOcrContext(image, _RecordingOcrBackend(), None, "rapid-v1")
        metrics = context.metrics

        with self.assertRaises(FrozenInstanceError):
            metrics.requests = 10  # type: ignore[misc]


class _FakeRapidOcrResult:
    """Minimal stand-in for the rapidocr 3.x engine result object."""

    def __init__(
        self,
        boxes: list[list[list[float]]] | None,
        txts: list[str] | None,
        scores: list[float] | None,
    ) -> None:
        self.boxes = boxes
        self.txts = txts
        self.scores = scores


class _FakeRapidOcrEngine:
    """Callable engine stub returning one configured 3.x result per call."""

    def __init__(self, result: _FakeRapidOcrResult) -> None:
        self.result = result
        self.payloads: list[bytes] = []
        self.use_det_calls: list[bool | None] = []
        self.use_cls_calls: list[bool | None] = []

    def __call__(
        self, payload: bytes, use_det: bool | None = None,
        use_cls: bool | None = None,
    ) -> _FakeRapidOcrResult:
        self.payloads.append(payload)
        self.use_det_calls.append(use_det)
        self.use_cls_calls.append(use_cls)
        return self.result


def _rapid_service(result: _FakeRapidOcrResult) -> tuple[RapidOcrService, _FakeRapidOcrEngine]:
    """Bind one fake engine through the patched rapidocr import."""

    engine = _FakeRapidOcrEngine(result)
    with mock.patch(
        "pnc_automation.core.vision.ocr.ocr_service.RapidOCR", return_value=engine
    ):
        service = RapidOcrService()
    return service, engine


class RapidOcrServiceAdapterTests(unittest.TestCase):
    """The adapter consumes the rapidocr 3.x boxes/txts/scores contract."""

    def test_engine_constructs_with_vendored_recognizer_and_canonical_shape(self) -> None:
        """The canonical backend pairs the vendored PP-OCRv3 recognizer with
        its aspect-preserving ``[3, 48, 0]`` input shape."""

        engine = _FakeRapidOcrEngine(_FakeRapidOcrResult(boxes=[], txts=[], scores=[]))
        with mock.patch(
            "pnc_automation.core.vision.ocr.ocr_service.RapidOCR", return_value=engine
        ) as constructor:
            RapidOcrService()

        constructor.assert_called_once()
        params = constructor.call_args.kwargs["params"]
        self.assertEqual("warning", params["Global.log_level"])
        self.assertTrue(params["Rec.model_path"].endswith("ch_PP-OCRv3_rec_infer.onnx"))
        self.assertEqual([3, 48, 0], params["Rec.rec_img_shape"])

    def test_boxes_txts_scores_become_localized_lines_with_synthesized_words(self) -> None:
        service, _engine = _rapid_service(
            _FakeRapidOcrResult(
                boxes=[[[5, 10], [25, 10], [25, 22], [5, 22]], [[30, 8], [48, 8], [48, 20], [30, 20]]],
                txts=["Ch.5", "Costa Dorad"],
                scores=[0.92, 0.87],
            )
        )

        result = service.read_result(Image.new("RGB", (200, 100)))

        self.assertEqual(2, len(result.lines))
        first, second = result.lines
        self.assertEqual("Ch.5", first.text)
        self.assertEqual(Bounds(5, 10, 20, 12), first.bounds)
        self.assertAlmostEqual(0.92, first.confidence)
        self.assertEqual(Bounds(30, 8, 18, 12), second.bounds)
        self.assertEqual(("Costa", "Dorad"), tuple(word.text for word in second.words))
        self.assertEqual(len(result.words), 3)

    def test_upright_request_disables_only_its_orientation_classifier(self) -> None:
        service, engine = _rapid_service(_FakeRapidOcrResult(boxes=[], txts=[], scores=[]))
        image = Image.new("RGB", (200, 100))
        service.read_result(image)
        service.read_lines(image, orientation=OcrTextOrientation.UPRIGHT)
        service.read_text(image, Bounds(0, 0, 150, 90))
        self.assertEqual([True, False, True], engine.use_cls_calls)
        self.assertEqual([True, True, True], engine.use_det_calls)

    def test_bounded_region_offsets_line_coordinates(self) -> None:
        service, _engine = _rapid_service(
            _FakeRapidOcrResult(
                boxes=[[[5, 10], [25, 10], [25, 22], [5, 22]]],
                txts=["Ch.5"],
                scores=[0.92],
            )
        )

        result = service.read_result(
            Image.new("RGB", (200, 100)), region=Bounds(30, 40, 100, 50)
        )

        self.assertEqual(Bounds(35, 50, 20, 12), result.lines[0].bounds)

    def test_missing_detection_fields_and_blank_text_produce_empty_lines(self) -> None:
        image = Image.new("RGB", (200, 100))
        for result in (
            _FakeRapidOcrResult(boxes=None, txts=None, scores=None),
            _FakeRapidOcrResult(
                boxes=[[[0, 0], [9, 0], [9, 9], [0, 9]]], txts=None, scores=[0.9]
            ),
            _FakeRapidOcrResult(
                boxes=[[[0, 0], [9, 0], [9, 9], [0, 9]]], txts=["   "], scores=[0.9]
            ),
        ):
            with self.subTest(result=result.txts):
                service, _engine = _rapid_service(result)
                self.assertEqual((), service.read_result(image).lines)

    def test_thin_or_wide_crops_use_recognition_only_then_detection_resumes(self) -> None:
        service, engine = _rapid_service(
            _FakeRapidOcrResult(
                boxes=[[[0, 0], [9, 0], [9, 9], [0, 9]]], txts=["x"], scores=[0.9]
            )
        )
        image = Image.new("RGB", (400, 200))

        service.read_result(image, region=Bounds(10, 10, 100, 28))
        service.read_result(image, region=Bounds(10, 60, 250, 31))
        service.read_result(image, region=Bounds(10, 100, 100, 60))

        self.assertEqual([False, False, True], engine.use_det_calls)

    def test_direct_recognition_filters_floor_and_offsets_crop_covering_lines(self) -> None:
        service, engine = _rapid_service(
            _FakeRapidOcrResult(boxes=None, txts=["Ch.5", "faint"], scores=[0.62, 0.49])
        )
        image = Image.new("RGB", (400, 200))

        result = service.read_result(image, region=Bounds(30, 40, 220, 26))

        self.assertEqual([False], engine.use_det_calls)
        self.assertEqual(1, len(result.lines))
        line = result.lines[0]
        self.assertEqual("Ch.5", line.text)
        self.assertAlmostEqual(0.62, line.confidence)
        self.assertEqual(Bounds(30, 40, 220, 26), line.bounds)
        self.assertEqual(Bounds(30, 40, 220, 26), line.words[0].bounds)

    def test_direct_recognition_empty_and_blank_output_stays_empty(self) -> None:
        image = Image.new("RGB", (400, 200))
        for result in (
            _FakeRapidOcrResult(boxes=None, txts=None, scores=None),
            _FakeRapidOcrResult(boxes=None, txts=["  "], scores=[0.9]),
            _FakeRapidOcrResult(boxes=None, txts=["4"], scores=[0.49]),
        ):
            with self.subTest(result=result.txts):
                service, engine = _rapid_service(result)
                self.assertEqual(
                    (), service.read_result(image, region=Bounds(10, 10, 90, 28)).lines
                )
                self.assertEqual([False], engine.use_det_calls)

    def test_direct_recognition_maps_digit_text_for_badge_style_crops(self) -> None:
        service, engine = _rapid_service(
            _FakeRapidOcrResult(boxes=None, txts=["9"], scores=[0.71])
        )
        image = Image.new("RGB", (400, 200))

        result = service.read_result(image, region=Bounds(51, 323, 30, 30))

        self.assertEqual([False], engine.use_det_calls)
        self.assertEqual("9", result.lines[0].text)
        self.assertAlmostEqual(0.71, result.lines[0].confidence)
        self.assertEqual(Bounds(51, 323, 30, 30), result.lines[0].bounds)


if __name__ == "__main__":
    unittest.main()
