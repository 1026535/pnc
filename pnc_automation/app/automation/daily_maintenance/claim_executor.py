"""Exactly-once Daily Quest claim execution from fresh visual row geometry."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.automation.daily_maintenance.coordinator import DailyQuestSession
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher,
    MutationOperation,
    MutationReconciliation,
)
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction
from pnc_automation.app.pnc.domain.daily_maintenance import (
    CoordinateProvenance,
    DailyQuestId,
    DailyQuestRow,
    DailyQuestRowState,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
)
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation, RowRecognitionStatus


@dataclass(slots=True)
class JournaledDailyClaimExecutor:
    """Claims one fresh row only after intent persistence and exact row re-resolution."""

    session: DailyQuestSession
    action_executor: ObservedActionExecutor
    dispatcher: JournaledMutationDispatcher
    maximum_claims: int

    def __post_init__(self) -> None:
        """Rejects an unbounded claim allowance."""

        if isinstance(self.maximum_claims, bool) or self.maximum_claims <= 0:
            raise ValueError("JournaledDailyClaimExecutor.maximum_claims must be positive.")

    def claim(
        self,
        *,
        row: DailyQuestRow,
        checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Dispatches one visual Claim and accepts only a proved row-state transition."""

        if row.row_status != RowRecognitionStatus.COMPLETE:
            raise RuntimeError("Daily Claim requires a complete visually resolved row.")
        if row.state != DailyQuestRowState.CLAIM:
            raise RuntimeError("Daily Claim requires a row currently in Claim state.")
        if row.coordinate_provenance != CoordinateProvenance.VISUAL_GEOMETRY:
            raise RuntimeError("Daily Claim requires visually materialized row geometry.")
        claim_count = sum(
            intent.quest_id == DailyQuestId.CLAIM_COMPLETED
            for intent in checkpoint.mutation_intents
        )
        if claim_count >= self.maximum_claims:
            raise PermissionError("Daily claim acknowledgement mutation cap has been exhausted.")
        operation_id = f"claim-{claim_count + 1:03d}-{row.quest_id.value}"
        source: Observation | None = None

        def dispatch() -> None:
            """Re-observes and resolves the exact visual fingerprint immediately before tapping."""

            nonlocal source
            source = self.session.observe_daily_quest(f"{operation_id}_pre")
            matching = tuple(
                entry
                for entry in source.entries(ListEntryKind.DAILY_QUEST)
                if entry.metadata.get("observation_fingerprint") == row.observation_fingerprint
                and entry.metadata.get("quest_id") == row.quest_id.value
                and entry.metadata.get("row_state") == DailyQuestRowState.CLAIM.value
                and entry.row_status == RowRecognitionStatus.COMPLETE
                and entry.action_point is not None
                and entry.action_bounds is not None
            )
            if len(matching) != 1:
                raise RuntimeError("Daily Claim row changed before dispatch; no tap was sent.")
            self.action_executor.execute_action(
                TapListEntryAction(
                    reason="claim_daily_quest_reward",
                    entry_kind=ListEntryKind.DAILY_QUEST,
                    metadata_key="observation_fingerprint",
                    metadata_value=row.observation_fingerprint,
                    use_action_point=True,
                ),
                source,
            )

        def reconcile() -> MutationReconciliation:
            """Uses one fresh typed observation to prove claim consumption or ambiguity."""

            after = self.session.observe_daily_quest(f"{operation_id}_post")
            same_quest_states = tuple(
                entry.metadata.get("row_state")
                for entry in after.entries(ListEntryKind.DAILY_QUEST)
                if entry.metadata.get("quest_id") == row.quest_id.value
            )
            artifact_paths = () if after.artifact_path is None else (str(after.artifact_path),)
            return MutationReconciliation(
                postcondition_proven=bool(same_quest_states)
                and all(
                    state in {
                        DailyQuestRowState.GO.value,
                        DailyQuestRowState.COMPLETED.value,
                        DailyQuestRowState.REQUIREMENT.value,
                    }
                    for state in same_quest_states
                ),
                original_precondition_proven=DailyQuestRowState.CLAIM.value in same_quest_states,
                artifact_paths=artifact_paths,
            )

        result = self.dispatcher.execute(
            checkpoint=checkpoint,
            operation=MutationOperation(
                operation_id=operation_id,
                quest_id=DailyQuestId.CLAIM_COMPLETED,
                expected_precondition=f"{row.quest_id.value} row is Claim with fresh fingerprint",
                expected_postcondition=f"{row.quest_id.value} row is no longer Claim",
            ),
            dispatch=dispatch,
            reconcile=reconcile,
        )
        status = (
            DailyTargetOutcomeStatus.SUCCESS
            if result.committed
            else DailyTargetOutcomeStatus.PENDING_CLARIFICATION
        )
        return result.checkpoint, DailyTargetOutcome(
            quest_id=row.quest_id,
            status=status,
            message=(
                "Daily reward claim was observed and committed."
                if result.committed
                else "Daily reward claim result was ambiguous; the mutation will not be replayed."
            ),
            artifact_paths=result.artifact_paths,
        )
