"""Deterministic ownership and fallback checks for fixed OCR region plans."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.ocr_region_plan import OcrRegionRead, OcrRegionReadStatus, OcrRegionPlan
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    OcrRegionFailurePolicy,
    OcrRegionPurpose,
    compile_ocr_region_plans,
    execute_ocr_region_plans,
)
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult
from PIL import Image


class _EmptyBackend:
    """Returns a deterministic empty OCR result for context tests."""

    def read_result(self, image, region=None):
        del image, region
        return OcrResult(lines=(), words=())


class _RegionAwareBackend:
    """Returns a crossing full-frame line and a separately recoverable crop line."""

    def __init__(self, crop_result: OcrResult) -> None:
        self.crop_result = crop_result
        self.regions: list[Bounds | None] = []

    def read_result(self, image, region=None):
        del image
        self.regions.append(region)
        if region is None:
            return OcrResult(
                lines=(OcrLine("crossing value", Bounds(90, 110, 240, 24), 0.9),),
                words=(),
            )
        return self.crop_result


class OcrRegionPlanTests(unittest.TestCase):
    """Keep fixed-field ownership screen-scoped and explicit about fallbacks."""

    def setUp(self) -> None:
        self.registry = build_default_selector_registry()

    def test_text_field_plan_requires_its_declared_screen(self) -> None:
        request = ObservationRequest.chat_transcript_observation()

        chat_plans = compile_ocr_region_plans(
            registry=self.registry,
            resolved_screen=ScreenType.PNC_CHAT,
            request=request,
            image_size=(540, 960),
        )
        home_plans = compile_ocr_region_plans(
            registry=self.registry,
            resolved_screen=ScreenType.PNC_HOME_CITY,
            request=request,
            image_size=(540, 960),
        )

        self.assertEqual(len(chat_plans), 1)
        self.assertEqual(chat_plans[0].purpose, OcrRegionPurpose.TEXT_FIELD)
        self.assertEqual(chat_plans[0].selector_id.value, "PNC_CHAT_INPUT_FIELD")
        self.assertEqual(home_plans, ())

    def test_unsupported_aspect_reports_named_full_frame_fallback(self) -> None:
        plans = compile_ocr_region_plans(
            registry=self.registry,
            resolved_screen=ScreenType.PNC_CHAT,
            request=ObservationRequest.chat_transcript_observation(),
            image_size=(700, 960),
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].purpose, OcrRegionPurpose.FULL_FRAME_FALLBACK)
        self.assertEqual(plans[0].failure_policy, OcrRegionFailurePolicy.FULL_FRAME_FALLBACK)
        self.assertEqual(plans[0].fallback_reason, "unsupported_aspect")

    def test_coordinate_only_plan_keeps_specialized_region_on_unlisted_resolution(self) -> None:
        plans = compile_ocr_region_plans(
            registry=self.registry,
            resolved_screen=ScreenType.PNC_WORLD_MAP,
            request=ObservationRequest.world_map_movement_proof_follow_up(),
            image_size=(700, 960),
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].purpose, OcrRegionPurpose.WORLD_COORDINATE_BAR)
        self.assertNotEqual(plans[0].fallback_reason, "unsupported_aspect")

    def test_execution_reuses_pinned_full_frame_without_second_backend_dispatch(self) -> None:
        image = Image.new("RGB", (540, 960), (0, 0, 0))
        context = ObservationOcrContext(image, _EmptyBackend(), None, "test")
        plan = compile_ocr_region_plans(
            registry=self.registry,
            resolved_screen=ScreenType.PNC_CHAT,
            request=ObservationRequest.chat_transcript_observation(),
            image_size=image.size,
        )

        context.read_result(image)
        reads = execute_ocr_region_plans(image=image, plans=plan, ocr_context=context)

        self.assertEqual(context.metrics.engine_calls, 1)
        self.assertGreaterEqual(context.metrics.fullframe_reuses, 1)
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0].status.value, "missing")

    def test_guard_and_unknown_content_reads_have_named_full_frame_reasons(self) -> None:
        image = Image.new("RGB", (540, 960), (0, 0, 0))
        context = ObservationOcrContext(image, _EmptyBackend(), None, "test")
        enricher = PncObservationEnricher()
        request = ObservationRequest.full_runtime_default()

        enricher.recognize_guards(image, request, ocr_context=context)
        enricher.enrich(
            image,
            ScreenType.UNKNOWN,
            {},
            request,
            ocr_context=context,
            ocr_regions={},
        )

        details = tuple(diagnostic.detail for diagnostic in context.read_diagnostics)
        self.assertIn("global_guard;fallback=mandatory_global_guard", details)
        self.assertIn("screen:unknown;fallback=identity_unresolved_requires_full_frame", details)

    def test_empty_coordinate_selector_scope_does_not_prepare_a_template_frame(self) -> None:
        image = Image.new("RGB", (700, 960), (0, 0, 0))

        class Matcher:
            prepared_calls = 0

            def prepare_frame(self, image, *, reference_size=None):
                del image, reference_size
                self.prepared_calls += 1
                return None

            def find_best_match(self, *args, **kwargs):
                del args, kwargs
                return None

        matcher = Matcher()
        context = ObservationOcrContext(image, _EmptyBackend(), None, "test")
        ImageSelectorEngine(matcher).detect(
            image,
            self.registry,
            selector_ids=(),
            ocr_context=context,
        )

        self.assertEqual(matcher.prepared_calls, 0)

    def test_field_resegments_when_contained_full_frame_line_crosses_region(self) -> None:
        image = Image.new("RGB", (540, 960), (0, 0, 0))
        region = Bounds(100, 100, 180, 50)
        backend = _RegionAwareBackend(
            OcrResult(lines=(OcrLine("Recovered value", Bounds(110, 112, 120, 22), 0.9),), words=())
        )
        context = ObservationOcrContext(image, backend, None, "test")
        context.read_result(image)
        plan = OcrRegionPlan(
            family=ScreenType.PNC_CHAT,
            purpose=OcrRegionPurpose.TEXT_FIELD,
            bounds=region,
            required_fact=UiElementId.PNC_CHAT_INPUT_FIELD.value,
            failure_policy=OcrRegionFailurePolicy.ABSTAIN,
            selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
        )
        state = PncObservationEnricher()._read_text_field_state(
            image=image,
            selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
            empty_placeholders=frozenset(),
            ocr_context=context,
            ocr_regions={
                UiElementId.PNC_CHAT_INPUT_FIELD: OcrRegionRead(
                    plan=plan,
                    result=OcrResult(lines=(), words=()),
                    status=OcrRegionReadStatus.PRESENT,
                )
            },
        )

        self.assertEqual(state.text, "Recovered value")
        self.assertFalse(state.empty)
        self.assertEqual(backend.regions, [None, region])
        self.assertIn(
            "field:PNC_CHAT_INPUT_FIELD;fallback=field_segmentation_missing",
            tuple(diagnostic.detail for diagnostic in context.read_diagnostics),
        )

    def test_missing_field_remains_unknown_after_dedicated_crop(self) -> None:
        image = Image.new("RGB", (540, 960), (0, 0, 0))
        region = Bounds(100, 100, 180, 50)
        backend = _RegionAwareBackend(OcrResult(lines=(), words=()))
        context = ObservationOcrContext(image, backend, None, "test")
        plan = OcrRegionPlan(
            family=ScreenType.PNC_CHAT,
            purpose=OcrRegionPurpose.TEXT_FIELD,
            bounds=region,
            required_fact=UiElementId.PNC_CHAT_INPUT_FIELD.value,
            failure_policy=OcrRegionFailurePolicy.ABSTAIN,
            selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
        )
        state = PncObservationEnricher()._read_text_field_state(
            image=image,
            selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
            empty_placeholders=frozenset(),
            ocr_context=context,
            ocr_regions={
                UiElementId.PNC_CHAT_INPUT_FIELD: OcrRegionRead(
                    plan=plan,
                    result=OcrResult(lines=(), words=()),
                    status=OcrRegionReadStatus.MISSING,
                )
            },
        )

        self.assertIsNone(state.text)
        self.assertIsNone(state.empty)
        self.assertEqual(backend.regions, [region])

    def test_known_placeholder_proves_empty_field(self) -> None:
        image = Image.new("RGB", (540, 960), (0, 0, 0))
        region = Bounds(100, 100, 180, 50)
        backend = _RegionAwareBackend(
            OcrResult(lines=(OcrLine("Enter content", Bounds(110, 112, 120, 22), 0.9),), words=())
        )
        context = ObservationOcrContext(image, backend, None, "test")
        plan = OcrRegionPlan(
            family=ScreenType.PNC_MAIL_COMPOSE_POPUP,
            purpose=OcrRegionPurpose.TEXT_FIELD,
            bounds=region,
            required_fact=UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD.value,
            failure_policy=OcrRegionFailurePolicy.ABSTAIN,
            selector_id=UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
        )
        state = PncObservationEnricher()._read_text_field_state(
            image=image,
            selector_id=UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
            empty_placeholders=frozenset({"ENTERCONTENT"}),
            ocr_context=context,
            ocr_regions={
                UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD: OcrRegionRead(
                    plan=plan,
                    result=OcrResult(lines=(), words=()),
                    status=OcrRegionReadStatus.MISSING,
                )
            },
        )

        self.assertIsNone(state.text)
        self.assertTrue(state.empty)


if __name__ == "__main__":
    unittest.main()
