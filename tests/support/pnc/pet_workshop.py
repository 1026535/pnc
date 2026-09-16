"""Synthetic Pet Workshop fixtures for shared-contract and publication tests.

All states, orders, and transitions built here are synthetic test data: they
exercise the typed contract in ``domain/pet_workshop.py`` and the packaged
catalog's real item ids and board layout, but they are not live or
catalog-derived game evidence. Nothing here performs runtime I/O beyond the
immutable packaged catalog load.
"""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopCell,
    WorkshopCellAccess,
    WorkshopCooldown,
    WorkshopEnergy,
    WorkshopItemStatus,
    WorkshopOccupancy,
    WorkshopObservation,
    WorkshopOrder,
    WorkshopOrderReward,
    WorkshopOrderRewardCategory,
    WorkshopOrderSurvey,
    WorkshopOrderView,
    WorkshopPolicy,
    WorkshopProductionMode,
    WorkshopSelection,
    WorkshopSelectionKind,
    WorkshopState,
    WorkshopSurfaceKind,
    WorkshopSurveyCoverage,
    WorkshopSurveyFreshness,
    WorkshopView,
)
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    WorkshopBoardLayout,
    load_pet_workshop_catalog,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds


_CATALOG = load_pet_workshop_catalog()

# Real catalog ids used by the synthetic scenarios below.
TREE_4 = 20004
FRUIT_1 = 20101
FRUIT_5 = 20105
STATUE_5 = 10205
WOOD_10 = 20210
FOOD_3 = 31103
TRAP_FEED_LOCKED = 50004
FISHING_TOOL_9 = 40209
FISHING_TOOL_6 = 40206


def catalog() -> PetWorkshopCatalog:
    """Returns the packaged catalog instance used by the synthetic fixtures."""

    return _CATALOG


def board_layout() -> WorkshopBoardLayout:
    """Returns the packaged 7 x 9 board layout owner for synthetic states."""

    return _CATALOG.board


def make_cell(
    row: int,
    column: int,
    *,
    access: WorkshopCellAccess = WorkshopCellAccess.USABLE,
    occupancy: WorkshopOccupancy = WorkshopOccupancy.OCCUPIED,
    item_id: int | None = None,
    item_status: WorkshopItemStatus | None = WorkshopItemStatus.NORMAL,
    cooldown: WorkshopCooldown = WorkshopCooldown.UNKNOWN,
) -> WorkshopCell:
    """Builds one synthetic observed cell on the packaged 7 x 9 board."""

    board = board_layout()
    return WorkshopCell(
        cell_id=board.cell_id(row, column),
        row=row,
        column=column,
        access=access,
        occupancy=occupancy,
        item_id=item_id,
        item_status=item_status,
        cooldown=cooldown,
    )


def make_empty_cells(*, rows: range | None = None, columns: range | None = None) -> tuple[WorkshopCell, ...]:
    """Builds known-empty usable cells over the requested board region."""

    rows = rows if rows is not None else range(1, 10)
    columns = columns if columns is not None else range(1, 8)
    return tuple(
        make_cell(row, column, occupancy=WorkshopOccupancy.EMPTY, item_status=None)
        for row in rows
        for column in columns
    )


def make_order(
    order_ref: int,
    requirements: dict[int, int],
    *,
    rewards: tuple[WorkshopOrderReward, ...] = (),
    completeness: RowRecognitionStatus = RowRecognitionStatus.COMPLETE,
    ready: bool | None = None,
    source: str | None = "order_strip",
) -> WorkshopOrder:
    """Builds one synthetic surveyed order card."""

    return WorkshopOrder(
        order_ref=order_ref,
        requirements=requirements,
        rewards=rewards,
        completeness=completeness,
        ready=ready,
        source=source,
    )


def make_state(
    *,
    cells: tuple[WorkshopCell, ...] = (),
    energy: WorkshopEnergy | None = None,
    surface: WorkshopSurfaceKind = WorkshopSurfaceKind.BOARD,
    production_mode: WorkshopProductionMode = WorkshopProductionMode.ORDINARY,
    workshop_level: int | None = 5,
    workshop_exp: int | None = 120,
    selection: WorkshopSelection | None = None,
    order_survey: WorkshopOrderSurvey | None = None,
) -> WorkshopState:
    """Builds a synthetic logical state on the packaged board layout."""

    return WorkshopState(
        board=board_layout(),
        surface=surface,
        cells=cells,
        energy=energy if energy is not None else WorkshopEnergy(current=100, capacity=200),
        production_mode=production_mode,
        workshop_level=workshop_level,
        workshop_exp=workshop_exp,
        selection=(
            selection
            if selection is not None
            else WorkshopSelection(WorkshopSelectionKind.NONE)
        ),
        order_survey=(
            order_survey
            if order_survey is not None
            else WorkshopOrderSurvey(
                coverage=WorkshopSurveyCoverage.COMPLETE,
                freshness=WorkshopSurveyFreshness.CURRENT,
            )
        ),
    )


