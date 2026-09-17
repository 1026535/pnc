"""Derived board facts and merge-chain lookups for the pure Workshop solver.

Both helpers recompute from the immutable catalog and the current typed
state on every planning call — the solver never persists a second inventory
or replays a speculative queue. ``MergeChains`` covers only catalog facts
(successor graph, tiers, base-unit values); ``BoardFacts`` covers only
observed cell facts (usable stock, space, unread cells).
"""

from __future__ import annotations

from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopCell,
    WorkshopCellAccess,
    WorkshopCooldown,
    WorkshopItemStatus,
    WorkshopOccupancy,
    WorkshopState,
)
from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog


class MergeChains:
    """Precomputed merge-graph lookups over the packaged catalog.

    The authored graph is a set of linear chains (verified for the packaged
    seed): every item has at most one successor and one predecessor. A tier-k
    piece is worth ``2 ** (k - 1)`` base units because each merge result
    takes exactly two copies of the predecessor.
    """

    def __init__(self, catalog: PetWorkshopCatalog) -> None:
        """Indexes successors and transitive predecessors once per planning call."""

        items = {item.item_id: item for item in catalog.items}
        predecessors: dict[int, tuple[int, ...]] = {}
        for item in catalog.items:
            if item.merge_successor_id is not None:
                prior = predecessors.get(item.merge_successor_id, ())
                predecessors[item.merge_successor_id] = (*prior, item.item_id)
        self._items = items
        self._predecessors = predecessors
        ancestors: dict[int, tuple[int, ...]] = {}
        for item_id in items:
            collected: list[int] = []
            seen: set[int] = set()
            stack = list(predecessors.get(item_id, ()))
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                collected.append(current)
                stack.extend(predecessors.get(current, ()))
            collected.sort(key=lambda other: items[other].tier, reverse=True)
            ancestors[item_id] = tuple(collected)
        self._ancestors = ancestors

    def item(self, item_id: int):
        """Returns the catalog record for one item, or ``None``."""

        return self._items.get(item_id)

    def tier(self, item_id: int) -> int:
        """Returns the authored tier, or 0 for an undefined item id."""

        item = self._items.get(item_id)
        return item.tier if item is not None else 0

    def successor(self, item_id: int) -> int | None:
        """Returns the merge successor item id, or ``None`` at max tier."""

        item = self._items.get(item_id)
        return item.merge_successor_id if item is not None else None

    def is_terminal(self, item_id: int) -> bool:
        """Returns whether the item has no merge successor."""

        return self.successor(item_id) is None

    def ancestors(self, item_id: int) -> tuple[int, ...]:
        """Returns every lower-tier chain member, highest tier first."""

        return self._ancestors.get(item_id, ())

    def closure(self, item_id: int) -> frozenset[int]:
        """Returns the item plus all lower-tier members of its chain."""

        return frozenset({item_id, *self._ancestors.get(item_id, ())})

    def unit_value(self, item_id: int) -> int:
        """Returns the binary-merge base-unit value of one piece (2^(tier-1))."""

        item = self._items.get(item_id)
        if item is None:
            return 0
        return 1 << (item.tier - 1)


