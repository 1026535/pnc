"""Typed popup classification."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.popup import PopupControlKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.pnc_observation_enricher import _build_popup_additions

from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class TypedPopupClassificationTests(unittest.TestCase):
    """Proves typed popup classification."""

    def test_popup_classifier_materializes_exact_app_update_confirm(self) -> None:
        """Exposes Confirm only when OCR proves the exact required-update modal."""

        additions = _build_popup_additions(
            image=Image.new("RGB", (540, 960)),
            lines=(
                _ocr_line("New version detected. Tap Confirm to update.", x=59, y=385, width=408, height=19),
                _ocr_line("Confirm", x=234, y=536, width=73, height=20),
            ),
            anchors=(),
        )

        self.assertIsNotNone(additions)
        confirm = additions.visible_elements[UiElementId.PNC_UPDATE_CONFIRM_BUTTON]
        self.assertEqual("Confirm", confirm.extracted_text)
        self.assertEqual((270, 546), confirm.action_point)
        self.assertEqual(ScreenType.PNC_POPUP, additions.screen_evidence[0].screen_type)

    def test_popup_classifier_materializes_exact_update_failure_confirm(self) -> None:
        """Publishes the existing update recovery control for the observed retry dialog."""

        additions = _build_popup_additions(
            image=Image.new("RGB", (900, 1600)),
            lines=(
                _ocr_line("CONQUEST", x=292, y=40, width=300, height=60),
                _ocr_line("Update failed. Try again?", x=98, y=640, width=374, height=38),
                _ocr_line("Confirm", x=388, y=890, width=124, height=39),
                _ocr_line("10%", x=420, y=1390, width=64, height=32),
                _ocr_line("Downloading update resources...0/2 0%", x=154, y=1449, width=593, height=36),
            ),
            anchors=(),
        )

        self.assertIsNotNone(additions)
        assert additions is not None
        confirm = additions.visible_elements[UiElementId.PNC_UPDATE_CONFIRM_BUTTON]
        self.assertEqual("Confirm", confirm.extracted_text)
        self.assertEqual((450, 909), confirm.action_point)
        self.assertIsNotNone(additions.popup_overlay)
        assert additions.popup_overlay is not None
        self.assertEqual(PopupControlKind.UPDATE_CONFIRM, additions.popup_overlay.candidates[0].control_kind)
        self.assertEqual("required_game_update", additions.popup_overlay.layout_id)

    def test_popup_classifier_rejects_nonexact_update_failure_message(self) -> None:
        """Does not authorize a generic Confirm for an unreviewed update message."""

        additions = _build_popup_additions(
            image=Image.new("RGB", (900, 1600)),
            lines=(
                _ocr_line("Update failed. Try later?", x=98, y=640, width=374, height=38),
                _ocr_line("Confirm", x=388, y=890, width=124, height=39),
            ),
            anchors=(),
        )

        self.assertIsNone(additions)

    def test_popup_classifier_accepts_generic_negative_only_with_compact_modal_support(self) -> None:
        """Requires message content above the paired negative/primary action row."""

        additions = _build_popup_additions(
            image=Image.new("RGB", (540, 960)),
            lines=(
                _ocr_line("Optional feature available", x=120, y=360, width=300, height=28),
                _ocr_line("Cancel", x=95, y=536, width=85, height=24),
                _ocr_line("Confirm", x=350, y=536, width=95, height=24),
            ),
            anchors=(),
        )

        self.assertIsNotNone(additions)
        self.assertEqual(additions.popup_overlay.layout_id, "generic_modal_negative")
        self.assertEqual(
            additions.popup_overlay.candidates[0].control_kind,
            PopupControlKind.CANCEL,
        )

    def test_popup_classifier_rejects_action_row_without_modal_support(self) -> None:
        """Does not turn an isolated background action row into a popup."""

        additions = _build_popup_additions(
            image=Image.new("RGB", (540, 960)),
            lines=(
                _ocr_line("Background heading", x=10, y=30, width=180, height=24),
                _ocr_line("Cancel", x=95, y=536, width=85, height=24),
                _ocr_line("Confirm", x=350, y=536, width=95, height=24),
            ),
            anchors=(),
        )

        self.assertIsNone(additions)

    def test_popup_classifier_prefers_typed_update_over_visual_x_on_same_frame(self) -> None:
        """Recognized affirmative recovery wins before the generic close-glyph fallback."""

        image = Image.new("RGB", (540, 960), (15, 28, 68))
        drawing = ImageDraw.Draw(image)
        drawing.line((485, 25, 515, 55), fill=(255, 247, 218), width=6)
        drawing.line((515, 25, 485, 55), fill=(255, 247, 218), width=6)
        additions = _build_popup_additions(
            image=image,
            lines=(
                _ocr_line("New version detected. Tap Confirm to update.", x=59, y=385, width=408, height=19),
                _ocr_line("Confirm", x=234, y=536, width=73, height=20),
            ),
            anchors=(),
        )

        self.assertIsNotNone(additions)
        self.assertIn(UiElementId.PNC_UPDATE_CONFIRM_BUTTON, additions.visible_elements)
        self.assertNotIn(UiElementId.PNC_POPUP_CLOSE_BUTTON, additions.visible_elements)
        self.assertEqual(additions.popup_overlay.candidates[0].control_kind.value, "update_confirm")
