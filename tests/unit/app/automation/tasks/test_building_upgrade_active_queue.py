"""Building upgrade active queue."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.pnc.domain.action_requests import TapAction, WaitAction
from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.domain.policy_models import BuildingUpgradePolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class BuildingUpgradeActiveQueueTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves building upgrade active queue."""

    def test_building_upgrade_task_waits_for_unknown_screen_to_settle(self) -> None:
        """Allows the task to recover from a transient unknown frame instead of failing applicability."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        actions = task.plan(
            context,
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertTrue(actions[0].observe_after)

    def test_building_upgrade_task_requests_visible_active_build_help_before_searching(self) -> None:
        """Treats a visible home-city `Help` button as an already-active build that should be helped opportunistically."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_BUILD_BUTTON)
        self.assertEqual(actions[0].reason, "request_active_build_help")
        self.assertTrue(actions[0].observe_after)

    def test_building_upgrade_task_skips_when_another_build_is_already_active_after_help_request(self) -> None:
        """Stops cleanly once a visible active build proves the construction queue is already occupied."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
            ),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("already active", result.message)

    def test_building_upgrade_task_skips_when_active_timer_is_visible_without_help(self) -> None:
        """Uses the shared home-city active-timer signal to skip when the builder is busy outside an alliance."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("already active", result.message)
