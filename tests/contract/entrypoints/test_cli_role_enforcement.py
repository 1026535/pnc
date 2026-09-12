"""Offline CLI workflow-role enforcement tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.entrypoints.cli import main
from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus


class _RoleAccount:
    """Records the role required by one CLI invocation."""

    def __init__(self, roles: frozenset[LiveAutomationRole]) -> None:
        self.roles = roles
        self.required: list[LiveAutomationRole] = []

    def require_live_role(self, role: LiveAutomationRole) -> None:
        """Accepts or rejects the requested workflow role from configured state."""

        self.required.append(role)
        if role not in self.roles:
            raise PermissionError(f"missing role: {role.value}")


class CliRoleEnforcementTests(unittest.TestCase):
    """Ensures generic CLI entry paths use configured workflow roles without account predicates."""

    def test_generic_login_requires_live_testing(self) -> None:
        """Routes a generic live CLI command through the configured LIVE_TESTING role."""

        account = _RoleAccount(frozenset({LiveAutomationRole.LIVE_TESTING}))
        application = _fake_application(account)
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=application), patch(
            "builtins.print"
        ):
            self.assertEqual(
                main(["login", "--account", "account_a", "--config", "config/accounts.yaml"]),
                0,
            )
        self.assertEqual(account.required, [LiveAutomationRole.LIVE_TESTING])
        application.prepare_account_session.assert_called_once_with(
            account_id="account_a",
            castle=None,
            required_role=LiveAutomationRole.LIVE_TESTING,
        )

    def test_generic_login_is_rejected_for_read_only_account(self) -> None:
        """Stops before runtime construction when the current YAML assigns READ_ONLY."""

        account = _RoleAccount(frozenset({LiveAutomationRole.READ_ONLY}))
        application = _fake_application(account)
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=application):
            with self.assertRaisesRegex(PermissionError, "missing role"):
                main(["login", "--account", "account_a", "--config", "config/accounts.yaml"])
        application.prepare_account_session.assert_not_called()


def _fake_application(account: _RoleAccount) -> SimpleNamespace:
    """Builds a small application-shaped object without constructing ADB or OCR services."""

    result = RunResult(
        account_id="account_a",
        script_name="prepare_account_session",
        steps=(
            StepRunResult(
                task_id=TaskId.LOGIN,
                status=TaskStatus.SUCCESS,
                attempts=1,
                message="ok",
            ),
        ),
        started_at=datetime.now(tz=UTC),
        finished_at=datetime.now(tz=UTC),
    )
    return SimpleNamespace(
        script_runner=SimpleNamespace(config=SimpleNamespace(require_account=lambda _account_id: account)),
        prepare_account_session=Mock(return_value=result),
    )


if __name__ == "__main__":
    unittest.main()
