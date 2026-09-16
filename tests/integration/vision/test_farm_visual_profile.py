"""Farm building-detail identity and control ownership regressions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds, Region
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService


FIXTURES = TEST_DATA_ROOT / "screen_recognition" / "building_variants"


def _capture(name: str) -> CapturedScreenshot:
    """Load one committed Farm frame into the canonical capture model."""

    with Image.open(FIXTURES / name) as source:
        image = source.convert("RGB")
    return _capture_image(image)


def _capture_image(image: Image.Image) -> CapturedScreenshot:
    """Attach fresh canonical provenance to an in-memory Farm frame."""

    frame = make_captured_frame(_encode_png(image), session_id="farm-visual-profile-test")
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(tz=UTC),
        frame_ref=frame.frame_ref,
    )


def _farm_lines(level: str | None = None) -> tuple[OcrLine, ...]:
    """Return crop-filterable OCR facts for the two reviewed detail states."""

    lines = [
        OcrLine("Farm", Bounds(180, 23, 123, 46), 1.0),
        OcrLine("Where Food is produced. Upgrade", Bounds(471, 245, 415, 26), 1.0),
        OcrLine("Upgrade", Bounds(671, 440, 147, 37), 1.0),
        OcrLine("Time", Bounds(59, 552, 71, 29), 1.0),
        OcrLine("Requirement", Bounds(62, 713, 177, 27), 1.0),
        OcrLine("Materials required", Bounds(61, 865, 251, 26), 1.0),
        OcrLine("Effect", Bounds(60, 1035, 83, 31), 1.0),
    ]
    if level is not None:
        lines.insert(2, OcrLine(level, Bounds(201, 408, 68, 31), 1.0))
    return tuple(lines)


@dataclass(slots=True)
class _CropHonoringOcrService(_RecordingOcrService):
    """Reject accidental unbounded backend calls while filtering lines by ROI."""

    regions: list[Region] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Require every backend request to identify a strict screenshot region."""

        if region is None:
            raise AssertionError("Farm observation OCR must receive a bounded region.")
        self.regions.append(region)
        return _RecordingOcrService.read_result(self, image, region)


