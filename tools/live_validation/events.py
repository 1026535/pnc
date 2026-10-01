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


class DispatchCollector:
    """Attributes every observer event to the current run phase.

    The collector preserves executor evidence verbatim: it never mutates a
    receipt, never converts a failure into a receipt, and never manufactures a
    record for an input the runtime did not report.
    """

    def __init__(self) -> None:
        self._phase: AttributionPhase = AttributionPhase.SETUP
        self._case_id: str | None = None
        self._events: list[AttributedDispatch] = []

    @property
    def events(self) -> tuple[AttributedDispatch, ...]:
        return tuple(self._events)

    def append(self, event: InputDispatchEvent) -> None:
        self._events.append(
            AttributedDispatch(
                event_id=f"in-{len(self._events) + 1:04d}",
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
        """Finds the event id of one exact receipt object within a case."""

        for attributed in self._events:
            if attributed.case_id == case_id and attributed.event is receipt:
                return attributed.event_id
        return None
