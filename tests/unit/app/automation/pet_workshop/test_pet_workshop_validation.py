"""Unit tests for the canonical ``validate_intent`` (PW03).

Every scenario is a synthetic fixture over the packaged catalog; the tests
exercise the typed legality contract only — LEGAL requires all needed facts
observed, ILLEGAL marks a known prohibition, UNCERTAIN marks a missing fact.
"""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.pet_workshop.policy import default_policy
from pnc_automation.app.automation.pet_workshop.validation import validate_intent
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopActivateIntent,
    WorkshopCellAccess,
    WorkshopCooldown,
    WorkshopEnergy,
    WorkshopFeedIntent,
    WorkshopInspectIntent,
    WorkshopInspectKind,
    WorkshopIntent,
    WorkshopItemStatus,
    WorkshopMergeIntent,
    WorkshopOccupancy,
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
WOOD_10 = fx.WOOD_10
FOOD_3 = fx.FOOD_3
TRAP = fx.TRAP_FEED_LOCKED
ANIMAL_1 = 50101

LEGAL = WorkshopValidationVerdict.LEGAL
ILLEGAL = WorkshopValidationVerdict.ILLEGAL
UNCERTAIN = WorkshopValidationVerdict.UNCERTAIN


def chest_order(order_ref: int, requirements: dict, *, ready=True):
    """One ready, eligible two-piece order rewarded with a chest."""

    return fx.make_order(
        order_ref,
        requirements,
        rewards=(WorkshopOrderReward(WorkshopOrderRewardCategory.CHEST, 1),),
        ready=ready,
    )


class ValidationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_pet_workshop_catalog()
        cls.policy = default_policy()

    def verdict(self, state: WorkshopState, intent: WorkshopIntent):
        return validate_intent(state, intent, self.catalog, self.policy).verdict


class TestSelectValidation(ValidationCase):
    def test_select_usable_occupied_cell(self) -> None:
        state = solver_fx.observed_state(fx.make_cell(1, 1, item_id=TREE_4))
        self.assertEqual(self.verdict(state, WorkshopSelectIntent(1)), LEGAL)

    def test_select_already_selected_cell(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
        )
        self.assertEqual(self.verdict(state, WorkshopSelectIntent(1)), ILLEGAL)

    def test_select_unobserved_cell_is_uncertain(self) -> None:
        state = fx.make_state(cells=())
        self.assertEqual(self.verdict(state, WorkshopSelectIntent(1)), UNCERTAIN)

    def test_select_locked_cell(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, access=WorkshopCellAccess.LOCKED)
        )
        self.assertEqual(self.verdict(state, WorkshopSelectIntent(1)), ILLEGAL)

    def test_select_empty_cell(self) -> None:
        state = solver_fx.observed_state()
        self.assertEqual(self.verdict(state, WorkshopSelectIntent(1)), ILLEGAL)


class TestProduceValidation(ValidationCase):
    def selected_state(self, **cell_kw) -> WorkshopState:
        return solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, **cell_kw),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
        )

    def test_selected_clear_producer_with_space(self) -> None:
        state = self.selected_state(cooldown=WorkshopCooldown.CLEAR)
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, TREE_4)), LEGAL
        )

    def test_produce_unselected_producer(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, cooldown=WorkshopCooldown.CLEAR)
        )
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, TREE_4)), ILLEGAL
        )

    def test_produce_active_cooldown(self) -> None:
        state = self.selected_state(cooldown=WorkshopCooldown.ACTIVE)
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, TREE_4)), ILLEGAL
        )

    def test_produce_unknown_cooldown(self) -> None:
        state = self.selected_state(cooldown=WorkshopCooldown.UNKNOWN)
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, TREE_4)), UNCERTAIN
        )

    def test_produce_zero_energy(self) -> None:
        state = self.selected_state(cooldown=WorkshopCooldown.CLEAR)
        state = solver_fx.update_state(
            state, energy=WorkshopEnergy(current=0, capacity=200)
        )
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, TREE_4)), ILLEGAL
        )

    def test_produce_auto_fusion_mode(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, cooldown=WorkshopCooldown.CLEAR),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
            production_mode=WorkshopProductionMode.AUTO_FUSION,
        )
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, TREE_4)), ILLEGAL
        )

    def test_produce_unknown_mode_is_uncertain(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, cooldown=WorkshopCooldown.CLEAR),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
            production_mode=WorkshopProductionMode.UNKNOWN,
        )
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, TREE_4)), UNCERTAIN
        )

    def test_produce_confirmed_full_board(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=TREE_4, cooldown=WorkshopCooldown.CLEAR),
            *(
                fx.make_cell(row, col, item_id=FRUIT_1)
                for row in range(1, 10)
                for col in range(1, 8)
                if (row, col) != (1, 1)
            ),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
        )
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, TREE_4)), ILLEGAL
        )

    def test_produce_wrong_item_identity(self) -> None:
        state = self.selected_state(cooldown=WorkshopCooldown.CLEAR)
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, FRUIT_1)), ILLEGAL
        )

    def test_produce_non_producer_item(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1, cooldown=WorkshopCooldown.CLEAR),
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=1),
        )
        self.assertEqual(
            self.verdict(state, WorkshopProduceIntent(1, FRUIT_1)), ILLEGAL
        )


