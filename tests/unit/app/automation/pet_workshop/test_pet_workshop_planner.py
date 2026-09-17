"""Scenario tests for the PW04 one-step planner.

Each test drives ``plan_next`` over synthetic typed states built on the
packaged catalog — the Plan 02 scenario-table acceptance criteria, plus the
observe → plan → apply-outcome → replan loop through the test-only driver.
"""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.pet_workshop import plan_next
from pnc_automation.app.automation.pet_workshop.policy import default_policy
from pnc_automation.app.automation.pet_workshop.validation import validate_intent
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopActivateIntent,
    WorkshopCooldown,
    WorkshopDecision,
    WorkshopEnergy,
    WorkshopFeedIntent,
    WorkshopInspectIntent,
    WorkshopInspectKind,
    WorkshopItemStatus,
    WorkshopMergeIntent,
    WorkshopOrderReward,
    WorkshopOrderRewardCategory,
    WorkshopOrderSurvey,
    WorkshopProduceIntent,
    WorkshopProductionMode,
    WorkshopRecycleIntent,
    WorkshopSelectIntent,
    WorkshopSelection,
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
from pnc_automation.app.pnc.pet_workshop_catalog import load_pet_workshop_catalog
from tests.support.pnc import pet_workshop as fx
from tests.support.pnc import pet_workshop_solver as solver_fx

TREE_4 = fx.TREE_4
FRUIT_1 = fx.FRUIT_1
FRUIT_2 = 20102
FRUIT_3 = 20103
FRUIT_5 = fx.FRUIT_5
STATUE_5 = fx.STATUE_5
WOOD_1 = 20201
WOOD_10 = fx.WOOD_10
FOOD_3 = fx.FOOD_3
TRAP = fx.TRAP_FEED_LOCKED
FISHING_TOOL_9 = fx.FISHING_TOOL_9
SEA_CREATURE_1 = 41101
ANIMAL_1 = 50101


def chest_order(order_ref: int, requirements: dict, *, ready=True):
    return fx.make_order(
        order_ref,
        requirements,
        rewards=(WorkshopOrderReward(WorkshopOrderRewardCategory.CHEST, 1),),
        ready=ready,
    )


def lasso_order(order_ref: int, requirements: dict, *, ready=True):
    return fx.make_order(
        order_ref,
        requirements,
        rewards=(
            WorkshopOrderReward(WorkshopOrderRewardCategory.BEAST_LASSO, 1),
        ),
        ready=ready,
    )


class PlannerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_pet_workshop_catalog()
        cls.policy = default_policy()

    def plan(self, state: WorkshopState) -> WorkshopDecision:
        return plan_next(state, self.catalog, self.policy)

    def full_board(self, *items: int, orders=()) -> WorkshopState:
        placed = list(items)
        placed.extend(
            item.item_id
            for item in self.catalog.items
            if item.item_id not in placed
        )
        cells = tuple(
            fx.make_cell(row, col, item_id=placed[(row - 1) * 7 + col - 1])
            for row in range(1, 10)
            for col in range(1, 8)
        )
        return solver_fx.observed_state(*cells, orders=orders)


