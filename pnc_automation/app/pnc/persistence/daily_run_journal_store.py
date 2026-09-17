"""Atomic persistence for daily-maintenance checkpoints and mutation intents."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Lock
from time import sleep
from typing import Any

from pnc_automation.app.pnc.domain.castles import CastleIdentity, castle_identity_key
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationBudgetKind,
    MutationIntent,
    MutationIntentState,
    WorkshopInvocationRecord,
)
from pnc_automation.app.pnc.domain.feature_actions import (
    is_workshop_journaled_action,
    normalize_journaled_action_kind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.storage.atomic_file import atomic_write_bytes, replace_flushed_file
from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


_ALLOWED_TRANSITIONS = {
    MutationIntentState.PREPARED: MutationIntentState.DISPATCHED,
    MutationIntentState.DISPATCHED: MutationIntentState.RECONCILED,
    MutationIntentState.RECONCILED: MutationIntentState.COMMITTED,
}

def _replace_checkpoint_file(source: Path, destination: Path) -> None:
    """Retry transient Windows denial of replacement without rewriting the payload.

    Open handles can briefly deny replacement even with valid file permissions.
    Keep the old journal intact and retry only the same flushed temporary file;
    persistent denials and other I/O errors must still stop mutation dispatch.
    """
    replace_flushed_file(source, destination, replace=os.replace, sleep_function=sleep)


@dataclass(frozen=True, slots=True)
class PendingWorkshopOperation:
    """One unresolved journaled Workshop operation and its original references."""

    journal_path: Path
    game_reset_id: str
    account_id: str
    castle: CastleIdentity
    checkpoint: DailyTaskCheckpoint
    intent: MutationIntent

    @property
    def operation_id(self) -> str:
        """The durable operation id assigned by its original invocation."""

        return self.intent.operation_id

    @property
    def invocation_id(self) -> str | None:
        """The invocation that journaled this operation, when recorded."""

        return self.intent.invocation_id


@dataclass(slots=True)
class DailyRunJournalStore:
    """Owns one durable checkpoint file per reset/account/castle boundary."""

    root: Path
    _lock: Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Resolves the artifact root and initializes write serialization."""

        self.root = self.root.resolve()
        self._lock = Lock()

    def checkpoint_path(
        self,
        *,
        game_reset_id: str,
        account_id: str,
        castle: CastleIdentity,
    ) -> Path:
        """Keys receipts by game reset so local midnight cannot renew mutation budgets."""

        castle_segment = sanitize_artifact_segment(f"{castle.kingdom}_{castle.castle_name}")
        return (
            self.root
            / sanitize_artifact_segment(game_reset_id)
            / sanitize_artifact_segment(account_id)
            / castle_segment
            / "daily-maintenance"
            / "journal.json"
        )

    def load(
        self,
        *,
        game_reset_id: str,
        account_id: str,
        castle: CastleIdentity,
    ) -> DailyTaskCheckpoint | None:
        """Loads and validates one existing checkpoint when present."""

        path = self.checkpoint_path(
            game_reset_id=game_reset_id,
            account_id=account_id,
            castle=castle,
        )
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            checkpoint = _deserialize_checkpoint(payload)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise ConfigurationError("Daily-maintenance journal is malformed.", path=str(path)) from error
        if (
            checkpoint.game_reset_id != game_reset_id
            or checkpoint.account_id != account_id
            or castle_identity_key(checkpoint.castle) != castle_identity_key(castle)
        ):
            raise ConfigurationError("Daily-maintenance journal identity does not match its path.", path=str(path))
        return checkpoint

    def save(self, checkpoint: DailyTaskCheckpoint) -> Path:
        """Atomically replaces one checkpoint after flushing its complete JSON payload."""

        path = self.checkpoint_path(
            game_reset_id=checkpoint.game_reset_id,
            account_id=checkpoint.account_id,
            castle=checkpoint.castle,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(_serialize_checkpoint(checkpoint), indent=2, sort_keys=True) + "\n").encode("utf-8")
        with self._lock:
            atomic_write_bytes(
                path,
                payload,
                prefix="journal-",
                suffix=".tmp",
                replace=os.replace,
                sleep_function=sleep,
            )
        return path

    def prepare_intent(self, checkpoint: DailyTaskCheckpoint, intent: MutationIntent) -> DailyTaskCheckpoint:
        """Persists a new prepared intent before its operation may dispatch."""

        if intent.state != MutationIntentState.PREPARED:
            raise ValueError("New mutation intents must start in prepared state.")
        if any(existing.operation_id == intent.operation_id for existing in checkpoint.mutation_intents):
            raise ValueError(f"Mutation operation '{intent.operation_id}' already exists.")
        updated = replace(checkpoint, mutation_intents=(*checkpoint.mutation_intents, intent))
        self.save(updated)
        return updated

    def transition_intent(
        self,
        checkpoint: DailyTaskCheckpoint,
        operation_id: str,
        next_state: MutationIntentState,
        *,
        diamonds_spent: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DailyTaskCheckpoint:
        """Persists one legal forward-only mutation transition."""

        intents = list(checkpoint.mutation_intents)
        for index, intent in enumerate(intents):
            if intent.operation_id != operation_id:
                continue
            expected_state = _ALLOWED_TRANSITIONS.get(intent.state)
            if expected_state != next_state:
                raise ValueError(
                    f"Mutation operation '{operation_id}' cannot transition from "
                    f"'{intent.state.value}' to '{next_state.value}'."
                )
            merged_metadata = dict(intent.metadata)
            if metadata is not None:
                merged_metadata.update(metadata)
            intents[index] = replace(
                intent,
                state=next_state,
                diamonds_spent=intent.diamonds_spent if diamonds_spent is None else diamonds_spent,
                metadata=merged_metadata,
            )
            updated = replace(checkpoint, mutation_intents=tuple(intents))
            self.save(updated)
            return updated
        raise KeyError(f"Mutation operation '{operation_id}' does not exist.")

    def mark_completed(self, checkpoint: DailyTaskCheckpoint, quest_id: DailyQuestId) -> DailyTaskCheckpoint:
        """Persists one completed capability idempotently."""

        if quest_id in checkpoint.completed_quest_ids:
            return checkpoint
        updated = replace(
            checkpoint,
            current_quest_id=None,
            completed_quest_ids=(*checkpoint.completed_quest_ids, quest_id),
        )
        self.save(updated)
        return updated

    def consume_recovery_stage(self, checkpoint: DailyTaskCheckpoint, stage: str) -> DailyTaskCheckpoint:
        """Consumes one recovery stage once and rejects cyclic reuse."""

        if not stage.strip():
            raise ValueError("Recovery stage cannot be empty.")
        if stage in checkpoint.consumed_recovery_stages:
            raise ValueError(f"Recovery stage '{stage}' was already consumed.")
        updated = replace(
            checkpoint,
            consumed_recovery_stages=(*checkpoint.consumed_recovery_stages, stage),
        )
        self.save(updated)
        return updated

    def find_pending_workshop_operations(
        self,
        *,
        account_id: str,
        castle: CastleIdentity,
    ) -> tuple[PendingWorkshopOperation, ...]:
        """Finds unresolved Workshop intents for one castle across every reset partition."""

        if not self.root.is_dir():
            return ()
        account_segment = sanitize_artifact_segment(account_id)
        castle_segment = sanitize_artifact_segment(f"{castle.kingdom}_{castle.castle_name}")
        pending: list[PendingWorkshopOperation] = []
        for reset_dir in sorted(self.root.iterdir()):
            if not reset_dir.is_dir():
                continue
            path = reset_dir / account_segment / castle_segment / "daily-maintenance" / "journal.json"
            if not path.is_file():
                continue
            try:
                checkpoint = _deserialize_checkpoint(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                raise ConfigurationError("Daily-maintenance journal is malformed.", path=str(path)) from error
            if (
                sanitize_artifact_segment(checkpoint.game_reset_id) != reset_dir.name
                or checkpoint.account_id != account_id
                or castle_identity_key(checkpoint.castle) != castle_identity_key(castle)
            ):
                raise ConfigurationError(
                    "Daily-maintenance journal identity does not match its path.",
                    path=str(path),
                )
            pending.extend(
                PendingWorkshopOperation(
                    journal_path=path,
                    game_reset_id=checkpoint.game_reset_id,
                    account_id=account_id,
                    castle=checkpoint.castle,
                    checkpoint=checkpoint,
                    intent=intent,
                )
                for intent in checkpoint.mutation_intents
                if is_workshop_journaled_action(intent.action_kind)
                and intent.state is not MutationIntentState.COMMITTED
            )
        return tuple(pending)

    def register_workshop_invocation(
        self,
        checkpoint: DailyTaskCheckpoint,
        record: WorkshopInvocationRecord,
    ) -> DailyTaskCheckpoint:
        """Persists one new Workshop invocation identity before its first mutation."""

        if not isinstance(record, WorkshopInvocationRecord):
            raise TypeError("Workshop invocations must be WorkshopInvocationRecord values.")
        if any(existing.invocation_id == record.invocation_id for existing in checkpoint.workshop_invocations):
            raise ValueError(f"Workshop invocation '{record.invocation_id}' already exists.")
        updated = replace(
            checkpoint,
            workshop_invocations=(*checkpoint.workshop_invocations, record),
        )
        self.save(updated)
        return updated

    def update_workshop_invocation(
        self,
        checkpoint: DailyTaskCheckpoint,
        record: WorkshopInvocationRecord,
    ) -> DailyTaskCheckpoint:
        """Persists the latest state of one registered Workshop invocation."""

        records = list(checkpoint.workshop_invocations)
        for index, existing in enumerate(records):
            if existing.invocation_id != record.invocation_id:
                continue
            records[index] = record
            updated = replace(checkpoint, workshop_invocations=tuple(records))
            self.save(updated)
            return updated
        raise KeyError(f"Workshop invocation '{record.invocation_id}' does not exist.")

    def allocate_workshop_operation_id(
        self,
        checkpoint: DailyTaskCheckpoint,
        invocation_id: str,
    ) -> tuple[DailyTaskCheckpoint, str]:
        """Assigns the next durable operation id inside one registered invocation."""

        record = next(
            (item for item in checkpoint.workshop_invocations if item.invocation_id == invocation_id),
            None,
        )
        if record is None:
            raise KeyError(f"Workshop invocation '{invocation_id}' does not exist.")
        sequence = record.operation_sequence + 1
        checkpoint = self.update_workshop_invocation(
            checkpoint,
            replace(record, operation_sequence=sequence),
        )
        return checkpoint, f"{invocation_id}-op-{sequence}"


def _serialize_checkpoint(checkpoint: DailyTaskCheckpoint) -> dict[str, Any]:
    """Converts one checkpoint to the canonical version-two JSON storage schema."""

    return {
        "schema_version": 2,
        "maintenance_date": checkpoint.maintenance_date,
        "game_reset_id": checkpoint.game_reset_id,
        "account_id": checkpoint.account_id,
        "castle": {
            "kingdom": checkpoint.castle.kingdom,
            "castle_name": checkpoint.castle.castle_name,
            "castle_level": checkpoint.castle.castle_level,
        },
        "current_quest_id": None if checkpoint.current_quest_id is None else checkpoint.current_quest_id.value,
        "completed_quest_ids": [item.value for item in checkpoint.completed_quest_ids],
        "mutation_intents": [
            {
                "operation_id": intent.operation_id,
                "quest_id": None if intent.quest_id is None else intent.quest_id.value,
                "state": intent.state.value,
                "expected_precondition": intent.expected_precondition,
                "expected_postcondition": intent.expected_postcondition,
                "diamond_budget": intent.diamond_budget,
                "diamonds_spent": intent.diamonds_spent,
                "metadata": intent.metadata,
                "action_kind": intent.action_kind,
                "target": intent.target,
                "invocation_id": intent.invocation_id,
            }
            for intent in checkpoint.mutation_intents
        ],
        "consumed_recovery_stages": list(checkpoint.consumed_recovery_stages),
        "last_typed_screen": None if checkpoint.last_typed_screen is None else checkpoint.last_typed_screen.value,
        "workshop_invocations": [
            {
                "invocation_id": record.invocation_id,
                "action_kind": record.action_kind,
                "budget_kind": record.budget_kind.value,
                "max_mutations": record.max_mutations,
                "operation_sequence": record.operation_sequence,
                "pending_operation_id": record.pending_operation_id,
                "stop_reason": record.stop_reason,
                "metadata": record.metadata,
            }
            for record in checkpoint.workshop_invocations
        ],
    }


def _deserialize_checkpoint(payload: Any) -> DailyTaskCheckpoint:
    """Builds one typed checkpoint from a supported versioned JSON schema."""

    if not isinstance(payload, dict) or payload.get("schema_version") not in (1, 2):
        raise ValueError("Unsupported daily-maintenance journal schema.")
    schema_version = payload["schema_version"]
    castle_raw = payload["castle"]
    if not isinstance(castle_raw, dict):
        raise TypeError("Journal castle must be a mapping.")
    intents_raw = payload["mutation_intents"]
    if not isinstance(intents_raw, list):
        raise TypeError("Journal mutation_intents must be a list.")
    return DailyTaskCheckpoint(
        maintenance_date=str(payload["maintenance_date"]),
        game_reset_id=str(payload["game_reset_id"]),
        account_id=str(payload["account_id"]),
        castle=CastleIdentity(
            kingdom=str(castle_raw["kingdom"]),
            castle_name=str(castle_raw["castle_name"]),
            castle_level=castle_raw.get("castle_level"),
        ),
        current_quest_id=(
            None if payload.get("current_quest_id") is None else DailyQuestId(payload["current_quest_id"])
        ),
        completed_quest_ids=tuple(DailyQuestId(item) for item in payload["completed_quest_ids"]),
        mutation_intents=tuple(
            MutationIntent(
                operation_id=str(item["operation_id"]),
                quest_id=(None if item.get("quest_id") is None else DailyQuestId(item["quest_id"])),
                state=MutationIntentState(item["state"]),
                expected_precondition=str(item["expected_precondition"]),
                expected_postcondition=str(item["expected_postcondition"]),
                diamond_budget=int(item["diamond_budget"]),
                diamonds_spent=int(item["diamonds_spent"]),
                metadata=dict(item.get("metadata") or {}),
                action_kind=(
                    None
                    if item.get("action_kind") is None
                    else normalize_journaled_action_kind(item["action_kind"]).value
                ),
                target=(None if item.get("target") is None else dict(item["target"])),
                invocation_id=(None if schema_version == 1 else item.get("invocation_id")),
            )
            for item in intents_raw
        ),
        consumed_recovery_stages=tuple(str(item) for item in payload["consumed_recovery_stages"]),
        last_typed_screen=(
            None if payload.get("last_typed_screen") is None else ScreenType(payload["last_typed_screen"])
        ),
        workshop_invocations=(
            () if schema_version == 1 else _deserialize_workshop_invocations(payload)
        ),
    )


def _deserialize_workshop_invocations(payload: dict[str, Any]) -> tuple[WorkshopInvocationRecord, ...]:
    """Builds the version-two Workshop invocation records for one checkpoint."""

    records_raw = payload["workshop_invocations"]
    if not isinstance(records_raw, list):
        raise TypeError("Journal workshop_invocations must be a list.")
    return tuple(
        WorkshopInvocationRecord(
            invocation_id=str(item["invocation_id"]),
            action_kind=str(item["action_kind"]),
            budget_kind=MutationBudgetKind(item["budget_kind"]),
            max_mutations=(None if item.get("max_mutations") is None else int(item["max_mutations"])),
            operation_sequence=int(item["operation_sequence"]),
            pending_operation_id=item.get("pending_operation_id"),
            stop_reason=item.get("stop_reason"),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in records_raw
    )
