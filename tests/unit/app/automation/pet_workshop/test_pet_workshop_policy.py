"""Unit tests for the PW03 policy, allocation, effort and ranking modules.

All states are synthetic fixtures over the packaged catalog; they exercise
the typed policy/solver contracts only and are not live game evidence.
"""

from __future__ import annotations

import unittest
from fractions import Fraction

from pnc_automation.app.automation.pet_workshop.board import BoardFacts, MergeChains
from pnc_automation.app.automation.pet_workshop.effort import (
    allocate_goal,
    estimate_goal,
    useful_units_per_draw,
)
from pnc_automation.app.automation.pet_workshop.goals import select_goals
from pnc_automation.app.automation.pet_workshop.policy import (
    assess_order,
    default_policy,
)
from pnc_automation.app.automation.pet_workshop.rules import goal_context
from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopCellAccess,
    WorkshopCooldown,
    WorkshopItemStatus,
    WorkshopOrder,
    WorkshopOrderReward,
    WorkshopOrderRewardCategory,
    WorkshopOrderSurvey,
    WorkshopSurveyCoverage,
    WorkshopSurveyFreshness,
)
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    load_pet_workshop_catalog,
)
from tests.support.pnc import pet_workshop as fx
from tests.support.pnc import pet_workshop_solver as solver_fx

TREE_1 = 20001
TREE_2 = 20002
TREE_4 = fx.TREE_4
FRUIT_1 = fx.FRUIT_1
FRUIT_2 = 20102
FRUIT_5 = fx.FRUIT_5
STATUE_5 = fx.STATUE_5
WOOD_1 = 20201
WOOD_2 = 20202
WOOD_3 = 20203
WOOD_4 = 20204
WOOD_10 = fx.WOOD_10
BOWL_5 = 30105
FOOD_3 = fx.FOOD_3
FISHING_TOOL_9 = fx.FISHING_TOOL_9
SEA_CREATURE_1 = 41101
TRAP = fx.TRAP_FEED_LOCKED
ANIMAL_1 = 50101
ITEM_CHEST = 60001


def reward(category: WorkshopOrderRewardCategory, quantity: int | None) -> WorkshopOrderReward:
    return WorkshopOrderReward(category, quantity)


class TestDefaultPolicy(unittest.TestCase):
    def test_default_policy_matches_plan_02(self) -> None:
        policy = default_policy()
        self.assertEqual(policy.order_piece_total, 2)
        self.assertEqual(
            policy.reward_priority[0], WorkshopOrderRewardCategory.BEAST_LASSO
        )
        self.assertEqual(policy.recyclable_item_ids, frozenset({FRUIT_5, STATUE_5}))
        self.assertEqual(policy.max_cooldown_wait_ms, 60_000)


class TestAssessOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_pet_workshop_catalog()
        cls.policy = default_policy()

    def assess(self, order: WorkshopOrder):
        return assess_order(order, 0, self.catalog, self.policy)

    def test_three_distinct_pieces_rejected(self) -> None:
        # The ready three-coconut order: total 3 pieces is never a goal.
        order = fx.make_order(1, {FRUIT_1: 1, WOOD_1: 1, STATUE_5: 1})
        assessment = self.assess(order)
        self.assertFalse(assessment.eligible)
        self.assertFalse(assessment.is_goal)

    def test_duplicate_two_piece_accepted(self) -> None:
        order = fx.make_order(
            1,
            {FRUIT_1: 2},
            rewards=(reward(WorkshopOrderRewardCategory.CHEST, 1),),
        )
        assessment = self.assess(order)
        self.assertTrue(assessment.eligible)
        self.assertTrue(assessment.is_goal)

    def test_mixed_two_piece_accepted(self) -> None:
        order = fx.make_order(1, {FRUIT_1: 1, WOOD_1: 1})
        self.assertTrue(self.assess(order).eligible)

    def test_incomplete_card_ineligible(self) -> None:
        order = fx.make_order(
            1, {FRUIT_1: 2}, completeness=RowRecognitionStatus.CLIPPED
        )
        self.assertFalse(self.assess(order).eligible)

    def test_unknown_item_ineligible(self) -> None:
        order = fx.make_order(1, {FRUIT_1: 1, 999999: 1})
        self.assertFalse(self.assess(order).eligible)

    def test_best_policy_reward_category_wins(self) -> None:
        order = fx.make_order(
            1,
            {FRUIT_1: 2},
            rewards=(
                reward(WorkshopOrderRewardCategory.CHEST, 9),
                reward(WorkshopOrderRewardCategory.BEAST_LASSO, 1),
            ),
        )
        assessment = self.assess(order)
        self.assertEqual(assessment.category, WorkshopOrderRewardCategory.BEAST_LASSO)
        self.assertEqual(assessment.category_rank, 0)
        self.assertEqual(assessment.primary_quantity, 1)
        self.assertEqual(assessment.secondary_quantity, 9)

    def test_unrewarded_order_not_a_goal(self) -> None:
        order = fx.make_order(1, {FRUIT_1: 2}, rewards=())
        assessment = self.assess(order)
        self.assertTrue(assessment.eligible)
        self.assertFalse(assessment.is_goal)

    def test_unread_primary_quantity_blocks_ranking(self) -> None:
        order = fx.make_order(
            1,
            {FRUIT_1: 2},
            rewards=(reward(WorkshopOrderRewardCategory.BEAST_LASSO, None),),
        )
        assessment = self.assess(order)
        self.assertTrue(assessment.is_goal)
        self.assertTrue(assessment.ranking_blocked)


