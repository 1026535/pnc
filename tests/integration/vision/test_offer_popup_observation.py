"""Offer popup observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

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
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class OfferPopupObservationTests(unittest.TestCase):
    """Proves offer popup observation."""

    def test_observation_builder_classifies_promotional_hero_offer_popup_from_ocr(self) -> None:
        """Recognizes the observed monetized hero-offer modal as a blocking popup with a close target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_offer_popup",
                label="hero_offer_popup",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("5 Hero", x=27, y=65, width=138, height=35),
                            _ocr_line("Savannah", x=68, y=113, width=94, height=22),
                            _ocr_line("$6.99", x=240, y=805, width=60, height=25),
                            _ocr_line("One-time", x=230, y=854, width=81, height=21),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
            self.assertTrue(observation.blocking_popup)
            self.assertEqual(observation.popup_overlay.layout_id, "recognized_offer_without_measured_close")

    def test_observation_builder_classifies_top_up_offer_popup_from_ocr(self) -> None:
        """Recognizes the observed top-up reward modal as a blocking popup with a close target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_top_up_popup",
                label="top_up_offer_popup",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Complete 1st Top-up to Obtain Yune", x=72, y=352, width=382, height=68),
                            _ocr_line("Obtain Now", x=176, y=500, width=180, height=28),
                            _ocr_line("Claim Next Day", x=160, y=612, width=210, height=30),
                            _ocr_line("Top Up", x=188, y=856, width=150, height=34),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
            self.assertTrue(observation.blocking_popup)
            self.assertEqual(observation.popup_overlay.layout_id, "recognized_offer_without_measured_close")

    def test_observation_builder_rejects_unowned_upper_right_x_without_popup_evidence(self) -> None:
        """Does not authorize a bright X when no recognized or measured popup owns it."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (900, 1600), (15, 28, 68))
            drawing = ImageDraw.Draw(image)
            drawing.line((794, 302, 832, 340), fill=(255, 247, 218), width=8)
            drawing.line((832, 302, 794, 340), fill=(255, 247, 218), width=8)
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="generic_visual_popup",
                label="upper_right_close_x",
            )
            ocr_service = _RecordingOcrService(lines=())
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(),
                ocr_service=ocr_service,
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
            self.assertEqual(ocr_service.read_result_calls, 1)
