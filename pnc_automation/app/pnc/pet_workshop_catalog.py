"""Canonical Pet Workshop catalog loaded from tracked package data.

The packaged seed reproduces the decoded PNC 5.0.203 client tables recorded in
the catalog's own ``provenance`` section: item definitions, producer (worker)
and drop-group records, the board area grid, Workshop level rows, and the
shared activity energy record. Inherited client-table defaults and shared
subtable references were resolved into plain data at authoring time, so the
loader executes no Lua and reads no machine-local extraction paths.

The catalog records game facts only. Order eligibility, supported-mechanic
choices, and recycling restrictions are user policy owned elsewhere; every
valid client-defined item stays representable here, including items current
policy never uses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

_PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data" / "pet_workshop"


class PetWorkshopCatalogError(ValueError):
    """Raised when authored Pet Workshop catalog data violates its schema."""


@dataclass(frozen=True, slots=True)
class CatalogSourceTable:
    """Provenance of one decoded client table that contributed seed rows."""

    name: str
    source_sha256: str
    decoded_sha256: str
    decode: str
    packaged_build: str
    rows: int


@dataclass(frozen=True, slots=True)
class CatalogProvenance:
    """Identifies the client build and source tables behind the packaged seed."""

    packaged_build: str
    generator: str
    source_tables: tuple[CatalogSourceTable, ...]

    def __post_init__(self) -> None:
        """Rejects an empty build label so provenance always names its source."""

        if not self.packaged_build:
            raise PetWorkshopCatalogError("Catalog provenance requires a packaged build label.")


@dataclass(frozen=True, slots=True)
class RecycleReward:
    """Authored reward granted when one board piece is recycled.

    ``item_id`` and ``reward_type`` reference the client's global reward
    tables, not this catalog; they are preserved raw. ``count`` is the granted
    quantity.
    """

    item_id: int
    count: int
    reward_type: int

    def __post_init__(self) -> None:
        """Rejects empty or dangling rewards at construction."""

        if self.item_id <= 0:
            raise PetWorkshopCatalogError("Recycle reward item id must be positive.")
        if self.count <= 0:
            raise PetWorkshopCatalogError("Recycle reward count must be positive.")


@dataclass(frozen=True, slots=True)
class PetWorkshopItem:
    """One client-defined Workshop item.

    ``tier`` is the item's level within its merge chain and
    ``merge_successor_id`` the next item id in that chain, or ``None`` at max
    level. ``item_type``, ``sub_type``, ``sort``, ``get_type``, and ``exp`` are
    raw authored client fields preserved without an asserted meaning.
    ``unlock_cost`` is the authored activation price some mergeable pieces
    carry. ``recoverable`` marks pieces the client permits in the recycling
    flow; ``recycle_reward`` holds the authored reward when one is configured.
    """

    item_id: int
    name: str
    tips: str
    icon: str
    tier: int
    item_type: int
    sub_type: int
    sort: int
    get_type: int
    exp: int
    merge_successor_id: int | None
    unlock_cost: int
    recoverable: bool
    recycle_reward: RecycleReward | None

    def __post_init__(self) -> None:
        """Rejects non-positive ids or tiers and negative quantities."""

        if self.item_id <= 0:
            raise PetWorkshopCatalogError("Item id must be positive.")
        if self.tier <= 0:
            raise PetWorkshopCatalogError(f"Item {self.item_id} has a non-positive tier.")
        if self.exp < 0 or self.unlock_cost < 0:
            raise PetWorkshopCatalogError(f"Item {self.item_id} has a negative authored quantity.")
        if self.merge_successor_id is not None and self.merge_successor_id <= 0:
            raise PetWorkshopCatalogError(f"Item {self.item_id} has a non-positive merge successor id.")


@dataclass(frozen=True, slots=True)
class PetWorkshopProducer:
    """Client producer (worker) record keyed by its generator item id.

    ``worker_type`` is the raw authored ``type`` code. ``num`` and ``max_num``
    are the authored use-count fields; ``max_num`` of 0 means no configured
    exhaustion bound. ``cooldown_ms`` is the authored production cooldown in
    milliseconds. ``group_id`` names the drop group rolled per production.
    ``feed_item_id`` is the authored ``unlockItemId`` ingredient that activates
    production, and ``change_item_id`` the authored exhaustion transform; both
    are ``None`` when the record carries none. ``assist`` is a raw authored
    flag kept for completeness.
    """

    item_id: int
    group_id: int
    worker_type: int
    num: int
    max_num: int
    cooldown_ms: int
    change_item_id: int | None
    feed_item_id: int | None
    assist: int

    def __post_init__(self) -> None:
        """Rejects non-positive ids and negative counts or cooldowns."""

        if self.item_id <= 0 or self.group_id <= 0:
            raise PetWorkshopCatalogError("Producer item and group ids must be positive.")
        if self.num < 0 or self.max_num < 0 or self.cooldown_ms < 0:
            raise PetWorkshopCatalogError(f"Producer {self.item_id} has a negative count or cooldown.")
        if self.change_item_id is not None and self.change_item_id <= 0:
            raise PetWorkshopCatalogError(f"Producer {self.item_id} has a non-positive transform item id.")
        if self.feed_item_id is not None and self.feed_item_id <= 0:
            raise PetWorkshopCatalogError(f"Producer {self.item_id} has a non-positive feed item id.")


@dataclass(frozen=True, slots=True)
class DropGroupEntry:
    """One weighted drop outcome; ``weight`` is the authored rate value.

    A zero weight is authored data (entries gated by other conditions) and is
    preserved; only a group's total must be positive.
    """

    item_id: int
    weight: int

    def __post_init__(self) -> None:
        """Rejects dangling or negatively weighted outcomes."""

        if self.item_id <= 0:
            raise PetWorkshopCatalogError("Drop entry item id must be positive.")
        if self.weight < 0:
            raise PetWorkshopCatalogError(f"Drop entry for item {self.item_id} has a negative weight.")


@dataclass(frozen=True, slots=True)
class DropGroup:
    """One producer drop group; probabilities normalize by the actual weight sum."""

    group_id: int
    entries: tuple[DropGroupEntry, ...]

    def __post_init__(self) -> None:
        """Rejects unnamed groups and groups whose weights cannot normalize."""

        if self.group_id <= 0:
            raise PetWorkshopCatalogError("Drop group id must be positive.")
        if self.total_weight <= 0:
            raise PetWorkshopCatalogError(f"Drop group {self.group_id} has a non-positive total weight.")

    @property
    def total_weight(self) -> int:
        """Returns the sum of authored weights, which need not equal 1000."""

        return sum(entry.weight for entry in self.entries)

    def probability_of(self, item_id: int) -> float:
        """Returns the normalized drop probability for one item, or 0.0 when absent."""

        return sum(entry.weight for entry in self.entries if entry.item_id == item_id) / self.total_weight


@dataclass(frozen=True, slots=True)
class BoardCell:
    """One authored area-grid row: a board position, its unlock gate, and seeds.

    ``position`` is the 1-based board cell index. ``unlock_level`` and
    ``unlock_type`` are raw authored unlock facts; the seed uses level 0 for
    cells with no Workshop-level gate. ``seed_item_ids`` preserves the authored
    ``randomItems`` candidates; it does not describe current board occupancy.
    The client obtains current pieces from server grid data, and automation
    must observe them rather than initializing state from this catalog.
    """

    cell_id: int
    position: int
    unlock_level: int
    unlock_type: int
    seed_item_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        """Rejects non-positive coordinates and negative unlock levels."""

        if self.cell_id <= 0 or self.position <= 0:
            raise PetWorkshopCatalogError("Board cell id and position must be positive.")
        if self.unlock_level < 0:
            raise PetWorkshopCatalogError(f"Board cell {self.cell_id} has a negative unlock level.")


@dataclass(frozen=True, slots=True)
class LevelReward:
    """One authored Workshop-level reward: an item id and a positive count."""

    item_id: int
    count: int

    def __post_init__(self) -> None:
        """Rejects dangling or empty rewards."""

        if self.item_id <= 0:
            raise PetWorkshopCatalogError("Level reward item id must be positive.")
        if self.count <= 0:
            raise PetWorkshopCatalogError("Level reward count must be positive.")


@dataclass(frozen=True, slots=True)
class WorkshopLevel:
    """One authored Workshop level row.

    ``exp`` is the authored experience threshold and ``productivity`` the
    authored energy value for the level; both are raw fields, and level 1
    legitimately carries zeroes. ``rewards`` lists granted items.
    """

    level: int
    exp: int
    productivity: int
    rewards: tuple[LevelReward, ...]

    def __post_init__(self) -> None:
        """Rejects non-positive levels and negative quantities."""

        if self.level <= 0:
            raise PetWorkshopCatalogError("Workshop level must be positive.")
        if self.exp < 0 or self.productivity < 0:
            raise PetWorkshopCatalogError(f"Workshop level {self.level} has a negative quantity.")


@dataclass(frozen=True, slots=True)
class CostEntry:
    """One raw authored cost record: a signed count and a currency ``cost_type``.

    Negative counts denote costs paid out; the sign convention is preserved
    raw from the client table.
    """

    count: int
    cost_type: int

    def __post_init__(self) -> None:
        """Rejects empty cost entries."""

        if self.count == 0 or self.cost_type <= 0:
            raise PetWorkshopCatalogError("Cost entries require a nonzero count and positive type.")


@dataclass(frozen=True, slots=True)
class WorkshopActivityConfig:
    """Authored activity record covering energy and shared costs.

    ``energy_item_id`` is the global item id of the energy currency (44009010
    in the seed). ``energy_capacity`` is the authored regeneration cap,
    ``production_energy_cost`` the energy spent per production, and
    ``energy_regen_ms`` the authored regeneration interval in milliseconds.
    ``cooldown_ms`` and ``cooldown_skip_cost`` are the shared generator
    cooldown facts. ``assist_cost``, ``assist_level``, ``buy_add_productivity``,
    ``buy_count``, ``buy_costs``, ``item_limit_raw``, and ``item_time_ms`` are
    raw authored fields preserved because their encodings are unverified.
    """

    energy_item_id: int
    energy_capacity: int
    production_energy_cost: int
    energy_regen_ms: int
    cooldown_ms: int
    cooldown_skip_cost: int
    assist_cost: int
    assist_level: int
    buy_add_productivity: int
    buy_count: int
    buy_costs: tuple[CostEntry, ...]
    item_limit_raw: str
    item_time_ms: int
    description: str

    def __post_init__(self) -> None:
        """Rejects missing energy facts and negative shared costs."""

        if self.energy_item_id <= 0:
            raise PetWorkshopCatalogError("Activity energy item id must be positive.")
        if self.energy_capacity <= 0 or self.production_energy_cost <= 0 or self.energy_regen_ms <= 0:
            raise PetWorkshopCatalogError("Activity energy capacity, cost, and regen interval must be positive.")
        if self.cooldown_ms < 0 or self.cooldown_skip_cost < 0 or self.item_time_ms < 0:
            raise PetWorkshopCatalogError("Activity cooldown and item-time fields must be non-negative.")


@dataclass(frozen=True, slots=True)
class WorkshopBoardLayout:
    """Logical board dimensions used to validate grid positions and cell ids.

    A cell id is ``(row - 1) * columns + column`` with 1-based row and column,
    matching the observed 7 x 9 board and its 63 authored area-grid rows.
    """

    columns: int
    rows: int

    def __post_init__(self) -> None:
        """Rejects degenerate board geometry."""

        if self.columns <= 0 or self.rows <= 0:
            raise PetWorkshopCatalogError("Board dimensions must be positive.")

    @property
    def cell_count(self) -> int:
        """Returns the number of addressable board cells."""

        return self.columns * self.rows

    def cell_id(self, row: int, column: int) -> int:
        """Returns the 1-based cell id for a coordinate, rejecting out-of-board input."""

        if not self.contains_position(row, column):
            raise PetWorkshopCatalogError(
                f"Board coordinate ({row}, {column}) is outside the {self.rows} x {self.columns} board."
            )
        return (row - 1) * self.columns + column

    def contains_position(self, row: int, column: int) -> bool:
        """Returns whether a 1-based row/column coordinate lies on the board."""

        return 1 <= row <= self.rows and 1 <= column <= self.columns

    def contains_cell_id(self, cell_id: int) -> bool:
        """Returns whether a cell id addresses a real board cell."""

        return 1 <= cell_id <= self.cell_count


class PetWorkshopCatalog:
    """Validated immutable view over the packaged Pet Workshop seed.

    Construction indexes the authored document and enforces schema integrity:
    unique ids, resolvable references, positive required quantities,
    in-bounds grid positions, and an acyclic merge-successor graph. It does not
    enforce the seed's current coverage (item counts, group weights summing to
    1000, or generator Workshop levels) as schema invariants.
    """

    def __init__(self, document: Mapping[str, Any]) -> None:
        """Builds the catalog from one parsed JSON document, failing on invalid data."""

        self._board = _parse_board(_section(document, "board"))
        self._activity = _parse_activity(_section(document, "activity"))
        self._provenance = _parse_provenance(_section(document, "provenance"))
        items = _parse_items(_section(document, "items"))
        producers = _parse_producers(_section(document, "producers"))
        groups = _parse_drop_groups(_section(document, "drop_groups"))
        cells = _parse_cells(_section(document, "grid_cells"), self._board)
        levels = _parse_levels(_section(document, "workshop_levels"))

        items_by_id = _unique_index(items, "item", "item_id")
        producers_by_item = _unique_index(producers, "producer", "item_id")
        groups_by_id = _unique_index(groups, "drop group", "group_id")
        cells_by_id = _unique_index(cells, "board cell", "cell_id")
        levels_by_level = _unique_index(levels, "Workshop level", "level")

        self._check_references(items_by_id, producers_by_item, groups_by_id, cells_by_id, levels_by_level)
        self._check_merge_acyclic(items_by_id)

        self._items = tuple(items)
        self._producers = tuple(producers)
        self._groups = tuple(groups)
        self._cells = tuple(cells)
        self._levels = tuple(levels)
        self._items_by_id = MappingProxyType(items_by_id)
        self._producers_by_item = MappingProxyType(producers_by_item)
        self._groups_by_id = MappingProxyType(groups_by_id)
        self._cells_by_id = MappingProxyType(cells_by_id)
        self._levels_by_level = MappingProxyType(levels_by_level)

    @property
    def board(self) -> WorkshopBoardLayout:
        """Returns the logical board layout that grid positions validate against."""

        return self._board

    @property
    def activity(self) -> WorkshopActivityConfig:
        """Returns the authored energy and shared-cost record."""

        return self._activity

    @property
    def provenance(self) -> CatalogProvenance:
        """Returns the build and source-table provenance of the packaged seed."""

        return self._provenance

    @property
    def items(self) -> tuple[PetWorkshopItem, ...]:
        """Returns every catalog item in authored id order."""

        return self._items

    @property
    def producers(self) -> tuple[PetWorkshopProducer, ...]:
        """Returns every producer record in authored id order."""

        return self._producers

    @property
    def drop_groups(self) -> tuple[DropGroup, ...]:
        """Returns every drop group in authored id order."""

        return self._groups

    @property
    def cells(self) -> tuple[BoardCell, ...]:
        """Returns every authored board cell in id order."""

        return self._cells

    @property
    def levels(self) -> tuple[WorkshopLevel, ...]:
        """Returns every authored Workshop level row in level order."""

        return self._levels

    def item(self, item_id: int) -> PetWorkshopItem | None:
        """Returns one item definition, or ``None`` for an id the client never defined."""

        return self._items_by_id.get(item_id)

    def require_item(self, item_id: int) -> PetWorkshopItem:
        """Returns one item definition or fails for a non-catalog item id."""

        try:
            return self._items_by_id[item_id]
        except KeyError as error:
            raise KeyError(f"Pet Workshop item '{item_id}' is not defined.") from error

    def producer_for(self, item_id: int) -> PetWorkshopProducer | None:
        """Returns the producer record behind a generator item, or ``None``."""

        return self._producers_by_item.get(item_id)

    def drop_group(self, group_id: int) -> DropGroup | None:
        """Returns one drop group by id, or ``None`` when undefined."""

        return self._groups_by_id.get(group_id)

    def cell(self, cell_id: int) -> BoardCell | None:
        """Returns the authored grid row for one cell id, or ``None``."""

        return self._cells_by_id.get(cell_id)

    def level(self, level: int) -> WorkshopLevel | None:
        """Returns the authored Workshop level row, or ``None``."""

        return self._levels_by_level.get(level)

    @staticmethod
    def _check_references(
        items_by_id: dict[int, PetWorkshopItem],
        producers_by_item: dict[int, PetWorkshopProducer],
        groups_by_id: dict[int, DropGroup],
        cells_by_id: dict[int, BoardCell],
        levels_by_level: dict[int, WorkshopLevel],
    ) -> None:
        """Fails the build on any dangling required reference between records.

        Recycle-reward and activity energy item ids intentionally escape this
        check: they reference the client's global item table, which is not part
        of this catalog.
        """

        def require_known(item_id: int, owner: str) -> None:
            """Rejects one missing item reference with its owning record named."""

            if item_id not in items_by_id:
                raise PetWorkshopCatalogError(f"{owner} references undefined item {item_id}.")

        for item in items_by_id.values():
            if item.merge_successor_id is not None:
                require_known(item.merge_successor_id, f"Item {item.item_id} merge successor")
        for producer in producers_by_item.values():
            require_known(producer.item_id, f"Producer {producer.item_id}")
            if producer.change_item_id is not None:
                require_known(producer.change_item_id, f"Producer {producer.item_id} exhaustion transform")
            if producer.feed_item_id is not None:
                require_known(producer.feed_item_id, f"Producer {producer.item_id} feed ingredient")
            if producer.group_id not in groups_by_id:
                raise PetWorkshopCatalogError(
                    f"Producer {producer.item_id} references undefined drop group {producer.group_id}."
                )
        for group in groups_by_id.values():
            for entry in group.entries:
                require_known(entry.item_id, f"Drop group {group.group_id} entry")
        for cell in cells_by_id.values():
            for seed_id in cell.seed_item_ids:
                require_known(seed_id, f"Board cell {cell.cell_id} seed")
        for level in levels_by_level.values():
            for reward in level.rewards:
                require_known(reward.item_id, f"Workshop level {level.level} reward")

    @staticmethod
    def _check_merge_acyclic(items_by_id: dict[int, PetWorkshopItem]) -> None:
        """Fails the build when any merge-successor chain revisits an item."""

        for start in items_by_id.values():
            seen: set[int] = set()
            node = start
            while node.merge_successor_id is not None:
                if node.item_id in seen:
                    raise PetWorkshopCatalogError(
                        f"Merge-successor chain starting at item {start.item_id} contains a cycle at {node.item_id}."
                    )
                seen.add(node.item_id)
                node = items_by_id[node.merge_successor_id]


def load_pet_workshop_catalog(path: Path | None = None) -> PetWorkshopCatalog:
    """Loads the packaged Pet Workshop seed and returns the validated catalog.

    The default path resolves inside the installed ``pnc_automation.app.pnc``
    package; it never consults the ignored client-extraction tree. An explicit
    ``path`` loads an alternate document for tests and tooling.
    """

    catalog_path = path or (_PACKAGE_DATA_DIR / "catalog.json")
    try:
        document = json.loads(
            catalog_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object
        )
    except OSError as error:
        raise PetWorkshopCatalogError(f"Cannot read Pet Workshop catalog at {catalog_path}.") from error
    except json.JSONDecodeError as error:
        raise PetWorkshopCatalogError(f"Pet Workshop catalog at {catalog_path} is not valid JSON: {error}.") from error
    if not isinstance(document, dict):
        raise PetWorkshopCatalogError(f"Pet Workshop catalog at {catalog_path} is not a JSON object.")
    return PetWorkshopCatalog(document)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Builds one authored JSON object without silently discarding duplicate keys."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PetWorkshopCatalogError(f"Duplicate JSON key {key!r} in Pet Workshop catalog.")
        result[key] = value
    return result


def _section(document: Mapping[str, Any], name: str) -> Any:
    """Returns one required top-level document section or fails with its name."""

    if name not in document:
        raise PetWorkshopCatalogError(f"Pet Workshop catalog is missing required section '{name}'.")
    return document[name]


def _require_int(value: Any, what: str) -> int:
    """Returns ``value`` as a strict int, rejecting bools and non-integers."""

    if type(value) is not int:
        raise PetWorkshopCatalogError(f"{what} must be an integer, got {value!r}.")
    return value


def _require_str(value: Any, what: str) -> str:
    """Returns ``value`` as a string, rejecting other types."""

    if not isinstance(value, str):
        raise PetWorkshopCatalogError(f"{what} must be a string, got {value!r}.")
    return value


def _require_bool(value: Any, what: str) -> bool:
    """Returns ``value`` as a strict bool, rejecting truthy lookalikes."""

    if not isinstance(value, bool):
        raise PetWorkshopCatalogError(f"{what} must be a boolean, got {value!r}.")
    return value


def _optional_item_id(value: Any, what: str) -> int | None:
    """Maps the client's ``0``/absent id sentinel to ``None``; keeps real ids."""

    if value is None:
        return None
    item_id = _require_int(value, what)
    return item_id or None


