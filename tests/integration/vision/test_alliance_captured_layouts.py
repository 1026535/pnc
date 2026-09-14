"""Qualify the compact and tabbed Alliance Home visual layouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.modal_overlay import (
    update_modal_lines,
    with_update_modal,
)


FIXTURE_ROOT = TEST_DATA_ROOT / "screen_recognition" / "alliance_variants"
REFERENCE_SIZE = (540, 960)


@dataclass(slots=True)
class _BoundedOcrService:
    """Return only controlled labels contained by each requested screenshot crop."""

    lines: tuple[OcrLine, ...]
    calls: list[Bounds | None] = field(default_factory=list)
    image_sizes: list[tuple[int, int]] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Reject full-frame acquisition and retain only lines in the crop."""

        self.calls.append(region)
        self.image_sizes.append(image.size)
        if region is None or region == Bounds(0, 0, image.width, image.height):
            raise AssertionError("Alliance qualification must use bounded OCR regions.")
        lines = tuple(line for line in self.lines if region.contains_bounds(line.bounds))
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Expose the OCR protocol's line helper through the same bounded read."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Expose the OCR protocol's text helper through the same bounded read."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _scale_bounds(bounds: Bounds, image_size: tuple[int, int]) -> Bounds:
    """Scale a reference-space OCR label to one of the reviewed viewports."""

    width, height = image_size
    return Bounds(
        round(bounds.x * width / REFERENCE_SIZE[0]),
        round(bounds.y * height / REFERENCE_SIZE[1]),
        round(bounds.width * width / REFERENCE_SIZE[0]),
        round(bounds.height * height / REFERENCE_SIZE[1]),
    )


def _lines_for(image_size: tuple[int, int], *, tabbed: bool, include_guard: bool = False) -> tuple[OcrLine, ...]:
    """Return only static labels needed by the existing Alliance Home parser."""

    tile_y = 528 if tabbed else 505
    lines = [
        ("Alliance", Bounds(109, 15, 117, 28)),
        ("Alliance Territory", Bounds(29, tile_y, 151, 24)),
        ("Alliance Member", Bounds(291, 814 if tabbed else 772, 158, 24)),
        ("Alliance Mail", Bounds(162, 919, 105, 20)),
    ]
    static_lines = tuple(OcrLine(text, _scale_bounds(bounds, image_size), 1.0) for text, bounds in lines)
    return static_lines + (update_modal_lines(image_size) if include_guard else ())


def _load_fixture(name: str) -> Image.Image:
    """Load one sanitized Alliance fixture."""

    path = FIXTURE_ROOT / name
    if not path.is_file():
        path = TEST_DATA_ROOT / "screen_recognition" / name
    with Image.open(path) as source:
        return source.convert("RGB")


