"""Chat classification: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import Bounds, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import _build_chat_overlay_additions

from tests.support.pnc.capture_vision.make_chat_ocr_fallback_fixture import (
    _make_chat_ocr_fallback_fixture,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.mail.build_observation import _build_observation


def _build_accepted_chat_fallback_observation(
    *,
    request: ObservationRequest,
    active_channel: ChatChannel | None,
    draft_ocr_text: str | None,
) -> object:
    """Run the chat row/draft parser with caller-owned accepted Chat identity."""

    screenshot, _registry, ocr_service = _make_chat_ocr_fallback_fixture(
        active_channel=active_channel,
        draft_ocr_text=draft_ocr_text,
    )
    return _build_observation(
        request=request,
        accepted_screen=ScreenType.PNC_CHAT,
        image=screenshot.image,
        image_size=screenshot.image.size,
        lines=ocr_service.lines,
    )


class ChatClassificationTests(unittest.TestCase):
    """Proves chat classification."""

    def test_observation_builder_classifies_chat_from_live_like_ocr(self) -> None:
        """Parses Chat controls after an explicit screen decision, preserving OCR geometry."""

        observation = _build_observation(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            accepted_screen=ScreenType.PNC_CHAT,
            semantic_parser=_build_chat_overlay_additions,
            lines=(
                _ocr_line("Chat", x=181, y=20, width=113, height=49),
                _ocr_line("Kingdom", x=202, y=117, width=143, height=40),
                _ocr_line("Alliance", x=652, y=116, width=123, height=39),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertTrue(observation.has(UiElementId.PNC_CHAT_HEADER))
        self.assertTrue(observation.has(UiElementId.PNC_CHAT_TAB_KINGDOM))
        self.assertTrue(observation.has(UiElementId.PNC_CHAT_TAB_ALLIANCE))
        self.assertTrue(observation.has(UiElementId.PNC_CHAT_SEND_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_CHAT_INPUT_FIELD))
        self.assertEqual(
            observation.require(UiElementId.PNC_CHAT_HEADER).source_kind,
            VisibleElementSourceKind.OCR,
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_CHAT_TAB_KINGDOM).source_kind,
            VisibleElementSourceKind.OCR,
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_CHAT_TAB_ALLIANCE).source_kind,
            VisibleElementSourceKind.OCR,
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_CHAT_TAB_KINGDOM).bounds,
            Bounds(x=202, y=117, width=143, height=40),
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_CHAT_TAB_ALLIANCE).bounds,
            Bounds(x=652, y=116, width=123, height=39),
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_CHAT_SEND_BUTTON).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_CHAT_INPUT_FIELD).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )

    def test_observation_builder_classifies_compact_chat_and_uses_ocr_tab_bounds(self) -> None:
        """Parses compact Chat tabs from explicit accepted identity and keeps measured OCR bounds."""

        image_size = (540, 960)
        observation = _build_observation(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            accepted_screen=ScreenType.PNC_CHAT,
            semantic_parser=_build_chat_overlay_additions,
            image_size=image_size,
            lines=(
                _ocr_line("Chat", x=111, y=16, width=75, height=28),
                _ocr_line("Kingdom", x=64, y=64, width=82, height=26),
                _ocr_line("Alliance", x=219, y=64, width=91, height=27),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        kingdom = observation.require(UiElementId.PNC_CHAT_TAB_KINGDOM)
        alliance = observation.require(UiElementId.PNC_CHAT_TAB_ALLIANCE)
        self.assertEqual(kingdom.source_kind, VisibleElementSourceKind.OCR)
        self.assertEqual(alliance.source_kind, VisibleElementSourceKind.OCR)
        self.assertEqual(kingdom.bounds, Bounds(x=64, y=64, width=82, height=26))
        self.assertEqual(alliance.bounds, Bounds(x=219, y=64, width=91, height=27))

    def test_observation_builder_extracts_chat_state_after_ocr_chat_fallback(self) -> None:
        """Carries active-channel and draft state through the parser after Chat identity is accepted."""

        observation = _build_accepted_chat_fallback_observation(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            active_channel=ChatChannel.ALLIANCE,
            draft_ocr_text="Pleaseter content",
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertTrue(observation.chat_draft_empty)
        self.assertIsNone(observation.chat_draft_text)

    def test_observation_builder_leaves_active_chat_channel_unknown_when_tab_colors_are_ambiguous(self) -> None:
        """Keeps the parser fail-safe when accepted Chat has ambiguous tab colors."""

        observation = _build_accepted_chat_fallback_observation(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            active_channel=None,
            draft_ocr_text="Pleaseter content",
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertIsNone(observation.active_chat_channel)
        self.assertTrue(observation.chat_draft_empty)
        self.assertIsNone(observation.chat_draft_text)

    def test_observation_builder_escalates_chat_send_follow_up_to_ocr_after_a_geometry_miss(self) -> None:
        """Parses post-send Chat state after accepted identity when geometry controls are absent."""

        observation = _build_accepted_chat_fallback_observation(
            request=ObservationRequest.chat_send_follow_up(),
            active_channel=ChatChannel.ALLIANCE,
            draft_ocr_text="",
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertIsNone(observation.chat_draft_empty)
