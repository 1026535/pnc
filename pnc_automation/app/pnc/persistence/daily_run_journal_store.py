"""Atomic persistence for daily-maintenance checkpoints and mutation intents."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Lock
from typing import Any

from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


_ALLOWED_TRANSITIONS = {
    MutationIntentState.PREPARED: MutationIntentState.DISPATCHED,
    MutationIntentState.DISPATCHED: MutationIntentState.RECONCILED,
    MutationIntentState.RECONCILED: MutationIntentState.COMMITTED,
}


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
            or checkpoint.castle != castle
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
        payload = json.dumps(_serialize_checkpoint(checkpoint), indent=2, sort_keys=True) + "\n"
        with self._lock:
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=path.parent,
                    prefix="journal-",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temporary_path = Path(handle.name)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, path)
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
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


def _serialize_checkpoint(checkpoint: DailyTaskCheckpoint) -> dict[str, Any]:
    """Converts one checkpoint to the versioned JSON storage schema."""

    return {
        "schema_version": 1,
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
                "quest_id": intent.quest_id.value,
                "state": intent.state.value,
                "expected_precondition": intent.expected_precondition,
                "expected_postcondition": intent.expected_postcondition,
                "diamond_budget": intent.diamond_budget,
                "diamonds_spent": intent.diamonds_spent,
                "metadata": intent.metadata,
            }
            for intent in checkpoint.mutation_intents
        ],
        "consumed_recovery_stages": list(checkpoint.consumed_recovery_stages),
        "last_typed_screen": None if checkpoint.last_typed_screen is None else checkpoint.last_typed_screen.value,
    }


def _deserialize_checkpoint(payload: Any) -> DailyTaskCheckpoint:
    """Builds one typed checkpoint from the exact version-one JSON schema."""

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported daily-maintenance journal schema.")
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
                quest_id=DailyQuestId(item["quest_id"]),
                state=MutationIntentState(item["state"]),
                expected_precondition=str(item["expected_precondition"]),
                expected_postcondition=str(item["expected_postcondition"]),
                diamond_budget=int(item["diamond_budget"]),
                diamonds_spent=int(item["diamonds_spent"]),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in intents_raw
        ),
        consumed_recovery_stages=tuple(str(item) for item in payload["consumed_recovery_stages"]),
        last_typed_screen=(
            None if payload.get("last_typed_screen") is None else ScreenType(payload["last_typed_screen"])
        ),
    )
