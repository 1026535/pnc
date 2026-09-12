"""Building upgrade prerequisites."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.pnc.domain.action_requests import KeyEventAction, TapAction
from pnc_automation.app.pnc.domain.policy_models import (
    BuildingPrerequisiteMode,
    BuildingPriority,
    BuildingUpgradePolicy,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class BuildingUpgradePrerequisitesTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves building upgrade prerequisites."""

    def test_building_upgrade_task_replans_once_when_upgrade_opens_final_confirmation(self) -> None:
        """Allows one extra confirmation pass when the first verified upgrade click opens the shared confirmation layout."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("final `Upgrade` click", result.message)
        self.assertTrue(context.runtime_state["building_upgrade_confirmation_pending"])

    def test_building_upgrade_task_replans_when_upgrade_opens_unmet_requirement_panel(self) -> None:
        """Marks the requested building ineligible when the verified upgrade click reveals a prerequisite gate."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                    UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                    UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
                ),
                visible_texts={
                    UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL: "Recruiting Center : Lv.7",
                },
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("Recruiting Center : Lv.7", result.message)
        self.assertIn(BuildingPriority.INFANTRY_BARRACKS, context.runtime_state["building_upgrade_ineligible_object_ids"])

    def test_building_upgrade_task_backs_out_of_unmet_requirement_panel(self) -> None:
        """Leaves the requirement-gated building screen instead of treating it as another confirmation click."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                    UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].reason, "leave_building_requirement_panel")
        self.assertTrue(actions[0].observe_after)

    def test_building_upgrade_task_queue_mode_opens_visible_prerequisite(self) -> None:
        """Uses the requirement Go control only when dependency resolution is explicitly enabled."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(
                priority=(BuildingPriority.INFANTRY_BARRACKS,),
                prerequisite_mode=BuildingPrerequisiteMode.QUEUE,
            ),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        actions = task.plan(
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
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON)
        queued = context.runtime_state["building_upgrade_queued_prerequisite"]
        self.assertEqual(queued.root_target, BuildingPriority.INFANTRY_BARRACKS)

    def test_building_upgrade_task_queue_mode_records_canonical_prerequisite(self) -> None:
        """Parses the live requirement row and makes that building the next active target."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(
                priority=(BuildingPriority.INFANTRY_BARRACKS,),
                prerequisite_mode=BuildingPrerequisiteMode.QUEUE,
            ),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        before = make_observation(
            ScreenType.PNC_INFANTRY_BARRACKS,
            visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
        )
        after = make_observation(
            ScreenType.PNC_INFANTRY_BARRACKS,
            visible_ids=(
                UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
            ),
            visible_texts={UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL: "Recruiting Center : Lv.7"},
        )

        result = task.verify(context, before, after)
        actions = task.plan(context, make_observation(ScreenType.PNC_HOME_CITY))

        self.assertEqual(result.status, TaskStatus.REPLAN)
        queued = context.runtime_state["building_upgrade_queued_prerequisite"]
        self.assertEqual(queued.root_target, BuildingPriority.INFANTRY_BARRACKS)
        self.assertEqual(queued.prerequisite, BuildingPriority.RECRUITING_CENTER)
        self.assertEqual(queued.required_level, 7)
        self.assertTrue(actions)

    def test_building_upgrade_task_reports_scheduler_ready_prerequisite_outcome(self) -> None:
        """Stops after starting the dependency and tells a future general scheduler when to rerun."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(
                priority=(BuildingPriority.INFANTRY_BARRACKS,),
                prerequisite_mode=BuildingPrerequisiteMode.QUEUE,
            ),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        requirement = make_observation(
            ScreenType.PNC_INFANTRY_BARRACKS,
            visible_ids=(
                UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
            ),
            visible_texts={UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL: "Recruiting Center : Lv.7"},
        )
        task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            requirement,
        )

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_BUILDING_DETAILS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_BUILDING_DETAILS,
                visible_ids=(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Prerequisite 'recruiting_center' toward Lv.7", result.message)
        self.assertIn("Run the original upgrade again", result.message)
        self.assertNotIn("building_upgrade_queued_prerequisite", context.runtime_state)
