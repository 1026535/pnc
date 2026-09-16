"""Unit tests for the canonical Pet Workshop shared models and contracts.

All states and transitions are synthetic fixtures; they exercise the typed
contract only and are not live game evidence.
"""

from __future__ import annotations

import typing
import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from pnc_automation.app.pnc.domain.observation import Observation, RowRecognitionStatus
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopActivateIntent,
    WorkshopCell,
    WorkshopCellAccess,
    WorkshopCooldown,
    WorkshopDecision,
    WorkshopEnergy,
    WorkshopFeedIntent,
    WorkshopInspectIntent,
    WorkshopInspectKind,
    WorkshopIntent,
    WorkshopIntentKind,
    WorkshopIntentValidation,
    WorkshopItemStatus,
    WorkshopMergeIntent,
    WorkshopObservation,
    WorkshopOccupancy,
    WorkshopOrder,
    WorkshopOrderReward,
    WorkshopOrderRewardCategory,
    WorkshopOrderSurvey,
    WorkshopOrderView,
    WorkshopPlanNext,
    WorkshopPolicy,
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
    WorkshopValidateIntent,
    WorkshopValidationVerdict,
    WorkshopView,
    WorkshopWaitIntent,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    PetWorkshopCatalogError,
)
from pnc_automation.core.vision.image.models import Bounds
from tests.support.pnc import pet_workshop as workshop_fixtures


class WorkshopCellTests(unittest.TestCase):
    """Cell facts keep access, occupancy, and item status independent."""

    def test_occupied_cell_with_status_and_cooldown(self) -> None:
        cell = workshop_fixtures.make_cell(
            4, 3,
            item_id=workshop_fixtures.TREE_4,
            cooldown=WorkshopCooldown.ACTIVE,
        )
        self.assertEqual(cell.cell_id, (4 - 1) * 7 + 3)
        self.assertEqual(cell.occupancy, WorkshopOccupancy.OCCUPIED)
        self.assertEqual(cell.item_status, WorkshopItemStatus.NORMAL)
        self.assertEqual(cell.cooldown, WorkshopCooldown.ACTIVE)

    def test_item_status_variants_stay_representable(self) -> None:
        for status in (
            WorkshopItemStatus.NORMAL,
            WorkshopItemStatus.INACTIVE,
            WorkshopItemStatus.BUBBLE,
            WorkshopItemStatus.FEED_LOCKED,
            WorkshopItemStatus.UNKNOWN,
        ):
            with self.subTest(status=status):
                cell = workshop_fixtures.make_cell(1, 1, item_id=workshop_fixtures.FRUIT_1, item_status=status)
                self.assertEqual(cell.item_status, status)

    def test_known_empty_cell_carries_no_item_facts(self) -> None:
        cell = workshop_fixtures.make_cell(
            1, 1, occupancy=WorkshopOccupancy.EMPTY, item_status=None,
        )
        self.assertIsNone(cell.item_id)
        self.assertIsNone(cell.item_status)

    def test_occupied_cell_may_have_unread_item_identity(self) -> None:
        cell = workshop_fixtures.make_cell(
            1, 1, item_id=None, item_status=WorkshopItemStatus.UNKNOWN,
        )
        self.assertEqual(cell.occupancy, WorkshopOccupancy.OCCUPIED)
        self.assertIsNone(cell.item_id)

    def test_invalid_coordinates_and_cell_ids_fail(self) -> None:
        for bad in (
            {"cell_id": 0, "row": 1, "column": 1},
            {"cell_id": 1, "row": 0, "column": 1},
            {"cell_id": 1, "row": 1, "column": 0},
            {"cell_id": -3, "row": 1, "column": 1},
            {"cell_id": True, "row": 1, "column": 1},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    WorkshopCell(**bad)

    def test_empty_cell_with_item_facts_fails(self) -> None:
        with self.assertRaises(ValueError):
            workshop_fixtures.make_cell(
                1, 1,
                occupancy=WorkshopOccupancy.EMPTY,
                item_id=workshop_fixtures.FRUIT_1,
                item_status=None,
            )

    def test_non_empty_cell_requires_a_status(self) -> None:
        with self.assertRaises(ValueError):
            workshop_fixtures.make_cell(1, 1, item_id=workshop_fixtures.FRUIT_1, item_status=None)

    def test_cells_are_immutable(self) -> None:
        cell = workshop_fixtures.make_cell(1, 1, item_id=workshop_fixtures.FRUIT_1)
        with self.assertRaises(FrozenInstanceError):
            cell.item_id = workshop_fixtures.FRUIT_5  # type: ignore[misc]


class WorkshopSelectionTests(unittest.TestCase):
    """Selection distinguishes a known cell, known-none, and unknown."""

    def test_known_selected_none_and_unknown_are_distinct(self) -> None:
        selected = WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=5)
        none = WorkshopSelection(WorkshopSelectionKind.NONE)
        unknown = WorkshopSelection(WorkshopSelectionKind.UNKNOWN)
        self.assertEqual(selected.cell_id, 5)
        self.assertIsNone(none.cell_id)
        self.assertIsNone(unknown.cell_id)
        self.assertNotEqual(none.kind, unknown.kind)

    def test_selected_without_cell_fails(self) -> None:
        with self.assertRaises(ValueError):
            WorkshopSelection(WorkshopSelectionKind.SELECTED)

    def test_non_selected_with_cell_fails(self) -> None:
        for kind in (WorkshopSelectionKind.NONE, WorkshopSelectionKind.UNKNOWN):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    WorkshopSelection(kind, cell_id=5)