def _capture(image: Image.Image, *, session_id: str) -> CapturedScreenshot:
    """Attach deterministic frame provenance to a fixture."""

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
    """Wire the production registry, selector engine, enricher, and recognizer."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=ocr,
        ocr_backend_revision="alliance-layout-qualification",
    )


def _perception(builder: ObservationBuilder) -> NavigationPerception:
    """Wire the replacement navigator against the same production components."""

    assert builder.visual_recognizer is not None
    return NavigationPerception(
        builder.visual_recognizer,
        builder.enricher,
        builder.screen_classifier,
        builder.create_ocr_context,
    )


def _assert_bounded(test: unittest.TestCase, service: _BoundedOcrService) -> None:
    """Require every backend request to name a strict crop."""

    test.assertTrue(service.calls)
    test.assertTrue(all(region is not None for region in service.calls))
    test.assertTrue(
        all(
            (region.x, region.y, region.width, region.height) != (0, 0, width, height)
            for region, (width, height) in zip(service.calls, service.image_sizes)
            if region is not None
        )
    )


class AllianceCapturedLayoutTests(unittest.TestCase):
    """Keep tabbed and compact Alliance layouts conservative and distinct."""

    def test_layouts_match_at_reference_and_native_sizes_through_both_paths(self) -> None:
        """Both production perception paths preserve each measured layout and controls."""

        cases = (
            ("alliance_compact.png", False, "alliance_home_compact"),
            ("alliance_tabbed.png", True, "alliance_home_tabbed"),
            ("alliance_tabbed_validation.png", True, "alliance_home_tabbed"),
            ("alliance_home_aug30.png", False, "alliance_home_compact"),
        )
        profile_controls = {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL,
            UiElementId.PNC_ALLIANCE_TILE_MEMBER,
        }
        published_controls = profile_controls - {UiElementId.PNC_BACK_BUTTON_TOP_LEFT}
        for fixture_name, tabbed, layout_id in cases:
            with self.subTest(fixture=fixture_name):
                base = _load_fixture(fixture_name)
                for size in (REFERENCE_SIZE, (900, 1600)):
                    image = base.resize(size)
                    builder_ocr = _BoundedOcrService(_lines_for(size, tabbed=tabbed))
                    builder = _builder(builder_ocr)
                    capture = _capture(image, session_id=f"builder:{fixture_name}:{size}")
                    visual_controls = {
                        control.selector_id
                        for control in builder.visual_recognizer.recognize(image).controls
                    }
                    self.assertTrue(profile_controls.issubset(visual_controls))
                    built = builder.build(capture, request=ObservationRequest.source_screen_retry(ScreenType.PNC_ALLIANCE_HOME))
                    self.assertEqual(built.frame_ref, capture.frame_ref)
                    self.assertEqual(built.screen_type, ScreenType.PNC_ALLIANCE_HOME)
                    self.assertEqual(built.decision.layout_id, layout_id)
                    self.assertEqual(built.decision.guard, GuardVerdict.CLEAR)
                    self.assertTrue(published_controls.issubset(built.visible_elements))
                    self.assertTrue(all(element.source_kind.name == "TEMPLATE" for element in built.visible_elements.values() if element.selector_id in published_controls))
                    _assert_bounded(self, builder_ocr)

                    perception_ocr = _BoundedOcrService(_lines_for(size, tabbed=tabbed))
                    perception_builder = _builder(perception_ocr)
                    perception_capture = _capture(image, session_id=f"perception:{fixture_name}:{size}")
                    perceived = _perception(perception_builder).build(
                        perception_capture,
                        include_content=True,
                    )
                    self.assertEqual(perceived.frame_ref, perception_capture.frame_ref)
                    self.assertEqual(perceived.screen_type, ScreenType.PNC_ALLIANCE_HOME)
                    self.assertEqual(perceived.decision.layout_id, layout_id)
                    self.assertTrue(published_controls.issubset(perceived.visible_elements))
                    _assert_bounded(self, perception_ocr)

    def test_layout_identity_is_mutually_exclusive_and_requires_member_proof(self) -> None:
        """The selected tab and fixed member icon prevent cross-layout or absent-tile claims."""

        recognizer = load_visual_screen_recognizer()
        compact = _load_fixture("alliance_compact.png")
        tabbed = _load_fixture("alliance_tabbed.png")
        compact_result = recognizer.recognize(compact)
        tabbed_result = recognizer.recognize(tabbed)
        self.assertEqual(compact_result.profile_ids, ("alliance_home_compact",))
        self.assertEqual(tabbed_result.profile_ids, ("alliance_home_tabbed",))

        missing_member = compact.copy()
        missing_member.paste((27, 52, 99), (291, 772, 449, 796))
        missing_result = recognizer.recognize(missing_member)
        self.assertEqual(missing_result.profile_ids, ("alliance_home_compact",))
        self.assertNotIn(UiElementId.PNC_ALLIANCE_TILE_MEMBER, {control.selector_id for control in missing_result.controls})

        missing_selected_tab = tabbed.copy()
        missing_selected_tab.paste((25, 48, 93), (60, 62, 222, 107))
        self.assertEqual(recognizer.recognize(missing_selected_tab).evidence, ())

    def test_existing_guard_owns_alliance_frame_and_hides_background_controls(self) -> None:
        """A reviewed update overlay remains foreground owner over either Alliance layout."""

        for fixture_name, tabbed in (("alliance_compact.png", False), ("alliance_tabbed.png", True)):
            with self.subTest(fixture=fixture_name):
                image = with_update_modal(_load_fixture(fixture_name))
                ocr = _BoundedOcrService(_lines_for(image.size, tabbed=tabbed, include_guard=True))
                builder = _builder(ocr)
                observation = builder.build(
                    _capture(image, session_id=f"guard:{fixture_name}"),
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_ALLIANCE_HOME),
                )
                self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
                self.assertTrue(observation.blocking_popup)
                self.assertIn(UiElementId.PNC_UPDATE_CONFIRM_BUTTON, observation.visible_elements)
                self.assertNotIn(UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL, observation.visible_elements)
                self.assertNotIn(UiElementId.PNC_ALLIANCE_TILE_MEMBER, observation.visible_elements)
                _assert_bounded(self, ocr)


if __name__ == "__main__":
    unittest.main()
