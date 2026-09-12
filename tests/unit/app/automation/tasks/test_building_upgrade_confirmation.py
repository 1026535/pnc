"""Building upgrade confirmation."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    SpatialObjectKind,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.domain.policy_models import BuildingUpgradePolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class BuildingUpgradeConfirmationTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves building upgrade confirmation."""

    def test_building_upgrade_task_opens_build_queue_for_verification(self) -> None:
        """Uses the shared left-rail build control for the second ordered success proof."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_success_verification_stage"] = "open_build_queue"

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Build"},
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_BUILD_BUTTON)
        self.assertEqual(actions[0].reason, "open_build_queue_for_upgrade_verification")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.build_queue_follow_up())

    def test_building_upgrade_task_succeeds_when_build_queue_shows_timer(self) -> None:
        """Accepts the second ordered success proof when the build queue exposes an active timer row."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_success_verification_stage"] = "open_build_queue"

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Build"},
            ),
            make_observation(
                ScreenType.PNC_BUILD_QUEUE,
                list_entries=(
                    make_entry(
                        ListEntryKind.BUILDING,
                        title="Wall",
                        timer_text="00:48:16",
                        metadata={"queue_state": "upgrading"},
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("build queue", result.message)

    def test_building_upgrade_task_succeeds_when_level_increases_after_build_queue_fallback(self) -> None:
        """Uses the final ordered level-change proof when neither timer-based observation stayed visible."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        task.plan(
            context,
            make_observation(
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
            ),
        )
        context.runtime_state["building_upgrade_success_verification_stage"] = "return_home_for_level"

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_BUILD_QUEUE),
            make_observation(
                ScreenType.PNC_HOME_CITY,
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

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Lv.3 to Lv.4", result.message)

    def test_building_upgrade_task_taps_upgrade_button_again_when_confirmation_is_pending(self) -> None:
        """Uses the shared blue `Upgrade` control as the final confirmation click on the exact screen."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_confirmation_pending"] = True

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON,
                ),
            ),
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_UPGRADE_BUTTON)
        self.assertEqual(actions[0].reason, "confirm_building_upgrade")
        self.assertTrue(actions[1].follow_up_request.include_building_upgrade_warning)

    def test_building_upgrade_task_replans_when_upgrade_confirmation_layout_appears(self) -> None:
        """Treats the shared exact-screen confirmation layout as a real confirmation step instead of a failed click."""

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
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON,
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("final `Upgrade` click", result.message)
        self.assertTrue(context.runtime_state["building_upgrade_confirmation_pending"])

    def test_building_upgrade_task_owns_and_confirms_post_upgrade_warning(self) -> None:
        """Confirms the task-scoped Castle shield warning before verifying the started build."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        warning = make_observation(
            ScreenType.PNC_BUILDING_UPGRADE_WARNING,
            visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON,),
        )

        actions = task.plan(context, warning)
        result = task.verify(
            context,
            warning,
            make_observation(
                ScreenType.PNC_CASTLE,
                visible_ids=(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,),
            ),
        )

        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON)
        self.assertEqual(actions[0].reason, "confirm_building_upgrade_warning")
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("warning confirmed", result.message)
