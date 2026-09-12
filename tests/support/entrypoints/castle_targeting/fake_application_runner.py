"""Synthetic FakeApplicationRunner fixture."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.task import TaskId, TaskResult
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.core.infra.emulator.session import BlueStacksSessionCleanupPolicy

from tests.support.entrypoints.castle_targeting.fake_reservation import _FakeReservation
from tests.support.entrypoints.castle_targeting.fake_script_runner import _FakeScriptRunner
from tests.support.entrypoints.castle_targeting.make_run_result import _make_run_result


@dataclass(slots=True)
class _FakeApplicationRunner:
    """Records Python API and CLI calls without constructing the full runtime."""

    run_calls: list[tuple[str, str, list[str] | None]] = field(default_factory=list)
    prepare_calls: list[tuple[str, CastleIdentity | None]] = field(default_factory=list)
    prepare_cleanup_policies: list[BlueStacksSessionCleanupPolicy | None] = field(
        default_factory=list,
    )
    task_calls: list[tuple[TaskId, str, dict[str, object] | None]] = field(default_factory=list)
    task_cleanup_policies: list[BlueStacksSessionCleanupPolicy | None] = field(
        default_factory=list,
    )
    preparation_result: RunResult | None = None
    reservations: list["_FakeReservation"] = field(default_factory=list)
    script_runner: object = field(init=False)

    def __post_init__(self) -> None:
        """Provides the canonical role-check surface expected by the CLI."""

        self.script_runner = _FakeScriptRunner()

    def reserve_accounts(self, account_ids: tuple[str, ...]):
        """Provides the application reservation boundary without live instance state."""

        del account_ids
        reservation = _FakeReservation()
        self.reservations.append(reservation)
        return reservation

    def run(
        self,
        *,
        account_id: str,
        script_path: str,
        castle_refs: list[str] | None = None,
        required_role: LiveAutomationRole | None = None,
    ) -> RunResult:
        """Records one CLI/script run request and returns a synthetic success result."""

        self.run_calls.append((account_id, script_path, castle_refs))
        return _make_run_result(script_name=script_path)

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> RunResult:
        """Records one session-preparation request and returns a synthetic success result."""

        self.prepare_calls.append((account_id, castle))
        self.prepare_cleanup_policies.append(session_cleanup_policy)
        return self.preparation_result or _make_run_result(script_name="prepare_account_session")

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, object] | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> StepRunResult:
        """Records one direct task call and returns a synthetic success result."""

        self.task_calls.append((task_id, account_id, params))
        self.task_cleanup_policies.append(session_cleanup_policy)
        return StepRunResult(
            task_id=task_id,
            status=TaskResult.success("ok").status,
            attempts=1,
            message="ok",
        )
