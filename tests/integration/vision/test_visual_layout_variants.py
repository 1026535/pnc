"""Appearance variants must preserve the independently reviewed layout identity."""

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from tests.support.paths import TEST_DATA_ROOT


class VisualLayoutVariantTests(unittest.TestCase):
    """Keep compatible Home appearances distinct from competing layout proofs."""

    def test_home_chat_appearances_share_actionable_layout(self) -> None:
        recognizer = load_visual_screen_recognizer()
        for name in ("home_city_core.png", "chat_home_alliance.png", "chat_home_kingdom.png"):
            with self.subTest(image=name), Image.open(TEST_DATA_ROOT / "screen_recognition" / name) as image:
                result = recognizer.recognize(image)
                self.assertGreater(len(result.profile_ids), 1)
                decision = ScreenClassifier().decide(
                    {}, evidence=result.evidence, guard=GuardVerdict.CLEAR,
                    viewport_reviewed=True,
                )
                self.assertEqual(ScreenType.PNC_HOME_CITY, decision.effective_screen)
                self.assertEqual("home_city", decision.layout_id)
                self.assertTrue(decision.action_eligible)

    def test_different_layouts_of_same_screen_remain_unresolved(self) -> None:
        decision = ScreenClassifier().decide(
            {}, evidence=(
                ScreenEvidence(ScreenType.PNC_HOME_CITY, "first", layout_id="home_city"),
                ScreenEvidence(ScreenType.PNC_HOME_CITY, "other", layout_id="other_home_layout"),
            ), guard=GuardVerdict.CLEAR, viewport_reviewed=True,
        )
        self.assertEqual(ScreenType.UNKNOWN, decision.effective_screen)
        self.assertFalse(decision.action_eligible)
