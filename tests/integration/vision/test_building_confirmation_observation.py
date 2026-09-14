"""Canonical construction and upgrade-confirmation parser qualifications."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import PopupControlKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    OcrRegionRead,
    OcrRegionReadStatus,
    compile_guard_ocr_region_plans,
    compile_screen_content_ocr_region_plans,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_building_construction_additions,
    _build_building_detail_additions,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.text_anchors import DetectedTextAnchor, TextAnchorId
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.integration.vision.test_alliance_remaining_visual_contracts import _BoundedOcrService
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession


VIEWPORT = (900, 1600)
FIXTURES = TEST_DATA_ROOT / "screen_recognition"


def _line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Create one localized OCR line for an already accepted building surface."""

    return OcrLine(text=text, bounds=Bounds(x, y, width, height), confidence=1.0)


def _construction_lines(*, include_build: bool = True) -> tuple[OcrLine, ...]:
    """Return construction body OCR while leaving title ownership to its plan."""

    lines = [
        _line("0/45", x=201, y=408, width=68, height=31),
        _line("Build Now", x=405, y=440, width=160, height=37),
        _line("Time", x=59, y=552, width=71, height=29),
        _line("Requirement", x=62, y=713, width=177, height=27),
        _line("Materials required", x=61, y=865, width=251, height=26),
    ]
    if include_build:
        lines.append(_line("Build", x=671, y=440, width=147, height=37))
    return tuple(lines)


def _construction_target_read(*, present: bool) -> OcrRegionRead:
    """Return the typed header read consumed by the construction parser."""

    plan = compile_screen_content_ocr_region_plans(
        resolved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
        request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_CONSTRUCTION),
        image_size=VIEWPORT,
    )[0]
    result = (
        OcrResult(lines=(_line("Farm", x=180, y=23, width=123, height=46),), words=())
        if present
        else OcrResult(lines=(), words=())
    )
    return OcrRegionRead(
        plan=plan,
        result=result,
        status=OcrRegionReadStatus.PRESENT if present else OcrRegionReadStatus.MISSING,
    )


