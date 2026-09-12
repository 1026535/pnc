"""Focused checks for typed screen-family OCR content strategies."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.pnc_ocr_capabilities import (
    FAMILY_REGIONS_NOT_REVIEWED,
    ScreenFamilyOcrStrategy,
    can_attempt_screen_family_ocr,
    runtime_screen_family_ocr_capabilities,
    runtime_screen_family_ocr_types,
    screen_family_ocr_capability,
)


class PncOcrCapabilitiesTests(unittest.TestCase):
    """Keep content strategy declarations derived from the canonical family registry."""

    def test_every_registered_family_has_exactly_one_typed_content_strategy(self) -> None:
        families = runtime_screen_family_ocr_types()
        capabilities = runtime_screen_family_ocr_capabilities()

        self.assertEqual(families, {capability.family for capability in capabilities})
        self.assertEqual(len(families), len(capabilities))
        for capability in capabilities:
            if capability.strategy == ScreenFamilyOcrStrategy.REVIEWED_REGION_PLAN:
                self.assertIsNone(capability.fallback_reason)
            else:
                self.assertEqual(FAMILY_REGIONS_NOT_REVIEWED, capability.fallback_reason)

    def test_only_reviewed_fixed_field_or_coordinate_families_are_region_planned(self) -> None:
        reviewed = {
            capability.family
            for capability in runtime_screen_family_ocr_capabilities()
            if capability.strategy == ScreenFamilyOcrStrategy.REVIEWED_REGION_PLAN
        }

        self.assertEqual(
            {
                ScreenType.PNC_BAG,
                ScreenType.PNC_CHAT,
                ScreenType.PNC_MAIL_COMPOSE_POPUP,
                ScreenType.PNC_QUEST_MAIN,
                ScreenType.PNC_QUEST_DAILY,
                ScreenType.PNC_WORLD_COORDINATE_DIALOG,
                ScreenType.PNC_WORLD_MAP,
            },
            reviewed,
        )
        for unsupported in (ScreenType.PNC_HOME_CITY,):
            self.assertEqual(
                ScreenFamilyOcrStrategy.GUARDED_FULL_FRAME_REUSE,
                screen_family_ocr_capability(unsupported).strategy,
            )

    def test_existing_source_screen_eligibility_is_unchanged(self) -> None:
        for family in runtime_screen_family_ocr_types():
            self.assertTrue(can_attempt_screen_family_ocr(request_screen=family, observed_screen=family))
        self.assertFalse(
            can_attempt_screen_family_ocr(
                request_screen=ScreenType.PNC_CHAT,
                observed_screen=ScreenType.PNC_BAG,
            )
        )
        self.assertFalse(
            can_attempt_screen_family_ocr(
                request_screen=ScreenType.PNC_HOME_CITY,
                observed_screen=ScreenType.PNC_CHAT,
            )
        )

    def test_unregistered_family_has_no_implicit_content_strategy(self) -> None:
        with self.assertRaises(KeyError):
            screen_family_ocr_capability(ScreenType.PNC_LOADING)


if __name__ == "__main__":
    unittest.main()
