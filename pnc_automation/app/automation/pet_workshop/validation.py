"""Canonical ``validate_intent`` — the single legal-action check (Plan 02 PW03).

One implementation serves the planner's self-check, later screenshot-time
revalidation and the future executor's fresh-state revalidation. Every
verdict reads only the typed state, the packaged catalog and the policy:
``LEGAL`` only when every fact the intent depends on was observed and
permits it, ``ILLEGAL`` on a known-fact prohibition, ``UNCERTAIN`` when a
required fact was never observed. Unknowns are never treated as permission.
"""

from __future__ import annotations

from pnc_automation.app.automation.pet_workshop.board import BoardFacts, MergeChains
from pnc_automation.app.automation.pet_workshop.policy import assess_order
from pnc_automation.app.automation.pet_workshop.rules import (
    GoalContext,
    activate_reservation_verdict,
    feed_reservation_verdict,
    goal_context,
    merge_reservation_verdict,
    recycle_is_blocked,
    submit_reservation_verdict,
)
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopActivateIntent,
    WorkshopCell,
    WorkshopCellAccess,
    WorkshopCooldown,
    WorkshopFeedIntent,
    WorkshopInspectIntent,
    WorkshopInspectKind,
    WorkshopIntent,
    WorkshopItemStatus,
    WorkshopMergeIntent,
    WorkshopOccupancy,
    WorkshopPolicy,
    WorkshopProduceIntent,
    WorkshopProductionMode,
    WorkshopRecycleIntent,
    WorkshopSelectIntent,
    WorkshopSelectionKind,
    WorkshopState,
    WorkshopStopIntent,
    WorkshopSubmitOrderIntent,
    WorkshopSurfaceKind,
    WorkshopValidationVerdict,
    WorkshopIntentValidation,
    WorkshopWaitIntent,
)
from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog

_OK = WorkshopIntentValidation(WorkshopValidationVerdict.LEGAL)


def _illegal(reason: str) -> WorkshopIntentValidation:
    """Returns an ILLEGAL verdict with one reason."""

    return WorkshopIntentValidation(WorkshopValidationVerdict.ILLEGAL, reason)


def _uncertain(reason: str) -> WorkshopIntentValidation:
    """Returns an UNCERTAIN verdict with one reason."""

    return WorkshopIntentValidation(WorkshopValidationVerdict.UNCERTAIN, reason)


def _surface_verdict(state: WorkshopState) -> WorkshopIntentValidation | None:
    """Board-surface gate shared by every mutation intent."""

    if state.surface == WorkshopSurfaceKind.BOARD:
        return None
    if state.surface == WorkshopSurfaceKind.UNKNOWN:
        return _uncertain("current surface is unread")
    return _illegal(f"surface is {state.surface.value}, not the board")


def _mutation_verdict(state: WorkshopState) -> WorkshopIntentValidation | None:
    """Surface, energy and production-mode gates for board mutations."""

    verdict = _surface_verdict(state)
    if verdict is not None:
        return verdict
    if state.energy.is_zero:
        return _illegal("zero energy observed; the planner must stop")
    return None


def _piece_verdict(
    state: WorkshopState,
    board: BoardFacts,
    cell_id: int,
    expected_item: int | None = None,
) -> WorkshopIntentValidation | WorkshopCell:
    """Checks one cell is observed, usable, occupied and (optionally) matches."""

    if not state.board.contains_cell_id(cell_id):
        return _illegal(f"cell {cell_id} is outside the board")
    cell = board.cell(cell_id)
    if cell is None:
        return _uncertain(f"cell {cell_id} was not observed")
    if cell.access == WorkshopCellAccess.LOCKED:
        return _illegal(f"cell {cell_id} is level-locked")
    if cell.access == WorkshopCellAccess.UNKNOWN:
        return _uncertain(f"cell {cell_id} access is unread")
    if cell.occupancy == WorkshopOccupancy.EMPTY:
        return _illegal(f"cell {cell_id} is empty")
    if cell.occupancy == WorkshopOccupancy.UNKNOWN:
        return _uncertain(f"cell {cell_id} occupancy is unread")
    if cell.item_id is None:
        return _uncertain(f"piece on cell {cell_id} is unidentified")
    if expected_item is not None and cell.item_id != expected_item:
        return _illegal(
            f"cell {cell_id} holds item {cell.item_id}, not expected {expected_item}"
        )
    if cell.item_status is None:
        return _uncertain(f"piece status on cell {cell_id} is unread")
    return cell


