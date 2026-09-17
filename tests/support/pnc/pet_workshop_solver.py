"""Test-only scenario driver for the pure Pet Workshop solver.

Every helper here mutates a synthetic ``WorkshopState`` the way an authored
outcome would — a merge consumes its two cells, a production fills one empty
cell, a feed unlocks its producer — and returns a *new* immutable state for
the next ``plan_next`` call. These transitions are scripted test data, not a
game simulator: they exist so tests can prove the planner replans from the
state it is actually given instead of replaying a queued script.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Iterable

from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopActivateIntent,
    WorkshopCell,
    WorkshopCooldown,
    WorkshopDecision,
    WorkshopFeedIntent,
    WorkshopItemStatus,
    WorkshopMergeIntent,
    WorkshopOccupancy,
    WorkshopOrder,
    WorkshopOrderSurvey,
    WorkshopPolicy,
    WorkshopSelection,
    WorkshopSelectionKind,
    WorkshopState,
    WorkshopStopIntent,
    WorkshopSubmitOrderIntent,
    WorkshopSurveyCoverage,
    WorkshopSurveyFreshness,
    WorkshopValidationVerdict,
)
from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog
from tests.support.pnc import pet_workshop as fx

Transition = Callable[[WorkshopState, WorkshopDecision], "WorkshopState | None"]


def observed_state(
    *cells: WorkshopCell,
    orders: Iterable[WorkshopOrder] = (),
    survey: WorkshopOrderSurvey | None = None,
    **state_kwargs,
) -> WorkshopState:
    """A fully observed board: the authored cells plus known-empty padding.

    Tests that need the planner to reach production/stop branches must not
    leave unobserved cells, so every board position not in ``cells`` is added
    as a usable, observed, empty cell.
    """

    taken = {cell.cell_id for cell in cells}
    board = fx.board_layout()
    padding = tuple(
        fx.make_cell(
            row, column, occupancy=WorkshopOccupancy.EMPTY, item_status=None
        )
        for row in range(1, board.rows + 1)
        for column in range(1, board.columns + 1)
        if board.cell_id(row, column) not in taken
    )
    return fx.make_state(
        cells=tuple(cells) + padding,
        order_survey=(
            survey
            if survey is not None
            else WorkshopOrderSurvey(
                orders=tuple(orders),
                coverage=WorkshopSurveyCoverage.COMPLETE,
                freshness=WorkshopSurveyFreshness.CURRENT,
            )
        ),
        **state_kwargs,
    )


def update_state(state: WorkshopState, **changes) -> WorkshopState:
    """Returns a copy of ``state`` with the named fields replaced."""

    return replace(state, **changes)


def set_cell(state: WorkshopState, cell_id: int, **changes) -> WorkshopState:
    """Replaces one observed cell's fields and returns the new state."""

    cells = tuple(
        replace(cell, **changes) if cell.cell_id == cell_id else cell
        for cell in state.cells
    )
    return replace(state, cells=cells)


def clear_cells(state: WorkshopState, *cell_ids: int) -> WorkshopState:
    """Empties the given cells — pieces consumed or moved off the board."""

    emptied = set(cell_ids)
    cells = tuple(
        replace(
            cell,
            occupancy=WorkshopOccupancy.EMPTY,
            item_id=None,
            item_status=None,
            cooldown=WorkshopCooldown.CLEAR,
        )
        if cell.cell_id in emptied
        else cell
        for cell in state.cells
    )
    return replace(state, cells=cells)


def place_item(
    state: WorkshopState,
    cell_id: int,
    item_id: int,
    *,
    status: WorkshopItemStatus = WorkshopItemStatus.NORMAL,
    cooldown: WorkshopCooldown = WorkshopCooldown.CLEAR,
) -> WorkshopState:
    """Puts one piece onto a cell — a produced drop or an authored grant."""

    return set_cell(
        state,
        cell_id,
        occupancy=WorkshopOccupancy.OCCUPIED,
        item_id=item_id,
        item_status=status,
        cooldown=cooldown,
    )


def set_selection(state: WorkshopState, cell_id: int) -> WorkshopState:
    """Marks one cell selected, as a successful select outcome would."""

    return replace(
        state,
        selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=cell_id),
    )


