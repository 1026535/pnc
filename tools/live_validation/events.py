"""Runner-owned attribution of actual input dispatch events.

The runtime observer delivers every typed dispatch receipt; this module binds
each record to the run phase and case in which it was produced. Attribution is
event-oriented metadata only — logical attempt counting stays in the journal,
and a receipt never asserts the UI accepted the gesture.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterator

from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchEvent,
    InputDispatchRecord,
)


class AttributionPhase(StrEnum):
    """The run phase in which one dispatch event was produced."""

    SETUP = "setup"
    CASE = "case"
    CLEANUP = "cleanup"


@dataclass(frozen=True, slots=True)
class AttributedDispatch:
    """One actual dispatch event bound to its producing phase and case."""

    event_id: str
    phase: AttributionPhase
    case_id: str | None
    event: InputDispatchEvent

    def __post_init__(self) -> None:
        if self.phase is AttributionPhase.CASE:
            if not self.case_id:
                raise ValueError("Case-phase dispatch events require a case_id.")
        elif self.case_id is not None:
            raise ValueError("Non-case dispatch events must not carry a case_id.")


class ReceiptIntegrityError(RuntimeError):
    """Physical input identity is duplicated or cannot be resolved exactly."""


def receipt_physical_key(event: InputDispatchEvent) -> tuple[str, int, int] | None:
    """Returns ``(session_id, session_epoch, input_sequence)`` for a receipt.

    This tuple is a physical input's unique identity within one session.
    Failure records carry no confirmed dispatch and return ``None``.
    """

    if not isinstance(event, InputDispatchRecord):
        return None
    frame = event.source_frame
    return (frame.session_id, frame.session_epoch, event.dispatch.input_sequence)


class DispatchCollector:
    """Attributes every observer event to the current run phase.

    The collector preserves executor evidence verbatim: it never mutates a
    receipt, never converts a failure into a receipt, and never manufactures a
    record for an input the runtime did not report. Physical receipt keys must
    stay unique for the whole run; a duplicate is recorded as an integrity
    error for the caller to halt on.
    """

    def __init__(self) -> None:
        self._phase: AttributionPhase = AttributionPhase.SETUP
        self._case_id: str | None = None
        self._events: list[AttributedDispatch] = []
        self._physical_keys: dict[tuple[str, int, int], str] = {}
        self._integrity_errors: list[str] = []

    @property
    def events(self) -> tuple[AttributedDispatch, ...]:
        return tuple(self._events)

    @property
    def integrity_errors(self) -> tuple[str, ...]:
        return tuple(self._integrity_errors)

    def append(self, event: InputDispatchEvent) -> None:
        event_id = f"in-{len(self._events) + 1:04d}"
        key = receipt_physical_key(event)
        if key is not None:
            owner = self._physical_keys.get(key)
            if owner is not None:
                self._integrity_errors.append(
                    f"duplicate physical input identity {key}: events "
                    f"{owner} and {event_id} claim the same dispatch."
                )
            else:
                self._physical_keys[key] = event_id
        self._events.append(
            AttributedDispatch(
                event_id=event_id,
                phase=self._phase,
                case_id=self._case_id,
                event=event,
            )
        )

    @contextmanager
    def phase(self, phase: AttributionPhase, *, case_id: str | None = None) -> Iterator[None]:
        """Attributes all subsequently observed events to one phase/case."""

        previous = (self._phase, self._case_id)
        if phase is AttributionPhase.CASE and not case_id:
            raise ValueError("Entering the case phase requires the owning case_id.")
        self._phase, self._case_id = phase, case_id
        try:
            yield
        finally:
            self._phase, self._case_id = previous

    def events_since(self, offset: int) -> tuple[AttributedDispatch, ...]:
        """Returns all events appended after the given marker position."""

        return tuple(self._events[offset:])

    def mark(self) -> int:
        """Returns the current end position for later ``events_since`` calls."""

        return len(self._events)

    def case_receipts(self, case_id: str) -> tuple[InputDispatchRecord, ...]:
        """Returns the successful dispatch receipts attributed to one case."""

        return tuple(
            attributed.event
            for attributed in self._events
            if attributed.case_id == case_id and isinstance(attributed.event, InputDispatchRecord)
        )

    def receipt_event_id(self, receipt: InputDispatchRecord, *, case_id: str) -> str | None:
        """Finds the event id of one receipt's exact physical identity in a case.

        Matching is by source identity — equal session, epoch, and input
        sequence — not object identity, so a distinct equal receipt still
        binds. ``None`` means no attributed receipt carries that identity;
        ``ReceiptIntegrityError`` means more than one does.
        """

        key = receipt_physical_key(receipt)
        matches = [
            attributed.event_id
            for attributed in self._events
            if attributed.case_id == case_id
            and isinstance(attributed.event, InputDispatchRecord)
            and receipt_physical_key(attributed.event) == key
        ]
        if len(matches) > 1:
            raise ReceiptIntegrityError(
                f"{len(matches)} case '{case_id}' receipts share physical key {key}."
            )
        return matches[0] if matches else None
