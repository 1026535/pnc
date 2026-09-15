"""The saved Institute prerequisite panel owns one measured, non-premium Go."""

from __future__ import annotations

import unittest
from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from tests.integration.vision.test_alliance_remaining_visual_contracts import (
    _BoundedOcrService, _builder, _capture, _perception,
)
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.modal_overlay import with_update_modal, update_modal_lines


class InstitutePrerequisiteCapturedTests(unittest.TestCase):
    def test_measured_prerequisite_go_and_level_are_separate_from_paid_builder_offer(self):
        with Image.open(TEST_DATA_ROOT / "screen_recognition/building_variants/institute_upgrade_blocked.png") as source:
            original = source.convert("RGB").resize((900, 1600), Image.Resampling.LANCZOS)
        lines = (
            OcrLine("Institute", Bounds(183, 21, 225, 44), 1.),
            OcrLine("22/45", Bounds(190, 408, 100, 32), 1.),
            OcrLine("Requirement", Bounds(59, 710, 191, 33), 1.),
            OcrLine("Castle: Lv.23", Bounds(151, 768, 174, 32), 1.),
            OcrLine("Go", Bounds(727, 762, 65, 39), 1.),
            OcrLine("Go", Bounds(727, 898, 65, 39), 1.),
        )
        erased = original.copy()
        erased.paste((27, 38, 65), (665, 748, 845, 813))
        for name, image in (("visible", original), ("erased_go", erased),
                            ("update", with_update_modal(original))):
            for path in ("builder", "navigation"):
                with self.subTest(variant=name, path=path):
                    backend = _BoundedOcrService(update_modal_lines(image.size) if name == "update" else lines)
                    builder = _builder(backend)
                    capture = _capture(image, session_id=f"institute:{name}:{path}")
                    observation = (builder.build(capture, request=ObservationRequest.source_screen_retry(ScreenType.PNC_INSTITUTE))
                                   if path == "builder" else _perception(builder).build(capture, include_content=True))
                    if name == "update":
                        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                        self.assertFalse(observation.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))
                    else:
                        self.assertEqual(observation.screen_type, ScreenType.PNC_INSTITUTE)
                        self.assertEqual(observation.decision.layout_id, "institute_upgrade_detail")
                        self.assertEqual(observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL).extracted_text, "22/45")
                    if name == "visible":
                        control = observation.require(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON)
                        self.assertEqual(control.source_kind.name, "TEMPLATE")
                        self.assertTrue(Bounds(670, 753, 170, 55).contains_point(control.action_point))
                        self.assertEqual(control.frame_ref, capture.frame_ref)
                        self.assertEqual(observation.require(UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL).extracted_text, "Castle: Lv.23")
                    else:
                        self.assertFalse(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON))
                        self.assertFalse(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_HEADER))
                    for selector in (UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                                     UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON):
                        self.assertFalse(observation.has(selector))
                    self.assertNotIn(Bounds(0, 0, *image.size), backend.calls)


if __name__ == "__main__":
    unittest.main()
