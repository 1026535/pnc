"""Chat row observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.chat import (
    ChatEntryKind,
    visible_player_chat_entries,
    visible_unsupported_chat_entries,
)
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.build_observation import _build_observation
from tests.support.pnc.mail.ocr_line import _ocr_line


class ChatRowObservationTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves chat row observation."""

    def test_observation_builder_parses_visible_chat_message_entries(self) -> None:
        """Builds visible chat sender entries so the chat-message profile route can stay inside shared flow planning."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob", x=120, y=260, width=180, height=24),
                _ocr_line("Hello there", x=160, y=292, width=200, height=24),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)
        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].title_text, "Enemy Bob")
        self.assertEqual(chat_entries[0].subtitle_text, "Hello there")
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.PLAYER.value)
        self.assertEqual(chat_entries[0].metadata["message_text"], "Hello there")

    def test_observation_builder_marks_announcement_rows_without_promoting_them_to_player_chat(self) -> None:
        """Keeps announcement rows visible for diagnostics while excluding them from player-chat projections."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob", x=120, y=260, width=180, height=24),
                _ocr_line("Hello there", x=160, y=292, width=200, height=24),
                _ocr_line("System Message", x=120, y=380, width=220, height=24),
                _ocr_line("Castle battle begins soon", x=160, y=412, width=340, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)
        player_entries = visible_player_chat_entries(chat_entries)

        self.assertEqual(len(chat_entries), 2)
        self.assertEqual(chat_entries[1].metadata["chat_entry_kind"], ChatEntryKind.ANNOUNCEMENT.value)
        self.assertEqual([entry.sender_name for entry in player_entries], ["Enemy Bob"])

    def test_observation_builder_marks_sender_only_single_line_chat_rows_as_unsupported(self) -> None:
        """Leaves sender-only OCR rows unsupported so chat archiving can fail fast instead of dropping them silently."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob", x=120, y=360, width=180, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.UNSUPPORTED.value)
        self.assertEqual(len(visible_unsupported_chat_entries(chat_entries)), 1)

    def test_observation_builder_marks_malformed_single_line_chat_rows_as_unsupported(self) -> None:
        """Leaves merged OCR rows unsupported when they do not match the trusted `Sender: message` player format."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob - Hello there", x=120, y=360, width=320, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.UNSUPPORTED.value)
        self.assertEqual(len(visible_unsupported_chat_entries(chat_entries)), 1)

    def test_observation_builder_keeps_explicit_system_message_rows_as_announcements(self) -> None:
        """Keeps the brown System Message row family classified as announcements instead of player chat."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("System Message", x=120, y=360, width=220, height=24),
                _ocr_line("Battle begins soon", x=160, y=392, width=300, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.ANNOUNCEMENT.value)
        self.assertEqual(chat_entries[0].title_text, "System Message")
        self.assertEqual(chat_entries[0].subtitle_text, "Battle begins soon")

    def test_observation_builder_does_not_create_false_player_rows_from_announcement_only_chat(self) -> None:
        """Treats announcement-only Kingdom Chat windows as non-player content so transcript deltas stay quiet."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("System Message", x=120, y=360, width=220, height=24),
                _ocr_line("The Apex Match World Championship has ended!", x=160, y=392, width=420, height=24),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(len(visible_player_chat_entries(observation.entries(ListEntryKind.CHAT_MESSAGE))), 0)

    def test_observation_builder_merges_split_sender_and_message_fragments_into_one_player_row(self) -> None:
        """Merges one isolated sender label with the adjacent message block when the attachment is unique."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("[DMG]Toast.", x=120, y=360, width=180, height=24),
                _ocr_line("it's a mystery", x=170, y=424, width=220, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].title_text, "[DMG]Toast.")
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.PLAYER.value)
        self.assertEqual(chat_entries[0].metadata["message_text"], "it's a mystery")

    def test_observation_builder_keeps_titled_and_tagged_player_rows_archivable(self) -> None:
        """Accepts optional title and alliance-tag prefixes as normal player sender evidence."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("[Ruler][RST]Queen Bee", x=120, y=260, width=260, height=24),
                _ocr_line("Good luck all", x=160, y=292, width=220, height=24),
                _ocr_line("[DMG]Toast.", x=120, y=380, width=180, height=24),
                _ocr_line("Still normal player chat", x=160, y=412, width=280, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual([entry.title_text for entry in chat_entries], ["[Ruler][RST]Queen Bee", "[DMG]Toast."])
        self.assertTrue(all(entry.metadata["chat_entry_kind"] == ChatEntryKind.PLAYER.value for entry in chat_entries))

    def test_observation_builder_keeps_autogenerated_player_style_rows_and_admin_rows_archivable(self) -> None:
        """Keeps player-chrome broadcasts and blue-bubble Admin rows in the player archive bucket."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Admin", x=120, y=260, width=140, height=24),
                _ocr_line("I obtained legendary hero Phoenix (Tap to Join)", x=160, y=292, width=520, height=24),
                _ocr_line("Cutie Voj", x=120, y=380, width=160, height=24),
                _ocr_line("I crafted Mythic Hammer! (Tap to view)", x=160, y=412, width=430, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual([entry.title_text for entry in chat_entries], ["Admin", "Cutie Voj"])
        self.assertTrue(all(entry.metadata["chat_entry_kind"] == ChatEntryKind.PLAYER.value for entry in chat_entries))

    def test_observation_builder_drops_bottom_clipped_sender_only_boundary_fragments(self) -> None:
        """Skips bottom-edge sender fragments that are visibly clipped instead of failing an otherwise valid snapshot."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob", x=120, y=1120, width=180, height=24),
                _ocr_line("Hello there", x=160, y=1152, width=220, height=24),
                _ocr_line("[DMG]Toast.", x=120, y=1450, width=180, height=24),
            ),
            image_size=(900, 1600),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].title_text, "Enemy Bob")
        self.assertEqual(len(visible_unsupported_chat_entries(chat_entries)), 0)