def _parse_provenance(raw: Any) -> CatalogProvenance:
    """Builds provenance from the authored section, tolerating absent tables."""

    if not isinstance(raw, Mapping):
        raise PetWorkshopCatalogError("Catalog provenance must be an object.")
    tables = raw.get("source_tables", {})
    if not isinstance(tables, Mapping):
        raise PetWorkshopCatalogError("Catalog provenance source_tables must be an object.")
    return CatalogProvenance(
        packaged_build=_require_str(raw.get("packaged_build", ""), "provenance packaged_build"),
        generator=_require_str(raw.get("generator", ""), "provenance generator"),
        source_tables=tuple(
            CatalogSourceTable(
                name=_require_str(name, "source table name"),
                source_sha256=_require_str(entry.get("source_sha256", ""), "source table source_sha256"),
                decoded_sha256=_require_str(entry.get("decoded_sha256", ""), "source table decoded_sha256"),
                decode=_require_str(entry.get("decode", ""), "source table decode"),
                packaged_build=_require_str(entry.get("packaged_build", ""), "source table packaged_build"),
                rows=_require_int(entry.get("rows", 0), "source table rows"),
            )
            for name, entry in tables.items()
        ),
    )


def _parse_board(raw: Any) -> WorkshopBoardLayout:
    """Builds the board layout from its authored column/row counts."""

    if not isinstance(raw, Mapping):
        raise PetWorkshopCatalogError("Catalog board must be an object.")
    return WorkshopBoardLayout(
        columns=_require_int(raw.get("columns"), "board columns"),
        rows=_require_int(raw.get("rows"), "board rows"),
    )


