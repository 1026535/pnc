"""Qualify captured Economy, Military, and Fortification Research detail states."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import unittest
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult, OcrTextOrientation
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame


FIXTURE_ROOT = TEST_DATA_ROOT / "screen_recognition" / "research_variants"
VIEWPORT = Bounds(0, 0, 540, 960)
START = UiElementId.PNC_RESEARCH_START_BUTTON


@dataclass(slots=True)
class _BoundedOcrService:
    """Return measured lines while rejecting accidental whole-frame OCR."""

    lines: tuple[OcrLine, ...]
    calls: list[Bounds | None] = field(default_factory=list)

    def read_result(
        self, image: Image.Image, region: Bounds | None = None,
        *, orientation: OcrTextOrientation = OcrTextOrientation.AUTO,
    ) -> OcrResult:
        """Return only lines contained by the requested crop."""

        self.calls.append(region)
        if region is None or region == VIEWPORT:
            raise AssertionError("Research qualification must use bounded OCR regions.")
        del image
        lines = tuple(
            line for line in self.lines if region.contains_bounds(line.bounds)
        )
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Expose the protocol's line helper through the same bounded read."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Expose the protocol's text helper through the same bounded read."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _line(text: str, x: int, y: int, width: int, height: int = 16) -> OcrLine:
    """Build one normalized line from the measured RapidOCR bounds."""

    return OcrLine(text, Bounds(x, y, width, height), 1.0)


def _detail_lines(*, title: str, might: str, effect: str, level: str, institute: str) -> tuple[OcrLine, ...]:
    """Return the bounded detail facts retained from the reviewed frame."""

    return (
        _line(title, 56, 286, 175, 20),
        _line(might, 182, 347, 100, 16),
        _line(effect, 182, 379, 202, 16),
        _line(level, 176, 451, 34, 17),
        _line("Research", 326, 461, 89, 19),
        _line("Research Now", 115, 468, 122, 17),
        _line("Original Time", 106, 529, 100, 16),
        _line("Actual Time", 277, 529, 88, 16),
        _line("00:17:41", 106, 549, 65, 16),
        _line("00:11:03", 276, 549, 66, 16),
        _line(institute, 106, 610, 105, 16),
        _line("130,770/5,330", 106, 673, 115, 16),
        _line("434,442/2,290", 106, 725, 105, 16),
    )


def _active_detail_lines() -> tuple[OcrLine, ...]:
    """Return measured active-detail lines, including the no-idle status."""

    return (
        _line("Food Output I (2/4)", 55, 261, 176, 20),
        _line("Might +320", 181, 323, 81, 16),
        _line("Food Production Speed+6%", 182, 355, 202, 16),
        _line("00:10:43", 169, 438, 65, 14),
        _line("Speedup", 394, 435, 88, 24),
        _line("Original Time", 106, 505, 100, 16),
        _line("Actual Time", 277, 505, 88, 16),
        _line("00:17:41", 106, 524, 65, 16),
        _line("00:11:03", 276, 524, 66, 16),
        _line("No idle queue", 106, 586, 104, 16),
        _line("00:10:43", 216, 585, 66, 16),
        _line("Speedup", 412, 584, 75, 19),
        _line("Institute:Lv.3", 105, 633, 105, 16),
        _line("125,440/5,330", 105, 697, 114, 16),
        _line("432,152/2,290", 106, 749, 105, 16),
    )


def _military_no_idle_lines() -> tuple[OcrLine, ...]:
    """Return measured Military busy-detail lines."""

    return (
        _line("Siege ATK I (1/3)", 58, 261, 152, 20),
        _line("Might +4,220", 181, 323, 95, 16),
        _line("Siege ATK +2%", 182, 355, 106, 16),
        _line("303", 170, 426, 30, 18),
        _line("Research", 326, 437, 89, 19),
        _line("Research Now", 115, 445, 122, 17),
        _line("Original Time", 106, 505, 100, 16),
        _line("Actual Time", 277, 505, 88, 16),
        _line("04:01:46", 106, 524, 66, 16),
        _line("02:31:06", 276, 524, 66, 16),
        _line("No idle queue", 105, 586, 104, 16),
        _line("00:03:47", 216, 585, 66, 16),
        _line("Speedup", 412, 584, 75, 19),
        _line("Institute:Lv.6", 104, 633, 105, 16),
        _line("125,440/38,300", 106, 697, 117, 16),
        _line("432,152/16,400", 105, 749, 118, 16),
    )


def _fortification_detail_lines() -> tuple[OcrLine, ...]:
    """Return measured Fortification available-detail lines."""

    return (
        _line("Wall DEF I (1/10)", 59, 286, 147, 18),
        _line("Might +3", 179, 346, 66, 18),
        _line("Wall DEF +1,000", 181, 380, 118, 15),
        _line("Research", 326, 461, 90, 20),
        _line("Research Now", 115, 468, 122, 17),
        _line("Original Time", 105, 529, 101, 18),
        _line("Actual Time", 277, 529, 87, 16),
        _line("00:00:15", 105, 549, 66, 16),
        _line("60:00:00", 276, 549, 66, 17),
        _line("Institute:Lv.2", 105, 610, 105, 16),
        _line("125,440/55", 106, 673, 83, 18),
        _line("432,152/23", 105, 726, 82, 15),
    )


def _load_fixture(name: str) -> Image.Image:
    """Load a tracked, sanitized 540x960 Research detail fixture."""

    path = FIXTURE_ROOT / name
    with Image.open(path) as source:
        image = source.convert("RGB")
    if image.size != (540, 960):
        raise AssertionError(f"Research fixture {path} has unexpected size {image.size}.")
    return image


def _capture(image: Image.Image, *, session_id: str) -> CapturedScreenshot:
    """Attach deterministic frame provenance to a fixture image."""

    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _builder(ocr: _BoundedOcrService) -> ObservationBuilder:
    """Wire the production ObservationBuilder stack with controlled OCR."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=ocr,
        ocr_backend_revision="research-variant-qualification",
    )


