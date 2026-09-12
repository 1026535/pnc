"""Open building."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.open_building_task import OpenBuildingTask
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.domain.policy_models import OpenBuildingPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class OpenBuildingTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves open building."""

    def test_open_building_task_parse_params_accepts_sanctum(self) -> None:
        """Allows direct open-building scripts to target non-upgrade sanctum navigation explicitly."""

        params = OpenBuildingTask().parse_params({"building": "sanctum"})

        self.assertEqual(params, OpenBuildingPolicy(building=HomeCityObjectId.SANCTUM))

    def test_open_building_task_opens_visible_requested_building(self) -> None:
        """Taps the visible requested home-city building instead of sweeping when it is already on-screen."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.INFANTRY_BARRACKS),
            task_id=TaskId.OPEN_BUILDING,
        )

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Infantry Barracks",
                            metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].reason, "open_requested_building")

    def test_open_building_task_replans_after_camera_focus_when_target_is_offscreen(self) -> None:
        """Keeps the dedicated open-building task alive while the shared home-city search adjusts the camera."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.WALL),
            task_id=TaskId.OPEN_BUILDING,
        )
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
        )

        actions = task.plan(context, before)
        result = task.verify(context, before, make_observation(ScreenType.PNC_HOME_CITY, spatial_surface=before.spatial_surface))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("searching", result.message)

    def test_open_building_task_succeeds_when_requested_building_screen_opens(self) -> None:
        """Finishes once the exact requested building-owned screen becomes visible."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.INFANTRY_BARRACKS),
            task_id=TaskId.OPEN_BUILDING,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(ScreenType.PNC_INFANTRY_BARRACKS),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Infantry Barracks", result.message)

    def test_open_building_task_accepts_matching_build_menu_for_unbuilt_target(self) -> None:
        """Accepts the exact build-menu option as success when the requested building slot is not built yet."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.MARKET),
            task_id=TaskId.OPEN_BUILDING,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(
                ScreenType.PNC_BUILD_MENU_LARGE_SLOT,
                visible_ids=(UiElementId.PNC_BUILD_MARKET_OPTION,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Market", result.message)

    def test_open_building_task_accepts_generic_building_details_for_unmodeled_screen_owner(self) -> None:
        """Accepts generic building details when the requested building has no dedicated screen enum yet."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.BANK),
            task_id=TaskId.OPEN_BUILDING,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(ScreenType.PNC_BUILDING_DETAILS),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Bank", result.message)
