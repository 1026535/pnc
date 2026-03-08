"""Persistence for the optional discovered castle-roster cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from pnc_automation.config.models import PncAccountCastleRosterConfig, SelectedCastleConfig
from pnc_automation.errors import ConfigurationError


@dataclass(slots=True)
class CastleRosterStore:
    """Owns the writable cache of discovered castles keyed by P&C username."""

    path: Path
    rosters: tuple[PncAccountCastleRosterConfig, ...] = ()
    _castle_maps: dict[str, dict[tuple[str, str], SelectedCastleConfig]] = field(init=False, repr=False)
    _account_order: list[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initializes the in-memory roster cache from the loaded configuration."""

        self.path = self.path.resolve()
        self._account_order = []
        self._castle_maps = {}
        for roster in self.rosters:
            self._account_order.append(roster.pnc_account_id)
            self._castle_maps[roster.pnc_account_id] = {
                (castle.kingdom, castle.castle_name): castle
                for castle in roster.castles
            }

    def sync(self, pnc_account_id: str, castles: tuple[SelectedCastleConfig, ...]) -> PncAccountCastleRosterConfig:
        """Merges discovered castles into the cache and persists the canonical YAML file."""

        if pnc_account_id.strip() == "":
            raise ConfigurationError("P&C roster sync requires a non-empty pnc_account_id.")
        if not castles:
            raise ConfigurationError(
                "P&C roster sync requires at least one discovered castle entry.",
                pnc_account_id=pnc_account_id,
            )

        existing_map = dict(self._castle_maps.get(pnc_account_id, {}))
        merged_map = dict(existing_map)
        for castle in castles:
            castle_key = (castle.kingdom, castle.castle_name)
            merged_map[castle_key] = _merge_castle(existing_map.get(castle_key), castle)

        if pnc_account_id not in self._castle_maps:
            self._account_order.append(pnc_account_id)
        if existing_map == merged_map:
            return PncAccountCastleRosterConfig(pnc_account_id=pnc_account_id, castles=tuple(merged_map.values()))

        self._castle_maps[pnc_account_id] = merged_map
        self._write()
        return PncAccountCastleRosterConfig(pnc_account_id=pnc_account_id, castles=tuple(merged_map.values()))

    def get(self, pnc_account_id: str) -> PncAccountCastleRosterConfig | None:
        """Returns one cached roster when it exists."""

        castle_map = self._castle_maps.get(pnc_account_id)
        if castle_map is None:
            return None
        return PncAccountCastleRosterConfig(pnc_account_id=pnc_account_id, castles=tuple(castle_map.values()))

    def _write(self) -> None:
        """Writes the current cache to disk using the canonical YAML schema."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pnc_accounts": [
                {
                    "pnc_account_id": pnc_account_id,
                    "castles": [_serialize_castle(castle) for castle in self._castle_maps.get(pnc_account_id, {}).values()],
                }
                for pnc_account_id in self._account_order
            ]
        }
        with self.path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)


def _merge_castle(existing: SelectedCastleConfig | None, discovered: SelectedCastleConfig) -> SelectedCastleConfig:
    """Combines one existing cached castle with a newly discovered observation."""

    if existing is None:
        return discovered
    return SelectedCastleConfig(
        kingdom=discovered.kingdom,
        castle_name=discovered.castle_name,
        castle_level=discovered.castle_level if discovered.castle_level is not None else existing.castle_level,
    )


def _serialize_castle(castle: SelectedCastleConfig) -> dict[str, str | int]:
    """Converts one typed castle identity into the persisted YAML shape."""

    payload: dict[str, str | int] = {
        "kingdom": castle.kingdom,
        "castle_name": castle.castle_name,
    }
    if castle.castle_level is not None:
        payload["castle_level"] = castle.castle_level
    return payload
