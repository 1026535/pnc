"""Typed helpers shared by legacy and replacement-core castle-roster scans."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    Observation,
    castle_identity_from_entry,
)
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.core.text.normalization import normalize_ocr_text


@dataclass(slots=True)
class CastleRosterScanState:
    """Accumulates one ordered scan while using cached levels only as hints."""

    level_hints: Mapping[tuple[str, str], int | None]
    seen_windows: set[tuple[tuple[str, str], ...]] = field(default_factory=set)
    ordered_castles: list[CastleIdentity] = field(default_factory=list)
    ordered_indexes: dict[tuple[str, str], int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Copies caller-owned hints so a scan cannot mutate its cache input."""

        self.level_hints = dict(self.level_hints)

    def record_window(self, castles: tuple[CastleIdentity, ...]) -> None:
        """Merges one observed ordered window into the scan-local roster."""

        for castle in castles:
            castle_key = castle_roster_scan_identity_key(castle)
            existing_index = self.ordered_indexes.get(castle_key)
            if existing_index is None:
                self.ordered_indexes[castle_key] = len(self.ordered_castles)
                self.ordered_castles.append(
                    merge_scanned_castle(
                        None,
                        castle,
                        level_hint=self.level_hints.get(castle_key),
                    )
                )
                continue
            self.ordered_castles[existing_index] = merge_scanned_castle(
                self.ordered_castles[existing_index],
                castle,
                level_hint=self.level_hints.get(castle_key),
            )

    def record_window_signature(self, signature: tuple[tuple[str, str], ...]) -> None:
        """Records one validated window signature for repeat and cycle detection."""

        self.seen_windows.add(signature)


def castle_roster_window_castles(observation: Observation) -> tuple[CastleIdentity, ...]:
    """Converts one Manage Characters observation into its ordered castle rows."""

    visible_castles = observation.entries(ListEntryKind.CASTLE)
    if not visible_castles:
        raise TaskVerificationError(
            "Castle roster refresh requires at least one visible castle entry on Manage Char.",
            screen_type=observation.screen_type,
        )
    return tuple(castle_identity_from_entry(entry) for entry in visible_castles)


def castle_roster_window_signature(observation: Observation) -> tuple[tuple[str, str], ...]:
    """Returns stable kingdom/name identities for one visible roster window."""

    return tuple(
        castle_roster_scan_identity_key(castle)
        for castle in castle_roster_window_castles(observation)
    )


def castle_roster_scan_identity_key(castle: CastleIdentity) -> tuple[str, str]:
    """Returns the exact kingdom and normalized OCR name used by scan matching."""

    return (castle.kingdom, normalize_ocr_text(castle.castle_name))


def merge_scanned_castle(
    existing: CastleIdentity | None,
    discovered: CastleIdentity,
    *,
    level_hint: int | None,
) -> CastleIdentity:
    """Builds scan-local state with observed levels before prior-cache hints."""

    castle_level = discovered.castle_level
    if castle_level is None and existing is not None:
        castle_level = existing.castle_level
    if castle_level is None:
        castle_level = level_hint
    return CastleIdentity(
        kingdom=discovered.kingdom,
        castle_name=discovered.castle_name,
        castle_level=castle_level,
    )
