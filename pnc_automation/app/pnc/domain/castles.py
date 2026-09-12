"""Castle identity and discovered roster values shared across P&C boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from pnc_automation.core.text.normalization import normalize_ocr_text


def normalize_castle_display_name(name_text: str) -> str:
    """Remove one leading alliance tag from a displayed castle name."""

    stripped = name_text.strip()
    normalized = re.sub(r"^\[[^\]]+\]\s*", "", stripped, count=1).strip()
    return stripped if normalized == "" else normalized


@dataclass(frozen=True, slots=True)
class CastleIdentity:
    """Identifies one castle across authored targets, rosters, and observations."""

    kingdom: str
    castle_name: str
    castle_level: int | None = None


def castle_names_match(left: str, right: str) -> bool:
    """Match displayed castle names through stable OCR whitespace normalization."""

    if left == right:
        return True
    return normalize_ocr_text(left) == normalize_ocr_text(right)


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
