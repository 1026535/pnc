"""Synthetic make_preparation_result fixture."""

from __future__ import annotations

from datetime import UTC, datetime

from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.task import TaskId, TaskResult



def _make_preparation_result() -> RunResult:
    """Builds a preparation result with an explicit successful step."""

    now = datetime.now(tz=UTC)
    return RunResult(
        account_id="account_a",
        script_name="prepare_account_session",
        steps=(
            StepRunResult(
                task_id=TaskId.LOGIN,
                status=TaskResult.success("ok").status,
                attempts=1,
                message="ok",
            ),
        ),
        started_at=now,
        finished_at=now,
    )
