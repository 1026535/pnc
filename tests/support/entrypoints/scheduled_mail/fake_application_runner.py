"""Synthetic FakeApplicationRunner fixture."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.task import TaskId, TaskResult
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.authoring.config.models import LiveAutomationRole

from tests.support.entrypoints.scheduled_mail.fake_reservation import _FakeReservation
from tests.support.entrypoints.scheduled_mail.fake_script_runner import _FakeScriptRunner
from tests.support.entrypoints.scheduled_mail.make_preparation_result import (
    _make_preparation_result,
)
from tests.support.entrypoints.scheduled_mail.make_run_result import _make_run_result


@dataclass(slots=True)
class _FakeApplicationRunner:
    """Records API and CLI scheduled-mail calls without constructing the full runtime."""

    prepare_calls: list[tuple[str, CastleIdentity | None]] = field(default_factory=list)
    task_calls: list[tuple[TaskId, str, dict[str, object] | None]] = field(default_factory=list)
    mail_schedule_calls: list[tuple[str, list[str] | None, datetime | None]] = field(default_factory=list)
    script_runner: object = field(init=False)

    def __post_init__(self) -> None:
        """Provides the canonical CLI role-check surface."""

        self.script_runner = _FakeScriptRunner()

    def reserve_accounts(self, account_ids: tuple[str, ...]) -> "_FakeReservation":
        """Provides the canonical scoped reservation surface without live state."""

        del account_ids
        return _FakeReservation()

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
        required_role: LiveAutomationRole | None = None,
    ) -> RunResult:
        """Records one session-preparation request and returns a synthetic success result."""

        self.prepare_calls.append((account_id, castle))
        return _make_preparation_result()

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, object] | None = None,
        required_role: LiveAutomationRole | None = None,
    ) -> StepRunResult:
        """Records one direct task call and returns a synthetic success result."""

        self.task_calls.append((task_id, account_id, params))
        return StepRunResult(
            task_id=task_id,
            status=TaskResult.success("ok").status,
            attempts=1,
            message="ok",
        )

    def run_mail_schedules(
        self,
        *,
        account_id: str,
        schedule_ids: list[str] | None = None,
        scheduled_for_utc: datetime | None = None,
        required_role: LiveAutomationRole | None = None,
    ) -> RunResult:
        """Records one scheduled-mail run request and returns a synthetic success result."""

        self.mail_schedule_calls.append((account_id, schedule_ids, scheduled_for_utc))
        return _make_run_result(script_name="generated_mail_schedule_20260331T050000Z")
