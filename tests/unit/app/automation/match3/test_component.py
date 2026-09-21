"""Shared match-3 component contract tests."""

from __future__ import annotations

import unittest
from typing import Any

from pnc_automation.app.automation.match3 import (
    Match3Component,
    Match3UnavailableError,
    UnavailableMatch3Component,
    require_match3_available,
)
from pnc_automation.app.pnc.domain.match3 import (
    Match3Availability,
    Match3AvailabilityStatus,
    Match3Context,
    Match3Mode,
    Match3Request,
    Match3Result,
)
from pnc_automation.core.errors import AutomationError, AutomationErrorKind, TaskVerificationError


class _ExplodingSession:
    """A borrowed session that fails the test on any access."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"The unavailable component must not access session.{name}.")


class _RecordingComponent:
    """A test implementation of the shared API that records its calls."""

    def __init__(self, availability_status: Match3AvailabilityStatus) -> None:
        self.availability_status = availability_status
        self.availability_calls: list[tuple[Match3Context, Match3Mode]] = []
        self.execute_calls: list[Match3Request] = []

    def availability(self, context: Match3Context, mode: Match3Mode) -> Match3Availability:
        """Records the query and returns the configured availability answer."""

        self.availability_calls.append((context, mode))
        return Match3Availability(
            context=context,
            mode=mode,
            status=self.availability_status,
            reason="configured by test" if self.availability_status is not Match3AvailabilityStatus.AVAILABLE else "",
        )

    def execute(self, *, request: Match3Request, session: object) -> Match3Result:
        """Records the execution call and returns a typed result."""

        self.execute_calls.append(request)
        return Match3Result(
            request=request,
            availability=self.availability(request.context, request.mode),
        )


class UnavailableMatch3ComponentTests(unittest.TestCase):
    """Proves the M0 unavailable implementation's honest contract."""

    def test_every_context_mode_pair_reports_not_implemented(self) -> None:
        """All nine valid combinations are typed and honestly unavailable."""

        component = UnavailableMatch3Component()

        for context in Match3Context:
            for mode in Match3Mode:
                with self.subTest(context=context, mode=mode):
                    availability = component.availability(context, mode)
                    self.assertIs(availability.context, context)
                    self.assertIs(availability.mode, mode)
                    self.assertEqual(availability.status, Match3AvailabilityStatus.NOT_IMPLEMENTED)
                    self.assertFalse(availability.available)
                    self.assertTrue(availability.reason.strip())

    def test_execute_returns_unavailable_without_touching_the_session(self) -> None:
        """An unavailable request returns a typed result without any runtime access."""

        component = UnavailableMatch3Component()
        request = Match3Request(context=Match3Context.CAMPAIGN, mode=Match3Mode.SOLVER)

        result = component.execute(request=request, session=_ExplodingSession())

        self.assertIs(result.request, request)
        self.assertEqual(result.availability.status, Match3AvailabilityStatus.NOT_IMPLEMENTED)
        self.assertFalse(result.availability.available)

    def test_recording_implementation_satisfies_the_shared_api(self) -> None:
        """Test substitutions implement the real interface with real request/result types."""

        component: Match3Component = _RecordingComponent(Match3AvailabilityStatus.AVAILABLE)
        request = Match3Request(context=Match3Context.ARENA, mode=Match3Mode.GAME_AUTO)

        result = component.execute(request=request, session=_ExplodingSession())

        self.assertEqual(component.execute_calls, [request])
        self.assertTrue(result.availability.available)


class RequireMatch3AvailableTests(unittest.TestCase):
    """Proves the shared availability guard fails closed."""

    def test_unavailable_pair_raises_typed_error_carrying_availability(self) -> None:
        """The refusal is a typed AutomationError with the typed availability attached."""

        request = Match3Request(context=Match3Context.CAMPAIGN, mode=Match3Mode.DAILY_EXIT)

        with self.assertRaises(Match3UnavailableError) as raised:
            require_match3_available(UnavailableMatch3Component(), request, task="campaign")

        error = raised.exception
        self.assertIsInstance(error, TaskVerificationError)
        self.assertIsInstance(error, AutomationError)
        self.assertEqual(error.kind, AutomationErrorKind.TASK_VERIFICATION)
        self.assertEqual(error.availability.status, Match3AvailabilityStatus.NOT_IMPLEMENTED)
        self.assertEqual(error.details["context"], "campaign")
        self.assertEqual(error.details["mode"], "daily_exit")
        self.assertEqual(error.details["task"], "campaign")
        self.assertIn("daily_exit", error.message)

    def test_available_pair_returns_the_availability_answer(self) -> None:
        """A component reporting available lets the request through unchanged."""

        component = _RecordingComponent(Match3AvailabilityStatus.AVAILABLE)
        request = Match3Request(context=Match3Context.LOST_LAND, mode=Match3Mode.SOLVER)

        availability = require_match3_available(component, request)

        self.assertTrue(availability.available)
        self.assertEqual(component.availability_calls, [(Match3Context.LOST_LAND, Match3Mode.SOLVER)])


if __name__ == "__main__":
    unittest.main()
