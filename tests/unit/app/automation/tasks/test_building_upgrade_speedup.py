"""Building upgrade speedup."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.pnc.domain.action_requests import TapAction
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


class BuildingUpgradeSpeedupTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves building upgrade speedup."""

    def test_building_upgrade_task_succeeds_when_speedup_replaces_upgrade_button(self) -> None:
        """Treats the shared `Speedup` control as a direct upgrade-start success proof."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Speedup", result.message)

    def test_building_upgrade_task_opens_speedup_only_when_explicitly_allowed(self) -> None:
        """Uses the active building's Speedup control only under the opt-in policy."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(allow_speedups=True),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_WAREHOUSE,
                visible_ids=(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_SPEEDUP_BUTTON)

    def test_building_upgrade_task_records_exact_screen_level_before_speedup(self) -> None:
        """Preserves a unique building's level when speedup starts from an already-open screen."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(allow_speedups=True),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        before = make_observation(
            ScreenType.PNC_WAREHOUSE,
            visible_ids=(
                UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,
                UiElementId.PNC_BUILDING_LEVEL_LABEL,
            ),
            visible_texts={UiElementId.PNC_BUILDING_LEVEL_LABEL: "8/45"},
        )

        task.plan(context, before)
        result = task.verify(
            context,
            make_observation(ScreenType.PNC_BUILD_SPEEDUP),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Warehouse",
                            level=9,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WAREHOUSE),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("increased from Lv.8 to Lv.9", result.message)

    def test_building_upgrade_task_selects_inventory_auto_speedup(self) -> None:
        """Selects Auto Speedup and never the premium Build Now control."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(allow_speedups=True),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_BUILD_SPEEDUP,
                visible_ids=(
                    UiElementId.PNC_BUILD_SPEEDUP_AUTO_BUTTON,
                    UiElementId.PNC_BUILD_SPEEDUP_PREMIUM_BUILD_NOW_BUTTON,
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILD_SPEEDUP_AUTO_BUTTON)

    def test_building_upgrade_task_confirms_inventory_auto_speedup(self) -> None:
        """Confirms the item-consumption popup only after speedups were explicitly allowed."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(allow_speedups=True),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_BUILD_SPEEDUP_CONFIRM,
                visible_ids=(UiElementId.PNC_BUILD_SPEEDUP_CONFIRM_BUTTON,),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILD_SPEEDUP_CONFIRM_BUTTON)

    def test_building_upgrade_task_verifies_level_increase_after_auto_speedup(self) -> None:
        """Requires the city-map building level to increase after inventory speedups are submitted."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(
                priority=(BuildingPriority.WAREHOUSE,),
                allow_speedups=True,
            ),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Warehouse",
                            level=8,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WAREHOUSE),
                        ),
                    ),
                    metadata={"active_build_timer_text": "02:42:25"},
                ),
            ),
        )

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_BUILD_SPEEDUP,
                visible_ids=(UiElementId.PNC_BUILD_SPEEDUP_AUTO_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Warehouse",
                            level=9,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WAREHOUSE),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("increased from Lv.8 to Lv.9", result.message)