def _validate_select(state: WorkshopState, board: BoardFacts, intent: WorkshopSelectIntent) -> WorkshopIntentValidation:
    verdict = _mutation_verdict(state)
    if verdict is not None:
        return verdict
    piece = _piece_verdict(state, board, intent.cell_id)
    if not isinstance(piece, WorkshopCell):
        return piece
    if piece.item_status == WorkshopItemStatus.UNKNOWN:
        return _uncertain(f"piece status on cell {intent.cell_id} is unread")
    selection = state.selection
    if selection.kind == WorkshopSelectionKind.SELECTED and selection.cell_id == intent.cell_id:
        return _illegal(f"cell {intent.cell_id} is already selected")
    if selection.kind == WorkshopSelectionKind.UNKNOWN:
        return _uncertain("board selection state is unread")
    return _OK


def _validate_produce(
    state: WorkshopState,
    board: BoardFacts,
    catalog: PetWorkshopCatalog,
    intent: WorkshopProduceIntent,
) -> WorkshopIntentValidation:
    verdict = _mutation_verdict(state)
    if verdict is not None:
        return verdict
    piece = _piece_verdict(state, board, intent.cell_id, intent.producer_item_id)
    if not isinstance(piece, WorkshopCell):
        return piece
    if piece.item_status != WorkshopItemStatus.NORMAL:
        if piece.item_status == WorkshopItemStatus.UNKNOWN:
            return _uncertain(f"piece status on cell {intent.cell_id} is unread")
        return _illegal(
            f"piece on cell {intent.cell_id} is {piece.item_status.value}, not producible"
        )
    producer = catalog.producer_for(intent.producer_item_id)
    if producer is None:
        return _illegal(f"item {intent.producer_item_id} is not a producer")
    if state.production_mode == WorkshopProductionMode.UNKNOWN:
        return _uncertain("production mode is unread")
    if state.production_mode == WorkshopProductionMode.AUTO_FUSION:
        return _illegal("automatic fusion is unsupported; production mode is wrong")
    if piece.cooldown == WorkshopCooldown.ACTIVE:
        return _illegal(f"producer on cell {intent.cell_id} is cooling down")
    if piece.cooldown == WorkshopCooldown.UNKNOWN:
        return _uncertain(f"cooldown on cell {intent.cell_id} is unread")
    selection = state.selection
    if selection.kind == WorkshopSelectionKind.UNKNOWN:
        return _uncertain("board selection state is unread")
    if selection.kind != WorkshopSelectionKind.SELECTED or selection.cell_id != intent.cell_id:
        return _illegal(f"producer on cell {intent.cell_id} is not selected")
    if state.energy.current is None:
        return _uncertain("energy reading is unknown")
    if state.energy.current < catalog.activity.production_energy_cost:
        return _illegal("insufficient observed energy for one production")
    if board.usable_empty_cells:
        return _OK
    if board.board_full is True:
        return _illegal("board is confirmed full; production needs a free cell")
    return _uncertain("usable free space is unconfirmed")


def _validate_merge(
    state: WorkshopState,
    board: BoardFacts,
    chains: MergeChains,
    ctx: GoalContext,
    intent: WorkshopMergeIntent,
) -> WorkshopIntentValidation:
    verdict = _mutation_verdict(state)
    if verdict is not None:
        return verdict
    for cell_id in (intent.source_cell_id, intent.target_cell_id):
        piece = _piece_verdict(state, board, cell_id, intent.item_id)
        if not isinstance(piece, WorkshopCell):
            return piece
        if piece.item_status != WorkshopItemStatus.NORMAL:
            if piece.item_status == WorkshopItemStatus.UNKNOWN:
                return _uncertain(f"piece status on cell {cell_id} is unread")
            return _illegal(
                f"piece on cell {cell_id} is {piece.item_status.value}; "
                "merge needs two Normal pieces"
            )
    if chains.successor(intent.item_id) is None:
        return _illegal(f"item {intent.item_id} has no merge successor")
    if not ctx.known:
        return _uncertain("goal context is unresolved")
    reason = merge_reservation_verdict(ctx, board, chains, intent.item_id)
    if reason is not None:
        return _illegal(reason)
    return _OK


