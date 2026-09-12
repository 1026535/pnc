"""Connected claim-only runner for the first promoted Daily maintenance slice."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.automation.daily_maintenance.application_service import (
    DailyCastleRunSummary,
    DailyRunBoundary,
)
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.core_daily_maintenance import CoreDailyMaintenanceWorkflow
from pnc_automation.app.automation.engine.core_daily_mutation import CoreDailyClaimBoundary
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime, build_core_runtime
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowRunner
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.authoring.config.models import AppConfig, LiveAutomationRole
from pnc_automation.app.automation.engine.script_runner import (
    ScriptRunner,
    require_successful_preparation,
)
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationIntentState,
)
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


@dataclass(slots=True)
class ConnectedClaimOnlyCastleRunner:
    """Runs the promoted claim sweep while rejecting every unpromoted capability."""

    instance_id: str
    app_config: AppConfig
    script_runner: ScriptRunner
    authorizer: DailyMutationAuthorizer

    def run_castle(
        self,
        *,
        target: DailyMaintenanceTargetConfig,
        boundary: DailyRunBoundary,
    ) -> DailyCastleRunSummary:
        """Aligns one castle, resumes its journal, and performs authorized claims."""

        account = self.app_config.require_account(target.account_id)
        if account.instance_id != self.instance_id:
            raise ValueError("Daily target was routed to the wrong instance worker.")
        account.require_live_role(LiveAutomationRole.DAILY_CANARY)
        if target.capabilities:
            labels = ", ".join(policy.quest_id.value for policy in target.capabilities)
            raise PermissionError(f"Daily capabilities are not promoted for unattended execution: {labels}.")
        self.authorizer.require_claims(
            account_id=target.account_id,
            castle_ref=target.castle_ref,
            maintenance_date=boundary.maintenance_date,
            max_claims=target.max_claims,
        )
        with self.script_runner.reserve_accounts((target.account_id,)):
            require_successful_preparation(
                self.script_runner.prepare_account_session(
                    account_id=target.account_id,
                    castle=target.castle,
                    required_role=LiveAutomationRole.DAILY_CANARY,
                )
            )

            with build_core_runtime(
                self.script_runner,
                account=account,
                artifact_directory=account.artifact_directory_name,
                required_role=LiveAutomationRole.DAILY_CANARY,
            ) as core:
                return self._run_connected_castle(
                    target=target,
                    boundary=boundary,
                    core=core,
                )

    def _run_connected_castle(
        self,
        *,
        target: DailyMaintenanceTargetConfig,
        boundary: DailyRunBoundary,
        core: CoreRuntime,
    ) -> DailyCastleRunSummary:
        """Runs the connected portion while the caller owns its lease bundle."""

        journal_store = DailyRunJournalStore(self.app_config.artifact_root)
        checkpoint = journal_store.load(
            game_reset_id=boundary.game_reset_id,
            account_id=target.account_id,
            castle=target.castle,
        ) or DailyTaskCheckpoint(
            maintenance_date=boundary.maintenance_date.isoformat(),
            game_reset_id=boundary.game_reset_id,
            account_id=target.account_id,
            castle=target.castle,
        )
        if checkpoint.game_reset_id != boundary.game_reset_id:
            raise RuntimeError("Existing Daily journal has a different game-reset identity.")
        unresolved = tuple(
            intent for intent in checkpoint.mutation_intents if intent.state != MutationIntentState.COMMITTED
        )
        if unresolved:
            raise RuntimeError(
                "Daily journal contains an unresolved mutation; reconcile it before another live run."
            )
        result = CoreWorkflowRunner(
            core,
            daily_claims=CoreDailyClaimBoundary(
                target=target, boundary=boundary, authorizer=self.authorizer,
                journal_store=journal_store,
            ),
        ).run(CoreDailyMaintenanceWorkflow(target, checkpoint, journal_store)).value
        failed_outcomes = tuple(
            outcome for outcome in result.outcomes
            if outcome.status not in {
                DailyTargetOutcomeStatus.SUCCESS,
                DailyTargetOutcomeStatus.APPLICABILITY_SKIP,
            }
        )
        succeeded = not failed_outcomes and not result.unknown_titles
        message = (
            f"Claim sweep completed across {result.scanned_viewports} viewports."
            if succeeded else
            f"Claim sweep stopped with {len(failed_outcomes)} unresolved outcome(s) "
            f"and {len(result.unknown_titles)} unknown title(s) "
            f"after {result.scanned_viewports} viewports."
        )
        journal_path = journal_store.checkpoint_path(
            game_reset_id=checkpoint.game_reset_id,
            account_id=target.account_id,
            castle=target.castle,
        )
        return DailyCastleRunSummary(
            account_id=target.account_id,
            castle_ref=target.castle_ref,
            succeeded=succeeded,
            message=message,
            artifact_paths=(str(journal_path),),
        )