class TestBoardFacts(unittest.TestCase):
    def test_partitions_observed_cells(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(
                1, 2, item_id=FRUIT_2, item_status=WorkshopItemStatus.INACTIVE
            ),
            fx.make_cell(
                1, 3, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED
            ),
            fx.make_cell(
                1, 4, item_id=FRUIT_1, item_status=WorkshopItemStatus.BUBBLE
            ),
            fx.make_cell(
                1, 5, item_id=FRUIT_1,
                item_status=WorkshopItemStatus.UNKNOWN,
            ),
        )
        board = BoardFacts(state)
        self.assertEqual(board.normal_cells(FRUIT_1), (1,))
        self.assertEqual(board.inactive_cells(FRUIT_2), (2,))
        self.assertEqual(board.feed_locked_cells(TRAP), (3,))
        self.assertEqual(board.bubble_cells(FRUIT_1), (4,))
        self.assertEqual(board.unread_piece_cells, (5,))
        self.assertFalse(board.board_full)

    def test_board_full_tri_state(self) -> None:
        full = solver_fx.observed_state(
            *(
                fx.make_cell(row, col, item_id=FRUIT_1)
                for row in range(1, 10)
                for col in range(1, 8)
            )
        )
        self.assertTrue(BoardFacts(full).board_full)
        with_empty = solver_fx.observed_state(fx.make_cell(1, 1, item_id=FRUIT_1))
        self.assertFalse(BoardFacts(with_empty).board_full)
        unobserved = fx.make_state(cells=(fx.make_cell(1, 1, item_id=FRUIT_1),))
        self.assertIsNone(BoardFacts(unobserved).board_full)

    def test_locked_cells_never_count_as_stock(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1, access=WorkshopCellAccess.LOCKED)
        )
        board = BoardFacts(state)
        self.assertEqual(board.normal_cells(FRUIT_1), ())
        self.assertEqual(board.normal_count(FRUIT_1), 0)


