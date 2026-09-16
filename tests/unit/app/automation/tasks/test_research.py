"""Research."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskPreflight, TaskStatus
from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.pnc.domain.action_requests import TapAction, TapListEntryAction
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    RowRecognitionStatus,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import (
    ResearchDetail,
    ResearchNodeFacts,
    ResearchNodeId,
    ResearchQueueState,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.image.models import Bounds

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


def _development_tree(*, node: ResearchNodeId = ResearchNodeId.CONSTRUCTION_I, title: str = "Construction I"):
    """Build a Development tree frame with one complete typed node row."""

    return make_observation(
        ScreenType.PNC_RESEARCH_TREE,
        list_entries=(
            make_entry(
                ListEntryKind.RESEARCH,
                title=title,
                row_status=RowRecognitionStatus.COMPLETE,
                action_bounds=Bounds(40, 40, 20, 20),
                research_facts=ResearchNodeFacts(
                    category=ResearchCategory.DEVELOPMENT,
                    node_id=node,
                ),
            ),
        ),
    )


def _idle_detail(
    node: ResearchNodeId = ResearchNodeId.CONSTRUCTION_I,
    *,
    category: ResearchCategory | None = None,
    start: bool = True,
):
    """Build a clear idle node-detail frame with an ordinary template Start."""

    return make_observation(
        ScreenType.PNC_RESEARCH_TREE,
        visible_ids=(UiElementId.PNC_RESEARCH_START_BUTTON,) if start else (),
        research_detail=ResearchDetail(node_id=node, category=category),
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_RESEARCH_TREE,
            effective_screen=ScreenType.PNC_RESEARCH_TREE,
            guard=GuardVerdict.CLEAR,
            evidence=(
                ScreenEvidence(
                    ScreenType.PNC_RESEARCH_TREE,
                    "visual_anchor:research_tree_node_detail",
                    layout_id="research_tree_node_detail",
                ),
            ),
        ),
    )


def _active_detail(node: ResearchNodeId = ResearchNodeId.CONSTRUCTION_I):
    """Build a clear active node-detail frame with no ordinary Start control."""

    return make_observation(
        ScreenType.PNC_RESEARCH_TREE,
        research_detail=ResearchDetail(
            node_id=node,
            queue_state=ResearchQueueState.ACTIVE,
            queue_timer_text="00:44:45",
        ),
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_RESEARCH_TREE,
            effective_screen=ScreenType.PNC_RESEARCH_TREE,
            guard=GuardVerdict.CLEAR,
            evidence=(
                ScreenEvidence(
                    ScreenType.PNC_RESEARCH_TREE,
                    "visual_anchor:research_tree_node_detail_active",
                    layout_id="research_tree_node_detail",
                ),
            ),
        ),
    )


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
        """Plans open, confirms the matching detail, starts once, then accepts the fresh active detail."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        tree = _development_tree()
        detail = _idle_detail()
        active = _active_detail()

        open_action = task.plan(context, tree)[0]
        self.assertIsInstance(open_action, TapListEntryAction)
        self.assertEqual(open_action.title_text, "Construction I")

        opened = task.verify(context, tree, detail)
        self.assertEqual(opened.status, TaskStatus.REPLAN)

        start_actions = task.plan(context, detail)
        self.assertEqual(len(start_actions), 1)
        self.assertIsInstance(start_actions[0], TapAction)
        self.assertEqual(start_actions[0].selector_id, UiElementId.PNC_RESEARCH_START_BUTTON)

        result = task.verify(context, detail, active)
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertTrue(result.succeeded)

    def test_research_task_never_starts_a_detail_that_was_not_verified(self) -> None:
        """A pre-existing detail after one tree plan stays read-only without detail verification."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        tree = _development_tree()
        detail = _idle_detail()

        self.assertEqual(len(task.plan(context, tree)), 1)
        self.assertEqual(task.plan(context, detail), [])

    def test_research_task_rejects_a_wrong_node_detail_and_stays_readonly(self) -> None:
        """A fresh detail for another node fails verification and clears the selection."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        tree = _development_tree()
        wrong = _idle_detail(node=ResearchNodeId.TROOP_LOAD_I)

        task.plan(context, tree)
        result = task.verify(context, tree, wrong)

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(task.plan(context, wrong), [])

    def test_research_task_rejects_a_conflicting_detail_category(self) -> None:
        """A visible detail category that conflicts with the verified source fails."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        tree = _development_tree()
        conflicting = _idle_detail(category=ResearchCategory.ECONOMY)

        task.plan(context, tree)
        result = task.verify(context, tree, conflicting)

        self.assertEqual(result.status, TaskStatus.FAILED)

    def test_research_task_rejects_a_stale_detail_frame(self) -> None:
        """An older capture cannot confirm the selected node's detail."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        stale_detail = _idle_detail()
        tree = _development_tree()

        task.plan(context, tree)
        result = task.verify(context, tree, stale_detail)

        self.assertEqual(result.status, TaskStatus.FAILED)

    def test_research_task_treats_a_matching_active_detail_as_read_only(self) -> None:
        """A verified detail that is already running confirms identity but never plans Start."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        tree = _development_tree()
        active = _active_detail()

        task.plan(context, tree)
        opened = task.verify(context, tree, active)
        self.assertEqual(opened.status, TaskStatus.REPLAN)
        self.assertEqual(task.plan(context, active), [])

    def test_research_task_does_not_share_selection_between_contexts(self) -> None:
        """An independent task context cannot inherit another step's verified selection."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        other = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        tree = _development_tree()
        detail = _idle_detail()

        task.plan(context, tree)
        task.verify(context, tree, detail)

        self.assertEqual(task.plan(other, detail), [])

    def test_research_task_plans_start_only_once_per_verified_detail(self) -> None:
        """Consumes the single Start permission so an uncertain outcome is not re-planned blindly."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        tree = _development_tree()
        detail = _idle_detail()

        task.plan(context, tree)
        task.verify(context, tree, detail)
        self.assertEqual(len(task.plan(context, detail)), 1)
        self.assertEqual(task.plan(context, detail), [])

    def test_research_task_rejects_start_when_only_ocr_start_is_visible(self) -> None:
        """Start planning requires the measured template control, not OCR text."""

        task = ResearchTask()
        context = self._make_context(
            task_id=TaskId.RESEARCH,
            params=task.parse_params({"priority": ["development"]}),
        )
        tree = _development_tree()
        detail = _idle_detail()

        task.plan(context, tree)
        task.verify(context, tree, detail)

        ocr_only = make_observation(
            ScreenType.PNC_RESEARCH_TREE,
            visible_ids=(UiElementId.PNC_RESEARCH_START_BUTTON,),
            source_kinds={UiElementId.PNC_RESEARCH_START_BUTTON: VisibleElementSourceKind.OCR},
            research_detail=ResearchDetail(node_id=ResearchNodeId.CONSTRUCTION_I),
        )
        self.assertEqual(task.plan(context, ocr_only), [])

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
