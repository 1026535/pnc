"""Bind the existing Daily claim authority and journal to the core lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.claim_executor import JournaledDailyClaimExecutor
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationDispatcher
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestRow, DailyTargetOutcome, DailyTaskCheckpoint, MutationIntentState,
)
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


@dataclass(frozen=True, slots=True)
class _ClaimObservationSession:
    """Supply only the fresh observation dependency of the canonical claim executor."""

    observe: Callable[[str], Observation]

    def observe_daily_quest(self, label: str) -> Observation:
        """Delegate capture and guards to the constrained workflow context."""

        return self.observe(label)


@dataclass(frozen=True, slots=True)
class CoreDailyClaimBoundary:
    """An exact claim-only scope; it grants no generic tap or capability execution."""

    target: DailyMaintenanceTargetConfig
    boundary: DailyRunBoundary
    authorizer: DailyMutationAuthorizer
    journal_store: DailyRunJournalStore

    def authorize(self) -> None:
        """Reject unsupported capabilities and missing authority before device access."""

        if self.target.capabilities:
            raise PermissionError("The core Daily claim boundary cannot execute action capabilities.")
        self.authorizer.require_claims(
            account_id=self.target.account_id,
            castle_ref=self.target.castle_ref,
            maintenance_date=self.boundary.maintenance_date,
            max_claims=self.target.max_claims,
        )

    def verify_active_castle(self, runtime: CoreRuntime) -> None:
        """Require the canonical nonselecting preflight before opening the claim flow."""

        self.authorize()
        if runtime.preflight_active_castle_identity() != self.target.castle:
            raise PermissionError("The active castle does not match the authorized Daily target.")

    def claim(
        self,
        *,
        runtime: CoreRuntime,
        observe: Callable[[str], Observation],
        row: DailyQuestRow,
        checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Use the existing executor once, preserving durable budget and ambiguity."""

        self.authorize()
        if (
            checkpoint.account_id != self.target.account_id
            or checkpoint.castle != self.target.castle
            or checkpoint.game_reset_id != self.boundary.game_reset_id
            or checkpoint.maintenance_date != self.boundary.maintenance_date.isoformat()
        ):
            raise PermissionError("Daily claim checkpoint does not match its authorized boundary.")
        persisted = self.journal_store.load(
            game_reset_id=checkpoint.game_reset_id,
            account_id=checkpoint.account_id,
            castle=checkpoint.castle,
        )
        if persisted is not None and persisted != checkpoint:
            raise RuntimeError("Daily claim checkpoint is stale relative to the durable journal.")
        if persisted is None and checkpoint.mutation_intents:
            raise RuntimeError("Daily claim history is missing from the durable journal.")
        if any(intent.state != MutationIntentState.COMMITTED for intent in checkpoint.mutation_intents):
            raise RuntimeError("An unresolved mutation must be reconciled before another claim.")
        executor = runtime.runtime.require_observed_action_executor(
            "Core Daily claims require the canonical observed action executor."
        )
        return JournaledDailyClaimExecutor(
            session=_ClaimObservationSession(observe),
            action_executor=executor,
            dispatcher=JournaledMutationDispatcher(self.journal_store),
            maximum_claims=self.target.max_claims,
        ).claim(row=row, checkpoint=checkpoint)
