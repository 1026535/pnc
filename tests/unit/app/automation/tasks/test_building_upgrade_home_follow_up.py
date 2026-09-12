"""Building upgrade home follow up."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
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


class BuildingUpgradeHomeFollowUpTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves building upgrade home follow up."""

    def test_building_upgrade_task_replans_when_upgrade_click_lands_on_unknown_transition(self) -> None:
        """Keeps the task alive when a verified upgrade click lands on a transient unknown frame."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("still settling", result.message)

    def test_building_upgrade_task_replans_for_help_when_upgrade_returns_home_city_with_help_visible(self) -> None:
        """Requests optional alliance help after the upgrade starts when the home-city help affordance is available."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("alliance help", result.message)
        self.assertTrue(context.runtime_state["building_upgrade_post_start_help_pending"])

    def test_building_upgrade_task_replans_for_build_queue_when_home_city_has_no_timer_or_level_change(self) -> None:
        """Falls through to the second ordered success proof when the home-city observation cannot yet prove the start."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        level=3,
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
        )
        task.plan(context, before)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Build"},
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Wall",
                            level=3,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("build queue", result.message)
        self.assertEqual(context.runtime_state["building_upgrade_success_verification_stage"], "open_build_queue")

    def test_building_upgrade_task_checks_build_queue_before_accepting_level_change(self) -> None:
        """Preserves the requested timer-first verification order when the level already changed quickly."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        level=3,
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
        )
        task.plan(context, before)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Build"},
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Wall",
                            level=4,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("build queue", result.message)
        self.assertEqual(context.runtime_state["building_upgrade_success_verification_stage"], "open_build_queue")

    def test_building_upgrade_task_extends_replan_budget_for_home_city_search(self) -> None:
        """Uses a task-local replan budget sized to the shared home-city sweep plus verification overhead."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.WALL,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        budget = task.max_replans_per_step(context)

        self.assertIsNotNone(budget)
        assert budget is not None
        self.assertEqual(
            budget,
            self.flows.home_city_navigator.focus_step_budget() + 10,
        )
        self.assertGreater(budget, 5)
