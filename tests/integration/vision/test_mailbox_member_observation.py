"""Mailbox member observation: verifies the named internal boundary with offline fixtures."""

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


class MailboxMemberObservationTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mailbox member observation."""

    def test_observation_builder_groups_alliance_member_rows_without_promoting_stats_or_actions(self) -> None:
        """Extracts one member entry per alliance row instead of treating stats and action labels as names."""

        observation = _build_observation(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
            lines=(
                _ocr_line("Alliance Member", x=240, y=42, width=220, height=24),
                _ocr_line("Enemy Bob", x=130, y=320, width=180, height=26),
                _ocr_line("145,022,677", x=310, y=358, width=160, height=24),
                _ocr_line("Manage", x=720, y=338, width=110, height=24),
                _ocr_line("Cutie Voj", x=130, y=488, width=170, height=26),
                _ocr_line("64,132,585", x=312, y=526, width=150, height=24),
                _ocr_line("Manage", x=720, y=506, width=110, height=24),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_MEMBER_LIST)
        entries = observation.entries(ListEntryKind.ALLIANCE_MEMBER)
        self.assertEqual([entry.title_text for entry in entries], ["Enemy Bob", "Cutie Voj"])
        self.assertEqual(entries[0].action_point, (775, 350))
        self.assertEqual(entries[1].action_point, (775, 518))

    def test_observation_builder_parses_centered_alliance_member_manage_popup(self) -> None:
        """Recognizes the centered alliance-member manage popup instead of leaving it as unknown."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP),
            lines=(
                _ocr_line("Manage", x=360, y=408, width=170, height=48),
                _ocr_line("Cutie Voj", x=392, y=496, width=130, height=38),
                _ocr_line("Personal Info", x=352, y=606, width=196, height=33),
                _ocr_line("Send", x=408, y=722, width=85, height=40),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP)
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON))

    def test_observation_builder_parses_empty_mailbox(self) -> None:
        """Treats the No report yet state as a valid mailbox instead of classifying it as unknown."""

        observation = _build_observation(
            request=ObservationRequest.mailbox_observation(MailboxType.PLAYER),
            lines=(
                _ocr_line("Player Mail", x=310, y=42, width=170, height=24),
                _ocr_line("Manage", x=720, y=44, width=90, height=22),
                _ocr_line("Mark all as read", x=560, y=44, width=150, height=22),
                _ocr_line("No report yet", x=300, y=730, width=180, height=26),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(observation.mailbox_type, MailboxType.PLAYER)
        self.assertTrue(observation.mailbox_empty)

    def test_observation_builder_parses_date_first_alliance_mail_row_without_promoting_footer_controls(self) -> None:
        """Keeps the visible alliance-mail thread row and ignores the footer action bar on the live mailbox layout."""

        observation = _build_observation(
            request=ObservationRequest.mailbox_observation(MailboxType.ALLIANCE),
            lines=(
                _ocr_line("Alliance Mail", x=183, y=17, width=292, height=52),
                _ocr_line("2026/03/22 14:46:46", x=617, y=130, width=257, height=26),
                _ocr_line("[AAS] pine cobaye 1", x=193, y=151, width=271, height=35),
                _ocr_line("(All Allies)Test", x=194, y=184, width=175, height=32),
                _ocr_line("(All Allies)test", x=196, y=220, width=169, height=27),
                _ocr_line("Mark All as", x=352, y=1475, width=193, height=39),
                _ocr_line("Read", x=402, y=1511, width=96, height=41),
                _ocr_line("Mail", x=136, y=1522, width=62, height=33),
                _ocr_line("Manage", x=678, y=1523, width=108, height=35),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(observation.mailbox_type, MailboxType.ALLIANCE)
        entries = observation.entries(ListEntryKind.MAIL_THREAD)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title_text, "[AAS] pine cobaye 1")
        self.assertEqual(entries[0].subtitle_text, "(All Allies)Test (All Allies)test")
        self.assertEqual(entries[0].metadata["date_text"], "2026/03/22 14:46:46")

    def test_mailbox_observation_uses_requested_mailbox_type(self) -> None:
        """Rejects mismatched mailbox OCR so narrow mailbox follow-ups actually verify the requested mailbox."""

        observation = _build_observation(
            request=ObservationRequest.mailbox_observation(MailboxType.PLAYER),
            lines=(
                _ocr_line("Alliance Mail", x=183, y=17, width=292, height=52),
                _ocr_line("[AAS] pine cobaye 1", x=193, y=151, width=271, height=35),
                _ocr_line("(All Allies)Test", x=194, y=184, width=175, height=32),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
