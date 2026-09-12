"""Building confirmation observation: verifies the named internal boundary with offline fixtures."""

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


class BuildingConfirmationObservationTests(unittest.TestCase):
    """Proves building confirmation observation."""

    def test_observation_builder_classifies_resource_funded_construction_confirmation(self) -> None:
        """Distinguishes ordinary Build from the premium Build Now action on construction confirmation."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="building_construction_confirmation",
                label="farm_construction_confirmation",
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
                            _ocr_line("Farm", x=179, y=23, width=124, height=46),
                            _ocr_line("Build", x=701, y=435, width=89, height=37),
                            _ocr_line("Build Now", x=437, y=455, width=156, height=30),
                            _ocr_line("Time", x=58, y=537, width=75, height=37),
                            _ocr_line("Requirement", x=61, y=714, width=176, height=30),
                            _ocr_line("Castle: Lv.1", x=153, y=768, width=141, height=27),
                            _ocr_line("Materials required", x=60, y=866, width=242, height=30),
                            _ocr_line("Effect", x=60, y=1036, width=83, height=33),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_CONSTRUCTION)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_NOW_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_HEADER))

    def test_generic_building_detail_exposes_upgrade_confirmation_panel(self) -> None:
        """Models final Upgrade from structural sections when low-contrast Upgrade Now OCR is missed."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="farm_upgrade_confirmation",
                label="farm_upgrade_confirmation",
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
                            _ocr_line("Farm", x=180, y=23, width=123, height=46),
                            _ocr_line("Where Food is produced. Upgrade", x=471, y=245, width=415, height=26),
                            _ocr_line("Upgrade", x=671, y=440, width=147, height=37),
                            _ocr_line("Time", x=59, y=552, width=71, height=29),
                            _ocr_line("Requirement", x=62, y=713, width=177, height=27),
                            _ocr_line("Materials required", x=61, y=865, width=251, height=26),
                            _ocr_line("Effect", x=60, y=1035, width=83, height=31),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON))

    def test_observation_builder_rejects_upgrade_like_non_building_screens(self) -> None:
        """Keeps ambiguous upgrade screens unknown when the building evidence is incomplete."""

        cases = (
            (
                "hero_detail_upgrade",
                (
                    _ocr_line("Hero", x=120, y=18, width=120, height=30),
                    _ocr_line("Upgrade", x=682, y=308, width=120, height=40),
                    _ocr_line("Enhance", x=118, y=210, width=160, height=34),
                    _ocr_line("Evolve", x=585, y=1220, width=160, height=40),
                ),
            ),
            (
                "generic_modal_upgrade",
                (
                    _ocr_line("Rewards", x=310, y=40, width=180, height=30),
                    _ocr_line("Upgrade", x=682, y=308, width=120, height=40),
                    _ocr_line("Claim Available", x=160, y=440, width=220, height=30),
                ),
            ),
        )

        for label, lines in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_directory:
                root = Path(temp_directory)
                screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
                screenshot = screenshot_service.capture(
                    _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                    artifact_directory="k313_probe",
                    label=label,
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
                            lines=lines,
                        )
                    ),
                )

                observation = builder.build(screenshot)

                self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
                self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
