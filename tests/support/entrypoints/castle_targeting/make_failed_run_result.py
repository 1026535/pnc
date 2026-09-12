"""Synthetic make_failed_run_result fixture."""

from __future__ import annotations

from datetime import UTC, datetime

from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus



def _make_failed_run_result() -> RunResult:
    """Builds one failed preparation result for scoped-entrypoint tests."""

    now = datetime.now(tz=UTC)
    return RunResult(
        account_id="account_a",
        script_name="prepare_account_session",
        steps=(
            StepRunResult(
                task_id=TaskId.LOGIN,
                status=TaskStatus.FAILED,
                attempts=1,
                message="failed",
            ),
        ),
        started_at=now,
        finished_at=now,
    )
