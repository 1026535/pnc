"""Valiant popup fixture: verifies the named internal boundary with offline fixtures."""

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
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_popup_additions,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class ValiantPopupFixtureTests(unittest.TestCase):
    """Proves valiant popup fixture."""

    def test_valiant_conquest_fixture_uses_ocr_ownership_and_measured_close_x(self) -> None:
        """Recognizes the real event modal only when OCR and its close X agree."""

        fixture_path = TEST_DATA_ROOT / "screen_recognition" / "valiant_conquest_popup_real_sanitized.png"
        with Image.open(fixture_path) as source:
            image = source.convert("RGB")
        lines = (
            _ocr_line("Valiant Conquest is about to start.", x=45, y=809, width=808, height=45),
            _ocr_line("Valiant Conquest is about to begin!", x=168, y=986, width=564, height=30),
            _ocr_line("Earn points by defeating enemies and", x=144, y=1022, width=613, height=34),
            _ocr_line("Activate shields", x=77, y=1220, width=235, height=27),
            _ocr_line("Event Details", x=77, y=1328, width=195, height=30),
        )

        additions = _build_popup_additions(image=image, lines=lines, anchors=())

        self.assertIsNotNone(additions)
        assert additions is not None
        close_button = additions.visible_elements[UiElementId.PNC_POPUP_CLOSE_BUTTON]
        self.assertEqual(VisibleElementSourceKind.GEOMETRY, close_button.source_kind)
        self.assertEqual("ocr_valiant_conquest_popup", additions.screen_evidence[0].reason)
        self.assertEqual((812, 322), close_button.action_point)

        with tempfile.TemporaryDirectory() as temp_directory:
            screenshot = ScreenshotService(
                artifact_store=ArtifactStore(root=Path(temp_directory) / "artifacts")
            ).capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="valiant_conquest_popup",
                label="known_event_popup",
            )
            observation = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(ocr_service=_FakeOcrService(lines=lines)),
            ).build(screenshot)

        self.assertEqual(ScreenType.PNC_POPUP, observation.screen_type)
        self.assertTrue(observation.blocking_popup)
        self.assertEqual(
            (812, 322),
            observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON).action_point,
        )

    def test_valiant_conquest_requires_supporting_ocr_and_measured_close_x(self) -> None:
        """Rejects title-like fragments when modal support or the measured X is absent."""

        fixture_path = TEST_DATA_ROOT / "screen_recognition" / "valiant_conquest_popup_real_sanitized.png"
        with Image.open(fixture_path) as source:
            image = source.convert("RGB")
        title = _ocr_line("Valiant Conquest is about to start.", x=45, y=809, width=808, height=45)
        support = _ocr_line("Event Details", x=77, y=1328, width=195, height=30)

        self.assertIsNone(_build_popup_additions(image=image, lines=(title,), anchors=()))

        without_x = image.copy()
        ImageDraw.Draw(without_x).rectangle((775, 275, 850, 365), fill=(26, 39, 76))
        self.assertIsNone(
            _build_popup_additions(image=without_x, lines=(title, support), anchors=())
        )
