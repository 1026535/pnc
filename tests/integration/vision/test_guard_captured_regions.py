"""Known modal controls require current captured panel and button geometry."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.ocr_region_plan import compile_guard_ocr_region_plans
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from tests.integration.vision.test_alliance_remaining_visual_contracts import (
    _BoundedOcrService, _builder, _capture, _perception,
)
from tests.support.paths import TEST_DATA_ROOT


CASES = (
    ("update_over_bag.png", ScreenType.PNC_POPUP, UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
     Bounds(178, 521, 184, 53), (
         OcrLine("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28), 1.),
         OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.),
     )),
    ("disconnect_negative.png", ScreenType.PNC_POPUP, UiElementId.PNC_RECONNECT_CONFIRM_BUTTON,
     Bounds(178, 514, 184, 54), (
         OcrLine("Disconnected. Reconnect now?[-10013]", Bounds(44, 384, 318, 20), 1.),
         OcrLine("Confirm", Bounds(228, 531, 84, 20), 1.),
     )),
    ("upgrade_warning_aug28.png", ScreenType.PNC_BUILDING_UPGRADE_WARNING,
     UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON, Bounds(495, 836, 307, 89), (
         OcrLine("Shield of Grace will expire at Lv.10 Castle.You won't be", Bounds(72, 619, 752, 29), 1.),
         OcrLine("protected from attacks!", Bounds(71, 655, 324, 34), 1.),
         OcrLine("Confirm", Bounds(580, 860, 140, 38), 1.),
     )),
)


class GuardCapturedRegionTests(unittest.TestCase):
    """Keep OCR message parsing separate from measured action qualification."""

    def test_current_button_geometry_and_bounded_guard_reads_through_both_paths(self) -> None:
        for fixture, screen, selector, manual_button, lines in CASES:
            with Image.open(TEST_DATA_ROOT / "screen_recognition" / fixture) as source:
                image = source.convert("RGB")
            for path in ("builder", "navigation"):
                with self.subTest(fixture=fixture, path=path):
                    ocr = _BoundedOcrService(lines)
                    builder = _builder(ocr)
                    capture = _capture(image, session_id=f"guard:{fixture}:{path}")
                    observation = builder.build(capture) if path == "builder" else _perception(builder).build(capture)
                    self.assertEqual(observation.screen_type, screen)
                    self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
                    control = observation.require(selector)
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.GEOMETRY)
                    self.assertEqual(control.frame_ref, capture.frame_ref)
                    self.assertIsNotNone(observation.decision.layout_id)
                    self.assertEqual(control.source_layout_id, observation.decision.layout_id)
                    self.assertTrue(manual_button.contains_point(control.action_point))
                    self.assertFalse(control.identity_evidence)
                    self.assertEqual(ocr.calls, [plan.bounds for plan in compile_guard_ocr_region_plans(image.size)])

    def test_missing_button_or_panel_never_reuses_ocr_padding_as_action_bounds(self) -> None:
        for fixture, _, selector, manual_button, lines in CASES:
            with Image.open(TEST_DATA_ROOT / "screen_recognition" / fixture) as source:
                image = source.convert("RGB")
            erased = image.copy()
            x, y, w, h = manual_button.x, manual_button.y, manual_button.width, manual_button.height
            erased.paste((25, 35, 53), (x - 3, y - 3, x + w + 3, y + h + 3))
            for variant in (erased, Image.new("RGB", image.size, (15, 28, 68))):
                for path in ("builder", "navigation"):
                    with self.subTest(fixture=fixture, path=path, panel=variant is erased):
                        builder = _builder(_BoundedOcrService(lines))
                        capture = _capture(variant, session_id=f"missing-guard:{fixture}:{path}")
                        observation = builder.build(capture) if path == "builder" else _perception(builder).build(capture)
                        self.assertEqual(observation.decision.guard, GuardVerdict.UNRESOLVED)
                        self.assertFalse(observation.decision.action_eligible)
                        self.assertNotIn(selector, observation.visible_elements)
                        self.assertFalse(observation.visible_elements)