class TestMergeValidation(ValidationCase):
    def two_fruits(self, *, orders=(), **kw) -> WorkshopState:
        return solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=orders,
            **kw,
        )

    def test_merge_surplus_pair(self) -> None:
        self.assertEqual(
            self.verdict(self.two_fruits(), WorkshopMergeIntent(1, 2, FRUIT_1)),
            LEGAL,
        )

    def test_merge_exact_reserved_pieces(self) -> None:
        state = self.two_fruits(orders=(chest_order(1, {FRUIT_1: 2}),))
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), ILLEGAL
        )

    def test_merge_reserved_intermediate_advancing_goal(self) -> None:
        # Demand F3 needs F1 intermediates; merging them into F2 advances it.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_3: 1, WOOD_10: 1}),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), LEGAL
        )

    def test_merge_terminal_item(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_5),
            fx.make_cell(1, 2, item_id=FRUIT_5),
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_5)), ILLEGAL
        )

    def test_merge_bubble_piece(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(
                1, 2, item_id=FRUIT_1, item_status=WorkshopItemStatus.BUBBLE
            ),
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), ILLEGAL
        )

    def test_merge_item_identity_mismatch(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_2),
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), ILLEGAL
        )

    def test_merge_unread_status_is_uncertain(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(
                1, 2, item_id=FRUIT_1, item_status=WorkshopItemStatus.UNKNOWN
            ),
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), UNCERTAIN
        )

    def test_merge_ignores_nonparticipating_unobserved_cells(self) -> None:
        # Both merged cells are fully read; unobserved cells elsewhere do
        # not block the merge, while a short-stock submit on the same state
        # stays UNCERTAIN because those cells might hold required pieces.
        order = chest_order(1, {FRUIT_3: 1, 20201: 1})
        state = fx.make_state(
            cells=(
                fx.make_cell(1, 1, item_id=FRUIT_1),
                fx.make_cell(1, 2, item_id=FRUIT_1),
            ),
            order_survey=WorkshopOrderSurvey(
                orders=(order,),
                coverage=WorkshopSurveyCoverage.COMPLETE,
                freshness=WorkshopSurveyFreshness.CURRENT,
            ),
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), LEGAL
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(1)), UNCERTAIN
        )


class TestActivateValidation(ValidationCase):
    def inactive_state(self, *, orders=()) -> WorkshopState:
        return solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(
                1, 2, item_id=FRUIT_1, item_status=WorkshopItemStatus.INACTIVE
            ),
            orders=orders,
        )

    def test_activate_serving_goal(self) -> None:
        # The missing F2 demand makes the activation's successor goal-serving.
        state = self.inactive_state(orders=(chest_order(1, {FRUIT_2: 1, 20201: 1}),))
        self.assertEqual(
            self.verdict(state, WorkshopActivateIntent(1, 2, FRUIT_1)), LEGAL
        )

    def test_activate_target_normal_is_illegal(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_2: 1, FRUIT_1: 1}),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopActivateIntent(1, 2, FRUIT_1)), ILLEGAL
        )

    def test_activate_bubble_target_is_illegal(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(
                1, 2, item_id=FRUIT_1, item_status=WorkshopItemStatus.BUBBLE
            ),
            orders=(chest_order(1, {FRUIT_2: 1, FRUIT_1: 1}),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopActivateIntent(1, 2, FRUIT_1)), ILLEGAL
        )

    def test_activate_serving_nothing_on_open_board(self) -> None:
        state = self.inactive_state(
            orders=(chest_order(1, {WOOD_10: 1, 20201: 1}),)
        )
        self.assertEqual(
            self.verdict(state, WorkshopActivateIntent(1, 2, FRUIT_1)), ILLEGAL
        )


