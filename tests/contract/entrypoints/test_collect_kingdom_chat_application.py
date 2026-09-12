"""Deterministic application and Python API migration tests for Kingdom Chat."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.entrypoints import api as api_module
from pnc_automation.app.entrypoints.api import AutomationApi, AutomationSession
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore


class CollectKingdomChatApplicationTests(unittest.TestCase):
    """Covers typed application lifecycle, direct API routing, and lease boundaries."""

    def test_application_preflights_before_workflow_and_forwards_role(self) -> None:
        """Uses the exact active castle and requested live role before running the workflow."""

        account = _account()
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        events: list[object] = []
        active_castle = CastleIdentity("K1", "Exact Active Castle", 22)

        def _preflight() -> CastleIdentity:
            events.append("preflight")
            return active_castle

        runtime.preflight_active_castle_identity.side_effect = _preflight
        typed_result = Mock(spec=CoreWorkflowResult)

        class _Runner:
            @classmethod
            def __class_getitem__(cls, _item):
                return cls

            def __init__(self, passed_runtime) -> None:
                events.append(("runner", passed_runtime))

            def run(self, workflow):
                events.append(("workflow", workflow.account_id, workflow.active_castle, workflow.archive_store))
                return typed_result

        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_store = ChatArchiveStore(Path(temporary_directory) / "chat")
            script_runner.chat_archive_store = archive_store
            with (
                patch(
                    "pnc_automation.app.entrypoints.app.build_core_runtime",
                    return_value=runtime,
                ) as factory,
                patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
            ):
                result = ApplicationRunner(script_runner).run_collect_kingdom_chat(
                    account_id="account",
                    required_role=LiveAutomationRole.READ_ONLY,
                )

        self.assertIs(typed_result, result)
        self.assertEqual(
            [
                "preflight",
                ("runner", runtime),
                ("workflow", "account", active_castle, archive_store),
            ],
            events,
        )
        factory.assert_called_once_with(
            script_runner,
            account,
            account.artifact_directory_name,
            required_role=LiveAutomationRole.READ_ONLY,
        )
        runtime.close.assert_called_once_with()

    def test_application_closes_runtime_when_preflight_fails(self) -> None:
        """Closes a connected core when active-castle preflight rejects the run."""

        script_runner = Mock()
        script_runner.config.require_account.return_value = _account()
        script_runner.chat_archive_store = object()
        runtime = Mock()
        runtime.preflight_active_castle_identity.side_effect = RuntimeError("identity absent")

        with (
            patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime),
            patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner") as runner_factory,
        ):
            with self.assertRaisesRegex(RuntimeError, "identity absent"):
                ApplicationRunner(script_runner).run_collect_kingdom_chat(account_id="account")

        runner_factory.assert_not_called()
        runtime.close.assert_called_once_with()

    def test_application_closes_runtime_when_workflow_fails(self) -> None:
        """Closes a connected core when typed workflow execution fails."""

        script_runner = Mock()
        script_runner.config.require_account.return_value = _account()
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

        with tempfile.TemporaryDirectory() as temporary_directory:
            script_runner.chat_archive_store = ChatArchiveStore(Path(temporary_directory) / "chat")
            with (
                patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime),
                patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
            ):
                with self.assertRaisesRegex(RuntimeError, "workflow failed"):
                    ApplicationRunner(script_runner).run_collect_kingdom_chat(account_id="account")

        runtime.close.assert_called_once_with()

    def test_application_requires_archive_store_before_connecting(self) -> None:
        """Rejects a missing canonical archive store before building a connected runtime."""

        script_runner = Mock()
        script_runner.config.require_account.return_value = _account()
        script_runner.chat_archive_store = None

        with patch("pnc_automation.app.entrypoints.app.build_core_runtime") as factory:
            with self.assertRaisesRegex(RuntimeError, "ChatArchiveStore"):
                ApplicationRunner(script_runner).run_collect_kingdom_chat(account_id="account")

        factory.assert_not_called()

    def test_direct_api_and_bound_session_return_typed_result_without_legacy_dispatch(self) -> None:
        """Routes direct and bound Chat calls to the typed application method."""

        application = Mock()
        typed_result = Mock(spec=CoreWorkflowResult)
        application.run_collect_kingdom_chat.return_value = typed_result
        api = AutomationApi(application=application)

        self.assertIs(typed_result, api.collect_kingdom_chat(account_id="account"))
        application.run_collect_kingdom_chat.assert_called_once_with(account_id="account")
        application.run_task.assert_not_called()
        application.reserve_accounts.assert_called_once_with(("account",))
        application.reserve_accounts.return_value.close.assert_called_once_with()

        application.reset_mock()
        application.run_collect_kingdom_chat.return_value = typed_result
        session = AutomationSession(api=api, account_id="account")

        self.assertIs(typed_result, session.collect_kingdom_chat())
        application.run_collect_kingdom_chat.assert_called_once_with(account_id="account")
        application.run_task.assert_not_called()
        application.reserve_accounts.assert_called_once_with(("account",))
        application.reserve_accounts.return_value.close.assert_called_once_with()

    def test_module_helper_returns_typed_result(self) -> None:
        """Keeps the module-level Chat helper as a thin typed API wrapper."""

        api = Mock()
        typed_result = Mock(spec=CoreWorkflowResult)
        api.collect_kingdom_chat.return_value = typed_result

        with patch.object(api_module, "_default_api", return_value=api):
            result = api_module.collect_kingdom_chat(account_id="account")

        self.assertIs(typed_result, result)
        api.collect_kingdom_chat.assert_called_once_with(account_id="account")

    def test_explicit_legacy_task_dispatch_remains_available(self) -> None:
        """Leaves authored TaskId dispatch explicit while direct Chat calls stay typed."""

        application = Mock()
        api = AutomationApi(application=application)

        api.run_task(account_id="account", task_id=TaskId.COLLECT_KINGDOM_CHAT)

        application.run_task.assert_called_once_with(
            account_id="account",
            task_id=TaskId.COLLECT_KINGDOM_CHAT,
            params=None,
        )
        application.run_collect_kingdom_chat.assert_not_called()

    def test_direct_api_releases_temporary_reservation_on_failure(self) -> None:
        """Closes a temporary direct-call lease even when the typed application call fails."""

        application = Mock()
        application.run_collect_kingdom_chat.side_effect = RuntimeError("failed")
        api = AutomationApi(application=application)

        with self.assertRaisesRegex(RuntimeError, "failed"):
            api.collect_kingdom_chat(account_id="account")

        application.reserve_accounts.assert_called_once_with(("account",))
        application.reserve_accounts.return_value.close.assert_called_once_with()

    def test_direct_api_reuses_active_reservation_and_rejects_wrong_account(self) -> None:
        """Reuses a caller-owned lease and rejects calls outside its declared account bundle."""

        application = Mock()
        typed_result = Mock(spec=CoreWorkflowResult)
        application.run_collect_kingdom_chat.return_value = typed_result
        api = AutomationApi(application=application)

        with api.reserve_accounts(("account",)):
            self.assertIs(typed_result, api.collect_kingdom_chat(account_id="account"))
            with self.assertRaisesRegex(RuntimeError, "outside the active workflow reservation"):
                api.collect_kingdom_chat(account_id="other")

        application.reserve_accounts.assert_called_once_with(("account",))
        application.reserve_accounts.return_value.close.assert_called_once_with()
        application.run_collect_kingdom_chat.assert_called_once_with(account_id="account")


def _account() -> SimpleNamespace:
    """Builds the minimal account shape needed before connected runtime construction."""

    return SimpleNamespace(
        id="account",
        artifact_directory_name="account",
    )


if __name__ == "__main__":
    unittest.main()