class BoardFacts:
    """Indexed view of the observed cells of one WorkshopState.

    Counts and cell lists cover only pieces that are both usable (unlocked
    cell) and observed Normal. Inactive, bubble, feed-locked, unread-status
    and unidentified pieces never count as spendable stock; they stay
    reachable through the dedicated accessors so callers can reason about
    them explicitly.
    """

    def __init__(self, state: WorkshopState) -> None:
        """Partitions observed cells once per planning call."""

        self.state = state
        self._cells: dict[int, WorkshopCell] = {cell.cell_id: cell for cell in state.cells}
        normal: dict[int, list[int]] = {}
        inactive: dict[int, list[int]] = {}
        feed_locked: dict[int, list[int]] = {}
        bubble: dict[int, list[int]] = {}
        usable_empty: list[int] = []
        unread_pieces: list[int] = []
        for cell in state.cells:
            if cell.access != WorkshopCellAccess.USABLE:
                continue
            if cell.occupancy == WorkshopOccupancy.EMPTY:
                usable_empty.append(cell.cell_id)
                continue
            if cell.occupancy != WorkshopOccupancy.OCCUPIED:
                continue
            if cell.item_id is None or cell.item_status is None:
                unread_pieces.append(cell.cell_id)
                continue
            if cell.item_status == WorkshopItemStatus.NORMAL:
                normal.setdefault(cell.item_id, []).append(cell.cell_id)
            elif cell.item_status == WorkshopItemStatus.INACTIVE:
                inactive.setdefault(cell.item_id, []).append(cell.cell_id)
            elif cell.item_status == WorkshopItemStatus.FEED_LOCKED:
                feed_locked.setdefault(cell.item_id, []).append(cell.cell_id)
            elif cell.item_status == WorkshopItemStatus.BUBBLE:
                bubble.setdefault(cell.item_id, []).append(cell.cell_id)
            else:
                unread_pieces.append(cell.cell_id)
        self._normal = {item: tuple(cells) for item, cells in normal.items()}
        self._inactive = {item: tuple(cells) for item, cells in inactive.items()}
        self._feed_locked = {item: tuple(cells) for item, cells in feed_locked.items()}
        self._bubble = {item: tuple(cells) for item, cells in bubble.items()}
        self._usable_empty = tuple(usable_empty)
        self._unread_pieces = tuple(unread_pieces)

    def cell(self, cell_id: int) -> WorkshopCell | None:
        """Returns the observed cell with one id, or ``None``."""

        return self._cells.get(cell_id)

    def normal_cells(self, item_id: int) -> tuple[int, ...]:
        """Returns usable Normal cells holding one item, in id order."""

        return self._normal.get(item_id, ())

    def normal_count(self, item_id: int) -> int:
        """Returns the usable Normal piece count for one item."""

        return len(self._normal.get(item_id, ()))

    def inactive_cells(self, item_id: int) -> tuple[int, ...]:
        """Returns usable Inactive (grey) cells holding one item."""

        return self._inactive.get(item_id, ())

    def feed_locked_cells(self, item_id: int) -> tuple[int, ...]:
        """Returns usable feed-locked cells holding one item."""

        return self._feed_locked.get(item_id, ())

    def bubble_cells(self, item_id: int) -> tuple[int, ...]:
        """Returns usable bubble cells holding one item."""

        return self._bubble.get(item_id, ())

    def occupied_known_cells(self) -> tuple[int, ...]:
        """Returns usable occupied cells with a read item and status."""

        out: list[int] = []
        for bucket in (self._normal, self._inactive, self._feed_locked, self._bubble):
            for cells in bucket.values():
                out.extend(cells)
        return tuple(sorted(out))

    @property
    def usable_empty_cells(self) -> tuple[int, ...]:
        """Returns cells confirmed usable and empty."""

        return self._usable_empty

    @property
    def unread_piece_cells(self) -> tuple[int, ...]:
        """Returns usable occupied cells whose piece identity/state was not read."""

        return self._unread_pieces

    @property
    def unknown_state_cells(self) -> tuple[int, ...]:
        """Returns observed cells whose access or occupancy was never read.

        These are the cells that leave ``board_full`` undetermined — a cell
        with unread access cannot be confirmed usable, and a usable cell
        with unread occupancy is neither confirmed empty nor occupied.
        """

        return tuple(
            sorted(
                cell.cell_id
                for cell in self.state.cells
                if cell.access == WorkshopCellAccess.UNKNOWN
                or cell.occupancy == WorkshopOccupancy.UNKNOWN
            )
        )

    @property
    def unobserved_cell_ids(self) -> frozenset[int]:
        """Returns board positions with no observation this frame."""

        return self.state.unobserved_cell_ids

    @property
    def board_full(self) -> bool | None:
        """Returns whether every usable cell is confirmed occupied.

        ``None`` means fullness cannot be established: some usable cell has
        unknown occupancy or is unobserved, so neither 'has space' nor
        'confirmed full' can be claimed.
        """

        if self._usable_empty:
            return False
        for cell_id in range(1, self.state.board.cell_count + 1):
            cell = self._cells.get(cell_id)
            if cell is None or cell.access == WorkshopCellAccess.UNKNOWN:
                return None
            if cell.access != WorkshopCellAccess.USABLE:
                continue
            if cell.occupancy != WorkshopOccupancy.OCCUPIED:
                return None
        return True

    def merge_pairs(self, item_id: int) -> tuple[tuple[int, int], ...]:
        """Returns unordered Normal pairings of one item, lowest cell ids first."""

        cells = self.normal_cells(item_id)
        return tuple(
            (cells[i], cells[j]) for i in range(len(cells)) for j in range(i + 1, len(cells))
        )

    @property
    def normal_items(self) -> tuple[int, ...]:
        """Returns item ids present as usable Normal pieces, id order."""

        return tuple(sorted(self._normal))

    @property
    def inactive_items(self) -> tuple[int, ...]:
        """Returns item ids present as usable Inactive (grey) pieces."""

        return tuple(sorted(self._inactive))

    @property
    def feed_locked_items(self) -> tuple[int, ...]:
        """Returns item ids present as usable feed-locked pieces."""

        return tuple(sorted(self._feed_locked))

    def normal_counts(self) -> dict[int, int]:
        """Returns a mutable item-id -> usable Normal count snapshot."""

        return {item_id: len(cells) for item_id, cells in self._normal.items()}
