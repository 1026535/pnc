"""Building upgrade selection."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeAction,
    TapAction,
    TapSpatialObjectAction,
    WaitAction,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.domain.policy_models import BuildingPriority, BuildingUpgradePolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class BuildingUpgradeSelectionTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves building upgrade selection."""

    def test_building_upgrade_task_chooses_highest_priority_candidate(self) -> None:
        """Selects the configured highest-priority building candidate for inspection before claiming eligibility."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(
                UiElementId.PNC_HOME_WORLD_SWITCH,
                UiElementId.PNC_HOME_CHARACTER_PANEL,
                UiElementId.PNC_HOME_BUILD_BUTTON,
            ),
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        action_point=(70, 60),
                    ),
                ),
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.name_text, "Castle")
        self.assertEqual(actions[0].target_point, (70, 60))

    def test_building_upgrade_task_replans_after_camera_focus_when_target_priority_is_offscreen(self) -> None:
        """Treats a home-city search swipe as progress even when other upgradeable buildings were already visible."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                ),
            ),
        )

        actions = task.plan(context, before)
        result = task.verify(context, before, make_observation(ScreenType.PNC_HOME_CITY))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("searching for the requested building", result.message)

    def test_building_upgrade_task_replans_when_details_confirm_upgrade_button(self) -> None:
        """Treats the details screen as the canonical proof that a building is actually upgradeable."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Castle",
                            metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                            action_point=(70, 60),
                        ),
                    ),
                ),
            ),
            make_observation(
                ScreenType.PNC_BUILDING_DETAILS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("upgrade button is available", result.message)

    def test_building_upgrade_task_replans_when_details_show_no_upgrade_button(self) -> None:
        """Does not report success when the inspected building lacks a visible upgrade action."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        action_point=(70, 60),
                    ),
                ),
            ),
        )
        task.plan(context, before)

        result = task.verify(
            context,
            before,
            make_observation(ScreenType.PNC_BUILDING_DETAILS),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("not upgradeable", result.message)
        self.assertIn((BuildingPriority.CASTLE, "Castle", (70, 60)), context.runtime_state["building_upgrade_ineligible_targets"])
        self.assertIn(BuildingPriority.CASTLE, context.runtime_state["building_upgrade_ineligible_object_ids"])

    def test_building_upgrade_task_accepts_exact_building_screen_as_verified_upgrade_context(self) -> None:
        """Treats exact building-owned screens as equivalent to the legacy generic detail screen."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Castle",
                            metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                            action_point=(70, 60),
                        ),
                    ),
                ),
            ),
            make_observation(
                ScreenType.PNC_CASTLE,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("upgrade button is available", result.message)

    def test_building_upgrade_task_taps_upgrade_only_from_verified_details_screen(self) -> None:
        """Starts the upgrade only after the task is already on a details screen with the upgrade button."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_BUILDING_DETAILS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_UPGRADE_BUTTON)
        self.assertIsInstance(actions[1], WaitAction)
        self.assertTrue(actions[1].observe_after)