class WorkshopEnergyTests(unittest.TestCase):
    """Energy keeps zero, unknown, and over-cap readings distinct."""

    def test_zero_energy_is_reliably_zero(self) -> None:
        energy = WorkshopEnergy(current=0, capacity=200)
        self.assertTrue(energy.known)
        self.assertTrue(energy.is_zero)

    def test_unknown_energy_is_never_zero(self) -> None:
        energy = WorkshopEnergy(current=None, capacity=None)
        self.assertFalse(energy.known)
        self.assertFalse(energy.is_zero)

    def test_over_cap_reading_is_valid(self) -> None:
        energy = WorkshopEnergy(current=250, capacity=200)
        self.assertEqual(energy.current, 250)

    def test_negative_or_typed_bad_readings_fail(self) -> None:
        for bad in (
            {"current": -1},
            {"current": 1.5},
            {"capacity": 0},
            {"capacity": -5},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    WorkshopEnergy(**bad)


class WorkshopOrderTests(unittest.TestCase):
    """Orders preserve quantities, coverage, rewards, and readiness."""

    def test_duplicate_ingredient_quantity_is_preserved(self) -> None:
        order = workshop_fixtures.make_order(1, {workshop_fixtures.FRUIT_1: 2})
        self.assertEqual(order.total_pieces, 2)
        self.assertEqual(order.requirements[workshop_fixtures.FRUIT_1], 2)

    def test_three_piece_orders_stay_representable(self) -> None:
        order = workshop_fixtures.make_order(
            1,
            {workshop_fixtures.WOOD_10: 1, workshop_fixtures.FRUIT_1: 2},
            rewards=(WorkshopOrderReward(WorkshopOrderRewardCategory.BEAST_LASSO, 2),),
        )
        self.assertEqual(order.total_pieces, 3)

    def test_clipped_order_keeps_partial_requirements(self) -> None:
        order = workshop_fixtures.make_order(
            1,
            {workshop_fixtures.WOOD_10: 1},
            completeness=RowRecognitionStatus.CLIPPED,
            ready=None,
        )
        self.assertEqual(order.completeness, RowRecognitionStatus.CLIPPED)
        self.assertIsNone(order.ready)

    def test_unknown_and_other_reward_categories_are_representable(self) -> None:
        order = workshop_fixtures.make_order(
            1,
            {workshop_fixtures.FRUIT_1: 1},
            rewards=(
                WorkshopOrderReward(WorkshopOrderRewardCategory.OTHER, label="mystery box"),
                WorkshopOrderReward(WorkshopOrderRewardCategory.UNKNOWN),
            ),
        )
        self.assertEqual(order.rewards[0].quantity, None)
        self.assertEqual(order.rewards[1].category, WorkshopOrderRewardCategory.UNKNOWN)

    def test_requirement_map_is_frozen_and_positive(self) -> None:
        order = workshop_fixtures.make_order(1, {workshop_fixtures.FRUIT_1: 2})
        self.assertIsInstance(order.requirements, MappingProxyType)
        for bad in ({0: 1}, {workshop_fixtures.FRUIT_1: 0}, {workshop_fixtures.FRUIT_1: -2}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    workshop_fixtures.make_order(1, bad)

    def test_invalid_refs_and_ready_flags_fail(self) -> None:
        with self.assertRaises(ValueError):
            workshop_fixtures.make_order(0, {workshop_fixtures.FRUIT_1: 1})
        with self.assertRaises(TypeError):
            workshop_fixtures.make_order(1, {workshop_fixtures.FRUIT_1: 1}, ready="yes")  # type: ignore[arg-type]

    def test_survey_rejects_duplicate_order_refs(self) -> None:
        order = workshop_fixtures.make_order(1, {workshop_fixtures.FRUIT_1: 1})
        with self.assertRaises(ValueError):
            WorkshopOrderSurvey(orders=(order, order))

    def test_survey_coverage_and_freshness_are_typed(self) -> None:
        survey = WorkshopOrderSurvey(
            orders=(),
            coverage=WorkshopSurveyCoverage.PARTIAL,
            freshness=WorkshopSurveyFreshness.STALE,
        )
        self.assertEqual(survey.coverage, WorkshopSurveyCoverage.PARTIAL)
        self.assertEqual(survey.freshness, WorkshopSurveyFreshness.STALE)
        with self.assertRaises(TypeError):
            WorkshopOrderSurvey(coverage="complete")  # type: ignore[arg-type]


class WorkshopStateTests(unittest.TestCase):
    """The logical state validates board consistency and keeps partial reads."""

    def test_partial_recognition_keeps_unobserved_positions(self) -> None:
        state = workshop_fixtures.make_state(
            cells=(
                workshop_fixtures.make_cell(1, 1, item_id=workshop_fixtures.TREE_4),
                workshop_fixtures.make_cell(9, 7, occupancy=WorkshopOccupancy.EMPTY, item_status=None),
            ),
        )
        self.assertEqual(state.observed_cell_ids, frozenset({1, 63}))
        self.assertEqual(len(state.unobserved_cell_ids), 61)
        self.assertEqual(state.cell(1).item_id, workshop_fixtures.TREE_4)
        self.assertIsNone(state.cell(2))
        self.assertIs(state.cell_at(9, 7), state.cell(63))

    def test_cell_address_must_match_board_coordinates(self) -> None:
        board = workshop_fixtures.board_layout()
        bad_cell = WorkshopCell(
            cell_id=board.cell_id(2, 1) + 1,
            row=2,
            column=1,
            occupancy=WorkshopOccupancy.EMPTY,
        )
        with self.assertRaises(ValueError):
            WorkshopState(board=board, cells=(bad_cell,))

    def test_out_of_board_coordinates_fail_via_layout_owner(self) -> None:
        with self.assertRaises(PetWorkshopCatalogError):
            workshop_fixtures.make_cell(10, 1)

    def test_duplicate_observed_cells_fail(self) -> None:
        cell = workshop_fixtures.make_cell(1, 1)
        with self.assertRaises(ValueError):
            workshop_fixtures.make_state(cells=(cell, cell))

    def test_selection_must_stay_on_the_board(self) -> None:
        with self.assertRaises(ValueError):
            workshop_fixtures.make_state(
                selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, cell_id=64),
            )

    def test_excluded_surface_and_production_mode_stay_representable(self) -> None:
        state = workshop_fixtures.make_state(
            surface=WorkshopSurfaceKind.EXCLUDED_MODAL,
            production_mode=WorkshopProductionMode.AUTO_FUSION,
        )
        self.assertEqual(state.surface, WorkshopSurfaceKind.EXCLUDED_MODAL)
        self.assertEqual(state.production_mode, WorkshopProductionMode.AUTO_FUSION)

    def test_board_layout_must_be_the_catalog_owner_type(self) -> None:
        with self.assertRaises(TypeError):
            WorkshopState(board={"columns": 7, "rows": 9})  # type: ignore[arg-type]


class WorkshopViewTests(unittest.TestCase):
    """The measured view validates geometry against the paired state."""

    def test_view_pairs_measured_bounds_with_state(self) -> None:
        state = workshop_fixtures.make_state(
            cells=(workshop_fixtures.make_cell(5, 4, item_id=workshop_fixtures.FRUIT_1),),
            order_survey=WorkshopOrderSurvey(
                orders=(workshop_fixtures.make_order(2, {workshop_fixtures.FRUIT_1: 1}, ready=True),),
            ),
        )
        observation = workshop_fixtures.make_observation(state, submit_refs=(2,))
        cell_id = state.board.cell_id(5, 4)
        self.assertIsNotNone(observation.view.cell_bounds_for(cell_id))
        order_view = observation.view.order_view(2)
        self.assertIsNotNone(order_view)
        self.assertIsNotNone(order_view.submit_bounds)

    def test_cell_bounds_outside_the_board_fail(self) -> None:
        state = workshop_fixtures.make_state()
        view = WorkshopView(cell_bounds={99: Bounds(x=0, y=0, width=10, height=10)})
        with self.assertRaises(ValueError):
            WorkshopObservation(state=state, view=view)

    def test_order_view_without_surveyed_order_fails(self) -> None:
        state = workshop_fixtures.make_state()
        view = WorkshopView(
            order_views=(WorkshopOrderView(order_ref=7, portrait_bounds=Bounds(x=0, y=0, width=5, height=5)),),
        )
        with self.assertRaises(ValueError):
            WorkshopObservation(state=state, view=view)

    def test_view_rejects_non_bounds_geometry(self) -> None:
        with self.assertRaises(TypeError):
            WorkshopView(cell_bounds={1: (0, 0, 10, 10)})  # type: ignore[dict-item]
        with self.assertRaises(TypeError):
            WorkshopView(recycle_control_bounds=(0, 0, 10, 10))  # type: ignore[arg-type]


class WorkshopIntentTests(unittest.TestCase):
    """Intents carry typed logical targets and reject malformed ones."""

    def test_every_variant_exposes_its_kind_tag(self) -> None:
        intents = (
            (WorkshopSelectIntent(cell_id=1), WorkshopIntentKind.SELECT),
            (WorkshopProduceIntent(cell_id=1, producer_item_id=workshop_fixtures.TREE_4), WorkshopIntentKind.PRODUCE),
            (WorkshopMergeIntent(source_cell_id=1, target_cell_id=2, item_id=workshop_fixtures.FRUIT_1), WorkshopIntentKind.MERGE),
            (WorkshopActivateIntent(source_cell_id=1, target_cell_id=2, item_id=workshop_fixtures.FRUIT_1), WorkshopIntentKind.ACTIVATE),
            (WorkshopFeedIntent(food_cell_id=1, producer_cell_id=2, food_item_id=workshop_fixtures.FOOD_3), WorkshopIntentKind.FEED),
            (WorkshopRecycleIntent(cell_id=1, item_id=workshop_fixtures.FRUIT_5), WorkshopIntentKind.RECYCLE),
            (WorkshopSubmitOrderIntent(order_ref=1), WorkshopIntentKind.SUBMIT_ORDER),
            (WorkshopInspectIntent(need=WorkshopInspectKind.ORDER_SURVEY), WorkshopIntentKind.INSPECT),
            (WorkshopWaitIntent(max_wait_ms=60_000), WorkshopIntentKind.WAIT),
            (WorkshopStopIntent(reason=WorkshopStopReason.ZERO_ENERGY), WorkshopIntentKind.STOP),
        )
        for intent, kind in intents:
            with self.subTest(kind=kind):
                self.assertEqual(intent.kind, kind)

    def test_pair_intents_reject_a_single_cell(self) -> None:
        for build in (
            lambda: WorkshopMergeIntent(source_cell_id=1, target_cell_id=1, item_id=workshop_fixtures.FRUIT_1),
            lambda: WorkshopActivateIntent(source_cell_id=1, target_cell_id=1, item_id=workshop_fixtures.FRUIT_1),
            lambda: WorkshopFeedIntent(food_cell_id=1, producer_cell_id=1, food_item_id=workshop_fixtures.FOOD_3),
        ):
            with self.subTest(build=build):
                with self.assertRaises(ValueError):
                    build()

    def test_inspect_subjects_match_their_need(self) -> None:
        WorkshopInspectIntent(need=WorkshopInspectKind.ORDER_CONTENTS, order_ref=3)
        WorkshopInspectIntent(need=WorkshopInspectKind.CELL_STATE, cell_id=3)
        for need, kwargs in (
            (WorkshopInspectKind.ORDER_CONTENTS, {"cell_id": 1}),
            (WorkshopInspectKind.ORDER_CONTENTS, {}),
            (WorkshopInspectKind.CELL_STATE, {"order_ref": 1}),
            (WorkshopInspectKind.CELL_STATE, {}),
            (WorkshopInspectKind.ORDER_SURVEY, {"cell_id": 1}),
            (WorkshopInspectKind.BOARD, {"order_ref": 1}),
        ):
            with self.subTest(need=need, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    WorkshopInspectIntent(need=need, **kwargs)

    def test_wait_requires_a_bound(self) -> None:
        with self.assertRaises(ValueError):
            WorkshopWaitIntent(max_wait_ms=0)

    def test_intents_reject_non_positive_targets(self) -> None:
        for build in (
            lambda: WorkshopSelectIntent(cell_id=0),
            lambda: WorkshopProduceIntent(cell_id=1, producer_item_id=0),
            lambda: WorkshopRecycleIntent(cell_id=1, item_id=-1),
            lambda: WorkshopSubmitOrderIntent(order_ref=0),
        ):
            with self.subTest(build=build):
                with self.assertRaises(ValueError):
                    build()


class WorkshopDecisionPolicyTests(unittest.TestCase):
    """Decisions carry revalidation context; policies keep typed knobs."""

    def test_decision_freezes_quantity_maps(self) -> None:
        decision = WorkshopDecision(
            intent=WorkshopSubmitOrderIntent(order_ref=1),
            reason="ready two-piece order",
            goal_order_ref=1,
            protected_quantities={workshop_fixtures.FRUIT_1: 1},
        )
        self.assertIsInstance(decision.protected_quantities, MappingProxyType)
        self.assertEqual(decision.goal_order_ref, 1)

    def test_decision_rejects_untyped_intent_and_bad_quantities(self) -> None:
        with self.assertRaises(TypeError):
            WorkshopDecision(intent="merge")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            WorkshopDecision(
                intent=WorkshopSelectIntent(cell_id=1),
                protected_quantities={workshop_fixtures.FRUIT_1: 0},
            )

    def test_policy_contract_validates_its_knobs(self) -> None:
        policy = workshop_fixtures.make_policy()
        self.assertEqual(policy.order_piece_total, 2)
        self.assertEqual(policy.reward_priority[0], WorkshopOrderRewardCategory.BEAST_LASSO)
        for bad in (
            {"order_piece_total": 0},
            {"reward_priority": ()},
            {"reward_priority": (WorkshopOrderRewardCategory.FEED, WorkshopOrderRewardCategory.FEED)},
            {"recyclable_item_ids": frozenset({0})},
            {"max_cooldown_wait_ms": 0},
        ):
            with self.subTest(bad=bad):
                kwargs = {
                    "order_piece_total": 2,
                    "reward_priority": (WorkshopOrderRewardCategory.FEED,),
                    "recyclable_item_ids": frozenset({workshop_fixtures.FRUIT_5}),
                    "max_cooldown_wait_ms": 60_000,
                }
                kwargs.update(bad)
                with self.assertRaises((ValueError, TypeError)):
                    WorkshopPolicy(**kwargs)

    def test_validation_result_contract(self) -> None:
        for verdict in WorkshopValidationVerdict:
            with self.subTest(verdict=verdict):
                result = WorkshopIntentValidation(verdict=verdict, reason="check")
                self.assertEqual(result.verdict, verdict)
        with self.assertRaises(TypeError):
            WorkshopIntentValidation(verdict="legal")  # type: ignore[arg-type]


class WorkshopInterfaceTests(unittest.TestCase):
    """The pure plan_next/validate_intent signatures are fixed for PW03/PW04."""

    def test_plan_next_signature(self) -> None:
        hints = typing.get_type_hints(WorkshopPlanNext.__call__)
        self.assertIs(hints["state"], WorkshopState)
        self.assertIs(hints["catalog"], PetWorkshopCatalog)
        self.assertIs(hints["policy"], WorkshopPolicy)
        self.assertIs(hints["return"], WorkshopDecision)

    def test_validate_intent_signature(self) -> None:
        hints = typing.get_type_hints(WorkshopValidateIntent.__call__)
        self.assertIs(hints["state"], WorkshopState)
        self.assertIs(hints["intent"], WorkshopIntent)
        self.assertIs(hints["catalog"], PetWorkshopCatalog)
        self.assertIs(hints["policy"], WorkshopPolicy)
        self.assertIs(hints["return"], WorkshopIntentValidation)


class WorkshopScenarioFixtureTests(unittest.TestCase):
    """Synthetic fixtures cover the agreed mechanic states; none are live proof."""

    def test_feed_locked_fixture_supports_a_feed_intent(self) -> None:
        state = workshop_fixtures.feed_locked_state()
        locked = state.cell_at(1, 1)
        food = state.cell_at(1, 2)
        self.assertEqual(locked.item_status, WorkshopItemStatus.FEED_LOCKED)
        intent = WorkshopFeedIntent(
            food_cell_id=food.cell_id,
            producer_cell_id=locked.cell_id,
            food_item_id=workshop_fixtures.FOOD_3,
        )
        self.assertEqual(intent.kind, WorkshopIntentKind.FEED)

    def test_activation_fixture_supports_an_activate_intent(self) -> None:
        state = workshop_fixtures.activation_state()
        inactive = state.cell_at(2, 1)
        normal = state.cell_at(2, 2)
        self.assertEqual(inactive.item_status, WorkshopItemStatus.INACTIVE)
        intent = WorkshopActivateIntent(
            source_cell_id=normal.cell_id,
            target_cell_id=inactive.cell_id,
            item_id=workshop_fixtures.FRUIT_1,
        )
        self.assertEqual(intent.kind, WorkshopIntentKind.ACTIVATE)

    def test_finite_producer_fixture_is_representable_without_use_counts(self) -> None:
        state = workshop_fixtures.finite_producer_state()
        producer = workshop_fixtures.catalog().producer_for(workshop_fixtures.FISHING_TOOL_9)
        self.assertIsNotNone(producer)
        self.assertEqual(producer.change_item_id, workshop_fixtures.FISHING_TOOL_6)
        self.assertGreater(producer.max_num, 0)
        self.assertEqual(state.cell_at(3, 1).item_id, workshop_fixtures.FISHING_TOOL_9)

    def test_recycling_fixture_supports_a_recycle_intent(self) -> None:
        state = workshop_fixtures.recycling_state()
        candidate = state.cell_at(9, 1)
        self.assertEqual(candidate.item_id, workshop_fixtures.FRUIT_5)
        intent = WorkshopRecycleIntent(cell_id=candidate.cell_id, item_id=workshop_fixtures.FRUIT_5)
        self.assertEqual(intent.kind, WorkshopIntentKind.RECYCLE)

    def test_zero_energy_fixture_stays_distinct(self) -> None:
        state = workshop_fixtures.zero_energy_state()
        self.assertTrue(state.energy.is_zero)
        stop = WorkshopDecision(
            intent=WorkshopStopIntent(reason=WorkshopStopReason.ZERO_ENERGY),
            reason="energy bar reliably reads zero",
        )
        self.assertEqual(stop.intent.reason, WorkshopStopReason.ZERO_ENERGY)


class ObservationFieldTests(unittest.TestCase):
    """The workshop field composes with the canonical Observation model."""

    def test_observation_carries_the_workshop_fact(self) -> None:
        workshop = workshop_fixtures.make_observation()
        observation = Observation(screen_type=ScreenType.PNC_SETTINGS, workshop=workshop)
        self.assertIs(observation.workshop, workshop)
        self.assertEqual(observation.screen_type, ScreenType.PNC_SETTINGS)

    def test_observation_default_is_no_workshop(self) -> None:
        observation = Observation(screen_type=ScreenType.PNC_SETTINGS)
        self.assertIsNone(observation.workshop)


if __name__ == "__main__":
    unittest.main()