class TestTerminalEvidence(PlannerCase):
    def test_zero_energy_stops_even_with_ready_order(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            energy=WorkshopEnergy(current=0, capacity=200),
            orders=(chest_order(1, {FRUIT_1: 2}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopStopIntent)
        self.assertEqual(
            decision.intent.reason, WorkshopStopReason.ZERO_ENERGY
        )

    def test_excluded_surface_stops(self) -> None:
        state = solver_fx.observed_state(
            surface=WorkshopSurfaceKind.EXCLUDED_MODAL
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopStopIntent)
        self.assertEqual(
            decision.intent.reason, WorkshopStopReason.EXCLUDED_SURFACE
        )

    def test_unknown_surface_inspects_board(self) -> None:
        state = solver_fx.observed_state(surface=WorkshopSurfaceKind.UNKNOWN)
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopInspectIntent)
        self.assertEqual(decision.intent.need, WorkshopInspectKind.BOARD)

    def test_auto_fusion_mode_stops(self) -> None:
        state = solver_fx.observed_state(
            production_mode=WorkshopProductionMode.AUTO_FUSION
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopStopIntent)


class TestSurveyAndInspection(PlannerCase):
    def test_partial_survey_inspects_orders(self) -> None:
        survey = WorkshopOrderSurvey(
            orders=(chest_order(1, {FRUIT_1: 2}),),
            coverage=WorkshopSurveyCoverage.PARTIAL,
            freshness=WorkshopSurveyFreshness.CURRENT,
        )
        decision = self.plan(solver_fx.observed_state(survey=survey))
        self.assertIsInstance(decision.intent, WorkshopInspectIntent)
        self.assertEqual(decision.intent.need, WorkshopInspectKind.ORDER_SURVEY)

    def test_stale_survey_inspects_orders(self) -> None:
        survey = WorkshopOrderSurvey(
            orders=(chest_order(1, {FRUIT_1: 2}),),
            coverage=WorkshopSurveyCoverage.COMPLETE,
            freshness=WorkshopSurveyFreshness.STALE,
        )
        decision = self.plan(solver_fx.observed_state(survey=survey))
        self.assertIsInstance(decision.intent, WorkshopInspectIntent)
        self.assertEqual(decision.intent.need, WorkshopInspectKind.ORDER_SURVEY)

    def test_unread_reward_quantity_inspects_card(self) -> None:
        order = fx.make_order(
            1,
            {FRUIT_1: 2},
            rewards=(
                WorkshopOrderReward(
                    WorkshopOrderRewardCategory.BEAST_LASSO, None
                ),
            ),
        )
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(order,),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopInspectIntent)
        self.assertEqual(decision.intent.need, WorkshopInspectKind.ORDER_CONTENTS)
        self.assertEqual(decision.intent.order_ref, 1)

    def test_satisfied_unready_order_re_reads_card(self) -> None:
        # Stock satisfies the order but the ready control was never read.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_1: 2}, ready=None),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopInspectIntent)
        self.assertEqual(decision.intent.need, WorkshopInspectKind.ORDER_CONTENTS)
        self.assertEqual(decision.intent.order_ref, 1)


class TestSubmission(PlannerCase):
    def test_ready_primary_submits(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_1: 2}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopSubmitOrderIntent)
        self.assertEqual(decision.intent.order_ref, 1)
        self.assertEqual(decision.goal_order_ref, 1)

    def test_surplus_secondary_submits_when_primary_unready(self) -> None:
        # Order 1 pays double the chests, so it ranks primary even unready;
        # the third F1 is surplus and order 2 submits safely.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=FRUIT_1),
            fx.make_cell(1, 4, item_id=WOOD_1),
            orders=(
                fx.make_order(
                    1,
                    {FRUIT_1: 2},
                    rewards=(
                        WorkshopOrderReward(
                            WorkshopOrderRewardCategory.CHEST, 2
                        ),
                    ),
                    ready=False,
                ),
                chest_order(2, {FRUIT_1: 1, WOOD_1: 1}, ready=True),
            ),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopSubmitOrderIntent)
        self.assertEqual(decision.intent.order_ref, 2)
        self.assertEqual(decision.goal_order_ref, 1)

    def test_reserved_stock_never_submits_lower_order(self) -> None:
        # Same orders, but only the two reserved F1s exist — order 2 would
        # consume a protected piece and must not be submitted.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=WOOD_1),
            orders=(
                fx.make_order(
                    1,
                    {FRUIT_1: 2},
                    rewards=(
                        WorkshopOrderReward(
                            WorkshopOrderRewardCategory.CHEST, 2
                        ),
                    ),
                    ready=False,
                ),
                chest_order(2, {FRUIT_1: 1, WOOD_1: 1}, ready=True),
            ),
        )
        decision = self.plan(state)
        self.assertNotIsInstance(decision.intent, WorkshopSubmitOrderIntent)

    def test_three_duplicates_one_reserved_two_submit(self) -> None:
        # Order 1 protects one F1 by quantity; order 2's two F1s come from
        # the true surplus of three, so its submission is legal.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=FRUIT_1),
            fx.make_cell(1, 4, item_id=WOOD_1),
            orders=(
                fx.make_order(
                    1,
                    {FRUIT_1: 1, WOOD_1: 1},
                    rewards=(
                        WorkshopOrderReward(
                            WorkshopOrderRewardCategory.CHEST, 2
                        ),
                    ),
                    ready=False,
                ),
                chest_order(2, {FRUIT_1: 2}, ready=True),
            ),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopSubmitOrderIntent)
        self.assertEqual(decision.intent.order_ref, 2)
        self.assertEqual(decision.goal_order_ref, 1)


