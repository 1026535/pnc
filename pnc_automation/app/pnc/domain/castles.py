"""Castle identity and discovered roster values shared across P&C boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class CastleIdentity:
    """Identifies one castle across authored targets, rosters, and observations."""

    kingdom: str
    castle_name: str
    castle_level: int | None = None


def castle_identity_key(castle: CastleIdentity) -> tuple[str, str]:
    """Returns the stable kingdom/name identity key shared across roster and observation code."""

    return (castle.kingdom, castle.castle_name)


class CastleRosterOrdering(StrEnum):
    """Describes whether a cached castle roster preserves trustworthy in-game ordering."""

    UNKNOWN = "unknown"
    FULL_SCAN = "full_scan"


@dataclass(frozen=True, slots=True)
class PncAccountCastleRosterConfig:
    """Declares the discovered castle roster cache for one identified P&C username."""

    pnc_account_id: str
    castles: tuple[CastleIdentity, ...]
    ordering: CastleRosterOrdering = CastleRosterOrdering.UNKNOWN

    @property
    def has_trusted_ordering(self) -> bool:
        """Returns whether the cached roster can drive directional off-screen scrolling."""

        return self.ordering == CastleRosterOrdering.FULL_SCAN
