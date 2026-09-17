"""Transition tests for the offline Workshop simulator.

Each test drives ``WorkshopSimulator.apply`` over synthetic typed states built
on the packaged catalog — the state -> intent -> expected-state replication
loop used for solver development and capture-derived regression tests.
"""

from __future__ import annotations

import random
import unittest

from pnc_automation.app.automation.pet_workshop.simulate import (
    ProduceOutcome,
    WorkshopSimulationError,
    WorkshopSimulator,
)
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopActivateIntent,
    WorkshopCell,
    WorkshopCellAccess,
    WorkshopCooldown,
    WorkshopEnergy,
    WorkshopFeedIntent,
    WorkshopInspectIntent,
    WorkshopInspectKind,
    WorkshopItemStatus,
    WorkshopMergeIntent,
    WorkshopOccupancy,
    WorkshopOrderReward,
    WorkshopOrderRewardCategory,
    WorkshopOrderSurvey,
    WorkshopProduceIntent,
    WorkshopRecycleIntent,
    WorkshopSelectIntent,
    WorkshopSelectionKind,
    WorkshopStopIntent,
    WorkshopStopReason,
    WorkshopSubmitOrderIntent,
    WorkshopSurveyCoverage,
    WorkshopSurveyFreshness,
    WorkshopWaitIntent,
)
from tests.support.pnc import pet_workshop as fx

MAP_1 = 10001
STATUE_1 = 10101
STATUE_2 = 10102
STATUE_3 = 10103
FRUIT_2 = 20102
FRUIT_1 = fx.FRUIT_1
FOOD_3 = fx.FOOD_3
TRAP = fx.TRAP_FEED_LOCKED
FISHING_TOOL_9 = fx.FISHING_TOOL_9
FISHING_TOOL_6 = fx.FISHING_TOOL_6


def _cell(state, cell_id: int) -> WorkshopCell:
    """Returns the cell with one id from a simulated state."""

    return next(cell for cell in state.cells if cell.cell_id == cell_id)


def _producing_state(item_id: int = MAP_1, **state_kwargs):
    """One producer on cell 1 with every other board cell usable and empty."""

    return fx.make_state(
        cells=(
            fx.make_cell(1, 1, item_id=item_id, cooldown=WorkshopCooldown.CLEAR),
            *(cell for cell in fx.make_empty_cells() if cell.cell_id != 1),
        ),
        **state_kwargs,
    )


