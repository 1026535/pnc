"""Focused offline coverage for the replacement-core open-building boundary."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult, WorkflowContext
from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.open_building import (
    OpenBuildingResult,
    OpenBuildingWorkflow,
    build_open_building_workflow,
)
from pnc_automation.app.entrypoints.api import AutomationApi
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.entrypoints.cli import main
from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import ScriptValidationError


class OpenBuildingCoreTests(unittest.TestCase):
    """Covers parse, lifecycle, constrained context, and direct entry points."""

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

    def test_application_preflight_precedes_open_building_workflow(self) -> None:
        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        events: list[str] = []
        runtime.preflight_active_castle_identity.side_effect = lambda: events.append("preflight")
        required_role = LiveAutomationRole.LIVE_TESTING

        class _Runner:
            @classmethod
            def __class_getitem__(cls, item):
                del item
                return cls

            def __init__(self, core_runtime) -> None:
                del core_runtime

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
                    required_role=LiveAutomationRole.LIVE_TESTING,
                )

        factory.assert_called_once_with(
            script_runner,
            account,
            "account",
            required_role=LiveAutomationRole.LIVE_TESTING,
        )
        runtime.close.assert_called_once_with()

    def test_workflow_uses_dynamic_exact_endpoint_and_typed_result(self) -> None:
        workflow = build_open_building_workflow({"building": HomeCityObjectId.INSTITUTE.value})
        captured_at = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
        observation = Observation(
            screen_type=ScreenType.PNC_INSTITUTE,
            visible_elements={},
            captured_at=captured_at,
            artifact_path=Path("institute.png"),
        )
        context = Mock()
        context.open_building.return_value = observation

        result = workflow.execute(context)

        self.assertEqual(ScreenType.PNC_INSTITUTE, workflow.spec.exit_screen)
        self.assertEqual(
            OpenBuildingResult(
                building=HomeCityObjectId.INSTITUTE,
                screen_type=ScreenType.PNC_INSTITUTE,
                captured_at=captured_at,
                artifact_path="institute.png",
            ),
            result,
        )
        context.open_building.assert_called_once_with(HomeCityObjectId.INSTITUTE)

    def test_context_delegates_once_and_does_not_replay_failure(self) -> None:
        runtime = Mock()
        runtime.navigation.open_building.side_effect = RuntimeError("completion failed")
        context = WorkflowContext(
            runtime,
            last_observation=Observation(
                screen_type=ScreenType.PNC_HOME_CITY,
                visible_elements={},
                captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "completion failed"):
            context.open_building(HomeCityObjectId.INSTITUTE)

        runtime.navigation.open_building.assert_called_once()

    def test_cli_routes_to_application_method_and_serializes_core_result(self) -> None:
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
        application.run_open_building.return_value = result
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

    def test_python_api_routes_to_application_open_building(self) -> None:
        application = Mock()
        expected = object()
        application.run_open_building.return_value = expected

        result = AutomationApi(application=application).open_building(
            account_id="account",
            building=HomeCityObjectId.INSTITUTE.value,
        )

        self.assertIs(expected, result)
        application.run_open_building.assert_called_once_with(
            account_id="account",
            building=HomeCityObjectId.INSTITUTE.value,
        )


if __name__ == "__main__":
    unittest.main()
