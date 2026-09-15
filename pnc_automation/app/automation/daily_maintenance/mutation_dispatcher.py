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
from pnc_automation.app.pnc.domain.building_operations import BuildingMutationKind
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


@dataclass(frozen=True, slots=True)
class MutationOperation:
    """Defines one bounded, independently journaled live mutation."""

    operation_id: str
    quest_id: DailyQuestId | None
    expected_precondition: str
    expected_postcondition: str
    diamond_budget: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
    action_kind: BuildingMutationKind | None = None
    target: dict[str, object] | None = None

    def __post_init__(self) -> None:
        """Validate optional feature action identity fields without changing Daily callers."""

        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("MutationOperation.operation_id cannot be empty.")
        if self.quest_id is not None and not isinstance(self.quest_id, DailyQuestId):
            raise TypeError("MutationOperation.quest_id must be a DailyQuestId or None.")
        if self.action_kind is not None and not isinstance(self.action_kind, BuildingMutationKind):
            raise TypeError("MutationOperation.action_kind must be a BuildingMutationKind or None.")
        if self.action_kind is not None and self.target is None:
            raise ValueError("Building MutationOperation requires an exact target.")


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
        revalidate_precondition: Callable[[], bool] | None = None,
    ) -> JournaledMutationResult:
        """Executes one fresh operation through prepared/dispatched/reconciled/committed."""

        existing = next(
            (item for item in checkpoint.mutation_intents if item.operation_id == operation.operation_id),
            None,
        )
        if existing is not None:
            if not _intent_matches_operation(existing, operation):
                raise ValueError(
                    f"Mutation operation '{operation.operation_id}' has a different action identity."
                )
            if (
                existing.state == MutationIntentState.PREPARED
                and revalidate_precondition is not None
            ):
                return self._resume_prepared(
                    checkpoint=checkpoint,
                    intent=existing,
                    revalidate_precondition=revalidate_precondition,
                    dispatch=dispatch,
                    reconcile=reconcile,
                )
            return self.reconcile_existing(
                checkpoint=checkpoint,
                operation_id=operation.operation_id,
                reconcile=reconcile,
            )
        intent = MutationIntent(
            operation_id=operation.operation_id,
            quest_id=operation.quest_id,
            state=MutationIntentState.PREPARED,
            expected_precondition=operation.expected_precondition,
            expected_postcondition=operation.expected_postcondition,
            diamond_budget=operation.diamond_budget,
            metadata=dict(operation.metadata),
            action_kind=None if operation.action_kind is None else operation.action_kind.value,
            target=None if operation.target is None else dict(operation.target),
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

    def _resume_prepared(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
        intent: MutationIntent,
        revalidate_precondition: Callable[[], bool],
        dispatch: Callable[[], None],
        reconcile: Callable[[], MutationReconciliation],
    ) -> JournaledMutationResult:
        """Resume one building PREPARED intent after its target is re-proved."""

        if not revalidate_precondition():
            return JournaledMutationResult(
                checkpoint=checkpoint,
                committed=False,
                retry_permitted=True,
                pending_clarification=False,
                artifact_paths=(),
            )
        checkpoint = self.journal_store.transition_intent(
            checkpoint,
            intent.operation_id,
            MutationIntentState.DISPATCHED,
        )
        dispatch()
        return self._reconcile(
            checkpoint=checkpoint,
            operation=_operation_from_intent(intent),
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
        if intent.state == MutationIntentState.COMMITTED:
            return JournaledMutationResult(
                checkpoint=checkpoint,
                committed=True,
                retry_permitted=False,
                pending_clarification=False,
                artifact_paths=tuple(_metadata_artifact_paths(intent.metadata)),
            )
        if intent.state != MutationIntentState.DISPATCHED:
            raise ValueError(
                f"Only prepared or dispatched operations can resume; '{operation_id}' is "
                f"'{intent.state.value}'."
            )
        operation = _operation_from_intent(intent)
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
        # A building operation may journal a target-bound follow-up (warning,
        # speedup confirmation, or Help) while its parent is still DISPATCHED.
        # Reload before the parent transition so that the follow-up intent is
        # not lost when the checkpoint is atomically rewritten.
        latest = self.journal_store.load(
            game_reset_id=checkpoint.game_reset_id,
            account_id=checkpoint.account_id,
            castle=checkpoint.castle,
        )
        if latest is not None:
            checkpoint = latest
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


def _intent_matches_operation(intent: MutationIntent, operation: MutationOperation) -> bool:
    """Require a retry to carry the same target and action identity."""

    # Building Daily-Go is optional progress context, not part of the durable
    # action identity.  A direct retry must therefore reconcile the same
    # receipt instead of being treated as a different operation (and the
    # stored budget remains authoritative for that retry).
    same_building_identity = (
        operation.action_kind is not None
        and intent.action_kind == operation.action_kind.value
    )
    return (
        (same_building_identity or intent.quest_id == operation.quest_id)
        and intent.expected_precondition == operation.expected_precondition
        and intent.expected_postcondition == operation.expected_postcondition
        and (same_building_identity or intent.diamond_budget == operation.diamond_budget)
        and intent.action_kind == (None if operation.action_kind is None else operation.action_kind.value)
        and intent.target == operation.target
    )


def _operation_from_intent(intent: MutationIntent) -> MutationOperation:
    """Rehydrate an exact operation from its durable journal record."""

    return MutationOperation(
        operation_id=intent.operation_id,
        quest_id=intent.quest_id,
        expected_precondition=intent.expected_precondition,
        expected_postcondition=intent.expected_postcondition,
        diamond_budget=intent.diamond_budget,
        metadata=dict(intent.metadata),
        action_kind=(
            None if intent.action_kind is None else BuildingMutationKind(intent.action_kind)
        ),
        target=None if intent.target is None else dict(intent.target),
    )


def _metadata_artifact_paths(metadata: dict[str, object]) -> tuple[str, ...]:
    """Read persisted artifact paths without trusting arbitrary metadata types."""

    value = metadata.get("artifact_paths")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))