class TestFreeProgress(PlannerCase):
    def test_merge_builds_missing_demand(self) -> None:
        # Wood 10 needs production, but the Fruit-3 demand is one merge away.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_2),
            fx.make_cell(1, 2, item_id=FRUIT_2),
            fx.make_cell(1, 3, item_id=TREE_4),
            orders=(lasso_order(1, {FRUIT_3: 1, WOOD_10: 1}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopMergeIntent)
        self.assertEqual(decision.intent.item_id, FRUIT_2)

    def test_no_over_merging_reserved_stock(self) -> None:
        # F1 is demanded exactly; merging the only pair must not happen.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=TREE_4),
            orders=(lasso_order(1, {FRUIT_1: 2}, ready=False),),
        )
        decision = self.plan(state)
        self.assertNotIsInstance(decision.intent, WorkshopMergeIntent)

    def test_activation_progress(self) -> None:
        # Inactive F2 + normal F2 yields F3 — the missing demand.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_2),
            fx.make_cell(
                1, 2, item_id=FRUIT_2, item_status=WorkshopItemStatus.INACTIVE
            ),
            orders=(lasso_order(1, {FRUIT_3: 1, WOOD_1: 1}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopActivateIntent)
        self.assertEqual(decision.intent.item_id, FRUIT_2)

    def test_bubble_pieces_are_not_progress(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_2),
            fx.make_cell(
                1, 2, item_id=FRUIT_2, item_status=WorkshopItemStatus.BUBBLE
            ),
            orders=(lasso_order(1, {FRUIT_3: 1, WOOD_1: 1}),),
        )
        decision = self.plan(state)
        self.assertNotIsInstance(
            decision.intent, (WorkshopMergeIntent, WorkshopActivateIntent)
        )

    def test_feed_progress(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FOOD_3),
            fx.make_cell(
                1, 2, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED
            ),
            fx.make_cell(1, 3, item_id=FRUIT_1),
            orders=(lasso_order(1, {ANIMAL_1: 1, FRUIT_1: 1}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopFeedIntent)
        self.assertEqual(decision.intent.food_item_id, FOOD_3)


class TestProduction(PlannerCase):
    def wood_goal_state(self, tree_cooldown: WorkshopCooldown, **kw) -> WorkshopState:
        return solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, cooldown=tree_cooldown),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(lasso_order(1, {WOOD_10: 1, FRUIT_1: 1}),),
            **kw,
        )

    def test_known_selection_produces(self) -> None:
        state = self.wood_goal_state(
            WorkshopCooldown.CLEAR,
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopProduceIntent)
        self.assertEqual(decision.intent.cell_id, 1)
        self.assertEqual(decision.intent.producer_item_id, TREE_4)

    def test_unselected_producer_selects_first(self) -> None:
        state = self.wood_goal_state(WorkshopCooldown.CLEAR)
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopSelectIntent)
        self.assertEqual(decision.intent.cell_id, 1)

    def test_unread_cooldown_inspects_cell(self) -> None:
        state = self.wood_goal_state(WorkshopCooldown.UNKNOWN)
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopInspectIntent)
        self.assertEqual(decision.intent.need, WorkshopInspectKind.CELL_STATE)
        self.assertEqual(decision.intent.cell_id, 1)

    def test_all_cooling_producers_wait_bounded(self) -> None:
        state = self.wood_goal_state(WorkshopCooldown.ACTIVE)
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopWaitIntent)
        self.assertEqual(
            decision.intent.max_wait_ms, self.policy.max_cooldown_wait_ms
        )

    def test_unread_selection_inspects_before_select(self) -> None:
        state = self.wood_goal_state(
            WorkshopCooldown.CLEAR,
            selection=WorkshopSelection(WorkshopSelectionKind.UNKNOWN),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopInspectIntent)

    def test_unread_energy_inspects_before_produce(self) -> None:
        state = self.wood_goal_state(
            WorkshopCooldown.CLEAR,
            energy=WorkshopEnergy(current=None, capacity=200),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopInspectIntent)

    def test_finite_remaining_uses_still_produce(self) -> None:
        # Fishing Tool 9 is a finite-use producer: the unknown remaining-use
        # count affects the estimate's confidence, never the legality.
        state = solver_fx.observed_state(
            fx.make_cell(
                1, 1, item_id=FISHING_TOOL_9, cooldown=WorkshopCooldown.CLEAR
            ),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
            orders=(lasso_order(1, {SEA_CREATURE_1: 1, FRUIT_1: 1}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopProduceIntent)
        self.assertEqual(decision.intent.producer_item_id, FISHING_TOOL_9)


class TestFullBoardAndStop(PlannerCase):
    def test_full_board_recycles_allowlisted_terminal(self) -> None:
        # The single on-board F1 leaves the duplicate demand open; with no
        # merge/activate/feed available, the unreserved terminal is recycled.
        state = self.full_board(
            STATUE_5, orders=(chest_order(1, {FRUIT_1: 2}),)
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopRecycleIntent)
        self.assertEqual(decision.intent.item_id, STATUE_5)

    def test_full_board_merges_before_recycling(self) -> None:
        # The F1 pair is a reservation-legal merge (F2 demand is missing),
        # which must be taken before any recycling is permitted.
        state = self.full_board(
            STATUE_5,
            FRUIT_1,
            FRUIT_1,
            orders=(chest_order(1, {FRUIT_2: 2}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopMergeIntent)
        self.assertEqual(decision.intent.item_id, FRUIT_1)

    def test_full_board_with_no_recovery_stops(self) -> None:
        # Unique non-mergeable pieces; both allowlisted terminals are
        # reservation-protected by the satisfied order.
        state = self.full_board(
            orders=(chest_order(1, {FRUIT_5: 1, STATUE_5: 1}, ready=False),)
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopStopIntent)
        self.assertEqual(
            decision.intent.reason, WorkshopStopReason.BOARD_BLOCKED
        )

    def test_no_supported_path_stops_unresolved(self) -> None:
        # The Trap itself is demanded but nothing produces it and none is on
        # the board to feed — no action remains.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            orders=(lasso_order(1, {TRAP: 1, FRUIT_1: 1}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopStopIntent)
        self.assertEqual(
            decision.intent.reason, WorkshopStopReason.UNRESOLVED_STATE
        )

    def test_no_eligible_goal_stops(self) -> None:
        # The ready three-piece chest order is ineligible on shape alone:
        # fully stocked and displayed ready, it still earns no submission.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_1: 3}),),
        )
        decision = self.plan(state)
        self.assertIsInstance(decision.intent, WorkshopStopIntent)
        self.assertEqual(
            decision.intent.reason, WorkshopStopReason.NO_ELIGIBLE_GOAL
        )


class TestReplanning(PlannerCase):
    def test_replan_after_merge_outcome_then_submit(self) -> None:
        # F2 pair merges to F3, then the satisfied order submits — every
        # decision comes from the current state, never a queued plan.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_2),
            fx.make_cell(1, 2, item_id=FRUIT_2),
            fx.make_cell(1, 3, item_id=FRUIT_1),
            orders=(lasso_order(1, {FRUIT_3: 1, FRUIT_1: 1}),),
        )

        def transition(current: WorkshopState, decision: WorkshopDecision):
            if isinstance(decision.intent, WorkshopMergeIntent):
                return solver_fx.apply_merge(
                    current, decision.intent, self.catalog
                )
            return None

        decisions = solver_fx.run_scenario(
            state, self.catalog, self.policy, transition
        )
        kinds = [decision.intent.kind for decision in decisions]
        self.assertEqual(kinds[0].value, "merge")
        self.assertIsInstance(decisions[-1].intent, WorkshopSubmitOrderIntent)

    def test_replan_after_select_outcome_produces(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, cooldown=WorkshopCooldown.CLEAR),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(lasso_order(1, {WOOD_10: 1, FRUIT_1: 1}),),
        )

        def transition(current: WorkshopState, decision: WorkshopDecision):
            if isinstance(decision.intent, WorkshopSelectIntent):
                return solver_fx.set_selection(current, decision.intent.cell_id)
            return None

        decisions = solver_fx.run_scenario(
            state, self.catalog, self.policy, transition
        )
        self.assertIsInstance(decisions[0].intent, WorkshopSelectIntent)
        self.assertIsInstance(decisions[1].intent, WorkshopProduceIntent)

    def test_replan_after_feed_outcome_unlocks_production(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FOOD_3),
            fx.make_cell(
                1, 2, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED
            ),
            fx.make_cell(1, 3, item_id=FRUIT_1),
            orders=(lasso_order(1, {ANIMAL_1: 1, FRUIT_1: 1}),),
        )

        def transition(current: WorkshopState, decision: WorkshopDecision):
            if isinstance(decision.intent, WorkshopFeedIntent):
                return solver_fx.apply_feed(current, decision.intent)
            if isinstance(decision.intent, WorkshopSelectIntent):
                return solver_fx.set_selection(current, decision.intent.cell_id)
            return None

        decisions = solver_fx.run_scenario(
            state, self.catalog, self.policy, transition
        )
        self.assertIsInstance(decisions[0].intent, WorkshopFeedIntent)
        produce = next(
            decision
            for decision in decisions
            if isinstance(decision.intent, WorkshopProduceIntent)
        )
        self.assertEqual(produce.intent.producer_item_id, TRAP)

    def test_replan_after_finite_producer_exhausts(self) -> None:
        # The Fishing Tool produced, then its authored outcome is the
        # exhaustion transform (40206, no rebuild partners): the next
        # decision must not retry the vanished producer.
        state = solver_fx.observed_state(
            fx.make_cell(
                1, 1, item_id=FISHING_TOOL_9, cooldown=WorkshopCooldown.CLEAR
            ),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
            orders=(lasso_order(1, {SEA_CREATURE_1: 1, FRUIT_1: 1}),),
        )

        def transition(current: WorkshopState, decision: WorkshopDecision):
            if isinstance(decision.intent, WorkshopProduceIntent):
                return solver_fx.place_item(current, 1, 40206)
            return None

        decisions = solver_fx.run_scenario(
            state, self.catalog, self.policy, transition
        )
        self.assertIsInstance(decisions[0].intent, WorkshopProduceIntent)
        second = decisions[1]
        self.assertNotIsInstance(second.intent, WorkshopProduceIntent)
        self.assertIsInstance(second.intent, WorkshopStopIntent)

    def test_newly_observed_energy_is_used_directly(self) -> None:
        # After an observed produce outcome the reported energy is used as
        # read — no session arithmetic or forced initial count.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, cooldown=WorkshopCooldown.CLEAR),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
            energy=WorkshopEnergy(current=1, capacity=200),
            orders=(lasso_order(1, {WOOD_10: 1, FRUIT_1: 1}),),
        )
        first = self.plan(state)
        self.assertIsInstance(first.intent, WorkshopProduceIntent)
        after = solver_fx.place_item(state, 3, WOOD_1)
        after = solver_fx.update_state(
            after, energy=WorkshopEnergy(current=99, capacity=200)
        )
        second = self.plan(after)
        self.assertIsInstance(second.intent, WorkshopProduceIntent)


