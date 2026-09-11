"""Regression coverage for the independently reviewed wrapped warning text."""

from dataclasses import dataclass
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult


@dataclass
class WarningOcr:
    result: OcrResult

    def read_result(self, image, region=None):
        return self.result


class UpgradeWarningGuardTests(unittest.TestCase):
    def test_wrapped_warning_has_exact_owner_and_confirm_inside_manual_box(self):
        for scale in (1.0, 0.6):
            with self.subTest(scale=scale):
                def line(text, x, y, width, height):
                    return OcrLine(text, Bounds(*(round(value * scale) for value in (x, y, width, height))), 0.9)

                lines = (
                    line("Shield of Grace will expire at Lv.1o Castle.You won't be", 72, 619, 752, 29),
                    line("protectedfromattacks!", 71, 655, 324, 34),
                    line("Cancel", 189, 857, 128, 43),
                    line("Confirm", 580, 860, 140, 38),
                )
                image = Image.new("RGB", (round(900 * scale), round(1600 * scale)))
                context = ObservationOcrContext(
                    image=image,
                    backend=WarningOcr(OcrResult(lines, ())),
                    frame_ref=None,
                    backend_revision="test-warning",
                )
                result = PncObservationEnricher().recognize_guards(
                    image,
                    ObservationRequest.building_upgrade_warning_follow_up(),
                    ocr_context=context,
                )
                self.assertEqual(result.guard_verdict, GuardVerdict.BLOCKED)
                self.assertEqual(result.screen_evidence[0].screen_type, ScreenType.PNC_BUILDING_UPGRADE_WARNING)
                confirm = result.visible_elements[UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON]
                x, y = confirm.action_point
                self.assertTrue(495 * scale <= x < 802 * scale)
                self.assertTrue(836 * scale <= y < 925 * scale)
                self.assertNotIn(UiElementId.PNC_POPUP_CLOSE_BUTTON, result.visible_elements)


if __name__ == "__main__":
    unittest.main()
