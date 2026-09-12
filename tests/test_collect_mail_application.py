"""Deterministic application and Python API migration tests for collect-mail."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.authoring.config.models import CastleIdentity, LiveAutomationRole
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.entrypoints import api as api_module
from pnc_automation.app.entrypoints.api import AutomationApi, AutomationSession
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.errors import ScriptValidationError


class CollectMailApplicationTests(unittest.TestCase):
    """Covers validation, preflight ordering, role forwarding, closure, and API routing."""

    def test_application_validates_before_building_connected_runtime(self) -> None:
        """Malformed collect-mail parameters fail before any runtime factory or preflight call."""

        script_runner = Mock()
        script_runner.config.require_account.return_value = _account()
        with patch("pnc_automation.app.entrypoints.app.build_core_runtime") as factory:
            with self.assertRaises(ScriptValidationError):
                ApplicationRunner(script_runner).run_collect_mail(
                    account_id="account",
                    params={"mailboxes": []},
                )
        factory.assert_not_called()

    def test_application_requires_archive_store_before_connecting(self) -> None:
        """A missing canonical archive store fails before the connected-core factory."""

        script_runner = Mock()
        script_runner.config.require_account.return_value = _account()
        script_runner.mail_archive_store = None
        with patch("pnc_automation.app.entrypoints.app.build_core_runtime") as factory:
            with self.assertRaisesRegex(RuntimeError, "MailArchiveStore"):
                ApplicationRunner(script_runner).run_collect_mail(
                    account_id="account",
                    params={"mailboxes": ["player"]},
                )
        factory.assert_not_called()

    def test_application_preflights_exact_castle_before_workflow_and_closes(self) -> None:
        """Forwards the live-testing role, passes the exact castle name, and closes on success."""

        account = _account()
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        with tempfile.TemporaryDirectory() as temporary_directory:
            script_runner.mail_archive_store = MailArchiveStore(root=Path(temporary_directory) / "mail")
            runtime = Mock()
            events: list[object] = []
            def _preflight() -> CastleIdentity:
                events.append("preflight")
                return CastleIdentity("K1", "Exact Active Castle", 22)

            runtime.preflight_active_castle_identity.side_effect = _preflight

            class _Runner:
                @classmethod
                def __class_getitem__(cls, _item):
                    return cls

                def __init__(self, passed_runtime) -> None:
                    events.append(("runner", passed_runtime))

                def run(self, workflow):
                    events.append(("workflow", workflow.active_castle))
                    return "result"

            with (
                patch(
                    "pnc_automation.app.entrypoints.app.build_core_runtime",
                    return_value=runtime,
                ) as factory,
                patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
            ):
                result = ApplicationRunner(script_runner).run_collect_mail(
                    account_id="account",
                    params={"mailboxes": ["player"]},
                )

        self.assertEqual("result", result)
        self.assertEqual(["preflight", ("runner", runtime), ("workflow", "Exact Active Castle")], events)
        factory.assert_called_once_with(
            script_runner,
            account,
            account.artifact_directory_name,
            required_role=LiveAutomationRole.LIVE_TESTING,
        )
        runtime.close.assert_called_once_with()

    def test_application_closes_runtime_when_workflow_fails(self) -> None:
        """Runtime cleanup is unconditional after preflight and workflow execution starts."""

        script_runner = Mock()
        script_runner.config.require_account.return_value = _account()
        with tempfile.TemporaryDirectory() as temporary_directory:
            script_runner.mail_archive_store = MailArchiveStore(root=Path(temporary_directory) / "mail")
            runtime = Mock()
            runtime.preflight_active_castle_identity.return_value = CastleIdentity("K1", "Castle", 22)

            class _Runner:
                @classmethod
                def __class_getitem__(cls, _item):
                    return cls

                def __init__(self, _runtime) -> None:
                    pass

                def run(self, _workflow):
                    raise RuntimeError("workflow failed")

            with (
                patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime),
                patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
            ):
                with self.assertRaisesRegex(RuntimeError, "workflow failed"):
                    ApplicationRunner(script_runner).run_collect_mail(
                        account_id="account",
                        params={"mailboxes": ["player"]},
                    )
        runtime.close.assert_called_once_with()

    def test_application_closes_runtime_when_preflight_fails(self) -> None:
        """Runtime cleanup also covers an active-castle preflight failure."""

        script_runner = Mock()
        script_runner.config.require_account.return_value = _account()
        with tempfile.TemporaryDirectory() as temporary_directory:
            script_runner.mail_archive_store = MailArchiveStore(root=Path(temporary_directory) / "mail")
            runtime = Mock()
            runtime.preflight_active_castle_identity.side_effect = RuntimeError("identity absent")
            with patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime):
                with self.assertRaisesRegex(RuntimeError, "identity absent"):
                    ApplicationRunner(script_runner).run_collect_mail(
                        account_id="account",
                        params={"mailboxes": ["player"]},
                    )
        runtime.close.assert_called_once_with()

    def test_python_api_and_bound_session_route_to_dedicated_application_method(self) -> None:
        """Direct Python surfaces return the typed core result and do not dispatch a legacy task."""

        application = Mock()
        typed_result = Mock(spec=CoreWorkflowResult)
        application.run_collect_mail.return_value = typed_result
        api = AutomationApi(application=application)

        self.assertIs(
            typed_result,
            api.collect_mail(account_id="account", mailboxes=["player"]),
        )
        application.run_collect_mail.assert_called_once_with(
            account_id="account",
            params={
                "mailboxes": ["player"],
                "archive_mode": "both",
                "limit_per_mailbox": 25,
                "only_new": True,
            },
        )

        application.reset_mock()
        session = AutomationSession(api=api, account_id="account")
        session.collect_mail(mailboxes=["alliance"], limit_per_mailbox=2)
        application.run_collect_mail.assert_called_once_with(
            account_id="account",
            params={
                "mailboxes": ["alliance"],
                "archive_mode": "both",
                "limit_per_mailbox": 2,
                "only_new": True,
            },
        )

    def test_legacy_task_id_dispatch_remains_available(self) -> None:
        """Authored TaskId callers retain the legacy ScriptRunner dispatch boundary."""

        application = Mock()
        api = AutomationApi(application=application)
        api.run_task(account_id="account", task_id=TaskId.COLLECT_MAIL, params={"mailboxes": ["player"]})
        application.run_task.assert_called_once_with(
            account_id="account",
            task_id=TaskId.COLLECT_MAIL,
            params={"mailboxes": ["player"]},
        )

    def test_module_collect_mail_helper_uses_typed_application_path(self) -> None:
        """The module-level convenience helper remains a thin typed API wrapper."""

        api = Mock()
        typed_result = Mock(spec=CoreWorkflowResult)
        api.collect_mail.return_value = typed_result
        with patch.object(api_module, "_default_api", return_value=api):
            result = api_module.collect_mail(account_id="account", mailboxes=["player"])

        self.assertIs(typed_result, result)
        api.collect_mail.assert_called_once_with(
            account_id="account",
            mailboxes=["player"],
            archive_mode="both",
            limit_per_mailbox=25,
            only_new=True,
        )


def _account() -> SimpleNamespace:
    """Builds the minimal account shape needed before connected runtime construction."""

    return SimpleNamespace(
        id="account",
        pnc_account_id="pnc-account",
        artifact_directory_name="account",
    )


if __name__ == "__main__":
    unittest.main()
