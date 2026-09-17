"""Missing-ingredient allocation and advisory effort estimates (Plan 02 PW03).

``allocate_goal`` owns both reservations and advisory effort. Exact order
pieces are reserved together before a shared stock pool allocates intermediates,
feed ingredients and producer construction. The selected recipe supplies the
planner's targets, so effort and legality cannot borrow the same piece twice.
Expected useful draws form a small conservative proxy, never authorization or
a predicted drop. Only observed stock and catalog recipes contribute; no
hypothetical regeneration, refunds or unclaimed inventory is credited.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping

from pnc_automation.app.automation.pet_workshop.board import BoardFacts, MergeChains
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    PetWorkshopProducer,
)

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
    intermediates and producer stock — the multiset other goals/actions must
    not consume. ``effort`` and the production/auxiliary targets come from
    this same allocation, never a second estimate against the original board.
    """

    demands: tuple[DemandAllocation, ...]
    protected_exact: Mapping[int, int]
    protected_intermediate: Mapping[int, int]
    free_actions: int
    effort: GoalEffort
    production_targets: frozenset[int]
    auxiliary_targets: frozenset[int]
    needed_producers: frozenset[int]

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

        return self.effort.energy == 0

    @property
    def satisfied(self) -> bool:
        """Returns whether usable Normal stock already meets every requirement."""

        return all(demand.normal_exact >= demand.required for demand in self.demands)

    def surplus_shortfall(self, requirements: Mapping[int, int], board: BoardFacts) -> int | None:
        """Returns the first item another order cannot take from unreserved stock."""

        protected = self.protected_quantities
        return next(
            (item for item, count in requirements.items()
             if board.normal_count(item) - count < protected.get(item, 0)),
            None,
        )


def _take_free_piece(
    target: int,
    pool: dict[int, int],
    inactive: dict[int, int],
    chains: MergeChains,
    used: dict[int, int],
    activated: dict[int, int],
) -> int | None:
    """Allocates one attainable piece and returns its free merge action count.

    A Normal activation partner may itself be built through earlier merges.
    Failed recipe branches restore the small observed-stock pool; successful
    branches record original pieces, never hypothetical surviving squares.
    """

    if pool.get(target, 0):
        pool[target] -= 1
        used[target] = used.get(target, 0) + 1
        return 0
    for predecessor in chains.predecessors(target):
        snapshots = tuple(dict(source) for source in (pool, inactive, used, activated))
        first = _take_free_piece(predecessor, pool, inactive, chains, used, activated)
        if first is not None:
            if inactive.get(predecessor, 0):
                inactive[predecessor] -= 1
                activated[predecessor] = activated.get(predecessor, 0) + 1
                return first + 1
            second = _take_free_piece(predecessor, pool, inactive, chains, used, activated)
            if second is not None:
                return first + second + 1
        for destination, saved in zip((pool, inactive, used, activated), snapshots):
            destination.clear()
            destination.update(saved)
    return None