def _validate_activate(
    state: WorkshopState,
    board: BoardFacts,
    chains: MergeChains,
    ctx: GoalContext,
    intent: WorkshopActivateIntent,
) -> WorkshopIntentValidation:
    verdict = _mutation_verdict(state)
    if verdict is not None:
        return verdict
    source = _piece_verdict(state, board, intent.source_cell_id, intent.item_id)
    if not isinstance(source, WorkshopCell):
        return source
    if source.item_status != WorkshopItemStatus.NORMAL:
        if source.item_status == WorkshopItemStatus.UNKNOWN:
            return _uncertain("activation source status is unread")
        return _illegal("activation source must be a Normal piece")
    target = _piece_verdict(state, board, intent.target_cell_id, intent.item_id)
    if not isinstance(target, WorkshopCell):
        return target
    if target.item_status != WorkshopItemStatus.INACTIVE:
        if target.item_status == WorkshopItemStatus.UNKNOWN:
            return _uncertain("activation target status is unread")
        return _illegal(
            f"activation target is {target.item_status.value}, not Inactive"
        )
    successor = chains.successor(intent.item_id)
    if successor is None:
        return _illegal(f"item {intent.item_id} has no merge successor to activate into")
    if not ctx.known:
        return _uncertain("goal context is unresolved")
    if board.board_full is not True and not any(
        successor in chains.closure(target_item) for target_item in ctx.all_targets
    ):
        return _illegal(
            f"activating item {intent.item_id} serves no goal, producer or space need"
        )
    reason = activate_reservation_verdict(ctx, board, chains, intent.item_id)
    return _illegal(reason) if reason else _OK


def _validate_feed(
    state: WorkshopState,
    board: BoardFacts,
    chains: MergeChains,
    ctx: GoalContext,
    catalog: PetWorkshopCatalog,
    intent: WorkshopFeedIntent,
) -> WorkshopIntentValidation:
    verdict = _mutation_verdict(state)
    if verdict is not None:
        return verdict
    producer_piece = _piece_verdict(state, board, intent.producer_cell_id)
    if not isinstance(producer_piece, WorkshopCell):
        return producer_piece
    producer = catalog.producer_for(producer_piece.item_id)
    if producer is None:
        return _illegal(f"item {producer_piece.item_id} is not a producer")
    if producer.feed_item_id is None:
        return _illegal(f"producer {producer.item_id} has no feed recipe")
    if producer.feed_item_id != intent.food_item_id:
        return _illegal(
            f"producer {producer.item_id} requires food {producer.feed_item_id}, "
            f"not {intent.food_item_id}"
        )
    if producer_piece.item_status != WorkshopItemStatus.FEED_LOCKED:
        if producer_piece.item_status == WorkshopItemStatus.UNKNOWN:
            return _uncertain("feed target status is unread")
        return _illegal(
            f"producer on cell {intent.producer_cell_id} is "
            f"{producer_piece.item_status.value}, not feed-locked"
        )
    food = _piece_verdict(state, board, intent.food_cell_id, intent.food_item_id)
    if not isinstance(food, WorkshopCell):
        return food
    if food.item_status != WorkshopItemStatus.NORMAL:
        if food.item_status == WorkshopItemStatus.UNKNOWN:
            return _uncertain("food piece status is unread")
        return _illegal("the feed ingredient must be a Normal piece")
    if not ctx.known:
        return _uncertain("goal context is unresolved")
    reason = feed_reservation_verdict(
        ctx, board, chains, producer.item_id, intent.food_item_id
    )
    return _illegal(reason) if reason else _OK


def _validate_recycle(
    state: WorkshopState,
    board: BoardFacts,
    chains: MergeChains,
    ctx: GoalContext,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
    intent: WorkshopRecycleIntent,
) -> WorkshopIntentValidation:
    verdict = _mutation_verdict(state)
    if verdict is not None:
        return verdict
    piece = _piece_verdict(state, board, intent.cell_id, intent.item_id)
    if not isinstance(piece, WorkshopCell):
        return piece
    if piece.item_status != WorkshopItemStatus.NORMAL:
        if piece.item_status == WorkshopItemStatus.UNKNOWN:
            return _uncertain(f"piece status on cell {intent.cell_id} is unread")
        return _illegal(
            f"piece on cell {intent.cell_id} is {piece.item_status.value}, not recyclable"
        )
    if intent.item_id not in policy.recyclable_item_ids:
        return _illegal(f"item {intent.item_id} is not in the recycling allowlist")
    if not chains.is_terminal(intent.item_id):
        return _illegal(f"item {intent.item_id} still has a merge successor")
    if board.board_full is not True:
        if board.board_full is None:
            return _uncertain("board fullness is unconfirmed")
        return _illegal("recycling is permitted only on a confirmed-full board")
    if board.normal_count(intent.item_id) - 1 < ctx.protected.get(intent.item_id, 0):
        return _illegal(f"piece {intent.item_id} is reserved for the primary goal")
    if not ctx.known:
        return _uncertain("goal context is unresolved")
    reason = recycle_is_blocked(ctx, board, chains, catalog, policy)
    return _illegal(reason) if reason else _OK