def _parse_recycle_reward(raw: Any, owner: str) -> RecycleReward | None:
    """Builds an optional recycle reward; ``None`` stays ``None``."""

    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise PetWorkshopCatalogError(f"{owner} recycle_reward must be an object.")
    return RecycleReward(
        item_id=_require_int(raw.get("item_id"), f"{owner} recycle_reward item_id"),
        count=_require_int(raw.get("count"), f"{owner} recycle_reward count"),
        reward_type=_require_int(raw.get("reward_type"), f"{owner} recycle_reward reward_type"),
    )


def _parse_items(raw: Any) -> list[PetWorkshopItem]:
    """Builds item records from the authored list, keeping raw client fields."""

    if not isinstance(raw, list):
        raise PetWorkshopCatalogError("Catalog items must be a list.")
    items = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise PetWorkshopCatalogError(f"Catalog item at index {index} must be an object.")
        owner = f"Item {row.get('id', f'at index {index}')}"
        items.append(
            PetWorkshopItem(
                item_id=_require_int(row.get("id"), f"{owner} id"),
                name=_require_str(row.get("name", ""), f"{owner} name"),
                tips=_require_str(row.get("tips", ""), f"{owner} tips"),
                icon=_require_str(row.get("icon", ""), f"{owner} icon"),
                tier=_require_int(row.get("tier"), f"{owner} tier"),
                item_type=_require_int(row.get("type"), f"{owner} type"),
                sub_type=_require_int(row.get("sub_type"), f"{owner} sub_type"),
                sort=_require_int(row.get("sort"), f"{owner} sort"),
                get_type=_require_int(row.get("get_type"), f"{owner} get_type"),
                exp=_require_int(row.get("exp"), f"{owner} exp"),
                merge_successor_id=_optional_item_id(row.get("merge_successor_id"), f"{owner} merge_successor_id"),
                unlock_cost=_require_int(row.get("unlock_cost"), f"{owner} unlock_cost"),
                recoverable=_require_bool(row.get("recoverable"), f"{owner} recoverable"),
                recycle_reward=_parse_recycle_reward(row.get("recycle_reward"), owner),
            )
        )
    return items


