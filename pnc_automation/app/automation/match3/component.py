"""The shared match-3 battle API and its M0 unavailable implementation.

Feature callers own target selection, qualified navigation/preparation and
the safe return; this component owns battle availability and, later, active
battle execution. M0 implements no battle policy: every valid context/mode
pair reports ``not_implemented`` and execution returns a typed unavailable
result without accessing the borrowed session or sending input.
"""

from __future__ import annotations

from typing import Any, Protocol

from pnc_automation.app.pnc.domain.match3 import (
    Match3Availability,
    Match3AvailabilityStatus,
    Match3Context,
    Match3Mode,
    Match3Request,
    Match3Result,
)
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import TaskVerificationError


class Match3Session(Protocol):
    """The borrowed constrained session supplied by a feature caller.

    The component borrows the caller's runtime and lease; it never opens a
    runner, connection or reservation of its own.
    """

    def observe(self, label: str, request: ObservationRequest | None = None) -> Observation:
        """Returns one fresh observation through the caller's connected services."""


class Match3Component(Protocol):
    """The shared match-3 API consumed by feature callers."""

    def availability(self, context: Match3Context, mode: Match3Mode) -> Match3Availability:
        """Reports whether one context/mode pair can execute in this build."""

    def execute(self, *, request: Match3Request, session: Match3Session) -> Match3Result:
        """Runs one requested battle through the caller's borrowed session."""


class Match3UnavailableError(TaskVerificationError):
    """Raised when a valid match-3 battle request selects an unavailable pair."""

    availability: Match3Availability

    def __init__(self, availability: Match3Availability, **details: Any) -> None:
        """Carries the component's typed availability answer into the failure."""

        self.availability = availability
        super().__init__(
            message=(
                f"Match-3 mode '{availability.mode.value}' is {availability.status.value}"
                f" for context '{availability.context.value}': {availability.reason}"
            ),
            context=availability.context.value,
            mode=availability.mode.value,
            availability_status=availability.status.value,
            **details,
        )


class UnavailableMatch3Component:
    """The default M0 component: every valid context/mode pair is not implemented."""

    def availability(self, context: Match3Context, mode: Match3Mode) -> Match3Availability:
        """Reports the requested pair honestly as not implemented."""

        return Match3Availability(
            context=context,
            mode=mode,
            status=Match3AvailabilityStatus.NOT_IMPLEMENTED,
            reason="No match-3 battle policy is implemented for this context/mode pair in this build.",
        )

    def execute(self, *, request: Match3Request, session: Match3Session) -> Match3Result:
        """Revalidates availability and returns the typed unavailable result.

        The borrowed session is never accessed: an unavailable request must not
        observe, navigate, dispatch input or spend resources.
        """

        del session
        return Match3Result(
            request=request,
            availability=self.availability(request.context, request.mode),
        )


def require_match3_available(
    component: Match3Component,
    request: Match3Request,
    **details: Any,
) -> Match3Availability:
    """Fails closed when the requested context/mode pair cannot execute."""

    availability = component.availability(request.context, request.mode)
    if not availability.available:
        raise Match3UnavailableError(availability, **details)
    return availability