def make_view(
    state: WorkshopState,
    *,
    frame_ref: FrameRef | None = None,
    image_size: tuple[int, int] = (900, 1600),
    with_cell_bounds: bool = True,
    submit_refs: tuple[int, ...] = (),
) -> WorkshopView:
    """Builds measured view geometry matching one synthetic state.

    Cell bounds are derived deterministically from each observed cell's row
    and column; submit bounds are added only for the listed order refs.
    """

    cell_bounds = (
        {
            cell.cell_id: Bounds(
                x=(cell.column - 1) * 100,
                y=400 + (cell.row - 1) * 100,
                width=100,
                height=100,
            )
            for cell in state.cells
        }
        if with_cell_bounds
        else {}
    )
    order_views = tuple(
        WorkshopOrderView(
            order_ref=order.order_ref,
            portrait_bounds=Bounds(x=60 * (index + 1), y=60, width=50, height=70),
            submit_bounds=(
                Bounds(x=60 * (index + 1) + 10, y=135, width=30, height=20)
                if order.order_ref in submit_refs
                else None
            ),
        )
        for index, order in enumerate(state.order_survey.orders)
    )
    return WorkshopView(
        cell_bounds=cell_bounds,
        order_views=order_views,
        detail_control_bounds=Bounds(x=10, y=1400, width=80, height=40),
        close_control_bounds=Bounds(x=800, y=40, width=60, height=60),
        recycle_control_bounds=Bounds(x=820, y=1500, width=60, height=60),
        confirm_control_bounds=Bounds(x=380, y=980, width=140, height=60),
        image_size=image_size,
        frame_ref=frame_ref,
    )


def make_observation(
    state: WorkshopState | None = None,
    *,
    frame_ref: FrameRef | None = None,
    submit_refs: tuple[int, ...] = (),
    with_cell_bounds: bool = True,
    image_size: tuple[int, int] = (900, 1600),
    **state_kwargs,
) -> WorkshopObservation:
    """Builds a synthetic WorkshopObservation pairing state and measured view.

    View options (``submit_refs``, ``with_cell_bounds``, ``image_size``) are
    forwarded to ``make_view``; remaining keywords build the state.
    """

    resolved_state = state if state is not None else make_state(**state_kwargs)
    return WorkshopObservation(
        state=resolved_state,
        view=make_view(
            resolved_state,
            frame_ref=frame_ref,
            image_size=image_size,
            with_cell_bounds=with_cell_bounds,
            submit_refs=submit_refs,
        ),
    )


def make_policy(
    *,
    order_piece_total: int = 2,
    reward_priority: tuple[WorkshopOrderRewardCategory, ...] = (
        WorkshopOrderRewardCategory.BEAST_LASSO,
        WorkshopOrderRewardCategory.FEED,
        WorkshopOrderRewardCategory.WORKSHOP_EXP,
        WorkshopOrderRewardCategory.BOTTLE,
        WorkshopOrderRewardCategory.CHEST,
    ),
    recyclable_item_ids: frozenset[int] = frozenset({FRUIT_5, STATUE_5}),
    max_cooldown_wait_ms: int = 60_000,
) -> WorkshopPolicy:
    """Builds the agreed-decision-shaped policy values as synthetic test data.

    These values mirror the reviewed user decisions; the policy defaults and
    their evaluation remain owned by the Plan 02 packages.
    """

    return WorkshopPolicy(
        order_piece_total=order_piece_total,
        reward_priority=reward_priority,
        recyclable_item_ids=recyclable_item_ids,
        max_cooldown_wait_ms=max_cooldown_wait_ms,
    )


def feed_locked_state() -> WorkshopState:
    """Synthetic board with a feed-locked Trap producer and a Food 3 piece."""

    return make_state(
        cells=(
            make_cell(1, 1, item_id=TRAP_FEED_LOCKED, item_status=WorkshopItemStatus.FEED_LOCKED),
            make_cell(1, 2, item_id=FOOD_3),
            make_cell(1, 3, occupancy=WorkshopOccupancy.EMPTY, item_status=None),
        ),
    )


def activation_state() -> WorkshopState:
    """Synthetic board with an inactive piece and its matching normal copy."""

    return make_state(
        cells=(
            make_cell(2, 1, item_id=FRUIT_1, item_status=WorkshopItemStatus.INACTIVE),
            make_cell(2, 2, item_id=FRUIT_1, item_status=WorkshopItemStatus.NORMAL),
        ),
    )


def finite_producer_state() -> WorkshopState:
    """Synthetic board with a configured finite producer (Fishing Tool 9).

    The catalog's ``max_num``/``change_item_id`` facts for item 40209 make it
    a producer whose exhaustion transform is known; the current remaining-use
    count stays unobserved by contract.
    """

    return make_state(
        cells=(
            make_cell(3, 1, item_id=FISHING_TOOL_9, cooldown=WorkshopCooldown.CLEAR),
            make_cell(3, 2, occupancy=WorkshopOccupancy.EMPTY, item_status=None),
        ),
    )


def recycling_state() -> WorkshopState:
    """Synthetic full board of terminal pieces with a Fruit 5 recycle candidate.

    This represents the required space constraint, not a policy verdict;
    the solver must still establish reservations and useful alternatives.
    """

    board = board_layout()
    cells = tuple(
        make_cell(row, column, item_id=FRUIT_5 if (row, column) == (9, 1) else STATUE_5)
        for row in range(1, board.rows + 1)
        for column in range(1, board.columns + 1)
    )
    return make_state(cells=cells, energy=WorkshopEnergy(current=4, capacity=200))


def zero_energy_state() -> WorkshopState:
    """Synthetic board with a reliably observed zero energy bar."""

    return make_state(
        cells=(make_cell(1, 1, item_id=TREE_4, cooldown=WorkshopCooldown.CLEAR),),
        energy=WorkshopEnergy(current=0, capacity=200),
    )
