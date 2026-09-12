"""Building upgrade completion."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.domain.policy_models import BuildingPriority, BuildingUpgradePolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class BuildingUpgradeCompletionTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves building upgrade completion."""

    def test_building_upgrade_task_taps_post_upgrade_help_when_pending(self) -> None:
        """Uses the shared home-city build-slot control to request help after a successful upgrade start."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_post_start_help_pending"] = True

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
        self.assertEqual(actions[0].reason, "request_post_upgrade_help")
        self.assertTrue(actions[0].observe_after)

    def test_building_upgrade_task_succeeds_when_confirmation_click_returns_home_city(self) -> None:
        """Treats the second verified click as success once the final confirmation is consumed."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_confirmation_pending"] = True

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
        )

        self.assertTrue(result.succeeded)
        self.assertNotIn("building_upgrade_confirmation_pending", context.runtime_state)

    def test_building_upgrade_task_succeeds_after_post_upgrade_help_tap_returns_home_city(self) -> None:
        """Treats the help tap as best-effort and still finishes once the task settles back at home city."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_post_start_help_pending"] = True

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
            ),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertTrue(result.succeeded)
        self.assertNotIn("building_upgrade_post_start_help_pending", context.runtime_state)

    def test_building_upgrade_task_succeeds_when_unknown_settle_returns_home_after_confirmation(self) -> None:
        """Accepts the post-confirm settle path once the transient unknown frame resolves to home city."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_confirmation_pending"] = True

        result = task.verify(
            context,
            make_observation(ScreenType.UNKNOWN),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
        )

        self.assertTrue(result.succeeded)
        self.assertNotIn("building_upgrade_confirmation_pending", context.runtime_state)

    def test_building_upgrade_task_fails_after_returning_home_with_no_remaining_requested_priorities(self) -> None:
        """Returns one known terminal failure once the explicit requested target is blocked by an unsupported prerequisite."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        context.runtime_state["building_upgrade_ineligible_object_ids"] = {BuildingPriority.INFANTRY_BARRACKS}
        context.runtime_state["building_upgrade_last_unmet_requirement"] = "Recruiting Center : Lv.7"

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(
                    UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                    UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                    UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
                ),
                visible_texts={UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL: "Recruiting Center : Lv.7"},
            ),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertFalse(result.retryable)
        self.assertIn("Recruiting Center : Lv.7", result.message)
        self.assertIn("not supported yet", result.message)

    def test_building_upgrade_task_skips_after_returning_home_with_no_remaining_requested_priorities_and_no_requirement(self) -> None:
        """Keeps generic no-candidate exhaustion as a skip when no unsupported prerequisite was observed."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        context.runtime_state["building_upgrade_ineligible_object_ids"] = {BuildingPriority.INFANTRY_BARRACKS}

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_INFANTRY_BARRACKS),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("currently eligible", result.message)
