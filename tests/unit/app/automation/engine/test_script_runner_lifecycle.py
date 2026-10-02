"""Deterministic connected-runtime lifecycle and outcome contracts."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from pnc_automation.app.automation.engine.script_runner import (
    ConnectedAccountRuntime,
    ConnectedAutomationRuntime,
    ScriptRunner,
)


@dataclass
class _FakeSession:
    """Records one connected-session cleanup and can reproduce its failure."""

    close_error: BaseException | None = None
    close_calls: int = 0
    instance: object = field(default_factory=object)

    def close(self) -> None:
        """Close the fake session once, optionally raising its configured error."""

        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


@dataclass
class _FakePerformanceRun:
    """Retains lifecycle outcomes without writing a report."""

    outcomes: list[str] = field(default_factory=list)

    def finish(self, outcome: str) -> None:
        """Record the finalized runtime outcome."""

        self.outcomes.append(outcome)


@dataclass
class _FakePerformanceActivation:
    """Records the activation context exit passed the active exception details."""

    exits: list[tuple[object, object, object]] = field(default_factory=list)

    def __exit__(self, exception_type: object, exception: object, traceback: object) -> None:
        """Record the context exit tuple."""

        self.exits.append((exception_type, exception, traceback))


class ConnectedRuntimeLifecycleTests(unittest.TestCase):
    """Covers success/error outcomes and single-owner cleanup."""

    def test_bundle_success_records_success_and_closes_once(self) -> None:
        """Normal bundle completion preserves the success outcome for existing callers."""

        session = _FakeSession()
        performance = _FakePerformanceRun()
        activation = _FakePerformanceActivation()
        runtime = _runtime(session=session, performance=performance, activation=activation)

        with ConnectedAutomationRuntime(runtime=runtime, runner=object()):
            pass

        self.assertEqual(1, session.close_calls)
        self.assertEqual(["success"], performance.outcomes)
        self.assertEqual([(None, None, None)], activation.exits)

    def test_bundle_body_failure_records_error_and_closes_once(self) -> None:
        """A failing bundle body reaches the inner runtime lifecycle with an error outcome."""

        session = _FakeSession()
        performance = _FakePerformanceRun()
        activation = _FakePerformanceActivation()
        runtime = _runtime(session=session, performance=performance, activation=activation)
        bundle = ConnectedAutomationRuntime(runtime=runtime, runner=object())

        with self.assertRaisesRegex(RuntimeError, "body failed"):
            with bundle:
                raise RuntimeError("body failed")

        self.assertEqual(1, session.close_calls)
        self.assertEqual(["error"], performance.outcomes)
        self.assertEqual(1, len(activation.exits))

    def test_bundle_cleanup_failure_preserves_active_body_error(self) -> None:
        """A session cleanup error remains grouped with the active operation failure."""

        session = _FakeSession(close_error=RuntimeError("cleanup failed"))
        performance = _FakePerformanceRun()
        runtime = _runtime(session=session, performance=performance, activation=_FakePerformanceActivation())

        with self.assertRaises(BaseExceptionGroup) as raised:
            with ConnectedAutomationRuntime(runtime=runtime, runner=object()):
                raise RuntimeError("body failed")

        self.assertEqual({str(error) for error in raised.exception.exceptions}, {"body failed", "cleanup failed"})
        self.assertEqual(1, session.close_calls)
        self.assertEqual(["error"], performance.outcomes)

    def test_runner_construction_failure_records_error_and_closes_once(self) -> None:
        """A failure after service acquisition uses the error cleanup outcome."""

        session = _FakeSession()
        performance = _FakePerformanceRun()
        runtime = _runtime(session=session, performance=performance, activation=_FakePerformanceActivation())
        script_runner = object.__new__(ScriptRunner)
        construction_error = RuntimeError("runner construction failed")

        with (
            patch.object(ScriptRunner, "_build_shared_extra", return_value={}),
            patch.object(ScriptRunner, "_build_core_step_executor", side_effect=construction_error),
        ):
            with self.assertRaisesRegex(RuntimeError, "runner construction failed"):
                script_runner._build_automation_runner_from_services(
                    account=object(),
                    connected_runtime=runtime,
                )

        self.assertEqual(1, session.close_calls)
        self.assertEqual(["error"], performance.outcomes)

    def test_runner_construction_and_cleanup_failures_remain_grouped(self) -> None:
        """Construction and cleanup failures are both retained by the factory boundary."""

        session = _FakeSession(close_error=RuntimeError("cleanup failed"))
        performance = _FakePerformanceRun()
        runtime = _runtime(session=session, performance=performance, activation=_FakePerformanceActivation())
        script_runner = object.__new__(ScriptRunner)

        with (
            patch.object(ScriptRunner, "_build_shared_extra", return_value={}),
            patch.object(ScriptRunner, "_build_core_step_executor", side_effect=RuntimeError("construction failed")),
        ):
            with self.assertRaises(BaseExceptionGroup) as raised:
                script_runner._build_automation_runner_from_services(
                    account=object(),
                    connected_runtime=runtime,
                )

        self.assertEqual(
            {str(error) for error in raised.exception.exceptions},
            {"construction failed", "cleanup failed"},
        )
        self.assertEqual(1, session.close_calls)
        self.assertEqual(["error"], performance.outcomes)


def _runtime(
    *,
    session: _FakeSession,
    performance: _FakePerformanceRun,
    activation: _FakePerformanceActivation,
) -> ConnectedAccountRuntime:
    """Build a real runtime owner around deterministic service placeholders."""

    return ConnectedAccountRuntime(
        session=session,  # type: ignore[arg-type]
        observation_service=object(),  # type: ignore[arg-type]
        flow_planner=object(),  # type: ignore[arg-type]
        world_map_survey_recorder=object(),  # type: ignore[arg-type]
        world_map_search_service=object(),  # type: ignore[arg-type]
        world_map_movement_calibration_service=object(),  # type: ignore[arg-type]
        world_map_movement_calibration_store=object(),  # type: ignore[arg-type]
        observed_action_executor=object(),  # type: ignore[arg-type]
        _performance_run=performance,  # type: ignore[arg-type]
        _performance_activation=activation,  # type: ignore[arg-type]
    )


if __name__ == "__main__":
    unittest.main()
