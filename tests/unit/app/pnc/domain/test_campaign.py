"""Deterministic Campaign stage-detail domain validation tests."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.campaign import CampaignMode, CampaignStageDetail
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError


class CampaignStageDetailTests(unittest.TestCase):
    """Unproven or contradictory stage facts are rejected, never defaulted."""

    def test_all_fields_may_stay_unobserved(self) -> None:
        detail = CampaignStageDetail()

        self.assertIsNone(detail.chapter_number)
        self.assertIsNone(detail.stage_number)
        self.assertIsNone(detail.name)
        self.assertIsNone(detail.mode)
        self.assertIsNone(detail.action_points)
        self.assertIsNone(detail.max_action_points)
        self.assertIsNone(detail.challenge_cost)

    def test_ordinals_max_gauge_and_cost_must_be_positive_integers(self) -> None:
        for field_name in ("chapter_number", "stage_number", "max_action_points", "challenge_cost"):
            with self.subTest(field=field_name, value=True):
                with self.assertRaises(TypeError):
                    CampaignStageDetail(**{field_name: True})
            with self.subTest(field=field_name, value="3"):
                with self.assertRaises(TypeError):
                    CampaignStageDetail(**{field_name: "3"})
            with self.subTest(field=field_name, value=0):
                with self.assertRaises(ValueError):
                    CampaignStageDetail(**{field_name: 0})

    def test_action_points_may_be_zero_but_never_negative_or_bool(self) -> None:
        self.assertEqual(0, CampaignStageDetail(action_points=0).action_points)
        with self.assertRaises(ValueError):
            CampaignStageDetail(action_points=-1)
        with self.assertRaises(TypeError):
            CampaignStageDetail(action_points=True)
        with self.assertRaises(TypeError):
            CampaignStageDetail(action_points="150")

    def test_name_and_mode_must_be_typed(self) -> None:
        with self.assertRaises(TypeError):
            CampaignStageDetail(name=123)
        with self.assertRaises(TypeError):
            CampaignStageDetail(mode="standard")
        self.assertEqual(
            CampaignMode.STANDARD,
            CampaignStageDetail(mode=CampaignMode.STANDARD).mode,
        )

    def test_source_screen_must_be_the_stage_detail_surface(self) -> None:
        self.assertEqual(
            ScreenType.PNC_CAMPAIGN_STAGE,
            CampaignStageDetail(source_screen=ScreenType.PNC_CAMPAIGN_STAGE).source_screen,
        )
        with self.assertRaises(SelectorResolutionError):
            CampaignStageDetail(source_screen=ScreenType.PNC_CAMPAIGN_CHAPTER)


if __name__ == "__main__":
    unittest.main()
