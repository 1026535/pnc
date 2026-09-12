"""Building speedup observation: verifies the named internal boundary with offline fixtures."""

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


class BuildingSpeedupObservationTests(unittest.TestCase):
    """Proves building speedup observation."""

    def test_observation_builder_classifies_exact_building_upgrade_confirmation_layout(self) -> None:
        """Keeps the exact building screen when the shared final-confirmation layout replaces the base tiles."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_wall_upgrade_confirm",
                label="wall_upgrade_confirm",
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
                            _ocr_line("Wall", x=182, y=18, width=107, height=50),
                            _ocr_line("Glory Level", x=655, y=346, width=182, height=42),
                            _ocr_line("Upgrade", x=672, y=437, width=146, height=41),
                            _ocr_line("Upgrade Now", x=401, y=459, width=210, height=32),
                            _ocr_line("Time", x=58, y=550, width=75, height=37),
                            _ocr_line("Requirement", x=61, y=714, width=176, height=30),
                            _ocr_line("Castle: Lv.8", x=153, y=768, width=141, height=27),
                            _ocr_line("Materials required", x=60, y=866, width=242, height=30),
                            _ocr_line("Effect", x=60, y=1036, width=83, height=33),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WALL)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL))
            self.assertTrue(observation.has(UiElementId.PNC_WALL_UPGRADE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_HEADER))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON))

    def test_observation_builder_exposes_shared_speedup_on_active_exact_building(self) -> None:
        """Models the common top-right Speedup action even when an exact screen has only an Upgrade spec."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="warehouse_speedup",
                label="warehouse_speedup",
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
                            _ocr_line("Warehouse", x=181, y=18, width=220, height=50),
                            _ocr_line("Glory Level", x=655, y=346, width=182, height=42),
                            _ocr_line("Speedup", x=675, y=438, width=145, height=41),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WAREHOUSE)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON))

    def test_observation_builder_classifies_inventory_build_speedup_screen(self) -> None:
        """Separates inventory Auto Speedup from the premium Build Now action."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="build_speedup",
                label="build_speedup",
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
                            _ocr_line("Build Speedup", x=182, y=18, width=280, height=50),
                            _ocr_line("Build Now", x=178, y=1510, width=180, height=45),
                            _ocr_line("Auto Speedup", x=520, y=1510, width=230, height=45),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILD_SPEEDUP)
            self.assertTrue(observation.has(UiElementId.PNC_BUILD_SPEEDUP_AUTO_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILD_SPEEDUP_PREMIUM_BUILD_NOW_BUTTON))

    def test_observation_builder_classifies_build_speedup_confirmation_popup(self) -> None:
        """Exposes the final inventory-consumption Confirm separately from the speedup list."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="build_speedup_confirm",
                label="build_speedup_confirm",
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
                            _ocr_line("Build Speedup", x=305, y=420, width=290, height=50),
                            _ocr_line("Confirm", x=362, y=1165, width=180, height=45),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILD_SPEEDUP_CONFIRM)
            self.assertTrue(observation.has(UiElementId.PNC_BUILD_SPEEDUP_CONFIRM_BUTTON))
