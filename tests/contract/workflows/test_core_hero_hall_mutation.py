"""Hero Hall core composition retains exact authority, durable receipts and no replay."""

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.core_hero_hall import CoreHeroHallReconciliationWorkflow
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowRunner, WorkflowEffect, WorkflowSpec
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.daily_maintenance import DailyCapabilityPolicy, DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, DailyTaskCheckpoint, MutationAcknowledgement, MutationIntentState
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from tests.contract.workflows.test_core_daily_mutation import Runtime
from tests.support.pnc.observations import make_observation


def hero(*, attempts=5, free=True, cooldown=None, generic=False):
    visible = [UiElementId.PNC_HERO_HALL_RECRUIT_BANNER]
    if free:
        visible.append(UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON)
    if generic:
        visible.append(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON)
    banner = f"Daily attempts:{attempts}" if attempts is not None else ""
    if cooldown is not None:
        banner += f" Free in {cooldown}"
    return make_observation(ScreenType.PNC_HERO_HALL, visible_ids=tuple(visible),
                            visible_texts={UiElementId.PNC_HERO_HALL_RECRUIT_BANNER: banner})


@dataclass
class Increment:
    checkpoint: DailyTaskCheckpoint
    spec = WorkflowSpec("hero_test", ScreenType.PNC_HERO_HALL, ScreenType.PNC_HOME_CITY,
                        WorkflowEffect.RESOURCE_CHANGING, DailyQuestId.HERO_HALL)

    def execute(self, context):
        return context.recruit_hero_hall(self.checkpoint)


class CoreHeroHallMutationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = DailyRunJournalStore(Path(temporary.name))
        self.castle = CastleIdentity("K1", "Castle", 20)
        self.checkpoint = DailyTaskCheckpoint("2026-09-13", "reset", "account", self.castle)
        self.scope = CoreMutationBoundary(
            DailyMaintenanceTargetConfig("account", "castle", self.castle, (
                DailyCapabilityPolicy(DailyQuestId.HERO_HALL, TaskId.HERO_HALL, 5),
            )), DailyRunBoundary(date(2026, 9, 13), "reset"),
            DailyMutationAuthorizer((MutationAcknowledgement(
                "account", "castle", DailyQuestId.HERO_HALL, date(2026, 9, 13), 5, 0,
            ),)), self.store,
        )

    def load(self):
        return self.store.load(game_reset_id="reset", account_id="account", castle=self.castle)

    def test_exact_free_dispatch_is_durable_and_returns_home_with_cooldown(self):
        runtime = Runtime(self.castle, (hero(), hero(), hero(attempts=4, free=False, cooldown="00:05:00")))
        def dispatch(action, observation):
            self.assertEqual(UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON, action.selector_id)
            self.assertEqual(MutationIntentState.DISPATCHED, self.load().mutation_intents[0].state)
            return True
        runtime.actuator.execute_action.side_effect = dispatch
        result = CoreWorkflowRunner(runtime, self.scope).run(Increment(self.checkpoint))
        checkpoint, outcome = result.value
        self.assertEqual(MutationIntentState.COMMITTED, checkpoint.mutation_intents[0].state)
        self.assertEqual("waiting_cooldown", outcome.status.value)
        self.assertEqual(ScreenType.PNC_HOME_CITY, result.exit_screen)
        self.assertIn("next_ready_at", checkpoint.mutation_intents[0].metadata)
        # Re-entering the executor during its durable cooldown sends no second action.
        again = CoreWorkflowRunner(runtime, self.scope).run(Increment(checkpoint))
        self.assertEqual("waiting_cooldown", again.value[1].status.value)
        self.assertEqual(1, runtime.actuator.execute_action.call_count)

    def test_authority_denied_before_preflight(self):
        runtime = Runtime(self.castle, ())
        scope = replace(self.scope, authorizer=DailyMutationAuthorizer())
        with self.assertRaises(PermissionError):
            CoreWorkflowRunner(runtime, scope).run(Increment(self.checkpoint))
        runtime.preflight_active_castle_identity.assert_not_called()
        runtime.actuator.execute_action.assert_not_called()

    def test_generic_or_missing_attempts_cannot_dispatch(self):
        for frame in (hero(free=False, generic=True), hero(attempts=None)):
            runtime = Runtime(self.castle, (frame,))
            result = CoreWorkflowRunner(runtime, self.scope).run(Increment(self.checkpoint))
            self.assertEqual("pending_clarification", result.value[1].status.value)
            runtime.actuator.execute_action.assert_not_called()
            self.assertIsNone(self.load())

    def test_disappearance_is_pending_and_reconciliation_never_replays(self):
        runtime = Runtime(self.castle, (hero(), hero(), hero(attempts=None, free=False)))
        runtime.actuator.execute_action.return_value = True
        checkpoint, outcome = CoreWorkflowRunner(runtime, self.scope).run(Increment(self.checkpoint)).value
        self.assertEqual("pending_clarification", outcome.status.value)
        runtime.observations = iter((hero(attempts=None, free=False),))
        _, outcome = CoreWorkflowRunner(runtime, self.scope).run(Increment(checkpoint)).value
        self.assertEqual("pending_clarification", outcome.status.value)
        self.assertEqual(1, runtime.actuator.execute_action.call_count)

    def test_changed_attempts_at_dispatch_retains_intent_without_input(self):
        runtime = Runtime(self.castle, (hero(), hero(attempts=4)))
        with self.assertRaisesRegex(RuntimeError, "positive attempts"):
            CoreWorkflowRunner(runtime, self.scope).run(Increment(self.checkpoint))
        runtime.actuator.execute_action.assert_not_called()
        self.assertEqual(MutationIntentState.DISPATCHED, self.load().mutation_intents[0].state)

    def pending_single(self):
        runtime = Runtime(self.castle, (hero(), hero(), hero(attempts=None, free=False)))
        runtime.actuator.execute_action.return_value = True
        checkpoint, _ = CoreWorkflowRunner(runtime, self.scope).run(Increment(self.checkpoint)).value
        intent = checkpoint.mutation_intents[0]
        checkpoint = replace(checkpoint, mutation_intents=(replace(
            intent, metadata={**intent.metadata, "next_ready_at": "2000-01-01T00:00:00+00:00"},
        ),))
        self.store.save(checkpoint)
        return checkpoint

    def test_reconciliation_without_new_authority_commits_exact_receipt_and_returns_home(self):
        checkpoint = self.pending_single()
        runtime = Runtime(self.castle, (hero(attempts=4),))
        runtime.navigation.open_building = lambda target, **kwargs: runtime.navigate(ScreenType.PNC_HERO_HALL)
        scope = replace(self.scope, authorizer=DailyMutationAuthorizer())
        workflow = CoreHeroHallReconciliationWorkflow(checkpoint, checkpoint.mutation_intents[0].operation_id)

        result = CoreWorkflowRunner(runtime, scope).run(workflow)

        self.assertTrue(result.value.committed)
        self.assertEqual(ScreenType.PNC_HOME_CITY, result.exit_screen)
        self.assertEqual(1, len(self.load().mutation_intents))
        self.assertEqual(MutationIntentState.COMMITTED, self.load().mutation_intents[0].state)
        runtime.actuator.execute_action.assert_not_called()

    def test_reconciliation_rejects_missing_journal_and_wrong_castle_before_navigation(self):
        runtime = Runtime(self.castle, ())
        workflow = CoreHeroHallReconciliationWorkflow(self.checkpoint, "hero-hall-recruit-001")
        scope = replace(self.scope, authorizer=DailyMutationAuthorizer())
        with self.assertRaisesRegex(PermissionError, "existing durable checkpoint"):
            CoreWorkflowRunner(runtime, scope).run(workflow)
        runtime.preflight_active_castle_identity.assert_not_called()
        checkpoint = self.pending_single()
        runtime = Runtime(CastleIdentity("K2", "Other", 20), ())
        with self.assertRaisesRegex(PermissionError, "active castle"):
            CoreWorkflowRunner(runtime, scope).run(CoreHeroHallReconciliationWorkflow(
                checkpoint, checkpoint.mutation_intents[0].operation_id,
            ))
        self.assertEqual([], runtime.targets)
        runtime.actuator.execute_action.assert_not_called()

    def test_reconciliation_scope_cannot_invoke_a_new_recruit(self):
        checkpoint = self.pending_single()
        contract = CoreHeroHallReconciliationWorkflow(checkpoint, checkpoint.mutation_intents[0].operation_id)
        attempted_recruit = Increment(checkpoint)
        attempted_recruit.spec = contract.spec
        runtime = Runtime(self.castle, ())
        scope = replace(self.scope, authorizer=DailyMutationAuthorizer())
        with self.assertRaisesRegex(PermissionError, "resource-changing boundary"):
            CoreWorkflowRunner(runtime, scope).run(attempted_recruit)
        runtime.actuator.execute_action.assert_not_called()
        self.assertEqual(checkpoint, self.load())

    def test_reconciliation_stale_checkpoint_cannot_overwrite_a_committed_receipt(self):
        stale = self.pending_single()
        runtime = Runtime(self.castle, (hero(attempts=4),))
        runtime.navigation.open_building = lambda target, **kwargs: runtime.navigate(ScreenType.PNC_HERO_HALL)
        scope = replace(self.scope, authorizer=DailyMutationAuthorizer())
        workflow = CoreHeroHallReconciliationWorkflow(stale, stale.mutation_intents[0].operation_id)
        CoreWorkflowRunner(runtime, scope).run(workflow)
        committed = self.load()
        with self.assertRaisesRegex(RuntimeError, "stale"):
            CoreWorkflowRunner(runtime, scope).run(workflow)
        self.assertEqual(committed, self.load())
        runtime.actuator.execute_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
