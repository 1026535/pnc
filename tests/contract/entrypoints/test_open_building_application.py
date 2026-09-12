"""Contract tests for the replacement-core open-building application and API."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult
from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.open_building import OpenBuildingResult
from pnc_automation.app.entrypoints.api import AutomationApi
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.entrypoints.cli import main
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import ScriptValidationError


class OpenBuildingApplicationTests(unittest.TestCase):
    """Covers application preflight, role forwarding, CLI routing, and API lease scope."""

    def test_invalid_primary_screen_rejects_before_factory_or_preflight(self) -> None:
        script_runner = Mock()
        with patch("pnc_automation.app.entrypoints.app.build_core_runtime") as factory:
            with self.assertRaises(ScriptValidationError):
                ApplicationRunner(script_runner).run_open_building(
                    account_id="account",
                    building=HomeCityObjectId.BANK.value,
                )
        factory.assert_not_called()
        script_runner.config.require_account.assert_not_called()

    def test_application_defaults_to_live_testing_role(self) -> None:
        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        runtime.preflight_active_castle_identity.return_value = None

        class _Runner:
            @classmethod
            def __class_getitem__(cls, _item):
                return cls

            def __init__(self, _runtime) -> None:
                pass

            def run(self, _workflow):
                return "result"

        with (
            patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime) as factory,
            patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
        ):
            result = ApplicationRunner(script_runner).run_open_building(
                account_id="account",
                building=HomeCityObjectId.INSTITUTE.value,
            )

        self.assertEqual("result", result)
        factory.assert_called_once_with(
            script_runner,
            account,
            "account",
            required_role=LiveAutomationRole.LIVE_TESTING,
            session_cleanup_policy=None,
        )
        runtime.close.assert_called_once_with()

    def test_application_preflight_precedes_open_building_workflow_and_forwards_explicit_role(self) -> None:
        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        events: list[str] = []
        runtime.preflight_active_castle_identity.side_effect = lambda: events.append("preflight")
        required_role = LiveAutomationRole.SMOKE_TEST

        class _Runner:
            @classmethod
            def __class_getitem__(cls, item):
                del item
                return cls

            def __init__(self, _runtime) -> None:
                pass

            def run(self, workflow):
                events.append(f"workflow:{workflow.spec.exit_screen.name}")
                return "result"

        with (
            patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime) as factory,
            patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
        ):
            result = ApplicationRunner(script_runner).run_open_building(
                account_id="account",
                building=HomeCityObjectId.INSTITUTE.value,
                required_role=required_role,
            )

        self.assertEqual("result", result)
        self.assertEqual(["preflight", "workflow:PNC_INSTITUTE"], events)
        factory.assert_called_once_with(
            script_runner,
            account,
            "account",
            required_role=required_role,
            session_cleanup_policy=None,
        )
        runtime.close.assert_called_once_with()

    def test_application_closes_runtime_when_preflight_fails(self) -> None:
        """Closes the connected replacement runtime on a preflight failure."""

        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        runtime.preflight_active_castle_identity.side_effect = RuntimeError("preflight failed")

        with patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime) as factory:
            with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                ApplicationRunner(script_runner).run_open_building(
                    account_id="account",
                    building=HomeCityObjectId.INSTITUTE.value,
                )

        factory.assert_called_once_with(
            script_runner,
            account,
            "account",
            required_role=LiveAutomationRole.LIVE_TESTING,
            session_cleanup_policy=None,
        )
        runtime.close.assert_called_once_with()

    def test_cli_routes_to_application_method_with_full_reservation_and_serializes_core_result(self) -> None:
        result = CoreWorkflowResult(
            workflow_name="open_building",
            succeeded=True,
            value=OpenBuildingResult(
                building=HomeCityObjectId.INSTITUTE,
                screen_type=ScreenType.PNC_INSTITUTE,
                captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
            ),
            exit_screen=ScreenType.PNC_INSTITUTE,
            trace_path="trace.jsonl",
        )
        application = Mock()
        events: list[str] = []

        class _Reservation:
            def __enter__(self):
                events.append("reserve_enter")
                return self

            def __exit__(self, exception_type, exception, traceback):
                del exception_type, exception, traceback
                events.append("reserve_exit")

        application.reserve_accounts.return_value = _Reservation()
        prepared = RunResult(
            account_id="account",
            script_name="prepare_account_session",
            steps=(
                StepRunResult(
                    task_id=TaskId.LOGIN,
                    status=TaskStatus.SUCCESS,
                    attempts=1,
                    message="ok",
                ),
            ),
            started_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
            finished_at=datetime(2026, 9, 11, 12, 0, 1, tzinfo=UTC),
        )
        application.prepare_account_session.side_effect = lambda **_: (events.append("prepare"), prepared)[1]
        application.run_open_building.side_effect = lambda **_: (events.append("open"), result)[1]

        with (
            patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=application),
            patch("builtins.print") as output,
        ):
            exit_code = main([
                "open-building",
                "--config",
                "accounts.yaml",
                "--account",
                "account",
                "--building",
                HomeCityObjectId.INSTITUTE.value,
                "--kingdom",
                "K230",
                "--castle-name",
                "Castle",
            ])

        self.assertEqual(0, exit_code)
        self.assertEqual(["reserve_enter", "prepare", "open", "reserve_exit"], events)
        application.reserve_accounts.assert_called_once_with(("account",))
        application.prepare_account_session.assert_called_once()
        application.run_open_building.assert_called_once_with(
            account_id="account",
            building=HomeCityObjectId.INSTITUTE.value,
            required_role=LiveAutomationRole.LIVE_TESTING,
        )
        application.run_task.assert_not_called()
        document = json.loads(output.call_args.args[0])
        self.assertEqual("open_building", document["workflow_name"])
        self.assertEqual(HomeCityObjectId.INSTITUTE.value, document["value"]["building"])

    def test_python_api_routes_to_application_and_closes_temporary_reservation_on_success(self) -> None:
        application = Mock()
        expected = Mock(spec=CoreWorkflowResult)
        application.run_open_building.return_value = expected
        api = AutomationApi(application=application)

        result = api.open_building(account_id="account", building=HomeCityObjectId.INSTITUTE.value)

        self.assertIs(expected, result)
        application.run_open_building.assert_called_once_with(
            account_id="account",
            building=HomeCityObjectId.INSTITUTE.value,
            session_cleanup_policy=None,
        )
        application.reserve_accounts.assert_called_once_with(("account",))
        application.reserve_accounts.return_value.close.assert_called_once_with()

    def test_python_api_closes_temporary_reservation_when_application_fails(self) -> None:
        application = Mock()
        application.run_open_building.side_effect = RuntimeError("open failed")
        api = AutomationApi(application=application)

        with self.assertRaisesRegex(RuntimeError, "open failed"):
            api.open_building(account_id="account", building=HomeCityObjectId.INSTITUTE.value)

        application.reserve_accounts.assert_called_once_with(("account",))
        application.reserve_accounts.return_value.close.assert_called_once_with()

    def test_python_api_reuses_active_reservation(self) -> None:
        application = Mock()
        expected = Mock(spec=CoreWorkflowResult)
        application.run_open_building.return_value = expected
        api = AutomationApi(application=application)

        with api.reserve_accounts(("account",)):
            self.assertIs(
                expected,
                api.open_building(account_id="account", building=HomeCityObjectId.INSTITUTE.value),
            )

        application.reserve_accounts.assert_called_once_with(("account",))
        application.reserve_accounts.return_value.close.assert_called_once_with()
        application.run_open_building.assert_called_once_with(
            account_id="account",
            building=HomeCityObjectId.INSTITUTE.value,
            session_cleanup_policy=None,
        )

    def test_python_api_rejects_account_outside_active_reservation(self) -> None:
        application = Mock()
        api = AutomationApi(application=application)

        with api.reserve_accounts(("account",)):
            with self.assertRaisesRegex(RuntimeError, "outside the active workflow reservation"):
                api.open_building(account_id="other", building=HomeCityObjectId.INSTITUTE.value)

        application.run_open_building.assert_not_called()

    def test_python_api_rejects_cross_api_call_during_active_reservation(self) -> None:
        first_application = Mock()
        second_application = Mock()
        first_api = AutomationApi(application=first_application)
        second_api = AutomationApi(application=second_application)

        with first_api.reserve_accounts(("account",)):
            with self.assertRaisesRegex(RuntimeError, "cannot switch AutomationApi instances"):
                second_api.open_building(account_id="account", building=HomeCityObjectId.INSTITUTE.value)

        second_application.reserve_accounts.assert_not_called()

    def test_legacy_task_id_dispatch_remains_available(self) -> None:
        """Authored TaskId callers retain the legacy ScriptRunner dispatch boundary."""

        application = Mock()
        api = AutomationApi(application=application)

        api.run_task(
            account_id="account",
            task_id=TaskId.OPEN_BUILDING,
            params={"building": HomeCityObjectId.INSTITUTE.value},
        )

        application.run_task.assert_called_once_with(
            account_id="account",
            task_id=TaskId.OPEN_BUILDING,
            params={"building": HomeCityObjectId.INSTITUTE.value},
        )
        application.run_open_building.assert_not_called()


if __name__ == "__main__":
    unittest.main()
