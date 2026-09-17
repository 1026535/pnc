"""Missing-ingredient allocation and advisory effort estimates (Plan 02 PW03).

Allocation answers "which observed pieces would fill this order's demands":
exact required pieces are reserved first, then the largest useful lower-tier
intermediates, then a residual base-unit gap that only production can cover.
Effort estimation answers "how much gross production energy would the residual
cost through the best supported producer path" — a deliberately small,
conservative proxy used for ranking, never for authorization. Both operate on
observed Normal usable stock only; no hypothetical regeneration, refunds,
level-up rewards or unclaimed inventory is credited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping

from pnc_automation.app.automation.pet_workshop.board import BoardFacts, MergeChains
from pnc_automation.app.pnc.domain.pet_workshop import WorkshopCooldown
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    PetWorkshopProducer,
)

_MAX_FEED_DEPTH = 2


@dataclass(frozen=True, slots=True)
class DemandAllocation:
    """How observed stock covers one order requirement.

    ``normal_exact`` counts usable Normal pieces of the demanded item;
    ``feedable_exact`` counts feed-locked pieces that a qualified feed would
    unlock with on-board food. ``intermediates`` records the lower-tier normal
    pieces (including consumed feed ingredients) and ``activatables`` the
    inactive pieces a normal partner could merge into the chain — every
    activation produces the catalog successor, so dead stock paired with live
    stock is real progress. ``residual_units`` is the base-unit gap production
    must still supply; when zero, the demand is achievable through free
    merges/activations/feeds.
    """

    item_id: int
    required: int
    normal_exact: int
    feedable_exact: int
    intermediates: Mapping[int, int]
    activatables: Mapping[int, int]
    feed_actions: int
    residual_units: int
    merges_to_build: int

    @property
    def exact(self) -> int:
        """Returns total immediately or freely obtainable required pieces."""

        return self.normal_exact + self.feedable_exact

    @property
    def missing(self) -> int:
        """Returns required pieces not already usable as exact items."""

        return self.required - self.exact

    @property
    def covered_by_stock(self) -> bool:
        """Returns whether merges/feeds alone can complete the demand."""

        return self.residual_units == 0


@dataclass(frozen=True, slots=True)
class GoalAllocation:
    """The reservation result for one order against the current board.

    ``protected_quantities`` is the union of exact required pieces, feed
    ingredients consumed to unlock demanded pieces, and allocated lower-tier
    intermediates — the multiset other goals/actions must not consume.
    """

    demands: tuple[DemandAllocation, ...]
    protected_exact: Mapping[int, int]
    protected_intermediate: Mapping[int, int]
    free_actions: int

    @property
    def missing_quantities(self) -> Mapping[int, int]:
        """Returns item id -> required pieces not yet usable as exact items."""

        return MappingProxyType(
            {demand.item_id: demand.missing for demand in self.demands if demand.missing > 0}
        )

    @property
    def protected_quantities(self) -> Mapping[int, int]:
        """Returns item id -> total reserved piece count for the goal."""

        totals: dict[int, int] = {}
        for source in (self.protected_exact, self.protected_intermediate):
            for item_id, count in source.items():
                totals[item_id] = totals.get(item_id, 0) + count
        return MappingProxyType(totals)

    @property
    def residual_units(self) -> int:
        """Returns the summed base-unit gap production must still supply."""

        return sum(demand.residual_units for demand in self.demands)

    @property
    def covered_by_stock(self) -> bool:
        """Returns whether the whole order is achievable without production."""

        return all(demand.covered_by_stock for demand in self.demands)

    @property
    def satisfied(self) -> bool:
        """Returns whether usable Normal stock already meets every requirement."""

        return all(demand.normal_exact >= demand.required for demand in self.demands)


def _simulate_merge_build(
    normal: dict[int, int],
    inactive: dict[int, int],
    target: int,
    chains: MergeChains,
) -> tuple[int, int]:
    """Greedy merging toward ``target``; returns (formed pieces, actions used).

    An activation is an ordinary 2:1 merge whose second operand is inactive:
    it consumes one Normal piece and one Inactive piece of the same item and
    produces the catalog successor. Only pieces strictly below the target
    tier participate, so a higher-tier piece can never masquerade as progress
    it cannot be split back into.
    """

    formed = 0
    actions = 0
    changed = True
    while changed:
        changed = False
        for item_id in chains.ancestors(target):
            successor = chains.successor(item_id)
            if successor is None:
                continue
            usable = normal.get(item_id, 0)
            pairable = min(inactive.get(item_id, 0), usable)
            pairs = pairable + (usable - pairable) // 2
            if pairs <= 0:
                continue
            normal[item_id] = usable - pairable - 2 * (pairs - pairable)
            inactive[item_id] = inactive.get(item_id, 0) - pairable
            actions += pairs
            changed = True
            if successor == target:
                formed += pairs
            else:
                normal[successor] = normal.get(successor, 0) + pairs
    return formed, actions


def _allocate_demand(
    item_id: int,
    required: int,
    pool: dict[int, int],
    inactive_pool: dict[int, int],
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
) -> DemandAllocation:
    """Reserves stock for one requirement, mutating the shared pools.

    Exact usable pieces are taken first. Feed-locked copies of the demanded
    item then count when their authored ingredient is on board — each claims
    one food piece, which lands in ``intermediates`` as protected stock.
    Finally the largest lower-tier intermediates are allocated toward the
    remaining deficit; an inactive piece counts as usable material only while
    a normal partner survives to merge it, and a merge simulation reports how
    many pieces the sweep can actually form. Whatever base units are left
    uncovered become the residual that production must supply.
    """

    normal_exact = min(required, pool.get(item_id, 0))
    pool[item_id] = pool.get(item_id, 0) - normal_exact
    feedable_exact = 0
    intermediates: dict[int, int] = {}
    producer = catalog.producer_for(item_id)
    if normal_exact < required and producer is not None and producer.feed_item_id is not None:
        take = min(
            required - normal_exact,
            len(board.feed_locked_cells(item_id)),
            pool.get(producer.feed_item_id, 0),
        )
        if take > 0:
            pool[producer.feed_item_id] = pool.get(producer.feed_item_id, 0) - take
            intermediates[producer.feed_item_id] = take
            feedable_exact = take
    missing = required - normal_exact - feedable_exact
    residual_units = 0
    merges = 0
    activatables: dict[int, int] = {}
    if missing > 0:
        needed_units = missing * chains.unit_value(item_id)
        residual_units = needed_units
        taken: dict[int, int] = {}
        taken_units = 0
        ancestors = chains.ancestors(item_id)
        while taken_units < needed_units:
            candidate = next(
                (
                    ancestor
                    for ancestor in ancestors
                    if taken.get(ancestor, 0)
                    < pool.get(ancestor, 0)
                    + min(inactive_pool.get(ancestor, 0), pool.get(ancestor, 0))
                ),
                None,
            )
            if candidate is None:
                break
            taken[candidate] = taken.get(candidate, 0) + 1
            taken_units += chains.unit_value(candidate)
        if taken:
            build_normal: dict[int, int] = {}
            build_inactive: dict[int, int] = {}
            for piece, count in taken.items():
                normals = min(count, pool.get(piece, 0))
                inactives = min(
                    count - normals, inactive_pool.get(piece, 0), normals
                )
                build_normal[piece] = normals
                if inactives:
                    build_inactive[piece] = inactives
                    activatables[piece] = inactives
            formed, merges = _simulate_merge_build(
                build_normal, build_inactive, item_id, chains
            )
            if formed >= missing:
                residual_units = 0
            else:
                residual_units = max(0, needed_units - taken_units)
            for piece, count in taken.items():
                normals = min(count, pool.get(piece, 0))
                pool[piece] = pool.get(piece, 0) - normals
                inactive_pool[piece] = inactive_pool.get(piece, 0) - min(
                    count - normals, inactive_pool.get(piece, 0), normals
                )
                if normals:
                    intermediates[piece] = intermediates.get(piece, 0) + normals
    return DemandAllocation(
        item_id=item_id,
        required=required,
        normal_exact=normal_exact,
        feedable_exact=feedable_exact,
        intermediates=MappingProxyType(intermediates),
        activatables=MappingProxyType(activatables),
        feed_actions=feedable_exact,
        residual_units=residual_units,
        merges_to_build=merges,
    )


def allocate_goal(
    requirements: Mapping[int, int],
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
) -> GoalAllocation:
    """Computes one order's reservations against the observed usable stock.

    Demands are processed lowest demanded tier first so a required low-tier
    piece is protected before a higher-tier demand may sweep the same item
    family as intermediate stock.
    """

    pool: dict[int, int] = board.normal_counts()
    inactive_pool: dict[int, int] = {
        item_id: len(board.inactive_cells(item_id)) for item_id in board.inactive_items
    }
    demands = sorted(requirements.items(), key=lambda kv: (chains.tier(kv[0]), kv[0]))
    allocated: list[DemandAllocation] = []
    for item_id, required in demands:
        allocated.append(
            _allocate_demand(item_id, required, pool, inactive_pool, board, chains, catalog)
        )
    protected_exact: dict[int, int] = {}
    protected_intermediate: dict[int, int] = {}
    free_actions = 0
    for demand in allocated:
        if demand.normal_exact:
            protected_exact[demand.item_id] = protected_exact.get(demand.item_id, 0) + demand.normal_exact
        if demand.feedable_exact:
            protected_intermediate[demand.item_id] = (
                protected_intermediate.get(demand.item_id, 0) + demand.feedable_exact
            )
        for piece, count in demand.intermediates.items():
            protected_intermediate[piece] = protected_intermediate.get(piece, 0) + count
        free_actions += demand.merges_to_build + demand.feed_actions
    return GoalAllocation(
        demands=tuple(allocated),
        protected_exact=MappingProxyType(protected_exact),
        protected_intermediate=MappingProxyType(protected_intermediate),
        free_actions=free_actions,
    )


def useful_units_per_draw(
    producer: PetWorkshopProducer,
    target: int,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
) -> Fraction:
    """Expected base units of ``target``'s chain per production draw.

    Only outputs in the same chain at or below the demanded tier count —
    a higher-tier output can never be split back down.
    """

    group = catalog.drop_group(producer.group_id)
    if group is None:
        return Fraction(0)
    total = Fraction(group.total_weight)
    useful = Fraction(0)
    for entry in group.entries:
        if entry.weight <= 0 or entry.item_id not in chains.closure(target):
            continue
        useful += Fraction(entry.weight * chains.unit_value(entry.item_id))
    return useful / total


@dataclass(frozen=True, slots=True)
class ProducerPath:
    """One supported way to put a needed producer into production."""

    producer_item_id: int
    mode: str  # "available" | "feed" | "build"
    acquire_energy: Fraction
    acquire_actions: int
    uncertain: bool
    feed_item_id: int | None
    note: str


def _estimate_item_energy(
    item_id: int,
    quantity: int,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    depth: int,
) -> tuple[Fraction | None, int, bool]:
    """Returns (energy, actions, uncertain) to obtain ``quantity`` of an item.

    Used recursively for feed ingredients so a missing Food 3 is never
    treated as free; bounded by ``_MAX_FEED_DEPTH``.
    """

    pool = board.normal_counts()
    inactive_pool = {
        item: len(board.inactive_cells(item)) for item in board.inactive_items
    }
    demand = _allocate_demand(
        item_id, quantity, pool, inactive_pool, board, chains, catalog
    )
    if demand.residual_units == 0:
        return Fraction(0), demand.merges_to_build + demand.feed_actions, False
    if depth >= _MAX_FEED_DEPTH:
        return None, 0, False
    estimate = _best_producer_estimate(
        demand.residual_units, item_id, board, chains, catalog, depth + 1
    )
    if estimate is None:
        return None, 0, False
    energy, actions, uncertain, _producer_item, _mode = estimate
    return energy, demand.merges_to_build + demand.feed_actions + actions, uncertain


def _producer_paths(
    producer: PetWorkshopProducer,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    depth: int,
) -> list[ProducerPath]:
    """Enumerates supported ways one producer could serve production.

    An existing finite producer carries an uncertain remaining-use count —
    that lowers estimate confidence, never the legality of one visible
    production. A newly built producer gets its full configured capacity.
    """

    item_id = producer.item_id
    finite = producer.max_num > 0
    paths: list[ProducerPath] = []
    for cell_id in board.normal_cells(item_id):
        cell = board.cell(cell_id)
        cooldown_note = (
            "clear"
            if cell is not None and cell.cooldown == WorkshopCooldown.CLEAR
            else "not clear"
        )
        paths.append(
            ProducerPath(
                producer_item_id=item_id,
                mode="available",
                acquire_energy=Fraction(0),
                acquire_actions=0,
                uncertain=finite,
                feed_item_id=None,
                note=(
                    f"producer on cell {cell_id}, cooldown {cooldown_note}"
                    + ("; finite uses unobserved" if finite else "")
                ),
            )
        )
    for cell_id in board.feed_locked_cells(item_id):
        if producer.feed_item_id is None:
            continue
        if board.normal_count(producer.feed_item_id) > 0:
            paths.append(
                ProducerPath(
                    producer_item_id=item_id,
                    mode="feed",
                    acquire_energy=Fraction(0),
                    acquire_actions=1,
                    uncertain=finite,
                    feed_item_id=producer.feed_item_id,
                    note=f"feed-locked producer on cell {cell_id}, food on board",
                )
            )
        else:
            food = _estimate_item_energy(
                producer.feed_item_id, 1, board, chains, catalog, depth + 1
            )
            if food[0] is not None:
                paths.append(
                    ProducerPath(
                        producer_item_id=item_id,
                        mode="feed",
                        acquire_energy=food[0],
                        acquire_actions=1 + food[1],
                        uncertain=finite or food[2],
                        feed_item_id=producer.feed_item_id,
                        note=f"feed-locked producer on cell {cell_id}, food must be produced",
                    )
                )
    # Building the producer from on-board chain pieces is a free path; an
    # inactive piece contributes when a normal partner can merge it.
    build_normal: dict[int, int] = {}
    build_inactive: dict[int, int] = {}
    for ancestor in chains.ancestors(item_id):
        count = board.normal_count(ancestor)
        if count:
            build_normal[ancestor] = count
        inactive_count = len(board.inactive_cells(ancestor))
        if inactive_count:
            build_inactive[ancestor] = inactive_count
    if build_normal or build_inactive:
        formed, merges = _simulate_merge_build(
            build_normal, build_inactive, item_id, chains
        )
        if formed > 0:
            paths.append(
                ProducerPath(
                    producer_item_id=item_id,
                    mode="build",
                    acquire_energy=Fraction(0),
                    acquire_actions=merges,
                    uncertain=False,
                    feed_item_id=None,
                    note=f"buildable from on-board chain pieces in {merges} merges",
                )
            )
    return paths


def _best_producer_estimate(
    residual_units: int,
    target: int,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    depth: int,
) -> tuple[Fraction, int, bool, int, str] | None:
    """Returns (energy, actions, uncertain, producer_item, mode) for the best path.

    Energy is expected gross production energy plus any feed-ingredient
    production energy; merges, activations and feeds themselves are free.
    For a newly built finite producer the build actions repeat per full
    configured capacity, so its estimate reflects amortized rebuilds.
    """

    cost = Fraction(catalog.activity.production_energy_cost)
    best: tuple[Fraction, int, bool, int, str] | None = None
    for producer in catalog.producers:
        useful = useful_units_per_draw(producer, target, chains, catalog)
        if useful <= 0:
            continue
        draws = Fraction(residual_units) / useful
        for path in _producer_paths(producer, board, chains, catalog, depth):
            builds = 1
            if path.mode == "build" and producer.max_num > 0 and draws > producer.max_num:
                # Amortized rebuilds: each fresh copy supplies max_num draws.
                builds = -(-draws.numerator // (draws.denominator * producer.max_num))
            energy = draws * cost + path.acquire_energy
            total_actions = path.acquire_actions * builds
            key = (energy, total_actions, path.uncertain, producer.item_id)
            if best is None or key < (best[0], best[1], best[2], best[3]):
                best = (energy, total_actions, path.uncertain, producer.item_id, path.mode)
    return best


@dataclass(frozen=True, slots=True)
class DemandEffort:
    """Advisory production estimate for one allocated demand."""

    item_id: int
    residual_units: int
    energy: Fraction | None
    producer_item_id: int | None
    path_mode: str | None
    uncertain: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GoalEffort:
    """Summed advisory estimate for one order goal.

    ``conservative`` marks the documented proxy limit: when one generator
    serves several demands the additive estimate overcounts relative to the
    exact joint expectation (synthetic A/B 50:50 example: proxy 4 draws vs
    exact 3). ``energy`` is ``None`` when any demand has no supported
    production path; such goals rank below all feasible positive-cost goals.
    """

    demand_efforts: tuple[DemandEffort, ...]
    energy: Fraction | None
    free_actions: int
    uncertain: bool
    uncertainty: tuple[str, ...]
    conservative: bool


def estimate_goal(
    allocation: GoalAllocation,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
) -> GoalEffort:
    """Computes the advisory energy estimate for one allocated goal."""

    demand_efforts: list[DemandEffort] = []
    uncertainty: list[str] = []
    producers_used: dict[int, int] = {}
    total_energy = Fraction(0)
    feasible = True
    for demand in allocation.demands:
        if demand.residual_units == 0:
            demand_efforts.append(
                DemandEffort(
                    item_id=demand.item_id,
                    residual_units=0,
                    energy=Fraction(0),
                    producer_item_id=None,
                    path_mode=None,
                    uncertain=False,
                )
            )
            continue
        estimate = _best_producer_estimate(
            demand.residual_units, demand.item_id, board, chains, catalog, 0
        )
        if estimate is None:
            feasible = False
            demand_efforts.append(
                DemandEffort(
                    item_id=demand.item_id,
                    residual_units=demand.residual_units,
                    energy=None,
                    producer_item_id=None,
                    path_mode=None,
                    uncertain=False,
                    notes=(f"no supported producer path for item {demand.item_id}",),
                )
            )
            continue
        energy, actions, uncertain, producer_item, mode = estimate
        total_energy += energy
        producers_used[producer_item] = producers_used.get(producer_item, 0) + 1
        if uncertain:
            uncertainty.append(
                f"producer {producer_item} ({mode}) has unobserved finite uses"
            )
        demand_efforts.append(
            DemandEffort(
                item_id=demand.item_id,
                residual_units=demand.residual_units,
                energy=energy,
                producer_item_id=producer_item,
                path_mode=mode,
                uncertain=uncertain,
            )
        )
    conservative = any(count > 1 for count in producers_used.values())
    return GoalEffort(
        demand_efforts=tuple(demand_efforts),
        energy=total_energy if feasible else None,
        free_actions=allocation.free_actions,
        uncertain=bool(uncertainty),
        uncertainty=tuple(uncertainty),
        conservative=conservative,
    )
