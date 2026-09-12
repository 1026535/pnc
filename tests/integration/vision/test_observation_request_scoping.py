"""Observation request scoping: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image

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
    build_default_selector_registry,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.recording_selector_engine import _RecordingSelectorEngine
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class ObservationRequestScopingTests(unittest.TestCase):
    """Proves observation request scoping."""

    def test_observation_builder_scans_only_probes_then_current_screen_selectors(self) -> None:
        """Limits template detection to classifier probes first, then the resolved screen slice."""

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
                    id=UiElementId.PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_BAG_SUBTAB_RESOURCE,
                    screens=(ScreenType.PNC_BAG,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
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
            enricher=DefaultObservationEnricher(),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(screenshot)

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(len(selector_engine.requested_selector_ids), 2)
        self.assertIn(UiElementId.PNC_HOME_WORLD_SWITCH, selector_engine.requested_selector_ids[0])
        self.assertIn(UiElementId.PNC_BAG_MAIN_TAB_BAG, selector_engine.requested_selector_ids[0])
        self.assertNotIn(UiElementId.PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON, selector_engine.requested_selector_ids[0])
        self.assertIn(UiElementId.PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON, selector_engine.requested_selector_ids[1])
        self.assertNotIn(UiElementId.PNC_BAG_MAIN_TAB_BAG, selector_engine.requested_selector_ids[1])

    def test_observation_builder_skips_selector_detection_for_world_map_movement_proof(self) -> None:
        """Avoids broad selector scans when movement proof only needs the coordinate bar."""

        registry = build_default_selector_registry()
        selector_engine = _RecordingSelectorEngine(responses=[()])
        coordinate_region = registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR).relative_bounds
        assert coordinate_region is not None
        bounds = coordinate_region.materialize_region(image_size=(100, 100))
        ocr_service = _RecordingOcrService(
            lines=(_ocr_line("X:12 Y:34", x=bounds.x, y=bounds.y, width=max(1, bounds.width), height=max(1, bounds.height)),)
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=selector_engine,
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(ocr_service=ocr_service, selector_registry=registry),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(screenshot, request=ObservationRequest.world_map_movement_proof_follow_up())

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(len(selector_engine.requested_selector_ids), 1)
        self.assertEqual(selector_engine.requested_selector_ids[0], ())
        self.assertEqual(ocr_service.read_result_calls, 0)

    def test_observation_builder_keeps_click_only_geometry_hidden_without_detection(self) -> None:
        """Does not auto-materialize relative click regions that still require explicit visibility proof."""

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
                    id=UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.PLANNED,
                    click=ClickDefinition(),
                    relative_bounds=RelativeBounds(
                        x_ratio=0.1,
                        y_ratio=0.1,
                        width_ratio=0.2,
                        height_ratio=0.2,
                    ),
                    materialize_relative_bounds=False,
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
                        selector_id=UiElementId.PNC_HOME_RESEARCH_BUTTON,
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
            enricher=DefaultObservationEnricher(),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(screenshot)

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertFalse(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))

    def test_observation_builder_skips_ocr_for_base_requests(self) -> None:
        """Leaves OCR idle when the caller requests only the cheap selector-and-geometry base pass."""

        ocr_service = _RecordingOcrService(lines=())
        builder = ObservationBuilder(
            selector_registry=SelectorRegistry(selectors=()),
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),
                ocr_service=ocr_service,
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(ocr_service=ocr_service),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        builder.build(screenshot, request=ObservationRequest.base())

        self.assertEqual(ocr_service.read_result_calls, 0)
        self.assertEqual(ocr_service.read_text_calls, 0)