class TestDecisionDiagnostics(PlannerCase):
    def test_decision_carries_goal_and_reservations(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_2),
            fx.make_cell(1, 2, item_id=FRUIT_2),
            fx.make_cell(1, 3, item_id=TREE_4),
            orders=(lasso_order(1, {FRUIT_3: 1, WOOD_10: 1}),),
        )
        decision = self.plan(state)
        self.assertEqual(decision.goal_order_ref, 1)
        self.assertEqual(decision.missing_quantities.get(WOOD_10), 1)
        self.assertEqual(decision.protected_quantities.get(FRUIT_2), 2)
        self.assertIn("est", decision.reason)
        self.assertIn("goal order 1", decision.reason)

    def test_every_returned_intent_is_canonically_legal(self) -> None:
        scenarios = [
            solver_fx.observed_state(
                fx.make_cell(1, 1, item_id=FRUIT_1),
                fx.make_cell(1, 2, item_id=FRUIT_1),
                orders=(chest_order(1, {FRUIT_1: 2}),),
            ),
            solver_fx.observed_state(
                fx.make_cell(1, 1, item_id=FRUIT_2),
                fx.make_cell(1, 2, item_id=FRUIT_2),
                fx.make_cell(1, 3, item_id=TREE_4),
                orders=(lasso_order(1, {FRUIT_3: 1, WOOD_10: 1}),),
            ),
            solver_fx.observed_state(
                fx.make_cell(
                    1, 1, item_id=TREE_4, cooldown=WorkshopCooldown.ACTIVE
                ),
                fx.make_cell(1, 2, item_id=FRUIT_1),
                orders=(lasso_order(1, {WOOD_10: 1, FRUIT_1: 1}),),
            ),
        ]
        for state in scenarios:
            decision = self.plan(state)
            verdict = validate_intent(
                state, decision.intent, self.catalog, self.policy
            )
            self.assertEqual(
                verdict.verdict,
                WorkshopValidationVerdict.LEGAL,
                f"{decision.intent!r} should be legal: {verdict.reason}",
            )


if __name__ == "__main__":
    unittest.main()
