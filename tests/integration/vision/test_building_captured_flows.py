from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    OcrRegionRead,
    OcrRegionReadStatus,
    OcrRegionPurpose,
    compile_screen_content_ocr_region_plans,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    _add_upgrade_requirement_controls,
    _build_build_queue_additions,
    _build_building_construction_additions,
    PncObservationEnricher,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import Region, build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.paths import TEST_DATA_ROOT


FIXTURES = TEST_DATA_ROOT / "screen_recognition"


def _capture(path: Path, *, session_id: str) -> CapturedScreenshot:
    """Attach explicit frame provenance to one committed capture fixture."""

    with Image.open(path) as source:
        image = source.convert("RGB")
    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(tz=UTC),
        frame_ref=frame.frame_ref,
    )


def _line(text: str, bounds: Bounds) -> OcrLine:
    """Build a localized deterministic OCR line for a captured frame."""

    return OcrLine(text=text, bounds=bounds, confidence=1.0)


def _construction_lines(
    *, include_header: bool = True, include_build: bool = True, include_level: bool = True,
) -> tuple[OcrLine, ...]:
    lines = [
        _line("Where Food is produced.", Bounds(463, 228, 347, 28)),
        _line("Upgrade to improve", Bounds(463, 258, 347, 28)),
        _line("capacity.", Bounds(463, 288, 180, 28)),
        _line("Build Now", Bounds(405, 440, 160, 37)),
        _line("Time", Bounds(59, 552, 71, 29)),
        _line("Requirement", Bounds(62, 713, 177, 27)),
        _line("Materials required", Bounds(61, 865, 251, 26)),
    ]
    if include_level:
        lines.insert(3, _line("0/45", Bounds(201, 408, 68, 31)))
    if include_header:
        lines.insert(0, _line("Farm", Bounds(180, 23, 123, 46)))
    if include_build:
        lines.append(_line("Build", Bounds(671, 440, 147, 37)))
    return tuple(lines)


def _queue_lines(*, active: bool) -> tuple[OcrLine, ...]:
    lines = [
        _line("Build Queue", Bounds(330, 432, 248, 57)),
        _line("2nd Build Queue", Bounds(212, 703, 225, 30)),
        _line("Inactive", Bounds(211, 758, 110, 30)),
        _line("Activate", Bounds(662, 734, 125, 31)),
    ]
    if active:
        lines.extend(
            (
                _line("Upgrading: Infirmary", Bounds(210, 543, 302, 40)),
                _line("00:48:16", Bounds(327, 593, 120, 35)),
                _line("Speedup", Bounds(618, 558, 215, 66)),
            )
        )
    else:
        lines.extend(
            (
                _line("1st Build Queue", Bounds(212, 543, 216, 32)),
                _line("Idle", Bounds(209, 596, 57, 33)),
            )
        )
    return tuple(lines)


@dataclass(slots=True)
class _BoundedOcrService(_RecordingOcrService):
    """Reject unbounded backend calls while preserving crop filtering."""

    regions: list[Region] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        if region is None or region == Bounds(0, 0, image.width, image.height):
            raise AssertionError("building OCR must use a bounded region")
        self.regions.append(region)
        return _RecordingOcrService.read_result(self, image, region)


def _wire(ocr: _BoundedOcrService) -> tuple[ObservationBuilder, NavigationPerception]:
    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    recognizer = load_visual_screen_recognizer(matcher=matcher)
    enricher = PncObservationEnricher(selector_registry=registry)
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        visual_recognizer=recognizer,
        ocr_service=ocr,
    )
    navigation = NavigationPerception(
        recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )
    return builder, navigation


