"""Authored Research uses the exact mutation scope and borrowed core lifecycle."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.core_script_dispatcher import CoreScriptDispatcher
from pnc_automation.app.automation.engine.task import CastleTargetPolicy, TaskId
from pnc_automation.app.automation.research import ResearchDisposition
from pnc_automation.app.authoring.config.daily_maintenance import DailyCapabilityPolicy, DailyMaintenanceTargetConfig
from pnc_automation.app.authoring.config.models import AccountConfig, LiveAutomationRole
from pnc_automation.app.authoring.scripts.models import PreparedScriptStep, ScriptStep
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId, DailyTaskCheckpoint, MutationAcknowledgement, MutationIntent, MutationIntentState,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from tests.contract.workflows.test_core_daily_mutation import Runtime
from tests.support.pnc.observations import make_observation


class CoreResearchDispatchTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = DailyRunJournalStore(Path(temporary.name))
        self.castle = CastleIdentity("K157", "NPC 2", 22)
        self.account = AccountConfig(
            id="account", instance_id="instance", pnc_account_id="pnc-account",
            live_roles=frozenset({LiveAutomationRole.DAILY_CANARY}),
        )
        self.scope = CoreMutationBoundary(
            DailyMaintenanceTargetConfig("account", "npc_2", self.castle, (
                DailyCapabilityPolicy(DailyQuestId.UPGRADE_RESEARCH, TaskId.RESEARCH, 1),
            )), DailyRunBoundary(date(2026, 9, 13), "reset"),
            DailyMutationAuthorizer((MutationAcknowledgement(
                "account", "npc_2", DailyQuestId.UPGRADE_RESEARCH, date(2026, 9, 13), 1, 0,
            ),)), self.store,
        )

    def step(self, *, priority="development", castle=None):
        definition = build_default_task_registry().require(TaskId.RESEARCH)
        authored = ScriptStep(TaskId.RESEARCH, params={"priority": [priority]})
        return PreparedScriptStep(
            authored, definition.parse_params(authored.params), CastleTargetPolicy.OPTIONAL,
            resolved_castle=castle,
        )

    def dispatcher(self, factory, scope):
        return CoreScriptDispatcher(
            account=self.account, chat_archive_store=None, core_runtime_factory=factory,
            required_role=LiveAutomationRole.DAILY_CANARY, mutation_boundary=scope,
        )

    def test_authored_research_retains_durable_receipts_and_borrows_runtime(self):
        receipt = MutationIntent(
            operation_id="hero-hall-recruit-001", quest_id=DailyQuestId.HERO_HALL,
            state=MutationIntentState.COMMITTED, expected_precondition="five attempts",
            expected_postcondition="four attempts", diamond_budget=0,
        )
        checkpoint = DailyTaskCheckpoint(
            "2026-09-13", "reset", "account", self.castle, mutation_intents=(receipt,),
        )
        self.store.save(checkpoint)
        runtime = Runtime(self.castle, (make_observation(ScreenType.PNC_RESEARCH_TREE),))
        runtime.close = Mock()
        runtime.navigation.open_building = lambda target, **kwargs: runtime.navigate(ScreenType.PNC_INSTITUTE)
        factory = Mock(return_value=runtime)

        result = self.dispatcher(factory, self.scope).execute(step=self.step(castle=self.castle))

        self.assertTrue(result.succeeded)
        self.assertEqual(ResearchDisposition.NO_VISIBLE_SUPPORTED_NODE, result.value.disposition)
        self.assertEqual(checkpoint, result.value.checkpoint)
        self.assertEqual(ScreenType.PNC_HOME_CITY, result.exit_screen)
        factory.assert_called_once()
        runtime.preflight_active_castle_identity.assert_called_once()
        runtime.actuator.execute_action.assert_not_called()
        runtime.close.assert_not_called()

    def test_missing_scope_and_unsupported_category_stop_before_runtime_factory(self):
        factory = Mock()
        with self.assertRaisesRegex(PermissionError, "CoreMutationBoundary"):
            self.dispatcher(factory, None).execute(step=self.step())
        with self.assertRaisesRegex(ValueError, "Development-only"):
            self.dispatcher(factory, self.scope).execute(step=self.step(priority="economy"))
        factory.assert_not_called()

    def test_wrong_requested_castle_and_journal_date_stop_before_runtime_factory(self):
        factory = Mock()
        with self.assertRaisesRegex(PermissionError, "account/castle"):
            self.dispatcher(factory, self.scope).execute(step=self.step(castle=CastleIdentity("K2", "Other", 20)))
        self.store.save(DailyTaskCheckpoint("2026-09-12", "reset", "account", self.castle))
        with self.assertRaisesRegex(PermissionError, "checkpoint"):
            self.dispatcher(factory, self.scope).execute(step=self.step())
        factory.assert_not_called()

    def test_wrong_active_identity_prevents_node_navigation(self):
        runtime = Runtime(CastleIdentity("K2", "Other", 20), ())
        with self.assertRaisesRegex(PermissionError, "active castle"):
            self.dispatcher(Mock(return_value=runtime), self.scope).execute(step=self.step())
        self.assertEqual([], runtime.targets)
        runtime.actuator.execute_action.assert_not_called()
