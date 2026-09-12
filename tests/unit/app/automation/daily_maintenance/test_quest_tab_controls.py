"""Keep fixed Quest tabs available independently of optional row OCR."""
from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.pnc_observation_enricher import _build_quest_additions
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult


class EmptyRows:
    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        return OcrResult(lines=(), words=())


class QuestTabControlsTests(unittest.TestCase):
    def test_proved_tabs_survive_missing_body_rows_at_both_resolutions(self) -> None:
        for width, height in ((540, 960), (900, 1600)):
            for selected, screen in ((0, ScreenType.PNC_QUEST_MAIN), (1, ScreenType.PNC_QUEST_DAILY)):
                with self.subTest(size=(width, height), screen=screen):
                    image = Image.new("RGB", (width, height), (15, 28, 68))
                    # Independently reviewed tab band: y=100..184 on the live 900 frame.
                    scale = width / 900
                    left = selected * width // 3
                    ImageDraw.Draw(image).rectangle(
                        (left, round(100 * scale), left + width // 3 - 1, round(184 * scale)),
                        fill=(160, 125, 45),
                    )
                    lines = tuple(
                        OcrLine(text, Bounds(10 + index * 30, 10 + index * 10, 20, 10), 1.0)
                        for index, text in enumerate(("Quest", "Main Quest", "Daily Quest", "Alliance Activity"))
                    )
                    context = ObservationOcrContext(image, EmptyRows(), None, "test")
                    result = _build_quest_additions(
                        image=image,
                        lines=lines,
                        proved_screen=screen,
                        ocr_context=context,
                        selector_registry=build_default_selector_registry(),
                    )
                    self.assertIsNotNone(result)
                    for index, selector in enumerate((
                        UiElementId.PNC_QUEST_TAB_MAIN,
                        UiElementId.PNC_QUEST_TAB_DAILY,
                        UiElementId.PNC_QUEST_TAB_ALLIANCE_ACTIVITY,
                    )):
                        point = result.visible_elements[selector].bounds.center()
                        self.assertTrue(Bounds(
                            index * width // 3, round(100 * scale), width // 3, round(84 * scale)
                        ).contains_point(point))
                    if selected == 0:
                        self.assertEqual(context.metrics.engine_calls, 0)
                    self.assertIsNone(_build_quest_additions(
                        image=image,
                        lines=lines[:2],
                        proved_screen=screen,
                        ocr_context=context,
                        selector_registry=build_default_selector_registry(),
                    ))