class BuildingCapturedFlowTests(unittest.TestCase):
    """Qualify construction and queue OCR against the captured visual layouts."""

    def _assert_frame_local_provenance(self, observation, capture: CapturedScreenshot, screen: ScreenType) -> None:
        """Require every published building fact to remain tied to this frame and layout."""

        self.assertEqual(observation.image_size, capture.image.size)
        self.assertEqual(observation.frame_ref, capture.frame_ref)
        self.assertEqual(observation.screen_type, screen)
        self.assertIsNotNone(observation.decision.layout_id)
        for element in observation.visible_elements.values():
            self.assertEqual(element.frame_ref, capture.frame_ref)
            self.assertEqual(element.source_screen, screen)
            self.assertEqual(element.source_layout_id, observation.decision.layout_id)

    def test_visual_profiles_bind_actual_construction_and_queue_templates(self) -> None:
        """OpenCV profiles identify the captured surfaces and own their fixed controls."""

        cases = (
            (
                "building_variants/farm_construction_available.png",
                "building_construction_farm",
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
                UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
            ),
            (
                "build_queue_variants/build_queue_idle.png",
                "build_queue_centered",
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
            ),
            (
                "build_queue_variants/build_queue_active_infirmary.png",
                "build_queue_centered",
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
            ),
        )
        recognizer = load_visual_screen_recognizer()
        for relative_path, profile_id, owned_control, excluded_control in cases:
            with self.subTest(relative_path=relative_path):
                with Image.open(FIXTURES / relative_path) as source:
                    result = recognizer.recognize(source.convert("RGB"))
                self.assertEqual(result.profile_ids, (profile_id,))
                controls = {item.selector_id: item for item in result.controls}
                self.assertIn(owned_control, controls)
                self.assertEqual(controls[owned_control].source_kind, VisibleElementSourceKind.TEMPLATE)
                self.assertNotIn(excluded_control, controls)

    def test_requirement_control_requires_unmet_go_row_and_upgrade_screen(self) -> None:
        """A satisfied Requirement heading cannot become an unmet blocking Go control."""

        image = Image.new("RGB", (900, 1600))
        header = _line("Requirement", Bounds(62, 713, 177, 27))
        target = _line("Castle: Lv.8", Bounds(154, 768, 147, 24))
        go = _line("Go", Bounds(671, 768, 80, 30))

        unmet: dict[UiElementId, VisibleElement] = {}
        _add_upgrade_requirement_controls(
            image=image,
            lines=(header, target, go),
            screen_type=ScreenType.PNC_INSTITUTE,
            visible_elements=unmet,
        )
        self.assertEqual(
            set(unmet),
            {
                UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
            },
        )

        satisfied: dict[UiElementId, VisibleElement] = {}
        _add_upgrade_requirement_controls(
            image=image,
            lines=(header, target),
            screen_type=ScreenType.PNC_INSTITUTE,
            visible_elements=satisfied,
        )
        self.assertEqual(satisfied, {})

        construction: dict[UiElementId, VisibleElement] = {}
        _add_upgrade_requirement_controls(
            image=image,
            lines=(header, target, go),
            screen_type=ScreenType.PNC_BUILDING_CONSTRUCTION,
            visible_elements=construction,
        )
        self.assertEqual(construction, {})

    def test_compiler_owns_bounded_construction_and_queue_regions(self) -> None:
        request = ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_CONSTRUCTION)
        construction = compile_screen_content_ocr_region_plans(
            resolved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
            request=request,
            image_size=(900, 1600),
        )
        self.assertEqual(
            [(read.purpose, read.required_fact, read.bounds) for read in construction],
            [
                (OcrRegionPurpose.HEADER, "construction_target_name", Bounds(162, 0, 648, 88)),
                (OcrRegionPurpose.BUILDING_LEVEL, "building_level", Bounds(18, 384, 864, 120)),
                (OcrRegionPurpose.SCREEN_FIELDS, "construction_requirements", Bounds(36, 512, 828, 512)),
            ],
        )
        queue = compile_screen_content_ocr_region_plans(
            resolved_screen=ScreenType.PNC_BUILD_QUEUE,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILD_QUEUE),
            image_size=(900, 1600),
        )
        self.assertEqual(
            [(read.purpose, read.required_fact, read.bounds) for read in queue],
            [
                (OcrRegionPurpose.HEADER, "build_queue_header", Bounds(198, 400, 504, 112)),
                (OcrRegionPurpose.ROW_BODY, "build_queue_first_row", Bounds(36, 512, 828, 160)),
                (OcrRegionPurpose.ROW_BODY, "build_queue_second_row", Bounds(36, 672, 828, 160)),
            ],
        )
        self.assertTrue(all(read.bounds != Bounds(0, 0, 900, 1600) for read in construction + queue))

    def test_proved_construction_publishes_read_controls_and_independent_level(self) -> None:
        image = Image.new("RGB", (900, 1600))
        target_plan = compile_screen_content_ocr_region_plans(
            resolved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_CONSTRUCTION),
            image_size=image.size,
        )[0]
        target_read = OcrRegionRead(
            plan=target_plan,
            result=OcrResult(lines=(_line("Farm", Bounds(180, 23, 123, 46)),), words=()),
            status=OcrRegionReadStatus.PRESENT,
        )
        additions = _build_building_construction_additions(
            image=image,
            lines=_construction_lines(),
            proved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
            target_read=target_read,
        )
        self.assertIsNotNone(additions)
        assert additions is not None
        self.assertEqual(
            set(additions.visible_elements),
            {
                UiElementId.PNC_BUILDING_CONSTRUCTION_HEADER,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_NOW_BUTTON,
            },
        )
        self.assertEqual(additions.screen_evidence, ())

        premium_only = _build_building_construction_additions(
            image=image,
            lines=_construction_lines(include_build=False),
            proved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
            target_read=target_read,
        )
        self.assertIsNotNone(premium_only)
        assert premium_only is not None
        self.assertNotIn(UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON, premium_only.visible_elements)
        self.assertIn(UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_NOW_BUTTON, premium_only.visible_elements)

        missing_header = _build_building_construction_additions(
            image=image,
            lines=_construction_lines(include_header=False),
            proved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
            target_read=OcrRegionRead(
                plan=target_plan,
                result=OcrResult(lines=(), words=()),
                status=OcrRegionReadStatus.MISSING,
            ),
        )
        self.assertIsNotNone(missing_header)
        assert missing_header is not None
        self.assertEqual(missing_header.visible_elements, {})

    def test_proved_queue_keeps_active_row_bounds_and_publishes_idle_fact(self) -> None:
        row_regions = (Bounds(36, 512, 828, 160), Bounds(36, 672, 828, 160))
        active = _build_build_queue_additions(
            image=Image.new("RGB", (900, 1600)),
            lines=_queue_lines(active=True),
            proved_screen=ScreenType.PNC_BUILD_QUEUE,
            row_regions=row_regions,
        )
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(len(active.list_entries), 1)
        self.assertEqual(active.list_entries[0].title_text, "Infirmary")
        self.assertEqual(active.list_entries[0].timer_text, "00:48:16")
        self.assertEqual(active.list_entries[0].bounds, row_regions[0])
        self.assertEqual(active.list_entries[0].metadata, {"queue_state": "upgrading"})
        self.assertEqual(active.screen_evidence, ())

        idle = _build_build_queue_additions(
            image=Image.new("RGB", (900, 1600)),
            lines=_queue_lines(active=False),
            proved_screen=ScreenType.PNC_BUILD_QUEUE,
            row_regions=row_regions,
        )
        self.assertIsNotNone(idle)
        assert idle is not None
        self.assertEqual(len(idle.list_entries), 1)
        self.assertEqual(idle.list_entries[0].bounds, row_regions[0])
        self.assertEqual(
            idle.list_entries[0].metadata,
            {"queue_state": "idle", "queue_index": 0},
        )

    def test_construction_title_or_level_misses_keep_visual_build_control(self) -> None:
        """Independent construction identity and the blue Build template survive OCR misses."""

        capture = _capture(
            FIXTURES / "building_variants/farm_construction_available.png",
            session_id="building-construction-fact-misses",
        )
        cases = (
            ("title-miss", _construction_lines(include_header=False), True),
            ("title-and-level-miss", _construction_lines(include_header=False, include_level=False), False),
        )
        for name, lines, has_level in cases:
            with self.subTest(name=name):
                ocr = _BoundedOcrService(lines=lines)
                builder, navigation = _wire(ocr)
                builder_observation = builder.build(
                    capture,
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_CONSTRUCTION),
                )
                navigation_observation = navigation.build(capture, include_content=True)
                for observation in (builder_observation, navigation_observation):
                    self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_CONSTRUCTION)
                    self.assertEqual(
                        observation.require(UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON).source_kind,
                        VisibleElementSourceKind.TEMPLATE,
                    )
                    self.assertEqual(
                        observation.has(UiElementId.PNC_BUILDING_LEVEL_LABEL),
                        has_level,
                    )
                    self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))

    def test_captured_profiles_and_both_production_paths_keep_reads_bounded(self) -> None:
        cases = (
            (
                "building_variants/farm_construction_available.png",
                _construction_lines(),
                ScreenType.PNC_BUILDING_CONSTRUCTION,
                UiElementId.PNC_BUILDING_LEVEL_LABEL,
                False,
            ),
            (
                "build_queue_variants/build_queue_idle.png",
                _queue_lines(active=False),
                ScreenType.PNC_BUILD_QUEUE,
                None,
                False,
            ),
            (
                "build_queue_variants/build_queue_active_infirmary.png",
                _queue_lines(active=True),
                ScreenType.PNC_BUILD_QUEUE,
                None,
                True,
            ),
            (
                "build_queue_variants/build_queue_active_infirmary_fresh.png",
                _queue_lines(active=True),
                ScreenType.PNC_BUILD_QUEUE,
                None,
                True,
            ),
        )
        for relative_path, lines, expected_screen, level_selector, active_queue in cases:
            with self.subTest(relative_path=relative_path):
                capture = _capture(FIXTURES / relative_path, session_id=f"building:{relative_path}")
                ocr = _BoundedOcrService(lines=lines)
                builder, navigation = _wire(ocr)
                request = ObservationRequest.source_screen_retry(expected_screen)
                built = builder.build(capture, request=request)
                self.assertEqual(built.screen_type, expected_screen)
                self._assert_frame_local_provenance(built, capture, expected_screen)
                if level_selector is not None:
                    self.assertEqual(built.require(level_selector).extracted_text, "0/45")
                    self.assertEqual(built.require(level_selector).source_kind, VisibleElementSourceKind.OCR)
                if expected_screen == ScreenType.PNC_BUILD_QUEUE:
                    entries = built.entries(ListEntryKind.BUILDING)
                    self.assertEqual(len(entries), 1)
                    if active_queue:
                        self.assertEqual(entries[0].title_text, "Infirmary")
                        self.assertEqual(entries[0].timer_text, "00:48:16")
                        self.assertEqual(entries[0].bounds, Bounds(36, 512, 828, 160))
                        self.assertEqual(entries[0].frame_ref, capture.frame_ref)
                        self.assertEqual(entries[0].source_screen, expected_screen)
                        self.assertEqual(entries[0].source_layout_id, built.decision.layout_id)
                        self.assertEqual(entries[0].metadata, {"queue_state": "upgrading"})
                    else:
                        self.assertEqual(entries[0].metadata, {"queue_state": "idle", "queue_index": 0})
                    self.assertEqual(
                        built.require(UiElementId.PNC_POPUP_CLOSE_BUTTON).source_kind,
                        VisibleElementSourceKind.TEMPLATE,
                    )
                if expected_screen == ScreenType.PNC_BUILDING_CONSTRUCTION:
                    self.assertTrue(built.has(UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON))
                    self.assertFalse(built.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
                self.assertTrue(ocr.regions)
                self.assertTrue(all(region != Bounds(0, 0, 900, 1600) for region in ocr.regions))

                navigation_observation = navigation.build(capture, include_content=True)
                self.assertEqual(navigation_observation.screen_type, expected_screen)
                self._assert_frame_local_provenance(navigation_observation, capture, expected_screen)
                if expected_screen == ScreenType.PNC_BUILD_QUEUE:
                    navigation_entries = navigation_observation.entries(ListEntryKind.BUILDING)
                    self.assertEqual(len(navigation_entries), 1)
                    if active_queue:
                        self.assertEqual(navigation_entries[0].title_text, "Infirmary")
                        self.assertEqual(navigation_entries[0].timer_text, "00:48:16")
                        self.assertEqual(navigation_entries[0].bounds, Bounds(36, 512, 828, 160))
                        self.assertEqual(navigation_entries[0].frame_ref, capture.frame_ref)
                        self.assertEqual(navigation_entries[0].source_screen, expected_screen)
                        self.assertEqual(navigation_entries[0].source_layout_id, navigation_observation.decision.layout_id)
                    else:
                        self.assertEqual(
                            navigation_entries[0].metadata,
                            {"queue_state": "idle", "queue_index": 0},
                        )
                self.assertTrue(ocr.regions)


if __name__ == "__main__":
    unittest.main()