def _perception(ocr: _BoundedOcrService) -> NavigationPerception:
    """Wire the production NavigationPerception stack with controlled OCR."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return NavigationPerception(
        load_visual_screen_recognizer(matcher=matcher),
        PncObservationEnricher(selector_registry=registry),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "research-variant-qualification",
        ),
    )


def _assert_bounded_reads(test: unittest.TestCase, ocr: _BoundedOcrService) -> None:
    """Require every OCR backend call to identify a strict screenshot crop."""

    test.assertTrue(ocr.calls)
    test.assertTrue(all(region is not None for region in ocr.calls))
    test.assertTrue(all(region != VIEWPORT for region in ocr.calls))


class ResearchCapturedVariantTests(unittest.TestCase):
    """Keep only observed Research controls authoritative across both consumers."""

    def test_idle_normal_detail_publishes_blue_start_without_premium_start(self) -> None:
        """Idle Economy captures expose blue Start through both production paths."""

        cases = (
            (
                "economy_detail_idle.png",
                _detail_lines(
                    title="Food Output I (2/4)",
                    might="Might +320",
                    effect="Food Production Speed+6%",
                    level="23",
                    institute="Institute:Lv.3",
                ),
            ),
            (
                "economy_detail_idle_holdout.png",
                _detail_lines(
                    title="Food Output I (3/4)",
                    might="Might +866",
                    effect="Food Production Speed+8%",
                    level="69",
                    institute="Institute:Lv.4",
                ),
            ),
            (
                "military_detail_idle.png",
                _detail_lines(
                    title="Siege ATK I (1/3)",
                    might="Might +4,220",
                    effect="Siege ATK +2%",
                    level="303",
                    institute="Institute:Lv.6",
                ),
            ),
        )
        for fixture_name, lines in cases:
            with self.subTest(fixture=fixture_name):
                builder_ocr = _BoundedOcrService(lines)
                built = _builder(builder_ocr).build(
                    _capture(_load_fixture(fixture_name), session_id=f"builder:{fixture_name}")
                )
                self.assertEqual(built.screen_type, ScreenType.PNC_RESEARCH_TREE)
                self.assertEqual(built.decision.guard, GuardVerdict.CLEAR)
                start = built.require(START)
                self.assertEqual(start.source_kind, VisibleElementSourceKind.TEMPLATE)
                self.assertEqual(start.bounds, Bounds(304, 447, 135, 49))
                self.assertNotIn(UiElementId.PNC_RESEARCH_QUEUE_CLOSE, built.visible_elements)
                self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, built.visible_elements)
                _assert_bounded_reads(self, builder_ocr)

                perception_ocr = _BoundedOcrService(lines)
                perceived = _perception(perception_ocr).build(
                    _capture(_load_fixture(fixture_name), session_id=f"perception:{fixture_name}"),
                    include_content=True,
                )
                self.assertEqual(perceived.screen_type, ScreenType.PNC_RESEARCH_TREE)
                self.assertEqual(perceived.decision.guard, GuardVerdict.CLEAR)
                perceived_start = perceived.require(START)
                self.assertEqual(perceived_start.source_kind, VisibleElementSourceKind.TEMPLATE)
                self.assertEqual(perceived_start.bounds, Bounds(304, 447, 135, 49))
                self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, perceived.visible_elements)
                _assert_bounded_reads(self, perception_ocr)

    def test_active_detail_is_strictly_verified_without_start(self) -> None:
        """Active Economy detail has identity and timer evidence but no Start target."""

        lines = _active_detail_lines()
        builder_ocr = _BoundedOcrService(lines)
        built = _builder(builder_ocr).build(
            _capture(_load_fixture("economy_detail_active.png"), session_id="builder:active")
        )
        self.assertEqual(built.screen_type, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(built.decision.guard, GuardVerdict.CLEAR)
        self.assertFalse(built.has(START))
        self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, built.visible_elements)
        self.assertTrue(
            any(
                item.reason == "visual_anchor:research_tree_node_detail_active"
                for item in built.decision.evidence
            )
        )
        _assert_bounded_reads(self, builder_ocr)

        perception_ocr = _BoundedOcrService(lines)
        perceived = _perception(perception_ocr).build(
            _capture(_load_fixture("economy_detail_active.png"), session_id="perception:active"),
            include_content=True,
        )
        self.assertEqual(perceived.screen_type, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(perceived.decision.guard, GuardVerdict.CLEAR)
        self.assertFalse(perceived.has(START))
        self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, perceived.visible_elements)
        self.assertTrue(
            any(
                item.reason == "visual_anchor:research_tree_node_detail_active"
                for item in perceived.decision.evidence
            )
        )
        _assert_bounded_reads(self, perception_ocr)

        task = ResearchTask()
        self.assertEqual(task.required_recognition_selectors, (START,))
        context = Mock(params=task.parse_params({"priority": ["economy"]}), runtime_state={})
        # An active detail at inspection is read-only: without a verified
        # selection the task never plans Start on it.
        self.assertEqual(task.plan(context, perceived), [])

    def test_visible_busy_military_detail_abstains_without_unproved_identity(self) -> None:
        """A no-idle Military detail visibly says Research but lacks a proved profile."""

        lines = _military_no_idle_lines()
        builder_ocr = _BoundedOcrService(lines)
        built = _builder(builder_ocr).build(
            _capture(_load_fixture("military_detail_no_idle.png"), session_id="builder:military")
        )
        self.assertEqual(built.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(built.decision.guard, GuardVerdict.CLEAR)
        self.assertFalse(built.visible_elements)
        _assert_bounded_reads(self, builder_ocr)

        perception_ocr = _BoundedOcrService(lines)
        perceived = _perception(perception_ocr).build(
            _capture(_load_fixture("military_detail_no_idle.png"), session_id="perception:military"),
            include_content=True,
        )
        self.assertEqual(perceived.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(perceived.decision.guard, GuardVerdict.CLEAR)
        self.assertFalse(perceived.visible_elements)
        _assert_bounded_reads(self, perception_ocr)

    def test_fortification_available_detail_uses_blue_start_profile(self) -> None:
        """The captured Fortification detail matches the shared blue Start profile."""

        lines = _fortification_detail_lines()
        builder_ocr = _BoundedOcrService(lines)
        built = _builder(builder_ocr).build(
            _capture(
                _load_fixture("fortification_detail_idle.png"),
                session_id="builder:fortification",
            )
        )
        self.assertEqual(built.screen_type, ScreenType.PNC_RESEARCH_TREE)
        self.assertTrue(built.has(START))
        self.assertEqual(built.require(START).source_kind, VisibleElementSourceKind.TEMPLATE)
        _assert_bounded_reads(self, builder_ocr)

        perception_ocr = _BoundedOcrService(lines)
        perceived = _perception(perception_ocr).build(
            _capture(
                _load_fixture("fortification_detail_idle.png"),
                session_id="perception:fortification",
            ),
            include_content=True,
        )
        self.assertEqual(perceived.screen_type, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(perceived.decision.guard, GuardVerdict.CLEAR)
        self.assertEqual(perceived.require(START).source_kind, VisibleElementSourceKind.TEMPLATE)
        _assert_bounded_reads(self, perception_ocr)


if __name__ == "__main__":
    unittest.main()