def _parse_producers(raw: Any) -> list[PetWorkshopProducer]:
    """Builds producer records from the authored worker list."""

    if not isinstance(raw, list):
        raise PetWorkshopCatalogError("Catalog producers must be a list.")
    producers = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise PetWorkshopCatalogError(f"Catalog producer at index {index} must be an object.")
        owner = f"Producer {row.get('item_id', f'at index {index}')}"
        producers.append(
            PetWorkshopProducer(
                item_id=_require_int(row.get("item_id"), f"{owner} item_id"),
                group_id=_require_int(row.get("group_id"), f"{owner} group_id"),
                worker_type=_require_int(row.get("worker_type"), f"{owner} worker_type"),
                num=_require_int(row.get("num"), f"{owner} num"),
                max_num=_require_int(row.get("max_num"), f"{owner} max_num"),
                cooldown_ms=_require_int(row.get("cooldown_ms"), f"{owner} cooldown_ms"),
                change_item_id=_optional_item_id(row.get("change_item_id"), f"{owner} change_item_id"),
                feed_item_id=_optional_item_id(row.get("feed_item_id"), f"{owner} feed_item_id"),
                assist=_require_int(row.get("assist"), f"{owner} assist"),
            )
        )
    return producers


def _parse_drop_groups(raw: Any) -> list[DropGroup]:
    """Builds drop groups keyed by group id; entry weights stay authored values."""

    if not isinstance(raw, Mapping):
        raise PetWorkshopCatalogError("Catalog drop_groups must be an object.")
    groups = []
    for key, entries in raw.items():
        try:
            group_id = int(key)
        except (TypeError, ValueError) as error:
            raise PetWorkshopCatalogError(f"Drop group id {key!r} must be an integer.") from error
        if not isinstance(entries, list):
            raise PetWorkshopCatalogError(f"Drop group {group_id} entries must be a list.")
        groups.append(
            DropGroup(
                group_id=group_id,
                entries=tuple(
                    DropGroupEntry(
                        item_id=_require_int(entry.get("item_id"), f"Drop group {group_id} entry item_id"),
                        weight=_require_int(entry.get("weight"), f"Drop group {group_id} entry weight"),
                    )
                    for entry in _entry_objects(entries, f"Drop group {group_id}")
                ),
            )
        )
    return groups