def _wire_observers(ocr: _BoundedOcrService) -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both production observation paths against the packaged recognizer."""

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


class BuildingConfirmationParserTests(unittest.TestCase):
    """Prove construction and upgrade-confirmation parsing after screen ownership."""

    def test_construction_parser_separates_normal_and_premium_build_controls(self) -> None:
        """A proved construction surface can expose either or both OCR-read actions."""

        image = Image.new("RGB", VIEWPORT)
        normal_and_premium = _build_building_construction_additions(
            image=image,
            lines=_construction_lines(),
            proved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
            target_read=_construction_target_read(present=True),
        )
        self.assertIsNotNone(normal_and_premium)
        assert normal_and_premium is not None
        self.assertEqual(normal_and_premium.screen_evidence, ())
        self.assertEqual(
            set(normal_and_premium.visible_elements),
            {
                UiElementId.PNC_BUILDING_CONSTRUCTION_HEADER,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_NOW_BUTTON,
            },
        )
        self.assertTrue(
            all(
                element.source_kind == VisibleElementSourceKind.OCR
                for element in normal_and_premium.visible_elements.values()
            )
        )

        premium_only = _build_building_construction_additions(
            image=image,
            lines=_construction_lines(include_build=False),
            proved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
            target_read=_construction_target_read(present=True),
        )
        self.assertIsNotNone(premium_only)
        assert premium_only is not None
        self.assertNotIn(
            UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
            premium_only.visible_elements,
        )
        self.assertIn(
            UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_NOW_BUTTON,
            premium_only.visible_elements,
        )

    def test_construction_parser_withholds_controls_when_target_read_is_missing(self) -> None:
        """A missing owned construction title cannot create a guessed building action."""

        additions = _build_building_construction_additions(
            image=Image.new("RGB", VIEWPORT),
            lines=_construction_lines(),
            proved_screen=ScreenType.PNC_BUILDING_CONSTRUCTION,
            target_read=_construction_target_read(present=False),
        )

        self.assertIsNotNone(additions)
        assert additions is not None
        self.assertEqual(additions.visible_elements, {})
        self.assertEqual(additions.screen_evidence, ())

    def test_upgrade_parser_keeps_final_confirmation_distinct_from_base_upgrade(self) -> None:
        """The detail parser exposes its final Upgrade Now confirmation panel separately."""

        image = Image.new("RGB", VIEWPORT)
        lines = (
            _line("Wall", x=182, y=18, width=107, height=50),
            _line("1/45", x=201, y=408, width=68, height=31),
            _line("Upgrade Now", x=401, y=459, width=210, height=32),
            _line("Time", x=58, y=550, width=75, height=37),
            _line("Requirement", x=61, y=714, width=176, height=30),
            _line("Materials required", x=60, y=866, width=242, height=30),
            _line("Effect", x=60, y=1036, width=83, height=33),
        )
        anchors = (
            DetectedTextAnchor(
                id=TextAnchorId.LABEL_UPGRADE,
                text="Upgrade",
                normalized_text="UPGRADE",
                bounds=Bounds(672, 437, 146, 41),
                confidence=1.0,
            ),
        )

        additions = _build_building_detail_additions(image=image, lines=lines, anchors=anchors)

        self.assertIsNotNone(additions)
        assert additions is not None
        self.assertEqual(
            additions.screen_evidence[0].screen_type,
            ScreenType.PNC_BUILDING_DETAILS,
        )
        self.assertIn(UiElementId.PNC_BUILDING_UPGRADE_BUTTON, additions.visible_elements)
        self.assertIn(
            UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
            additions.visible_elements,
        )
        self.assertIn(UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON, additions.visible_elements)
        self.assertEqual(
            additions.visible_elements[
                UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON
            ].extracted_text,
            "Upgrade Now",
        )

    def test_captured_update_failure_is_guarded_through_both_observer_paths(self) -> None:
        """Require exact retry wording and measured controls on the saved splash capture."""

        # A preflight frame: 20260913T211852Z_core_20260913T211751Z_e1dd626b_0012_preflight_settle_11.png.
        with Image.open(FIXTURES / "update_failure_retry_publisher_splash.png") as source:
            image = source.convert("RGB")
        retry_line = _line("Update failed. Try again?", x=98, y=640, width=374, height=38)
        confirm_line = _line("Confirm", x=388, y=890, width=124, height=39)

        with tempfile.TemporaryDirectory() as temp_directory:
            screenshot = ScreenshotService(
                artifact_store=ArtifactStore(root=Path(temp_directory) / "artifacts")
            ).capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="update_failure_popup",
                label="update_failure_popup",
            )
            cases = (
                ("exact_retry", (retry_line, confirm_line), True),
                ("missing_confirm", (retry_line,), False),
                (
                    "nonexact_retry",
                    (_line("Update failed. Try later?", x=98, y=640, width=374, height=38), confirm_line),
                    False,
                ),
            )
            for path in ("builder", "navigation"):
                for case, lines, owns_update in cases:
                    with self.subTest(path=path, case=case):
                        ocr = _BoundedOcrService(lines)
                        builder, navigation = _wire_observers(ocr)
                        observation = (
                            builder.build(screenshot)
                            if path == "builder"
                            else navigation.build(screenshot)
                        )

                        self.assertEqual(
                            ocr.calls,
                            [plan.bounds for plan in compile_guard_ocr_region_plans(image.size)],
                        )
                        self.assertEqual(
                            observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON),
                            owns_update,
                        )
                        if not owns_update:
                            self.assertNotEqual(observation.screen_type, ScreenType.PNC_POPUP)
                            self.assertFalse(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))
                            continue
                        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                        self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
                        self.assertFalse(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))
                        self.assertEqual(observation.frame_ref, screenshot.frame_ref)
                        self.assertIsNotNone(observation.popup_overlay)
                        assert observation.popup_overlay is not None
                        self.assertEqual(
                            observation.popup_overlay.candidates[0].control_kind,
                            PopupControlKind.UPDATE_CONFIRM,
                        )
                        self.assertEqual(
                            observation.require(UiElementId.PNC_UPDATE_CONFIRM_BUTTON).source_kind,
                            VisibleElementSourceKind.GEOMETRY,
                        )
                        confirm = observation.require(UiElementId.PNC_UPDATE_CONFIRM_BUTTON)
                        self.assertEqual(confirm.frame_ref, screenshot.frame_ref)
                        self.assertTrue(Bounds(297, 868, 306, 89).contains_point(confirm.action_point))


if __name__ == "__main__":
    unittest.main()
