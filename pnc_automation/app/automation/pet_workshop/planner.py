"""Deterministic one-step planner for the Pet Workshop (Plan 02 PW04).

``plan_next`` reads the recognized board state, the packaged catalog and the
policy, and returns exactly one ``WorkshopDecision`` — one typed intent plus
the reservation and effort diagnostics the caller and the fresh-state
revalidator need. It performs no I/O of any kind: no emulator, image,
filesystem, clock or network access, and it never queues speculative
follow-up actions. Every decision re-derives goal ranking, reservations and
legality from the current state, and every returned mutation intent is
self-checked through the canonical ``validate_intent``.
"""

from __future__ import annotations

from fractions import Fraction

from pnc_automation.app.automation.pet_workshop.board import BoardFacts, MergeChains
from pnc_automation.app.automation.pet_workshop.rules import (
    GoalContext,
    activate_reservation_verdict,
    feed_reservation_verdict,
    goal_context,
    merge_reservation_verdict,
)
from pnc_automation.app.automation.pet_workshop.effort import useful_units_per_draw
from pnc_automation.app.automation.pet_workshop.validation import validate_intent
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopActivateIntent,
    WorkshopCooldown,
    WorkshopDecision,
    WorkshopFeedIntent,
    WorkshopInspectIntent,
    WorkshopInspectKind,
    WorkshopIntent,
    WorkshopMergeIntent,
    WorkshopPolicy,
    WorkshopProduceIntent,
    WorkshopProductionMode,
    WorkshopRecycleIntent,
    WorkshopSelectIntent,
    WorkshopSelectionKind,
    WorkshopState,
    WorkshopStopIntent,
    WorkshopStopReason,
    WorkshopSubmitOrderIntent,
    WorkshopSurfaceKind,
    WorkshopSurveyCoverage,
    WorkshopSurveyFreshness,
    WorkshopValidationVerdict,
    WorkshopWaitIntent,
)
from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog


