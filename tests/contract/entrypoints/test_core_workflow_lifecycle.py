"""Lifecycle contracts shared by the typed replacement-core application entrypoints."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.entrypoints.api import AutomationApi
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.infra.emulator.session import BlueStacksSessionCleanupPolicy


class CoreWorkflowApplicationLifecycleTests(unittest.TestCase):
    """Covers cleanup-policy forwarding and failure preservation for typed entrypoints."""

    def test_typed_entrypoints_forward_outer_cleanup_policy(self) -> None:
        """Passes the active phase policy through every typed application runner."""

        policy = BlueStacksSessionCleanupPolicy.close_at_phase_end(
            close_preexisting_instance=True,
        )
        for method_name in _METHOD_NAMES:
            with self.subTest(method=method_name), tempfile.TemporaryDirectory() as temporary_directory:
                script_runner, account = _script_runner(Path(temporary_directory))
                runtime = Mock()
                runtime.preflight_active_castle_identity.return_value = CastleIdentity("K1", "Castle", 22)
                with (
                    patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime) as factory,
                    patch(
                        "pnc_automation.app.entrypoints.app.CoreWorkflowRunner",
                        _successful_workflow_runner,
                    ),
                ):
                    result = _invoke(ApplicationRunner(script_runner), method_name, policy=policy)

                self.assertEqual("result", result)
                factory.assert_called_once_with(
                    script_runner,
                    account,
                    account.artifact_directory_name,
                    required_role=LiveAutomationRole.LIVE_TESTING,
                    session_cleanup_policy=policy,
                )
                runtime.close.assert_called_once_with()

    def test_typed_entrypoints_preserve_workflow_and_close_failures(self) -> None:
        """Keeps both the workflow failure and runtime-close failure visible."""

        for method_name in _METHOD_NAMES:
            with self.subTest(method=method_name), tempfile.TemporaryDirectory() as temporary_directory:
                script_runner, _account = _script_runner(Path(temporary_directory))
                runtime = Mock()
                runtime.preflight_active_castle_identity.return_value = CastleIdentity("K1", "Castle", 22)
                runtime.close.side_effect = RuntimeError("close failed")
                with (
                    patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime),
                    patch(
                        "pnc_automation.app.entrypoints.app.CoreWorkflowRunner",
                        _failing_workflow_runner,
                    ),
                ):
                    with self.assertRaises(BaseExceptionGroup) as raised:
                        _invoke(ApplicationRunner(script_runner), method_name)

                self.assertEqual(
                    {str(error) for error in raised.exception.exceptions},
                    {"workflow failed", "close failed"},
                )
                runtime.close.assert_called_once_with()

    def test_api_typed_callbacks_forward_outer_cleanup_policy(self) -> None:
        """Passes the reservation policy into each typed application callback."""

        policy = BlueStacksSessionCleanupPolicy.close_at_phase_end(
            close_preexisting_instance=True,
        )
        for method_name in _METHOD_NAMES:
            with self.subTest(method=method_name):
                application = Mock()
                application.reserve_accounts.return_value = Mock()
                api = AutomationApi(application=application)
                expected = object()
                getattr(application, method_name).return_value = expected

                with api.reserve_accounts(("account",), session_cleanup_policy=policy):
                    self.assertIs(expected, _invoke_api(api, method_name))

                expected_call = _api_call(method_name, policy)
                getattr(application, method_name).assert_called_once_with(**expected_call)


_METHOD_NAMES = (
    "run_collect_mail",
    "run_collect_kingdom_chat",
    "run_open_building",
    "run_refresh_castle_roster",
)


def _script_runner(root: Path) -> tuple[Mock, SimpleNamespace]:
    """Builds the minimal runner and account shape used before core connection."""

    account = SimpleNamespace(
        id="account",
        pnc_account_id="pnc-account",
        artifact_directory_name="account",
    )
    script_runner = Mock()
    script_runner.config.require_account.return_value = account
    script_runner.mail_archive_store = MailArchiveStore(root / "mail")
    script_runner.chat_archive_store = ChatArchiveStore(root / "chat")
    script_runner.castle_roster_store = CastleRosterStore(root / "castles.yaml")
    return script_runner, account


def _invoke(
    application: ApplicationRunner,
    method_name: str,
    *,
    policy: BlueStacksSessionCleanupPolicy | None = None,
) -> object:
    """Invokes one typed application method with its smallest valid arguments."""

    if method_name == "run_collect_mail":
        return application.run_collect_mail(
            account_id="account",
            params={"mailboxes": ["player"]},
            session_cleanup_policy=policy,
        )
    if method_name == "run_collect_kingdom_chat":
        return application.run_collect_kingdom_chat(
            account_id="account",
            session_cleanup_policy=policy,
        )
    if method_name == "run_open_building":
        return application.run_open_building(
            account_id="account",
            building=HomeCityObjectId.INSTITUTE.value,
            session_cleanup_policy=policy,
        )
    if method_name == "run_refresh_castle_roster":
        return application.run_refresh_castle_roster(
            account_id="account",
            session_cleanup_policy=policy,
        )
    raise AssertionError(f"Unknown typed application method: {method_name}")


def _invoke_api(api: AutomationApi, method_name: str) -> object:
    """Invokes one typed Python API method with its smallest valid arguments."""

    if method_name == "run_collect_mail":
        return api.collect_mail(account_id="account", mailboxes=["player"])
    if method_name == "run_collect_kingdom_chat":
        return api.collect_kingdom_chat(account_id="account")
    if method_name == "run_open_building":
        return api.open_building(account_id="account", building=HomeCityObjectId.INSTITUTE.value)
    if method_name == "run_refresh_castle_roster":
        return api.refresh_castle_roster(account_id="account")
    raise AssertionError(f"Unknown typed API method: {method_name}")


def _api_call(method_name: str, policy: BlueStacksSessionCleanupPolicy) -> dict[str, object]:
    """Returns expected application callback arguments for one typed API method."""

    if method_name == "run_collect_mail":
        return {
            "account_id": "account",
            "params": {
                "mailboxes": ["player"],
                "archive_mode": "both",
                "limit_per_mailbox": 25,
                "only_new": True,
            },
            "session_cleanup_policy": policy,
        }
    if method_name == "run_collect_kingdom_chat":
        return {"account_id": "account", "session_cleanup_policy": policy}
    if method_name == "run_open_building":
        return {
            "account_id": "account",
            "building": HomeCityObjectId.INSTITUTE.value,
            "session_cleanup_policy": policy,
        }
    if method_name == "run_refresh_castle_roster":
        return {"account_id": "account", "session_cleanup_policy": policy}
    raise AssertionError(f"Unknown typed application method: {method_name}")


class _successful_workflow_runner:
    """Minimal generic runner stand-in for successful application tests."""

    @classmethod
    def __class_getitem__(cls, _item: object) -> type["_successful_workflow_runner"]:
        return cls

    def __init__(self, _runtime: object) -> None:
        pass

    def run(self, _workflow: object) -> str:
        return "result"


class _failing_workflow_runner:
    """Minimal generic runner stand-in for cleanup failure tests."""

    @classmethod
    def __class_getitem__(cls, _item: object) -> type["_failing_workflow_runner"]:
        return cls

    def __init__(self, _runtime: object) -> None:
        pass

    def run(self, _workflow: object) -> None:
        raise RuntimeError("workflow failed")


if __name__ == "__main__":
    unittest.main()
