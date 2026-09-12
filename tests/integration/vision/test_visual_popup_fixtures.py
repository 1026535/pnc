"""Visual popup fixtures: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pnc_automation.core.errors import ScreenClassificationError
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.ocr.ocr_service import RapidOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_popup_additions,
    _build_visual_popup_close_additions,
)
from pnc_automation.app.pnc.vision.text_anchors import TextAnchorDetector

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class VisualPopupFixturesTests(unittest.TestCase):
    """Proves visual popup fixtures."""

    def test_shifted_x_real_fixture_gate_when_configured(self) -> None:
        """Gate generic shifted-X promotion on a real screenshot fixture.

        Configure ``popup_recovery_shifted_x_real_fixture`` in the local-only
        fixture map with a reviewed screenshot when one is available.  Until
        then this remains an applicability skip rather than treating synthetic
        geometry as provenance for live promotion.
        """

        fixture_path = require_local_fixture_artifact("popup_recovery_shifted_x_real_fixture")
        try:
            ocr_service = RapidOcrService()
        except ScreenClassificationError as error:
            self.skipTest(str(error))
        with Image.open(fixture_path) as fixture:
            image = fixture.convert("RGB")
        ocr_result = ocr_service.read_result(image)
        additions = _build_popup_additions(
            image=image,
            lines=ocr_result.lines,
            anchors=TextAnchorDetector().detect(ocr_result),
        )
        if additions is None or UiElementId.PNC_POPUP_CLOSE_BUTTON not in additions.visible_elements:
            self.fail(
                "Configured popup_recovery_shifted_x_real_fixture did not prove a modal-owned measured X; "
                "retain the feature behind the evidence gate."
            )
        close_button = additions.visible_elements[UiElementId.PNC_POPUP_CLOSE_BUTTON]
        self.assertLess(close_button.action_point[0], int(image.width * 0.86))

    def test_visual_popup_close_fixtures_require_surface_and_emit_action_points(self) -> None:
        """Accepts both sanitized real modal layouts through the surface-owned X fallback."""

        fixture_directory = TEST_DATA_ROOT / "screen_recognition"
        for fixture_name in ("generic_popup_quit_real_sanitized.png", "generic_popup_offer_real_sanitized.png"):
            with self.subTest(fixture=fixture_name), Image.open(fixture_directory / fixture_name) as source:
                additions = _build_visual_popup_close_additions(image=source.convert("RGB"))

            self.assertIsNotNone(additions)
            assert additions is not None
            close_button = additions.visible_elements[UiElementId.PNC_POPUP_CLOSE_BUTTON]
            self.assertEqual(VisibleElementSourceKind.GEOMETRY, close_button.source_kind)
            self.assertEqual("visual_upper_right_close_x", additions.screen_evidence[0].reason)
            self.assertGreater(close_button.action_point[0], 0)
            self.assertGreater(close_button.action_point[1], 0)

    def test_recognized_update_popup_wins_over_generic_x_fallback(self) -> None:
        """Keeps the typed update control when the same frame also contains a generic X."""

        image = Image.new("RGB", (540, 960), (15, 28, 68))
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((25, 100, 515, 780), fill=(25, 33, 50), outline=(65, 82, 110), width=4)
        drawing.line((476, 46, 504, 74), fill=(255, 247, 218), width=7)
        drawing.line((504, 46, 476, 74), fill=(255, 247, 218), width=7)
        enricher = PncObservationEnricher(
            ocr_service=_FakeOcrService(
                lines=(
                    _ocr_line("New version detected. Tap Confirm to update.", x=58, y=300, width=420, height=28),
                    _ocr_line("Confirm", x=221, y=531, width=90, height=27),
                )
            )
        )

        additions = enricher.detect_interruption(image)

        self.assertIn(UiElementId.PNC_UPDATE_CONFIRM_BUTTON, additions.visible_elements)
        self.assertNotIn(UiElementId.PNC_POPUP_CLOSE_BUTTON, additions.visible_elements)
        self.assertEqual("ocr_update_required_popup", additions.screen_evidence[0].reason)
