"""Transition tests for the offline Workshop simulator.

Each test drives ``WorkshopSimulator.apply`` over synthetic typed states built
on the packaged catalog — the state -> intent -> expected-state replication
loop used for solver development and capture-derived regression tests.
"""

from __future__ import annotations

import random
import unittest

from pnc_automation.app.automation.pet_workshop import plan_next
from pnc_automation.app.automation.pet_workshop.simulate import (
    ProduceOutcome,
    WorkshopSimulationError,
    WorkshopSimulator,
)
from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
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
    WorkshopSelection,
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
BOWL_1 = 30101
BOWL_3 = 30103
BOWL_4 = 30104
BOWL_5 = 30105
CLAY_3 = 30003
CLAY_4 = 30004
FOOD_1 = 31101
FOOD_3 = fx.FOOD_3
SEA_CREATURE_1 = 41101
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
            outcome=ProduceOutcome(item_id=STATUE_2, cell_id=40),
        )

        self.assertEqual(_cell(state, 40).item_id, STATUE_2)
        self.assertEqual(state.energy.current, 99)

    def test_produce_outcome_rejects_a_piece_outside_the_drop_group(self) -> None:
        """An injected outcome must name one of the producer's possible drops."""

        sim = WorkshopSimulator(_producing_state(), rng=random.Random(7))

        with self.assertRaises(WorkshopSimulationError):
            sim.apply(
                WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1),
                outcome=ProduceOutcome(item_id=FRUIT_2, cell_id=40),
            )

    def test_determined_mode_requires_an_outcome_for_produce(self) -> None:
        """Determined-input mode raises on a missing outcome instead of drawing."""

        sim = WorkshopSimulator(_producing_state(), require_produce_outcome=True)

        with self.assertRaises(WorkshopSimulationError):
            sim.apply(WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1))

        state = sim.apply(
            WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1),
            outcome=ProduceOutcome(item_id=STATUE_1, cell_id=40),
        )
        self.assertEqual(_cell(state, 40).item_id, STATUE_1)

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

    def test_submit_rejects_orders_the_client_cannot_complete(self) -> None:
        """A ``ready=False`` marker or a clipped card has no completable control.

        ``ready=None`` (the control was never evaluated) stays submittable —
        only a marker observed False proves the game would not offer the
        transition.
        """

        def built(ready: bool | None, completeness=RowRecognitionStatus.COMPLETE):
            return WorkshopSimulator(
                fx.make_state(
                    cells=(fx.make_cell(1, 1, item_id=FRUIT_1),),
                    order_survey=WorkshopOrderSurvey(
                        orders=(
                            fx.make_order(
                                7, {FRUIT_1: 1}, ready=ready, completeness=completeness
                            ),
                        ),
                        coverage=WorkshopSurveyCoverage.COMPLETE,
                        freshness=WorkshopSurveyFreshness.CURRENT,
                    ),
                )
            )

        for sim in (
            built(ready=False),
            built(ready=True, completeness=RowRecognitionStatus.CLIPPED),
        ):
            with self.assertRaises(WorkshopSimulationError):
                sim.apply(WorkshopSubmitOrderIntent(order_ref=7))
            self.assertIsNotNone(sim.state.order_survey.order(7))
            self.assertEqual(_cell(sim.state, 1).item_id, FRUIT_1)

        unevaluated = built(ready=None)
        state = unevaluated.apply(WorkshopSubmitOrderIntent(order_ref=7))
        self.assertIsNone(state.order_survey.order(7))
        self.assertEqual(_cell(state, 1).occupancy, WorkshopOccupancy.EMPTY)

    def test_consuming_intents_reconcile_the_selection(self) -> None:
        """Merge and feed select the drop target; recycle and submit clear consumed selections."""

        merge_state = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=STATUE_1),
                    fx.make_cell(1, 2, item_id=STATUE_1),
                ),
                selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, 1),
            )
        ).apply(WorkshopMergeIntent(source_cell_id=1, target_cell_id=2, item_id=STATUE_1))
        self.assertEqual(merge_state.selection.cell_id, 2)

        recycle_state = WorkshopSimulator(
            fx.make_state(
                cells=(fx.make_cell(1, 1, item_id=STATUE_3),),
                selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, 1),
            )
        ).apply(WorkshopRecycleIntent(cell_id=1, item_id=STATUE_3))
        self.assertEqual(recycle_state.selection.kind, WorkshopSelectionKind.NONE)

        feed_state = WorkshopSimulator(fx.feed_locked_state()).apply(
            WorkshopFeedIntent(food_cell_id=2, producer_cell_id=1, food_item_id=FOOD_3)
        )
        self.assertEqual(feed_state.selection.cell_id, 1)

        order = fx.make_order(7, {FRUIT_1: 1}, ready=True)
        submit_state = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=FRUIT_1),
                    fx.make_cell(1, 2, item_id=STATUE_1),
                ),
                selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, 1),
                order_survey=WorkshopOrderSurvey(
                    orders=(order,),
                    coverage=WorkshopSurveyCoverage.COMPLETE,
                    freshness=WorkshopSurveyFreshness.CURRENT,
                ),
            )
        ).apply(WorkshopSubmitOrderIntent(order_ref=7))
        self.assertEqual(submit_state.selection.kind, WorkshopSelectionKind.NONE)

        unrelated = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=STATUE_3),
                    fx.make_cell(1, 2, item_id=STATUE_1),
                ),
                selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, 2),
            )
        ).apply(WorkshopRecycleIntent(cell_id=1, item_id=STATUE_3))
        self.assertEqual(unrelated.selection.cell_id, 2)

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

    def test_order_readiness_refreshes_after_a_stock_changing_merge(self) -> None:
        """A merge completing an order flips ready; the planner then submits it.

        Reproduces review finding R1: ``plan_next -> apply -> plan_next`` must
        reach SUBMIT once the board satisfies the order instead of stopping on
        the stale ``ready=False`` marker.
        """

        survey = WorkshopOrderSurvey(
            orders=(
                fx.make_order(
                    7,
                    {FRUIT_2: 2},
                    rewards=(
                        WorkshopOrderReward(
                            category=WorkshopOrderRewardCategory.WORKSHOP_EXP,
                            quantity=25,
                        ),
                    ),
                    ready=False,
                ),
            ),
            coverage=WorkshopSurveyCoverage.COMPLETE,
            freshness=WorkshopSurveyFreshness.CURRENT,
        )
        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=FRUIT_1),
                    fx.make_cell(1, 2, item_id=FRUIT_1),
                    fx.make_cell(1, 3, item_id=FRUIT_2),
                    *(cell for cell in fx.make_empty_cells() if cell.cell_id > 3),
                ),
                order_survey=survey,
            )
        )
        catalog = fx.catalog()
        policy = fx.make_policy()

        first = plan_next(sim.state, catalog, policy)
        self.assertIsInstance(first.intent, WorkshopMergeIntent)

        state = sim.apply(first.intent)
        self.assertEqual(state.order_survey.order(7).ready, True)

        second = plan_next(state, catalog, policy)
        self.assertIsInstance(second.intent, WorkshopSubmitOrderIntent)
        self.assertEqual(second.intent.order_ref, 7)
        state = sim.apply(second.intent)
        self.assertIsNone(state.order_survey.order(7))
        self.assertEqual(_cell(state, 2).occupancy, WorkshopOccupancy.EMPTY)
        self.assertEqual(_cell(state, 3).occupancy, WorkshopOccupancy.EMPTY)

    def test_order_readiness_drops_when_stock_leaves_the_board(self) -> None:
        """Submitting one order flips a ready order back when shared stock is consumed."""

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=FRUIT_2),
                    fx.make_cell(1, 2, item_id=FRUIT_2),
                    fx.make_cell(1, 3, item_id=FRUIT_2),
                    *(cell for cell in fx.make_empty_cells() if cell.cell_id > 3),
                ),
                order_survey=WorkshopOrderSurvey(
                    orders=(
                        fx.make_order(7, {FRUIT_2: 2}, ready=True),
                        fx.make_order(8, {FRUIT_2: 3}, ready=True),
                    ),
                    coverage=WorkshopSurveyCoverage.COMPLETE,
                    freshness=WorkshopSurveyFreshness.CURRENT,
                ),
            )
        )

        state = sim.apply(WorkshopSubmitOrderIntent(order_ref=7))

        self.assertIsNone(state.order_survey.order(7))
        self.assertEqual(state.order_survey.order(8).ready, False)

    def test_order_readiness_stays_underived_while_stock_is_unread(self) -> None:
        """Unread stock or incomplete requirements cannot prove new readiness."""

        def exp_order(order_ref: int, **kwargs):
            return fx.make_order(
                order_ref,
                {FRUIT_2: 2},
                rewards=(
                    WorkshopOrderReward(
                        category=WorkshopOrderRewardCategory.WORKSHOP_EXP,
                        quantity=25,
                    ),
                ),
                ready=False,
                **kwargs,
            )

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=STATUE_1),
                    fx.make_cell(1, 2, item_id=STATUE_1),
                    fx.make_cell(1, 3, item_id=FRUIT_2),
                    fx.make_cell(
                        2, 1, occupancy=WorkshopOccupancy.UNKNOWN, item_status=None
                    ),
                    *(
                        cell
                        for cell in fx.make_empty_cells()
                        if cell.cell_id not in (1, 2, 3, 8)
                    ),
                ),
                order_survey=WorkshopOrderSurvey(
                    orders=(
                        exp_order(7),
                        exp_order(8, completeness=RowRecognitionStatus.CLIPPED),
                    ),
                    coverage=WorkshopSurveyCoverage.COMPLETE,
                    freshness=WorkshopSurveyFreshness.CURRENT,
                ),
            )
        )

        state = sim.apply(
            WorkshopMergeIntent(source_cell_id=1, target_cell_id=2, item_id=STATUE_1)
        )

        self.assertIsNone(state.order_survey.order(7).ready)
        self.assertIsNone(state.order_survey.order(8).ready)

    def test_clipped_ready_control_is_invalidated_when_stock_changes(self) -> None:
        """A previously ready clipped card cannot retain stale readiness."""

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=fx.FRUIT_5),
                    *(cell for cell in fx.make_empty_cells() if cell.cell_id != 1),
                ),
                order_survey=WorkshopOrderSurvey(
                    orders=(
                        fx.make_order(
                            7, {fx.FRUIT_5: 1}, ready=True,
                            completeness=RowRecognitionStatus.CLIPPED,
                        ),
                    ),
                    coverage=WorkshopSurveyCoverage.PARTIAL,
                    freshness=WorkshopSurveyFreshness.CURRENT,
                ),
            )
        )

        state = sim.apply(WorkshopRecycleIntent(cell_id=1, item_id=fx.FRUIT_5))

        self.assertIsNone(state.order_survey.order(7).ready)

    def test_reused_cell_does_not_inherit_the_removed_producers_uses(self) -> None:
        """A fresh Bowl 5 on a recycled cell starts with zero lifetime uses.

        Reproduces review finding R2: nine uses spent by the recycled Bowl 5
        must not follow the fresh producer later built on the same cell.
        """

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=BOWL_5, cooldown=WorkshopCooldown.CLEAR),
                    fx.make_cell(1, 2, item_id=CLAY_4, cooldown=WorkshopCooldown.CLEAR),
                    fx.make_cell(1, 3, item_id=BOWL_3),
                    fx.make_cell(1, 4, item_id=BOWL_4),
                    *(cell for cell in fx.make_empty_cells() if cell.cell_id > 4),
                )
            )
        )
        for destination in range(5, 14):
            sim.apply(
                WorkshopProduceIntent(cell_id=1, producer_item_id=BOWL_5),
                outcome=ProduceOutcome(item_id=FOOD_1, cell_id=destination),
            )
        sim.apply(WorkshopRecycleIntent(cell_id=1, item_id=BOWL_5))
        sim.apply(
            WorkshopProduceIntent(cell_id=2, producer_item_id=CLAY_4),
            outcome=ProduceOutcome(item_id=BOWL_3, cell_id=1),
        )
        sim.apply(WorkshopMergeIntent(source_cell_id=3, target_cell_id=1, item_id=BOWL_3))
        state = sim.apply(
            WorkshopMergeIntent(source_cell_id=4, target_cell_id=1, item_id=BOWL_4)
        )
        self.assertEqual(_cell(state, 1).item_id, BOWL_5)

        state = sim.apply(
            WorkshopProduceIntent(cell_id=1, producer_item_id=BOWL_5),
            outcome=ProduceOutcome(item_id=FOOD_1, cell_id=14),
        )

        self.assertEqual(_cell(state, 1).item_id, BOWL_5)
        self.assertEqual(_cell(state, 14).item_id, FOOD_1)

    def test_replacing_a_cooling_piece_drops_its_deadline(self) -> None:
        """A merge superseding a cooling producer frees the successor to produce."""

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=CLAY_3, cooldown=WorkshopCooldown.CLEAR),
                    fx.make_cell(1, 2, item_id=CLAY_3),
                    *(cell for cell in fx.make_empty_cells() if cell.cell_id > 2),
                )
            )
        )
        for destination in range(3, 33):  # thirty uses trigger the cooldown cycle
            sim.apply(
                WorkshopProduceIntent(cell_id=1, producer_item_id=CLAY_3),
                outcome=ProduceOutcome(item_id=BOWL_1, cell_id=destination),
            )
        self.assertEqual(_cell(sim.state, 1).cooldown, WorkshopCooldown.ACTIVE)

        state = sim.apply(
            WorkshopMergeIntent(source_cell_id=2, target_cell_id=1, item_id=CLAY_3)
        )
        self.assertEqual(_cell(state, 1).item_id, CLAY_4)
        self.assertEqual(_cell(state, 1).cooldown, WorkshopCooldown.CLEAR)

        state = sim.apply(
            WorkshopProduceIntent(cell_id=1, producer_item_id=CLAY_4),
            outcome=ProduceOutcome(item_id=BOWL_3, cell_id=2),
        )
        self.assertEqual(_cell(state, 2).item_id, BOWL_3)

    def test_unchanged_producers_keep_counters_and_deadlines(self) -> None:
        """Removing another piece leaves a producer's deadline and lifetime intact."""

        sim = WorkshopSimulator(_producing_state(FISHING_TOOL_9))
        for destination in range(2, 12):  # ten uses trigger the cooldown cycle
            sim.apply(
                WorkshopProduceIntent(cell_id=1, producer_item_id=FISHING_TOOL_9),
                outcome=ProduceOutcome(item_id=SEA_CREATURE_1, cell_id=destination),
            )
        self.assertEqual(_cell(sim.state, 1).cooldown, WorkshopCooldown.ACTIVE)

        sim.apply(WorkshopRecycleIntent(cell_id=2, item_id=SEA_CREATURE_1))
        with self.assertRaises(WorkshopSimulationError):
            sim.apply(
                WorkshopProduceIntent(cell_id=1, producer_item_id=FISHING_TOOL_9)
            )
        sim.apply(WorkshopWaitIntent(max_wait_ms=3_000))
        for destination in (2, *range(12, 20)):  # nine more uses keep the piece
            sim.apply(
                WorkshopProduceIntent(cell_id=1, producer_item_id=FISHING_TOOL_9),
                outcome=ProduceOutcome(item_id=SEA_CREATURE_1, cell_id=destination),
            )
        self.assertEqual(_cell(sim.state, 1).item_id, FISHING_TOOL_9)

        state = sim.apply(
            WorkshopProduceIntent(cell_id=1, producer_item_id=FISHING_TOOL_9),
            outcome=ProduceOutcome(item_id=SEA_CREATURE_1, cell_id=20),
        )
        self.assertEqual(_cell(state, 1).item_id, FISHING_TOOL_6)

    def test_initial_cooldown_expires_on_cumulative_wait_time(self) -> None:
        """An initially ACTIVE marker clears once total waited time reaches the window.

        Reproduces review finding R3: three 10s waits must expire a 30s
        cooldown exactly as one 30s wait does.
        """

        sim = WorkshopSimulator(
            fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=MAP_1, cooldown=WorkshopCooldown.ACTIVE),
                    *(cell for cell in fx.make_empty_cells() if cell.cell_id != 1),
                )
            )
        )

        sim.apply(WorkshopWaitIntent(max_wait_ms=10_000))
        sim.apply(WorkshopWaitIntent(max_wait_ms=10_000))
        self.assertEqual(_cell(sim.state, 1).cooldown, WorkshopCooldown.ACTIVE)
        with self.assertRaises(WorkshopSimulationError):
            sim.apply(WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1))

        state = sim.apply(WorkshopWaitIntent(max_wait_ms=10_000))
        self.assertEqual(_cell(state, 1).cooldown, WorkshopCooldown.CLEAR)
        state = sim.apply(
            WorkshopProduceIntent(cell_id=1, producer_item_id=MAP_1),
            outcome=ProduceOutcome(item_id=STATUE_1, cell_id=2),
        )
        self.assertEqual(_cell(state, 2).item_id, STATUE_1)

    def test_initial_cooldown_expires_exactly_at_the_window(self) -> None:
        """Waits reaching the authored cooldown exactly clear the marker at expiry."""

        def cooling_state():
            return fx.make_state(
                cells=(
                    fx.make_cell(1, 1, item_id=MAP_1, cooldown=WorkshopCooldown.ACTIVE),
                    *(cell for cell in fx.make_empty_cells() if cell.cell_id != 1),
                )
            )

        exact = WorkshopSimulator(cooling_state())
        state = exact.apply(WorkshopWaitIntent(max_wait_ms=30_000))
        self.assertEqual(_cell(state, 1).cooldown, WorkshopCooldown.CLEAR)

        partitioned = WorkshopSimulator(cooling_state())
        partitioned.apply(WorkshopWaitIntent(max_wait_ms=29_999))
        self.assertEqual(
            _cell(partitioned.state, 1).cooldown, WorkshopCooldown.ACTIVE
        )
        state = partitioned.apply(WorkshopWaitIntent(max_wait_ms=1))
        self.assertEqual(_cell(state, 1).cooldown, WorkshopCooldown.CLEAR)

    def test_produce_triggered_cooldown_expires_across_partitioned_waits(self) -> None:
        """A cycle cooldown armed by production expires on the same deadline clock."""

        sim = WorkshopSimulator(_producing_state(FISHING_TOOL_9))
        for destination in range(2, 12):  # ten uses trigger the cooldown cycle
            sim.apply(
                WorkshopProduceIntent(cell_id=1, producer_item_id=FISHING_TOOL_9),
                outcome=ProduceOutcome(item_id=SEA_CREATURE_1, cell_id=destination),
            )
        self.assertEqual(_cell(sim.state, 1).cooldown, WorkshopCooldown.ACTIVE)

        sim.apply(WorkshopWaitIntent(max_wait_ms=1_500))
        self.assertEqual(_cell(sim.state, 1).cooldown, WorkshopCooldown.ACTIVE)
        state = sim.apply(WorkshopWaitIntent(max_wait_ms=1_500))
        self.assertEqual(_cell(state, 1).cooldown, WorkshopCooldown.CLEAR)


if __name__ == "__main__":
    unittest.main()
