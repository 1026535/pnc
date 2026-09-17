"""Canonical action-legality predicates shared by planner and validator.

``GoalContext`` packages the survey-derived facts an action's legality
depends on — the primary goal's reservations, unmet demands and the
producers that could serve them. ``validate_intent`` composes these
predicates with the mechanics checks; the planner reuses the same predicates
when enumerating candidates, so a proposed action can never be legal in one
place and illegal in the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping

from pnc_automation.app.automation.pet_workshop.board import BoardFacts, MergeChains
from pnc_automation.app.automation.pet_workshop.effort import useful_units_per_draw
from pnc_automation.app.automation.pet_workshop.goals import GoalSelection, select_goals
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopPolicy,
    WorkshopState,
    WorkshopSurveyCoverage,
    WorkshopSurveyFreshness,
)
from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog, PetWorkshopProducer


@dataclass(frozen=True, slots=True)
class GoalContext:
    """Reservation and target facts derived from the current survey.

    ``known`` is False when survey coverage/freshness or ranking-blocking
    reward facts leave goal selection untrustworthy; reservation-bearing
    intents then validate as UNCERTAIN rather than guessing. ``all_targets``
    unions the unmet demanded items, the producers that could serve them and
    feed ingredients a supported feed path still needs produced.
    """

    known: bool
    selection: GoalSelection | None
    protected: Mapping[int, int]
    protected_exact: Mapping[int, int]
    demanded_items: frozenset[int]
    demand_targets: frozenset[int]
    produce_targets: frozenset[int]
    needed_producers: frozenset[int]
    aux_targets: frozenset[int]
    all_targets: frozenset[int]


def goal_context(
    state: WorkshopState,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> GoalContext:
    """Computes the reservation context once per validation or plan pass."""

    survey = state.order_survey
    survey_ok = (
        survey.coverage == WorkshopSurveyCoverage.COMPLETE
        and survey.freshness == WorkshopSurveyFreshness.CURRENT
    )
    if not survey_ok:
        return GoalContext(
            known=False,
            selection=None,
            protected={},
            protected_exact={},
            demanded_items=frozenset(),
            demand_targets=frozenset(),
            produce_targets=frozenset(),
            needed_producers=frozenset(),
            aux_targets=frozenset(),
            all_targets=frozenset(),
        )
    selection = select_goals(state, catalog, policy)
    if selection.inspect_order_ref is not None:
        return GoalContext(
            known=False,
            selection=selection,
            protected={},
            protected_exact={},
            demanded_items=frozenset(),
            demand_targets=frozenset(),
            produce_targets=frozenset(),
            needed_producers=frozenset(),
            aux_targets=frozenset(),
            all_targets=frozenset(),
        )
    primary = selection.primary
    if primary is None:
        return GoalContext(
            known=True,
            selection=selection,
            protected={},
            protected_exact={},
            demanded_items=frozenset(),
            demand_targets=frozenset(),
            produce_targets=frozenset(),
            needed_producers=frozenset(),
            aux_targets=frozenset(),
            all_targets=frozenset(),
        )
    demanded_items = frozenset(primary.assessment.order.requirements)
    demand_targets = frozenset(
        demand.item_id
        for demand in primary.allocation.demands
        if demand.missing > 0
    )
    produce_targets = primary.allocation.production_targets
    needed_producers = primary.allocation.needed_producers
    aux_targets = primary.allocation.auxiliary_targets
    all_targets = demand_targets | aux_targets
    return GoalContext(
        known=True,
        selection=selection,
        protected=primary.allocation.protected_quantities,
        protected_exact=primary.allocation.protected_exact,
        demanded_items=demanded_items,
        demand_targets=demand_targets,
        produce_targets=produce_targets,
        needed_producers=needed_producers,
        aux_targets=frozenset(aux_targets),
        all_targets=all_targets,
    )


def merge_advances(
    ctx: GoalContext,
    successor: int,
    chains: MergeChains,
) -> bool:
    """Returns whether a merge result piece serves an unmet goal demand."""

    return any(
        successor in chains.closure(target) for target in ctx.all_targets
    )


def produce_reservation_verdict(
    ctx: GoalContext, board: BoardFacts, catalog: PetWorkshopCatalog, item_id: int,
) -> str | None:
    """Protects exact order stock from a finite producer's possible exhaustion.

    Unlimited producers remain usable while reserved. With duplicate finite
    pieces, one may produce only while a full required quantity can survive
    that copy's disappearance or transformation.
    """

    producer = catalog.producer_for(item_id)
    if producer is not None and producer.max_num > 0:
        if board.normal_count(item_id) - 1 < ctx.protected_exact.get(item_id, 0):
            return f"finite production could consume required {item_id} pieces"
    return None


def production_progress(
    ctx: GoalContext, producer: PetWorkshopProducer, chains: MergeChains,
    catalog: PetWorkshopCatalog,
) -> Fraction:
    """Returns expected useful units for this producer against the current recipe.

    Planning and pre-gesture revalidation share this calculation. A changed
    survey or completed demand cannot leave an old production action useful
    merely because its selected generator is still mechanically available.
    """

    return sum(
        (useful_units_per_draw(producer, target, chains, catalog)
         for target in ctx.produce_targets), Fraction(0),
    )


def merge_reservation_verdict(
    ctx: GoalContext,
    board: BoardFacts,
    chains: MergeChains,
    item_id: int,
) -> str | None:
    """Returns ``None`` when merging two Normal pieces of ``item_id`` is safe.

    Surplus copies are always mergeable. Reserved intermediates may merge
    only when the result still advances the primary goal, and exact required
    pieces are never consumed.
    """

    usable = board.normal_count(item_id)
    protected = ctx.protected.get(item_id, 0)
    if usable - 2 >= protected:
        return None
    if usable - 2 < ctx.protected_exact.get(item_id, 0):
        return f"merge would consume required {item_id} pieces"
    successor = chains.successor(item_id)
    if successor is None or not merge_advances(ctx, successor, chains):
        return f"merge of reserved {item_id} does not advance the primary goal"
    return None


def activate_reservation_verdict(
    ctx: GoalContext,
    board: BoardFacts,
    chains: MergeChains,
    item_id: int,
) -> str | None:
    """Returns ``None`` when an activation merge on ``item_id`` is safe.

    The consumed Normal fuel may dip into intermediate reservations only when
    the resulting successor still advances the primary goal; exact required
    pieces are never fuel.
    """

    usable = board.normal_count(item_id)
    if usable - 1 < ctx.protected_exact.get(item_id, 0):
        return f"activation would consume required {item_id} pieces"
    if usable - 1 >= ctx.protected.get(item_id, 0):
        return None
    successor = chains.successor(item_id)
    if successor is None or not merge_advances(ctx, successor, chains):
        return f"activation of reserved {item_id} does not advance the primary goal"
    return None


def feed_reservation_verdict(
    ctx: GoalContext,
    board: BoardFacts,
    chains: MergeChains,
    producer_item_id: int,
    food_item_id: int,
) -> str | None:
    """Returns ``None`` when feeding ``food_item_id`` to ``producer_item_id`` is safe.

    The food piece must be unreserved surplus or an ingredient the primary
    goal's production recipe already claims — food reserved as an exact order
    requirement is never feedable.
    """

    target_is_useful = (
        producer_item_id in ctx.needed_producers
        or producer_item_id in ctx.demanded_items
        or any(
            producer_item_id in chains.closure(target)
            for target in ctx.demand_targets
        )
    )
    usable_food = board.normal_count(food_item_id)
    if usable_food - 1 < ctx.protected_exact.get(food_item_id, 0):
        return f"feed would consume required {food_item_id} pieces"
    if usable_food - 1 >= ctx.protected.get(food_item_id, 0):
        return None
    if not target_is_useful:
        return f"feed target {producer_item_id} does not serve the primary goal"
    return None


def recycle_is_blocked(
    ctx: GoalContext,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> str | None:
    """Returns ``None`` only when no useful permitted action frees space.

    A legal merge, activation or feed anywhere on the board — or a ready
    reservation-safe submission — must be tried before the restricted
    recycling allowlist applies.
    """

    for item_id in board.normal_items:
        if chains.successor(item_id) is None:
            continue
        if merge_reservation_verdict(ctx, board, chains, item_id) is None and (
            len(board.normal_cells(item_id)) >= 2
        ):
            return f"legal merge on item {item_id} still frees space"
    for item_id in board.inactive_items:
        if board.normal_count(item_id) <= 0:
            continue
        if chains.successor(item_id) is None:
            continue
        if activate_reservation_verdict(ctx, board, chains, item_id) is None:
            return f"legal activation on item {item_id} still frees space"
    for item_id in board.feed_locked_items:
        producer = catalog.producer_for(item_id)
        if producer is None or producer.feed_item_id is None:
            continue
        if board.normal_count(producer.feed_item_id) <= 0:
            continue
        if feed_reservation_verdict(
            ctx, board, chains, item_id, producer.feed_item_id
        ) is None:
            return f"legal feed on producer {item_id} still frees space"
    if ctx.selection is not None:
        for evaluation in ctx.selection.ranked:
            order = evaluation.assessment.order
            if order.ready is not True:
                continue
            if all(
                board.normal_count(item_id) >= quantity
                for item_id, quantity in order.requirements.items()
            ) and submit_reservation_verdict(ctx, board, order.order_ref) is None:
                return f"ready order {order.order_ref} still frees space"
    return None


def submit_reservation_verdict(
    ctx: GoalContext,
    board: BoardFacts,
    order_ref: int,
) -> str | None:
    """Returns ``None`` when submitting ``order_ref`` keeps the primary's stock.

    The primary goal always passes; any other ready eligible order must leave
    every primary-protected quantity intact on the observed board.
    """

    if ctx.selection is None or ctx.selection.primary is None:
        return None
    if order_ref == ctx.selection.primary.order_ref:
        return None
    order = ctx.selection.evaluation_for(order_ref)
    if order is None:
        return f"order {order_ref} is not an eligible goal"
    item_id = ctx.selection.primary.allocation.surplus_shortfall(
        order.assessment.order.requirements, board
    )
    if item_id is not None:
        return (
            f"submitting order {order_ref} would consume {item_id} "
            f"reserved for the primary goal"
        )
    return None