def _parse_cells(raw: Any, board: WorkshopBoardLayout) -> list[BoardCell]:
    """Builds board cells, validating positions against the declared layout."""

    if not isinstance(raw, list):
        raise PetWorkshopCatalogError("Catalog grid_cells must be a list.")
    cells = []
    positions: set[int] = set()
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise PetWorkshopCatalogError(f"Catalog grid cell at index {index} must be an object.")
        owner = f"Board cell {row.get('cell_id', f'at index {index}')}"
        cell = BoardCell(
            cell_id=_require_int(row.get("cell_id"), f"{owner} cell_id"),
            position=_require_int(row.get("position"), f"{owner} position"),
            unlock_level=_require_int(row.get("unlock_level"), f"{owner} unlock_level"),
            unlock_type=_require_int(row.get("unlock_type"), f"{owner} unlock_type"),
            seed_item_ids=tuple(_require_int(v, f"{owner} seed item id") for v in row.get("seed_item_ids", [])),
        )
        if not board.contains_cell_id(cell.position):
            raise PetWorkshopCatalogError(
                f"Board cell {cell.cell_id} position {cell.position} is outside the {board.rows} x {board.columns} board."
            )
        if cell.position in positions:
            raise PetWorkshopCatalogError(f"Duplicate board position {cell.position}.")
        positions.add(cell.position)
        cells.append(cell)
    return cells


