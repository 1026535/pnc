"""Synthetic make_run_result fixture."""

from __future__ import annotations

from datetime import UTC, datetime

from pnc_automation.app.automation.engine.runner import RunResult



def _make_run_result(*, script_name: str) -> RunResult:
    """Builds one minimal successful run result for scheduled-mail API and CLI tests."""

    now = datetime.now(tz=UTC)
    return RunResult(
        account_id="account_a",
        script_name=script_name,
        steps=(),
        started_at=now,
        finished_at=now,
    )