def _allocate_demand(
    item_id: int,
    required: int,
    pool: dict[int, int],
    inactive_pool: dict[int, int],
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    *,
    exact_reserved: int | None = None,
    feed_pool: dict[int, int],
) -> DemandAllocation:
    """Reserves stock for one requirement, mutating the shared pools.

    Exact usable pieces are taken first. Feed-locked copies of the demanded
    item then count when their authored ingredient is on board — each claims
    one food piece, which lands in ``intermediates`` as protected stock.
    Finally the largest attainable lower-tier intermediates are allocated
    toward the deficit. Inactive material counts only with a Normal partner,
    including one built by the same free traversal. Remaining base units are
    completed by the shared recipe evaluator.
    """

    if exact_reserved is None:
        normal_exact = min(required, pool.get(item_id, 0))
        pool[item_id] = pool.get(item_id, 0) - normal_exact
    else:
        normal_exact = exact_reserved
    feedable_exact = 0
    intermediates: dict[int, int] = {}
    producer = catalog.producer_for(item_id)
    if normal_exact < required and producer is not None and producer.feed_item_id is not None:
        take = min(
            required - normal_exact,
            feed_pool.get(item_id, 0),
            pool.get(producer.feed_item_id, 0),
        )
        if take > 0:
            pool[producer.feed_item_id] = pool.get(producer.feed_item_id, 0) - take
            intermediates[producer.feed_item_id] = take
            feedable_exact = take
            feed_pool[item_id] -= take
    missing = required - normal_exact - feedable_exact
    residual_units = 0
    merges = 0
    activatables: dict[int, int] = {}
    if missing > 0:
        needed_units = missing * chains.unit_value(item_id)
        residual_units = needed_units
        # Exact attainable results come first, then largest useful partial
        # results. Both use the same free recipe traversal and stock pool.
        for target in (item_id, *chains.ancestors(item_id)):
            units = chains.unit_value(target)
            while residual_units >= units:
                actions = _take_free_piece(
                    target, pool, inactive_pool, chains, intermediates, activatables
                )
                if actions is None:
                    break
                residual_units -= units
                merges += actions
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

    Every exact requirement is reserved before any recipe can consume its
    ingredients. Remaining demands allocate largest useful attainable
    intermediates without reusing Normal or inactive pieces. Feed and producer
    recipes then consume that same remaining pool; the result carries both
    reservations and effort for every caller.
    """

    pool: dict[int, int] = board.normal_counts()
    exact = {item: min(required, pool.get(item, 0)) for item, required in requirements.items()}
    for item, count in exact.items():
        pool[item] = pool.get(item, 0) - count
    inactive_pool: dict[int, int] = {
        item_id: len(board.inactive_cells(item_id)) for item_id in board.inactive_items
    }
    feed_pool = {item: len(board.feed_locked_cells(item)) for item in board.feed_locked_items}
    demands = sorted(requirements.items(), key=lambda kv: (chains.tier(kv[0]), kv[0]))
    allocated: list[DemandAllocation] = []
    for item_id, required in demands:
        allocated.append(
            _allocate_demand(
                item_id, required, pool, inactive_pool, chains, catalog,
                exact_reserved=exact[item_id],
                feed_pool=feed_pool,
            )
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
    recipe = _RecipePool(pool, inactive_pool, feed_pool)
    for item, count in protected_exact.items():
        producer = catalog.producer_for(item)
        if count and producer is not None and producer.max_num == 0:
            recipe.supplies[item] = _Supply(None, "available")
    evaluator = _RecipePlanner(chains, catalog)
    efforts: list[DemandEffort] = []
    feasible = True
    for demand in allocated:
        before = recipe.energy
        result = evaluator.complete(demand.item_id, demand.residual_units, recipe, frozenset())
        if result is None:
            feasible = False
            efforts.append(DemandEffort(demand.item_id, demand.residual_units, None, None, None, False,
                                       (f"no supported producer path for item {demand.item_id}",)))
            continue
        recipe, producer_item, mode = result
        efforts.append(DemandEffort(demand.item_id, demand.residual_units,
                                   recipe.energy - before if recipe.complete else None,
                                   producer_item, mode, recipe.uncertain))
    for piece, count in recipe.protected.items():
        protected_intermediate[piece] = protected_intermediate.get(piece, 0) + count
    effort = GoalEffort(
        demand_efforts=tuple(efforts), energy=recipe.energy if feasible and recipe.complete else None,
        free_actions=free_actions + recipe.actions, uncertain=recipe.uncertain,
        uncertainty=tuple(sorted(recipe.notes)),
        conservative=any(len(targets) > 1 for targets in recipe.served.values()),
    )
    return GoalAllocation(
        demands=tuple(allocated),
        protected_exact=MappingProxyType(protected_exact),
        protected_intermediate=MappingProxyType(protected_intermediate),
        free_actions=free_actions + recipe.actions,
        effort=effort,
        production_targets=frozenset(recipe.production_targets),
        auxiliary_targets=frozenset(recipe.auxiliary_targets),
        needed_producers=frozenset(recipe.served),
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


@dataclass(frozen=True, slots=True)
class _Supply:
    """One allocated producer: only a newly built copy has known finite capacity."""

    remaining: Fraction | None
    mode: str
    uncertain: bool = False


@dataclass(slots=True)
class _RecipePool:
    """One goal's remaining observed stock and selected advisory recipe.

    Alternative paths copy this small multiset; only the chosen path survives.
    Produced drops are priced, never inserted into the observed stock pool.
    Supplies retain acquisition cost and fresh finite capacity across demands.
    """

    normal: dict[int, int]
    inactive: dict[int, int]
    locked: dict[int, int]
    protected: dict[int, int] = field(default_factory=dict)
    supplies: dict[int, _Supply] = field(default_factory=dict)
    production_targets: set[int] = field(default_factory=set)
    auxiliary_targets: set[int] = field(default_factory=set)
    served: dict[int, frozenset[int]] = field(default_factory=dict)
    energy: Fraction = Fraction(0)
    actions: int = 0
    uncertain: bool = False
    notes: set[str] = field(default_factory=set)
    complete: bool = True

    def copy(self) -> _RecipePool:
        """Copies mutable allocation state before trying a recipe alternative."""

        return replace(
            self, normal=dict(self.normal), inactive=dict(self.inactive), locked=dict(self.locked),
            protected=dict(self.protected), supplies=dict(self.supplies),
            production_targets=set(self.production_targets), auxiliary_targets=set(self.auxiliary_targets),
            served=dict(self.served), notes=set(self.notes),
        )

    def reserve(self, used: Mapping[int, int]) -> None:
        """Adds original Normal pieces consumed or retained by this recipe."""

        for item, count in used.items():
            if count:
                self.protected[item] = self.protected.get(item, 0) + count


@dataclass(frozen=True, slots=True)
class _RecipePlanner:
    """Expands catalog recipes against one shared goal pool without simulating drops."""

    chains: MergeChains
    catalog: PetWorkshopCatalog

    def obtain(self, target: int, pool: _RecipePool, trail: frozenset[int]) -> _RecipePool | None:
        """Allocates one ingredient, pricing its uncovered units through reachable producers."""

        if target in trail:
            return None
        candidate = pool.copy()
        demand = _allocate_demand(
            target, 1, candidate.normal, candidate.inactive, self.chains, self.catalog,
            feed_pool=candidate.locked,
        )
        candidate.reserve(demand.intermediates)
        candidate.reserve({target: demand.normal_exact})
        candidate.actions += demand.merges_to_build + demand.feed_actions
        if demand.normal_exact < 1:
            candidate.auxiliary_targets.add(target)
        if demand.residual_units == 0:
            return candidate
        result = self.complete(target, demand.residual_units, candidate, trail)
        return result[0] if result is not None and result[0].complete else None

    def complete(
        self, target: int, units: int, pool: _RecipePool, trail: frozenset[int],
    ) -> tuple[_RecipePool, int | None, str | None] | None:
        """Chooses production or an observed feed-locked copy for an uncovered demand."""

        if units == 0:
            return pool, None, None
        if target in trail:
            return None
        trail = trail | {target}
        candidates: list[tuple[_RecipePool, int | None, str | None]] = []
        production = self.produce(target, units, pool, trail)
        if production is not None:
            candidates.append(production)
        producer = self.catalog.producer_for(target)
        quantity = (units + self.chains.unit_value(target) - 1) // self.chains.unit_value(target)
        if producer is not None and producer.feed_item_id is not None and pool.locked.get(target, 0) >= quantity:
            fed: _RecipePool | None = pool.copy()
            for _ in range(quantity):
                fed = self.feed(producer, fed, trail)
                if fed is None:
                    break
            if fed is not None:
                candidates.append((fed, target, "feed"))
        return min(candidates, key=lambda result: (not result[0].complete, result[0].energy, result[0].actions,
                   result[0].uncertain, result[1] or 0)) if candidates else None

    def feed(
        self, producer: PetWorkshopProducer, pool: _RecipePool, trail: frozenset[int],
    ) -> _RecipePool | None:
        """Claims one feed-locked piece and its exact separately allocated ingredient."""

        if producer.feed_item_id is None or pool.locked.get(producer.item_id, 0) <= 0:
            return None
        candidate = self.obtain(producer.feed_item_id, pool, trail)
        if candidate is None:
            return None
        candidate.locked[producer.item_id] -= 1
        candidate.actions += 1
        candidate.auxiliary_targets.add(producer.item_id)
        return candidate

    def acquire(
        self, producer: PetWorkshopProducer, pool: _RecipePool, trail: frozenset[int],
    ) -> _RecipePool | None:
        """Chooses one existing, fed or freshly constructed producer without borrowing stock twice."""

        item = producer.item_id
        candidates: list[_RecipePool] = []
        if pool.normal.get(item, 0):
            available = pool.copy()
            available.normal[item] -= 1
            available.reserve({item: 1})
            available.supplies[item] = _Supply(None, "available", producer.max_num > 0)
            candidates.append(available)
        fed = self.feed(producer, pool, trail | {item})
        if fed is not None:
            # Feeding an observed copy does not reveal its remaining counter.
            fed.supplies[item] = _Supply(None, "feed", producer.max_num > 0)
            candidates.append(fed)
        if not pool.normal.get(item, 0):
            built = self.obtain(item, pool, trail)
            if built is not None:
                # Only an ordinary construction receives a fresh maximum.
                # A fed existing copy retains explicitly unknown capacity.
                fed_existing = built.locked.get(item, 0) < pool.locked.get(item, 0)
                built.supplies[item] = _Supply(
                    Fraction(producer.max_num) if producer.max_num and not fed_existing else None,
                    "feed" if fed_existing else "build", bool(producer.max_num and fed_existing),
                )
                built.auxiliary_targets.add(item)
                candidates.append(built)
        return min(candidates, key=lambda candidate: (candidate.energy, candidate.actions,
                   candidate.supplies[item].uncertain)) if candidates else None

    def produce(
        self, target: int, units: int, pool: _RecipePool, trail: frozenset[int],
    ) -> tuple[_RecipePool, int, str] | None:
        """Prices useful expected draws and every required fresh finite replacement.

        An observed finite supply has unknown remaining uses: its numerical
        proxy stays uncertain and is never granted a fresh maximum. For a
        constructed supply, additional copies consume new ingredients from
        the same pool, including their upstream production energy.
        """

        candidates: list[tuple[_RecipePool, int, str]] = []
        for producer in self.catalog.producers:
            useful = useful_units_per_draw(producer, target, self.chains, self.catalog)
            if useful <= 0:
                continue
            item = producer.item_id
            candidate: _RecipePool | None = pool.copy()
            draws = Fraction(units) / useful
            mode: str | None = None
            while draws > 0:
                supply = candidate.supplies.get(item)
                if supply is None or supply.remaining == 0:
                    acquired = self.acquire(producer, candidate, trail)
                    if acquired is None:
                        if mode is None:
                            candidate = None
                        else:
                            candidate.complete = False
                            candidate.notes.add(f"additional producer {item} has no supported acquisition path")
                        break
                    candidate = acquired
                    supply = candidate.supplies[item]
                mode = mode or supply.mode
                used = draws if supply.remaining is None else min(draws, supply.remaining)
                candidate.energy += used * self.catalog.activity.production_energy_cost
                candidate.uncertain |= supply.uncertain
                if supply.uncertain:
                    candidate.notes.add(f"producer {item} ({supply.mode}) has unobserved finite uses")
                if supply.remaining is not None:
                    candidate.supplies[item] = replace(supply, remaining=supply.remaining - used)
                draws -= used
            if candidate is not None and mode is not None:
                candidate.production_targets.add(target)
                candidate.served[item] = candidate.served.get(item, frozenset()) | {target}
                candidates.append((candidate, item, mode))
        return min(candidates, key=lambda result: (not result[0].complete, result[0].energy, result[0].actions,
                   result[0].uncertain, result[1])) if candidates else None