class TestMergeChains(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chains = MergeChains(load_pet_workshop_catalog())

    def test_linear_successor_and_terminal(self) -> None:
        self.assertEqual(self.chains.successor(FRUIT_1), FRUIT_2)
        self.assertIsNone(self.chains.successor(FRUIT_5))
        self.assertTrue(self.chains.is_terminal(FRUIT_5))

    def test_unit_values_are_binary(self) -> None:
        self.assertEqual(self.chains.unit_value(FRUIT_1), 1)
        self.assertEqual(self.chains.unit_value(WOOD_10), 512)
        self.assertEqual(self.chains.unit_value(999999), 0)

    def test_ancestors_highest_first(self) -> None:
        ancestors = self.chains.ancestors(WOOD_10)
        self.assertEqual(ancestors[0], 20209)
        self.assertEqual(ancestors[-1], WOOD_1)

    def test_closure_includes_self(self) -> None:
        self.assertIn(WOOD_10, self.chains.closure(WOOD_10))
        self.assertIn(WOOD_1, self.chains.closure(WOOD_10))
        self.assertNotIn(FRUIT_1, self.chains.closure(WOOD_10))


class TestAllocateGoal(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_pet_workshop_catalog()
        cls.chains = MergeChains(cls.catalog)

    def allocate(self, requirements, *cells):
        board = BoardFacts(solver_fx.observed_state(*cells))
        return allocate_goal(requirements, board, self.chains, self.catalog)

    def test_exact_stock_reserved_first(self) -> None:
        allocation = self.allocate(
            {FRUIT_1: 2},
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=FRUIT_1),
        )
        self.assertTrue(allocation.satisfied)
        self.assertEqual(allocation.protected_exact[FRUIT_1], 2)
        self.assertEqual(allocation.residual_units, 0)

    def test_lower_tier_intermediates_build_demand(self) -> None:
        allocation = self.allocate(
            {WOOD_4: 1},
            fx.make_cell(1, 1, item_id=WOOD_3),
            fx.make_cell(1, 2, item_id=WOOD_2),
            fx.make_cell(1, 3, item_id=WOOD_1),
            fx.make_cell(1, 4, item_id=WOOD_1),
        )
        self.assertTrue(allocation.covered_by_stock)
        self.assertEqual(allocation.free_actions, 3)
        self.assertEqual(allocation.protected_intermediate[WOOD_1], 2)

    def test_no_stock_leaves_full_residual(self) -> None:
        # Regression: an empty taken-set must keep the entire demand as
        # residual units, not collapse it to zero.
        allocation = self.allocate({WOOD_10: 1})
        demand = allocation.demands[0]
        self.assertEqual(demand.missing, 1)
        self.assertEqual(demand.residual_units, 512)
        self.assertFalse(allocation.covered_by_stock)

    def test_higher_tier_stock_is_never_split_backwards(self) -> None:
        allocation = self.allocate(
            {FRUIT_1: 1}, fx.make_cell(1, 1, item_id=FRUIT_5)
        )
        demand = allocation.demands[0]
        self.assertEqual(demand.normal_exact, 0)
        self.assertEqual(demand.residual_units, 1)

    def test_feed_locked_piece_counts_only_with_food_on_board(self) -> None:
        with_food = self.allocate(
            {TRAP: 1},
            fx.make_cell(1, 1, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED),
            fx.make_cell(1, 2, item_id=FOOD_3),
        )
        self.assertEqual(with_food.demands[0].feedable_exact, 1)
        self.assertEqual(with_food.free_actions, 1)
        self.assertEqual(with_food.protected_intermediate[FOOD_3], 1)
        without_food = self.allocate(
            {TRAP: 1},
            fx.make_cell(1, 1, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED),
        )
        self.assertEqual(without_food.demands[0].feedable_exact, 0)
        self.assertEqual(without_food.demands[0].missing, 1)
        self.assertFalse(without_food.covered_by_stock)

    def test_inactive_piece_builds_through_activation(self) -> None:
        # An inactive F2 plus a normal partner produces F3 — dead stock is
        # real progress, not residual production.
        allocation = self.allocate(
            {20103: 1},
            fx.make_cell(1, 1, item_id=FRUIT_2),
            fx.make_cell(
                1, 2, item_id=FRUIT_2, item_status=WorkshopItemStatus.INACTIVE
            ),
        )
        self.assertTrue(allocation.covered_by_stock)
        self.assertEqual(allocation.free_actions, 1)


class TestUsefulUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_pet_workshop_catalog()
        cls.chains = MergeChains(cls.catalog)

    def useful(self, producer_item: int, target: int) -> Fraction:
        producer = self.catalog.producer_for(producer_item)
        return useful_units_per_draw(producer, target, self.chains, self.catalog)

    def test_tree_1_drops_only_fruit(self) -> None:
        self.assertEqual(self.useful(TREE_1, FRUIT_1), Fraction(1))
        self.assertEqual(self.useful(TREE_1, WOOD_1), Fraction(0))

    def test_mixed_output_counts_each_chain_weight(self) -> None:
        self.assertEqual(self.useful(TREE_2, FRUIT_1), Fraction(550, 1000))
        self.assertEqual(self.useful(TREE_2, WOOD_1), Fraction(450, 1000))

    def test_higher_tier_output_is_never_counted_for_lower_demand(self) -> None:
        # Tree 4 drops W1/W2/W3; demand for W1 can use only the W1 share —
        # a higher-tier piece can never be split back into lower-tier units.
        self.assertEqual(self.useful(TREE_4, WOOD_1), Fraction(315, 1000))

    def test_deep_demand_counts_lower_tier_unit_values(self) -> None:
        self.assertEqual(self.useful(TREE_4, WOOD_10), Fraction(675, 1000))


class TestEstimateGoal(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_pet_workshop_catalog()
        cls.chains = MergeChains(cls.catalog)

    def estimate(self, requirements, *cells):
        board = BoardFacts(solver_fx.observed_state(*cells))
        allocation = allocate_goal(requirements, board, self.chains, self.catalog)
        return estimate_goal(allocation, board, self.chains, self.catalog)

    def test_stocked_goal_costs_zero(self) -> None:
        effort = self.estimate(
            {FRUIT_1: 2},
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
        )
        self.assertEqual(effort.energy, Fraction(0))
        self.assertFalse(effort.conservative)

    def test_production_estimate_uses_expected_units(self) -> None:
        effort = self.estimate(
            {WOOD_2: 1, FRUIT_1: 1},
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=TREE_4),
        )
        # W2 needs 2 base units; Tree 4 yields W1/W2 wood at
        # (315*1 + 90*2)/1000 = 99/200 units per draw (W3 is unsplittable).
        expected = Fraction(2 * 200, 99)
        self.assertEqual(effort.energy, expected)

    def test_one_producer_serving_two_demands_is_conservative(self) -> None:
        # The documented A/B proxy: Tree 2 drops fruit and wood, so the
        # additive estimate counts draws twice where the exact joint
        # expectation is lower.
        effort = self.estimate(
            {FRUIT_1: 1, WOOD_1: 1},
            fx.make_cell(1, 1, item_id=TREE_2),
        )
        self.assertTrue(effort.conservative)
        self.assertEqual(effort.energy, Fraction(20, 11) + Fraction(20, 9))

    def test_synthetic_equal_split_proxy_is_4_versus_exact_3(self) -> None:
        # Plan 02's documented estimator limit: a synthetic generator
        # emitting A or B at 50:50 prices one of each at 2 + 2 = 4 draws in
        # the additive proxy, while the exact joint expectation is 3.
        document = {
            "provenance": {
                "packaged_build": "test",
                "generator": "test",
                "source_tables": {},
            },
            "board": {"columns": 2, "rows": 2},
            "activity": {
                "energy_item_id": 44009010,
                "energy_capacity": 200,
                "production_energy_cost": 1,
                "energy_regen_ms": 300000,
                "cooldown_ms": 20000,
                "cooldown_skip_cost": 50,
                "assist_cost": 2,
                "assist_level": 999,
                "buy_add_productivity": 1,
                "buy_count": 0,
                "buy_costs": [],
                "item_limit_raw": "",
                "item_time_ms": 120000,
                "description": "",
            },
            "items": [
                {
                    "id": 900001, "name": "Gen", "tips": "", "icon": "g",
                    "tier": 1, "type": 1, "sub_type": 1, "sort": 0,
                    "get_type": 1, "exp": 0, "merge_successor_id": None,
                    "unlock_cost": 0, "recoverable": False,
                    "recycle_reward": None,
                },
                {
                    "id": 900002, "name": "A", "tips": "", "icon": "a",
                    "tier": 1, "type": 2, "sub_type": 0, "sort": 0,
                    "get_type": 11, "exp": 0, "merge_successor_id": None,
                    "unlock_cost": 0, "recoverable": True,
                    "recycle_reward": None,
                },
                {
                    "id": 900003, "name": "B", "tips": "", "icon": "b",
                    "tier": 1, "type": 2, "sub_type": 0, "sort": 0,
                    "get_type": 11, "exp": 0, "merge_successor_id": None,
                    "unlock_cost": 0, "recoverable": True,
                    "recycle_reward": None,
                },
            ],
            "producers": [
                {
                    "item_id": 900001, "group_id": 7, "worker_type": 1,
                    "num": 30, "max_num": 0, "cooldown_ms": 30000,
                    "change_item_id": None, "feed_item_id": None, "assist": 0,
                },
            ],
            "drop_groups": {
                "7": [
                    {"item_id": 900002, "weight": 500},
                    {"item_id": 900003, "weight": 500},
                ],
            },
            "grid_cells": [
                {
                    "cell_id": 1, "position": 1, "unlock_level": 0,
                    "unlock_type": 2, "seed_item_ids": [900001],
                },
            ],
            "workshop_levels": [],
        }
        catalog = PetWorkshopCatalog(document)
        chains = MergeChains(catalog)
        board = BoardFacts(
            solver_fx.observed_state(fx.make_cell(1, 1, item_id=900001))
        )
        allocation = allocate_goal({900002: 1, 900003: 1}, board, chains, catalog)
        effort = estimate_goal(allocation, board, chains, catalog)
        self.assertTrue(effort.conservative)
        self.assertEqual(effort.energy, Fraction(4))

    def test_finite_producer_marks_uncertainty_not_illegality(self) -> None:
        effort = self.estimate(
            {SEA_CREATURE_1: 1, FRUIT_1: 1},
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FISHING_TOOL_9),
        )
        self.assertTrue(effort.uncertain)
        self.assertIsNotNone(effort.energy)

    def test_feed_ingredient_is_never_free(self) -> None:
        # Animal 1 needs the feed-locked Trap; the missing Food 3 is priced
        # through Bowl 5 rather than assumed.
        effort = self.estimate(
            {ANIMAL_1: 1, FRUIT_1: 1},
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(
                1, 2, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED
            ),
            fx.make_cell(1, 3, item_id=BOWL_5),
        )
        self.assertIsNotNone(effort.energy)
        trap_only = Fraction(1000, 650)
        self.assertGreater(effort.energy, trap_only)

    def test_unproducible_demand_is_infeasible(self) -> None:
        # No producer drops the Trap itself and none is on the board.
        effort = self.estimate({TRAP: 1, FRUIT_1: 1}, fx.make_cell(1, 1, item_id=FRUIT_1))
        self.assertIsNone(effort.energy)

    def test_producer_rebuild_path_is_a_supported_estimate(self) -> None:
        # Two Fishing Tool 8s rebuild Tool 9, then sea creatures produce.
        effort = self.estimate(
            {SEA_CREATURE_1: 1, FRUIT_1: 1},
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=40208),
            fx.make_cell(1, 3, item_id=40208),
        )
        self.assertIsNotNone(effort.energy)
        sea = next(
            effort for effort in effort.demand_efforts
            if effort.item_id == SEA_CREATURE_1
        )
        self.assertEqual(sea.producer_item_id, FISHING_TOOL_9)
        self.assertEqual(sea.path_mode, "build")


