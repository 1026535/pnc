"""Connected claim-only runner for the first promoted Daily maintenance slice."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.automation.daily_maintenance.application_service import (
    DailyCastleRunSummary,
    DailyRunBoundary,
)
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.claim_executor import JournaledDailyClaimExecutor
from pnc_automation.app.automation.daily_maintenance.coordinator import (
    DailyMaintenanceCoordinator,
)
from pnc_automation.app.automation.daily_maintenance.live_session import ConnectedDailyQuestSession
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationDispatcher
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.authoring.config.models import AccountConfig, AppConfig, LiveAutomationRole
from pnc_automation.app.automation.engine.script_runner import (
    ConnectedAutomationRuntime,
    ScriptRunner,
    require_successful_preparation,
)
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestRow,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationAcknowledgement,
    MutationIntentState,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
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
        acknowledgement = self.authorizer.require_claims(
            account_id=target.account_id,
            castle_ref=target.castle_ref,
            maintenance_date=boundary.maintenance_date,
            max_claims=target.max_claims,
        )
        with self.script_runner.reserve_accounts((target.account_id,)):
            preparation = require_successful_preparation(
                self.script_runner.prepare_account_session(
                    account_id=target.account_id,
                    castle=target.castle,
                    required_role=LiveAutomationRole.DAILY_CANARY,
                )
            )

            with self.script_runner.build_connected_runtime_bundle(
                account=account,
                required_role=LiveAutomationRole.DAILY_CANARY,
            ) as bundle:
                return self._run_connected_castle(
                    target=target,
                    boundary=boundary,
                    account=account,
                    acknowledgement=acknowledgement,
                    bundle=bundle,
                )

    def _run_connected_castle(
        self,
        *,
        target: DailyMaintenanceTargetConfig,
        boundary: DailyRunBoundary,
        account: AccountConfig,
        acknowledgement: MutationAcknowledgement,
        bundle: ConnectedAutomationRuntime,
    ) -> DailyCastleRunSummary:
        """Runs the connected portion while the caller owns its lease bundle."""

        connected = bundle.runtime
        action_executor = connected.require_observed_action_executor(
            "Daily claims require the canonical selector-backed action executor."
        )
        session = ConnectedDailyQuestSession(
            runner=bundle.runner,
            observation_service=connected.observation_service,
            action_executor=action_executor,
        )
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
        coordinator = DailyMaintenanceCoordinator(
            session=session,
            claim_executor=JournaledDailyClaimExecutor(
                session=session,
                action_executor=action_executor,
                dispatcher=JournaledMutationDispatcher(journal_store),
                maximum_claims=acknowledgement.max_mutations,
            ),
            capability_executor=_RejectingCapabilityExecutor(),
            journal_store=journal_store,
            catalog=DailyQuestCatalog(),
        )
        result = coordinator.run(target=target, checkpoint=checkpoint)
        failed_outcomes = tuple(
            outcome for outcome in result.outcomes
            if outcome.status not in {
                DailyTargetOutcomeStatus.SUCCESS,
                DailyTargetOutcomeStatus.APPLICABILITY_SKIP,
            }
        )
        succeeded = not failed_outcomes
        message = (
            f"Claim sweep completed across {result.scanned_viewports} viewports."
            if succeeded else
            f"Claim sweep stopped with {len(failed_outcomes)} unresolved outcome(s) "
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


class _RejectingCapabilityExecutor:
    """Fails closed if configuration bypasses pre-ADB capability promotion checks."""

    def execute(self, *, row: DailyQuestRow, target, checkpoint) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Rejects execution because no action capability has passed its live promotion gate."""

        del target, checkpoint
        raise PermissionError(f"Daily capability '{row.quest_id.value}' is not promoted.")
