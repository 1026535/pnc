"""Centralized mail enum definitions."""

from enum import StrEnum


class MailboxType(StrEnum):
    """Supported mailbox scopes in the current mail automation slice."""

    PLAYER = "player"
    ALLIANCE = "alliance"


class MailRecipientKind(StrEnum):
    """Supported mail recipient kinds in the current mail automation slice."""

    PLAYER = "player"
    ALLIANCE = "alliance"


class MailArchiveMode(StrEnum):
    """Controls which archive artifacts are persisted for collected mail."""

    SCREENSHOT = "screenshot"
    TEXT = "text"
    BOTH = "both"


class PlayerProfileRouteKind(StrEnum):
    """Supported routes that can reach one remote player profile."""

    PLAYER_TERRITORY = "player_territory"
    CHAT_MESSAGE = "chat_message"
    ALLIANCE_MEMBER = "alliance_member"
    MIGHT_RANK = "might_rank"
