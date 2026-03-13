"""Shared chat-domain models and helpers."""

from __future__ import annotations

from enum import StrEnum

from pnc_automation.pnc.ui_element_id import UiElementId


class ChatChannel(StrEnum):
    """Supported reusable chat destinations."""

    WORLD = "world"
    ALLIANCE = "alliance"


def chat_channel_selector_id(channel: ChatChannel) -> UiElementId:
    """Returns the selector that activates the requested chat channel."""

    if channel == ChatChannel.WORLD:
        return UiElementId.PNC_CHAT_TAB_KINGDOM
    if channel == ChatChannel.ALLIANCE:
        return UiElementId.PNC_CHAT_TAB_ALLIANCE
    raise ValueError(f"Unsupported chat channel '{channel}'.")
