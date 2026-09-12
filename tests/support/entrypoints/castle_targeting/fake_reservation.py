"""Synthetic FakeReservation fixture."""

from __future__ import annotations



class _FakeReservation:
    """Implements the closable/context-managed reservation contract for offline fakes."""

    def __init__(self) -> None:
        """Starts the fake reservation open."""

        self.closed = False

    def __enter__(self) -> "_FakeReservation":
        """Returns the fake reservation for a scoped CLI call."""

        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        """Closes the fake reservation at the end of a scoped call."""

        self.close()

    def close(self) -> None:
        """Records release while remaining idempotent."""

        self.closed = True
