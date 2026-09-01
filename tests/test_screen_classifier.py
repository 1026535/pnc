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

    def test_classify_vip_daily_reset_from_header_and_close_button(self) -> None:
        """Recognizes the VIP daily-reset modal from its dedicated header and Close button selectors."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_VIP_DAILY_RESET_HEADER: make_visible(UiElementId.PNC_VIP_DAILY_RESET_HEADER),
                UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON: make_visible(UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_VIP_DAILY_RESET)

    def test_classify_daily_to_do_from_header_selector(self) -> None:
        """Recognizes the Daily To-Do overlay from its canonical header anchor."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_DAILY_TO_DO_HEADER: make_visible(UiElementId.PNC_DAILY_TO_DO_HEADER),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_DAILY_TO_DO)

    def test_classify_elemental_fluctuation_intro_from_header(self) -> None:
        """Recognizes the informational Hero Showdown intro from its unique heading."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_HEADER: make_visible(
                    UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_HEADER
                ),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO)

    def test_classify_hero_formation_from_header_and_save_action(self) -> None:
        """Recognizes the weekly Hero Formation gate from its guarded controls."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_HERO_FORMATION_HEADER: make_visible(UiElementId.PNC_HERO_FORMATION_HEADER),
                UiElementId.PNC_HERO_FORMATION_SAVE_BUTTON: make_visible(
                    UiElementId.PNC_HERO_FORMATION_SAVE_BUTTON
                ),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_HERO_FORMATION)

    def test_classify_hero_showdown_ranking_from_rank_and_challenge(self) -> None:
        """Recognizes the normal Hero Showdown ranking destination."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_HERO_SHOWDOWN_RANKING_HEADER: make_visible(
                    UiElementId.PNC_HERO_SHOWDOWN_RANKING_HEADER
                ),
                UiElementId.PNC_HERO_SHOWDOWN_CURRENT_RANK_LABEL: make_visible(
                    UiElementId.PNC_HERO_SHOWDOWN_CURRENT_RANK_LABEL
                ),
                UiElementId.PNC_HERO_SHOWDOWN_CHALLENGE_BUTTON: make_visible(
                    UiElementId.PNC_HERO_SHOWDOWN_CHALLENGE_BUTTON
                ),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_HERO_SHOWDOWN_RANKING)

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

    def test_classify_world_coordinate_dialog_from_fields_and_go(self) -> None:
        """Recognizes the coordinate dialog from its committed fields and submit controls."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD: make_visible(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD),
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD: make_visible(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD),
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON: make_visible(UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON),
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON: make_visible(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)

    def test_classify_world_map_overview_from_header_close_and_map_region(self) -> None:
        """Recognizes the overview screen from its fixed chrome and overview map region."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_WORLD_OVERVIEW_HEADER: make_visible(UiElementId.PNC_WORLD_OVERVIEW_HEADER),
                UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON: make_visible(UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON),
                UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION: make_visible(UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION),
                UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON: make_visible(UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON),
            }
        )

        self.assertEqual(screen_type, ScreenType.PNC_WORLD_MAP_OVERVIEW)

    def test_classify_accepts_compatible_world_map_root_evidence_for_exact_world_map_selectors(self) -> None:
        """Keeps exact world-map selectors authoritative when parser evidence only proved the coarse world-map root."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {
                UiElementId.PNC_WORLD_HOME_NAV: make_visible(UiElementId.PNC_WORLD_HOME_NAV),
                UiElementId.PNC_WORLD_COORDINATE_BAR: make_visible(UiElementId.PNC_WORLD_COORDINATE_BAR),
            },
            evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP_ROOT, "ocr_world_map_root"),),
        )

        self.assertEqual(screen_type, ScreenType.PNC_WORLD_MAP)

    def test_classify_returns_exact_screen_when_exact_and_coarse_root_evidence_agree(self) -> None:
        """Collapses compatible coarse-plus-exact parser evidence to the exact screen instead of unknown."""

        classifier = ScreenClassifier()

        screen_type = classifier.classify(
            {},
            evidence=(
                ScreenEvidence(ScreenType.PNC_WORLD_MAP_ROOT, "ocr_world_map_root"),
                ScreenEvidence(ScreenType.PNC_WORLD_MAP, "ocr_world_coordinates_and_bottom_nav"),
            ),
        )

        self.assertEqual(screen_type, ScreenType.PNC_WORLD_MAP)


if __name__ == "__main__":
    unittest.main()
