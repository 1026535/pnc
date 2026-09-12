"""Research."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskPreflight, TaskStatus
from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_entry, make_observation
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

    def test_research_task_verifies_detail_start_to_active_detail(self) -> None:
        """Accepts a running detail frame after the visible Start control disappears."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        before = make_observation(
            ScreenType.PNC_RESEARCH_TREE,
            visible_ids=(UiElementId.PNC_RESEARCH_START_BUTTON,),
            list_entries=(
                make_entry(
                    ListEntryKind.RESEARCH,
                    title="Construction I",
                    metadata={"category": "development"},
                ),
            ),
        )
        after = make_observation(
            ScreenType.PNC_RESEARCH_TREE,
            list_entries=(make_entry(ListEntryKind.RESEARCH, title="Construction I", metadata={"category": "development"}),),
            decision=ScreenDecision(
                base_screen=ScreenType.PNC_RESEARCH_TREE,
                effective_screen=ScreenType.PNC_RESEARCH_TREE,
                guard=GuardVerdict.CLEAR,
                evidence=(
                    ScreenEvidence(
                        ScreenType.PNC_RESEARCH_TREE,
                        "visual_anchor:research_tree_node_detail_active",
                        layout_id="research_tree_development",
                    ),
                ),
            ),
        )

        result = task.verify(context, before, after)

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertTrue(result.succeeded)

    def test_research_task_rejects_ordinary_tree_without_start_as_postcondition(self) -> None:
        """Does not confirm a start from an ordinary Development tree frame."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        before = make_observation(
            ScreenType.PNC_RESEARCH_TREE,
            visible_ids=(UiElementId.PNC_RESEARCH_START_BUTTON,),
            list_entries=(make_entry(ListEntryKind.RESEARCH, title="Construction I", metadata={"category": "development"}),),
        )
        after = make_observation(
            ScreenType.PNC_RESEARCH_TREE,
        )

        result = task.verify(context, before, after)

        self.assertEqual(result.status, TaskStatus.FAILED)

    def test_research_task_rejects_generic_same_screen_without_start(self) -> None:
        """Does not accept a same-screen observation without active-detail evidence."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        before = make_observation(
            ScreenType.PNC_RESEARCH_TREE,
            visible_ids=(UiElementId.PNC_RESEARCH_START_BUTTON,),
            list_entries=(make_entry(ListEntryKind.RESEARCH, title="Construction I", metadata={"category": "development"}),),
        )
        after = make_observation(
            ScreenType.PNC_RESEARCH_TREE,
            list_entries=(make_entry(ListEntryKind.RESEARCH, title="Construction I", metadata={"category": "development"}),),
            decision=ScreenDecision(
                base_screen=ScreenType.PNC_RESEARCH_TREE,
                effective_screen=ScreenType.PNC_RESEARCH_TREE,
                guard=GuardVerdict.CLEAR,
                evidence=(ScreenEvidence(ScreenType.PNC_RESEARCH_TREE, "generic_same_screen"),),
            ),
        )

        result = task.verify(context, before, after)

        self.assertEqual(result.status, TaskStatus.FAILED)
