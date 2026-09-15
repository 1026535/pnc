"""Research consumes published facts through the same durable core boundary as claims."""

from dataclasses import replace
from datetime import UTC, date, datetime
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
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    PopupDismissCandidate,
    PopupEvidenceKind,
    PopupOverlayObservation,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.vision.image.models import Bounds
from tests.contract.workflows.test_core_daily_mutation import Runtime
from tests.support.pnc.observations import make_observation


def research(
    profile, *, start=False, rows=(), resources_sufficient=None, queue_available=None,
):
    return replace(make_observation(
        ScreenType.PNC_RESEARCH_TREE,
        decision=ScreenDecision(
            ScreenType.PNC_RESEARCH_TREE, ScreenType.PNC_RESEARCH_TREE,
            guard=GuardVerdict.CLEAR,
            evidence=(ScreenEvidence(ScreenType.PNC_RESEARCH_TREE, f"visual_anchor:{profile}"),),
        ),
        list_entries=rows,
        research_start_resources_sufficient=resources_sufficient,
        research_start_queue_available=queue_available,
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
            row_status=RowRecognitionStatus.COMPLETE,
            metadata={
                "category": "development",
                "research_access_state": "available",
                "research_progress_state": "incomplete",
                "research_progress_current": 2,
                "research_progress_limit": 5,
            },
        )
        self.grid = research("research_tree_development", rows=(self.node,))
        self.idle = research(
            "research_tree_node_detail",
            start=True,
            resources_sufficient=True,
            queue_available=True,
        )
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
        max_node = replace(
            self.node,
            metadata={**self.node.metadata, "research_progress_state": "max"},
        )
        locked_node = replace(
            self.node,
            metadata={**self.node.metadata, "research_access_state": "locked"},
        )
        for rows in (
            (),
            (self.node, self.node),
            (replace(self.node, row_status=RowRecognitionStatus.CLIPPED),),
            (max_node,),
            (locked_node,),
        ):
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

    def test_insufficient_detail_resources_do_not_create_intent_or_dispatch_start(self):
        short = research(
            "research_tree_node_detail",
            start=True,
            resources_sufficient=False,
            queue_available=True,
        )
        runtime, context = self.context((self.grid, self.idle, self.idle, short))
        context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)

        with self.assertRaisesRegex(RuntimeError, "Bag confirmation is disabled"):
            context.start_research(self.checkpoint)

        self.assertEqual(1, runtime.actuator.execute_action.call_count)
        self.assertIsNone(self.load())

    def test_opt_in_journals_before_confirm_then_starts_from_funded_detail(self):
        """Confirms exact Auto Use once, re-proves funding, and sends the second Research tap."""

        short = research(
            "research_tree_node_detail",
            start=True,
            resources_sufficient=False,
            queue_available=True,
        )
        funded = research(
            "research_tree_node_detail",
            start=True,
            resources_sufficient=True,
            queue_available=True,
        )
        popup_bounds = Bounds(120, 70, 80, 30)
        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_RESEARCH_RESOURCE_CONFIRM_BUTTON,),
            source_kinds={
                UiElementId.PNC_RESEARCH_RESOURCE_CONFIRM_BUTTON: VisibleElementSourceKind.OCR,
            },
            visible_texts={
                UiElementId.PNC_RESEARCH_RESOURCE_CONFIRM_BUTTON: "Confirm",
            },
            blocking_popup=True,
            image_size=(540, 960),
            popup_overlay=PopupOverlayObservation(
                image_size=(540, 960),
                layout_id="research_resource_auto_use",
                candidates=(
                    PopupDismissCandidate(
                        PopupControlKind.RESEARCH_RESOURCE_CONFIRM,
                        popup_bounds,
                        popup_bounds.center(),
                        1.0,
                        PopupEvidenceKind.OCR_TEXT,
                        extracted_text="Confirm",
                    ),
                ),
            ),
        )
        runtime, context = self.context(
            (self.grid, short, short, short, popup, funded, self.active, self.active)
        )
        context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)
        dispatched_selectors = []

        def check_dispatch(action, source):
            dispatched_selectors.append(action.selector_id)
            if (
                action.selector_id == UiElementId.PNC_RESEARCH_START_BUTTON
                and len(dispatched_selectors) == 1
            ):
                self.assertEqual(
                    MutationIntentState.DISPATCHED,
                    self.load().mutation_intents[0].state,
                )
            if action.selector_id == UiElementId.PNC_RESEARCH_RESOURCE_CONFIRM_BUTTON:
                self.assertEqual(MutationIntentState.DISPATCHED, self.load().mutation_intents[0].state)
            return True

        runtime.actuator.execute_action.side_effect = check_dispatch
        checkpoint, outcome = context.start_research(
            self.checkpoint,
            confirm_resource_shortfall_from_bag=True,
        )

        self.assertEqual(
            [
                UiElementId.PNC_RESEARCH_START_BUTTON,
                UiElementId.PNC_RESEARCH_RESOURCE_CONFIRM_BUTTON,
                UiElementId.PNC_RESEARCH_START_BUTTON,
            ],
            dispatched_selectors,
        )
        self.assertEqual(MutationIntentState.COMMITTED, checkpoint.mutation_intents[0].state)
        self.assertEqual("success", outcome.status.value)

    def test_opt_in_journals_reveal_and_refuses_unrecognized_popup(self):
        """The journal blocks replay when the first Start reveals an unknown popup."""

        short = research(
            "research_tree_node_detail",
            start=True,
            resources_sufficient=False,
            queue_available=True,
        )
        generic = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
        )
        runtime, context = self.context((self.grid, short, short, short, generic))
        context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)

        with self.assertRaisesRegex(RuntimeError, "exact Auto Use popup"):
            context.start_research(
                self.checkpoint,
                confirm_resource_shortfall_from_bag=True,
            )

        self.assertEqual(
            MutationIntentState.DISPATCHED,
            self.load().mutation_intents[0].state,
        )
        self.assertEqual(2, runtime.actuator.execute_action.call_count)
        with self.assertRaises(PermissionError):
            context.start_research(
                self.checkpoint,
                confirm_resource_shortfall_from_bag=True,
            )
        self.assertEqual(2, runtime.actuator.execute_action.call_count)

    def test_busy_research_queue_does_not_create_intent_or_dispatch_start(self):
        busy = research(
            "research_tree_node_detail",
            start=True,
            resources_sufficient=True,
            queue_available=False,
        )
        runtime, context = self.context((self.grid, self.idle, self.idle, busy))
        context.open_research_node("Construction I", ResearchCategory.DEVELOPMENT)

        with self.assertRaisesRegex(RuntimeError, "idle queue"):
            context.start_research(self.checkpoint)

        self.assertEqual(1, runtime.actuator.execute_action.call_count)
        self.assertIsNone(self.load())

    def test_idle_detail_without_idle_ocr_carries_fresh_queue_surface_proof(self):
        """Carries the prior canonical Queue Idle fact onto the actual detail shape."""

        detail_without_queue_text = replace(self.idle, research_start_queue_available=None)
        queue_proof = replace(make_observation(
            ScreenType.PNC_RESEARCH_QUEUE,
            decision=ScreenDecision(
                ScreenType.PNC_RESEARCH_QUEUE,
                ScreenType.PNC_RESEARCH_QUEUE,
                guard=GuardVerdict.CLEAR,
                evidence=(ScreenEvidence(ScreenType.PNC_RESEARCH_QUEUE, "visual_anchor:research_queue"),),
            ),
            research_start_queue_available=True,
        ), captured_at=datetime(2026, 9, 12, tzinfo=UTC))
        runtime, context = self.context((
            self.grid,
            detail_without_queue_text,
            detail_without_queue_text,
            detail_without_queue_text,
            self.active,
            self.active,
        ))
        context._research_queue_observation = queue_proof

        observed = context.open_research_node(
            "Construction I",
            ResearchCategory.DEVELOPMENT,
        )
        checkpoint, outcome = context.start_research(self.checkpoint)

        self.assertTrue(observed.research_start_queue_available)
        self.assertGreater(observed.captured_at, queue_proof.captured_at)
        self.assertEqual("success", outcome.status.value)
        self.assertEqual(2, runtime.actuator.execute_action.call_count)
        self.assertEqual(MutationIntentState.COMMITTED, checkpoint.mutation_intents[0].state)

    def test_busy_detail_overrides_prior_idle_queue_surface_proof(self):
        """Preserves explicit detail NOIDLEQUEUE over an earlier Queue Idle frame."""

        busy_detail = replace(self.idle, research_start_queue_available=False)
        queue_proof = replace(make_observation(
            ScreenType.PNC_RESEARCH_QUEUE,
            decision=ScreenDecision(
                ScreenType.PNC_RESEARCH_QUEUE,
                ScreenType.PNC_RESEARCH_QUEUE,
                guard=GuardVerdict.CLEAR,
                evidence=(ScreenEvidence(ScreenType.PNC_RESEARCH_QUEUE, "visual_anchor:research_queue"),),
            ),
            research_start_queue_available=True,
        ), captured_at=datetime(2026, 9, 12, tzinfo=UTC))
        runtime, context = self.context((busy_detail,))
        context._research_queue_observation = queue_proof

        observed = context._observe_research_content("busy_detail_overrides_idle_proof")

        self.assertFalse(observed.research_start_queue_available)

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