class TestFeedValidation(ValidationCase):
    def feed_state(self, *, orders=(), food_status=WorkshopItemStatus.NORMAL) -> WorkshopState:
        return solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FOOD_3, item_status=food_status),
            fx.make_cell(
                1, 2, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED
            ),
            orders=orders,
        )

    def test_feed_correct_ingredient_serving_goal(self) -> None:
        state = self.feed_state(orders=(chest_order(1, {ANIMAL_1: 1, FRUIT_1: 1}),))
        self.assertEqual(
            self.verdict(state, WorkshopFeedIntent(1, 2, FOOD_3)), LEGAL
        )

    def test_feed_wrong_food_id(self) -> None:
        state = self.feed_state(orders=(chest_order(1, {ANIMAL_1: 1, FRUIT_1: 1}),))
        self.assertEqual(
            self.verdict(state, WorkshopFeedIntent(1, 2, 31101)), ILLEGAL
        )

    def test_feed_normal_producer_is_illegal(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FOOD_3),
            fx.make_cell(1, 2, item_id=TRAP),
            orders=(chest_order(1, {ANIMAL_1: 1, FRUIT_1: 1}),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopFeedIntent(1, 2, FOOD_3)), ILLEGAL
        )

    def test_feed_reserved_food(self) -> None:
        # Food 3 is an exact requirement of the primary order; the Trap is
        # unrelated, so consuming the only food piece is illegal.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FOOD_3),
            fx.make_cell(
                1, 2, item_id=TRAP, item_status=WorkshopItemStatus.FEED_LOCKED
            ),
            orders=(chest_order(1, {FOOD_3: 1, FRUIT_1: 1}),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopFeedIntent(1, 2, FOOD_3)), ILLEGAL
        )


class TestRecycleValidation(ValidationCase):
    def full_board(self, *items: int, orders=()) -> WorkshopState:
        """Confirmed-full board: the authored pieces then unique fillers.

        Fillers draw one copy of every catalog item not already placed, so no
        merge pair exists unless the authored items introduce one.
        """

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

    def test_recycle_allowlisted_terminal_on_full_board(self) -> None:
        state = self.full_board(STATUE_5)
        self.assertEqual(
            self.verdict(state, WorkshopRecycleIntent(1, STATUE_5)), LEGAL
        )

    def test_recycle_rejects_non_allowlisted_item(self) -> None:
        # Animal 5 is terminal but not in the recycling allowlist.
        state = self.full_board(50105)
        self.assertEqual(
            self.verdict(state, WorkshopRecycleIntent(1, 50105)), ILLEGAL
        )

    def test_recycle_rejects_mergeable_item(self) -> None:
        state = self.full_board(FRUIT_1)
        self.assertEqual(
            self.verdict(state, WorkshopRecycleIntent(1, FRUIT_1)), ILLEGAL
        )

    def test_recycle_rejected_on_board_with_space(self) -> None:
        state = solver_fx.observed_state(fx.make_cell(1, 1, item_id=STATUE_5))
        self.assertEqual(
            self.verdict(state, WorkshopRecycleIntent(1, STATUE_5)), ILLEGAL
        )

    def test_recycle_reserved_piece(self) -> None:
        # Statue 5 demanded by the primary order; the single copy is reserved.
        state = self.full_board(
            STATUE_5, orders=(chest_order(1, {STATUE_5: 1, FRUIT_1: 1}),)
        )
        self.assertEqual(
            self.verdict(state, WorkshopRecycleIntent(1, STATUE_5)), ILLEGAL
        )

    def test_recycle_blocked_while_legal_merge_remains(self) -> None:
        # Two F1s form a legal merge pair, which must be used before any
        # restricted recycling is permitted.
        state = self.full_board(STATUE_5, FRUIT_1, FRUIT_1)
        self.assertEqual(
            self.verdict(state, WorkshopRecycleIntent(1, STATUE_5)), ILLEGAL
        )


