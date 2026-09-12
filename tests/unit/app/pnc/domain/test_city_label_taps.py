"""Keep city label recognition separate from a reviewed building hit point."""

import unittest

from PIL import Image

from pnc_automation.app.pnc.vision.spatial_surfaces import _classify_home_city_object
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


class CityLabelTapTests(unittest.TestCase):
    def test_goddess_tap_hits_the_body_instead_of_the_noninteractive_nameplate(self) -> None:
        for scale in (1.0, 0.6):
            image = Image.new("RGB", (round(900 * scale), round(1600 * scale)))
            line = OcrLine("Goddess Statue", Bounds(*[
                round(value * scale) for value in (388, 841, 145, 20)
            ]), 0.99)
            target = _classify_home_city_object(image=image, line=line, normalized_text="GODDESSSTATUE")
            x, y = target.action_point
            # Independent body interior reviewed in the panned September 10 frame.
            self.assertTrue(390 <= x / scale <= 570)
            self.assertTrue(600 <= y / scale <= 760)
            self.assertEqual(target.bounds, line.bounds)

    def test_offset_body_under_hud_does_not_become_an_actionable_object(self) -> None:
        target = _classify_home_city_object(
            image=Image.new("RGB", (900, 1600)),
            line=OcrLine("Goddess Statue", Bounds(388, 200, 145, 20), 0.99),
            normalized_text="GODDESSSTATUE",
        )
        self.assertIsNone(target)
