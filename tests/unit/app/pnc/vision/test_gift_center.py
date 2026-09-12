"""Regressions for the Gift Center observed during the navigation audit."""

from dataclasses import replace
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import _build_gift_center_additions
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


class GiftCenterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = Image.new("RGB", (900, 1600))
        self.lines = (
            OcrLine("Gift Center", Bounds(183, 22, 250, 49), 0.99),
            OcrLine("Login Gift", Bounds(662, 155, 190, 45), 0.99),
            OcrLine("Expires in 03:12:06", Bounds(599, 279, 252, 25), 0.99),
            OcrLine("Lucifer Special Offer", Bounds(446, 380, 410, 44), 0.99),
            OcrLine("Claim rewards daily for 3 days", Bounds(382, 508, 460, 27), 0.99),
            OcrLine("Deluxe Summons", Bounds(501, 605, 355, 43), 0.99),
        )

    def test_reads_right_aligned_titles_without_expiry_or_subtitle_rows(self) -> None:
        additions = _build_gift_center_additions(image=self.image, lines=self.lines)
        self.assertIsNotNone(additions)
        self.assertEqual([entry.title_text for entry in additions.list_entries], [
            "Login Gift", "Lucifer Special Offer", "Deluxe Summons",
        ])
        self.assertTrue(all(entry.kind == ListEntryKind.GIFT_ENTRY for entry in additions.list_entries))
        # Back is published only from catalog-reviewed safe-root screens;
        # Gift Center has no independently proved Back control.
        self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, additions.visible_elements)
        self.assertEqual(ScreenClassifier().classify(additions.visible_elements, additions.screen_evidence), ScreenType.PNC_GIFT_CENTER)
        self.assertTrue(ObservationRequest.full_runtime_default().requires_ocr(ScreenType.PNC_GIFT_CENTER))

    def test_requires_the_header_and_at_least_one_card_title(self) -> None:
        for lines in (self.lines[1:], self.lines[:1], (replace(self.lines[0], text="Event Center"), *self.lines[1:])):
            with self.subTest(lines=lines):
                self.assertIsNone(_build_gift_center_additions(image=self.image, lines=lines))

    def test_preserves_a_wrapped_banner_title(self) -> None:
        additions = _build_gift_center_additions(image=self.image, lines=(
            self.lines[0],
            OcrLine("Permanent Build", Bounds(488, 805, 367, 43), 0.99),
            OcrLine("Queue", Bounds(720, 857, 135, 43), 0.99),
        ))
        self.assertEqual(len(additions.list_entries), 1)
        self.assertEqual(additions.list_entries[0].title_text, "Permanent Build Queue")
