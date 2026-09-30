"""Login observation: semantic parsers under explicit screen decisions."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationAdditions
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    _build_account_switch_additions,
    _build_login_additions,
)
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import OcrResult, OcrService
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.build_observation_from_ocr_lines import (
    _build_observation_from_ocr_lines,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.publication import make_publication_pair


class LoginObservationTests(unittest.TestCase):
    """Proves login semantic parsing after explicit identity acceptance."""

    def test_both_publishers_retain_current_account_content(self) -> None:
        """The real publisher pair shares the declared account content contract."""

        class LoginGuard:
            def recognize_guards(self, image, request, *, ocr_context):
                return ObservationAdditions(guard_verdict=GuardVerdict.CLEAR)

            def detect_interruption(self, image, *, ocr_context, owned_dismiss_bounds=(), owned_navigation_screen=None):
                return ObservationAdditions(guard_verdict=GuardVerdict.CLEAR)

            def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions, layout_id=None):
                return ObservationAdditions(current_pnc_account_id="user@example.com")

        recognizer = Mock()
        recognizer.recognize.return_value = VisualRecognition(evidence=(
            ScreenEvidence(ScreenType.PNC_LOGIN, "login_fixture"),
        ))
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        with patch("tests.support.pnc.publication.load_visual_screen_recognizer", return_value=recognizer):
            builder, navigation = make_publication_pair(
                selector_registry=build_default_selector_registry(),
                matcher=OpenCvTemplateMatcher(),
                enricher=LoginGuard(),
                ocr_service=ocr,
            )
        capture = CapturedScreenshot(
            None, Image.new("RGB", (540, 960), "white"), "PNG",
            ephemeral_captured_at=datetime.now(UTC),
        )

        with patch.object(ImageSelectorEngine, "detect", return_value=[]):
            legacy = builder.build(capture)
        core = navigation.build(capture, include_content=True)
        self.assertEqual((legacy.screen_type, core.screen_type), (ScreenType.PNC_LOGIN,) * 2)
        self.assertEqual(legacy.current_pnc_account_id, "user@example.com")
        self.assertEqual(core.current_pnc_account_id, legacy.current_pnc_account_id)

    def test_explicit_screen_decision_publishes_login_controls(self) -> None:
        """Publishes credential controls and the displayed account identifier."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Email", x=80, y=225, width=70, height=26),
                _ocr_line("user@example.com", x=92, y=276, width=188, height=22),
                _ocr_line("Password", x=82, y=365, width=110, height=26),
                _ocr_line("Log In", x=211, y=566, width=105, height=30),
            ),
            accepted_screen=ScreenType.PNC_LOGIN,
            image_size=(540, 960),
            semantic_parser=lambda image, lines: _build_login_additions(image=image, lines=lines),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_LOGIN)
        self.assertTrue(observation.has(UiElementId.PNC_LOGIN_USERNAME_FIELD))
        self.assertTrue(observation.has(UiElementId.PNC_LOGIN_PASSWORD_FIELD))
        self.assertTrue(observation.has(UiElementId.PNC_LOGIN_SUBMIT_BUTTON))
        self.assertEqual(observation.require(UiElementId.PNC_LOGIN_USERNAME_FIELD).bounds.x, 60)
        self.assertEqual(observation.require(UiElementId.PNC_LOGIN_PASSWORD_FIELD).bounds.y, 352)
        self.assertEqual(observation.require(UiElementId.PNC_LOGIN_SUBMIT_BUTTON).bounds.width, 210)
        self.assertEqual(observation.current_pnc_account_id, "user@example.com")

    def test_explicit_screen_decision_publishes_account_switch_controls(self) -> None:
        """Publishes account-switch continuation controls and the displayed account identifier."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Switch Account", x=134, y=42, width=180, height=28),
                _ocr_line("user@example.com", x=116, y=292, width=188, height=22),
                _ocr_line("Continue", x=210, y=576, width=102, height=28),
                _ocr_line("Change Account", x=165, y=654, width=170, height=28),
            ),
            accepted_screen=ScreenType.PNC_ACCOUNT_SWITCH,
            image_size=(540, 960),
            semantic_parser=lambda image, lines: _build_account_switch_additions(image=image, lines=lines),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ACCOUNT_SWITCH)
        self.assertTrue(observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON))
        self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON).bounds.x, 159)
        self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON).bounds.width, 340)
        self.assertEqual(observation.current_pnc_account_id, "user@example.com")


if __name__ == "__main__":
    unittest.main()
