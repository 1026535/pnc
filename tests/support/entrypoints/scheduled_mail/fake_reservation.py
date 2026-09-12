"""Synthetic FakeReservation fixture."""

from __future__ import annotations



class _FakeReservation:
    """Implements the closable context contract for offline routing tests."""

    def __init__(self) -> None:
        """Starts open."""

        self.closed = False

    def __enter__(self) -> "_FakeReservation":
        """Returns this reservation for a scoped call."""

        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        """Closes the reservation at scope exit."""

        self.close()

    def close(self) -> None:
        """Releases the fake reservation idempotently."""

        self.closed = True
