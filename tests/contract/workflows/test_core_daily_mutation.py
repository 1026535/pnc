"""Exercise the core claim lifecycle with real authority, executor and durable journal."""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.coordinator import daily_viewport_from_observation
from pnc_automation.app.automation.daily_maintenance.connected_runner import ConnectedClaimOnlyCastleRunner
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowRunner, WorkflowContext, WorkflowEffect, WorkflowSpec
from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy
from pnc_automation.app.pnc.domain.action_requests import SwipeAction
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId, DailyTaskCheckpoint, DailyTargetOutcomeStatus, MutationAcknowledgement, MutationIntentState,
)
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.vision.image.models import Bounds
from tests.support.pnc.observations import make_observation


def daily(state="claim", *, guard=GuardVerdict.CLEAR):
    """Build a complete visual row with explicit screen and guard facts."""

    return make_observation(
        ScreenType.PNC_QUEST_DAILY,
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_QUEST_DAILY,
            effective_screen=ScreenType.PNC_QUEST_DAILY, guard=guard,
        ),
        image_size=(540, 960),
        list_entries=(DetectedListEntry(
            kind=ListEntryKind.DAILY_QUEST, bounds=Bounds(9, 372, 518, 99),
            title_text="Upgrade Building", action_point=(454, 421),
            action_bounds=Bounds(430, 400, 60, 40), row_status=RowRecognitionStatus.COMPLETE,
            metadata={"quest_id": "upgrade_building", "row_state": state,
                      "coordinate_provenance": "visual_geometry", "observation_fingerprint": "row",
                      "bottom_marker": True},
        ),),
    )


class Runtime:
    """Fake only the device, retaining the real workflow and mutation owners."""

    def __init__(self, castle, observations):
        self.observations = iter(observations)
        self.observation_count = 0
        self.last_observation = None
        self.navigation = SimpleNamespace(navigate=self.navigate)
        self.preflight_active_castle_identity = Mock(return_value=castle)
        self.actuator = Mock()
        self.runtime = SimpleNamespace(require_observed_action_executor=lambda reason: self.actuator)
        self.trace_path = Path("trace.jsonl")
        self.record = Mock()
        self.targets = []

    def fresh(self, observation):
        self.observation_count += 1
        self.last_observation = replace(
            observation, captured_at=datetime(2026, 9, 12, tzinfo=UTC)
            + timedelta(seconds=self.observation_count),
        )
        return self.last_observation

    def navigate(self, target):
        self.targets.append(target)
        return self.fresh(make_observation(target))

    def observe(self, label, *, include_content=False):
        return self.fresh(next(self.observations))


@dataclass
class ClaimWorkflow:
    checkpoint: DailyTaskCheckpoint
    spec = WorkflowSpec(
        "daily_claim_test", ScreenType.PNC_QUEST_DAILY, ScreenType.PNC_HOME_CITY,
        WorkflowEffect.RESOURCE_CHANGING, DailyQuestId.CLAIM_COMPLETED,
    )

    def execute(self, context):
        row = daily_viewport_from_observation(daily()).rows[0]
        return context.claim_daily_reward(row, self.checkpoint)


class CoreDailyMutationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = DailyRunJournalStore(Path(temporary.name))
        self.castle = CastleIdentity("K1", "Castle", 20)
        self.checkpoint = DailyTaskCheckpoint("2026-09-12", "reset", "account", self.castle)
        self.scope = CoreMutationBoundary(
            target=DailyMaintenanceTargetConfig("account", "castle", self.castle, (), max_claims=1),
            boundary=DailyRunBoundary(date(2026, 9, 12), "reset"),
            authorizer=DailyMutationAuthorizer((MutationAcknowledgement(
                "account", "castle", DailyQuestId.CLAIM_COMPLETED, date(2026, 9, 12), 1, 0,
            ),)), journal_store=self.store,
        )

    def load(self):
        return self.store.load(game_reset_id="reset", account_id="account", castle=self.castle)

    def test_missing_authority_denied_before_preflight_or_capture(self):
        runtime = Runtime(self.castle, ())
        scope = replace(self.scope, authorizer=DailyMutationAuthorizer())
        with self.assertRaises(PermissionError):
            CoreWorkflowRunner(runtime, scope).run(ClaimWorkflow(self.checkpoint))
        runtime.preflight_active_castle_identity.assert_not_called()
        self.assertEqual(0, runtime.observation_count)

    def test_wrong_active_castle_denied_before_claim(self):
        runtime = Runtime(CastleIdentity("K2", "Castle", 20), ())
        with self.assertRaises(PermissionError):
            CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.checkpoint))
        self.assertEqual([], runtime.targets)
        runtime.actuator.execute_action.assert_not_called()

    def test_commits_after_dispatch_is_durable_and_confirms_home(self):
        runtime = Runtime(self.castle, (daily(), daily("completed")))
        def assert_durable(*args):
            self.assertEqual(MutationIntentState.DISPATCHED, self.load().mutation_intents[0].state)
        runtime.actuator.execute_action.side_effect = assert_durable
        result = CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.checkpoint))
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, result.value[1].status)
        self.assertEqual(MutationIntentState.COMMITTED, self.load().mutation_intents[0].state)
        self.assertEqual(ScreenType.PNC_HOME_CITY, result.exit_screen)
        runtime.actuator.execute_action.assert_called_once()

    def test_stale_checkpoint_cannot_erase_receipt_or_replay(self):
        runtime = Runtime(self.castle, (daily(), daily("unknown_action")))
        result = CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.checkpoint))
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, result.value[1].status)
        with self.assertRaisesRegex(RuntimeError, "stale"):
            CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.checkpoint))
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.load()))
        runtime.actuator.execute_action.assert_called_once()

    def test_dispatch_failure_leaves_receipt_and_does_not_exit_or_replay(self):
        runtime = Runtime(self.castle, (daily(),))
        runtime.actuator.execute_action.side_effect = RuntimeError("device failed")
        with self.assertRaisesRegex(RuntimeError, "device failed"):
            CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.checkpoint))
        self.assertEqual(MutationIntentState.DISPATCHED, self.load().mutation_intents[0].state)
        self.assertNotIn(ScreenType.PNC_HOME_CITY, runtime.targets)
        runtime.actuator.execute_action.assert_called_once()

    def test_consumed_cap_and_wrong_boundary_are_rejected(self):
        runtime = Runtime(self.castle, (daily(), daily("completed")))
        CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.checkpoint))
        with self.assertRaises(PermissionError):
            CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.load()))
        with self.assertRaises(PermissionError):
            CoreWorkflowRunner(runtime, self.scope).run(
                ClaimWorkflow(replace(self.checkpoint, account_id="other")),
            )
        runtime.actuator.execute_action.assert_called_once()

    def test_other_resource_capability_stays_denied(self):
        workflow = ClaimWorkflow(self.checkpoint)
        workflow.spec = replace(workflow.spec, mutation_capability=DailyQuestId.UPGRADE_RESEARCH)
        runtime = Runtime(self.castle, ())
        with self.assertRaises(PermissionError):
            CoreWorkflowRunner(runtime, self.scope).run(workflow)
        runtime.preflight_active_castle_identity.assert_not_called()

    def test_blocked_source_or_postflight_never_becomes_success(self):
        for blocked_first in (True, False):
            with self.subTest(blocked_first=blocked_first):
                blocked = daily("completed", guard=GuardVerdict.UNRESOLVED)
                observations = (blocked,) if blocked_first else (daily(), blocked)
                runtime = Runtime(self.castle, observations)
                # Give each subcase a separate canonical reset journal.
                checkpoint = replace(self.checkpoint, game_reset_id=str(blocked_first))
                scope = replace(self.scope, boundary=replace(self.scope.boundary, game_reset_id=str(blocked_first)))
                with self.assertRaisesRegex(RuntimeError, "unblocked Daily"):
                    CoreWorkflowRunner(runtime, scope).run(ClaimWorkflow(checkpoint))
                self.assertEqual(0 if blocked_first else 1, runtime.actuator.execute_action.call_count)
                self.assertNotIn(ScreenType.PNC_HOME_CITY, runtime.targets)

    def test_stale_source_does_not_dispatch(self):
        runtime = Runtime(self.castle, ())
        def stale(label, *, include_content=False):
            runtime.observation_count += 1
            return replace(daily(), captured_at=runtime.last_observation.captured_at)
        runtime.observe = stale
        with self.assertRaisesRegex(RuntimeError, "stale"):
            CoreWorkflowRunner(runtime, self.scope).run(ClaimWorkflow(self.checkpoint))
        runtime.actuator.execute_action.assert_not_called()

    def test_daily_scroll_dispatches_once_and_confirms_fresh_daily_frames(self):
        runtime = Runtime(self.castle, (daily(), daily(), daily()))
        before = runtime.fresh(daily())
        runtime.navigation = NavigationCore(
            runtime.actuator, lambda label: runtime.observe(label), (),
            policy=NavigationPolicy(poll_seconds=0),
        )
        runtime.actuator.execute_action.return_value = True
        context = WorkflowContext(runtime, last_observation=before)
        after = context.scroll_daily_quest(adjusted=True)
        action = runtime.actuator.execute_action.call_args.args[0]
        self.assertIsInstance(action, SwipeAction)
        self.assertEqual((0.82, 0.49, 420), (action.start_y_ratio, action.end_y_ratio, action.duration_ms))
        self.assertGreater(after.captured_at, before.captured_at)
        runtime.actuator.execute_action.assert_called_once()

    def test_production_connected_runner_composes_real_core_and_claim_owners(self):
        runtime = Runtime(self.castle, (
            daily(), daily(), daily(), daily("completed"), daily("completed"), daily("completed"),
        ))
        runner = ConnectedClaimOnlyCastleRunner(
            "instance", SimpleNamespace(artifact_root=self.store.root), Mock(), self.scope.authorizer,
        )
        result = runner._run_connected_castle(
            target=self.scope.target, boundary=self.scope.boundary, core=runtime,
        )
        self.assertTrue(result.succeeded)
        self.assertEqual(MutationIntentState.COMMITTED, self.load().mutation_intents[0].state)
        self.assertEqual(ScreenType.PNC_HOME_CITY, runtime.targets[-1])
        runtime.actuator.execute_action.assert_called_once()
        runtime.preflight_active_castle_identity.assert_called_once()

    def test_connected_summary_does_not_report_unknown_rows_as_complete(self):
        observation = daily("unknown_action")
        row = observation.list_entries[0]
        unknown = replace(observation, list_entries=(replace(
            row, title_text="Future Quest", metadata={**row.metadata, "quest_id": None},
        ),))
        runtime = Runtime(self.castle, (unknown, unknown))
        runner = ConnectedClaimOnlyCastleRunner(
            "instance", SimpleNamespace(artifact_root=self.store.root), Mock(), self.scope.authorizer,
        )
        result = runner._run_connected_castle(
            target=self.scope.target, boundary=self.scope.boundary, core=runtime,
        )
        self.assertFalse(result.succeeded)
        self.assertIn("1 unknown title", result.message)
        runtime.actuator.execute_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
