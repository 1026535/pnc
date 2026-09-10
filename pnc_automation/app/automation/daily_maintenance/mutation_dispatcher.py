"""Exactly-once mutation dispatch and reconciliation for daily capabilities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


@dataclass(frozen=True, slots=True)
class MutationOperation:
    """Defines one bounded, independently journaled live mutation."""

    operation_id: str
    quest_id: DailyQuestId
    expected_precondition: str
    expected_postcondition: str
    diamond_budget: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MutationReconciliation:
    """Reports the one fresh post-dispatch reconciliation observation."""

    postcondition_proven: bool
    original_precondition_proven: bool
    diamonds_spent: int = 0
    artifact_paths: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects ambiguous contradictory proof and negative spend."""

        if self.postcondition_proven and self.original_precondition_proven:
            raise ValueError("Mutation reconciliation cannot prove both precondition and postcondition.")
        if self.diamonds_spent < 0:
            raise ValueError("Mutation reconciliation diamonds_spent cannot be negative.")


@dataclass(frozen=True, slots=True)
class JournaledMutationResult:
    """Returns the durable checkpoint and reconciliation disposition."""

    checkpoint: DailyTaskCheckpoint
    committed: bool
    retry_permitted: bool
    pending_clarification: bool
    artifact_paths: tuple[str, ...]


@dataclass(slots=True)
class JournaledMutationDispatcher:
    """Persists intent before dispatch and reconciles exactly once afterward."""

    journal_store: DailyRunJournalStore

    def execute(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
        operation: MutationOperation,
        dispatch: Callable[[], None],
        reconcile: Callable[[], MutationReconciliation],
    ) -> JournaledMutationResult:
        """Executes one fresh operation through prepared/dispatched/reconciled/committed."""

        intent = MutationIntent(
            operation_id=operation.operation_id,
            quest_id=operation.quest_id,
            state=MutationIntentState.PREPARED,
            expected_precondition=operation.expected_precondition,
            expected_postcondition=operation.expected_postcondition,
            diamond_budget=operation.diamond_budget,
            metadata=dict(operation.metadata),
        )
        checkpoint = self.journal_store.prepare_intent(checkpoint, intent)
        checkpoint = self.journal_store.transition_intent(
            checkpoint,
            operation.operation_id,
            MutationIntentState.DISPATCHED,
        )
        dispatch()
        return self._reconcile(
            checkpoint=checkpoint,
            operation=operation,
            reconcile=reconcile,
        )

    def reconcile_existing(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
        operation_id: str,
        reconcile: Callable[[], MutationReconciliation],
    ) -> JournaledMutationResult:
        """Reconciles one interrupted prepared/dispatched operation without blind replay."""

        intent = next(
            (item for item in checkpoint.mutation_intents if item.operation_id == operation_id),
            None,
        )
        if intent is None:
            raise KeyError(f"Mutation operation '{operation_id}' does not exist.")
        if intent.state == MutationIntentState.PREPARED:
            return JournaledMutationResult(
                checkpoint=checkpoint,
                committed=False,
                retry_permitted=True,
                pending_clarification=False,
                artifact_paths=(),
            )
        if intent.state == MutationIntentState.RECONCILED:
            result = reconcile()
            if result.postcondition_proven:
                checkpoint = self.journal_store.transition_intent(
                    checkpoint,
                    operation_id,
                    MutationIntentState.COMMITTED,
                    diamonds_spent=result.diamonds_spent,
                    metadata={
                        "postcondition_proven": True,
                        "artifact_paths": list(result.artifact_paths),
                        **result.metadata,
                    },
                )
                return JournaledMutationResult(
                    checkpoint=checkpoint,
                    committed=True,
                    retry_permitted=False,
                    pending_clarification=False,
                    artifact_paths=result.artifact_paths,
                )
            return JournaledMutationResult(
                checkpoint=checkpoint,
                committed=False,
                retry_permitted=False,
                pending_clarification=True,
                artifact_paths=result.artifact_paths,
            )
        if intent.state != MutationIntentState.DISPATCHED:
            raise ValueError(
                f"Only prepared or dispatched operations can resume; '{operation_id}' is "
                f"'{intent.state.value}'."
            )
        operation = MutationOperation(
            operation_id=intent.operation_id,
            quest_id=intent.quest_id,
            expected_precondition=intent.expected_precondition,
            expected_postcondition=intent.expected_postcondition,
            diamond_budget=intent.diamond_budget,
            metadata=dict(intent.metadata),
        )
        return self._reconcile(checkpoint=checkpoint, operation=operation, reconcile=reconcile)

    def _reconcile(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
        operation: MutationOperation,
        reconcile: Callable[[], MutationReconciliation],
    ) -> JournaledMutationResult:
        """Consumes one reconciliation observation and commits only a proven postcondition."""

        result = reconcile()
        metadata = {
            "postcondition_proven": result.postcondition_proven,
            "original_precondition_proven": result.original_precondition_proven,
            "artifact_paths": list(result.artifact_paths),
            **result.metadata,
        }
        checkpoint = self.journal_store.transition_intent(
            checkpoint,
            operation.operation_id,
            MutationIntentState.RECONCILED,
            diamonds_spent=result.diamonds_spent,
            metadata=metadata,
        )
        if result.postcondition_proven:
            checkpoint = self.journal_store.transition_intent(
                checkpoint,
                operation.operation_id,
                MutationIntentState.COMMITTED,
            )
            return JournaledMutationResult(
                checkpoint=checkpoint,
                committed=True,
                retry_permitted=False,
                pending_clarification=False,
                artifact_paths=result.artifact_paths,
            )
        return JournaledMutationResult(
            checkpoint=checkpoint,
            committed=False,
            retry_permitted=result.original_precondition_proven,
            pending_clarification=not result.original_precondition_proven,
            artifact_paths=result.artifact_paths,
        )