class TestSubmitValidation(ValidationCase):
    def test_submit_ready_order_with_stock(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_1: 2}),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(1)), LEGAL
        )

    def test_submit_unready_order(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_1: 2}, ready=False),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(1)), ILLEGAL
        )

    def test_submit_unread_ready_flag(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_1: 2}, ready=None),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(1)), UNCERTAIN
        )

    def test_submit_three_piece_order(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_1: 3}),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(1)), ILLEGAL
        )

    def test_submit_short_stock_fully_observed(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            orders=(chest_order(1, {FRUIT_1: 2}),),
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(1)), ILLEGAL
        )

    def test_submit_short_stock_with_unread_cells(self) -> None:
        state = fx.make_state(
            cells=(fx.make_cell(1, 1, item_id=FRUIT_1),),
            order_survey=WorkshopOrderSurvey(
                orders=(chest_order(1, {FRUIT_1: 2}),),
                coverage=WorkshopSurveyCoverage.COMPLETE,
                freshness=WorkshopSurveyFreshness.CURRENT,
            ),
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(1)), UNCERTAIN
        )

    def test_submit_consuming_primary_reservation(self) -> None:
        # Primary needs both F1s; submitting the lower-ranked order would
        # consume one reserved piece.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=20201),
            orders=(
                chest_order(1, {FRUIT_1: 2}),
                chest_order(2, {FRUIT_1: 1, 20201: 1}, ready=True),
            ),
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(2)), ILLEGAL
        )

    def test_submit_surplus_lower_order(self) -> None:
        # Three F1s: primary keeps two, the third safely fills order 2.
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            fx.make_cell(1, 3, item_id=FRUIT_1),
            fx.make_cell(1, 4, item_id=20201),
            orders=(
                chest_order(1, {FRUIT_1: 2}),
                chest_order(2, {FRUIT_1: 1, 20201: 1}, ready=True),
            ),
        )
        self.assertEqual(
            self.verdict(state, WorkshopSubmitOrderIntent(2)), LEGAL
        )


class TestSharedGates(ValidationCase):
    def test_zero_energy_blocks_every_mutation(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            energy=WorkshopEnergy(current=0, capacity=200),
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), ILLEGAL
        )

    def test_excluded_surface_blocks_mutations(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            surface=WorkshopSurfaceKind.EXCLUDED_MODAL,
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), ILLEGAL
        )

    def test_unknown_surface_is_uncertain(self) -> None:
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            surface=WorkshopSurfaceKind.UNKNOWN,
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), UNCERTAIN
        )

    def test_unresolved_goal_context_blocks_reservation_intents(self) -> None:
        # A stale survey leaves the reservation context unknown; merges that
        # could consume protected pieces must not validate as legal.
        survey = WorkshopOrderSurvey(
            orders=(chest_order(1, {FRUIT_1: 2}),),
            coverage=WorkshopSurveyCoverage.COMPLETE,
            freshness=WorkshopSurveyFreshness.STALE,
        )
        state = solver_fx.observed_state(
            fx.make_cell(1, 1, item_id=FRUIT_1),
            fx.make_cell(1, 2, item_id=FRUIT_1),
            survey=survey,
        )
        self.assertEqual(
            self.verdict(state, WorkshopMergeIntent(1, 2, FRUIT_1)), UNCERTAIN
        )

    def test_wait_bound(self) -> None:
        state = solver_fx.observed_state()
        self.assertEqual(
            self.verdict(state, WorkshopWaitIntent(60_000)), LEGAL
        )
        self.assertEqual(
            self.verdict(state, WorkshopWaitIntent(60_001)), ILLEGAL
        )

    def test_inspect_and_stop_always_legal(self) -> None:
        state = solver_fx.observed_state()
        self.assertEqual(
            self.verdict(
                state, WorkshopInspectIntent(WorkshopInspectKind.BOARD)
            ),
            LEGAL,
        )
        self.assertEqual(
            self.verdict(
                state,
                WorkshopStopIntent(WorkshopStopReason.UNRESOLVED_STATE),
            ),
            LEGAL,
        )


if __name__ == "__main__":
    unittest.main()
