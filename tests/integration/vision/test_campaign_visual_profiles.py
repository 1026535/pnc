"""Reviewed visual recognition contracts for Campaign navigation surfaces."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.automation.engine.navigation_core import reviewed_navigation_edges
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer

from tests.support.paths import TEST_DATA_ROOT


FIXTURES = TEST_DATA_ROOT / "screen_recognition"


def _image(name: str) -> Image.Image:
    with Image.open(FIXTURES / name) as source:
        return source.convert("RGB")


class CampaignVisualProfileTests(unittest.TestCase):
    """Require campaign identity and controls to remain evidence-backed and scoped."""

    def test_campaign_profiles_expose_their_measured_controls(self) -> None:
        recognizer = load_visual_screen_recognizer()
        expected = {
            "campaign_map.png": (
                ScreenType.PNC_CAMPAIGN_MAP,
                {UiElementId.PNC_CAMPAIGN_HOME_PORTAL},
            ),
            "campaign_chapter_10.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
            ),
            "campaign_stage_10_3.png": (
                ScreenType.PNC_CAMPAIGN_STAGE,
                {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
            ),
        }
        for name, (screen, selectors) in expected.items():
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name))
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
                self.assertEqual({item.selector_id for item in result.controls}, selectors)
                self.assertTrue(
                    all(item.source_kind is VisibleElementSourceKind.TEMPLATE for item in result.controls)
                )
                if screen is ScreenType.PNC_CAMPAIGN_STAGE:
                    self.assertEqual(
                        {item.selector_id for item in result.dismiss_controls},
                        {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
                    )
                else:
                    self.assertEqual(result.dismiss_controls, ())

    def test_campaign_profiles_are_mutually_exclusive_at_reference_and_scaled_sizes(self) -> None:
        recognizer = load_visual_screen_recognizer()
        expected = {
            "campaign_map.png": (ScreenType.PNC_CAMPAIGN_MAP, UiElementId.PNC_CAMPAIGN_HOME_PORTAL),
            "campaign_chapter_10.png": (ScreenType.PNC_CAMPAIGN_CHAPTER, UiElementId.PNC_CAMPAIGN_BACK_BUTTON),
            "campaign_stage_10_3.png": (ScreenType.PNC_CAMPAIGN_STAGE, UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON),
        }
        for name, (screen, selector) in expected.items():
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name).resize((900, 1600)))
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
                self.assertEqual({item.selector_id for item in result.controls}, {selector})

    def test_campaign_detail_close_is_owned_and_challenge_is_not_a_control(self) -> None:
        recognizer = load_visual_screen_recognizer()
        result = recognizer.recognize(_image("campaign_stage_10_3.png"))
        self.assertEqual(
            {item.selector_id for item in result.dismiss_controls},
            {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
        )
        self.assertNotIn(
            UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
            {item.selector_id for item in result.controls},
        )
        stage_profile = next(profile for profile in recognizer.profiles if profile.id == "campaign_stage_10_3")
        close_control = next(
            control
            for control in stage_profile.controls
            if control.selector_id is UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON
        )
        self.assertTrue(close_control.dismisses_surface)

    def test_campaign_portal_registry_and_reviewed_home_edge_are_canonical(self) -> None:
        selector = build_default_selector_registry().require(UiElementId.PNC_CAMPAIGN_HOME_PORTAL)
        self.assertEqual(selector.interaction_kind, SelectorInteractionKind.NAVIGATION)
        self.assertEqual(selector.click_outcomes[0].target_screen, ScreenType.PNC_HOME_CITY)
        self.assertTrue(selector.click_outcomes[0].safe_to_click)
        self.assertFalse(selector.click_outcomes[0].monetized)
        self.assertIn(
            (
                ScreenType.PNC_CAMPAIGN_MAP,
                UiElementId.PNC_CAMPAIGN_HOME_PORTAL,
                frozenset({ScreenType.PNC_HOME_CITY}),
            ),
            tuple((edge.source, edge.selector, edge.destinations) for edge in reviewed_navigation_edges()),
        )

    def test_campaign_anchor_gate_fails_closed_when_identity_is_partial(self) -> None:
        recognizer = load_visual_screen_recognizer()
        mutations = (
            ("campaign_map.png", (180, 220, 350, 350)),
            ("campaign_chapter_10.png", (205, 38, 530, 98)),
            ("campaign_stage_10_3.png", (120, 201, 420, 250)),
        )
        for name, box in mutations:
            with self.subTest(name=name):
                image = _image(name)
                image.paste((0, 0, 0), box)
                self.assertEqual(recognizer.recognize(image).evidence, ())


if __name__ == "__main__":
    unittest.main()
