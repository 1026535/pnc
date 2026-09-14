"""Observation source tags: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.clear_observation_enricher import _ClearObservationEnricher
from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame

import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    DefaultObservationEnricher,
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.image_models import SelectorMatch
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import (
    ClickDefinition,
    DetectionKind,
    RelativeBounds,
    Region,
    SelectorDefinition,
    SelectorRegistry,
    SelectorStatus,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.recording_selector_engine import _RecordingSelectorEngine
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class ObservationSourceTagsTests(unittest.TestCase):
    """Proves observation source tags."""

    def test_observation_builder_runs_requested_bounded_content_reads(self) -> None:
        """Read the requested building level only after captured Institute identity."""

        from tests.integration.vision.test_building_level_publication import _wire, _capture, _institute_lines
        builder, _, contexts = _wire(_institute_lines())
        screenshot = _capture("institute_audit.png", session_id="requested-source-tags")
        context = builder.create_ocr_context(screenshot)
        observation = builder.build(screenshot, request=ObservationRequest.source_screen_retry(ScreenType.PNC_INSTITUTE), ocr_context=context)
        self.assertEqual(observation.screen_type, ScreenType.PNC_INSTITUTE)
        self.assertTrue(any(read.required_fact == "building_level_and_actions" for read in context.read_diagnostics))
        self.assertTrue(all(read.region is not None for read in context.read_diagnostics))


    def test_observation_builder_tags_template_and_geometry_sources(self) -> None:
        """Carries template and geometry provenance onto the final visible-element map."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_BOTTOM_NAV_MORE,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.GUARDED_GEOMETRY,
                    status=SelectorStatus.CLICK_MAPPED,
                    click=ClickDefinition(),
                    relative_bounds=RelativeBounds(
                        x_ratio=0.70,
                        y_ratio=0.80,
                        width_ratio=0.10,
                        height_ratio=0.10,
                    ),
                ),
            )
        )
        selector_engine = _RecordingSelectorEngine(
            responses=[
                (
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_WORLD_SWITCH,
                        bounds=Region(x=10, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                        bounds=Region(x=40, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        bounds=Region(x=70, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                ),
                (),
            ]
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=selector_engine,
            screen_classifier=ScreenClassifier(),
            enricher=_ClearObservationEnricher(),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (900, 1600), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
                "frame_ref": make_captured_frame(b"").frame_ref,
            },
        )()

        observation = builder.build(screenshot, request=ObservationRequest.base())

        self.assertEqual(
            observation.require(UiElementId.PNC_HOME_WORLD_SWITCH).source_kind,
            VisibleElementSourceKind.TEMPLATE,
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_BOTTOM_NAV_MORE).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )

    def test_observation_builder_tags_captured_ocr_labels_with_frame_provenance(self) -> None:
        """Parsed level labels retain OCR provenance and cannot become controls."""

        from tests.integration.vision.test_building_level_publication import _wire, _capture, _institute_lines
        builder, _, _ = _wire(_institute_lines())
        capture = _capture("institute_audit.png", session_id="label-source-tags")
        observation = builder.build(capture)
        label = observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL)
        self.assertEqual(label.source_kind, VisibleElementSourceKind.OCR)
        self.assertEqual(label.frame_ref, capture.frame_ref)
        self.assertEqual(label.source_screen, ScreenType.PNC_INSTITUTE)
        self.assertEqual(label.extracted_text, "8/45")
        self.assertFalse(label.identity_evidence)
        self.assertIsNone(label.action_point)
