"""Popup close rejection: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
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


class PopupCloseRejectionTests(unittest.TestCase):
    """Proves popup close rejection."""

    def test_observation_builder_rejects_bright_x_outside_popup_close_zone(self) -> None:
        """Avoids treating crossed artwork left of the guarded upper-right close band as a popup."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (900, 1600), (15, 28, 68))
            drawing = ImageDraw.Draw(image)
            drawing.line((698, 302, 736, 340), fill=(255, 210, 90), width=8)
            drawing.line((736, 302, 698, 340), fill=(255, 210, 90), width=8)
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="generic_visual_popup",
                label="crossed_artwork",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(ocr_service=_FakeOcrService(lines=())),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.blocking_popup)

    def test_observation_builder_rejects_wide_crossed_badge_in_popup_close_zone(self) -> None:
        """Rejects the live-like wide crossed badge geometry found in the home-city top-right HUD."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (900, 1600), (15, 28, 68))
            drawing = ImageDraw.Draw(image)
            drawing.line((814, 110, 860, 142), fill=(255, 211, 92), width=7)
            drawing.line((860, 110, 814, 142), fill=(255, 211, 92), width=7)
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="generic_visual_popup",
                label="wide_crossed_badge",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(ocr_service=_FakeOcrService(lines=())),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.blocking_popup)

    def test_observation_builder_owns_visual_x_as_post_upgrade_warning_when_requested(self) -> None:
        """Routes the warning X to the building task and localizes Confirm without OCR."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (900, 1600), (15, 28, 68))
            drawing = ImageDraw.Draw(image)
            drawing.line((778, 514, 820, 556), fill=(255, 211, 92), width=8)
            drawing.line((820, 514, 778, 556), fill=(255, 211, 92), width=8)
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="building_upgrade_warning",
                label="shield_warning",
            )
            ocr_service = _RecordingOcrService(lines=())
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(ocr_service=ocr_service),
            )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.building_upgrade_warning_follow_up(),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_UPGRADE_WARNING)
            self.assertFalse(observation.blocking_popup)
            confirm = observation.require(UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON)
            self.assertEqual(confirm.action_point, (648, 880))
            self.assertEqual(confirm.source_kind, VisibleElementSourceKind.GEOMETRY)
            self.assertEqual(ocr_service.read_result_calls, 0)

    def test_observation_builder_classifies_vip_daily_reset_popup_from_ocr(self) -> None:
        """Recognizes the VIP daily-reset popup as a dedicated blocking screen with a tappable Close button."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (384, 633), (15, 28, 68)))),
                artifact_directory="vip_daily_reset_popup",
                label="vip_daily_reset_popup",
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
                            _ocr_line("VIP", x=176, y=222, width=43, height=24),
                            _ocr_line("Log in every day to get VIP pts.", x=98, y=246, width=208, height=22),
                            _ocr_line("Gain VIP pts: 96", x=113, y=278, width=160, height=24),
                            _ocr_line("Consec. login days: 2", x=93, y=312, width=190, height=22),
                            _ocr_line("Pts to gain tomorrow: 112", x=90, y=339, width=205, height=20),
                            _ocr_line("Close", x=155, y=407, width=75, height=28),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_VIP_DAILY_RESET)
            self.assertTrue(observation.blocking_popup)
            self.assertTrue(observation.has(UiElementId.PNC_VIP_DAILY_RESET_HEADER))
            self.assertTrue(observation.has(UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_observation_builder_rejects_hero_offer_near_match_without_price_and_one_time(self) -> None:
        """Keeps the screen unknown when the hero-offer popup evidence is incomplete."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_offer_probe",
                label="hero_offer_near_match",
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
                            _ocr_line("5 Hero", x=27, y=65, width=138, height=35),
                            _ocr_line("Savannah", x=68, y=113, width=94, height=22),
                            _ocr_line("1100", x=236, y=443, width=98, height=44),
                            _ocr_line("3900%", x=410, y=397, width=87, height=68),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
