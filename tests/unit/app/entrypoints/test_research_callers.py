"""Caller boundaries for the Development-only replacement-core Research workflow."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyCapabilityPolicy,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.automation.engine.script_runner import ScriptRunner
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CredentialSource,
    LiveAutomationRole,
    ResolvedCredentials,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, MutationAcknowledgement
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


class ResearchCallerTests(unittest.TestCase):
    """Proves caller validation and role wiring before a session is connected."""

    def test_run_research_rejects_wrong_journal_root_before_building_runtime(self) -> None:
        """Rejects a scope bound to another journal root before any device work."""

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            scope = _research_scope(root / "journal")
            account = _account()
            script_runner = Mock(spec=ScriptRunner)
            script_runner.config.require_account.return_value = account
            script_runner.config.artifact_root = root / "other-journal"

            with patch("pnc_automation.app.entrypoints.app.build_core_runtime") as build_core_runtime:
                with self.assertRaisesRegex(PermissionError, "configured durable journal root"):
                    ApplicationRunner(script_runner).run_research(
                        account_id=account.id,
                        params={"priority": ["development"]},
                        mutation_boundary=scope,
                    )

            build_core_runtime.assert_not_called()

    def test_run_research_forwards_scope_and_daily_canary_role(self) -> None:
        """Builds one canary runtime and runs the typed workflow with the supplied scope."""

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            scope = _research_scope(root)
            account = _account()
            script_runner = Mock(spec=ScriptRunner)
            script_runner.config.require_account.return_value = account
            script_runner.config.artifact_root = root
            core_runtime = Mock()
            expected = CoreWorkflowResult(
                workflow_name="research",
                succeeded=True,
                value=object(),
                exit_screen=ScreenType.PNC_HOME_CITY,
                trace_path="trace.jsonl",
            )
            cleanup_policy = object()

            with (
                patch(
                    "pnc_automation.app.entrypoints.app.build_core_runtime",
                    return_value=core_runtime,
                ) as build_core_runtime,
                patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner") as workflow_runner,
            ):
                workflow_runner.return_value.run.return_value = expected
                result = ApplicationRunner(script_runner).run_research(
                    account_id=account.id,
                    params={"priority": ["development"]},
                    mutation_boundary=scope,
                    session_cleanup_policy=cleanup_policy,
                )

            self.assertIs(result, expected)
            build_core_runtime.assert_called_once_with(
                script_runner,
                account,
                account.artifact_directory_name,
                required_role=LiveAutomationRole.DAILY_CANARY,
                session_cleanup_policy=cleanup_policy,
            )
            workflow_runner.assert_called_once_with(core_runtime, scope)
            core_runtime.close.assert_called_once_with()

    def test_run_research_rejects_legacy_broad_default_before_building_runtime(self) -> None:
        """Preserves the broad legacy default while rejecting it at the typed boundary."""

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            scope = _research_scope(root)
            account = _account()
            script_runner = Mock(spec=ScriptRunner)
            script_runner.config.require_account.return_value = account
            script_runner.config.artifact_root = root

            with patch("pnc_automation.app.entrypoints.app.build_core_runtime") as build_core_runtime:
                with self.assertRaisesRegex(ValueError, "Development-only"):
                    ApplicationRunner(script_runner).run_research(
                        account_id=account.id,
                        params={},
                        mutation_boundary=scope,
                    )

            build_core_runtime.assert_not_called()

    def test_authored_research_rejects_explicit_non_canary_role_before_connection(self) -> None:
        """Keeps Research on its exact canary authority when a caller supplies another role."""

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            scope = _research_scope(root)
            account = _account()
            config = Mock()
            config.artifact_root = root
            config.find_castle_targets.return_value = ()
            script_runner = ScriptRunner(
                config=config,
                task_registry=build_default_task_registry(),
                screenshot_service=Mock(),
                observation_builder=Mock(),
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=Mock(),
                instance_resolver=Mock(),
                logger=Mock(),
            )
            script = RunScript(
                name="research",
                path=Path("<test:research>"),
                steps=(
                    ScriptStep(
                        task=TaskId.RESEARCH,
                        params={"priority": ["development"]},
                    ),
                ),
            )

            with patch.object(ScriptRunner, "_build_runner") as build_runner:
                with self.assertRaisesRegex(PermissionError, "DAILY_CANARY"):
                    script_runner._run_script_for_account(
                        account=account,
                        script=script,
                        required_role=LiveAutomationRole.LIVE_TESTING,
                        mutation_boundary=scope,
                    )

            build_runner.assert_not_called()


def _account() -> AccountConfig:
    """Builds the minimal configured account needed by the application caller."""

    return AccountConfig(
        id="account_a",
        instance_id="instance",
        pnc_account_id="pnc-account",
        credentials=ResolvedCredentials(
            username="user",
            password="pass",
            source=CredentialSource.INLINE,
        ),
        live_roles=frozenset({LiveAutomationRole.DAILY_CANARY}),
    )


def _research_scope(root: Path) -> CoreMutationBoundary:
    """Builds an exact Development Research mutation scope with one acknowledgement."""

    castle = CastleIdentity("K1", "Castle", 20)
    maintenance_date = date(2026, 9, 13)
    return CoreMutationBoundary(
        target=DailyMaintenanceTargetConfig(
            account_id="account_a",
            castle_ref="castle",
            castle=castle,
            capabilities=(
                DailyCapabilityPolicy(
                    DailyQuestId.UPGRADE_RESEARCH,
                    TaskId.RESEARCH,
                    max_mutations=1,
                ),
            ),
        ),
        boundary=DailyRunBoundary(maintenance_date, "reset"),
        authorizer=DailyMutationAuthorizer(
            (
                MutationAcknowledgement(
                    "account_a",
                    "castle",
                    DailyQuestId.UPGRADE_RESEARCH,
                    maintenance_date,
                    1,
                    0,
                ),
            ),
        ),
        journal_store=DailyRunJournalStore(root),
    )


if __name__ == "__main__":
    unittest.main()
