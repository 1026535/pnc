"""Persisted logical attempt journal for live validation runs.

Every consumed logical attempt — including attempts refused before physical
input — is appended to ``attempts.jsonl`` and fsynced before the associated
operation runs. A begin row references the attempt's authorizing frame; a
finish row binds the terminal status and, for dispatched attempts, the exact
attributed dispatch event id. Replay-safe: the journal can be scanned to list
attempts that began but never finished.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TextIO

from pnc_automation.app.automation.engine.developmental_control import ConsumedCaseAttempt


class AttemptStatus(StrEnum):
    """Terminal disposition of one logical attempt."""

    DISPATCHED = "dispatched"
    REFUSED = "refused"
    UNCERTAIN = "uncertain"
    ANNOTATION_TIMEOUT = "annotation_timeout"


class AttemptIntent(StrEnum):
    """The physical input one journaled attempt intended to send."""

    BODY_ENTRY = "body_entry"
    CONTROL = "control"
    ROUTE = "route"


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One deserialized journal row."""

    seq: int
    record_type: str
    attempt_id: str | None
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class PendingAttempt:
    """One begun attempt that has no terminal finish row yet."""

    attempt_id: str
    case_id: str
    control_name: str
    number: int
    limit: int
    intent: str
    journal_ref: str
    begin_seq: int


class LogicalAttemptJournal:
    """Appends fsynced attempt rows so every consumed ordinal is auditable."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file: TextIO = path.open("a", encoding="utf-8")
        self._seq = self._existing_seq(path)

    @staticmethod
    def _existing_seq(path: Path) -> int:
        try:
            rows = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return 0
        return sum(1 for row in rows if row.strip())

    @property
    def path(self) -> Path:
        return self._path

    def begin(
        self,
        *,
        case_id: str,
        control_name: str,
        operation_id: str,
        number: int,
        limit: int,
        source_frame: dict[str, object],
        intent: str = AttemptIntent.CONTROL,
    ) -> tuple[str, ConsumedCaseAttempt]:
        """Consumes one logical attempt and returns its journal-anchored handle.

        The consumed attempt is handed to the executor scope; its
        ``journal_ref`` points at this journal's begin row. ``intent`` names
        the physical input this attempt intends to send and is fsynced before
        that send.
        """

        self._seq += 1
        attempt_id = f"attempt-{self._seq:04d}"
        journal_ref = f"{self._path.name}#{self._seq}"
        self._append_row(
            {
                "seq": self._seq,
                "type": "attempt_begin",
                "attempt_id": attempt_id,
                "case_id": case_id,
                "control_name": control_name,
                "operation_id": operation_id,
                "number": number,
                "limit": limit,
                "intent": str(intent),
                "source_frame": source_frame,
            }
        )
        return attempt_id, ConsumedCaseAttempt(
            case_id=case_id,
            control_name=control_name,
            number=number,
            limit=limit,
            journal_ref=journal_ref,
        )

    def finish(
        self,
        attempt_id: str,
        *,
        status: AttemptStatus,
        dispatch_event_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Terminates one begun attempt, optionally bound to its receipt event."""

        self._seq += 1
        self._append_row(
            {
                "seq": self._seq,
                "type": "attempt_finish",
                "attempt_id": attempt_id,
                "status": status.value,
                "dispatch_event_id": dispatch_event_id,
                "detail": detail,
            }
        )

    def _append_row(self, row: dict[str, object]) -> None:
        self._file.write(json.dumps(row, sort_keys=True) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        self._file.close()


def read_journal(path: Path) -> tuple[JournalEntry, ...]:
    """Reads every journal row, in order."""

    entries: list[JournalEntry] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        entries.append(
            JournalEntry(
                seq=int(row["seq"]),
                record_type=str(row["type"]),
                attempt_id=row.get("attempt_id"),
                payload=row,
            )
        )
    return tuple(entries)


def pending_attempts(path: Path) -> tuple[PendingAttempt, ...]:
    """Lists begun attempts that never received a terminal finish row."""

    finished = {
        entry.attempt_id for entry in read_journal(path) if entry.record_type == "attempt_finish"
    }
    pending: list[PendingAttempt] = []
    for entry in read_journal(path):
        if entry.record_type != "attempt_begin" or entry.attempt_id in finished:
            continue
        pending.append(
            PendingAttempt(
                attempt_id=str(entry.attempt_id),
                case_id=str(entry.payload.get("case_id")),
                control_name=str(entry.payload.get("control_name")),
                number=int(entry.payload.get("number", 0)),
                limit=int(entry.payload.get("limit", 0)),
                intent=str(entry.payload.get("intent", AttemptIntent.CONTROL.value)),
                journal_ref=f"{path.name}#{entry.seq}",
                begin_seq=entry.seq,
            )
        )
    return tuple(pending)
