"""Reviewed visual recognition contracts for Campaign navigation surfaces."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.automation.engine.navigation_core import reviewed_navigation_edges
from pnc_automation.app.pnc.domain.observation import ListEntryKind, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.campaign_ocr_regions import (
    CAMPAIGN_CHAPTER_STAGE_THREE_ROW,
    CAMPAIGN_CHAPTER_TITLE_REGION,
    CAMPAIGN_MAP_CHAPTER_ROW,
    CAMPAIGN_REFERENCE_SIZE,
    scale_campaign_bounds,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import DetectionKind, build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.modal_overlay import (
    update_modal_lines,
    with_update_modal,
)
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
CAMPAIGN_CHALLENGE_BOX = Bounds(178, 643, 184, 54)


def _image(name: str) -> Image.Image:
    with Image.open(FIXTURES / name) as source:
        return source.convert("RGB")


def _capture(image: Image.Image) -> CapturedScreenshot:
    """Wrap one fixture in the canonical capture model with explicit provenance."""

    frame = make_captured_frame(_encode_png(image), session_id="campaign-visual-test")
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _builder(ocr_lines: tuple[OcrLine, ...] = ()) -> ObservationBuilder:
    """Wire the production observation builder to deterministic OCR."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        ocr_service=_RecordingOcrService(lines=ocr_lines),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )


def _navigation_perception(ocr_lines: tuple[OcrLine, ...] = ()) -> NavigationPerception:
    """Wire NavigationPerception to the same registry and controlled OCR."""

    registry = build_default_selector_registry()
    ocr = _FakeOcrService(lines=ocr_lines)
    return NavigationPerception(
        load_visual_screen_recognizer(),
        PncObservationEnricher(selector_registry=registry),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "campaign-visual-test",
        ),
    )


class _CampaignCropOcrService:
    """Honors requested regions while retaining every backend crop for assertions."""

    def __init__(self, lines: tuple[OcrLine, ...]) -> None:
        """Initialize one fixture-backed OCR response set."""

        self.lines = lines
        self.regions: list[Bounds | None] = []

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Return only lines wholly contained by the requested native region."""

        self.regions.append(region)
        if region is None:
            return OcrResult(lines=self.lines, words=())
        lines = tuple(line for line in self.lines if region.contains_bounds(line.bounds))
        return OcrResult(lines=lines, words=())

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Return crop-filtered lines through the backend protocol."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Return newline-joined crop-filtered text through the backend protocol."""

        return "\n".join(line.text for line in self.read_lines(image, region))


