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

    def test_observation_builder_runs_ocr_when_requested(self) -> None:
        """Invokes OCR when the observation request explicitly asks for OCR-backed facts."""

        ocr_service = _RecordingOcrService(lines=())
        builder = ObservationBuilder(
            selector_registry=_minimal_runtime_registry(),
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),

            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(),
            ocr_service=ocr_service,
            )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
                "frame_ref": make_captured_frame(b"").frame_ref,
            },
        )()

        builder.build(screenshot, request=ObservationRequest.full_runtime_default())

        self.assertEqual(ocr_service.read_result_calls, 1)

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

    def test_observation_builder_tags_ocr_sources(self) -> None:
        """Keeps OCR-synthesized selectors distinct from geometry-backed visibility."""

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
                    relative_bounds=None,
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
            enricher=PncObservationEnricher(

            ),
            ocr_service=_FakeOcrService(
                    lines=(
                        _ocr_line("Alliance", x=108, y=883, width=124, height=8),
                        _ocr_line("More", x=360, y=883, width=74, height=8),
                    )
                )
            )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (540, 960), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
                "frame_ref": make_captured_frame(b"").frame_ref,
            },
        )()

        observation = builder.build(
            screenshot,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(
            observation.require(UiElementId.PNC_BOTTOM_NAV_MORE).source_kind,
            VisibleElementSourceKind.OCR,
        )
