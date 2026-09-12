"""Synthetic RealLeaseApplicationRunner fixture."""

from __future__ import annotations

from pathlib import Path

from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.core.errors import InstanceBusyError
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry

from tests.support.entrypoints.castle_targeting.make_failed_run_result import (
    _make_failed_run_result,
)
from tests.support.entrypoints.castle_targeting.make_run_result import _make_run_result


class _RealLeaseApplicationRunner:
    """Exercises public API reservation calls with a real temp-root registry."""

    def __init__(self, root: Path, *, preparation_failed: bool = False) -> None:
        """Initializes one account-to-display binding and a competing registry probe."""

        self.registry = InstanceLeaseRegistry(root=root / "leases")
        self.preparation_failed = preparation_failed
        self.competitor_acquired_after_scope = False

    def reserve_accounts(self, account_ids: tuple[str, ...]):
        """Returns the real scoped bundle used by the public API entrypoint."""

        self.assertEqual_account_ids(account_ids)
        bundle = self.registry.acquire_bundle(("serious_stuff",))
        self.assert_competitor_blocked()
        return bundle

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
        required_role: LiveAutomationRole | None = None,
    ) -> RunResult:
        """Probes lease ownership during preparation and returns the configured result."""

        del castle, required_role
        self.assertEqual_account_ids((account_id,))
        self.assert_competitor_blocked()
        return _make_failed_run_result() if self.preparation_failed else _make_run_result(
            script_name="prepare_account_session"
        )

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, object] | None = None,
        required_role: LiveAutomationRole | None = None,
    ) -> StepRunResult:
        """Probes lease ownership while the dependent API action is running."""

        del params, required_role
        self.assertEqual_account_ids((account_id,))
        self.assert_competitor_blocked()
        return StepRunResult(task_id=task_id, status=TaskStatus.SUCCESS, attempts=1, message="ok")

    def assert_competitor_blocked(self) -> None:
        """Requires a separate registry to remain excluded during the public API scope."""

        competitor = InstanceLeaseRegistry(root=self.registry.root, wait_timeout_seconds=0)
        try:
            competitor.acquire(display_name="serious_stuff")
        except InstanceBusyError:
            return
        finally:
            competitor.release_all()
        raise AssertionError("The public API did not hold the account lease during dependent work.")

    def assertEqual_account_ids(self, account_ids: tuple[str, ...]) -> None:
        """Keeps the fake binding explicit instead of silently accepting another account."""

        if account_ids != ("account_a",):
            raise AssertionError(f"unexpected account ids: {account_ids}")

    def probe_after_scope(self) -> None:
        """Confirms the competitor can enter once the public API scope exits."""

        competitor = InstanceLeaseRegistry(root=self.registry.root, wait_timeout_seconds=0)
        try:
            competitor.acquire(display_name="serious_stuff")
            self.competitor_acquired_after_scope = True
        finally:
            competitor.release_all()