def apply_merge(
    state: WorkshopState,
    intent: WorkshopMergeIntent,
    catalog: PetWorkshopCatalog,
) -> WorkshopState:
    """Applies a merge outcome: both pieces leave; the successor lands on the target."""

    successor = catalog.item(intent.item_id).merge_successor_id
    state = clear_cells(state, intent.source_cell_id, intent.target_cell_id)
    return place_item(state, intent.target_cell_id, successor)


def apply_activate(
    state: WorkshopState,
    intent: WorkshopActivateIntent,
    catalog: PetWorkshopCatalog,
) -> WorkshopState:
    """Applies an activation outcome — identical shape to a merge."""

    successor = catalog.item(intent.item_id).merge_successor_id
    state = clear_cells(state, intent.source_cell_id, intent.target_cell_id)
    return place_item(state, intent.target_cell_id, successor)


def apply_feed(state: WorkshopState, intent: WorkshopFeedIntent) -> WorkshopState:
    """Applies a feed outcome: the food leaves, the producer becomes Normal."""

    state = clear_cells(state, intent.food_cell_id)
    return set_cell(
        state,
        intent.producer_cell_id,
        item_status=WorkshopItemStatus.NORMAL,
        cooldown=WorkshopCooldown.CLEAR,
    )


def apply_submit(state: WorkshopState, intent: WorkshopSubmitOrderIntent) -> WorkshopState:
    """Applies a submit outcome: required pieces leave by quantity, order is gone.

    Consumption is quantity-based — any observed Normal copies of each
    required item leave, matching the reservation semantics that protect
    quantities rather than selected cell identities.
    """

    order = state.order_survey.order(intent.order_ref)
    consume: dict[int, int] = dict(order.requirements)
    cells = []
    for cell in state.cells:
        if (
            cell.occupancy == WorkshopOccupancy.OCCUPIED
            and cell.item_status == WorkshopItemStatus.NORMAL
            and consume.get(cell.item_id, 0) > 0
        ):
            consume[cell.item_id] -= 1
            cell = replace(
                cell,
                occupancy=WorkshopOccupancy.EMPTY,
                item_id=None,
                item_status=None,
                cooldown=WorkshopCooldown.CLEAR,
            )
        cells.append(cell)
    survey = state.order_survey
    orders = tuple(o for o in survey.orders if o.order_ref != intent.order_ref)
    return replace(state, cells=tuple(cells), order_survey=replace(survey, orders=orders))


def first_empty_cell(state: WorkshopState) -> int:
    """Returns the first usable empty cell id for an authored drop landing."""

    for cell in state.cells:
        if cell.occupancy == WorkshopOccupancy.EMPTY and cell.item_id is None:
            return cell.cell_id
    raise AssertionError("authored scenario has no empty cell for the drop")


def run_scenario(
    initial: WorkshopState,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
    transition: Transition,
    *,
    max_steps: int = 12,
) -> list[WorkshopDecision]:
    """Replans through authored outcomes until a Stop or a terminal transition.

    ``transition(state, decision)`` returns the next observed state, or
    ``None`` when the authored sequence ends on a non-stop intent. Every step
    calls ``plan_next`` on the current state only — the same replanning loop
    the runtime lane will use.
    """

    from pnc_automation.app.automation.pet_workshop import plan_next
    from pnc_automation.app.automation.pet_workshop.validation import validate_intent

    decisions: list[WorkshopDecision] = []
    state = initial
    for _ in range(max_steps):
        decision = plan_next(state, catalog, policy)
        decisions.append(decision)
        # Every proposed intent must pass the canonical validator on the
        # state that produced it — the same contract the executor reuses.
        verdict = validate_intent(state, decision.intent, catalog, policy)
        if verdict.verdict != WorkshopValidationVerdict.LEGAL:
            raise AssertionError(
                f"step {len(decisions)}: {decision.intent!r} failed canonical "
                f"validation as {verdict.verdict.value} ({verdict.reason})"
            )
        if isinstance(decision.intent, WorkshopStopIntent):
            return decisions
        next_state = transition(state, decision)
        if next_state is None:
            return decisions
        state = next_state
    raise AssertionError(
        f"scenario did not stop within {max_steps} steps: "
        + ", ".join(d.intent.kind.value for d in decisions)
    )


__all__ = [
    "Transition",
    "apply_activate",
    "apply_feed",
    "apply_merge",
    "apply_submit",
    "clear_cells",
    "first_empty_cell",
    "observed_state",
    "place_item",
    "run_scenario",
    "set_cell",
    "set_selection",
    "update_state",
]
