"""Offline contract coverage for typed building identities and replay safety."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.buildings import (
    BuildingUpgradeWorkflow,
    _validate_target_observation,
)
from pnc_automation.app.automation.daily_maintenance.authorization import (
    DailyMutationAuthorizer,
)
from pnc_automation.app.automation.engine.core_daily_mutation import _building_receipt_proof
from pnc_automation.app.automation.engine.core_workflow import (
    WorkflowContext,
    WorkflowEffect,
    _resolve_unique_home_building_identity,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher,
    MutationOperation,
    MutationReconciliation,
)
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.building_operations import (
    BuildingActionIdentity,
    BuildingConstructionTarget,
    BuildingMutationKind,
    BuildingUpgradeTarget,
    observable_building_instance_key,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationAcknowledgement,
    MutationIntentState,
)
from pnc_automation.app.pnc.domain.policy_models import BuildingUpgradePolicy
from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
    VisibleElement,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.errors import ScriptValidationError, TaskVerificationError


class BuildingMutationIdentityTests(unittest.TestCase):
    """Prove target identity, persistence and no-replay behavior without a device."""

    def test_upgrade_identity_requires_exact_level_transition_and_target(self) -> None:
        target = BuildingUpgradeTarget(
            building=HomeCityObjectId.INSTITUTE,
            instance_key="institute-main",
            current_level=7,
            next_level=8,
        )
        action = BuildingActionIdentity(
            kind=BuildingMutationKind.UPGRADE,
            operation_id="upgrade-001",
            target=target,
        )

        self.assertEqual("building_upgrade", action.as_metadata()["action_kind"])
        self.assertEqual("institute-main", action.as_metadata()["target"]["instance_key"])
        with self.assertRaisesRegex(ValueError, "exactly current_level"):
            BuildingUpgradeTarget(
                building=HomeCityObjectId.INSTITUTE,
                instance_key="institute-main",
                current_level=7,
                next_level=9,
            )

    def test_construction_identity_requires_an_observed_slot_instance(self) -> None:
        """Prevents a catalog slot family from standing in for one exact slot."""

        unresolved = BuildingConstructionTarget.for_building(HomeCityObjectId.INSTITUTE)
        with self.assertRaisesRegex(ValueError, "exact observed slot"):
            BuildingActionIdentity(
                kind=BuildingMutationKind.CONSTRUCT,
                operation_id="construct-001",
                target=unresolved,
            )
        resolved = unresolved.bind_slot(
            "home-slot:reserved_institute_slot:100,200,80,60:140,230"
        )
        action = BuildingActionIdentity(
            kind=BuildingMutationKind.CONSTRUCT,
            operation_id="construct-001",
            target=resolved,
        )
        self.assertEqual(
            resolved.slot_instance_key,
            action.as_metadata()["target"]["slot_instance_key"],
        )

    def test_daily_upgrade_context_is_explicit_and_does_not_create_construction_context(self) -> None:
        policy = BuildingUpgradePolicy.from_params(
            {"daily_quest_id": DailyQuestId.UPGRADE_BUILDING.value}
        )
        self.assertEqual(DailyQuestId.UPGRADE_BUILDING, policy.daily_quest_id)
        self.assertTrue(policy.request_help)
        with self.assertRaises(ScriptValidationError):
            BuildingUpgradePolicy.from_params({"daily_quest_id": "building_construct"})

    def test_building_authorizer_returns_the_exact_non_daily_acknowledgement(self) -> None:
        acknowledgement = MutationAcknowledgement(
            account_id="account",
            castle_ref="K1:Main",
            quest_id=None,
            maintenance_date=date(2026, 9, 14),
            max_mutations=1,
            max_diamond_spend=0,
            action_kind=BuildingMutationKind.UPGRADE.value,
        )

        authorized = DailyMutationAuthorizer((acknowledgement,)).require_building(
            account_id="account",
            castle_ref="K1:Main",
            action_kind=BuildingMutationKind.UPGRADE.value,
            maintenance_date=date(2026, 9, 14),
        )

        self.assertIs(acknowledgement, authorized)

    def test_direct_upgrade_does_not_claim_daily_authority(self) -> None:
        checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-14",
            game_reset_id="reset-1",
            account_id="account",
            castle=CastleIdentity("K1", "Main", 10),
        )
        direct = BuildingUpgradeWorkflow(
            policy=BuildingUpgradePolicy.from_params(
                {"priority": [HomeCityObjectId.INSTITUTE.value], "operation_id": "direct-1"}
            ),
            checkpoint=checkpoint,
        )
        daily = BuildingUpgradeWorkflow(
            policy=BuildingUpgradePolicy.from_params(
                {
                    "priority": [HomeCityObjectId.INSTITUTE.value],
                    "daily_quest_id": DailyQuestId.UPGRADE_BUILDING.value,
                }
            ),
            checkpoint=checkpoint,
        )

        self.assertIsNone(direct.spec.mutation_capability)
        self.assertEqual(DailyQuestId.UPGRADE_BUILDING, daily.spec.mutation_capability)

    def test_home_identity_uses_production_metadata_and_observable_geometry(self) -> None:
        home_object = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(100, 200, 80, 60),
            action_point=(140, 230),
            metadata={"home_city_object_id": HomeCityObjectId.INSTITUTE.value},
        )
        observation = Observation(
            screen_type=ScreenType.PNC_HOME_CITY,
            spatial_surface=SpatialSurfaceObservation(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                viewport=SpatialViewport(SpatialViewportAddressingKind.CAMERA_RELATIVE),
                objects=(home_object,),
            ),
        )

        identity = _resolve_unique_home_building_identity(
            observation,
            target=HomeCityObjectId.INSTITUTE,
        )

        self.assertEqual(
            identity,
            observable_building_instance_key(HomeCityObjectId.INSTITUTE, home_object),
        )
        self.assertNotIn("instance_key", home_object.metadata)

    def test_home_identity_fails_closed_for_duplicate_or_repeatable_objects(self) -> None:
        def observation(*objects: DetectedSpatialObject) -> Observation:
            return Observation(
                screen_type=ScreenType.PNC_HOME_CITY,
                spatial_surface=SpatialSurfaceObservation(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    viewport=SpatialViewport(SpatialViewportAddressingKind.CAMERA_RELATIVE),
                    objects=objects,
                ),
            )

        institute = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(100, 200, 80, 60),
            action_point=(140, 230),
            metadata={"home_city_object_id": HomeCityObjectId.INSTITUTE.value},
        )
        duplicate = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(300, 200, 80, 60),
            action_point=(340, 230),
            metadata={"home_city_object_id": HomeCityObjectId.INSTITUTE.value},
        )
        with self.assertRaisesRegex(RuntimeError, "exact Home object"):
            _resolve_unique_home_building_identity(
                observation(institute, duplicate),
                target=HomeCityObjectId.INSTITUTE,
            )
        farm = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(500, 200, 80, 60),
            action_point=(540, 230),
            metadata={"home_city_object_id": HomeCityObjectId.FARM.value},
        )
        second_farm = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(650, 200, 80, 60),
            action_point=(690, 230),
            metadata={"home_city_object_id": HomeCityObjectId.FARM.value},
        )
        with self.assertRaisesRegex(RuntimeError, "exact Home object"):
            _resolve_unique_home_building_identity(
                observation(farm, second_farm),
                target=HomeCityObjectId.FARM,
            )

    def test_construction_slot_uses_current_frame_spatial_query_not_legacy_planner(self) -> None:
        slot = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_EMPTY_SLOT,
            bounds=Bounds(100, 200, 80, 60),
            action_point=(140, 230),
            metadata={"home_city_object_id": HomeCityObjectId.RESERVED_INSTITUTE_SLOT.value},
        )
        home = Observation(
            screen_type=ScreenType.PNC_HOME_CITY,
            spatial_surface=SpatialSurfaceObservation(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                viewport=SpatialViewport(SpatialViewportAddressingKind.CAMERA_RELATIVE),
                objects=(slot,),
            ),
        )
        menu = Observation(screen_type=ScreenType.PNC_BUILD_MENU_FIXED_SLOT)
        executed: list[tuple[object, ...]] = []

        class Executor:
            def execute_actions(self, actions, _observation, *, observe):
                executed.append(tuple(actions))
                return SimpleNamespace(observation=menu)

        legacy_planner = Mock()
        legacy_planner.open_home_city_empty_slot.side_effect = AssertionError(
            "construction must not use the atlas-backed legacy planner"
        )
        runtime = SimpleNamespace(
            runtime=SimpleNamespace(
                require_observed_action_executor=lambda _reason: Executor(),
                flow_planner=SimpleNamespace(home_city_navigator=legacy_planner),
            ),
            observation_count=1,
            observe=lambda _label, include_content=True: home,
        )
        context = WorkflowContext.__new__(WorkflowContext)
        context._runtime = runtime
        context._last_navigation_count = 1
        context._last_observation = home
        context._effect = WorkflowEffect.RESOURCE_CHANGING
        context._mutation_boundary = None
        context._research_node = None
        context._reconciliation_operation_id = None

        _, slot_instance_key = context.open_construction_slot(
            BuildingConstructionTarget.for_building(HomeCityObjectId.INSTITUTE)
        )

        self.assertEqual(1, len(executed))
        self.assertEqual(1, len(executed[0]))
        self.assertIsInstance(executed[0][0], TapSpatialObjectAction)
        self.assertEqual(HomeCityObjectId.RESERVED_INSTITUTE_SLOT.value, executed[0][0].query.metadata_value)
        self.assertIsNone(executed[0][0].target_point)
        self.assertIn("reserved_institute_slot", slot_instance_key)
        legacy_planner.open_home_city_empty_slot.assert_not_called()

    def test_target_validation_requires_typed_owner_not_level_alone(self) -> None:
        target = BuildingUpgradeTarget(
            building=HomeCityObjectId.INSTITUTE,
            instance_key="home:institute:100,200,80,60:140,230",
            current_level=7,
            next_level=8,
        )
        level = VisibleElement(
            selector_id=UiElementId.PNC_BUILDING_LEVEL_LABEL,
            bounds=Bounds(10, 10, 30, 20),
            confidence=1.0,
            extracted_text="Lv. 7",
        )
        with self.assertRaisesRegex(TaskVerificationError, "building-owned detail"):
            _validate_target_observation(
                Observation(screen_type=ScreenType.PNC_BUILDING_DETAILS, visible_elements={level.selector_id: level}),
                target,
            )
        _validate_target_observation(
            Observation(screen_type=ScreenType.PNC_INSTITUTE, visible_elements={level.selector_id: level}),
            target,
        )

    def test_home_receipt_proof_correlates_geometry_without_instance_metadata(self) -> None:
        home_object = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(100, 200, 80, 60),
            action_point=(140, 230),
            level=8,
            metadata={"home_city_object_id": HomeCityObjectId.INSTITUTE.value},
        )
        target = BuildingUpgradeTarget(
            building=HomeCityObjectId.INSTITUTE,
            instance_key=observable_building_instance_key(HomeCityObjectId.INSTITUTE, home_object),
            current_level=7,
            next_level=8,
        )
        proven, status = _building_receipt_proof(
            BuildingActionIdentity(
                kind=BuildingMutationKind.UPGRADE,
                operation_id="upgrade-geometry-001",
                target=target,
            ),
            Observation(
                screen_type=ScreenType.PNC_HOME_CITY,
                spatial_surface=SpatialSurfaceObservation(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    viewport=SpatialViewport(SpatialViewportAddressingKind.CAMERA_RELATIVE),
                    objects=(home_object,),
                ),
            ),
        )

        self.assertTrue(proven)
        self.assertEqual("level_increased", status.value)

    def test_daily_go_with_generic_arrival_reacquires_explicit_target_typed_detail(self) -> None:
        target = BuildingUpgradeTarget(
            building=HomeCityObjectId.INSTITUTE,
            instance_key="home:institute:100,200,80,60:140,230",
            current_level=7,
            next_level=8,
        )
        policy = BuildingUpgradePolicy.from_params(
            {
                "priority": [HomeCityObjectId.INSTITUTE.value],
                "daily_quest_id": DailyQuestId.UPGRADE_BUILDING.value,
                "operation_id": "daily-upgrade-001",
            }
        )
        checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-14",
            game_reset_id="reset-1",
            account_id="account",
            castle=CastleIdentity("K1", "Main", 10),
        )
        level = VisibleElement(
            selector_id=UiElementId.PNC_BUILDING_LEVEL_LABEL,
            bounds=Bounds(10, 10, 30, 20),
            confidence=1.0,
            extracted_text="Lv. 7",
        )
        typed_detail = Observation(
            screen_type=ScreenType.PNC_INSTITUTE,
            visible_elements={level.selector_id: level},
        )
        opened: list[HomeCityObjectId] = []

        class Context:
            def open_daily_upgrade_go(self):
                return Observation(screen_type=ScreenType.PNC_BUILDING_DETAILS)

            def open_building_with_identity(self, building, *, expected_instance_key=None):
                opened.append(building)
                return typed_detail, expected_instance_key

            def execute_building(self, _identity, _checkpoint, _source):
                return checkpoint, None, SimpleNamespace(committed=True)

        result = BuildingUpgradeWorkflow(
            policy=policy,
            checkpoint=checkpoint,
            target=target,
            daily_quest_id=DailyQuestId.UPGRADE_BUILDING,
        ).execute(Context())

        self.assertEqual([HomeCityObjectId.INSTITUTE], opened)
        self.assertEqual("daily-upgrade-001", result.action.operation_id)

    def test_upgrade_preserves_priority_fallback_before_creating_an_intent(self) -> None:
        checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-14",
            game_reset_id="reset-1",
            account_id="account",
            castle=CastleIdentity("K1", "Main", 10),
        )

        def element(selector: UiElementId, text: str | None = None) -> VisibleElement:
            return VisibleElement(
                selector_id=selector,
                bounds=Bounds(10, 10, 30, 20),
                confidence=1.0,
                extracted_text=text,
            )

        watchtower = Observation(
            screen_type=ScreenType.PNC_WATCHTOWER,
            visible_elements={
                UiElementId.PNC_BUILDING_LEVEL_LABEL: element(
                    UiElementId.PNC_BUILDING_LEVEL_LABEL,
                    "Lv. 7",
                ),
                UiElementId.PNC_BUILDING_REQUIREMENT_HEADER: element(
                    UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                    "Requirement",
                ),
                UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL: element(
                    UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                    "Castle : Lv.18",
                ),
            },
        )
        institute = Observation(
            screen_type=ScreenType.PNC_INSTITUTE,
            visible_elements={
                UiElementId.PNC_BUILDING_LEVEL_LABEL: element(
                    UiElementId.PNC_BUILDING_LEVEL_LABEL,
                    "Lv. 6",
                ),
                UiElementId.PNC_BUILDING_UPGRADE_BUTTON: element(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    "Upgrade",
                ),
            },
        )
        opened: list[HomeCityObjectId] = []
        returned: list[ScreenType] = []
        dispatched: list[BuildingActionIdentity] = []

        class Context:
            def open_building_with_identity(self, building, *, expected_instance_key=None):
                del expected_instance_key
                opened.append(building)
                observation = watchtower if building is HomeCityObjectId.WATCHTOWER else institute
                return observation, f"home:{building.value}:10,20,30,40:25,40"

            def navigate(self, screen):
                returned.append(screen)
                return Observation(screen_type=screen)

            def execute_building(self, identity, _checkpoint, _source):
                dispatched.append(identity)
                return checkpoint, None, SimpleNamespace(committed=True)

        result = BuildingUpgradeWorkflow(
            policy=BuildingUpgradePolicy.from_params(
                {
                    "priority": [
                        HomeCityObjectId.WATCHTOWER.value,
                        HomeCityObjectId.INSTITUTE.value,
                    ],
                    "operation_id": "priority-upgrade-001",
                }
            ),
            checkpoint=checkpoint,
        ).execute(Context())

        self.assertEqual(
            [HomeCityObjectId.WATCHTOWER, HomeCityObjectId.INSTITUTE],
            opened,
        )
        self.assertEqual([ScreenType.PNC_HOME_CITY], returned)
        self.assertEqual(HomeCityObjectId.INSTITUTE, result.action.target.building)
        self.assertEqual([result.action], dispatched)

    def test_same_operation_id_reconciles_persisted_receipt_without_dispatch(self) -> None:
        target = BuildingUpgradeTarget(
            building=HomeCityObjectId.FARM,
            instance_key="farm-1",
            current_level=3,
            next_level=4,
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = DailyRunJournalStore(Path(temporary))
            checkpoint = DailyTaskCheckpoint(
                maintenance_date="2026-09-14",
                game_reset_id="reset-1",
                account_id="account",
                castle=CastleIdentity("K1", "Main", 10),
            )
            operation = MutationOperation(
                operation_id="upgrade-001",
                quest_id=None,
                expected_precondition="Farm has Upgrade",
                expected_postcondition="Farm start receipt",
                action_kind=BuildingMutationKind.UPGRADE,
                target=target.as_metadata(),
                metadata={"target": target.as_metadata()},
            )
            calls: list[str] = []
            dispatcher = JournaledMutationDispatcher(store)

            first = dispatcher.execute(
                checkpoint=checkpoint,
                operation=operation,
                dispatch=lambda: calls.append("dispatch"),
                reconcile=lambda: MutationReconciliation(
                    postcondition_proven=True,
                    original_precondition_proven=False,
                    metadata={"receipt_status": "started"},
                ),
            )
            second = dispatcher.execute(
                checkpoint=first.checkpoint,
                operation=operation,
                dispatch=lambda: calls.append("replayed"),
                reconcile=lambda: MutationReconciliation(
                    postcondition_proven=True,
                    original_precondition_proven=False,
                ),
            )

            self.assertEqual(["dispatch"], calls)
            self.assertTrue(first.committed)
            self.assertTrue(second.committed)
            loaded = store.load(
                game_reset_id="reset-1",
                account_id="account",
                castle=CastleIdentity("K1", "Main", 10),
            )
            assert loaded is not None
            intent = loaded.mutation_intents[0]
            self.assertEqual(MutationIntentState.COMMITTED, intent.state)
            self.assertEqual("building_upgrade", intent.action_kind)
            self.assertEqual("farm-1", intent.target["instance_key"])

    def test_same_operation_id_cannot_change_target(self) -> None:
        target = BuildingUpgradeTarget(
            building=HomeCityObjectId.FARM,
            instance_key="farm-1",
            current_level=3,
            next_level=4,
        )
        other = BuildingUpgradeTarget(
            building=HomeCityObjectId.FARM,
            instance_key="farm-2",
            current_level=3,
            next_level=4,
        )
        checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-14",
            game_reset_id="reset-1",
            account_id="account",
            castle=CastleIdentity("K1", "Main", 10),
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = DailyRunJournalStore(Path(temporary))
            dispatcher = JournaledMutationDispatcher(store)
            operation = MutationOperation(
                operation_id="upgrade-001",
                quest_id=None,
                expected_precondition="Farm has Upgrade",
                expected_postcondition="Farm start receipt",
                action_kind=BuildingMutationKind.UPGRADE,
                target=target.as_metadata(),
            )
            first = dispatcher.execute(
                checkpoint=checkpoint,
                operation=operation,
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
            with self.assertRaisesRegex(ValueError, "different action identity"):
                dispatcher.execute(
                    checkpoint=first.checkpoint,
                    operation=MutationOperation(
                        operation_id="upgrade-001",
                        quest_id=None,
                        expected_precondition="Farm has Upgrade",
                        expected_postcondition="Farm start receipt",
                        action_kind=BuildingMutationKind.UPGRADE,
                        target=other.as_metadata(),
                    ),
                    dispatch=lambda: None,
                    reconcile=lambda: MutationReconciliation(True, False),
                )

    def test_distinct_operation_ids_dispatch_as_distinct_authorized_operations(self) -> None:
        target = BuildingUpgradeTarget(
            building=HomeCityObjectId.FARM,
            instance_key="farm-1",
            current_level=3,
            next_level=4,
        )
        checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-14",
            game_reset_id="reset-1",
            account_id="account",
            castle=CastleIdentity("K1", "Main", 10),
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = DailyRunJournalStore(Path(temporary))
            dispatcher = JournaledMutationDispatcher(store)
            calls: list[str] = []

            def operation(operation_id: str) -> MutationOperation:
                return MutationOperation(
                    operation_id=operation_id,
                    quest_id=None,
                    expected_precondition="Farm has Upgrade",
                    expected_postcondition="Farm start receipt",
                    action_kind=BuildingMutationKind.UPGRADE,
                    target=target.as_metadata(),
                )

            first = dispatcher.execute(
                checkpoint=checkpoint,
                operation=operation("upgrade-001"),
                dispatch=lambda: calls.append("first"),
                reconcile=lambda: MutationReconciliation(True, False),
            )
            second = dispatcher.execute(
                checkpoint=first.checkpoint,
                operation=operation("upgrade-002"),
                dispatch=lambda: calls.append("second"),
                reconcile=lambda: MutationReconciliation(True, False),
            )

            self.assertEqual(["first", "second"], calls)
            self.assertEqual(2, len(second.checkpoint.mutation_intents))
            self.assertTrue(
                all(
                    intent.state == MutationIntentState.COMMITTED
                    for intent in second.checkpoint.mutation_intents
                )
            )


if __name__ == "__main__":
    unittest.main()
