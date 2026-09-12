"""Settings profile observation: verifies the named internal boundary with offline fixtures."""

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


class SettingsProfileObservationTests(unittest.TestCase):
    """Proves settings profile observation."""

    def test_observation_builder_classifies_more_menu_and_exposes_requested_actions(self) -> None:
        """Recognizes More-related overlays and exposes both the footer Settings action and direct menu entries."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k304_more_menu",
                label="more_menu_live_like",
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
                            _ocr_line("Manage Char", x=78, y=1330, width=178, height=34),
                            _ocr_line("Lord Info", x=315, y=1332, width=154, height=34),
                            _ocr_line("VIP", x=562, y=1333, width=58, height=34),
                            _ocr_line("Improve Might", x=690, y=1330, width=184, height=34),
                            _ocr_line("Rank", x=105, y=1444, width=72, height=31),
                            _ocr_line("Friend", x=318, y=1444, width=88, height=31),
                            _ocr_line("Guides", x=520, y=1444, width=91, height=31),
                            _ocr_line("Settings", x=742, y=1444, width=112, height=31),
                            _ocr_line("More", x=794, y=1567, width=71, height=27),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_MORE_MENU)
            self.assertTrue(observation.has(UiElementId.PNC_MORE_SETTINGS))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_OVERLAY_MANAGE_CHAR))
            self.assertFalse(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_LORD_INFO))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_VIP))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_IMPROVE_MIGHT))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_builder_classifies_more_settings_submenu_with_top_left_back(self) -> None:
        """Recognizes the full-screen Settings submenu and exposes the canonical back target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k304_more_settings_menu",
                label="more_settings_menu_live_like",
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
                            _ocr_line("Settings", x=112, y=20, width=128, height=28),
                            _ocr_line("Account", x=120, y=94, width=102, height=24),
                            _ocr_line("Manage Char.", x=304, y=94, width=134, height=24),
                            _ocr_line("Search", x=122, y=188, width=88, height=24),
                            _ocr_line("Rank", x=344, y=188, width=64, height=24),
                            _ocr_line("Blacklist", x=320, y=374, width=104, height=24),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_SETTINGS)
            self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))
            self.assertFalse(observation.has(UiElementId.PNC_MORE_SETTINGS))
            self.assertFalse(observation.has(UiElementId.PNC_MORE_OVERLAY_MANAGE_CHAR))
            self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_builder_classifies_lord_info_and_extracts_displayed_name(self) -> None:
        """Recognizes the Lord Info screen and exposes the OCR-backed displayed lord name."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k304_lord_info",
                label="lord_info_live_like",
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
                            _ocr_line("Lord Info", x=184, y=20, width=208, height=48),
                            _ocr_line("Gear", x=52, y=111, width=83, height=42),
                            _ocr_line("K304554ca2797", x=240, y=1048, width=210, height=27),
                            _ocr_line("Talent", x=68, y=1560, width=82, height=28),
                            _ocr_line("Lord Info", x=220, y=1559, width=114, height=30),
                            _ocr_line("Boost Info", x=386, y=1561, width=124, height=27),
                            _ocr_line("Alliance Info", x=561, y=1561, width=120, height=26),
                            _ocr_line("Achievements", x=731, y=1567, width=115, height=17),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LORD_INFO)
            self.assertTrue(observation.has(UiElementId.PNC_LORD_INFO_HEADER))
            self.assertEqual(
                observation.require(UiElementId.PNC_LORD_INFO_NAME_LABEL).extracted_text,
                "K304554ca2797",
            )
            self.assertEqual(observation.current_castle_name, "K304554ca2797")
