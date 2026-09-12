"""Login observation: verifies the named internal boundary with offline fixtures."""

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
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class LoginObservationTests(unittest.TestCase):
    """Proves login observation."""

    def test_observation_builder_classifies_login_from_live_like_ocr(self) -> None:
        """Recognizes the credential form from OCR and exposes the actionable login controls."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_login",
                label="login_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Email", x=80, y=225, width=70, height=26),
                            _ocr_line("user@example.com", x=92, y=276, width=188, height=22),
                            _ocr_line("Password", x=82, y=365, width=110, height=26),
                            _ocr_line("Log In", x=211, y=566, width=105, height=30),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LOGIN)
            self.assertTrue(observation.has(UiElementId.PNC_LOGIN_USERNAME_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_LOGIN_PASSWORD_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_LOGIN_SUBMIT_BUTTON))
            self.assertEqual(observation.require(UiElementId.PNC_LOGIN_USERNAME_FIELD).bounds.x, 60)
            self.assertEqual(observation.require(UiElementId.PNC_LOGIN_PASSWORD_FIELD).bounds.y, 352)
            self.assertEqual(observation.require(UiElementId.PNC_LOGIN_SUBMIT_BUTTON).bounds.width, 210)
            self.assertEqual(observation.current_pnc_account_id, "user@example.com")

    def test_observation_builder_classifies_account_switch_from_live_like_ocr(self) -> None:
        """Recognizes account-switch UI and exposes the verified-account continuation controls."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_account_switch",
                label="account_switch_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Switch Account", x=134, y=42, width=180, height=28),
                            _ocr_line("user@example.com", x=116, y=292, width=188, height=22),
                            _ocr_line("Continue", x=210, y=576, width=102, height=28),
                            _ocr_line("Change Account", x=165, y=654, width=170, height=28),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_ACCOUNT_SWITCH)
            self.assertTrue(observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON))
            self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON).bounds.x, 159)
            self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON).bounds.width, 340)
            self.assertEqual(observation.current_pnc_account_id, "user@example.com")