def plan_next(
    state: WorkshopState,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> WorkshopDecision:
    """Returns the single next logical action for one observed state.

    The decision order is the Plan 02 contract: terminal evidence first,
    then the survey/ranking facts every reservation depends on, ready
    submissions, useful free progress, full-board recovery, production, and
    finally bounded inspection or a typed stop. Nothing is scheduled ahead;
    the caller replans from the next observed state.
    """

    board = BoardFacts(state)
    chains = MergeChains(catalog)
    ctx = goal_context(state, board, chains, catalog, policy)

    # 1. Terminal observed evidence wins over every other consideration.
    if state.energy.is_zero:
        return _decision(
            ctx,
            WorkshopStopIntent(WorkshopStopReason.ZERO_ENERGY),
            "observed zero energy; no ready order or recycle overrides the stop",
        )
    if state.surface != WorkshopSurfaceKind.BOARD:
        if state.surface == WorkshopSurfaceKind.UNKNOWN:
            return _decision(
                ctx,
                WorkshopInspectIntent(WorkshopInspectKind.BOARD),
                "current surface is unread; re-observe before any board action",
            )
        return _decision(
            ctx,
            WorkshopStopIntent(WorkshopStopReason.EXCLUDED_SURFACE),
            f"surface {state.surface.value} admits no board actions",
        )
    if state.production_mode == WorkshopProductionMode.AUTO_FUSION:
        return _decision(
            ctx,
            WorkshopStopIntent(WorkshopStopReason.EXCLUDED_SURFACE),
            "automatic-fusion production surface is unsupported",
        )

    # 2. The order survey gates every reservation-bearing intent.
    survey = state.order_survey
    if not (
        survey.coverage == WorkshopSurveyCoverage.COMPLETE
        and survey.freshness == WorkshopSurveyFreshness.CURRENT
    ):
        return _decision(
            ctx,
            WorkshopInspectIntent(WorkshopInspectKind.ORDER_SURVEY),
            "order survey is not complete and current",
        )
    selection = ctx.selection
    if selection is not None and selection.inspect_order_ref is not None:
        ref = selection.inspect_order_ref
        return _decision(
            ctx,
            WorkshopInspectIntent(WorkshopInspectKind.ORDER_CONTENTS, order_ref=ref),
            f"inspect order {ref}: ranking needs reward facts the card did not read",
        )
    primary = selection.primary if selection is not None else None
    if primary is None:
        return _decision(
            ctx,
            WorkshopStopIntent(WorkshopStopReason.NO_ELIGIBLE_GOAL),
            selection.reason if selection is not None else "no order survey goals",
        )

    # 3. Submit the best ready goal whose stock is confirmed.
    uncertain_order: int | None = None
    for evaluation in selection.ranked:
        order = evaluation.assessment.order
        if order.ready is not True:
            continue
        intent = WorkshopSubmitOrderIntent(order.order_ref)
        verdict = validate_intent(state, intent, catalog, policy)
        if verdict.verdict == WorkshopValidationVerdict.LEGAL:
            note = "ready primary goal" if evaluation is primary else (
                "ready lower-ranked goal; primary reservations intact"
            )
            return _decision(ctx, intent, f"submit order {order.order_ref}: {note}")
        if verdict.verdict == WorkshopValidationVerdict.UNCERTAIN:
            uncertain_order = order.order_ref
            break
    if uncertain_order is not None:
        inspect = _cell_inspect(board)
        if inspect is not None:
            return _decision(
                ctx,
                inspect,
                f"submit order {uncertain_order} is unconfirmed; read the blocking cells",
            )
    for evaluation in selection.ranked:
        order = evaluation.assessment.order
        if order.ready is None and evaluation.satisfied:
            return _decision(
                ctx,
                WorkshopInspectIntent(
                    WorkshopInspectKind.ORDER_CONTENTS, order_ref=order.order_ref
                ),
                f"order {order.order_ref} is stock-satisfied; re-read its ready control",
            )

    # 4. Free progress toward the primary goal: merges, activations, feeds.
    progress = _best_progress(ctx, board, chains, catalog, policy)
    if progress is not None:
        intent, summary = progress
        return _decision(ctx, intent, summary)

    # 5. A confirmed-full board must free a cell before production.
    if board.board_full is True:
        recovery = _space_recovery(ctx, board, chains, catalog, policy)
        if recovery is not None:
            intent, summary = recovery
            return _decision(ctx, intent, summary)
        return _decision(
            ctx,
            WorkshopStopIntent(WorkshopStopReason.BOARD_BLOCKED),
            "board is confirmed full with no permitted merge, feed or recycle",
        )

    # 6. Production: the best on-board generator serving an open demand.
    blocked_on_cooldown = False
    if ctx.produce_targets or ctx.aux_targets:
        production = _production_step(
            state, ctx, board, chains, catalog, policy
        )
        if production is not None:
            intent, summary, cooldown_wait = production
            if intent is not None:
                return _decision(ctx, intent, summary)
            blocked_on_cooldown = cooldown_wait

    # 7. Bounded information acquisition while the primary is unfinished.
    if primary.allocation.missing_quantities or ctx.aux_targets:
        inspect = _cell_inspect(board)
        if inspect is not None:
            return _decision(
                ctx,
                inspect,
                "unread or unobserved cells may hold progress stock",
            )
    if state.energy.current is not None and (
        ctx.produce_targets or ctx.aux_targets
    ) and state.energy.current < catalog.activity.production_energy_cost:
        return _decision(
            ctx,
            WorkshopStopIntent(WorkshopStopReason.UNRESOLVED_STATE),
            "observed energy is below one production",
        )
    if blocked_on_cooldown:
        return _decision(
            ctx,
            WorkshopWaitIntent(policy.max_cooldown_wait_ms),
            f"every supported producer is cooling down; wait up to "
            f"{policy.max_cooldown_wait_ms} ms",
        )
    return _decision(
        ctx,
        WorkshopStopIntent(WorkshopStopReason.UNRESOLVED_STATE),
        "no supported merge, feed, production, inspection or wait remains",
    )


def _decision(ctx: GoalContext, intent: WorkshopIntent, summary: str) -> WorkshopDecision:
    """Packages one intent with the primary goal's diagnostics."""

    primary = ctx.selection.primary if ctx.selection is not None else None
    if primary is None:
        return WorkshopDecision(intent=intent, reason=summary)
    assessment = primary.assessment
    effort = primary.effort
    energy = "none" if effort.energy is None else str(effort.energy)
    flags = [flag for flag, on in (
        ("uncertain", effort.uncertain),
        ("conservative", effort.conservative),
    ) if on]
    estimate = f"est {energy} production energy"
    if flags:
        estimate += f" ({', '.join(flags)})"
    missing = dict(primary.allocation.missing_quantities)
    protected = dict(primary.allocation.protected_quantities)
    reason = (
        f"{summary} — goal order {primary.order_ref} "
        f"({assessment.category.value} x{assessment.primary_quantity}): "
        f"missing {missing or '{}'}, protected {protected or '{}'}, {estimate}"
    )
    return WorkshopDecision(
        intent=intent,
        reason=reason,
        goal_order_ref=primary.order_ref,
        missing_quantities=missing,
        protected_quantities=protected,
    )


def _cell_inspect(board: BoardFacts) -> WorkshopInspectIntent | None:
    """Returns the most relevant board-level inspection, if any is needed.

    Covers every cell-level unknown the board view tracks: unread piece
    identity, unread access/occupancy (the cells that leave ``board_full``
    undetermined), and positions with no observation at all.
    """

    if board.unread_piece_cells:
        return WorkshopInspectIntent(
            WorkshopInspectKind.CELL_STATE, cell_id=min(board.unread_piece_cells)
        )
    if board.unknown_state_cells:
        return WorkshopInspectIntent(
            WorkshopInspectKind.CELL_STATE, cell_id=min(board.unknown_state_cells)
        )
    if board.unobserved_cell_ids:
        return WorkshopInspectIntent(WorkshopInspectKind.BOARD)
    return None


def _progress_gap(
    ctx: GoalContext,
    chains: MergeChains,
    successor: int,
) -> tuple[int, int] | None:
    """Scores a merge/activation result against the primary's open targets.

    The score is (phase, tier gap): phase 0 fills an unmet demand directly;
    phase 1 builds a needed producer or a still-missing feed ingredient.
    ``None`` means the result serves no current target.
    """

    gaps = [
        chains.tier(target) - chains.tier(successor)
        for target in ctx.demand_targets
        if successor in chains.closure(target)
    ]
    if gaps:
        return (0, min(gaps))
    gaps = [
        chains.tier(target) - chains.tier(successor)
        for target in ctx.needed_producers | ctx.aux_targets
        if successor in chains.closure(target)
    ]
    if gaps:
        return (1, min(gaps))
    return None


def _best_progress(
    ctx: GoalContext,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> tuple[WorkshopIntent, str] | None:
    """Chooses the free action nearest a missing primary-goal target.

    Candidates are merges, supported activations and exact feeds whose
    result serves an unmet demand, a needed producer or a missing feed
    ingredient. Ordering is (phase, tier gap, source cell, target cell) —
    every candidate frees exactly one cell, so cell ids are the stable
    tie-break.
    """

    primary = ctx.selection.primary
    feedable = {
        demand.item_id
        for demand in primary.allocation.demands
        if demand.feedable_exact > 0
    }
    candidates: list[tuple[tuple[int, int, int, int], WorkshopIntent, str]] = []
    for item_id in board.normal_items:
        cells = board.normal_cells(item_id)
        if len(cells) < 2:
            continue
        successor = chains.successor(item_id)
        if successor is None:
            continue
        gap = _progress_gap(ctx, chains, successor)
        if gap is None:
            continue
        if merge_reservation_verdict(ctx, board, chains, item_id) is not None:
            continue
        intent = WorkshopMergeIntent(cells[0], cells[1], item_id)
        candidates.append(
            ((*gap, cells[0], cells[1]), intent, f"merge item {item_id} toward {successor}")
        )
    for item_id in board.inactive_items:
        normal = board.normal_cells(item_id)
        if not normal:
            continue
        successor = chains.successor(item_id)
        if successor is None:
            continue
        gap = _progress_gap(ctx, chains, successor)
        if gap is None:
            continue
        if activate_reservation_verdict(ctx, board, chains, item_id) is not None:
            continue
        inactive = board.inactive_cells(item_id)
        intent = WorkshopActivateIntent(normal[0], inactive[0], item_id)
        candidates.append(
            (
                (*gap, normal[0], inactive[0]),
                intent,
                f"activate inactive {item_id} into {successor}",
            )
        )
    for item_id in board.feed_locked_items:
        producer = catalog.producer_for(item_id)
        if producer is None or producer.feed_item_id is None:
            continue
        food = producer.feed_item_id
        food_cells = board.normal_cells(food)
        if not food_cells:
            continue
        if item_id in feedable:
            gap = (0, 0)
            why = f"feed {food} to demanded piece {item_id}"
        elif item_id in ctx.needed_producers:
            gap = (1, 0)
            why = f"feed {food} to producer {item_id} serving the goal"
        else:
            continue
        if feed_reservation_verdict(ctx, board, chains, item_id, food) is not None:
            continue
        locked_cell = board.feed_locked_cells(item_id)[0]
        intent = WorkshopFeedIntent(food_cells[0], locked_cell, food)
        candidates.append(((*gap, food_cells[0], locked_cell), intent, why))
    for _, intent, summary in sorted(candidates, key=lambda entry: entry[0]):
        if validate_intent(board.state, intent, catalog, policy).verdict == WorkshopValidationVerdict.LEGAL:
            return intent, summary
    return None


def _space_recovery(
    ctx: GoalContext,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> tuple[WorkshopIntent, str] | None:
    """Chooses one permitted space-freeing action on a confirmed-full board.

    Any reservation-legal merge, activation or feed outranks recycling; only
    then may one unreserved allowlisted terminal piece be recycled, least
    useful first.
    """

    candidates: list[tuple[tuple[int, int, int], WorkshopIntent, str]] = []
    for item_id in board.normal_items:
        cells = board.normal_cells(item_id)
        if len(cells) < 2 or chains.successor(item_id) is None:
            continue
        if merge_reservation_verdict(ctx, board, chains, item_id) is not None:
            continue
        candidates.append(
            (
                (0, cells[0], cells[1]),
                WorkshopMergeIntent(cells[0], cells[1], item_id),
                f"merge item {item_id} to free a cell",
            )
        )
    for item_id in board.inactive_items:
        normal = board.normal_cells(item_id)
        if not normal or chains.successor(item_id) is None:
            continue
        if activate_reservation_verdict(ctx, board, chains, item_id) is not None:
            continue
        inactive = board.inactive_cells(item_id)
        candidates.append(
            (
                (1, normal[0], inactive[0]),
                WorkshopActivateIntent(normal[0], inactive[0], item_id),
                f"activate inactive {item_id} to free a cell",
            )
        )
    for item_id in board.feed_locked_items:
        producer = catalog.producer_for(item_id)
        if producer is None or producer.feed_item_id is None:
            continue
        food_cells = board.normal_cells(producer.feed_item_id)
        if not food_cells:
            continue
        if feed_reservation_verdict(
            ctx, board, chains, item_id, producer.feed_item_id
        ) is not None:
            continue
        locked_cell = board.feed_locked_cells(item_id)[0]
        candidates.append(
            (
                (2, food_cells[0], locked_cell),
                WorkshopFeedIntent(food_cells[0], locked_cell, producer.feed_item_id),
                f"feed producer {item_id} to free a cell",
            )
        )
    for _, intent, summary in sorted(candidates, key=lambda entry: entry[0]):
        if validate_intent(board.state, intent, catalog, policy).verdict == WorkshopValidationVerdict.LEGAL:
            return intent, summary
    recyclable: list[tuple[tuple[int, int, int], int]] = []
    ranked = ctx.selection.ranked if ctx.selection is not None else ()
    for item_id in policy.recyclable_item_ids:
        cells = board.normal_cells(item_id)
        if not cells or not chains.is_terminal(item_id):
            continue
        if len(cells) - 1 < ctx.protected.get(item_id, 0):
            continue
        usefulness = sum(
            item_id in evaluation.assessment.order.requirements
            for evaluation in ranked
        )
        for cell_id in cells:
            recyclable.append(((usefulness, item_id, cell_id), cell_id))
    for _, cell_id in sorted(recyclable, key=lambda entry: entry[0]):
        piece = board.cell(cell_id)
        intent = WorkshopRecycleIntent(cell_id, piece.item_id)
        if validate_intent(board.state, intent, catalog, policy).verdict == WorkshopValidationVerdict.LEGAL:
            return intent, f"recycle unreserved allowlisted piece {piece.item_id} on cell {cell_id}"
    return None


def _production_step(
    state: WorkshopState,
    ctx: GoalContext,
    board: BoardFacts,
    chains: MergeChains,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> tuple[WorkshopIntent | None, str, bool] | None:
    """Chooses the production action, or reports what blocks it.

    Scores every on-board Normal producer by expected useful base units per
    draw across the primary's residual demands and missing feed ingredients.
    Returns ``(intent, summary, cooldown_blocked)``: a Select/Produce when a
    generator is known-clear, an Inspect when the best producer's cooldown
    was never read, ``(None, ..., True)`` when all candidates are cooling
    down, and ``None`` when no on-board producer serves the goal.
    """

    cost = catalog.activity.production_energy_cost
    targets = ctx.produce_targets | ctx.aux_targets
    scored: list[tuple[Fraction, int, int, WorkshopCooldown]] = []
    for producer in catalog.producers:
        useful = sum(
            useful_units_per_draw(producer, target, chains, catalog)
            for target in targets
        )
        if useful <= 0:
            continue
        for cell_id in board.normal_cells(producer.item_id):
            cell = board.cell(cell_id)
            cooldown = cell.cooldown if cell is not None else WorkshopCooldown.UNKNOWN
            scored.append((useful, producer.item_id, cell_id, cooldown))
    if not scored:
        return None
    key = lambda entry: (-entry[0], entry[1], entry[2])
    clear = [entry for entry in scored if entry[3] == WorkshopCooldown.CLEAR]
    unread = [entry for entry in scored if entry[3] == WorkshopCooldown.UNKNOWN]
    cooling = [entry for entry in scored if entry[3] == WorkshopCooldown.ACTIVE]
    if not clear:
        if unread:
            _, item_id, cell_id, _ = min(unread, key=key)
            return (
                WorkshopInspectIntent(WorkshopInspectKind.CELL_STATE, cell_id=cell_id),
                f"cooldown on producer {item_id} cell {cell_id} is unread",
                False,
            )
        if cooling:
            _, item_id, cell_id, _ = min(cooling, key=key)
            return (
                None,
                f"producer {item_id} on cell {cell_id} is cooling down",
                True,
            )
        return None
    useful, item_id, cell_id, _ = min(clear, key=key)
    label = f"producer {item_id} on cell {cell_id} ({useful} useful units/draw)"
    if state.energy.current is None:
        return (
            WorkshopInspectIntent(WorkshopInspectKind.BOARD),
            f"energy is unread; {label} cannot be confirmed affordable",
            False,
        )
    if state.energy.current < cost:
        return (None, f"energy {state.energy.current} below cost {cost}", False)
    if board.board_full is None:
        inspect = _cell_inspect(board)
        if inspect is not None:
            return inspect, "usable free space for production is unconfirmed", False
    if state.production_mode == WorkshopProductionMode.UNKNOWN:
        return (
            WorkshopInspectIntent(WorkshopInspectKind.BOARD),
            f"production mode is unread; {label} cannot be produced from yet",
            False,
        )
    if state.selection.kind == WorkshopSelectionKind.UNKNOWN:
        return (
            WorkshopInspectIntent(WorkshopInspectKind.BOARD),
            "board selection state is unread",
            False,
        )
    if state.selection.kind != WorkshopSelectionKind.SELECTED or (
        state.selection.cell_id != cell_id
    ):
        intent = WorkshopSelectIntent(cell_id)
        summary = f"select {label} before producing"
    else:
        intent = WorkshopProduceIntent(cell_id, item_id)
        summary = f"produce once from {label}"
    verdict = validate_intent(state, intent, catalog, policy)
    if verdict.verdict == WorkshopValidationVerdict.LEGAL:
        return intent, summary, False
    if verdict.verdict == WorkshopValidationVerdict.UNCERTAIN:
        return WorkshopInspectIntent(WorkshopInspectKind.BOARD), verdict.reason, False
    return None