class TestSelectGoals(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_pet_workshop_catalog()
        cls.policy = default_policy()

    def select(self, *cells, orders=(), survey=None):
        state = solver_fx.observed_state(*cells, orders=orders, survey=survey)
        return select_goals(state, self.catalog, self.policy)

    def lasso(self, qty):
        return reward(WorkshopOrderRewardCategory.BEAST_LASSO, qty)

    def test_incomplete_survey_blocks_all_goals(self) -> None:
        survey = WorkshopOrderSurvey(
            orders=(fx.make_order(1, {FRUIT_1: 2}, rewards=(self.lasso(1),)),),
            coverage=WorkshopSurveyCoverage.PARTIAL,
            freshness=WorkshopSurveyFreshness.CURRENT,
        )
        selection = self.select(survey=survey)
        self.assertFalse(selection.survey_ok)
        self.assertIsNone(selection.primary)

    def test_zero_cost_goal_beats_larger_positive_reward(self) -> None:
        # Order 2 offers triple the lassos but needs Wood 10 production; the
        # mergeable Fruit-3 order is free and must rank first.
        selection = self.select(
            fx.make_cell(1, 1, item_id=FRUIT_2),
            fx.make_cell(1, 2, item_id=FRUIT_2),
            fx.make_cell(1, 3, item_id=TREE_4),
            orders=(
                fx.make_order(1, {20103: 1, WOOD_1: 1}, rewards=(self.lasso(1),)),
                fx.make_order(2, {WOOD_10: 1, FRUIT_1: 1}, rewards=(self.lasso(3),)),
            ),
        )
        self.assertEqual(selection.primary.order_ref, 1)

    def test_positive_cost_ratio_decides_inside_category(self) -> None:
        # Same lasso reward; the cheap Wood-2 order beats the Wood-10 order.
        selection = self.select(
            fx.make_cell(1, 1, item_id=TREE_4),
            orders=(
                fx.make_order(1, {WOOD_10: 1, FRUIT_1: 1}, rewards=(self.lasso(1),)),
                fx.make_order(2, {WOOD_2: 1, FRUIT_1: 1}, rewards=(self.lasso(1),)),
            ),
        )
        self.assertEqual(selection.primary.order_ref, 2)

    def test_higher_category_always_wins(self) -> None:
        # A free chest order never outranks an unfinished lasso order.
        selection = self.select(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=TREE_4),
            orders=(
                fx.make_order(
                    1,
                    {FRUIT_1: 2},
                    rewards=(reward(WorkshopOrderRewardCategory.CHEST, 9),),
                ),
                fx.make_order(2, {WOOD_10: 1, FRUIT_1: 1}, rewards=(self.lasso(1),)),
            ),
        )
        self.assertEqual(selection.primary.order_ref, 2)

    def test_unread_reward_quantity_requests_inspection(self) -> None:
        selection = self.select(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(
                fx.make_order(1, {FRUIT_1: 2}, rewards=(self.lasso(None),)),
            ),
        )
        self.assertEqual(selection.inspect_order_ref, 1)
        self.assertEqual(selection.primary.order_ref, 1)

    def test_tied_zero_cost_goals_inspect_unread_secondary(self) -> None:
        selection = self.select(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=FRUIT_2),
            fx.make_cell(1, 4, item_id=FRUIT_2),
            orders=(
                fx.make_order(
                    1,
                    {FRUIT_1: 2},
                    rewards=(
                        self.lasso(1),
                        reward(WorkshopOrderRewardCategory.CHEST, None),
                    ),
                ),
                fx.make_order(
                    2,
                    {FRUIT_2: 2},
                    rewards=(
                        self.lasso(1),
                        reward(WorkshopOrderRewardCategory.CHEST, 5),
                    ),
                ),
            ),
        )
        self.assertEqual(selection.inspect_order_ref, 1)


class TestGoalContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_pet_workshop_catalog()
        cls.chains = MergeChains(cls.catalog)
        cls.policy = default_policy()

    def context(self, *cells, orders=()):
        state = solver_fx.observed_state(*cells, orders=orders)
        return goal_context(
            state, BoardFacts(state), self.chains, self.catalog, self.policy
        )

    def test_produce_targets_cover_only_missing_demands(self) -> None:
        ctx = self.context(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            orders=(
                fx.make_order(
                    1,
                    {WOOD_2: 1, FRUIT_1: 1},
                    rewards=(WorkshopOrderReward(WorkshopOrderRewardCategory.CHEST, 1),),
                ),
            ),
        )
        self.assertEqual(ctx.produce_targets, frozenset({WOOD_2}))
        self.assertEqual(ctx.protected_exact.get(FRUIT_1), 1)

    def test_feed_locked_demand_produces_its_food_target(self) -> None:
        ctx = self.context(
            fx.make_cell(
                1, 1, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED
            ),
            orders=(
                fx.make_order(
                    1,
                    {ANIMAL_1: 1, FRUIT_1: 1},
                    rewards=(
                        WorkshopOrderReward(WorkshopOrderRewardCategory.CHEST, 1),
                    ),
                ),
            ),
        )
        self.assertIn(FOOD_3, ctx.aux_targets)
        self.assertIn(BOWL_5, ctx.needed_producers)


if __name__ == "__main__":
    unittest.main()