class WorkshopSimulatorTests(unittest.TestCase):
    """Drives intents through the simulator and asserts the replicated state."""

    def test_merge_produces_catalog_successor_and_empties_source(self) -> None:
        """Two matching Normal pieces become the authored successor."""

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=STATUE_1),
                    fx.make_cell(1, 2, item_id=STATUE_1),
                )
            )
        )

        state = sim.apply(WorkshopMergeIntent(source_cell_id=1, target_cell_id=2, item_id=STATUE_1))

        self.assertEqual(_cell(state, 1).occupancy, WorkshopOccupancy.EMPTY)
        self.assertEqual(_cell(state, 2).item_id, STATUE_2)
        self.assertEqual(_cell(state, 2).item_status, WorkshopItemStatus.NORMAL)

    def test_merge_rejects_mismatched_or_max_tier_pieces(self) -> None:
        """Merging unlike items or a terminal piece is impossible."""

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=STATUE_1),
                    fx.make_cell(1, 2, item_id=FRUIT_1),
                )
            )
        )

        with self.assertRaises(WorkshopSimulationError):
            sim.apply(WorkshopMergeIntent(source_cell_id=1, target_cell_id=2, item_id=STATUE_1))
        with self.assertRaises(WorkshopSimulationError):
            WorkshopSimulator(
                fx.make_state(
                    cells=(
                        fx.make_cell(1, 1, item_id=FISHING_TOOL_9),
                        fx.make_cell(1, 2, item_id=FISHING_TOOL_9),
                    )
                )
            ).apply(WorkshopMergeIntent(source_cell_id=1, target_cell_id=2, item_id=FISHING_TOOL_9))

    def test_activate_consumes_fuel_into_inactive_target(self) -> None:
        """A Normal piece activates its matching Inactive piece into the successor."""

        sim = WorkshopSimulator(fx.activation_state())

        state = sim.apply(
            WorkshopActivateIntent(source_cell_id=9, target_cell_id=8, item_id=FRUIT_1)
        )

        self.assertEqual(_cell(state, 9).occupancy, WorkshopOccupancy.EMPTY)
        self.assertEqual(_cell(state, 8).item_id, FRUIT_2)
        self.assertEqual(_cell(state, 8).item_status, WorkshopItemStatus.NORMAL)

    def test_feed_unlocks_feed_locked_producer(self) -> None:
        """Feeding the authored ingredient turns the Trap producible."""

        sim = WorkshopSimulator(fx.feed_locked_state())

        state = sim.apply(
            WorkshopFeedIntent(food_cell_id=2, producer_cell_id=1, food_item_id=FOOD_3)
        )

        self.assertEqual(_cell(state, 2).occupancy, WorkshopOccupancy.EMPTY)
        self.assertEqual(_cell(state, 1).item_status, WorkshopItemStatus.NORMAL)

    def test_feed_rejects_wrong_ingredient(self) -> None:
        """The producer only accepts its authored feed item."""

        sim = WorkshopSimulator(fx.feed_locked_state())

        with self.assertRaises(WorkshopSimulationError):
            sim.apply(
                WorkshopFeedIntent(food_cell_id=2, producer_cell_id=1, food_item_id=FRUIT_1)
            )

    def test_recycle_removes_piece_and_grants_authored_energy(self) -> None:
        """Recycling a recoverable piece empties the cell and adds the reward."""

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(fx.make_cell(1, 1, item_id=STATUE_3),),
                energy=WorkshopEnergy(current=100, capacity=200),
            )
        )

        state = sim.apply(WorkshopRecycleIntent(cell_id=1, item_id=STATUE_3))

        self.assertEqual(_cell(state, 1).occupancy, WorkshopOccupancy.EMPTY)
        self.assertEqual(state.energy.current, 102)

    def test_produce_draws_authored_item_and_spends_energy(self) -> None:
        """Map 1's drop group has a single positive outcome: Statue 1."""

        sim = WorkshopSimulator(_producing_state(), rng=random.Random(7))

        state = sim.apply(WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1))

        self.assertEqual(state.energy.current, 99)
        spawned = [
            cell
            for cell in state.cells
            if cell.occupancy == WorkshopOccupancy.OCCUPIED and cell.cell_id != 1
        ]
        self.assertEqual(len(spawned), 1)
        self.assertEqual(spawned[0].item_id, STATUE_1)
        self.assertEqual(spawned[0].item_status, WorkshopItemStatus.NORMAL)

    def test_produce_outcome_replays_the_captured_result(self) -> None:
        """An injected outcome lands the captured piece on the captured cell."""

        sim = WorkshopSimulator(_producing_state(), rng=random.Random(7))

        state = sim.apply(
            WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1),
            outcome=ProduceOutcome(item_id=FRUIT_2, cell_id=40),
        )

        self.assertEqual(_cell(state, 40).item_id, FRUIT_2)
        self.assertEqual(state.energy.current, 99)

    def test_produce_rejects_impossible_transitions(self) -> None:
        """Non-producers, zero energy, cooling markers, and full boards all stop production."""

        with self.assertRaises(WorkshopSimulationError):
            WorkshopSimulator(
                _producing_state(item_id=STATUE_1)
            ).apply(WorkshopProduceIntent(cell_id=1, producer_item_id=STATUE_1))
        with self.assertRaises(WorkshopSimulationError):
            WorkshopSimulator(
                _producing_state(energy=WorkshopEnergy(current=0, capacity=200))
            ).apply(WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1))
        with self.assertRaises(WorkshopSimulationError):
            WorkshopSimulator(
                fx.make_state(
                    cells=(
                        fx.make_cell(1, 1, item_id=MAP_1, cooldown=WorkshopCooldown.ACTIVE),
                        *(cell for cell in fx.make_empty_cells() if cell.cell_id != 1),
                    )
                )
            ).apply(WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1))
        board = fx.board_layout()
        full = tuple(
            fx.make_cell(row, column, item_id=MAP_1 if (row, column) == (1, 1) else fx.STATUE_5)
            for row in range(1, board.rows + 1)
            for column in range(1, board.columns + 1)
        )
        with self.assertRaises(WorkshopSimulationError):
            WorkshopSimulator(fx.make_state(cells=full)).apply(
                WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1)
            )

    def test_cooldown_cycle_and_exhaustion_transform(self) -> None:
        """Fishing Tool 9 cools after 10 uses, waits clear it, and 20 uses transform it."""

        sim = WorkshopSimulator(
            _producing_state(item_id=FISHING_TOOL_9), rng=random.Random(3)
        )
        produce = WorkshopProduceIntent(cell_id=1, producer_item_id=FISHING_TOOL_9)

        for _ in range(10):
            sim.apply(produce)
        self.assertEqual(_cell(sim.state, 1).cooldown, WorkshopCooldown.ACTIVE)
        with self.assertRaises(WorkshopSimulationError):
            sim.apply(produce)

        sim.apply(WorkshopWaitIntent(max_wait_ms=3_000))
        self.assertEqual(_cell(sim.state, 1).cooldown, WorkshopCooldown.CLEAR)

        for _ in range(10):
            sim.apply(produce)
        self.assertEqual(_cell(sim.state, 1).item_id, FISHING_TOOL_6)

    def test_wait_clears_observed_cooldown_and_regenerates_energy(self) -> None:
        """A full authored cooldown window clears an observed marker; regen fills the bar."""

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=MAP_1, cooldown=WorkshopCooldown.ACTIVE),
                    *tuple(cell for cell in fx.make_empty_cells() if cell.cell_id != 1),
                ),
                energy=WorkshopEnergy(current=50, capacity=200),
            )
        )

        state = sim.apply(WorkshopWaitIntent(max_wait_ms=300_000))

        self.assertEqual(_cell(state, 1).cooldown, WorkshopCooldown.CLEAR)
        self.assertEqual(state.energy.current, 51)

    def test_submit_consumes_requirements_and_removes_order(self) -> None:
        """Submitting consumes stock and drops the card; level and EXP stay fixed."""

        order = fx.make_order(
            7,
            {FRUIT_1: 2},
            rewards=(
                WorkshopOrderReward(
                    category=WorkshopOrderRewardCategory.WORKSHOP_EXP, quantity=25
                ),
            ),
            ready=True,
        )
        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=FRUIT_1),
                    fx.make_cell(1, 2, item_id=FRUIT_1),
                    fx.make_cell(1, 3, occupancy=WorkshopOccupancy.EMPTY, item_status=None),
                    fx.make_cell(4, 6, access=WorkshopCellAccess.LOCKED,
                                 occupancy=WorkshopOccupancy.EMPTY, item_status=None),
                ),
                workshop_level=1,
                workshop_exp=20,
                order_survey=WorkshopOrderSurvey(
                    orders=(order,),
                    coverage=WorkshopSurveyCoverage.COMPLETE,
                    freshness=WorkshopSurveyFreshness.CURRENT,
                ),
            )
        )

        state = sim.apply(WorkshopSubmitOrderIntent(order_ref=7))

        self.assertIsNone(state.order_survey.order(7))
        self.assertEqual(_cell(state, 1).occupancy, WorkshopOccupancy.EMPTY)
        self.assertEqual(_cell(state, 2).occupancy, WorkshopOccupancy.EMPTY)
        self.assertEqual(_cell(state, 3).occupancy, WorkshopOccupancy.EMPTY)
        self.assertEqual(state.workshop_level, 1)
        self.assertEqual(state.workshop_exp, 20)
        self.assertEqual(_cell(state, 27).access, WorkshopCellAccess.LOCKED)

    def test_submit_rejects_insufficient_stock(self) -> None:
        """An order demanding more than the board holds cannot be submitted."""

        order = fx.make_order(3, {FRUIT_1: 2}, ready=True)
        sim = WorkshopSimulator(
            fx.make_state(
                cells=(fx.make_cell(1, 1, item_id=FRUIT_1),),
                order_survey=WorkshopOrderSurvey(
                    orders=(order,),
                    coverage=WorkshopSurveyCoverage.COMPLETE,
                    freshness=WorkshopSurveyFreshness.CURRENT,
                ),
            )
        )

        with self.assertRaises(WorkshopSimulationError):
            sim.apply(WorkshopSubmitOrderIntent(order_ref=3))
        self.assertIsNotNone(sim.state.order_survey.order(3))
        self.assertEqual(_cell(sim.state, 1).item_id, FRUIT_1)

    def test_select_marks_usable_cells_only(self) -> None:
        """Selecting a usable cell marks it; a locked cell leaves the selection alone."""

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=STATUE_1),
                    fx.make_cell(1, 2, access=WorkshopCellAccess.LOCKED,
                                 occupancy=WorkshopOccupancy.EMPTY, item_status=None),
                )
            )
        )

        state = sim.apply(WorkshopSelectIntent(cell_id=1))
        self.assertEqual(state.selection.kind, WorkshopSelectionKind.SELECTED)
        self.assertEqual(state.selection.cell_id, 1)

        state = sim.apply(WorkshopSelectIntent(cell_id=2))
        self.assertEqual(state.selection.cell_id, 1)

    def test_inspect_and_stop_leave_state_unchanged(self) -> None:
        """Information and terminal intents never mutate the replicated state."""

        initial = fx.activation_state()
        sim = WorkshopSimulator(initial)

        self.assertIs(
            sim.apply(WorkshopInspectIntent(need=WorkshopInspectKind.BOARD)), sim.state
        )
        self.assertIs(
            sim.apply(WorkshopStopIntent(reason=WorkshopStopReason.ZERO_ENERGY)), sim.state
        )
        self.assertEqual(sim.state.cells, initial.cells)


if __name__ == "__main__":
    unittest.main()
