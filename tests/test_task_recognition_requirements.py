"""Focused guards for mandatory task recognition dependencies."""

from __future__ import annotations

import logging
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.task_executor import TaskExecutor
from pnc_automation.app.automation.tasks.campaign_task import CampaignTask
from pnc_automation.app.automation.tasks.gathering_task import GatheringTask
from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import TaskVerificationError


class TaskRecognitionRequirementTests(unittest.TestCase):
    """Rejects unsupported mandatory selectors before recovery or task planning."""

    def test_primary_tasks_declare_only_their_mandatory_selector_dependencies(self) -> None:
        self.assertEqual(
            ("PNC_RESEARCH_START_BUTTON",),
            tuple(selector.value for selector in ResearchTask.required_recognition_selectors),
        )
        self.assertEqual(
            ("PNC_GATHER_BUTTON", "PNC_MARCH_CONFIRM_BUTTON"),
            tuple(selector.value for selector in GatheringTask.required_recognition_selectors),
        )
        self.assertEqual(
            ("PNC_CAMPAIGN_BATTLE_BUTTON",),
            tuple(selector.value for selector in CampaignTask.required_recognition_selectors),
        )

    def test_unsupported_requirement_fails_before_recovery_or_plan(self) -> None:
        registry = build_default_selector_registry()
        action_executor = Mock()
        canonical_registry = registry
        action_executor.action_executor.selector_registry = canonical_registry
        observation_service = Mock()
        task_executor = TaskExecutor(
            observation_service=observation_service,
            action_executor=action_executor,
            logger=Mock(spec=logging.LoggerAdapter),
            max_replans_per_step=2,
            max_retries_per_step=1,
        )

        for task in (ResearchTask(), GatheringTask(), CampaignTask()):
            with self.subTest(task=task.id.value):
                with self.assertRaises(TaskVerificationError) as raised:
                    task_executor.execute(task=task, context=Mock(), before=Mock())

                error = raised.exception
                self.assertEqual(task.id, error.details["task_id"])
                self.assertEqual(task.required_recognition_selectors[0], error.details["selector_id"])
                self.assertIn("explicitly unsupported", error.details["catalog_reason"])
                self.assertIn("producer", error.details["catalog_reason"])
                action_executor.recover_interruption_if_required.assert_not_called()
                action_executor.execute_actions.assert_not_called()
                observation_service.observe.assert_not_called()

    def test_default_task_requirement_is_empty(self) -> None:
        from pnc_automation.app.automation.engine.task import BaseAutomationTask

        self.assertEqual((), BaseAutomationTask.required_recognition_selectors)


if __name__ == "__main__":
    unittest.main()