def _builder_with_backend(ocr_service: _CampaignCropOcrService) -> ObservationBuilder:
    """Wire the production builder to one crop-aware OCR backend."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )


def _navigation_perception_with_backend(ocr_service: _CampaignCropOcrService) -> NavigationPerception:
    """Wire replacement perception to one crop-aware OCR backend."""

    registry = build_default_selector_registry()
    return NavigationPerception(
        load_visual_screen_recognizer(),
        PncObservationEnricher(selector_registry=registry),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr_service,
            capture.frame_ref,
            "campaign-visual-test",
        ),
    )


class CampaignVisualProfileTests(unittest.TestCase):
    """Require campaign identity and controls to remain evidence-backed and scoped."""

    def test_stage_content_request_preserves_controls_without_unused_body_ocr(self) -> None:
        """The captured stage needs foreground guarding, not an unused body scan."""
        capture = _capture(_image("campaign_stage_10_3.png"))
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                backend = _CampaignCropOcrService(())
                observation = (
                    _builder_with_backend(backend).build(
                        capture, request=ObservationRequest.campaign_map_follow_up()
                    )
                    if path == "builder"
                    else _navigation_perception_with_backend(backend).build(
                        capture, include_content=True
                    )
                )
                self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
                for selector in (
                    UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
                    UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
                ):
                    self.assertTrue(observation.has(selector))
                    self.assertEqual(observation.visible_elements[selector].frame_ref, capture.frame_ref)
                self.assertFalse(observation.list_entries)
                self.assertEqual(backend.regions, [Bounds(16, 134, 508, 586)])

    def test_campaign_ocr_regions_scale_reference_geometry(self) -> None:
        """Scale the reviewed Campaign regions without changing their native reference geometry."""

        self.assertEqual(CAMPAIGN_REFERENCE_SIZE, (540, 960))
        self.assertEqual(
            scale_campaign_bounds(CAMPAIGN_MAP_CHAPTER_ROW, (900, 1600)),
            Bounds(323, 757, 252, 83),
        )
        self.assertEqual(
            scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, CAMPAIGN_REFERENCE_SIZE),
            CAMPAIGN_CHAPTER_TITLE_REGION,
        )
        with self.assertRaisesRegex(ValueError, "positive image dimensions"):
            scale_campaign_bounds(CAMPAIGN_MAP_CHAPTER_ROW, (0, 960))

    def test_benchmark_wrapper_preserves_owned_detail_close(self) -> None:
        """Timing instrumentation must retain the production guard contract."""
        from tools.benchmark_screen_recognition import _instrument_builder

        builder, probe = _instrument_builder(_builder((
            OcrLine("[10-3] Grandia Ruins", Bounds(142, 211, 256, 27), 1.0),
            OcrLine("Challenge", Bounds(216, 666, 109, 25), 1.0),
        )))
        observation = builder.build(_capture(_image("campaign_stage_10_3.png")))
        self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertIsNotNone(probe)
        self.assertGreater(probe.guard_calls, 0)

    def test_campaign_profiles_expose_their_measured_controls(self) -> None:
        recognizer = load_visual_screen_recognizer()
        expected = {
            "campaign_map.png": (
                ScreenType.PNC_CAMPAIGN_MAP,
                {UiElementId.PNC_CAMPAIGN_HOME_PORTAL},
            ),
            "campaign_chapter_10.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {
                    UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
                    UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE,
                },
            ),
            "campaign_stage_10_3.png": (
                ScreenType.PNC_CAMPAIGN_STAGE,
                {
                    UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
                    UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
                },
            ),
        }
        for name, (screen, selectors) in expected.items():
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name))
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
                self.assertEqual({item.selector_id for item in result.controls}, selectors)
                self.assertTrue(
                    all(item.source_kind is VisibleElementSourceKind.TEMPLATE for item in result.controls)
                )
                if screen is ScreenType.PNC_CAMPAIGN_STAGE:
                    self.assertEqual(
                        {item.selector_id for item in result.dismiss_controls},
                        {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
                    )
                else:
                    self.assertEqual(result.dismiss_controls, ())

    def test_campaign_profiles_are_mutually_exclusive_at_reference_and_scaled_sizes(self) -> None:
        recognizer = load_visual_screen_recognizer()
        expected = {
            "campaign_map.png": (ScreenType.PNC_CAMPAIGN_MAP, UiElementId.PNC_CAMPAIGN_HOME_PORTAL),
            "campaign_chapter_10.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {
                    UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
                    UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE,
                },
            ),
            "campaign_stage_10_3.png": (
                ScreenType.PNC_CAMPAIGN_STAGE,
                {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON, UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON},
            ),
        }
        for name, (screen, selector) in expected.items():
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name).resize((900, 1600)))
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
                expected_selectors = selector if isinstance(selector, set) else {selector}
                self.assertEqual({item.selector_id for item in result.controls}, expected_selectors)

    def test_campaign_detail_close_and_challenge_are_owned_controls(self) -> None:
        recognizer = load_visual_screen_recognizer()
        result = recognizer.recognize(_image("campaign_stage_10_3.png"))
        self.assertEqual(
            {item.selector_id for item in result.dismiss_controls},
            {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
        )
        self.assertIn(
            UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
            {item.selector_id for item in result.controls},
        )
        stage_profile = next(profile for profile in recognizer.profiles if profile.id == "campaign_stage_10_3")
        close_control = next(
            control
            for control in stage_profile.controls
            if control.selector_id is UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON
        )
        self.assertTrue(close_control.dismisses_surface)

    def test_campaign_challenge_removal_preserves_stage_identity_without_control(self) -> None:
        recognizer = load_visual_screen_recognizer()
        image = _image("campaign_stage_10_3.png")
        image.paste((0, 0, 0), (178, 643, 362, 697))

        result = recognizer.recognize(image)

        self.assertEqual({item.screen_type for item in result.evidence}, {ScreenType.PNC_CAMPAIGN_STAGE})
        self.assertEqual(
            {item.selector_id for item in result.controls},
            {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
        )
        self.assertEqual(
            {item.selector_id for item in result.dismiss_controls},
            {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
        )

    def test_campaign_challenge_uses_measured_geometry_at_both_viewports(self) -> None:
        recognizer = load_visual_screen_recognizer()
        control = next(
            item
            for item in recognizer.recognize(_image("campaign_stage_10_3.png")).controls
            if item.selector_id is UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON
        )
        self.assertEqual(control.bounds, CAMPAIGN_CHALLENGE_BOX)
        self.assertTrue(CAMPAIGN_CHALLENGE_BOX.contains_point(control.action_point or control.bounds.center()))

        scaled = recognizer.recognize(_image("campaign_stage_10_3.png").resize((900, 1600)))
        scaled_control = next(
            item
            for item in scaled.controls
            if item.selector_id is UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON
        )
        self.assertEqual(scaled_control.bounds, Bounds(297, 1072, 306, 90))
        self.assertTrue(
            scaled_control.bounds.contains_point(scaled_control.action_point or scaled_control.bounds.center())
        )

    def test_campaign_enricher_publishes_only_observed_rows_without_mode(self) -> None:
        map_lines = (
            OcrLine("10", Bounds(205, 473, 22, 14), 1.0),
            OcrLine("Grandia Ruins", Bounds(236, 472, 106, 17), 1.0),
        )
        map_observation = _builder(map_lines).build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(map_observation.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        self.assertEqual(len(map_observation.entries(ListEntryKind.CAMPAIGN_CHAPTER)), 1)
        chapter = map_observation.entries(ListEntryKind.CAMPAIGN_CHAPTER)[0]
        self.assertEqual(chapter.title_text, "10 Grandia Ruins")
        self.assertEqual(chapter.metadata, {"chapter_number": 10})
        self.assertNotIn("mode", chapter.metadata)
        self.assertEqual(chapter.bounds, CAMPAIGN_MAP_CHAPTER_ROW)
        self.assertEqual(chapter.action_bounds, CAMPAIGN_MAP_CHAPTER_ROW)
        self.assertEqual(chapter.action_point, CAMPAIGN_MAP_CHAPTER_ROW.center())
        self.assertEqual(chapter.source_screen, ScreenType.PNC_CAMPAIGN_MAP)
        self.assertEqual(chapter.source_layout_id, "campaign_map")
        self.assertEqual(chapter.frame_ref, map_observation.frame_ref)

        chapter_lines = (
            OcrLine("Ch.10 Grandia Ruins", Bounds(230, 55, 295, 30), 1.0),
        )
        chapter_observation = _builder(chapter_lines).build(
            _capture(_image("campaign_chapter_10.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(chapter_observation.screen_type, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertEqual(len(chapter_observation.entries(ListEntryKind.CAMPAIGN_STAGE)), 1)
        stage = chapter_observation.entries(ListEntryKind.CAMPAIGN_STAGE)[0]
        self.assertEqual(stage.title_text, "3")
        self.assertEqual(stage.metadata, {"chapter_number": 10, "stage_number": 3})
        self.assertNotIn("mode", stage.metadata)
        self.assertEqual(stage.bounds, CAMPAIGN_CHAPTER_STAGE_THREE_ROW)
        self.assertEqual(stage.action_bounds, CAMPAIGN_CHAPTER_STAGE_THREE_ROW)
        self.assertEqual(stage.action_point, CAMPAIGN_CHAPTER_STAGE_THREE_ROW.center())
        self.assertEqual(stage.source_screen, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertEqual(stage.source_layout_id, "campaign_chapter_10")
        self.assertEqual(stage.frame_ref, chapter_observation.frame_ref)
        self.assertTrue(chapter_observation.has(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE))
        chapter_control = chapter_observation.visible_elements[UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE]
        self.assertEqual(chapter_control.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(chapter_control.source_screen, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertEqual(chapter_control.source_layout_id, "campaign_chapter_10")
        self.assertEqual(chapter_control.frame_ref, chapter_observation.frame_ref)

    def test_campaign_paths_use_bounded_ocr_and_retain_native_rows(self) -> None:
        """Both observation paths keep Campaign rows while using only their semantic OCR crops."""

        cases = (
            (
                "campaign_map.png",
                (
                    OcrLine("10", Bounds(205, 473, 22, 14), 1.0),
                    OcrLine("Grandia Ruins", Bounds(236, 472, 106, 17), 1.0),
                ),
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                CAMPAIGN_MAP_CHAPTER_ROW,
                "campaign_map",
            ),
            (
                "campaign_chapter_10.png",
                (OcrLine("Ch.10 Grandia Ruins", Bounds(230, 55, 295, 30), 1.0),),
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                CAMPAIGN_CHAPTER_STAGE_THREE_ROW,
                "campaign_chapter_10",
            ),
        )
        for name, lines, expected_screen, entry_kind, expected_row, layout_id in cases:
            with self.subTest(path="builder", name=name):
                backend = _CampaignCropOcrService(lines)
                builder = _builder_with_backend(backend)
                capture = _capture(_image(name))
                context = ObservationOcrContext(
                    capture.image,
                    backend,
                    capture.frame_ref,
                    "campaign-visual-test",
                )
                observation = builder.build(
                    capture,
                    request=ObservationRequest.campaign_map_follow_up(),
                    ocr_context=context,
                )
                self.assertEqual(observation.screen_type, expected_screen)
                entries = observation.entries(entry_kind)
                self.assertEqual(len(entries), 1)
                entry = entries[0]
                self.assertEqual(entry.bounds, expected_row)
                self.assertEqual(entry.action_bounds, expected_row)
                self.assertEqual(entry.source_screen, expected_screen)
                self.assertEqual(entry.source_layout_id, layout_id)
                self.assertEqual(entry.frame_ref, capture.frame_ref)
                self.assertTrue(backend.regions)
                self.assertTrue(all(region is not None for region in backend.regions))
                expected_ocr_region = (
                    CAMPAIGN_MAP_CHAPTER_ROW
                    if expected_screen is ScreenType.PNC_CAMPAIGN_MAP
                    else CAMPAIGN_CHAPTER_TITLE_REGION
                )
                self.assertIn(expected_ocr_region, backend.regions)

            with self.subTest(path="navigation", name=name):
                backend = _CampaignCropOcrService(lines)
                capture = _capture(_image(name))
                observation = _navigation_perception_with_backend(backend).build(
                    capture,
                    include_content=True,
                )
                self.assertEqual(observation.screen_type, expected_screen)
                entries = observation.entries(entry_kind)
                self.assertEqual(len(entries), 1)
                entry = entries[0]
                self.assertEqual(entry.bounds, expected_row)
                self.assertEqual(entry.action_bounds, expected_row)
                self.assertEqual(entry.source_screen, expected_screen)
                self.assertEqual(entry.source_layout_id, layout_id)
                self.assertEqual(entry.frame_ref, capture.frame_ref)
                self.assertTrue(backend.regions)
                self.assertTrue(all(region is not None for region in backend.regions))
                expected_ocr_region = (
                    CAMPAIGN_MAP_CHAPTER_ROW
                    if expected_screen is ScreenType.PNC_CAMPAIGN_MAP
                    else CAMPAIGN_CHAPTER_TITLE_REGION
                )
                self.assertIn(expected_ocr_region, backend.regions)

    def test_campaign_chapter_is_in_the_narrow_and_full_runtime_ocr_scopes(self) -> None:
        follow_up = ObservationRequest.campaign_map_follow_up()
        self.assertIn(ScreenType.PNC_CAMPAIGN_CHAPTER, follow_up.candidate_screen_types)
        self.assertIn(ScreenType.PNC_CAMPAIGN_CHAPTER, follow_up.ocr_screen_types)
        self.assertIn(ScreenType.PNC_CAMPAIGN_CHAPTER, ObservationRequest.full_runtime_default().ocr_screen_types)

    def test_navigation_perception_publishes_campaign_rows_with_provenance(self) -> None:
        cases = (
            (
                "campaign_map.png",
                (
                    OcrLine("10", Bounds(205, 473, 22, 14), 1.0),
                    OcrLine("Grandia Ruins", Bounds(236, 472, 106, 17), 1.0),
                ),
                ListEntryKind.CAMPAIGN_CHAPTER,
                ScreenType.PNC_CAMPAIGN_MAP,
                "campaign_map",
            ),
            (
                "campaign_chapter_10.png",
                (OcrLine("Ch.10 Grandia Ruins", Bounds(230, 55, 295, 30), 1.0),),
                ListEntryKind.CAMPAIGN_STAGE,
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                "campaign_chapter_10",
            ),
        )
        for name, lines, kind, screen, layout_id in cases:
            with self.subTest(name=name):
                capture = _capture(_image(name))
                observation = _navigation_perception(lines).build(capture, include_content=True)
                entries = observation.entries(kind)
                self.assertEqual(observation.screen_type, screen)
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0].source_screen, screen)
                self.assertEqual(entries[0].source_layout_id, layout_id)
                self.assertEqual(entries[0].frame_ref, capture.frame_ref)
                self.assertNotIn("mode", entries[0].metadata)
                if screen is ScreenType.PNC_CAMPAIGN_CHAPTER:
                    self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE))
                    control = observation.visible_elements[UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE]
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.TEMPLATE)
                    self.assertEqual(control.source_screen, screen)
                    self.assertEqual(control.source_layout_id, layout_id)
                    self.assertEqual(control.frame_ref, capture.frame_ref)

    def test_campaign_content_abstains_without_exact_title_or_header(self) -> None:
        missing_map_title = _builder().build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(missing_map_title.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        self.assertFalse(missing_map_title.entries(ListEntryKind.CAMPAIGN_CHAPTER))

        missing_stage_badge = _image("campaign_chapter_10.png")
        missing_stage_badge.paste((0, 0, 0), (301, 591, 351, 644))
        missing_chapter_stage = _builder(
            (
                OcrLine("Ch.10 Grandia Ruins", Bounds(230, 55, 295, 30), 1.0),
                OcrLine("3", Bounds(318, 606, 18, 28), 1.0),
            )
        ).build(
            _capture(missing_stage_badge),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertIn(missing_chapter_stage.screen_type, {ScreenType.UNKNOWN, ScreenType.PNC_CAMPAIGN_CHAPTER})
        self.assertFalse(missing_chapter_stage.entries(ListEntryKind.CAMPAIGN_STAGE))
        self.assertFalse(missing_chapter_stage.has(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE))

        partial_stage_badge = _image("campaign_chapter_10.png")
        partial_stage_badge.paste((0, 0, 0), (321, 608, 337, 628))
        partial_chapter_stage = _builder(
            (
                OcrLine("Ch.10 Grandia Ruins", Bounds(230, 55, 295, 30), 1.0),
                OcrLine("3", Bounds(318, 606, 18, 28), 1.0),
            )
        ).build(
            _capture(partial_stage_badge),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertIn(partial_chapter_stage.screen_type, {ScreenType.UNKNOWN, ScreenType.PNC_CAMPAIGN_CHAPTER})
        self.assertFalse(partial_chapter_stage.entries(ListEntryKind.CAMPAIGN_STAGE))
        self.assertFalse(partial_chapter_stage.has(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE))

        foreign_map_title = _builder(
            (
                OcrLine("10", Bounds(10, 473, 22, 14), 1.0),
                OcrLine("Grandia Ruins", Bounds(41, 472, 106, 17), 1.0),
            )
        ).build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(foreign_map_title.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        self.assertFalse(foreign_map_title.entries(ListEntryKind.CAMPAIGN_CHAPTER))

        foreign_stage_content = _builder(
            (OcrLine("10 Grandia Ruins", Bounds(237, 473, 105, 15), 1.0),)
        ).build(
            _capture(_image("campaign_stage_10_3.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertNotIn(
            foreign_stage_content.screen_type,
            {ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_CHAPTER},
        )
        self.assertFalse(foreign_stage_content.entries(ListEntryKind.CAMPAIGN_CHAPTER))
        self.assertFalse(foreign_stage_content.entries(ListEntryKind.CAMPAIGN_STAGE))

    def test_campaign_blocking_overlay_suppresses_background_controls_and_rows(self) -> None:
        image = with_update_modal(_image("campaign_stage_10_3.png"))
        popup_lines = update_modal_lines(image.size)
        stage_capture = _capture(image)
        blocked_builder = _builder(popup_lines).build(
            stage_capture,
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(blocked_builder.screen_type, ScreenType.PNC_POPUP)
        self.assertFalse(blocked_builder.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertFalse(blocked_builder.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
        self.assertFalse(blocked_builder.list_entries)

        blocked_navigation = _navigation_perception(popup_lines).build(
            stage_capture,
            include_content=True,
        )
        self.assertEqual(blocked_navigation.screen_type, ScreenType.PNC_POPUP)
        self.assertFalse(blocked_navigation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertFalse(blocked_navigation.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
        self.assertFalse(blocked_navigation.list_entries)

    def test_navigation_perception_keeps_stage_detail_outside_generic_popup_guard(self) -> None:
        """The owned stage Close is passed to popup detection without making it a popup."""

        capture = _capture(_image("campaign_stage_10_3.png"))
        stage_lines = (
            OcrLine("[10-3] Grandia Ruins", Bounds(142, 211, 256, 27), 1.0),
            OcrLine("Enemylineup", Bounds(209, 271, 117, 20), 1.0),
            OcrLine("150/120", Bounds(379, 593, 78, 20), 1.0),
            OcrLine("Challenge", Bounds(216, 666, 109, 25), 1.0),
        )
        perception = _navigation_perception(stage_lines)

        result = perception.build(capture)

        self.assertEqual(result.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertFalse(result.blocking_popup)
        self.assertTrue(result.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
        self.assertTrue(result.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertFalse(result.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
        self.assertEqual(result.decision.guard.value, "clear")

        builder_result = _builder(stage_lines).build(
            capture,
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(builder_result.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertFalse(builder_result.blocking_popup)
        self.assertTrue(builder_result.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
        self.assertTrue(builder_result.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertFalse(builder_result.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
        self.assertEqual(builder_result.decision.guard.value, "clear")

    def test_owned_stage_close_does_not_hide_an_additional_unowned_close(self) -> None:
        """A measured detail dismiss control cannot clear another surface's X."""

        image = _image("campaign_stage_10_3.png")
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((465, 300, 510, 345), fill=(15, 28, 68))
        drawing.line((474, 309, 501, 336), fill=(255, 247, 218), width=5)
        drawing.line((501, 309, 474, 336), fill=(255, 247, 218), width=5)
        self.assertTrue(load_visual_screen_recognizer().recognize(image).dismiss_controls)
        lines = (OcrLine("[10-3] Grandia Ruins", Bounds(142, 211, 256, 27), 1.0),)
        capture = _capture(image)

        for index, observation in enumerate((
            _builder(lines).build(capture),
            _navigation_perception(lines).build(capture),
        )):
            with self.subTest(path=index):
                self.assertNotEqual(observation.decision.guard.value, "clear")
                self.assertFalse(observation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))

    def test_campaign_registry_and_reviewed_edges_are_canonical(self) -> None:
        registry = build_default_selector_registry()
        stage_node = registry.require(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE)
        self.assertEqual(stage_node.status.value, "planned")
        self.assertEqual(stage_node.detection_kind, DetectionKind.SEMANTIC)
        self.assertEqual(stage_node.interaction_kind, SelectorInteractionKind.ACTION)
        self.assertFalse(stage_node.materialize_relative_bounds)

        battle = registry.require(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON)
        self.assertEqual(battle.status.value, "planned")
        self.assertEqual(battle.detection_kind, DetectionKind.SEMANTIC)
        self.assertEqual(battle.interaction_kind, SelectorInteractionKind.ACTION)
        self.assertFalse(battle.materialize_relative_bounds)
        stage_profile = next(
            profile for profile in load_visual_screen_recognizer().profiles if profile.id == "campaign_stage_10_3"
        )
        challenge_anchor = next(
            control.anchor
            for control in stage_profile.controls
            if control.selector_id is UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON
        )
        self.assertEqual(challenge_anchor.search_region, CAMPAIGN_CHALLENGE_BOX)
        entry = registry.require(UiElementId.PNC_CAMPAIGN_ENTRY_BUTTON)
        self.assertEqual(entry.detection_kind, DetectionKind.UNSUPPORTED)
        selector = registry.require(UiElementId.PNC_CAMPAIGN_HOME_PORTAL)
        self.assertEqual(selector.interaction_kind, SelectorInteractionKind.NAVIGATION)
        self.assertEqual(selector.click_outcomes[0].target_screen, ScreenType.PNC_HOME_CITY)
        self.assertTrue(selector.click_outcomes[0].safe_to_click)
        self.assertFalse(selector.click_outcomes[0].monetized)
        self.assertIn(
            (
                ScreenType.PNC_CAMPAIGN_MAP,
                UiElementId.PNC_CAMPAIGN_HOME_PORTAL,
                frozenset({ScreenType.PNC_HOME_CITY}),
            ),
            tuple((edge.source, edge.selector, edge.destinations) for edge in reviewed_navigation_edges()),
        )

        expected_returns = (
            (
                UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ScreenType.PNC_CAMPAIGN_MAP,
            ),
            (
                UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
                ScreenType.PNC_CAMPAIGN_STAGE,
                ScreenType.PNC_CAMPAIGN_CHAPTER,
            ),
        )
        edges = tuple((edge.source, edge.selector, edge.destinations) for edge in reviewed_navigation_edges())
        registry = build_default_selector_registry()
        for selector_id, source, destination in expected_returns:
            with self.subTest(selector=selector_id):
                definition = registry.require(selector_id)
                self.assertEqual(definition.interaction_kind, SelectorInteractionKind.NAVIGATION)
                self.assertEqual(definition.click_outcomes[0].target_screen, destination)
                self.assertTrue(definition.click_outcomes[0].safe_to_click)
                self.assertFalse(definition.click_outcomes[0].monetized)
                self.assertIn((source, selector_id, frozenset({destination})), edges)

    def test_campaign_fixture_and_challenge_provenance_are_explicit(self) -> None:
        manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        samples = {sample["image"]: sample for sample in manifest["samples"]}
        provenance = json.loads((FIXTURES / "replacement_core_provenance.json").read_text(encoding="utf-8"))
        by_asset = {item["asset"]: item for item in provenance}
        recognizer = load_visual_screen_recognizer()
        stage = next(profile for profile in recognizer.profiles if profile.id == "campaign_stage_10_3")
        sample = samples[Path(stage.source.fixture).name]
        self.assertEqual(sample["sha256"], stage.source.decoded_sha256)
        self.assertEqual(sample["group"], stage.source.capture_group)
        self.assertEqual(sample["split"], "reference")
        challenge = by_asset["screen_anchors/campaign_challenge_button.png"]
        self.assertEqual(challenge["reference_size"], [540, 960])
        self.assertEqual(challenge["crop"], [178, 643, 362, 697])
        self.assertEqual(challenge["capture_group"], stage.source.capture_group)
        self.assertEqual(challenge["source_sha256"], by_asset["tests/data/screen_recognition/campaign_stage_10_3.png"]["source_sha256"])
        stage_three = by_asset["screen_anchors/campaign_stage_three.png"]
        self.assertEqual(stage_three["reference_size"], [540, 960])
        self.assertEqual(stage_three["crop"], [301, 591, 351, 644])
        self.assertEqual(stage_three["capture_group"], "2026-09-12/serious_stuff/campaign_navigation")
        self.assertEqual(
            stage_three["source_sha256"],
            by_asset["tests/data/screen_recognition/campaign_chapter_10.png"]["source_sha256"],
        )

    def test_campaign_anchor_gate_fails_closed_when_identity_is_partial(self) -> None:
        recognizer = load_visual_screen_recognizer()
        mutations = (
            ("campaign_map.png", (180, 220, 350, 350)),
            ("campaign_chapter_10.png", (205, 38, 530, 98)),
            ("campaign_stage_10_3.png", (120, 201, 420, 250)),
        )
        for name, box in mutations:
            with self.subTest(name=name):
                image = _image(name)
                image.paste((0, 0, 0), box)
                self.assertEqual(recognizer.recognize(image).evidence, ())


if __name__ == "__main__":
    unittest.main()