def _validate_submit(
    state: WorkshopState,
    board: BoardFacts,
    ctx: GoalContext,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
    intent: WorkshopSubmitOrderIntent,
) -> WorkshopIntentValidation:
    verdict = _mutation_verdict(state)
    if verdict is not None:
        return verdict
    if not ctx.known:
        return _uncertain("goal context is unresolved")
    order = state.order_survey.order(intent.order_ref)
    if order is None:
        return _illegal(f"order {intent.order_ref} is not in the current survey")
    survey_index = next(
        index
        for index, surveyed in enumerate(state.order_survey.orders)
        if surveyed.order_ref == intent.order_ref
    )
    assessment = assess_order(order, survey_index, catalog, policy)
    if not assessment.eligible:
        return _illegal(f"order {intent.order_ref} is ineligible: {assessment.ineligible_reason}")
    if not assessment.is_goal:
        return _illegal(f"order {intent.order_ref} is not a policy goal")
    if order.ready is None:
        return _uncertain(f"order {intent.order_ref} readiness was not observed")
    if order.ready is False:
        return _illegal(f"order {intent.order_ref} shows no ready control")
    unobserved = board.unobserved_cell_ids or board.unread_piece_cells
    for item_id, quantity in order.requirements.items():
        if board.normal_count(item_id) < quantity:
            if unobserved:
                return _uncertain(
                    f"observed stock of item {item_id} is short and some cells are unread"
                )
            return _illegal(
                f"order {intent.order_ref} requires {quantity} of item {item_id}; "
                f"only {board.normal_count(item_id)} usable"
            )
    reason = submit_reservation_verdict(ctx, board, intent.order_ref)
    return _illegal(reason) if reason else _OK


def _validate_inspect(state: WorkshopState, intent: WorkshopInspectIntent) -> WorkshopIntentValidation:
    if intent.need == WorkshopInspectKind.ORDER_CONTENTS:
        if state.order_survey.order(intent.order_ref) is None:
            return _illegal(f"order {intent.order_ref} is not in the current survey")
        return _OK
    if intent.need == WorkshopInspectKind.CELL_STATE:
        if not state.board.contains_cell_id(intent.cell_id):
            return _illegal(f"cell {intent.cell_id} is outside the board")
        return _OK
    return _OK


def _validate_wait(policy: WorkshopPolicy, intent: WorkshopWaitIntent) -> WorkshopIntentValidation:
    if intent.max_wait_ms > policy.max_cooldown_wait_ms:
        return _illegal(
            f"wait bound {intent.max_wait_ms} exceeds policy {policy.max_cooldown_wait_ms}"
        )
    return _OK


def validate_intent(
    state: WorkshopState,
    intent: WorkshopIntent,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> WorkshopIntentValidation:
    """Checks one intent against the observed state, catalog and policy.

    The single canonical legality check: relevant known item/status/selection,
    recipe and feed identity, quantity reservations, order eligibility and
    readiness, energy, space, restricted recycling and surface gates — the
    same predicates the planner uses and the executor revalidates verbatim.
    """

    if isinstance(intent, (WorkshopInspectIntent,)):
        return _validate_inspect(state, intent)
    if isinstance(intent, WorkshopWaitIntent):
        return _validate_wait(policy, intent)
    if isinstance(intent, WorkshopStopIntent):
        return _OK
    board = BoardFacts(state)
    chains = MergeChains(catalog)
    ctx = goal_context(state, board, chains, catalog, policy)
    if isinstance(intent, WorkshopSelectIntent):
        return _validate_select(state, board, intent)
    if isinstance(intent, WorkshopProduceIntent):
        return _validate_produce(state, board, catalog, intent)
    if isinstance(intent, WorkshopMergeIntent):
        return _validate_merge(state, board, chains, ctx, intent)
    if isinstance(intent, WorkshopActivateIntent):
        return _validate_activate(state, board, chains, ctx, intent)
    if isinstance(intent, WorkshopFeedIntent):
        return _validate_feed(state, board, chains, ctx, catalog, intent)
    if isinstance(intent, WorkshopRecycleIntent):
        return _validate_recycle(state, board, chains, ctx, catalog, policy, intent)
    if isinstance(intent, WorkshopSubmitOrderIntent):
        return _validate_submit(state, board, ctx, catalog, policy, intent)
    return _illegal(f"unrecognized intent {intent!r}")