def _parse_levels(raw: Any) -> list[WorkshopLevel]:
    """Builds Workshop level rows with their parsed reward lists."""

    if not isinstance(raw, list):
        raise PetWorkshopCatalogError("Catalog workshop_levels must be a list.")
    levels = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise PetWorkshopCatalogError(f"Catalog Workshop level at index {index} must be an object.")
        owner = f"Workshop level {row.get('level', f'at index {index}')}"
        rewards = row.get("rewards", [])
        if not isinstance(rewards, list):
            raise PetWorkshopCatalogError(f"{owner} rewards must be a list.")
        levels.append(
            WorkshopLevel(
                level=_require_int(row.get("level"), f"{owner} level"),
                exp=_require_int(row.get("exp"), f"{owner} exp"),
                productivity=_require_int(row.get("productivity"), f"{owner} productivity"),
                rewards=tuple(
                    LevelReward(
                        item_id=_require_int(entry.get("item_id"), f"{owner} reward item_id"),
                        count=_require_int(entry.get("count"), f"{owner} reward count"),
                    )
                    for entry in _entry_objects(rewards, owner)
                ),
            )
        )
    return levels


def _parse_activity(raw: Any) -> WorkshopActivityConfig:
    """Builds the shared activity/energy record, preserving unverified fields raw."""

    if not isinstance(raw, Mapping):
        raise PetWorkshopCatalogError("Catalog activity must be an object.")
    buy_costs = raw.get("buy_costs", [])
    if not isinstance(buy_costs, list):
        raise PetWorkshopCatalogError("Activity buy_costs must be a list.")
    return WorkshopActivityConfig(
        energy_item_id=_require_int(raw.get("energy_item_id"), "activity energy_item_id"),
        energy_capacity=_require_int(raw.get("energy_capacity"), "activity energy_capacity"),
        production_energy_cost=_require_int(raw.get("production_energy_cost"), "activity production_energy_cost"),
        energy_regen_ms=_require_int(raw.get("energy_regen_ms"), "activity energy_regen_ms"),
        cooldown_ms=_require_int(raw.get("cooldown_ms"), "activity cooldown_ms"),
        cooldown_skip_cost=_require_int(raw.get("cooldown_skip_cost"), "activity cooldown_skip_cost"),
        assist_cost=_require_int(raw.get("assist_cost"), "activity assist_cost"),
        assist_level=_require_int(raw.get("assist_level"), "activity assist_level"),
        buy_add_productivity=_require_int(raw.get("buy_add_productivity"), "activity buy_add_productivity"),
        buy_count=_require_int(raw.get("buy_count"), "activity buy_count"),
        buy_costs=tuple(
            CostEntry(
                count=_require_int(entry.get("count"), "activity buy_costs count"),
                cost_type=_require_int(entry.get("type"), "activity buy_costs type"),
            )
            for entry in _entry_objects(buy_costs, "activity buy_costs")
        ),
        item_limit_raw=_require_str(raw.get("item_limit_raw", ""), "activity item_limit_raw"),
        item_time_ms=_require_int(raw.get("item_time_ms"), "activity item_time_ms"),
        description=_require_str(raw.get("description", ""), "activity description"),
    )


def _entry_objects(entries: list, owner: str) -> list:
    """Returns the list unchanged after verifying every element is an object."""

    for entry in entries:
        if not isinstance(entry, Mapping):
            raise PetWorkshopCatalogError(f"{owner} entries must be objects, got {entry!r}.")
    return entries


def _unique_index(records: list, owner: str, key_field: str) -> dict[int, Any]:
    """Indexes records by ``key_field``, rejecting duplicate ids."""

    indexed: dict[int, Any] = {}
    for record in records:
        key = getattr(record, key_field)
        if key in indexed:
            raise PetWorkshopCatalogError(f"Duplicate {owner} id {key}.")
        indexed[key] = record
    return indexed
