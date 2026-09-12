"""Deterministic authored Kingdom Chat dispatch coverage."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.automation.engine.core_script_dispatcher import CoreScriptDispatcher
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult
from pnc_automation.app.automation.engine.runner import AutomationRunner, CoreStepRunResult
from pnc_automation.app.automation.engine.script_runner import ScriptRunner
from pnc_automation.app.automation.engine.task import (
    CastleTargetPolicy,
    CoreWorkflowTaskDefinition,
    TaskId,
    TaskStatus,
)
from pnc_automation.app.authoring.config.models import AccountConfig, DefaultsConfig, LiveAutomationRole
from pnc_automation.app.authoring.scripts.models import (
    PreparedRunScript,
    PreparedScriptStep,
    RunScript,
    ScriptStep,
)
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore

from tests.support.core.logging import build_logger


class TypedCoreDispatchTests(unittest.TestCase):
    """Covers typed task preparation, runner routing, and dispatcher ownership."""

    def test_default_registry_uses_immutable_parameterless_core_definition(self) -> None:
        """Keeps Chat metadata independent from concrete workflow implementations."""

        definition = build_default_task_registry().require(TaskId.COLLECT_KINGDOM_CHAT)

        self.assertIsInstance(definition, CoreWorkflowTaskDefinition)
        self.assertEqual(definition.castle_target_policy, CastleTargetPolicy.OPTIONAL)
        self.assertIsNone(definition.parse_params({}))
        with self.assertRaisesRegex(Exception, "does not accept"):
            definition.parse_params({"unexpected": True})
        with self.assertRaises(AttributeError):
            definition.id = TaskId.COLLECT_MAIL  # type: ignore[misc]

    def test_current_castle_core_step_skips_legacy_observation_and_retains_typed_result(self) -> None:
        """Dispatches a current-castle Chat step directly through the typed executor."""

        workflow_result = _workflow_result()
        executor = Mock()
        executor.execute.return_value = workflow_result
        observation_service = Mock()
        runner = _make_runner(observation_service=observation_service, core_step_executor=executor)

        result = runner.run(
            _account(),
            PreparedRunScript(name="chat", path=Path("chat.yaml"), steps=(_prepared_chat_step(),)),
        )

        self.assertIsInstance(result.steps[0], CoreStepRunResult)
        self.assertIs(result.steps[0].workflow_result, workflow_result)
        self.assertEqual(result.steps[0].status, TaskStatus.SUCCESS)
        self.assertEqual(asdict(result.steps[0])["workflow_result"], asdict(workflow_result))
        observation_service.observe.assert_not_called()
        executor.execute.assert_called_once()

    def test_core_step_without_dispatcher_fails_closed_before_legacy_loop(self) -> None:
        """Rejects an unavailable typed executor without observing or executing a legacy task."""

        observation_service = Mock()
        runner = _make_runner(observation_service=observation_service)

        with self.assertRaisesRegex(RuntimeError, "no configured core-step executor"):
            runner.run(
                _account(),
                PreparedRunScript(name="chat", path=Path("chat.yaml"), steps=(_prepared_chat_step(),)),
            )

        observation_service.observe.assert_not_called()

    def test_core_failure_result_stops_before_following_step(self) -> None:
        """Does not continue a mixed script after a typed workflow reports failure."""

        executor = Mock()
        failed = _workflow_result()
        failed = CoreWorkflowResult(
            workflow_name=failed.workflow_name,
            succeeded=False,
            value=failed.value,
            exit_screen=failed.exit_screen,
            trace_path=failed.trace_path,
        )
        executor.execute.return_value = failed
        script = PreparedRunScript(
            name="chat",
            path=Path("chat.yaml"),
            steps=(_prepared_chat_step(), _prepared_chat_step()),
        )

        with self.assertRaisesRegex(RuntimeError, "reported failure"):
            _make_runner(observation_service=Mock(), core_step_executor=executor).run(_account(), script)

        executor.execute.assert_called_once()

    def test_core_exception_stops_before_following_step(self) -> None:
        """Propagates a typed core exception without replaying it or running the next step."""

        executor = Mock()
        executor.execute.side_effect = RuntimeError("core failed")
        script = PreparedRunScript(
            name="chat",
            path=Path("chat.yaml"),
            steps=(_prepared_chat_step(), _prepared_chat_step()),
        )

        with self.assertRaisesRegex(RuntimeError, "core failed"):
            _make_runner(observation_service=Mock(), core_step_executor=executor).run(_account(), script)

        executor.execute.assert_called_once()

    def test_explicit_castle_uses_existing_alignment_once_before_core_dispatch(self) -> None:
        """Runs the established synthetic castle alignment once, then delegates the typed step."""

        executor = Mock()
        executor.execute.return_value = _workflow_result()
        observation_service = Mock()
        runner = _make_runner(observation_service=observation_service, core_step_executor=executor)
        step = _prepared_chat_step(castle=CastleIdentity("K1", "Castle", 12))

        with patch.object(AutomationRunner, "_align_step_castle_target", return_value=None) as align:
            runner.run(_account(), PreparedRunScript(name="chat", path=Path("chat.yaml"), steps=(step,)))

        observation_service.observe.assert_called_once_with("collect_kingdom_chat_before")
        align.assert_called_once()
        executor.execute.assert_called_once_with(step=step)

    def test_dispatcher_rejects_missing_archive_before_composition(self) -> None:
        """Fails before core assembly when the canonical Chat archive dependency is absent."""

        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=Mock(),
        )

        with self.assertRaisesRegex(RuntimeError, "ChatArchiveStore"):
            dispatcher.execute(step=_prepared_chat_step())

        dispatcher.core_runtime_factory.assert_not_called()  # type: ignore[attr-defined]

    def test_dispatcher_validates_exact_castle_after_core_preflight(self) -> None:
        """Uses the canonical exact identity matcher and leaves the shared runtime open per step."""

        active = CastleIdentity("K1", "Active", 12)
        requested = CastleIdentity("K1", "Requested", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        runner_factory = Mock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            dispatcher = CoreScriptDispatcher(
                account=_account(),
                chat_archive_store=ChatArchiveStore(Path(temporary_directory) / "chat"),
                core_runtime_factory=Mock(return_value=core_runtime),
            )

            with patch(
                "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
                runner_factory,
            ):
                with self.assertRaisesRegex(RuntimeError, "requested castle target"):
                    dispatcher.execute(step=_prepared_chat_step(castle=requested))

        core_runtime.preflight_active_castle_identity.assert_called_once_with()
        runner_factory.assert_not_called()
        core_runtime.close.assert_not_called()

    def test_dispatcher_lazily_composes_once_and_returns_typed_result(self) -> None:
        """Uses the supplied connected-runtime factory without taking ownership of its close."""

        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = CastleIdentity("K1", "Active", 12)
        typed_result = _workflow_result()
        workflow_runner = Mock()
        workflow_runner.run.return_value = typed_result
        runner_factory = Mock(return_value=workflow_runner)
        runtime_factory = Mock(return_value=core_runtime)
        with tempfile.TemporaryDirectory() as temporary_directory:
            dispatcher = CoreScriptDispatcher(
                account=_account(),
                chat_archive_store=ChatArchiveStore(Path(temporary_directory) / "chat"),
                core_runtime_factory=runtime_factory,
            )
            with patch(
                "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
                runner_factory,
            ):
                self.assertIs(typed_result, dispatcher.execute(step=_prepared_chat_step()))
                self.assertIs(typed_result, dispatcher.execute(step=_prepared_chat_step()))

        runtime_factory.assert_called_once_with()
        runner_factory.assert_called_once_with(core_runtime)
        self.assertEqual(workflow_runner.run.call_count, 2)
        core_runtime.close.assert_not_called()

    def test_script_runner_validates_dependencies_before_connection_and_forwards_role(self) -> None:
        """Rejects unavailable typed scripts before connect and forwards explicit authority."""

        account = _account(roles=frozenset({LiveAutomationRole.SMOKE_TEST}))
        script_runner = _minimal_script_runner(archive_store=None)
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaisesRegex(RuntimeError, "ChatArchiveStore"):
                script_runner._run_script_for_account(account=account, script=_run_script(params={}))
        build_runner.assert_not_called()

        script_runner = _minimal_script_runner(
            archive_store=ChatArchiveStore(Path(tempfile.mkdtemp()) / "chat"),
        )
        fake_runner = Mock()
        fake_runner.run.return_value = Mock()
        with patch.object(ScriptRunner, "_build_runner", return_value=(fake_runner, lambda: None)) as build_runner:
            script_runner._run_script_for_account(
                account=account,
                script=_run_script(params={}),
                required_role=LiveAutomationRole.SMOKE_TEST,
            )
        build_runner.assert_called_once_with(account, required_role=LiveAutomationRole.SMOKE_TEST)

        invalid = _minimal_script_runner(
            archive_store=ChatArchiveStore(Path(tempfile.mkdtemp()) / "chat"),
        )
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaisesRegex(Exception, "does not accept"):
                invalid._run_script_for_account(account=account, script=_run_script(params={"unexpected": True}))
        build_runner.assert_not_called()


def _account(*, roles: frozenset[LiveAutomationRole] | None = None) -> AccountConfig:
    """Builds one offline account binding with the requested live roles."""

    return AccountConfig(
        id="account",
        instance_id="instance",
        pnc_account_id="pnc-account",
        live_roles=frozenset({LiveAutomationRole.LIVE_TESTING}) if roles is None else roles,
    )


def _prepared_chat_step(*, castle: CastleIdentity | None = None) -> PreparedScriptStep:
    """Builds one already-prepared typed Chat step."""

    script_step = ScriptStep(task=TaskId.COLLECT_KINGDOM_CHAT, castle=castle)
    return PreparedScriptStep(
        script_step=script_step,
        parsed_params=None,
        castle_target_policy=CastleTargetPolicy.OPTIONAL,
        resolved_castle=castle,
    )


def _workflow_result() -> CoreWorkflowResult[object]:
    """Builds a minimal successful typed result for runner routing tests."""

    return CoreWorkflowResult(
        workflow_name="collect_kingdom_chat",
        succeeded=True,
        value="value",
        exit_screen=ScreenType.PNC_HOME_CITY,
        trace_path="trace.jsonl",
    )


def _make_runner(*, observation_service: Mock, core_step_executor: object | None = None) -> AutomationRunner:
    """Builds an offline runner with only the dependencies used by typed dispatch."""

    return AutomationRunner(
        defaults=DefaultsConfig(),
        observation_service=observation_service,
        action_executor=Mock(),
        task_registry=build_default_task_registry(),
        flow_planner=Mock(),
        logger=build_logger(),
        core_step_executor=core_step_executor,
    )


def _run_script(*, params: dict[str, object]) -> RunScript:
    """Builds a minimal authored Chat script for ScriptRunner preflight tests."""

    return RunScript(
        name="chat",
        path=Path("chat.yaml"),
        steps=(ScriptStep(task=TaskId.COLLECT_KINGDOM_CHAT, params=params),),
    )


def _minimal_script_runner(*, archive_store: ChatArchiveStore | None) -> ScriptRunner:
    """Builds the smallest ScriptRunner object needed to test pre-connect validation."""

    runner = ScriptRunner.__new__(ScriptRunner)
    runner.config = SimpleNamespace(find_castle_targets=lambda _account_id: None)
    runner.task_registry = build_default_task_registry()
    runner.castle_roster_store = None
    runner.mail_archive_store = None
    runner.chat_archive_store = archive_store
    return runner


if __name__ == "__main__":
    unittest.main()
