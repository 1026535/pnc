"""Screen-classifier tests for selector and parser evidence integration."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier, ScreenEvidence
from tests.test_support import make_visible


class ScreenClassifierTests(unittest.TestCase):
    """Validates final screen decisions from selector and parser evidence."""

    def test_classify_uses_single_parser_evidence_when_selectors_are_absent(self) -> None:
        """Accepts one strong parser conclusion when no selector rule matches."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {},
            evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, "bottom_nav_and_home_actions"),),
        )

        self.assertEqual(screen_type, ScreenType.PNC_HOME_CITY)

    def test_classify_rejects_conflicting_parser_evidence(self) -> None:
        """Keeps the result unknown when selector anchors and parser evidence disagree."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_WORLD_HOME_NAV: make_visible(UiElementId.PNC_WORLD_HOME_NAV),
                UiElementId.PNC_WORLD_SEARCH_BUTTON: make_visible(UiElementId.PNC_WORLD_SEARCH_BUTTON),
            },
            evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, "bottom_nav_and_home_actions"),),
        )

        self.assertEqual(screen_type, ScreenType.UNKNOWN)

    def test_classify_prioritizes_popup_selector_over_underlying_screen_selectors(self) -> None:
        """Treats popup dismissal controls as blocking overlays even when root-screen selectors remain visible."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_HOME_WORLD_SWITCH: make_visible(UiElementId.PNC_HOME_WORLD_SWITCH),
                UiElementId.PNC_HOME_CHARACTER_PANEL: make_visible(UiElementId.PNC_HOME_CHARACTER_PANEL),
                UiElementId.PNC_HOME_BUILD_BUTTON: make_visible(UiElementId.PNC_HOME_BUILD_BUTTON),
                UiElementId.PNC_POPUP_CLOSE_BUTTON: make_visible(UiElementId.PNC_POPUP_CLOSE_BUTTON),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_POPUP)

    def test_classify_daily_to_do_from_header_selector(self) -> None:
        """Recognizes the Daily To-Do overlay from its canonical header anchor."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_DAILY_TO_DO_HEADER: make_visible(UiElementId.PNC_DAILY_TO_DO_HEADER),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_DAILY_TO_DO)

    def test_classify_chat_from_header_tabs_and_send(self) -> None:
        """Recognizes chat from its header, one channel tab, and the footer send action."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_CHAT_HEADER: make_visible(UiElementId.PNC_CHAT_HEADER),
                UiElementId.PNC_CHAT_TAB_KINGDOM: make_visible(UiElementId.PNC_CHAT_TAB_KINGDOM),
                UiElementId.PNC_CHAT_SEND_BUTTON: make_visible(UiElementId.PNC_CHAT_SEND_BUTTON),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_CHAT)

    def test_classify_world_map_from_world_home_nav_and_coordinate_bar(self) -> None:
        """Recognizes world map from the return-home nav plus the coordinate bar when search is absent."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_WORLD_HOME_NAV: make_visible(UiElementId.PNC_WORLD_HOME_NAV),
                UiElementId.PNC_WORLD_COORDINATE_BAR: make_visible(UiElementId.PNC_WORLD_COORDINATE_BAR),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_WORLD_MAP)


if __name__ == "__main__":
    unittest.main()
