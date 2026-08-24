"""Focused tests for the canonical building-construction workflow."""

from __future__ import annotations

import unittest

from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CredentialSource,
    DefaultsConfig,
    ResolvedCredentials,
)
from pnc_automation.app.authoring.scripts.models import ScriptStep
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.automation.tasks.building_construction_task import BuildingConstructionTask
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapAction, TapSpatialObjectAction, WaitAction
from pnc_automation.app.pnc.domain.building_catalog import (
    ConstructionSlotFamily,
    HomeCityObjectId,
    constructable_home_city_object_ids,
    require_building_construction_source,
)
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation, SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.domain.policy_models import BuildingConstructionPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import ScriptValidationError
from tests.test_support import build_logger, make_entry, make_observation, make_spatial_object, make_spatial_surface


class BuildingConstructionTests(unittest.TestCase):
    """Validates construction policy, source routing, and one-shot verification."""

    def setUp(self) -> None:
        """Builds one deterministic task context."""

        self.task = BuildingConstructionTask()
        self.account = AccountConfig(
            id="testing",
            instance_id="bs-main",
            pnc_account_id="test@example.com",
            credentials=ResolvedCredentials(
                username="test@example.com",
                password="secret",
                source=CredentialSource.INLINE,
            ),
        )

    def _context(self, building: HomeCityObjectId) -> TaskContext:
        """Builds a context for one exact construction target."""

        return TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0),
            step=ScriptStep(task=TaskId.BUILDING_CONSTRUCT),
            params=BuildingConstructionPolicy(building=building),
            flows=ScreenFlowPlanner(),
            logger=build_logger(),
        )

    def test_catalog_assigns_all_constructable_targets_to_expected_families(self) -> None:
        """Keeps every supported target in exactly one canonical source family."""

        targets = constructable_home_city_object_ids()
        families = {target: require_building_construction_source(target).slot_family for target in targets}

        self.assertEqual(len(targets), 14)
        self.assertEqual(sum(family == ConstructionSlotFamily.FIXED for family in families.values()), 4)
        self.assertEqual(sum(family == ConstructionSlotFamily.LARGE for family in families.values()), 3)
        self.assertEqual(sum(family == ConstructionSlotFamily.SMALL for family in families.values()), 7)

    def test_every_construction_option_is_registered_as_an_action(self) -> None:
        """Keeps observed option rows executable through the canonical action executor."""

        registry = build_default_selector_registry()

        for target in constructable_home_city_object_ids():
            with self.subTest(target=target):
                source = require_building_construction_source(target)
                selector = registry.require(source.option_selector_id)
                self.assertIn(source.menu_screen_type, selector.screens)
                self.assertEqual(selector.interaction_kind, SelectorInteractionKind.ACTION)

    def test_policy_rejects_a_nonconstructable_building(self) -> None:
        """Rejects owned-only buildings before runtime actions are planned."""

        with self.assertRaises(ScriptValidationError):
            self.task.parse_params({"building": "castle"})

    def test_task_opens_the_exact_typed_empty_slot(self) -> None:
        """Uses the source-slot metadata instead of a generic unlabeled tap."""

        source = require_building_construction_source(HomeCityObjectId.FARM)
        slot = make_spatial_object(
            SpatialObjectKind.HOME_EMPTY_SLOT,
            metadata={"home_city_object_id": source.slot_id.value},
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE, objects=(slot,)),
        )

        actions = self.task.plan(self._context(HomeCityObjectId.FARM), observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].target_point, slot.action_point)

    def test_fixed_and_large_sources_use_atlas_backed_target_positions(self) -> None:
        """Routes unbuilt fixed and large targets through their trusted catalog coordinates."""

        castle = make_spatial_object(
            SpatialObjectKind.HOME_BUILDING,
            name_text="Castle",
            metadata={"home_city_object_id": HomeCityObjectId.CASTLE.value},
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(castle,),
            ),
        )

        for target in (HomeCityObjectId.INSTITUTE, HomeCityObjectId.MARKET):
            with self.subTest(target=target):
                actions = self.task.plan(self._context(target), observation)
                self.assertTrue(actions)
                self.assertTrue(all(isinstance(action, SwipeAction) for action in actions))

    def test_task_emits_the_construction_option_only_once(self) -> None:
        """Never repeats the mutation while waiting for direct-start evidence."""

        context = self._context(HomeCityObjectId.FARM)
        source = require_building_construction_source(HomeCityObjectId.FARM)
        menu = make_observation(source.menu_screen_type, visible_ids=(source.option_selector_id,))

        first_actions = self.task.plan(context, menu)
        second_actions = self.task.plan(context, menu)

        self.assertEqual(len(first_actions), 1)
        self.assertIsInstance(first_actions[0], TapAction)
        self.assertEqual(first_actions[0].selector_id, source.option_selector_id)
        self.assertEqual(len(second_actions), 1)
        self.assertIsInstance(second_actions[0], WaitAction)

    def test_resource_popup_is_only_the_insufficient_resources_branch(self) -> None:
        """Fails explicitly when the post-click observation exposes an unmet requirement."""

        context = self._context(HomeCityObjectId.FARM)
        source = require_building_construction_source(HomeCityObjectId.FARM)
        menu = make_observation(source.menu_screen_type, visible_ids=(source.option_selector_id,))
        self.task.plan(context, menu)
        before = self._construction_confirmation()
        self.task.plan(context, before)
        after = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(
                UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
            ),
            visible_texts={UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL: "Wood"},
        )

        result = self.task.verify(context, before, after)

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIn("Wood", result.message)

    def test_direct_start_without_resource_popup_succeeds_from_home_timer(self) -> None:
        """Accepts the normal sufficient-resource path without expecting a popup."""

        context = self._context(HomeCityObjectId.FARM)
        source = require_building_construction_source(HomeCityObjectId.FARM)
        menu = make_observation(source.menu_screen_type, visible_ids=(source.option_selector_id,))
        self.task.plan(context, menu)
        before = self._construction_confirmation()
        self.task.plan(context, before)
        after = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                metadata={"active_build_timer_text": "00:04:31"},
            ),
        )

        result = self.task.verify(context, before, after)

        self.assertEqual(result.status, TaskStatus.SUCCESS)

    def test_direct_start_without_resource_popup_succeeds_from_build_queue(self) -> None:
        """Accepts an active queue row as alternate direct-start proof."""

        context = self._context(HomeCityObjectId.FARM)
        source = require_building_construction_source(HomeCityObjectId.FARM)
        menu = make_observation(source.menu_screen_type, visible_ids=(source.option_selector_id,))
        self.task.plan(context, menu)
        before = self._construction_confirmation()
        self.task.plan(context, before)
        after = make_observation(
            ScreenType.PNC_BUILD_QUEUE,
            list_entries=(
                make_entry(
                    ListEntryKind.BUILDING,
                    title="Farm",
                    timer_text="00:04:31",
                    metadata={"queue_state": "upgrading"},
                ),
            ),
        )

        result = self.task.verify(context, before, after)

        self.assertEqual(result.status, TaskStatus.SUCCESS)

    def test_task_uses_only_the_ordinary_build_button_on_confirmation(self) -> None:
        """Keeps the premium Build Now action outside the construction task."""

        context = self._context(HomeCityObjectId.FARM)
        source = require_building_construction_source(HomeCityObjectId.FARM)
        menu = make_observation(source.menu_screen_type, visible_ids=(source.option_selector_id,))
        self.task.plan(context, menu)

        actions = self.task.plan(context, self._construction_confirmation())

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON)
        self.assertNotEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_NOW_BUTTON)

    def test_instant_construction_succeeds_when_visible_target_count_increases(self) -> None:
        """Proves zero-duration construction by replacing an empty slot with another target building."""

        context = self._context(HomeCityObjectId.FARM)
        source = require_building_construction_source(HomeCityObjectId.FARM)
        slot = make_spatial_object(
            SpatialObjectKind.HOME_EMPTY_SLOT,
            metadata={"home_city_object_id": source.slot_id.value},
        )
        existing_farm = make_spatial_object(
            SpatialObjectKind.HOME_BUILDING,
            metadata={"home_city_object_id": HomeCityObjectId.FARM.value},
        )
        home_before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(slot, existing_farm),
            ),
        )
        self.task.plan(context, home_before)
        menu = make_observation(source.menu_screen_type, visible_ids=(source.option_selector_id,))
        self.task.plan(context, menu)
        confirmation = self._construction_confirmation()
        self.task.plan(context, confirmation)
        home_after = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(existing_farm, existing_farm),
            ),
        )

        result = self.task.verify(context, confirmation, home_after)

        self.assertEqual(result.status, TaskStatus.SUCCESS)

    @staticmethod
    def _construction_confirmation() -> Observation:
        """Builds the sufficient-resource Farm confirmation with both live-observed actions."""

        return make_observation(
            ScreenType.PNC_BUILDING_CONSTRUCTION,
            visible_ids=(
                UiElementId.PNC_BUILDING_CONSTRUCTION_HEADER,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
                UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_NOW_BUTTON,
            ),
            visible_texts={UiElementId.PNC_BUILDING_CONSTRUCTION_HEADER: "Farm"},
        )


if __name__ == "__main__":
    unittest.main()
