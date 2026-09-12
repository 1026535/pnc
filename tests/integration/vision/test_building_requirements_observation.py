"""Building requirements observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class BuildingRequirementsObservationTests(unittest.TestCase):
    """Proves building requirements observation."""

    def test_observation_builder_classifies_building_detail_and_exposes_back_click_target(self) -> None:
        """Recognizes a building-detail screen from OCR and surfaces tappable controls."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k313_colddukeofthenorth",
                label="building_detail",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Castle", x=88, y=16, width=120, height=30),
                            _ocr_line("Upgrade", x=682, y=308, width=120, height=40),
                            _ocr_line("ColdDukeOfTheNorth", x=101, y=465, width=256, height=32),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
            self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))

    def test_observation_builder_exposes_shared_building_requirement_controls_on_exact_building_screens(self) -> None:
        """Recognizes unmet upgrade prerequisites on exact building-owned screens through shared OCR controls."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_infantry_requirement",
                label="infantry_requirement",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Infantry Barracks", x=88, y=16, width=240, height=30),
                            _ocr_line("Glory Level", x=588, y=142, width=154, height=32),
                            _ocr_line("Upgrade", x=734, y=308, width=120, height=40),
                            _ocr_line("Requirement", x=59, y=714, width=177, height=32),
                            _ocr_line("Recruiting Center : Lv.7", x=152, y=769, width=278, height=28),
                            _ocr_line("Go", x=732, y=766, width=47, height=31),
                            _ocr_line("Materials required", x=58, y=866, width=246, height=33),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_INFANTRY_BARRACKS)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_HEADER))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON))
            self.assertEqual(
                observation.require(UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL).extracted_text,
                "Recruiting Center : Lv.7",
            )

    def test_observation_builder_pairs_requirement_label_with_actionable_go_row(self) -> None:
        """Selects the unmet row aligned with Go when a satisfied prerequisite is listed above it."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="castle_multi_requirement",
                label="castle_multi_requirement",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Castle", x=88, y=16, width=120, height=30),
                            _ocr_line("Territory Overview", x=620, y=130, width=220, height=32),
                            _ocr_line("Upgrade", x=680, y=420, width=150, height=45),
                            _ocr_line("Requirement", x=60, y=714, width=177, height=32),
                            _ocr_line("Wall : Lv.9", x=154, y=768, width=150, height=28),
                            _ocr_line("Warehouse : Lv.9", x=154, y=834, width=210, height=28),
                            _ocr_line("Go", x=732, y=832, width=47, height=31),
                            _ocr_line("Materials required", x=58, y=931, width=246, height=33),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE)
            self.assertEqual(
                observation.require(UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL).extracted_text,
                "Warehouse : Lv.9",
            )

    def test_observation_builder_classifies_castle_screen_when_territory_overview_wraps_across_two_ocr_lines(self) -> None:
        """Keeps Castle on its exact screen when OCR splits `Territory Overview` into stacked fragments."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_castle_split_overview",
                label="castle_split_overview",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Castle", x=181, y=18, width=144, height=51),
                            _ocr_line("Territory", x=691, y=129, width=108, height=32),
                            _ocr_line("Overview", x=691, y=157, width=115, height=27),
                            _ocr_line("Glory Level", x=655, y=346, width=183, height=44),
                            _ocr_line("Upgrade", x=673, y=438, width=146, height=41),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE)
            self.assertTrue(observation.has(UiElementId.PNC_CASTLE_TERRITORY_OVERVIEW_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_CASTLE_GLORY_LEVEL_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
