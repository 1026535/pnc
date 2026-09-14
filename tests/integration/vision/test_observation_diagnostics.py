"""Offline coverage for frame-local observation diagnostic exports."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.vision.observation_diagnostics import (
    ObservationDebugArtifactCollector,
)
from pnc_automation.app.pnc.vision.world_map_coordinates import read_world_coordinate_bar_viewport
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import (
    CapturedScreenshot,
    ScreenshotService,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.errors import ScreenClassificationError
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadPurpose,
    OcrReadStatus,
    OcrRequiredFieldStatus,
    OcrResult,
)
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    OcrRegionFailurePolicy,
    OcrRegionPlan,
    OcrRegionPurpose,
    OcrRegionReadStatus,
    execute_ocr_region_plans,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import (
    _FakeScreenshotSession,
)
from tests.support.pnc.capture_vision.coordinate_bar_top_hud_fallback_ocr_service import (
    _CoordinateBarTopHudFallbackOcrService,
)
from tests.support.pnc.observations import make_observation


@dataclass(slots=True)
class _BoundedOcrSpy:
    """Returns queued results and fails if a collector requests full-frame OCR."""

    responses: list[OcrResult | BaseException] = field(default_factory=list)
    calls: list[Bounds | None] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Record one backend call and return its next bounded response."""

        del image
        self.calls.append(region)
        if region is None:
            raise AssertionError("Diagnostic export must not request full-frame OCR.")
        if not self.responses:
            return OcrResult(lines=(), words=())
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