def _wire(ocr: _CropHonoringOcrService) -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire the real catalog, recognizer, enricher, builder, and navigator."""

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


class FarmVisualProfileTests(unittest.TestCase):
    """Keep Farm identity independent from OCR and premium action controls."""

    def test_profile_matches_both_detail_levels_and_measures_phase_controls(self) -> None:
        """The exact Farm title/description pair identifies both 1/45 and 7/45 details.

        The shared button pixels measure both phase-owned selectors; the typed
        phase filter at publish time keeps only the one the frame proves.
        """

        registry = build_default_selector_registry()
        upgrade_selector = registry.require(UiElementId.PNC_BUILDING_UPGRADE_BUTTON)
        self.assertIn(ScreenType.PNC_BUILDING_DETAILS, upgrade_selector.screens)
        recognizer = load_visual_screen_recognizer()

        for name in ("farm_upgrade_available.png", "farm_level_one_detail.png"):
            with self.subTest(name=name):
                with Image.open(FIXTURES / name) as source:
                    result = recognizer.recognize(source.convert("RGB"))
                self.assertEqual(
                    {(item.screen_type, item.layout_id) for item in result.evidence},
                    {(ScreenType.PNC_BUILDING_DETAILS, "building_detail_farm")},
                )
                self.assertEqual(result.profile_ids, ("building_detail_farm",))
                controls = {item.selector_id: item for item in result.controls}
                self.assertEqual(
                    set(controls),
                    {
                        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON,
                        UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    },
                )
                self.assertEqual(
                    controls[UiElementId.PNC_BACK_BUTTON_TOP_LEFT].source_kind,
                    VisibleElementSourceKind.TEMPLATE,
                )
                for selector_id in (
                    UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                ):
                    self.assertEqual(
                        controls[selector_id].source_kind,
                        VisibleElementSourceKind.TEMPLATE,
                    )
                back_center = controls[UiElementId.PNC_BACK_BUTTON_TOP_LEFT].bounds.center()
                self.assertTrue(35 <= back_center[0] <= 135)
                self.assertTrue(15 <= back_center[1] <= 85)
                upgrade_center = controls[UiElementId.PNC_BUILDING_UPGRADE_BUTTON].bounds.center()
                self.assertTrue(630 <= upgrade_center[0] <= 860)
                self.assertTrue(410 <= upgrade_center[1] <= 510)
                self.assertEqual(
                    controls[UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON].bounds,
                    controls[UiElementId.PNC_BUILDING_UPGRADE_BUTTON].bounds,
                )

    def test_real_builder_and_navigation_keep_farm_identity_and_current_level(self) -> None:
        """Both production perception paths retain frame-local OCR level facts."""

        for name, level in (
            ("farm_level_one_detail.png", "1/45"),
            ("farm_upgrade_available.png", "7/45"),
        ):
            with self.subTest(name=name):
                capture = _capture(name)
                ocr = _CropHonoringOcrService(lines=_farm_lines(level))
                builder, navigation = _wire(ocr)
                observation = builder.build(
                    capture,
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_DETAILS),
                )
                self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
                self.assertEqual(
                    observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL).extracted_text,
                    level,
                )
                builder_level = observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL)
                self.assertEqual(builder_level.source_kind, VisibleElementSourceKind.OCR)
                self.assertFalse(builder_level.identity_evidence)
                self.assertIsNone(builder_level.action_point)
                self.assertEqual(builder_level.frame_ref, capture.frame_ref)
                self.assertEqual(builder_level.source_screen, ScreenType.PNC_BUILDING_DETAILS)
                self.assertEqual(builder_level.source_layout_id, observation.decision.layout_id)
                self.assertEqual(
                    observation.require(UiElementId.PNC_BUILDING_UPGRADE_BUTTON).source_kind,
                    VisibleElementSourceKind.TEMPLATE,
                )
                self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
                self.assertTrue(ocr.regions)
                self.assertTrue(
                    all(region != Bounds(0, 0, capture.image.width, capture.image.height) for region in ocr.regions)
                )

                visual = load_visual_screen_recognizer().recognize(capture.image)
                visual_controls = {item.selector_id: item for item in visual.controls}
                for selector_id in (
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                ):
                    control = observation.require(selector_id)
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.TEMPLATE)
                    self.assertEqual(control.bounds, visual_controls[selector_id].bounds)
                    self.assertEqual(control.frame_ref, capture.frame_ref)
                    self.assertEqual(control.source_screen, ScreenType.PNC_BUILDING_DETAILS)
                    self.assertEqual(control.source_layout_id, observation.decision.layout_id)

                navigation_observation = navigation.build(capture, include_content=True)
                self.assertEqual(navigation_observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
                navigation_level = navigation_observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL)
                self.assertEqual(navigation_level.extracted_text, level)
                self.assertEqual(navigation_level.source_kind, VisibleElementSourceKind.OCR)
                self.assertFalse(navigation_level.identity_evidence)
                self.assertIsNone(navigation_level.action_point)
                self.assertEqual(navigation_level.frame_ref, capture.frame_ref)
                self.assertEqual(navigation_level.source_screen, ScreenType.PNC_BUILDING_DETAILS)
                self.assertEqual(navigation_level.source_layout_id, navigation_observation.decision.layout_id)
                self.assertTrue(navigation_observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
                self.assertTrue(navigation_observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
                for selector_id in (
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                ):
                    control = navigation_observation.require(selector_id)
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.TEMPLATE)
                    self.assertEqual(control.bounds, visual_controls[selector_id].bounds)
                    self.assertEqual(control.frame_ref, capture.frame_ref)
                    self.assertEqual(control.source_screen, ScreenType.PNC_BUILDING_DETAILS)
                    self.assertEqual(control.source_layout_id, navigation_observation.decision.layout_id)

    def test_level_only_ocr_proves_no_phase_and_suppresses_phase_controls(self) -> None:
        """A degraded level-only read cannot turn the spending panel into an entry."""

        capture = _capture("farm_upgrade_available.png")
        ocr = _CropHonoringOcrService(
            lines=(
                OcrLine("Farm", Bounds(172, 14, 139, 61), 1.0),
                OcrLine("7/45", Bounds(203, 412, 64, 24), 1.0),
                OcrLine("Upgrade", Bounds(668, 436, 153, 44), 1.0),
            )
        )
        builder, navigation = _wire(ocr)
        for observation in (
            builder.build(
                capture,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_DETAILS),
            ),
            navigation.build(capture, include_content=True),
        ):
            detail = observation.building_detail
            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertEqual(detail.building_id, HomeCityObjectId.FARM)
            self.assertIsNone(detail.phase)
            self.assertEqual((detail.current_level, detail.max_level), (7, 45))
            # Neither generic phase-owned control may publish unproved, so no
            # navigation or mutation input can be derived from this frame.
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))

    def test_food_output_alone_cannot_prove_primary(self) -> None:
        """`Food Output` without `Overall Hourly Output` leaves phase unproved."""

        capture = _capture("farm_level_one_detail.png")
        ocr = _CropHonoringOcrService(
            lines=(
                OcrLine("Farm", Bounds(173, 14, 139, 62), 1.0),
                OcrLine("1/45", Bounds(202, 410, 66, 27), 1.0),
                OcrLine("Food Output", Bounds(465, 574, 170, 30), 1.0),
            )
        )
        builder, navigation = _wire(ocr)
        for observation in (
            builder.build(
                capture,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_DETAILS),
            ),
            navigation.build(capture, include_content=True),
        ):
            detail = observation.building_detail
            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertIsNone(detail.phase)
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))

    def test_navigation_without_content_keeps_visual_controls_only(self) -> None:
        """The default navigation pass does not publish OCR labels."""

        capture = _capture("farm_level_one_detail.png")
        ocr = _CropHonoringOcrService(lines=_farm_lines("1/45"))
        _builder, navigation = _wire(ocr)
        observation = navigation.build(capture, include_content=False)
        self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
        self.assertFalse(observation.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))
        self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))

    def test_missing_level_keeps_independent_upgrade_control(self) -> None:
        """A missing level remains unknown while the visually measured Upgrade stays available."""

        capture = _capture("farm_level_one_detail.png")
        ocr = _CropHonoringOcrService(lines=_farm_lines())
        builder, navigation = _wire(ocr)
        builder_observation = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_DETAILS),
        )
        navigation_observation = navigation.build(capture, include_content=True)
        for observation in (builder_observation, navigation_observation):
            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))
            self.assertEqual(
                observation.require(UiElementId.PNC_BUILDING_UPGRADE_BUTTON).source_kind,
                VisibleElementSourceKind.TEMPLATE,
            )

    def test_construction_wrong_building_and_obscured_description_abstain(self) -> None:
        """Farm detail identity requires its stable two-line description and exact layout."""

        recognizer = load_visual_screen_recognizer()
        with Image.open(FIXTURES / "farm_construction_available.png") as source:
            construction = source.convert("RGB")
        construction_result = recognizer.recognize(construction)
        self.assertEqual(construction_result.profile_ids, ("building_construction_farm",))
        construction_controls = {
            item.selector_id: item for item in construction_result.controls
        }
        self.assertEqual(
            set(construction_controls),
            {
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
            },
        )
        self.assertEqual(
            construction_controls[UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON].source_kind,
            VisibleElementSourceKind.TEMPLATE,
        )
        self.assertNotIn(UiElementId.PNC_BUILDING_UPGRADE_BUTTON, construction_controls)

        for name in ("castle_audit.png", "warehouse_audit.png"):
            with self.subTest(name=name):
                with Image.open(TEST_DATA_ROOT / "screen_recognition" / name) as source:
                    result = recognizer.recognize(source.convert("RGB"))
                self.assertNotIn("building_detail_farm", result.profile_ids)

        with Image.open(FIXTURES / "farm_upgrade_available.png") as source:
            obscured = source.convert("RGB")
        obscured.paste((0, 0, 0), (450, 210, 899, 335))
        self.assertNotIn("building_detail_farm", recognizer.recognize(obscured).profile_ids)

    def test_premium_button_cannot_replace_missing_normal_upgrade(self) -> None:
        """Removing the blue Upgrade leaves identity but no actionable upgrade control."""

        with Image.open(FIXTURES / "farm_upgrade_available.png") as source:
            image = source.convert("RGB")
        image.paste((16, 30, 68), (630, 410, 860, 505))
        result = load_visual_screen_recognizer().recognize(image)
        self.assertEqual(result.profile_ids, ("building_detail_farm",))
        self.assertEqual(
            {item.selector_id for item in result.controls},
            {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
        )

    def test_ocr_upgrade_label_cannot_fabricate_missing_normal_control(self) -> None:
        """An OCR Upgrade label cannot replace the missing measured blue control."""

        capture = _capture("farm_level_one_detail.png")
        image = capture.image.copy()
        image.paste((16, 30, 68), (630, 410, 860, 505))
        capture = _capture_image(image)
        ocr = _CropHonoringOcrService(lines=_farm_lines("1/45"))
        builder, navigation = _wire(ocr)
        builder_observation = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_DETAILS),
        )
        navigation_observation = navigation.build(capture, include_content=True)
        for observation in (builder_observation, navigation_observation):
            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))


if __name__ == "__main__":
    unittest.main()
