"""Chat fragment observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.chat import ChatEntryKind, visible_unsupported_chat_entries
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.build_chat_fixture_image import _build_chat_fixture_image
from tests.support.pnc.mail.build_observation import _build_observation
from tests.support.pnc.mail.draw_chat_emoji import _draw_chat_emoji
from tests.support.pnc.mail.ocr_line import _ocr_line


class ChatFragmentObservationTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves chat fragment observation."""

    def test_observation_builder_marks_interior_message_only_fragments_as_unsupported(self) -> None:
        """Keeps interior message-only OCR fragments fail-fast when no trustworthy sender can be attached."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("just some floating message text", x=200, y=360, width=300, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.UNSUPPORTED.value)
        self.assertEqual(chat_entries[0].metadata["unsupported_reason"], "message_only")

    def test_observation_builder_archives_emoji_only_rows_with_controlled_placeholders(self) -> None:
        """Maps confidently image-only emoji rows onto the canonical placeholder vocabulary."""

        image = _build_chat_fixture_image()
        _draw_chat_emoji(image, top=330, kind="happy")
        _draw_chat_emoji(image, top=520, kind="eyes")
        _draw_chat_emoji(image, top=710, kind="generic")
        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            image=image,
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Happy Bot", x=120, y=290, width=180, height=24),
                _ocr_line("Eyes Bot", x=120, y=480, width=180, height=24),
                _ocr_line("Mystery Bot", x=120, y=670, width=180, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(
            [entry.metadata["message_text"] for entry in chat_entries],
            ["[happy emoji]", "[eyes emoji]", "[emoji]"],
        )
        self.assertTrue(all(entry.metadata["chat_entry_kind"] == ChatEntryKind.PLAYER.value for entry in chat_entries))

    def test_observation_builder_normalizes_live_march_24_kingdom_chat_failure_shape(self) -> None:
        """Covers the March 24, 2026 live OCR shape so split rows, timestamps, and sticker rows normalize safely."""

        image = Image.open(
            require_local_fixture_artifact(
                "kingdom_chat_failure_shape",
                default_repo_relative_path=(
                    "artifacts/2026-03-24/serious_stuff/"
                    "20260324T143723Z_collect_kingdom_chat_failure_result.png"
                ),
            )
        )
        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            image=image,
            image_size=image.size,
            lines=(
                _ocr_line("Chat", x=107, y=10, width=70, height=33),
                _ocr_line("Kingdom", x=123, y=70, width=85, height=24),
                _ocr_line("Alliance", x=391, y=68, width=75, height=26),
                _ocr_line("[Deceiver] [DMG]   Sonny Corinthos", x=109, y=165, width=253, height=16),
                _ocr_line("plscometome", x=112, y=198, width=115, height=17),
                _ocr_line("[MIR]yJeTalO", x=109, y=270, width=107, height=18),
                _ocr_line("ABOTAyMarOyTOTyTKTOeCTbAaXeHe3HarOTKaKW3", x=110, y=304, width=382, height=17),
                _ocr_line("3ayeroBceHayaocb)", x=111, y=327, width=169, height=15),
                _ocr_line("2026-03-2410:00", x=196, y=382, width=149, height=17),
                _ocr_line("SystemMessage", x=103, y=431, width=123, height=21),
                _ocr_line("The Apex Match World Championship has ended!", x=112, y=465, width=362, height=19),
                _ocr_line("Congrats to Xo-xo-xo.from Kingdom 297 on winning", x=111, y=487, width=391, height=20),
                _ocr_line("theworldchampion title!", x=112, y=511, width=185, height=15),
                _ocr_line("2026-03-2410:37", x=196, y=567, width=148, height=17),
                _ocr_line("[DMG]  Toast.", x=108, y=618, width=100, height=18),
                _ocr_line("it'samystery", x=109, y=650, width=102, height=21),
                _ocr_line("[DMG]p2o2i2u2ueu3u47484", x=108, y=724, width=220, height=17),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 5)
        self.assertEqual(
            [entry.metadata["chat_entry_kind"] for entry in chat_entries],
            [
                ChatEntryKind.PLAYER.value,
                ChatEntryKind.PLAYER.value,
                ChatEntryKind.ANNOUNCEMENT.value,
                ChatEntryKind.PLAYER.value,
                ChatEntryKind.PLAYER.value,
            ],
        )
        self.assertEqual(chat_entries[2].title_text, "SystemMessage")
        self.assertEqual(chat_entries[4].metadata["message_text"], "[sticker]")
        self.assertEqual(len(visible_unsupported_chat_entries(chat_entries)), 0)
