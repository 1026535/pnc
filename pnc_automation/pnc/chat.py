"""Shared chat-domain models and helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.enums.chat import ChatChannel, ChatEntryKind
from pnc_automation.pnc.ui_element_id import UiElementId

if TYPE_CHECKING:
    from pnc_automation.pnc.observation import DetectedListEntry


@dataclass(frozen=True, slots=True)
class ObservedChatEntry:
    """Projects one shared list entry into the canonical chat-domain meaning consumed by tasks."""

    kind: ChatEntryKind
    sender_name: str | None
    message_text: str
    visible_order: int

    @property
    def is_player(self) -> bool:
        """Returns whether the visible chat row is trustworthy player-authored chat."""

        return self.kind == ChatEntryKind.PLAYER

    @property
    def is_announcement(self) -> bool:
        """Returns whether the visible chat row is a non-player system or announcement row."""

        return self.kind == ChatEntryKind.ANNOUNCEMENT

    @property
    def is_supported(self) -> bool:
        """Returns whether the visible row can safely participate in archive decisions."""

        return self.kind != ChatEntryKind.UNSUPPORTED


def chat_channel_selector_id(channel: ChatChannel) -> UiElementId:
    """Returns the selector that activates the requested chat channel."""

    if channel == ChatChannel.WORLD:
        return UiElementId.PNC_CHAT_TAB_KINGDOM
    if channel == ChatChannel.ALLIANCE:
        return UiElementId.PNC_CHAT_TAB_ALLIANCE
    raise ValueError(f"Unsupported chat channel '{channel}'.")


def chat_channel_archive_directory(channel: ChatChannel) -> str:
    """Returns the durable archive directory name used for the requested in-game chat channel."""

    if channel == ChatChannel.WORLD:
        return "kingdom"
    if channel == ChatChannel.ALLIANCE:
        return "alliance"
    raise ValueError(f"Unsupported chat channel '{channel}'.")


def chat_entry_from_list_entry(entry: "DetectedListEntry") -> ObservedChatEntry:
    """Projects one shared chat list entry into the canonical typed chat-domain model."""

    from pnc_automation.pnc.observation import ListEntryKind

    if entry.kind != ListEntryKind.CHAT_MESSAGE:
        raise SelectorResolutionError("Only chat-message list entries can be projected as chat rows.", entry_kind=entry.kind)
    if "chat_entry_kind" not in entry.metadata:
        legacy_message_text = entry.subtitle_text if isinstance(entry.subtitle_text, str) else entry.title_text or ""
        return ObservedChatEntry(
            kind=ChatEntryKind.PLAYER,
            sender_name=entry.title_text.strip() if isinstance(entry.title_text, str) and entry.title_text.strip() != "" else None,
            message_text=legacy_message_text,
            visible_order=0,
        )
    raw_kind = entry.require_metadata("chat_entry_kind")
    try:
        kind = ChatEntryKind(raw_kind)
    except ValueError as error:
        raise SelectorResolutionError(
            "Observed chat entry has an unsupported chat_entry_kind.",
            chat_entry_kind=raw_kind,
        ) from error
    message_text = entry.metadata.get("message_text")
    if not isinstance(message_text, str):
        raise SelectorResolutionError(
            "Observed chat entry is missing its message_text metadata.",
            chat_entry_kind=kind.value,
        )
    visible_order = entry.metadata.get("visible_order")
    if not isinstance(visible_order, int) or visible_order < 0:
        raise SelectorResolutionError(
            "Observed chat entry is missing a valid visible_order metadata field.",
            chat_entry_kind=kind.value,
            visible_order=visible_order,
        )
    sender_name = entry.title_text.strip() if isinstance(entry.title_text, str) and entry.title_text.strip() != "" else None
    return ObservedChatEntry(
        kind=kind,
        sender_name=sender_name,
        message_text=message_text,
        visible_order=visible_order,
    )


def is_player_chat_entry(entry: "DetectedListEntry") -> bool:
    """Returns whether one shared chat row is trustworthy player-authored chat."""

    return chat_entry_from_list_entry(entry).is_player


def visible_player_chat_entries(entries: tuple["DetectedListEntry", ...]) -> tuple[ObservedChatEntry, ...]:
    """Returns the typed player-chat rows from one visible chat-window entry set."""

    from pnc_automation.pnc.observation import ListEntryKind

    projected = tuple(chat_entry_from_list_entry(entry) for entry in entries if entry.kind == ListEntryKind.CHAT_MESSAGE)
    return tuple(entry for entry in projected if entry.is_player)


def visible_unsupported_chat_entries(entries: tuple["DetectedListEntry", ...]) -> tuple[ObservedChatEntry, ...]:
    """Returns visible chat rows whose OCR structure was not trustworthy enough to archive."""

    from pnc_automation.pnc.observation import ListEntryKind

    projected = tuple(chat_entry_from_list_entry(entry) for entry in entries if entry.kind == ListEntryKind.CHAT_MESSAGE)
    return tuple(entry for entry in projected if not entry.is_supported)


def normalize_chat_text(value: str) -> str:
    """Normalizes chat text for deterministic overlap and fingerprint comparisons."""

    return re.sub(r"\s+", " ", value.strip())
