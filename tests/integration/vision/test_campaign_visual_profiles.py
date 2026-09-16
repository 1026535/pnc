"""Reviewed visual recognition contracts for Campaign navigation surfaces."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.automation.engine.navigation_core import reviewed_navigation_edges
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    RowRecognitionStatus,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.campaign_ocr_regions import (
    CAMPAIGN_CHAPTER_TITLE_REGION,
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
from tests.support.pnc.capture_vision.require_rapid_ocr_service import (
    _require_rapid_ocr_service,
)


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
        enricher=PncObservationEnricher(selector_registry=registry, template_matcher=matcher),
        ocr_service=_RecordingOcrService(lines=ocr_lines),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )


def _navigation_perception(ocr_lines: tuple[OcrLine, ...] = ()) -> NavigationPerception:
    """Wire NavigationPerception to the same registry and controlled OCR."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    ocr = _FakeOcrService(lines=ocr_lines)
    return NavigationPerception(
        load_visual_screen_recognizer(matcher=matcher),
        PncObservationEnricher(selector_registry=registry, template_matcher=matcher),
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
        enricher=PncObservationEnricher(selector_registry=registry, template_matcher=matcher),
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )


def _navigation_perception_with_backend(ocr_service: _CampaignCropOcrService) -> NavigationPerception:
    """Wire replacement perception to one crop-aware OCR backend."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return NavigationPerception(
        load_visual_screen_recognizer(matcher=matcher),
        PncObservationEnricher(selector_registry=registry, template_matcher=matcher),
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

    def test_persisted_southern_map_view_has_owned_home_return_on_both_paths(self) -> None:
        """The live reopened map needs its measured portal and only honest rows."""
        image = _image("campaign_map_southern_view_20260916.png")
        expected_counts = {(540, 960): (1, 2), (900, 1600): (2, 2)}
        for size in ((540, 960), (900, 1600)):
            capture = _capture(image.resize(size, Image.Resampling.LANCZOS))
            for path in ("builder", "navigation"):
                with self.subTest(size=size, path=path):
                    observation = (
                        _builder().build(capture)
                        if path == "builder"
                        else _navigation_perception().build(capture, include_content=True)
                    )
                    self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, observation.screen_type)
                    control = observation.get(UiElementId.PNC_CAMPAIGN_HOME_PORTAL)
                    self.assertIsNotNone(control)
                    self.assertEqual(VisibleElementSourceKind.TEMPLATE, control.source_kind)
                    self.assertEqual(capture.frame_ref, control.frame_ref)
                    rows = observation.entries(ListEntryKind.CAMPAIGN_CHAPTER)
                    clipped = [
                        row for row in rows if row.row_status is RowRecognitionStatus.CLIPPED
                    ]
                    unreadable = [
                        row for row in rows if row.row_status is RowRecognitionStatus.UNREADABLE
                    ]
                    expected_clipped, expected_unreadable = expected_counts[size]
                    self.assertEqual(expected_clipped, len(clipped))
                    self.assertEqual(expected_unreadable, len(unreadable))
                    for row in rows:
                        self.assertIsNone(row.action_point)
                        self.assertIsNone(row.action_bounds)
                        self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, row.source_screen)
                        self.assertEqual("campaign_map", row.source_layout_id)
                        self.assertEqual(capture.frame_ref, row.frame_ref)
                    for row in unreadable:
                        self.assertIs(row.campaign_node.locked, False)
                        self.assertIsNone(row.campaign_node.chapter_number)
        # One isolated chapter label cannot qualify this appearance.
        erased = image.copy()
        ImageDraw.Draw(erased).rectangle((85, 350, 260, 413), fill=(0, 0, 0))
        recognition = load_visual_screen_recognizer().recognize(erased)
        self.assertNotIn("campaign_map_southern_view", recognition.profile_ids)

    def test_stage_content_request_preserves_controls_without_unused_body_ocr(self) -> None:
        """A recognized stage skips popup guard OCR while retaining measured controls."""
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
                self.assertEqual(backend.regions, [])

    def test_campaign_ocr_regions_scale_reference_geometry(self) -> None:
        """Scale the reviewed Campaign regions without changing their native reference geometry."""

        self.assertEqual(CAMPAIGN_REFERENCE_SIZE, (540, 960))
        self.assertEqual(
            scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, (900, 1600)),
            Bounds(342, 63, 542, 100),
        )
        self.assertEqual(
            scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, CAMPAIGN_REFERENCE_SIZE),
            CAMPAIGN_CHAPTER_TITLE_REGION,
        )
        with self.assertRaisesRegex(ValueError, "positive image dimensions"):
            scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, (0, 960))

    def test_benchmark_wrapper_preserves_owned_detail_close(self) -> None:
        """Timing instrumentation forwards the base-first visual contract."""
        from tools.benchmark_screen_recognition import _instrument_builder

        builder, probe = _instrument_builder(_builder((
            OcrLine("[10-3] Grandia Ruins", Bounds(142, 211, 256, 27), 1.0),
            OcrLine("Challenge", Bounds(216, 666, 109, 25), 1.0),
        )))
        observation = builder.build(_capture(_image("campaign_stage_10_3.png")))
        self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertIsNotNone(probe)
        self.assertEqual(probe.guard_calls, 0)

    def test_campaign_profiles_expose_their_measured_controls(self) -> None:
        recognizer = load_visual_screen_recognizer()
        expected = {
            "campaign_map.png": (
                ScreenType.PNC_CAMPAIGN_MAP,
                {UiElementId.PNC_CAMPAIGN_HOME_PORTAL},
            ),
            "campaign_map_chapter_6.png": (
                ScreenType.PNC_CAMPAIGN_MAP,
                {UiElementId.PNC_CAMPAIGN_HOME_PORTAL},
            ),
            "campaign_map_chapter_6_pulse.png": (
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
            "campaign_chapter_10_unmasked.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {
                    UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
                    UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE,
                },
            ),
            "campaign_chapter_6_path.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
            ),
            "campaign_chapter_6_path_return.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
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
            "campaign_map.png": (ScreenType.PNC_CAMPAIGN_MAP, {UiElementId.PNC_CAMPAIGN_HOME_PORTAL}),
            "campaign_map_chapter_6.png": (
                ScreenType.PNC_CAMPAIGN_MAP,
                {UiElementId.PNC_CAMPAIGN_HOME_PORTAL},
            ),
            "campaign_map_chapter_6_pulse.png": (
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
            "campaign_chapter_10_unmasked.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {
                    UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
                    UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE,
                },
            ),
            "campaign_chapter_6_path.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
            ),
            "campaign_chapter_6_path_return.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
            ),
            "campaign_stage_10_3.png": (
                ScreenType.PNC_CAMPAIGN_STAGE,
                {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON, UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON},
            ),
        }
        for name, (screen, expected_selectors) in expected.items():
            with self.subTest(name=name):
                image = _image(name)
                alternate = image.resize((900, 1600) if image.size == (540, 960) else (540, 960))
                result = recognizer.recognize(alternate)
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
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

    def test_campaign_producer_publishes_typed_rows_with_provenance(self) -> None:
        """Map and chapter frames publish only evidence-backed typed node facts."""

        map_lines = (
            OcrLine("10", Bounds(205, 468, 20, 16), 1.0),
            OcrLine("Grandia Ruins", Bounds(235, 470, 107, 20), 1.0),
        )
        map_observation = _builder(map_lines).build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(map_observation.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        self.assertIsNone(map_observation.campaign_chapter)
        chapters = map_observation.entries(ListEntryKind.CAMPAIGN_CHAPTER)
        self.assertEqual(len(chapters), 2)
        unreadable = next(
            entry for entry in chapters if entry.row_status is RowRecognitionStatus.UNREADABLE
        )
        self.assertIsNotNone(unreadable.campaign_node)
        self.assertIsNone(unreadable.campaign_node.chapter_number)
        self.assertIs(unreadable.campaign_node.locked, False)
        self.assertIsNone(unreadable.action_point)
        self.assertEqual(unreadable.metadata, {})
        complete = next(
            entry for entry in chapters if entry.row_status is RowRecognitionStatus.COMPLETE
        )
        self.assertEqual(complete.campaign_node.chapter_number, 10)
        self.assertEqual(complete.campaign_node.name, "Grandia Ruins")
        self.assertIs(complete.campaign_node.locked, False)
        self.assertIsNone(complete.campaign_node.mode)
        self.assertEqual(complete.metadata, {"chapter_number": 10})
        self.assertIsNotNone(complete.action_point)
        self.assertTrue(complete.action_bounds.contains_point(complete.action_point))
        self.assertTrue(complete.bounds.contains_bounds(complete.action_bounds))
        for entry in chapters:
            self.assertEqual(entry.source_screen, ScreenType.PNC_CAMPAIGN_MAP)
            self.assertEqual(entry.source_layout_id, "campaign_map")
            self.assertEqual(entry.frame_ref, map_observation.frame_ref)

        chapter_lines = (
            OcrLine("Ch.10 C", Bounds(224, 50, 140, 39), 1.0),
            OcrLine("Grandia Ruins", Bounds(368, 50, 160, 39), 1.0),
            OcrLine("3", Bounds(315, 610, 15, 20), 1.0),
        )
        chapter_observation = _builder(chapter_lines).build(
            _capture(_image("campaign_chapter_10.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(chapter_observation.screen_type, ScreenType.PNC_CAMPAIGN_CHAPTER)
        identity = chapter_observation.campaign_chapter
        self.assertIsNotNone(identity)
        self.assertEqual(identity.chapter_number, 10)
        self.assertEqual(identity.source_screen, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertEqual(identity.source_layout_id, "campaign_chapter_10")
        self.assertEqual(identity.frame_ref, chapter_observation.frame_ref)
        stages = chapter_observation.entries(ListEntryKind.CAMPAIGN_STAGE)
        self.assertEqual(len(stages), 9)
        locked = [
            entry for entry in stages if entry.row_status is RowRecognitionStatus.NO_ACTION
        ]
        self.assertEqual(len(locked), 6)
        for entry in locked:
            self.assertIs(entry.campaign_node.locked, True)
            self.assertEqual(entry.campaign_node.chapter_number, 10)
            self.assertIsNone(entry.campaign_node.stage_number)
            self.assertIsNone(entry.action_point)
        unreadable_stages = [
            entry for entry in stages if entry.row_status is RowRecognitionStatus.UNREADABLE
        ]
        self.assertEqual(len(unreadable_stages), 2)
        for entry in unreadable_stages:
            self.assertIs(entry.campaign_node.locked, False)
            self.assertIsNone(entry.campaign_node.stage_number)
            self.assertIsNone(entry.action_point)
        stage_three = next(
            entry for entry in stages if entry.row_status is RowRecognitionStatus.COMPLETE
        )
        self.assertEqual(stage_three.campaign_node.chapter_number, 10)
        self.assertEqual(stage_three.campaign_node.stage_number, 3)
        self.assertIs(stage_three.campaign_node.locked, False)
        self.assertEqual(
            stage_three.metadata, {"chapter_number": 10, "stage_number": 3}
        )
        self.assertNotIn("mode", stage_three.metadata)
        self.assertIsNotNone(stage_three.action_point)
        self.assertTrue(stage_three.action_bounds.contains_point(stage_three.action_point))
        for entry in stages:
            self.assertEqual(entry.source_screen, ScreenType.PNC_CAMPAIGN_CHAPTER)
            self.assertEqual(entry.source_layout_id, "campaign_chapter_10")
            self.assertEqual(entry.frame_ref, chapter_observation.frame_ref)
        self.assertTrue(chapter_observation.has(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE))
        chapter_control = chapter_observation.visible_elements[UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE]
        self.assertEqual(chapter_control.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(chapter_control.source_screen, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertEqual(chapter_control.source_layout_id, "campaign_chapter_10")
        self.assertEqual(chapter_control.frame_ref, chapter_observation.frame_ref)

    def test_campaign_paths_use_bounded_ocr_and_retain_native_rows(self) -> None:
        """Both observation paths keep typed Campaign rows using only candidate-local reads."""

        cases = (
            (
                "campaign_map.png",
                (
                    OcrLine("10", Bounds(205, 468, 20, 16), 1.0),
                    OcrLine("Grandia Ruins", Bounds(235, 470, 107, 20), 1.0),
                ),
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map",
            ),
            (
                "campaign_chapter_10.png",
                (
                    OcrLine("Ch.10 C", Bounds(224, 50, 140, 39), 1.0),
                    OcrLine("Grandia Ruins", Bounds(368, 50, 160, 39), 1.0),
                ),
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                "campaign_chapter_10",
            ),
        )
        for name, lines, expected_screen, entry_kind, layout_id in cases:
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
                self.assertTrue(entries)
                for entry in entries:
                    self.assertEqual(entry.source_screen, expected_screen)
                    self.assertEqual(entry.source_layout_id, layout_id)
                    self.assertEqual(entry.frame_ref, capture.frame_ref)
                self.assertTrue(backend.regions)
                self.assertTrue(all(region is not None for region in backend.regions))
                self.assertTrue(
                    all(
                        Bounds(0, 0, *capture.image.size).contains_bounds(region)
                        for region in backend.regions
                    )
                )
                if expected_screen is ScreenType.PNC_CAMPAIGN_CHAPTER:
                    self.assertIn(CAMPAIGN_CHAPTER_TITLE_REGION, backend.regions)
                    self.assertIsNotNone(observation.campaign_chapter)
                else:
                    badge_disc = Bounds(196, 458, 39, 39)
                    self.assertTrue(
                        any(
                            badge_disc.contains_bounds(region)
                            for region in backend.regions
                        ),
                        "map producer must read the badge numeral inside its disc",
                    )

            with self.subTest(path="navigation", name=name):
                backend = _CampaignCropOcrService(lines)
                capture = _capture(_image(name))
                observation = _navigation_perception_with_backend(backend).build(
                    capture,
                    include_content=True,
                )
                self.assertEqual(observation.screen_type, expected_screen)
                entries = observation.entries(entry_kind)
                self.assertTrue(entries)
                for entry in entries:
                    self.assertEqual(entry.source_screen, expected_screen)
                    self.assertEqual(entry.source_layout_id, layout_id)
                    self.assertEqual(entry.frame_ref, capture.frame_ref)
                self.assertTrue(backend.regions)
                self.assertTrue(all(region is not None for region in backend.regions))
                if expected_screen is ScreenType.PNC_CAMPAIGN_CHAPTER:
                    self.assertIn(CAMPAIGN_CHAPTER_TITLE_REGION, backend.regions)
                    self.assertIsNotNone(observation.campaign_chapter)

    def test_real_ocr_binds_current_typed_rows_on_both_publishers(self) -> None:
        """RapidOCR 3.4.5 proves the measured chapter/stage ordinals end to end."""
        backend = _require_rapid_ocr_service(self)
        cases = (
            (
                "campaign_map.png",
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map",
                {9, 10},
                (),
                None,
            ),
            (
                "campaign_map_chapter_6.png",
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map_chapter_6",
                {4, 5, 6},
                {7, 8, 9},
                None,
            ),
            (
                "campaign_map_chapter_6_pulse.png",
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map_chapter_6",
                {4, 5, 6},
                None,
                None,
            ),
            (
                "campaign_map_southern_view_20260916.png",
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map",
                {2, 5},
                (),
                None,
            ),
            (
                "campaign_chapter_10_unmasked.png",
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                "campaign_chapter_10",
                {1, 2, 3},
                (),
                10,
            ),
            (
                "campaign_chapter_6_path.png",
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                "campaign_chapter_6",
                {1, 2, 3, 4, 5},
                (),
                6,
            ),
            (
                "campaign_chapter_6_path_return.png",
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                "campaign_chapter_6",
                {1, 2, 3, 4, 5},
                (),
                6,
            ),
        )
        for name, screen, kind, layout_id, complete_numbers, locked_numbers, chapter in cases:
            capture = _capture(_image(name))
            for publisher in ("builder", "navigation"):
                with self.subTest(frame=name, publisher=publisher):
                    observation = (
                        _builder_with_backend(backend).build(
                            capture, request=ObservationRequest.campaign_map_follow_up()
                        )
                        if publisher == "builder"
                        else _navigation_perception_with_backend(backend).build(
                            capture, include_content=True
                        )
                    )
                    self.assertEqual(screen, observation.screen_type)
                    rows = observation.entries(kind)
                    complete = [
                        row for row in rows if row.row_status is RowRecognitionStatus.COMPLETE
                    ]
                    number_of = (
                        (lambda row: row.campaign_node.chapter_number)
                        if kind is ListEntryKind.CAMPAIGN_CHAPTER
                        else (lambda row: row.campaign_node.stage_number)
                    )
                    self.assertEqual(
                        complete_numbers, {number_of(row) for row in complete}
                    )
                    for row in complete:
                        self.assertIs(row.campaign_node.locked, False)
                        self.assertIsNone(row.campaign_node.mode)
                        self.assertIsNone(row.campaign_node.completed)
                        self.assertIsNotNone(row.action_point)
                        self.assertTrue(row.bounds.contains_bounds(row.action_bounds))
                        self.assertTrue(row.action_bounds.contains_point(row.action_point))
                    locked = [
                        row for row in rows if row.row_status is RowRecognitionStatus.NO_ACTION
                    ]
                    if locked_numbers:
                        self.assertEqual(
                            locked_numbers, {number_of(row) for row in locked}
                        )
                    for row in locked:
                        self.assertIs(row.campaign_node.locked, True)
                        self.assertIsNone(row.action_point)
                        if kind is ListEntryKind.CAMPAIGN_STAGE:
                            self.assertIsNone(row.campaign_node.stage_number)
                    for row in rows:
                        self.assertEqual(screen, row.source_screen)
                        self.assertEqual(layout_id, row.source_layout_id)
                        self.assertEqual(capture.frame_ref, row.frame_ref)
                    if chapter is not None:
                        self.assertIsNotNone(observation.campaign_chapter)
                        self.assertEqual(chapter, observation.campaign_chapter.chapter_number)
                        self.assertEqual(
                            capture.frame_ref, observation.campaign_chapter.frame_ref
                        )

    def test_real_ocr_binds_scaled_return_path_stage_numbers(self) -> None:
        """The reference-size return frame still resolves every visible stage."""
        backend = _require_rapid_ocr_service(self)
        capture = _capture(
            _image("campaign_chapter_6_path_return.png").resize(
                (540, 960), Image.Resampling.LANCZOS
            )
        )
        for publisher in ("builder", "navigation"):
            with self.subTest(publisher=publisher):
                observation = (
                    _builder_with_backend(backend).build(
                        capture, request=ObservationRequest.campaign_map_follow_up()
                    )
                    if publisher == "builder"
                    else _navigation_perception_with_backend(backend).build(
                        capture, include_content=True
                    )
                )
                self.assertEqual(
                    {1, 2, 3, 4, 5},
                    {
                        row.campaign_node.stage_number
                        for row in observation.entries(ListEntryKind.CAMPAIGN_STAGE)
                        if row.row_status is RowRecognitionStatus.COMPLETE
                    },
                )

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
                    OcrLine("10", Bounds(205, 468, 20, 16), 1.0),
                    OcrLine("Grandia Ruins", Bounds(235, 470, 107, 20), 1.0),
                ),
                ListEntryKind.CAMPAIGN_CHAPTER,
                ScreenType.PNC_CAMPAIGN_MAP,
                "campaign_map",
            ),
            (
                "campaign_chapter_10.png",
                (
                    OcrLine("Ch.10 C", Bounds(224, 50, 140, 39), 1.0),
                    OcrLine("Grandia Ruins", Bounds(368, 50, 160, 39), 1.0),
                ),
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
                self.assertTrue(entries)
                for entry in entries:
                    self.assertIsNotNone(entry.campaign_node)
                    self.assertEqual(entry.source_screen, screen)
                    self.assertEqual(entry.source_layout_id, layout_id)
                    self.assertEqual(entry.frame_ref, capture.frame_ref)
                    self.assertNotIn("mode", entry.metadata)
                if screen is ScreenType.PNC_CAMPAIGN_CHAPTER:
                    self.assertIsNotNone(observation.campaign_chapter)
                    self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE))
                    control = observation.visible_elements[UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE]
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.TEMPLATE)
                    self.assertEqual(control.source_screen, screen)
                    self.assertEqual(control.source_layout_id, layout_id)
                    self.assertEqual(control.frame_ref, capture.frame_ref)

    def test_campaign_producer_abstains_on_missing_foreign_and_clipped_evidence(self) -> None:
        """Unprovable content stays unresolved; foreign features never publish a row."""

        empty_map = _builder().build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(empty_map.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        chapters = empty_map.entries(ListEntryKind.CAMPAIGN_CHAPTER)
        self.assertEqual(len(chapters), 2)
        for entry in chapters:
            self.assertIs(entry.campaign_node.locked, False)
            self.assertIsNone(entry.campaign_node.chapter_number)
            self.assertIs(entry.row_status, RowRecognitionStatus.UNREADABLE)
            self.assertIsNone(entry.action_point)

        foreign_digits = _builder(
            (
                OcrLine("10", Bounds(10, 473, 22, 14), 1.0),
                OcrLine("Grandia Ruins", Bounds(41, 472, 106, 17), 1.0),
            )
        ).build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(foreign_digits.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        self.assertFalse(
            any(
                entry.row_status is RowRecognitionStatus.COMPLETE
                for entry in foreign_digits.entries(ListEntryKind.CAMPAIGN_CHAPTER)
            ),
            "text outside the measured badge disc must not prove a chapter number",
        )

        map6 = _builder().build(
            _capture(_image("campaign_map_chapter_6.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(map6.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        rows = map6.entries(ListEntryKind.CAMPAIGN_CHAPTER)
        self.assertEqual(len(rows), 6)
        locked_rows = [entry for entry in rows if entry.campaign_node.locked is True]
        self.assertEqual(len(locked_rows), 3)
        for entry in locked_rows:
            self.assertIs(entry.row_status, RowRecognitionStatus.NO_ACTION)
            self.assertIsNone(entry.action_point)
        unlocked_rows = [entry for entry in rows if entry.campaign_node.locked is False]
        self.assertEqual(len(unlocked_rows), 3)
        for entry in unlocked_rows:
            self.assertIs(entry.row_status, RowRecognitionStatus.UNREADABLE)
        neptune_padlock = Bounds(440, 640, 100, 120)
        self.assertFalse(
            any(
                not (
                    entry.bounds.x + entry.bounds.width <= neptune_padlock.x
                    or neptune_padlock.x + neptune_padlock.width <= entry.bounds.x
                    or entry.bounds.y + entry.bounds.height <= neptune_padlock.y
                    or neptune_padlock.y + neptune_padlock.height <= entry.bounds.y
                )
                for entry in rows
            ),
            "the foreign Neptune's Laby padlock must not publish a chapter row",
        )

        stage_observation = _builder(
            (OcrLine("10 Grandia Ruins", Bounds(237, 473, 105, 15), 1.0),)
        ).build(
            _capture(_image("campaign_stage_10_3.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertNotIn(
            stage_observation.screen_type,
            {ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_CHAPTER},
        )
        self.assertFalse(stage_observation.entries(ListEntryKind.CAMPAIGN_CHAPTER))
        self.assertFalse(stage_observation.entries(ListEntryKind.CAMPAIGN_STAGE))

        unnamed_title = _builder(
            (OcrLine("Marsh of Tear", Bounds(368, 50, 160, 39), 1.0),)
        ).build(
            _capture(_image("campaign_chapter_10.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(unnamed_title.screen_type, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertIsNone(unnamed_title.campaign_chapter)
        self.assertTrue(unnamed_title.entries(ListEntryKind.CAMPAIGN_STAGE))

        missing_stage_badge = _image("campaign_chapter_10.png")
        missing_stage_badge.paste((0, 0, 0), (301, 591, 351, 644))
        missing_chapter_stage = _builder(
            (OcrLine("Ch.10 Grandia Ruins", Bounds(230, 55, 295, 30), 1.0),)
        ).build(
            _capture(missing_stage_badge),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertIn(
            missing_chapter_stage.screen_type,
            {ScreenType.UNKNOWN, ScreenType.PNC_CAMPAIGN_CHAPTER},
        )
        stage_bounds = Bounds(302, 598, 49, 49)
        self.assertFalse(
            any(
                entry.bounds == stage_bounds or stage_bounds.contains_bounds(entry.bounds)
                for entry in missing_chapter_stage.entries(ListEntryKind.CAMPAIGN_STAGE)
            ),
            "a blacked-out badge must not publish a stage row",
        )

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

    def test_recognized_stage_owns_generic_like_x_without_popup_promotion(self) -> None:
        """A recognized stage keeps its own controls when another X is present."""

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
                self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
                self.assertEqual(observation.decision.guard.value, "clear")
                self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
                self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
                self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

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
        chapter_six = next(
            profile for profile in recognizer.profiles if profile.id == "campaign_chapter_6"
        )
        chapter_six_sample = samples[Path(chapter_six.source.fixture).name]
        self.assertEqual(chapter_six_sample["sha256"], chapter_six.source.decoded_sha256)
        self.assertEqual(chapter_six_sample["group"], chapter_six.source.capture_group)
        self.assertEqual(chapter_six_sample["split"], "reference")
        for asset in (
            "screen_anchors/campaign_chapter_6_path_title.png",
            "screen_anchors/campaign_chapter_6_path_terrain.png",
        ):
            with self.subTest(asset=asset):
                anchor = by_asset[asset]
                self.assertEqual(anchor["reference_size"], [540, 960])
                self.assertEqual(anchor["capture_group"], chapter_six.source.capture_group)
                self.assertEqual(
                    anchor["source_sha256"],
                    by_asset["tests/data/screen_recognition/campaign_chapter_6_path.png"][
                        "source_sha256"
                    ],
                )
        for asset in (
            "screen_anchors/campaign_map_padlock.png",
            "screen_anchors/campaign_map_padlock_alt.png",
        ):
            with self.subTest(asset=asset):
                anchor = by_asset[asset]
                self.assertEqual(anchor["reference_size"], [540, 960])
                self.assertEqual(
                    anchor["capture_group"], "2026-09-15/vision_live_tour_20260915"
                )
                self.assertEqual(
                    anchor["source_sha256"],
                    by_asset["tests/data/screen_recognition/campaign_map_chapter_6.png"][
                        "source_sha256"
                    ],
                )

    def test_campaign_anchor_gate_fails_closed_when_identity_is_partial(self) -> None:
        recognizer = load_visual_screen_recognizer()
        mutations = (
            ("campaign_map.png", (180, 220, 350, 350)),
            ("campaign_map_chapter_6.png", (178, 435, 363, 520)),
            ("campaign_chapter_10.png", (205, 38, 530, 98)),
            ("campaign_chapter_6_path.png", (95, 35, 540, 200)),
            ("campaign_stage_10_3.png", (120, 201, 420, 250)),
        )
        for name, box in mutations:
            with self.subTest(name=name):
                image = _image(name)
                image.paste((0, 0, 0), box)
                self.assertEqual(recognizer.recognize(image).evidence, ())


if __name__ == "__main__":
    unittest.main()
