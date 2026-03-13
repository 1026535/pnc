"""Persistence for the optional discovered castle-roster cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from pnc_automation.config.models import CastleIdentity, CastleRosterOrdering, PncAccountCastleRosterConfig
from pnc_automation.errors import ConfigurationError


@dataclass(slots=True)
class CastleRosterStore:
    """Owns the writable cache of discovered castles keyed by P&C username."""

    path: Path
    rosters: tuple[PncAccountCastleRosterConfig, ...] = ()
    _rosters_by_account: dict[str, PncAccountCastleRosterConfig] = field(init=False, repr=False)
    _account_order: list[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initializes the in-memory roster cache from the loaded configuration."""

        self.path = self.path.resolve()
        self._account_order = []
        self._rosters_by_account = {}
        for roster in self.rosters:
            self._account_order.append(roster.pnc_account_id)
            self._rosters_by_account[roster.pnc_account_id] = roster

    def sync(
        self,
        pnc_account_id: str,
        castles: tuple[CastleIdentity, ...],
        *,
        ordering: CastleRosterOrdering = CastleRosterOrdering.UNKNOWN,
    ) -> PncAccountCastleRosterConfig:
        """Merges discovered castles into the cache and persists the canonical YAML file."""

        if pnc_account_id.strip() == "":
            raise ConfigurationError("P&C roster sync requires a non-empty pnc_account_id.")
        if not castles:
            raise ConfigurationError(
                "P&C roster sync requires at least one discovered castle entry.",
                pnc_account_id=pnc_account_id,
            )

        existing_roster = self._rosters_by_account.get(pnc_account_id)
        merged_roster = _merge_roster(existing_roster, pnc_account_id=pnc_account_id, castles=castles, ordering=ordering)
        if pnc_account_id not in self._rosters_by_account:
            self._account_order.append(pnc_account_id)
        if existing_roster == merged_roster:
            return merged_roster

        self._rosters_by_account[pnc_account_id] = merged_roster
        self._write()
        return merged_roster

    def replace_full_scan(
        self,
        pnc_account_id: str,
        castles: tuple[CastleIdentity, ...],
    ) -> PncAccountCastleRosterConfig:
        """Persists one deterministic full-scan roster ordering for the account."""

        return self.sync(
            pnc_account_id,
            castles,
            ordering=CastleRosterOrdering.FULL_SCAN,
        )

    def get(self, pnc_account_id: str) -> PncAccountCastleRosterConfig | None:
        """Returns one cached roster when it exists."""

        return self._rosters_by_account.get(pnc_account_id)

    def _write(self) -> None:
        """Writes the current cache to disk using the canonical YAML schema."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pnc_accounts": [
                {
                    "pnc_account_id": pnc_account_id,
                    "ordering": self._rosters_by_account[pnc_account_id].ordering.value,
                    "castles": [_serialize_castle(castle) for castle in self._rosters_by_account[pnc_account_id].castles],
                }
                for pnc_account_id in self._account_order
            ]
        }
        with self.path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)


def _merge_castle(existing: CastleIdentity | None, discovered: CastleIdentity) -> CastleIdentity:
    """Combines one existing cached castle with a newly discovered observation."""

    if existing is None:
        return discovered
    return CastleIdentity(
        kingdom=discovered.kingdom,
        castle_name=discovered.castle_name,
        castle_level=discovered.castle_level if discovered.castle_level is not None else existing.castle_level,
    )


def _merge_roster(
    existing: PncAccountCastleRosterConfig | None,
    *,
    pnc_account_id: str,
    castles: tuple[CastleIdentity, ...],
    ordering: CastleRosterOrdering,
) -> PncAccountCastleRosterConfig:
    """Builds the next canonical roster snapshot from one observed castle window."""

    if ordering == CastleRosterOrdering.FULL_SCAN:
        return _merge_full_scan(existing, pnc_account_id=pnc_account_id, castles=castles)

    existing_castles = () if existing is None else existing.castles
    merged_castles = _merge_partial_window(existing_castles, castles)
    merged_ordering = _merge_partial_ordering(existing, castles)
    return PncAccountCastleRosterConfig(
        pnc_account_id=pnc_account_id,
        castles=merged_castles,
        ordering=merged_ordering,
    )


def _merge_full_scan(
    existing: PncAccountCastleRosterConfig | None,
    *,
    pnc_account_id: str,
    castles: tuple[CastleIdentity, ...],
) -> PncAccountCastleRosterConfig:
    """Replaces one roster using a deterministic full-scan ordering."""

    existing_map = {} if existing is None else _castle_map(existing.castles)
    merged_castles = tuple(_merge_castle(existing_map.get(_castle_key(castle)), castle) for castle in castles)
    return PncAccountCastleRosterConfig(
        pnc_account_id=pnc_account_id,
        castles=merged_castles,
        ordering=CastleRosterOrdering.FULL_SCAN,
    )


def _merge_partial_window(
    existing_castles: tuple[CastleIdentity, ...],
    castles: tuple[CastleIdentity, ...],
) -> tuple[CastleIdentity, ...]:
    """Updates one roster window without inventing canonical ordering."""

    merged_order: list[CastleIdentity] = list(existing_castles)
    existing_indexes = {_castle_key(castle): index for index, castle in enumerate(existing_castles)}
    for castle in castles:
        castle_key = _castle_key(castle)
        if castle_key in existing_indexes:
            merged_order[existing_indexes[castle_key]] = _merge_castle(merged_order[existing_indexes[castle_key]], castle)
            continue
        existing_indexes[castle_key] = len(merged_order)
        merged_order.append(castle)
    return tuple(merged_order)


def _merge_partial_ordering(
    existing: PncAccountCastleRosterConfig | None,
    castles: tuple[CastleIdentity, ...],
) -> CastleRosterOrdering:
    """Preserves full-scan ordering only while partial updates remain compatible."""

    if existing is None or not existing.has_trusted_ordering:
        return CastleRosterOrdering.UNKNOWN
    existing_keys = {_castle_key(castle) for castle in existing.castles}
    observed_keys = tuple(_castle_key(castle) for castle in castles)
    if any(castle_key not in existing_keys for castle_key in observed_keys):
        return CastleRosterOrdering.UNKNOWN
    if not _is_in_order_subsequence(tuple(_castle_key(castle) for castle in existing.castles), observed_keys):
        return CastleRosterOrdering.UNKNOWN
    return CastleRosterOrdering.FULL_SCAN


def _castle_map(castles: tuple[CastleIdentity, ...]) -> dict[tuple[str, str], CastleIdentity]:
    """Indexes castle identities by their stable kingdom/name key."""

    return {_castle_key(castle): castle for castle in castles}


def _castle_key(castle: CastleIdentity) -> tuple[str, str]:
    """Returns the stable storage key for one castle identity."""

    return (castle.kingdom, castle.castle_name)


def _is_in_order_subsequence(
    ordering: tuple[tuple[str, str], ...],
    observed: tuple[tuple[str, str], ...],
) -> bool:
    """Returns whether one partial observation preserves the known canonical ordering."""

    next_index = 0
    for castle_key in observed:
        try:
            next_index = ordering.index(castle_key, next_index) + 1
        except ValueError:
            return False
    return True


def _serialize_castle(castle: CastleIdentity) -> dict[str, str | int]:
    """Converts one typed castle identity into the persisted YAML shape."""

    payload: dict[str, str | int] = {
        "kingdom": castle.kingdom,
        "castle_name": castle.castle_name,
    }
    if castle.castle_level is not None:
        payload["castle_level"] = castle.castle_level
    return payload
