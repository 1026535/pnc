"""Centralized chat enum definitions."""

from enum import StrEnum


class ChatChannel(StrEnum):
    """Supported reusable chat destinations."""

    WORLD = "world"
    ALLIANCE = "alliance"


class ChatEntryKind(StrEnum):
    """Typed meanings assigned to OCR-backed visible chat rows."""

    PLAYER = "player"
    ANNOUNCEMENT = "announcement"
    UNSUPPORTED = "unsupported"
