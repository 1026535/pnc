"""Alliance mail observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.build_observation import _build_observation
from tests.support.pnc.mail.ocr_line import _ocr_line


class AllianceMailObservationTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves alliance mail observation."""

    def test_observation_builder_keeps_mail_hub_out_of_compose_popup(self) -> None:
        """Does not promote the shared Mail hub into compose-popup state when only the generic Mail header is visible."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(),
            lines=(
                _ocr_line("Mail", x=310, y=42, width=110, height=24),
                _ocr_line("Player Mail", x=220, y=317, width=155, height=39),
                _ocr_line("No report yet", x=670, y=320, width=188, height=35),
                _ocr_line("Alliance Mail", x=221, y=481, width=176, height=32),
                _ocr_line("No report yet", x=670, y=480, width=189, height=38),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_HUB)
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD))
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON))
        player_mail = observation.require(UiElementId.PNC_MAIL_ROW_PLAYER_MAIL)
        self.assertIsNotNone(player_mail.action_point)
        self.assertGreaterEqual(player_mail.action_point[0], 800)

    def test_observation_builder_parses_live_like_alliance_home_instead_of_mail_hub(self) -> None:
        """Classifies alliance home from its tiles and bottom tabs instead of misreading Alliance Mail as the mail hub."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_MAIL_HUB),
            lines=(
                _ocr_line("Alliance", x=182, y=17, width=183, height=54),
                _ocr_line("Alliance Territory", x=49, y=842, width=253, height=40),
                _ocr_line("Alliance Tech", x=482, y=991, width=198, height=33),
                _ocr_line("Rank", x=479, y=1136, width=82, height=35),
                _ocr_line("AllianceMember", x=484, y=1284, width=251, height=30),
                _ocr_line("Alliance Shop", x=51, y=1533, width=168, height=32),
                _ocr_line("Alliance Mail'Alliance Help", x=270, y=1530, width=379, height=35),
                _ocr_line("Operations", x=682, y=1534, width=154, height=33),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_HOME)
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_TILE_TERRITORY))
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_TILE_RANK))
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_TILE_MEMBER))
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL))
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL))

    def test_observation_builder_does_not_treat_bottom_tab_alliance_mail_as_mail_hub(self) -> None:
        """Rejects the lower alliance-home tab label as mail-hub evidence when no mailbox rows are present."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_MAIL_HUB),
            lines=(
                _ocr_line("Alliance", x=182, y=17, width=183, height=54),
                _ocr_line("Alliance Mail", x=270, y=1532, width=175, height=32),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL))

    def test_observation_builder_tolerates_alliance_mail_ocr_typo_on_alliance_home(self) -> None:
        """Keeps the alliance mail tab actionable when OCR reads Mail as Mait on alliance home."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_HOME),
            lines=(
                _ocr_line("Alliance", x=182, y=17, width=183, height=54),
                _ocr_line("Alliance Territory", x=49, y=842, width=253, height=40),
                _ocr_line("Alliance Tech", x=482, y=991, width=198, height=33),
                _ocr_line("AllianceMember", x=482, y=1282, width=254, height=35),
                _ocr_line("Alliance Mait", x=270, y=1532, width=178, height=32),
                _ocr_line("Alliance Help", x=467, y=1532, width=182, height=33),
                _ocr_line("Alliance Shop", x=51, y=1533, width=168, height=32),
                _ocr_line("Operations", x=683, y=1534, width=153, height=33),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_HOME)
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL))

    def test_observation_builder_parses_alliance_home_status_banner(self) -> None:
        """Carries the transient alliance-home status banner so tasks can fail with the live gate reason."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_HOME),
            lines=(
                _ocr_line("Alliance", x=182, y=17, width=183, height=54),
                _ocr_line("Please clear Campaign Ch.3 first", x=194, y=454, width=512, height=39),
                _ocr_line("Alliance Territory", x=49, y=842, width=253, height=40),
                _ocr_line("Alliance Mait", x=270, y=1532, width=178, height=32),
                _ocr_line("Alliance Help", x=467, y=1532, width=182, height=33),
                _ocr_line("Alliance Shop", x=51, y=1533, width=168, height=32),
                _ocr_line("Operations", x=683, y=1534, width=153, height=33),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_HOME)
        self.assertTrue(observation.has(UiElementId.PNC_STATUS_BANNER))

    def test_observation_builder_surfaces_alliance_status_banner_even_when_screen_stays_unknown(self) -> None:
        """Preserves the Campaign Ch.3 banner for compose follow-up handling even when alliance-home chrome is incomplete."""

        observation = _build_observation(
            request=ObservationRequest.mail_compose_follow_up(),
            lines=(
                _ocr_line("Please clear Campaign Ch.3 first", x=194, y=454, width=512, height=39),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertTrue(observation.has(UiElementId.PNC_STATUS_BANNER))

    def test_observation_builder_keeps_chat_send_button_out_of_mail_compose_popup(self) -> None:
        """Does not treat the shared chat Send button as compose-popup evidence without a mail header."""

        observation = _build_observation(
            request=ObservationRequest.runtime_default(),
            lines=(
                _ocr_line("Chat", x=240, y=38, width=100, height=26),
                _ocr_line("Kingdom", x=210, y=118, width=120, height=34),
                _ocr_line("Alliance", x=650, y=118, width=120, height=34),
                _ocr_line("Enemy Bob", x=180, y=900, width=130, height=24),
                _ocr_line("Hello there", x=185, y=945, width=140, height=24),
                _ocr_line("Send", x=770, y=1530, width=88, height=36),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)

    def test_observation_builder_emits_typed_mailbox_categories_and_unavailable_state(self) -> None:
        """Carries only Player/Alliance category availability into typed hub content."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB),
            lines=(
                _ocr_line("Mail", x=310, y=42, width=110, height=24),
                _ocr_line("Player Mail", x=220, y=317, width=155, height=39),
                _ocr_line("No report yet", x=670, y=320, width=188, height=35),
                _ocr_line("Alliance Mail", x=221, y=481, width=176, height=32),
                _ocr_line("3 new", x=670, y=480, width=120, height=38),
            ),
        )

        categories = observation.entries(ListEntryKind.MAILBOX_CATEGORY)
        self.assertEqual(len(categories), 2)
        self.assertEqual(
            [(entry.metadata["mailbox_type"], entry.metadata["available"]) for entry in categories],
            [(MailboxType.PLAYER.value, False), (MailboxType.ALLIANCE.value, True)],
        )
        self.assertTrue(all(set(entry.metadata) == {"mailbox_type", "available"} for entry in categories))
