"""Research consumes published facts through the same durable core boundary as claims."""

from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.core_workflow import WorkflowContext, WorkflowEffect
from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.daily_maintenance import DailyCapabilityPolicy, DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, DailyTaskCheckpoint, MutationAcknowledgement, MutationIntentState
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, RowRecognitionStatus, VisibleElement
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.vision.image.models import Bounds
from tests.contract.workflows.test_core_daily_mutation import Runtime
from tests.support.pnc.observations import make_observation


def research(profile, *, start=False, rows=()):
    return replace(make_observation(
        ScreenType.PNC_RESEARCH_TREE,
        decision=ScreenDecision(
            ScreenType.PNC_RESEARCH_TREE, ScreenType.PNC_RESEARCH_TREE,
            guard=GuardVerdict.CLEAR,
            evidence=(ScreenEvidence(ScreenType.PNC_RESEARCH_TREE, f"visual_anchor:{profile}"),),
        ),
        list_entries=rows,
    ), visible_elements={UiElementId.PNC_RESEARCH_START_BUTTON: VisibleElement(
            UiElementId.PNC_RESEARCH_START_BUTTON, Bounds(304, 447, 135, 49), 1.0,
        )} if start else {},
    )


class CoreResearchMutationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = DailyRunJournalStore(Path(temporary.name))
        self.castle = CastleIdentity("K1", "Castle", 20)
        self.checkpoint = DailyTaskCheckpoint("2026-09-12", "reset", "account", self.castle)
        self.scope = CoreMutationBoundary(
            DailyMaintenanceTargetConfig("account", "castle", self.castle, (
                DailyCapabilityPolicy(DailyQuestId.UPGRADE_RESEARCH, TaskId.RESEARCH, 1),
            )),
            DailyRunBoundary(date(2026, 9, 12), "reset"),
            DailyMutationAuthorizer((MutationAcknowledgement(
                "account", "castle", DailyQuestId.UPGRADE_RESEARCH, date(2026, 9, 12), 1, 0,
            ),)), self.store,
        )
        self.node = DetectedListEntry(
            ListEntryKind.RESEARCH, Bounds(200, 200, 100, 90), title_text="Construction I",
            action_point=(250, 240), action_bounds=Bounds(200, 200, 100, 80),
            row_status=RowRecognitionStatus.COMPLETE, metadata={"category": "development"},
        )
        self.grid = research("research_tree_development", rows=(self.node,))
        self.idle = research("research_tree_node_detail", start=True)
        self.active = research("research_tree_node_detail_active")

    def context(self, observations):
        runtime = Runtime(self.castle, observations)
        before = runtime.fresh(self.grid)
        runtime.navigation = NavigationCore(
            runtime.actuator, runtime.observe, (), policy=NavigationPolicy(poll_seconds=0, max_observations=2),
        )
        runtime.actuator.execute_action.return_value = True
        return runtime, WorkflowContext(
            runtime, last_observation=before, effect=WorkflowEffect.RESOURCE_CHANGING,
            mutation_boundary=self.scope,
        )

    def load(self):
        return self.store.load(game_reset_id="reset", account_id="account", castle=self.castle)

    def test_exact_node_then_one_journaled_start_requires_active_detail(self):
        runtime, context = self.context((self.grid, self.idle, self.idle, self.idle, self.active, self.active))
        context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)
        def check_dispatch(action, source):
            self.assertEqual(UiElementId.PNC_RESEARCH_START_BUTTON, action.selector_id)
            self.assertEqual(MutationIntentState.DISPATCHED, self.load().mutation_intents[0].state)
            return True
        runtime.actuator.execute_action.side_effect = check_dispatch
        checkpoint, outcome = context.start_research(self.checkpoint)
        self.assertEqual(MutationIntentState.COMMITTED, checkpoint.mutation_intents[0].state)
        self.assertEqual("success", outcome.status.value)
        self.assertEqual(2, runtime.actuator.execute_action.call_count)
        with self.assertRaises(PermissionError):
            context.start_research(checkpoint)
        self.assertEqual(2, runtime.actuator.execute_action.call_count)

    def test_start_disappearance_without_active_detail_is_not_success_or_replayed(self):
        empty = research("research_tree_node_detail")
        runtime, context = self.context((self.grid, self.idle, self.idle, self.idle, empty, empty))
        context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            context.start_research(self.checkpoint)
        self.assertEqual(MutationIntentState.DISPATCHED, self.load().mutation_intents[0].state)
        self.assertEqual(2, runtime.actuator.execute_action.call_count)
        with self.assertRaises(PermissionError):
            context.start_research(self.checkpoint)
        self.assertEqual(2, runtime.actuator.execute_action.call_count)

    def test_changed_or_ambiguous_node_does_not_tap(self):
        for rows in ((), (self.node, self.node), (replace(self.node, row_status=RowRecognitionStatus.CLIPPED),)):
            runtime, context = self.context((research("research_tree_development", rows=rows),))
            with self.assertRaises(RuntimeError):
                context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)
            runtime.actuator.execute_action.assert_not_called()

    def test_start_control_without_idle_detail_provenance_does_not_dispatch(self):
        wrong_detail = research("research_tree_development", start=True)
        runtime, context = self.context((self.grid, self.idle, self.idle, wrong_detail))
        context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)
        with self.assertRaisesRegex(RuntimeError, "normal Start"):
            context.start_research(self.checkpoint)
        self.assertEqual(1, runtime.actuator.execute_action.call_count)
        self.assertIsNone(self.load())

    def test_executor_declines_start_without_committing_or_replaying(self):
        runtime, context = self.context((self.grid, self.idle, self.idle, self.idle))
        context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)
        runtime.actuator.execute_action.return_value = False
        with self.assertRaisesRegex(RuntimeError, "not executed"):
            context.start_research(self.checkpoint)
        self.assertEqual(MutationIntentState.DISPATCHED, self.load().mutation_intents[0].state)
        with self.assertRaises(PermissionError):
            context.start_research(self.checkpoint)
        self.assertEqual(2, runtime.actuator.execute_action.call_count)


if __name__ == "__main__":
    unittest.main()