@dataclass(slots=True)
class _EmptyOcrSpy:
    """Returns empty OCR while allowing the production guard's full-frame read."""

    calls: list[Bounds | None] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Record every production OCR request and return no recognized text."""

        del image
        self.calls.append(region)
        return OcrResult(lines=(), words=())


class _ExportObservingCollector(ObservationDebugArtifactCollector):
    """Expose the context snapshot around a production recognition-gap export."""

    def __init__(self) -> None:
        """Initialize observations captured around the base collector call."""

        self.calls = 0
        self.before_metrics = None
        self.after_metrics = None

    def persist_recognition_gap(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
        ocr_context: ObservationOcrContext,
        profile_ids: tuple[str, ...] = (),
    ) -> None:
        """Record OCR state before and after invoking the real exporter."""

        self.calls += 1
        self.before_metrics = ocr_context.metrics
        super().persist_recognition_gap(
            screenshot=screenshot,
            observation=observation,
            ocr_context=ocr_context,
            profile_ids=profile_ids,
        )
        self.after_metrics = ocr_context.metrics


def _ocr_result(*lines: OcrLine) -> OcrResult:
    """Build one result with the same line and word snapshots."""

    return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))


def _ocr_line(text: str, *, x: int, y: int, width: int = 80, height: int = 20) -> OcrLine:
    """Build one native-frame OCR line."""

    return OcrLine(text=text, bounds=Bounds(x=x, y=y, width=width, height=height), confidence=0.97)


class ObservationDiagnosticsTests(unittest.TestCase):
    """Proves diagnostic export consumes only evidence already recorded for a frame."""

    def _capture(
        self,
        root: Path,
        *,
        persist: bool = True,
        size: tuple[int, int] = (240, 160),
        label: str = "capture",
    ) -> CapturedScreenshot:
        """Capture a real synthetic PNG through the canonical screenshot service."""

        screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
        payload = _encode_png(Image.new("RGB", size, (15, 28, 68)))
        return screenshot_service.capture(
            _FakeScreenshotSession(payload),
            artifact_directory="diagnostic_test",
            label=label,
            persist=persist,
        )

    @staticmethod
    def _context(
        screenshot: CapturedScreenshot,
        backend: _BoundedOcrSpy,
        *,
        frame_ref: FrameRef | None = None,
    ) -> ObservationOcrContext:
        """Bind a context to the exact image and provenance under test."""

        return ObservationOcrContext(
            screenshot.image,
            backend,
            screenshot.frame_ref if frame_ref is None else frame_ref,
            "diagnostic-test-backend",
        )

    @staticmethod
    def _sidecar(screenshot: CapturedScreenshot, kind: str) -> Path:
        """Resolve a sidecar path beside a persisted screenshot."""

        assert screenshot.artifact_path is not None
        return screenshot.artifact_path.with_name(f"{screenshot.artifact_path.stem}_{kind}.json")

    @staticmethod
    def _production_builder(
        backend: _EmptyOcrSpy,
        collector: _ExportObservingCollector,
    ) -> ObservationBuilder:
        """Wire the default registry, visual recognizer, selector engine, and enricher."""

        registry = build_default_selector_registry()
        return ObservationBuilder(
            selector_registry=registry,
            selector_engine=ImageSelectorEngine(template_matcher=OpenCvTemplateMatcher()),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(selector_registry=registry),
            visual_recognizer=load_visual_screen_recognizer(),
            ocr_service=backend,
            debug_artifact_collector=collector,
        )

    def test_bounded_crop_sidecar_uses_recorded_results_and_preserves_native_bounds(self) -> None:
        """Exports only the unknown line from a bounded OCR result without another read."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root)
            observation = make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
                visible_texts={UiElementId.PNC_CHAT_SHORTCUT: "Known Label"},
                frame_ref=screenshot.frame_ref,
            )
            crop = Bounds(x=40, y=30, width=160, height=90)
            backend = _BoundedOcrSpy(
                responses=[
                    _ocr_result(
                        _ocr_line("Known Label", x=55, y=42),
                        _ocr_line("Mystery Badge", x=125, y=78, width=96),
                    )
                ]
            )
            context = self._context(screenshot, backend)
            context.read_result(
                screenshot.image,
                crop,
                purpose=OcrReadPurpose.CONTENT,
                detail="bounded_requested_region",
            )
            before_metrics = context.metrics

            ObservationDebugArtifactCollector().persist_unidentified_ocr_sidecar(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertEqual(context.metrics, before_metrics)
            self.assertEqual(backend.calls, [crop])
            document = json.loads(self._sidecar(screenshot, "unidentified_ocr").read_text(encoding="utf-8"))
            self.assertEqual(
                [line["text"] for line in document["unidentified_ocr_lines"]],
                ["Mystery Badge"],
            )
            self.assertEqual(
                document["unidentified_ocr_lines"][0]["bounds"],
                {"x": 125, "y": 78, "width": 96, "height": 20},
            )
            self.assertNotIn("Known Label", {
                line["text"] for line in document["unidentified_ocr_lines"]
            })

    def test_unknown_empty_context_writes_recognition_gap_without_backend_reads(self) -> None:
        """Records an unknown decision even when no OCR request was made."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root)
            observation = make_observation(ScreenType.UNKNOWN, frame_ref=screenshot.frame_ref)
            backend = _BoundedOcrSpy()
            context = self._context(screenshot, backend)
            before_metrics = context.metrics

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertEqual(context.metrics, before_metrics)
            self.assertEqual(backend.calls, [])
            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertEqual(document["reasons"], ["unknown_screen", "guard_unresolved"])
            self.assertEqual(document["ocr_reads"], [])

    def test_missing_requested_field_writes_gap_and_keeps_verified_observation_facts(self) -> None:
        """Preserves a known screen's typed identity while exporting a missing field read."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root)
            observation = make_observation(
                ScreenType.PNC_PLAYER_PROFILE,
                profile_player_name="Verified Lord",
                frame_ref=screenshot.frame_ref,
            )
            backend = _BoundedOcrSpy()
            context = self._context(screenshot, backend)
            field_region = Bounds(x=70, y=40, width=130, height=28)
            context.record_diagnostic(
                purpose=OcrReadPurpose.CONTENT,
                status=OcrReadStatus.MISSING,
                region=field_region,
                detail="field:PNC_PLAYER_PROFILE_NAME_LABEL",
            )
            before_metrics = context.metrics

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertEqual(observation.profile_player_name, "Verified Lord")
            self.assertEqual(context.metrics, before_metrics)
            self.assertEqual(backend.calls, [])
            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertEqual(document["reasons"], ["missing_ocr_facts"])
            self.assertEqual(document["missing_reads"][0]["detail"], "field:PNC_PLAYER_PROFILE_NAME_LABEL")

    def test_parser_missing_field_writes_gap_after_nonempty_ocr_read(self) -> None:
        """Reports a semantic parser miss separately from generic OCR read misses."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, label="parser_missing")
            observation = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=screenshot.frame_ref)
            field_region = Bounds(x=70, y=40, width=130, height=28)
            backend = _BoundedOcrSpy(responses=[_ocr_result(_ocr_line("not-a-coordinate", x=75, y=44))])
            context = self._context(screenshot, backend)
            context.read_result(
                screenshot.image,
                field_region,
                purpose=OcrReadPurpose.CONTENT,
                detail="plan:world_coordinate_pair",
            )
            context.record_required_field_diagnostic(
                required_fact="world_coordinate_pair",
                status=OcrRequiredFieldStatus.INVALID,
                region=field_region,
                reason="invalid_value",
                detail="parser:world_coordinate_dialog_field",
            )

            before_metrics = context.metrics
            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertEqual(context.metrics, before_metrics)
            self.assertEqual(backend.calls, [field_region])
            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertEqual(document["reasons"], ["missing_required_fields"])
            self.assertEqual(document["missing_reads"], [])
            self.assertEqual(
                document["missing_required_fields"],
                [{
                    "required_fact": "world_coordinate_pair",
                    "status": "invalid",
                    "region": {"x": 70, "y": 40, "width": 130, "height": 28},
                    "reason": "invalid_value",
                    "detail": "parser:world_coordinate_dialog_field",
                }],
            )

    def test_recovered_parser_field_does_not_leave_a_gap(self) -> None:
        """Uses the latest parser outcome when a retry recovers the same field."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, label="parser_recovered")
            observation = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=screenshot.frame_ref)
            field_region = Bounds(x=70, y=40, width=130, height=28)
            backend = _BoundedOcrSpy()
            context = self._context(screenshot, backend)
            context.record_required_field_diagnostic(
                required_fact="world_coordinate_pair",
                status=OcrRequiredFieldStatus.INVALID,
                region=field_region,
                reason="invalid_value",
            )
            context.record_required_field_diagnostic(
                required_fact="world_coordinate_pair",
                status=OcrRequiredFieldStatus.PRESENT,
                region=field_region,
                reason="parsed",
            )

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertFalse(self._sidecar(screenshot, "recognition_gap").exists())
            self.assertEqual(backend.calls, [])

    def test_coordinate_top_hud_recovery_clears_linked_miss_and_retains_attempt_history(self) -> None:
        """Keeps bounded fallback provenance while leaving unrelated misses reportable."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, size=(540, 960), label="coordinate_fallback_recovered")
            observation = make_observation(ScreenType.PNC_WORLD_MAP, frame_ref=screenshot.frame_ref)
            selector_region = Bounds(x=100, y=100, width=200, height=50)
            top_hud_region = Bounds(x=0, y=0, width=540, height=172)
            backend = _CoordinateBarTopHudFallbackOcrService(
                top_hud_lines=(_ocr_line("X:370Y:510", x=10, y=10, width=100, height=20),)
            )
            context = self._context(screenshot, backend)
            context.record_required_field_diagnostic(
                required_fact="world_coordinate_pair",
                status=OcrRequiredFieldStatus.INVALID,
                region=selector_region,
                reason="invalid_value",
            )
            parsed = read_world_coordinate_bar_viewport(
                image=screenshot.image,
                bounds=selector_region,
                ocr_context=context,
            )
            context.record_diagnostic(
                purpose=OcrReadPurpose.CONTENT,
                status=OcrReadStatus.MISSING,
                region=selector_region,
                detail="unrelated_fact",
                required_fact="unrelated_fact",
            )

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertIsNotNone(parsed)
            self.assertEqual(
                [(diagnostic.status, diagnostic.region) for diagnostic in context.required_field_diagnostics],
                [
                    (OcrRequiredFieldStatus.INVALID, selector_region),
                    (OcrRequiredFieldStatus.PRESENT, top_hud_region),
                ],
            )
            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertEqual(document["reasons"], ["missing_ocr_facts"])
            self.assertEqual(
                [read["detail"] for read in document["missing_reads"]],
                ["unrelated_fact"],
            )
            self.assertEqual(
                [read["required_fact"] for read in document["ocr_reads"]],
                [
                    "world_coordinate_pair",
                    "world_coordinate_pair",
                    "world_coordinate_pair",
                    "unrelated_fact",
                ],
            )
            self.assertEqual(
                [field["region"] for field in document["required_field_diagnostics"]],
                [
                    {"x": 100, "y": 100, "width": 200, "height": 50},
                    {"x": 0, "y": 0, "width": 540, "height": 172},
                ],
            )

    def test_known_clear_observation_with_no_misses_creates_no_gap(self) -> None:
        """Does not report a recognition gap after a successful bounded read on a clear screen."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root)
            observation = make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
                visible_texts={UiElementId.PNC_CHAT_SHORTCUT: "Known Label"},
                frame_ref=screenshot.frame_ref,
            )
            crop = Bounds(x=40, y=30, width=160, height=90)
            backend = _BoundedOcrSpy(responses=[_ocr_result(_ocr_line("Known Label", x=55, y=42))])
            context = self._context(screenshot, backend)
            context.read_result(
                screenshot.image,
                crop,
                purpose=OcrReadPurpose.CONTENT,
                detail="known_field",
            )

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertFalse(self._sidecar(screenshot, "recognition_gap").exists())
            self.assertEqual(backend.calls, [crop])

    def test_foreign_observation_or_context_frame_is_rejected_before_report(self) -> None:
        """Rejects mismatched observation and context provenance without writing a report."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root)
            assert screenshot.frame_ref is not None
            foreign_frame = replace(screenshot.frame_ref, capture_sequence=screenshot.frame_ref.capture_sequence + 1)
            collector = ObservationDebugArtifactCollector()

            with self.subTest(kind="foreign observation"):
                backend = _BoundedOcrSpy()
                context = self._context(screenshot, backend)
                observation = make_observation(ScreenType.UNKNOWN, frame_ref=foreign_frame)
                with self.assertRaisesRegex(ValueError, "different capture frame"):
                    collector.persist_recognition_gap(
                        screenshot=screenshot,
                        observation=observation,
                        ocr_context=context,
                    )
                self.assertEqual(backend.calls, [])

            with self.subTest(kind="foreign context frame"):
                backend = _BoundedOcrSpy()
                context = self._context(screenshot, backend, frame_ref=foreign_frame)
                observation = make_observation(ScreenType.UNKNOWN, frame_ref=screenshot.frame_ref)
                with self.assertRaisesRegex(ValueError, "different frame provenance"):
                    collector.persist_recognition_gap(
                        screenshot=screenshot,
                        observation=observation,
                        ocr_context=context,
                    )
                self.assertEqual(backend.calls, [])

            self.assertFalse(any(root.rglob("*_recognition_gap.json")))

    def test_recovered_ocr_retry_does_not_leave_a_remaining_gap(self) -> None:
        """Uses the latest successful retry outcome when deciding whether a gap remains."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root)
            observation = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=screenshot.frame_ref)
            crop = Bounds(x=40, y=30, width=160, height=90)
            backend = _BoundedOcrSpy(
                responses=[RuntimeError("temporary OCR failure"), _ocr_result(_ocr_line("Recovered", x=55, y=42))]
            )
            context = self._context(screenshot, backend)
            with self.assertRaisesRegex(RuntimeError, "temporary OCR failure"):
                context.read_result(
                    screenshot.image,
                    crop,
                    purpose=OcrReadPurpose.CONTENT,
                    detail="retryable_field",
                )
            context.read_result(
                screenshot.image,
                crop,
                purpose=OcrReadPurpose.CONTENT,
                detail="retryable_field",
            )

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertFalse(self._sidecar(screenshot, "recognition_gap").exists())
            self.assertEqual(backend.calls, [crop, crop])
            self.assertEqual(
                [read.status for read in context.read_diagnostics],
                [OcrReadStatus.ERROR, OcrReadStatus.ENGINE],
            )

    def test_recovered_planned_ocr_retry_does_not_leave_a_remaining_gap(self) -> None:
        """Correlates a planned classification miss with its successful retry."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, size=(540, 960), label="planned_retry")
            observation = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=screenshot.frame_ref)
            crop = Bounds(x=40, y=30, width=160, height=90)
            backend = _BoundedOcrSpy(
                responses=[
                    ScreenClassificationError("temporary planned miss", region=crop),
                    _ocr_result(_ocr_line("Recovered", x=55, y=42)),
                ]
            )
            context = self._context(screenshot, backend)
            plan = OcrRegionPlan(
                family=ScreenType.PNC_HOME_CITY,
                purpose=OcrRegionPurpose.TEXT_FIELD,
                bounds=crop,
                required_fact="planned_field",
                failure_policy=OcrRegionFailurePolicy.ABSTAIN,
            )

            first_read = execute_ocr_region_plans(
                image=screenshot.image,
                plans=(plan,),
                ocr_context=context,
            )
            second_read = execute_ocr_region_plans(
                image=screenshot.image,
                plans=(plan,),
                ocr_context=context,
            )
            self.assertEqual(first_read[0].status, OcrRegionReadStatus.MISSING)
            self.assertEqual(second_read[0].status, OcrRegionReadStatus.PRESENT)
            before_metrics = context.metrics

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertFalse(self._sidecar(screenshot, "recognition_gap").exists())
            self.assertEqual(context.metrics, before_metrics)
            self.assertEqual(backend.calls, [crop, crop])

    def test_unrecovered_planned_empty_read_still_reports_missing_fact(self) -> None:
        """Keeps an empty planned result reportable when no retry recovers it."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, size=(540, 960), label="planned_empty")
            observation = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=screenshot.frame_ref)
            crop = Bounds(x=40, y=30, width=160, height=90)
            backend = _BoundedOcrSpy(responses=[_ocr_result()])
            context = self._context(screenshot, backend)
            plan = OcrRegionPlan(
                family=ScreenType.PNC_HOME_CITY,
                purpose=OcrRegionPurpose.TEXT_FIELD,
                bounds=crop,
                required_fact="planned_field",
                failure_policy=OcrRegionFailurePolicy.ABSTAIN,
            )

            reads = execute_ocr_region_plans(
                image=screenshot.image,
                plans=(plan,),
                ocr_context=context,
            )
            self.assertEqual(reads[0].status, OcrRegionReadStatus.MISSING)

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertEqual(document["reasons"], ["missing_ocr_facts"])
            self.assertEqual(document["missing_reads"][0]["detail"], "plan:planned_field")
            self.assertEqual(backend.calls, [crop])

    def test_planned_retry_does_not_clear_a_different_fact_at_same_bounds(self) -> None:
        """Scopes retry correlation by required fact even when regions overlap exactly."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, size=(540, 960), label="planned_distinct_facts")
            observation = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=screenshot.frame_ref)
            crop = Bounds(x=40, y=30, width=160, height=90)
            backend = _BoundedOcrSpy(
                responses=[
                    ScreenClassificationError("temporary planned miss", region=crop),
                    ScreenClassificationError("different planned miss", region=crop),
                    _ocr_result(_ocr_line("Recovered", x=55, y=42)),
                ]
            )
            context = self._context(screenshot, backend)
            recovered_plan = OcrRegionPlan(
                family=ScreenType.PNC_HOME_CITY,
                purpose=OcrRegionPurpose.TEXT_FIELD,
                bounds=crop,
                required_fact="recovered_field",
                failure_policy=OcrRegionFailurePolicy.ABSTAIN,
            )
            missing_plan = replace(recovered_plan, required_fact="different_field")

            execute_ocr_region_plans(
                image=screenshot.image,
                plans=(recovered_plan, missing_plan),
                ocr_context=context,
            )
            execute_ocr_region_plans(
                image=screenshot.image,
                plans=(recovered_plan,),
                ocr_context=context,
            )

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertEqual(document["reasons"], ["missing_ocr_facts"])
            self.assertEqual(
                [read["detail"] for read in document["missing_reads"]],
                ["plan:different_field"],
            )
            self.assertEqual(backend.calls, [crop, crop, crop])

    def test_semantic_misses_sharing_read_key_do_not_overwrite_each_other(self) -> None:
        """Keeps distinct semantic misses when their OCR request metadata is identical."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, label="semantic_shared_read")
            observation = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=screenshot.frame_ref)
            crop = Bounds(x=40, y=30, width=160, height=90)
            backend = _BoundedOcrSpy()
            context = self._context(screenshot, backend)

            for required_fact in ("missing_fact", "recovered_fact"):
                context.record_diagnostic(
                    purpose=OcrReadPurpose.CONTENT,
                    status=OcrReadStatus.MISSING,
                    region=crop,
                    detail="shared_detail",
                    required_fact=required_fact,
                )
            context.record_required_field_diagnostic(
                required_fact="recovered_fact",
                status=OcrRequiredFieldStatus.PRESENT,
                region=crop,
                reason="parsed",
            )

            ObservationDebugArtifactCollector().persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertEqual(document["reasons"], ["missing_ocr_facts"])
            self.assertEqual(
                [(read["detail"], read["required_fact"]) for read in document["missing_reads"]],
                [("shared_detail", "missing_fact")],
            )
            self.assertEqual(
                [read["required_fact"] for read in document["ocr_reads"]],
                ["missing_fact", "recovered_fact"],
            )

    def test_ephemeral_capture_writes_no_files_or_extra_ocr_and_retains_diagnostics(self) -> None:
        """Leaves ephemeral captures file-free while preserving their existing OCR diagnostics."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, persist=False)
            observation = make_observation(ScreenType.UNKNOWN, frame_ref=screenshot.frame_ref)
            crop = Bounds(x=40, y=30, width=160, height=90)
            backend = _BoundedOcrSpy(responses=[_ocr_result(_ocr_line("Unclassified", x=55, y=42))])
            context = self._context(screenshot, backend)
            context.read_result(
                screenshot.image,
                crop,
                purpose=OcrReadPurpose.CONTENT,
                detail="ephemeral_content",
            )
            before_metrics = context.metrics
            before_diagnostics = context.read_diagnostics

            collector = ObservationDebugArtifactCollector()
            collector.persist_unidentified_ocr_sidecar(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )
            collector.persist_recognition_gap(
                screenshot=screenshot,
                observation=observation,
                ocr_context=context,
            )

            self.assertIsNone(screenshot.artifact_path)
            self.assertEqual(context.metrics, before_metrics)
            self.assertEqual(context.read_diagnostics, before_diagnostics)
            self.assertEqual(backend.calls, [crop])
            self.assertFalse(any(path.is_file() for path in root.rglob("*")))

    def test_production_builder_publishes_unknown_gap_without_debug_ocr(self) -> None:
        """Publishes an UNKNOWN report from the real builder stack without an export-time OCR read."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, size=(900, 1600), label="builder_unknown")
            backend = _EmptyOcrSpy()
            collector = _ExportObservingCollector()
            builder = self._production_builder(backend, collector)
            context = builder.create_ocr_context(screenshot)

            observation = builder.build(screenshot, ocr_context=context)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertEqual(collector.calls, 1)
            self.assertEqual(collector.before_metrics, collector.after_metrics)
            self.assertGreaterEqual(len(backend.calls), 1)
            self.assertFalse(any(read.purpose == OcrReadPurpose.DEBUG for read in context.read_diagnostics))
            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertIn("unknown_screen", document["reasons"])

    def test_production_navigation_perception_publishes_unknown_gap_without_debug_ocr(self) -> None:
        """Publishes an UNKNOWN report from replacement navigation without an export-time OCR read."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = self._capture(root, size=(900, 1600), label="navigation_unknown")
            backend = _EmptyOcrSpy()
            collector = _ExportObservingCollector()
            registry = build_default_selector_registry()

            created_contexts: list[ObservationOcrContext] = []

            def create_context(capture: CapturedScreenshot) -> ObservationOcrContext:
                """Create and retain the exact context consumed by perception."""

                context = ObservationOcrContext(
                    capture.image,
                    backend,
                    capture.frame_ref,
                    "navigation-diagnostic-test",
                )
                created_contexts.append(context)
                return context

            perception = NavigationPerception(
                recognizer=load_visual_screen_recognizer(),
                guard=PncObservationEnricher(selector_registry=registry),
                screen_classifier=ScreenClassifier(),
                create_ocr_context=create_context,
                debug_artifact_collector=collector,
            )

            observation = perception.build(screenshot)
            self.assertEqual(len(created_contexts), 1)
            context = created_contexts[0]

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertEqual(collector.calls, 1)
            self.assertEqual(collector.before_metrics, collector.after_metrics)
            self.assertGreaterEqual(len(backend.calls), 1)
            self.assertFalse(any(read.purpose == OcrReadPurpose.DEBUG for read in context.read_diagnostics))
            document = json.loads(self._sidecar(screenshot, "recognition_gap").read_text(encoding="utf-8"))
            self.assertIn("unknown_screen", document["reasons"])


if __name__ == "__main__":
    unittest.main()
