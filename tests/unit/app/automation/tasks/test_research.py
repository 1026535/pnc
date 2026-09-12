"""Research."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskPreflight
from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class ResearchTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves research."""

    def test_research_task_uses_highest_priority_visible_institute_button(self) -> None:
        """Uses the exact institute category buttons instead of a generic academy badge."""

        task = ResearchTask()
        context = self._make_context(task_id=TaskId.RESEARCH, params=task.parse_params({"priority": ["economy", "development"]}))

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_INSTITUTE,
                visible_ids=(
                    UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
                    UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON,
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON)

    def test_research_task_supports_fortification_category_as_first_class_institute_route(self) -> None:
        """Uses the Fortification Institute button when the policy requests that visible category."""

        task = ResearchTask()
        context = self._make_context(task_id=TaskId.RESEARCH, params=task.parse_params({"priority": ["fortification"]}))

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_INSTITUTE,
                visible_ids=(UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON,),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON)

    def test_home_city_entry_tasks_declare_runner_owned_home_city_preflight(self) -> None:
        """Declares one shared runner-owned home-city preflight for tasks whose bodies truly start from home city."""

        self.assertEqual(ResearchTask.preflight, TaskPreflight.HOME_CITY)
