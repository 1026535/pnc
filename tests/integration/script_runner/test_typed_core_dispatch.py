"""Deterministic authored typed core dispatch coverage."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.automation.engine.core_runtime import build_core_runtime
from pnc_automation.app.automation.engine.core_script_dispatcher import CoreScriptDispatcher, GameReadyResult
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult
from pnc_automation.app.automation.collect_mail import (
    CollectMailMailboxResult,
    CollectMailResult,
    CollectMailWorkflow,
)
from pnc_automation.app.automation.open_building import OpenBuildingResult, OpenBuildingWorkflow
from pnc_automation.app.automation.send_chat import SendChatWorkflow
from pnc_automation.app.automation.select_castle import SelectCastleWorkflow
from pnc_automation.app.automation.refresh_castle_roster import (
    RefreshCastleRosterResult,
    RefreshCastleRosterWorkflow,
)
from pnc_automation.app.automation.engine.runner import (
    AutomationRunner,
    CoreStepRunResult,
    RunResult,
)
from pnc_automation.app.pnc.domain.action_requests import InputTextAction, TapAction
from pnc_automation.app.automation.engine.script_runner import ScriptRunner
from pnc_automation.app.automation.engine.task import (
    BaseAutomationTask,
    CastleTargetPolicy,
    CoreWorkflowTaskDefinition,
    TaskResult,
    TaskId,
    TaskStatus,
    require_no_params,
)
from pnc_automation.app.automation.match3 import UnavailableMatch3Component
from pnc_automation.app.authoring.config.models import AccountConfig, DefaultsConfig, LiveAutomationRole
from pnc_automation.app.authoring.scripts.models import (
    PreparedRunScript,
    PreparedScriptStep,
    RunScript,
    ScriptStep,
)
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.entrypoints.cli import _serialize_run_result
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatMessageTaskParams
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.app.pnc.domain.mail import (
    CollectMailParams,
    MailArchiveMode,
    MailboxAvailability,
    MailboxType,
)
from pnc_automation.app.pnc.domain.policy_models import OpenBuildingPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.errors import ScriptValidationError
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.session import BlueStacksSessionCleanupPolicy

from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_entry, make_observation


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

    def test_default_registry_uses_typed_world_chat_message_definition(self) -> None:
        """Keeps authored World Chat metadata independent from the workflow implementation."""

        definition = build_default_task_registry().require(TaskId.SEND_WORLD_CHAT_MESSAGE)

        self.assertIsInstance(definition, CoreWorkflowTaskDefinition)
        self.assertEqual(CastleTargetPolicy.OPTIONAL, definition.castle_target_policy)
        self.assertEqual(
            ChatMessageTaskParams(message="hello"),
            definition.parse_params({"message": "hello"}),
        )

    def test_default_registry_uses_required_typed_select_castle_definition(self) -> None:
        """Keeps authored castle selection parameterless while requiring its explicit target."""

        definition = build_default_task_registry().require(TaskId.SELECT_CASTLE)

        self.assertIsInstance(definition, CoreWorkflowTaskDefinition)
        self.assertEqual(CastleTargetPolicy.REQUIRED, definition.castle_target_policy)
        self.assertIsNone(definition.parse_params({}))

    def test_dispatcher_builds_select_castle_workflow_without_storage_dependencies(self) -> None:
        """Builds typed selection after active identity preflight and keeps the target exact."""

        active = CastleIdentity("K1", "Current", 12)
        target = CastleIdentity("K2", "Target", 11)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        typed_result = _workflow_result()
        workflow_runner = Mock()
        workflow_runner.run.return_value = typed_result
        runtime_factory = Mock(return_value=core_runtime)
        runner_factory = Mock(return_value=workflow_runner)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            mail_archive_store=None,
            castle_roster_store=None,
            core_runtime_factory=runtime_factory,
        )

        with patch(
            "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
            runner_factory,
        ):
            result = dispatcher.execute(step=_prepared_select_step(target))

        self.assertIs(typed_result, result)
        workflow = workflow_runner.run.call_args.args[0]
        self.assertIsInstance(workflow, SelectCastleWorkflow)
        self.assertEqual(active, workflow.original_castle)
        self.assertEqual(target, workflow.target_castle)
        runtime_factory.assert_called_once_with()
        core_runtime.preflight_active_castle_identity.assert_called_once_with()

    def test_dispatcher_rejects_select_castle_without_target_before_runtime(self) -> None:
        """Rejects malformed typed selection before composing a connected runtime."""

        runtime_factory = Mock()
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=runtime_factory,
        )

        with self.assertRaisesRegex(RuntimeError, "explicit castle target"):
            dispatcher.execute(step=_prepared_select_step(None))

        runtime_factory.assert_not_called()

    def test_dispatcher_rejects_malformed_chat_params_before_runtime(self) -> None:
        """Rejects unparsed typed World and Alliance payloads without composing the runtime."""

        for task_id, prepared_step in (
            (TaskId.SEND_WORLD_CHAT_MESSAGE, _prepared_world_chat_step()),
            (TaskId.SEND_ALLIANCE_CHAT_MESSAGE, _prepared_alliance_chat_step()),
        ):
            for malformed_params in (None, {"message": "hello"}):
                with self.subTest(task_id=task_id, malformed_params=malformed_params):
                    runtime_factory = Mock()
                    dispatcher = CoreScriptDispatcher(
                        account=_account(),
                        chat_archive_store=None,
                        core_runtime_factory=runtime_factory,
                    )

                    with self.assertRaisesRegex(RuntimeError, "ChatMessageTaskParams"):
                        dispatcher.execute(
                            step=replace(
                                prepared_step,
                                parsed_params=malformed_params,
                            )
                        )

                    runtime_factory.assert_not_called()

    def test_dispatcher_builds_world_chat_workflow_without_archive_store(self) -> None:
        """Builds the fixed World Chat workflow from typed params without Chat storage."""

        active = CastleIdentity("K1", "free cookies", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        typed_result = _workflow_result()
        workflow_runner = Mock()
        workflow_runner.run.return_value = typed_result
        runtime_factory = Mock(return_value=core_runtime)
        runner_factory = Mock(return_value=workflow_runner)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=runtime_factory,
        )

        with patch(
            "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
            runner_factory,
        ):
            result = dispatcher.execute(step=_prepared_world_chat_step())

        self.assertIs(typed_result, result)
        workflow = workflow_runner.run.call_args.args[0]
        self.assertIsInstance(workflow, SendChatWorkflow)
        self.assertEqual(ChatMessageTaskParams(message="hello"), workflow.params)
        self.assertEqual(ChatChannel.WORLD, workflow.channel)
        self.assertIs(active, workflow.active_castle)
        runtime_factory.assert_called_once_with()
        core_runtime.preflight_active_castle_identity.assert_called_once_with()

    def test_dispatcher_builds_alliance_chat_workflow_without_archive_store(self) -> None:
        """Builds Alliance Chat through the same typed dispatcher without storage dependencies."""

        active = CastleIdentity("K1", "free cookies", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        typed_result = _workflow_result()
        workflow_runner = Mock()
        workflow_runner.run.return_value = typed_result
        runtime_factory = Mock(return_value=core_runtime)
        runner_factory = Mock(return_value=workflow_runner)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=runtime_factory,
        )

        with patch(
            "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
            runner_factory,
        ):
            result = dispatcher.execute(step=_prepared_alliance_chat_step())

        self.assertIs(typed_result, result)
        workflow = workflow_runner.run.call_args.args[0]
        self.assertIsInstance(workflow, SendChatWorkflow)
        self.assertEqual(ChatMessageTaskParams(message="hello"), workflow.params)
        self.assertEqual(ChatChannel.ALLIANCE, workflow.channel)
        self.assertIs(active, workflow.active_castle)
        runtime_factory.assert_called_once_with()
        core_runtime.preflight_active_castle_identity.assert_called_once_with()

    def test_authored_alliance_chat_send_reaches_home_after_whitespace_receipt(self) -> None:
        """Runs one authored Alliance send through real receipt completion and Home exit."""

        message = "test from bot"
        castle = CastleIdentity("K1", "free cookies")
        runtime = _FakeChatCoreRuntime(_alliance_send_frames(message), active_castle=castle)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=lambda: runtime,
        )
        runner = _make_runner(observation_service=Mock(), core_step_executor=dispatcher)
        script = build_default_task_registry().prepare_script(
            RunScript(
                name="alliance_chat",
                path=Path("alliance_chat.yaml"),
                steps=(
                    ScriptStep(
                        task=TaskId.SEND_ALLIANCE_CHAT_MESSAGE,
                        params={"message": message},
                    ),
                ),
            )
        )

        result = runner.run(_account(), script)

        step_result = result.steps[0]
        self.assertIsInstance(step_result, CoreStepRunResult)
        self.assertEqual(TaskStatus.SUCCESS, step_result.status)
        self.assertEqual(TaskId.SEND_ALLIANCE_CHAT_MESSAGE, step_result.task_id)
        self.assertTrue(step_result.workflow_result.succeeded)
        self.assertEqual("send_alliance_chat", step_result.workflow_result.workflow_name)
        self.assertEqual(ScreenType.PNC_HOME_CITY, step_result.workflow_result.exit_screen)
        self.assertEqual(ChatChannel.ALLIANCE, step_result.workflow_result.value.channel)
        self.assertEqual(message, step_result.workflow_result.value.message)
        self.assertEqual(1, step_result.workflow_result.value.receipt_count)
        self.assertTrue(step_result.workflow_result.value.sent_proof)
        self.assertEqual(ScreenType.PNC_HOME_CITY, runtime.last_observation.screen_type)
        self.assertEqual(16, runtime.observation_count)

        submitted = [
            action
            for action in runtime.actuator.actions
            if isinstance(action, TapAction)
            and action.selector_id == UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON
        ]
        typed = [action for action in runtime.actuator.actions if isinstance(action, InputTextAction)]
        self.assertEqual(1, len(submitted))
        self.assertEqual(1, len(typed))
        self.assertEqual(message, typed[0].text)
        self.assertFalse(typed[0].replace_existing)

    def test_default_registry_uses_canonical_mail_parser(self) -> None:
        """Registers authored mail as an optional typed step with the shared domain parser."""

        definition = build_default_task_registry().require(TaskId.COLLECT_MAIL)

        self.assertIsInstance(definition, CoreWorkflowTaskDefinition)
        self.assertEqual(definition.castle_target_policy, CastleTargetPolicy.OPTIONAL)
        self.assertEqual(
            CollectMailParams(
                mailboxes=(MailboxType.PLAYER, MailboxType.ALLIANCE),
                archive_mode=MailArchiveMode.TEXT,
                limit_per_mailbox=2,
                only_new=False,
            ),
            definition.parse_params(
                {
                    "mailboxes": ["player", "alliance", "player"],
                    "archive_mode": "text",
                    "limit_per_mailbox": 2,
                    "only_new": False,
                }
            ),
        )

    def test_default_registry_uses_typed_open_building_definition(self) -> None:
        """Registers authored open-building with the canonical policy parser and optional target."""

        definition = build_default_task_registry().require(TaskId.OPEN_BUILDING)

        self.assertIsInstance(definition, CoreWorkflowTaskDefinition)
        self.assertEqual(definition.castle_target_policy, CastleTargetPolicy.OPTIONAL)
        self.assertEqual(
            OpenBuildingPolicy(building=HomeCityObjectId.CASTLE),
            definition.parse_params({"building": HomeCityObjectId.CASTLE.value}),
        )
        with self.assertRaises(AttributeError):
            definition.id = TaskId.COLLECT_MAIL  # type: ignore[misc]

    def test_script_runner_rejects_unmodeled_open_building_before_connection(self) -> None:
        """Rejects a legacy-only generic building endpoint during typed pre-connect validation."""

        script_runner = _minimal_script_runner(archive_store=None)
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaisesRegex(ScriptValidationError, "no modeled primary screen"):
                script_runner._run_script_for_account(
                    account=_account(),
                    script=_run_open_building_script(building=HomeCityObjectId.BANK.value),
                )

        build_runner.assert_not_called()

    def test_dispatcher_rejects_malformed_open_building_policy_before_connection(self) -> None:
        """Rejects an unparsed authored policy without constructing the connected runtime."""

        for malformed_params in (None, {"building": HomeCityObjectId.CASTLE.value}):
            with self.subTest(malformed_params=malformed_params):
                runtime_factory = Mock()
                dispatcher = CoreScriptDispatcher(
                    account=_account(),
                    chat_archive_store=None,
                    core_runtime_factory=runtime_factory,
                )

                with self.assertRaisesRegex(
                    RuntimeError,
                    "Typed Open Building dispatch requires parsed OpenBuildingPolicy",
                ):
                    dispatcher.execute(
                        step=replace(
                            _prepared_open_building_step(),
                            parsed_params=malformed_params,
                        )
                    )

                runtime_factory.assert_not_called()

    def test_script_runner_validates_open_building_without_archive_dependencies(self) -> None:
        """Accepts a supported typed open-building step without mail, Chat, or roster storage."""

        script_runner = _minimal_script_runner(
            archive_store=None,
            mail_archive_store=None,
            castle_roster_store=None,
        )
        prepared = script_runner.task_registry.prepare_script(
            _run_open_building_script(building=HomeCityObjectId.CASTLE.value)
        ).steps

        script_runner._validate_core_script_dependencies(prepared)

    def test_default_registry_uses_immutable_parameterless_roster_definition(self) -> None:
        """Registers roster refresh as an untargeted typed core step."""

        definition = build_default_task_registry().require(TaskId.REFRESH_CASTLE_ROSTER)

        self.assertIsInstance(definition, CoreWorkflowTaskDefinition)
        self.assertEqual(definition.castle_target_policy, CastleTargetPolicy.DISALLOWED)
        self.assertIsNone(definition.parse_params({}))
        with self.assertRaisesRegex(Exception, "does not accept"):
            definition.parse_params({"unexpected": True})
        with self.assertRaises(AttributeError):
            definition.id = TaskId.COLLECT_MAIL  # type: ignore[misc]

    def test_registry_rejects_roster_castle_target_before_dispatch(self) -> None:
        """Rejects a forbidden explicit castle target while preparing the script."""

        script = RunScript(
            name="roster",
            path=Path("roster.yaml"),
            steps=(
                ScriptStep(
                    task=TaskId.REFRESH_CASTLE_ROSTER,
                    castle=CastleIdentity("K1", "Castle", 12),
                ),
            ),
        )

        with self.assertRaisesRegex(Exception, "does not accept"):
            build_default_task_registry().prepare_script(script)

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

    def test_script_runner_builds_mixed_steps_over_one_connected_graph(self) -> None:
        """Wires both dispatch paths to one connected service graph and one owner close."""

        events: list[str] = []
        observation_service = Mock()
        observation_service.observe.side_effect = lambda label, **_kwargs: (
            events.append(f"observe:{label}") or Mock()
        )
        observed_action_executor = Mock()
        observed_action_executor.recover_interruption_if_required.return_value = None
        core_executor = Mock()
        core_executor.execute.side_effect = lambda **_kwargs: (
            events.append("core") or _workflow_result()
        )
        connected_runtime = SimpleNamespace(
            session=SimpleNamespace(
                instance=BlueStacksInstance(
                    id="instance",
                    display_name="display",
                    device_id="device",
                    app_package="package",
                )
            ),
            observation_service=observation_service,
            flow_planner=Mock(),
            world_map_survey_recorder=None,
            world_map_search_service=None,
            close=Mock(side_effect=lambda: events.append("close")),
            require_observed_action_executor=Mock(return_value=observed_action_executor),
        )
        script_runner = _minimal_script_runner(archive_store=Mock(spec=ChatArchiveStore))
        script_runner.config.defaults = DefaultsConfig()
        script_runner.logger = build_logger()
        registry = TaskRegistry(
            tasks=(
                _LegacyNoOpTask(events),
                CoreWorkflowTaskDefinition(
                    id=TaskId.COLLECT_KINGDOM_CHAT,
                    castle_target_policy=CastleTargetPolicy.OPTIONAL,
                    parameter_parser=lambda params: require_no_params(TaskId.COLLECT_KINGDOM_CHAT, params),
                ),
            )
        )

        script_runner.task_registry = registry
        script = registry.prepare_script(
            RunScript(
                name="mixed",
                path=Path("mixed.yaml"),
                steps=(
                    ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
                    ScriptStep(task=TaskId.COLLECT_KINGDOM_CHAT),
                ),
            )
        )

        with patch.object(ScriptRunner, "_build_core_step_executor", return_value=core_executor) as build_core:
            runner = script_runner._build_automation_runner_from_services(
                account=_account(),
                connected_runtime=connected_runtime,
            )
        runner.run(_account(), script)
        runner.close()

        build_core.assert_called_once_with(
            account=_account(),
            connected_runtime=connected_runtime,
            required_role=LiveAutomationRole.LIVE_TESTING,
            mutation_boundary=None,
        )
        self.assertEqual(["observe:ensure_game_running_before", "legacy", "core", "close"], events)
        connected_runtime.require_observed_action_executor.assert_called_once()
        connected_runtime.close.assert_called_once_with()
        self.assertEqual(1, observation_service.observe.call_count)

    def test_default_registry_uses_parameterless_lifecycle_definition(self) -> None:
        """Registers readiness as a castle-independent typed lifecycle operation."""

        definition = build_default_task_registry().require(TaskId.ENSURE_GAME_RUNNING)

        self.assertIsInstance(definition, CoreWorkflowTaskDefinition)
        self.assertEqual(definition.castle_target_policy, CastleTargetPolicy.DISALLOWED)
        self.assertIsNone(definition.parse_params({}))
        with self.assertRaisesRegex(Exception, "does not accept"):
            definition.parse_params({"unexpected": True})

    def test_default_registry_uses_typed_popup_recovery_definition(self) -> None:
        """Registers popup recovery as a castle-independent parameterless lifecycle operation."""

        definition = build_default_task_registry().require(TaskId.POPUP_RECOVERY)

        self.assertIsInstance(definition, CoreWorkflowTaskDefinition)
        self.assertEqual(definition.castle_target_policy, CastleTargetPolicy.DISALLOWED)
        self.assertIsNone(definition.parse_params({}))
        with self.assertRaisesRegex(Exception, "does not accept"):
            definition.parse_params({"unexpected": True})
        with self.assertRaises(AttributeError):
            definition.id = TaskId.ENSURE_GAME_RUNNING  # type: ignore[misc]

    def test_dispatcher_lifecycle_step_proves_readiness_without_identity_or_store(self) -> None:
        """Runs lifecycle readiness on the shared core graph without castle preflight or archive access."""

        captured_at = datetime(2026, 9, 12, 5, 0, tzinfo=UTC)
        observation = Observation(
            screen_type=ScreenType.PNC_LOGIN,
            visible_elements={},
            captured_at=captured_at,
            artifact_path=Path("ready.png"),
        )
        core_runtime = Mock()
        core_runtime.ensure_game_ready.return_value = observation
        core_runtime.trace_path = Path("trace.jsonl")
        runtime_factory = Mock(return_value=core_runtime)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=runtime_factory,
        )

        result = dispatcher.execute(step=_prepared_ensure_step())

        self.assertTrue(result.succeeded)
        self.assertEqual(TaskId.ENSURE_GAME_RUNNING.value, result.workflow_name)
        self.assertEqual(
            GameReadyResult(ScreenType.PNC_LOGIN, captured_at, Path("ready.png")),
            result.value,
        )
        self.assertEqual(ScreenType.PNC_LOGIN, result.exit_screen)
        core_runtime.ensure_game_ready.assert_called_once_with()
        core_runtime.preflight_active_castle_identity.assert_not_called()
        runtime_factory.assert_called_once_with()
        core_runtime.close.assert_not_called()

    def test_dispatcher_lifecycle_failure_does_not_fallback_or_close_shared_runtime(self) -> None:
        """Propagates readiness failure without invoking identity preflight, legacy execution, or close."""

        core_runtime = Mock()
        core_runtime.ensure_game_ready.side_effect = RuntimeError("unknown startup screen")
        core_runtime.trace_path = Path("trace.jsonl")
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=Mock(return_value=core_runtime),
        )

        with self.assertRaisesRegex(RuntimeError, "unknown startup screen"):
            dispatcher.execute(step=_prepared_ensure_step())

        core_runtime.ensure_game_ready.assert_called_once_with()
        core_runtime.preflight_active_castle_identity.assert_not_called()
        core_runtime.close.assert_not_called()

    def test_dispatcher_popup_recovery_uses_lifecycle_boundary_without_identity_or_store(self) -> None:
        """Dispatches popup recovery directly through CoreRuntime without foreground or castle preflight."""

        captured_at = datetime(2026, 9, 12, 5, 0, tzinfo=UTC)
        observation = Observation(
            screen_type=ScreenType.PNC_HOME_CITY,
            visible_elements={},
            captured_at=captured_at,
            artifact_path=Path("recovered.png"),
        )
        core_runtime = Mock()
        core_runtime.recover_popup.return_value = observation
        core_runtime.trace_path = Path("trace.jsonl")
        runtime_factory = Mock(return_value=core_runtime)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=runtime_factory,
        )

        result = dispatcher.execute(step=_prepared_popup_step())

        self.assertTrue(result.succeeded)
        self.assertEqual(TaskId.POPUP_RECOVERY.value, result.workflow_name)
        self.assertEqual(
            GameReadyResult(ScreenType.PNC_HOME_CITY, captured_at, Path("recovered.png")),
            result.value,
        )
        core_runtime.recover_popup.assert_called_once_with()
        core_runtime.ensure_game_ready.assert_not_called()
        core_runtime.preflight_active_castle_identity.assert_not_called()
        core_runtime.close.assert_not_called()

    def test_dispatcher_popup_failure_does_not_fallback_or_close_shared_runtime(self) -> None:
        """Propagates popup recovery failure without invoking another lifecycle or legacy path."""

        core_runtime = Mock()
        core_runtime.recover_popup.side_effect = RuntimeError("popup recovery budget exhausted")
        core_runtime.trace_path = Path("trace.jsonl")
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=Mock(return_value=core_runtime),
        )

        with self.assertRaisesRegex(RuntimeError, "popup recovery budget exhausted"):
            dispatcher.execute(step=_prepared_popup_step())

        core_runtime.recover_popup.assert_called_once_with()
        core_runtime.ensure_game_ready.assert_not_called()
        core_runtime.preflight_active_castle_identity.assert_not_called()
        core_runtime.close.assert_not_called()

    def test_script_runner_rejects_popup_params_before_connection(self) -> None:
        """Rejects authored popup parameters before constructing a connected runner."""

        script_runner = _minimal_script_runner(archive_store=None)
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaisesRegex(Exception, "does not accept"):
                script_runner._run_script_for_account(
                    account=_account(),
                    script=_run_popup_script(params={"unexpected": True}),
                )

        build_runner.assert_not_called()

    def test_script_runner_rejects_popup_castle_target_before_connection(self) -> None:
        """Rejects a castle target on the castle-independent popup lifecycle step before connect."""

        script_runner = _minimal_script_runner(archive_store=None)
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaisesRegex(Exception, "does not accept"):
                script_runner._run_script_for_account(
                    account=_account(),
                    script=_run_popup_script(
                        params={},
                        castle=CastleIdentity("K1", "Castle", 12),
                    ),
                )

        build_runner.assert_not_called()

    def test_script_runner_accepts_lifecycle_step_without_archive_before_connection(self) -> None:
        """Validates parameterless lifecycle preparation without requiring a workflow store."""

        script_runner = _minimal_script_runner(archive_store=None)
        fake_runner = Mock()
        fake_runner.run.return_value = Mock()

        with patch.object(
            ScriptRunner,
            "_build_runner",
            return_value=(fake_runner, lambda: None),
        ) as build_runner:
            script_runner._run_script_for_account(
                account=_account(),
                script=_run_ensure_script(params={}),
            )

        build_runner.assert_called_once()
        fake_runner.close.assert_called_once_with()

    def test_script_runner_rejects_lifecycle_params_before_connection(self) -> None:
        """Rejects authored lifecycle parameters before constructing a connected runner."""

        script_runner = _minimal_script_runner(archive_store=None)
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaisesRegex(Exception, "does not accept"):
                script_runner._run_script_for_account(
                    account=_account(),
                    script=_run_ensure_script(params={"unexpected": True}),
                )

        build_runner.assert_not_called()

    def test_explicit_castle_is_asserted_without_legacy_alignment_before_core_dispatch(self) -> None:
        """Routes typed steps directly to the core executor without legacy observation or alignment."""

        executor = Mock()
        executor.execute.return_value = _workflow_result()
        observation_service = Mock()
        runner = _make_runner(observation_service=observation_service, core_step_executor=executor)
        step = _prepared_chat_step(castle=CastleIdentity("K1", "Castle", 12))

        with patch.object(AutomationRunner, "_align_step_castle_target", return_value=None) as align:
            runner.run(_account(), PreparedRunScript(name="chat", path=Path("chat.yaml"), steps=(step,)))

        observation_service.observe.assert_not_called()
        align.assert_not_called()
        executor.execute.assert_called_once_with(step=step)

    def test_real_dispatcher_rejects_typed_target_mismatch_without_legacy_actions(self) -> None:
        """Lets the real dispatcher reject a typed target while the runner performs no legacy work."""

        active = CastleIdentity("K1", "Active", 12)
        requested = CastleIdentity("K2", "Requested", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        runtime_factory = Mock(return_value=core_runtime)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=runtime_factory,
        )
        observation_service = Mock()
        runner = _make_runner(observation_service=observation_service, core_step_executor=dispatcher)
        step = _prepared_alliance_chat_step(castle=requested)

        with patch.object(AutomationRunner, "_align_step_castle_target") as align:
            with self.assertRaisesRegex(RuntimeError, "requested castle target"):
                runner.run(
                    _account(),
                    PreparedRunScript(name="chat", path=Path("chat.yaml"), steps=(step,)),
                )

        observation_service.observe.assert_not_called()
        runner.action_executor.execute_actions.assert_not_called()
        align.assert_not_called()
        runtime_factory.assert_called_once_with()
        core_runtime.preflight_active_castle_identity.assert_called_once_with()

    def test_real_dispatcher_delegates_matching_typed_target_without_legacy_actions(self) -> None:
        """Delegates a matching typed target to the real dispatcher after one exact preflight."""

        active = CastleIdentity("K1", "Active", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        runtime_factory = Mock(return_value=core_runtime)
        workflow_runner = Mock()
        workflow_runner.run.return_value = _workflow_result()
        runner_factory = Mock(return_value=workflow_runner)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=runtime_factory,
        )
        observation_service = Mock()
        runner = _make_runner(observation_service=observation_service, core_step_executor=dispatcher)
        step = _prepared_alliance_chat_step(castle=active)

        with patch(
            "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
            runner_factory,
        ):
            with patch.object(AutomationRunner, "_align_step_castle_target") as align:
                result = runner.run(
                    _account(),
                    PreparedRunScript(name="chat", path=Path("chat.yaml"), steps=(step,)),
                )

        observation_service.observe.assert_not_called()
        runner.action_executor.execute_actions.assert_not_called()
        align.assert_not_called()
        runtime_factory.assert_called_once_with()
        core_runtime.preflight_active_castle_identity.assert_called_once_with()
        workflow_runner.run.assert_called_once()
        workflow = workflow_runner.run.call_args.args[0]
        self.assertIsInstance(workflow, SendChatWorkflow)
        self.assertEqual(ChatChannel.ALLIANCE, workflow.channel)
        self.assertEqual(TaskStatus.SUCCESS, result.steps[0].status)
        self.assertEqual(active, result.steps[0].requested_castle)

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

    def test_dispatcher_rejects_missing_mail_archive_before_composition(self) -> None:
        """Rejects typed mail before core assembly when only the Chat archive exists."""

        runtime_factory = Mock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            dispatcher = CoreScriptDispatcher(
                account=_account(),
                chat_archive_store=ChatArchiveStore(Path(temporary_directory) / "chat"),
                mail_archive_store=None,
                core_runtime_factory=runtime_factory,
            )

            with self.assertRaisesRegex(RuntimeError, "MailArchiveStore"):
                dispatcher.execute(step=_prepared_mail_step())

        runtime_factory.assert_not_called()

    def test_dispatcher_rejects_missing_roster_store_before_composition(self) -> None:
        """Fails before core assembly when an authored roster step lacks its store."""

        runtime_factory = Mock()
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            mail_archive_store=None,
            castle_roster_store=None,
            core_runtime_factory=runtime_factory,
        )

        with self.assertRaisesRegex(RuntimeError, "CastleRosterStore"):
            dispatcher.execute(step=_prepared_roster_step())

        runtime_factory.assert_not_called()

    def test_dispatcher_refresh_roster_uses_canonical_store_without_mail_or_chat(self) -> None:
        """Preflights once and builds the existing typed roster workflow from its own store."""

        active = CastleIdentity("K1", "Castle", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        typed_result = CoreWorkflowResult(
            workflow_name="refresh_castle_roster",
            succeeded=True,
            value=RefreshCastleRosterResult(
                castles=(active,),
                captured_at=datetime(2026, 9, 12, tzinfo=UTC),
            ),
            exit_screen=ScreenType.PNC_HOME_CITY,
            trace_path="trace.jsonl",
        )
        workflow_runner = Mock()
        workflow_runner.run.return_value = typed_result
        runtime_factory = Mock(return_value=core_runtime)
        runner_factory = Mock(return_value=workflow_runner)
        with tempfile.TemporaryDirectory() as temporary_directory:
            roster_store = CastleRosterStore(Path(temporary_directory) / "castles.yaml")
            dispatcher = CoreScriptDispatcher(
                account=_account(),
                chat_archive_store=None,
                mail_archive_store=None,
                castle_roster_store=roster_store,
                core_runtime_factory=runtime_factory,
            )
            with patch(
                "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
                runner_factory,
            ):
                result = dispatcher.execute(step=_prepared_roster_step())

        self.assertIs(typed_result, result)
        workflow = workflow_runner.run.call_args.args[0]
        self.assertIsInstance(workflow, RefreshCastleRosterWorkflow)
        self.assertEqual("account", workflow.account_id)
        self.assertEqual("pnc-account", workflow.pnc_account_id)
        self.assertIs(active, workflow.active_castle)
        self.assertIs(roster_store, workflow.roster_store)
        runtime_factory.assert_called_once_with()
        core_runtime.preflight_active_castle_identity.assert_called_once_with()
        core_runtime.close.assert_not_called()

    def test_script_runner_rejects_roster_without_store_before_connection(self) -> None:
        """Validates roster persistence before constructing a connected runner."""

        script_runner = _minimal_script_runner(archive_store=None, castle_roster_store=None)
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaisesRegex(RuntimeError, "CastleRosterStore"):
                script_runner._run_script_for_account(
                    account=_account(),
                    script=_run_roster_script(),
                )

        build_runner.assert_not_called()

    def test_script_runner_builds_roster_dispatcher_without_mail_or_chat(self) -> None:
        """Keeps roster dispatch independent from the mail and Chat archive stores."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            roster_store = CastleRosterStore(Path(temporary_directory) / "castles.yaml")
            script_runner = _minimal_script_runner(
                archive_store=None,
                mail_archive_store=None,
                castle_roster_store=roster_store,
            )
            dispatcher = script_runner._build_core_step_executor(
                account=_account(),
                connected_runtime=SimpleNamespace(),
                required_role=LiveAutomationRole.LIVE_TESTING,
            )

        self.assertIsInstance(dispatcher, CoreScriptDispatcher)
        self.assertIs(roster_store, dispatcher.castle_roster_store)  # type: ignore[union-attr]
        self.assertIsNone(dispatcher.chat_archive_store)  # type: ignore[union-attr]
        self.assertIsNone(dispatcher.mail_archive_store)  # type: ignore[union-attr]

    def test_dispatcher_collect_mail_uses_mail_store_without_chat_store(self) -> None:
        """Builds the canonical typed mail workflow from the mail store alone."""

        active = CastleIdentity("K1", "Castle", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        typed_result = CoreWorkflowResult(
            workflow_name="collect_mail",
            succeeded=True,
            value=CollectMailResult(
                mailboxes=(
                    _mailbox_result(MailboxType.PLAYER),
                )
            ),
            exit_screen=ScreenType.PNC_HOME_CITY,
            trace_path="trace.jsonl",
        )
        workflow_runner = Mock()
        workflow_runner.run.return_value = typed_result
        runtime_factory = Mock(return_value=core_runtime)
        runner_factory = Mock(return_value=workflow_runner)
        with tempfile.TemporaryDirectory() as temporary_directory:
            mail_store = MailArchiveStore(Path(temporary_directory) / "mail")
            dispatcher = CoreScriptDispatcher(
                account=_account(),
                chat_archive_store=None,
                mail_archive_store=mail_store,
                core_runtime_factory=runtime_factory,
            )
            with patch(
                "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
                runner_factory,
            ):
                result = dispatcher.execute(step=_prepared_mail_step())

        self.assertIs(typed_result, result)
        workflow = workflow_runner.run.call_args.args[0]
        self.assertIsInstance(workflow, CollectMailWorkflow)
        self.assertEqual(_mail_params(), workflow.params)
        self.assertEqual("Castle", workflow.active_castle)
        self.assertIs(mail_store, workflow.archive_store)
        runtime_factory.assert_called_once_with()
        core_runtime.close.assert_not_called()

    def test_dispatcher_open_building_uses_typed_workflow_without_stores(self) -> None:
        """Builds the canonical open-building workflow after exact active-castle preflight."""

        active = CastleIdentity("K1", "Castle", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        typed_result = CoreWorkflowResult(
            workflow_name="open_building",
            succeeded=True,
            value=OpenBuildingResult(
                building=HomeCityObjectId.CASTLE,
                screen_type=ScreenType.PNC_CASTLE,
                captured_at=datetime(2026, 9, 12, tzinfo=UTC),
            ),
            exit_screen=ScreenType.PNC_CASTLE,
            trace_path="trace.jsonl",
        )
        workflow_runner = Mock()
        workflow_runner.run.return_value = typed_result
        runtime_factory = Mock(return_value=core_runtime)
        runner_factory = Mock(return_value=workflow_runner)
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            mail_archive_store=None,
            castle_roster_store=None,
            core_runtime_factory=runtime_factory,
        )

        with patch(
            "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
            runner_factory,
        ):
            result = dispatcher.execute(step=_prepared_open_building_step())

        self.assertIs(typed_result, result)
        workflow = workflow_runner.run.call_args.args[0]
        self.assertIsInstance(workflow, OpenBuildingWorkflow)
        self.assertEqual(OpenBuildingPolicy(HomeCityObjectId.CASTLE), workflow.policy)
        core_runtime.preflight_active_castle_identity.assert_called_once_with()
        runtime_factory.assert_called_once_with()
        core_runtime.close.assert_not_called()

    def test_dispatcher_open_building_rejects_requested_castle_mismatch(self) -> None:
        """Rejects a typed open-building step when exact preflight identity differs from its target."""

        active = CastleIdentity("K1", "Active", 12)
        requested = CastleIdentity("K2", "Requested", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        runtime_factory = Mock(return_value=core_runtime)
        runner_factory = Mock()
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=runtime_factory,
        )

        with patch(
            "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
            runner_factory,
        ):
            with self.assertRaisesRegex(RuntimeError, "requested castle target"):
                dispatcher.execute(step=_prepared_open_building_step(castle=requested))

        core_runtime.preflight_active_castle_identity.assert_called_once_with()
        runner_factory.assert_not_called()
        core_runtime.close.assert_not_called()

    def test_dispatcher_open_building_preserves_core_route_guard_without_legacy_fallback(self) -> None:
        """Propagates a mapped endpoint's missing reviewed route without replaying through legacy dispatch."""

        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = CastleIdentity("K1", "Active", 12)
        core_runtime.trace_path = Path("trace.jsonl")
        core_runtime.navigation.navigate.return_value = Observation(
            screen_type=ScreenType.PNC_HOME_CITY,
            visible_elements={},
            captured_at=datetime(2026, 9, 12, tzinfo=UTC),
        )
        core_runtime.navigation.open_building.side_effect = RuntimeError("no reviewed navigation route")
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=Mock(return_value=core_runtime),
        )

        with self.assertRaisesRegex(RuntimeError, "no reviewed navigation route"):
            dispatcher.execute(
                step=_prepared_open_building_step(
                    policy=OpenBuildingPolicy(HomeCityObjectId.SANCTUM),
                )
            )

        core_runtime.navigation.open_building.assert_called_once()
        core_runtime.close.assert_not_called()

    def test_dispatcher_collect_mail_requires_active_castle_before_workflow(self) -> None:
        """Fails before workflow construction when typed mail cannot prove active identity."""

        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.side_effect = RuntimeError("identity absent")
        runtime_factory = Mock(return_value=core_runtime)
        with tempfile.TemporaryDirectory() as temporary_directory:
            dispatcher = CoreScriptDispatcher(
                account=_account(),
                chat_archive_store=None,
                mail_archive_store=MailArchiveStore(Path(temporary_directory) / "mail"),
                core_runtime_factory=runtime_factory,
            )
            with patch(
                "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
            ) as runner_factory:
                with self.assertRaisesRegex(RuntimeError, "identity absent"):
                    dispatcher.execute(step=_prepared_mail_step())

        runner_factory.assert_not_called()
        core_runtime.close.assert_not_called()

    def test_script_runner_builds_mail_dispatcher_when_chat_store_is_absent(self) -> None:
        """Keeps the typed dispatcher available for mail-only configurations."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            mail_store = MailArchiveStore(Path(temporary_directory) / "mail")
            script_runner = _minimal_script_runner(
                archive_store=None,
                mail_archive_store=mail_store,
            )
            dispatcher = script_runner._build_core_step_executor(
                account=_account(),
                connected_runtime=SimpleNamespace(),
                required_role=LiveAutomationRole.LIVE_TESTING,
            )

        self.assertIsInstance(dispatcher, CoreScriptDispatcher)
        self.assertIs(mail_store, dispatcher.mail_archive_store)  # type: ignore[union-attr]
        self.assertIsNone(dispatcher.chat_archive_store)  # type: ignore[union-attr]

    def test_dispatcher_rejects_unsupported_task_before_composition(self) -> None:
        """Fails closed for a task without a typed dispatcher before assembling core services."""

        runtime_factory = Mock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            dispatcher = CoreScriptDispatcher(
                account=_account(),
                chat_archive_store=ChatArchiveStore(Path(temporary_directory) / "chat"),
                core_runtime_factory=runtime_factory,
            )
            unsupported = PreparedScriptStep(
                script_step=ScriptStep(task=TaskId.SEND_MAIL),
                parsed_params=None,
                castle_target_policy=CastleTargetPolicy.OPTIONAL,
            )

            with self.assertRaisesRegex(RuntimeError, "No typed core dispatcher"):
                dispatcher.execute(step=unsupported)

        runtime_factory.assert_not_called()

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

    def test_alliance_dispatcher_rejects_requested_castle_mismatch(self) -> None:
        """Applies the same exact active-castle guard to the typed Alliance send."""

        active = CastleIdentity("K1", "Active", 12)
        requested = CastleIdentity("K1", "Requested", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        runner_factory = Mock()
        dispatcher = CoreScriptDispatcher(
            account=_account(),
            chat_archive_store=None,
            core_runtime_factory=Mock(return_value=core_runtime),
        )

        with patch(
            "pnc_automation.app.automation.engine.core_script_dispatcher.CoreWorkflowRunner",
            runner_factory,
        ):
            with self.assertRaisesRegex(RuntimeError, "requested castle target"):
                dispatcher.execute(step=_prepared_alliance_chat_step(castle=requested))

        core_runtime.preflight_active_castle_identity.assert_called_once_with()
        runner_factory.assert_not_called()
        core_runtime.close.assert_not_called()

    def test_dispatcher_accepts_valid_exact_castle_match(self) -> None:
        """Executes a targeted typed step only after exact active-castle confirmation."""

        active = CastleIdentity("K1", "Requested", 12)
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        workflow_result = _workflow_result()
        workflow_runner = Mock()
        workflow_runner.run.return_value = workflow_result
        runtime_factory = Mock(return_value=core_runtime)
        runner_factory = Mock(return_value=workflow_runner)
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
                result = dispatcher.execute(step=_prepared_chat_step(castle=active))

        self.assertIs(workflow_result, result)
        core_runtime.preflight_active_castle_identity.assert_called_once_with()
        workflow_runner.run.assert_called_once()
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

        policy = BlueStacksSessionCleanupPolicy.close_at_phase_end(shutdown_grace_seconds=0)
        with tempfile.TemporaryDirectory() as temporary_directory:
            script_runner = _minimal_script_runner(
                archive_store=ChatArchiveStore(Path(temporary_directory) / "chat"),
            )
            fake_runner = Mock()
            fake_runner.run.return_value = Mock()
            with patch.object(ScriptRunner, "_build_runner", return_value=(fake_runner, lambda: None)) as build_runner:
                script_runner._run_script_for_account(
                    account=account,
                    script=_run_script(params={}),
                    required_role=LiveAutomationRole.SMOKE_TEST,
                    session_cleanup_policy=policy,
                )
            build_runner.assert_called_once_with(
                account,
                required_role=LiveAutomationRole.SMOKE_TEST,
                session_cleanup_policy=policy,
                mutation_boundary=None,
            )

            invalid = _minimal_script_runner(
                archive_store=ChatArchiveStore(Path(temporary_directory) / "invalid-chat"),
            )
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaisesRegex(Exception, "does not accept"):
                invalid._run_script_for_account(account=account, script=_run_script(params={"unexpected": True}))
            build_runner.assert_not_called()

    def test_script_runner_rejects_mail_without_archive_before_connection(self) -> None:
        """Validates authored mail dependencies before constructing a connected runner."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            script_runner = _minimal_script_runner(
                archive_store=ChatArchiveStore(Path(temporary_directory) / "chat"),
                mail_archive_store=None,
            )
            with patch.object(ScriptRunner, "_build_runner") as build_runner:
                with self.assertRaisesRegex(RuntimeError, "MailArchiveStore"):
                    script_runner._run_script_for_account(
                        account=_account(),
                        script=_run_mail_script(),
                    )

            build_runner.assert_not_called()

    def test_script_runner_closes_runner_when_core_execution_fails(self) -> None:
        """Closes the connected owner after a typed script fails during execution."""

        account = _account()
        with tempfile.TemporaryDirectory() as temporary_directory:
            script_runner = _minimal_script_runner(
                archive_store=ChatArchiveStore(Path(temporary_directory) / "chat"),
            )
            fake_runner = Mock()
            fake_runner.run.side_effect = RuntimeError("core execution failed")
            with patch.object(
                ScriptRunner,
                "_build_runner",
                return_value=(fake_runner, lambda: None),
            ):
                with self.assertRaisesRegex(RuntimeError, "core execution failed"):
                    script_runner._run_script_for_account(account=account, script=_run_script(params={}))

        fake_runner.close.assert_called_once_with()

    def test_core_runtime_construction_failure_closes_connected_owner(self) -> None:
        """Closes the connected graph when core assembly fails after session construction."""

        connected_runtime = Mock()
        script_runner = Mock()
        account = _account()
        script_runner.build_connected_runtime.return_value = connected_runtime
        with patch(
            "pnc_automation.app.automation.engine.core_runtime.assemble_core_runtime",
            side_effect=RuntimeError("core assembly failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "core assembly failed"):
                build_core_runtime(script_runner, account, "account")

        connected_runtime.close.assert_called_once_with()
        script_runner.build_connected_runtime.assert_called_once_with(
            account=account,
            required_role=None,
            session_cleanup_policy=None,
        )

    def test_cli_run_serializer_emits_typed_core_result_contract(self) -> None:
        """Serializes the retained typed workflow result through the actual CLI JSON path."""

        now = datetime.now(tz=UTC)
        result = RunResult(
            account_id="account",
            script_name="chat",
            steps=(
                CoreStepRunResult(
                    task_id=TaskId.COLLECT_KINGDOM_CHAT,
                    status=TaskStatus.SUCCESS,
                    attempts=1,
                    message="completed",
                    workflow_result=_workflow_result(),
                ),
            ),
            started_at=now,
            finished_at=now,
        )

        payload = json.loads(_serialize_run_result(result))

        self.assertEqual("account", payload["account_id"])
        self.assertEqual("collect_kingdom_chat", payload["steps"][0]["task_id"])
        self.assertEqual("collect_kingdom_chat", payload["steps"][0]["workflow_result"]["workflow_name"])
        self.assertTrue(payload["steps"][0]["workflow_result"]["succeeded"])


def _account(*, roles: frozenset[LiveAutomationRole] | None = None) -> AccountConfig:
    """Builds one offline account binding with the requested live roles."""

    return AccountConfig(
        id="account",
        instance_id="instance",
        pnc_account_id="pnc-account",
        live_roles=frozenset({LiveAutomationRole.LIVE_TESTING}) if roles is None else roles,
    )


class _LegacyNoOpTask(BaseAutomationTask):
    """Small legacy task used to prove mixed dispatch ordering."""

    id = TaskId.ENSURE_GAME_RUNNING

    def __init__(self, events: list[str]) -> None:
        self._events = events

    def parse_params(self, params):
        require_no_params(self.id, params)
        return None

    def is_applicable(self, context, observation) -> bool:
        del context, observation
        self._events.append("legacy")
        return True

    def plan(self, context, observation):
        del context, observation
        return []

    def verify(self, context, before, after):
        del context, before, after
        return TaskResult.success("legacy complete")


def _prepared_chat_step(*, castle: CastleIdentity | None = None) -> PreparedScriptStep:
    """Builds one already-prepared typed Chat step."""

    script_step = ScriptStep(task=TaskId.COLLECT_KINGDOM_CHAT, castle=castle)
    return PreparedScriptStep(
        script_step=script_step,
        parsed_params=None,
        castle_target_policy=CastleTargetPolicy.OPTIONAL,
        resolved_castle=castle,
    )


def _prepared_select_step(target: CastleIdentity | None) -> PreparedScriptStep:
    """Builds one prepared typed Select Castle step for dispatcher validation tests."""

    script_step = ScriptStep(task=TaskId.SELECT_CASTLE, castle=target)
    return PreparedScriptStep(
        script_step=script_step,
        parsed_params=None,
        castle_target_policy=CastleTargetPolicy.REQUIRED,
        resolved_castle=target,
    )


def _prepared_world_chat_step(*, castle: CastleIdentity | None = None) -> PreparedScriptStep:
    """Builds one already-prepared typed World Chat send step."""

    script_step = ScriptStep(task=TaskId.SEND_WORLD_CHAT_MESSAGE, castle=castle)
    return PreparedScriptStep(
        script_step=script_step,
        parsed_params=ChatMessageTaskParams(message="hello"),
        castle_target_policy=CastleTargetPolicy.OPTIONAL,
        resolved_castle=castle,
    )


def _prepared_alliance_chat_step(*, castle: CastleIdentity | None = None) -> PreparedScriptStep:
    """Builds one already-prepared typed Alliance Chat send step."""

    script_step = ScriptStep(task=TaskId.SEND_ALLIANCE_CHAT_MESSAGE, castle=castle)
    return PreparedScriptStep(
        script_step=script_step,
        parsed_params=ChatMessageTaskParams(message="hello"),
        castle_target_policy=CastleTargetPolicy.OPTIONAL,
        resolved_castle=castle,
    )


def _prepared_roster_step() -> PreparedScriptStep:
    """Builds one already-prepared parameterless typed roster step."""

    return PreparedScriptStep(
        script_step=ScriptStep(task=TaskId.REFRESH_CASTLE_ROSTER),
        parsed_params=None,
        castle_target_policy=CastleTargetPolicy.DISALLOWED,
        resolved_castle=None,
    )


def _prepared_ensure_step(*, params: object | None = None) -> PreparedScriptStep:
    """Builds one already-prepared parameterless lifecycle step."""

    return PreparedScriptStep(
        script_step=ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
        parsed_params=params,
        castle_target_policy=CastleTargetPolicy.DISALLOWED,
    )


def _prepared_popup_step(*, params: object | None = None) -> PreparedScriptStep:
    """Builds one already-prepared parameterless popup lifecycle step."""

    return PreparedScriptStep(
        script_step=ScriptStep(task=TaskId.POPUP_RECOVERY),
        parsed_params=params,
        castle_target_policy=CastleTargetPolicy.DISALLOWED,
    )


def _mail_params() -> CollectMailParams:
    """Builds one canonical typed mail payload for dispatcher tests."""

    return CollectMailParams(
        mailboxes=(MailboxType.PLAYER,),
        archive_mode=MailArchiveMode.TEXT,
        limit_per_mailbox=2,
        only_new=False,
    )


def _mailbox_result(mailbox: MailboxType) -> CollectMailMailboxResult:
    """Builds one zero-count mailbox result for typed dispatcher return coverage."""

    return CollectMailMailboxResult(
        mailbox=mailbox,
        availability=MailboxAvailability.UNAVAILABLE,
        processed_count=0,
        archived_count=0,
        skipped_existing_count=0,
        scroll_count=0,
    )


def _prepared_mail_step(
    *,
    castle: CastleIdentity | None = None,
    params: CollectMailParams | None = None,
) -> PreparedScriptStep:
    """Builds one already-prepared typed mail step."""

    return PreparedScriptStep(
        script_step=ScriptStep(task=TaskId.COLLECT_MAIL, castle=castle),
        parsed_params=_mail_params() if params is None else params,
        castle_target_policy=CastleTargetPolicy.OPTIONAL,
        resolved_castle=castle,
    )


def _prepared_open_building_step(
    *,
    castle: CastleIdentity | None = None,
    policy: OpenBuildingPolicy | None = None,
) -> PreparedScriptStep:
    """Builds one already-prepared typed open-building step."""

    return PreparedScriptStep(
        script_step=ScriptStep(task=TaskId.OPEN_BUILDING, castle=castle),
        parsed_params=OpenBuildingPolicy(HomeCityObjectId.CASTLE) if policy is None else policy,
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


class _RecordingActuator:
    """Records real NavigationCore actions while accepting each deterministic fixture action."""

    def __init__(self) -> None:
        self.actions: list[object] = []

    def execute_action(self, action: object, _observation: Observation) -> bool:
        """Accept one observed action and keep it available for assertions."""

        self.actions.append(action)
        return True


class _FakeChatCoreRuntime:
    """Provides the narrow CoreRuntime surface needed by authored chat dispatch."""

    def __init__(self, observations: tuple[Observation, ...], *, active_castle: CastleIdentity) -> None:
        self._observations = iter(observations)
        self._observation_count = 0
        self._last_observation: Observation | None = None
        self.active_castle = active_castle
        self.trace_path = Path("trace.jsonl")
        self.actuator = _RecordingActuator()
        self.records: list[dict[str, object]] = []
        self.navigation = NavigationCore(
            self.actuator,
            self.observe,
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4, poll_seconds=0, stable_observations=2),
            sleep=lambda _seconds: None,
            record=self.record,
        )

    @property
    def observation_count(self) -> int:
        """Returns the number of fixture frames consumed by the core."""

        return self._observation_count

    @property
    def last_observation(self) -> Observation | None:
        """Returns the latest fixture frame consumed by the core."""

        return self._last_observation

    def observe(self, label: str, *, include_content: bool = False) -> Observation:
        """Consumes one fresh deterministic frame and records its label."""

        del include_content
        try:
            observation = next(self._observations)
        except StopIteration as error:
            raise AssertionError(f"Unexpected fixture capture for '{label}'.") from error
        self._observation_count += 1
        self._last_observation = observation
        return observation

    def record(self, entry: dict[str, object]) -> None:
        """Keeps navigation trace metadata available for focused assertions."""

        self.records.append(entry)

    def preflight_active_castle_identity(self) -> CastleIdentity:
        """Returns the exact active identity that the typed dispatcher would preflight."""

        return self.active_castle


def _alliance_send_frames(message: str) -> tuple[Observation, ...]:
    """Builds Home, Chat, receipt, and Home frames for one authored send."""

    start = datetime(2026, 9, 12, 19, 0, tzinfo=UTC)
    receipt = make_entry(
        ListEntryKind.CHAT_MESSAGE,
        title="[NAX] freecookies",
        metadata={
            "chat_entry_kind": "player",
            "message_text": "testfrom bot",
            "visible_order": 0,
        },
    )
    home = (UiElementId.PNC_CHAT_SHORTCUT,)
    back = (UiElementId.PNC_BACK_BUTTON_TOP_LEFT,)
    input_field = (UiElementId.PNC_CHAT_INPUT_FIELD, *back)
    focused_empty = (
        UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT,
        UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON,
        *back,
    )
    focused_send = (UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON, *back)
    frames = (
        (ScreenType.PNC_HOME_CITY, home, None, None, None, ()),
        (ScreenType.PNC_HOME_CITY, home, None, None, None, ()),
        (ScreenType.PNC_HOME_CITY, home, None, None, None, ()),
        (ScreenType.PNC_CHAT, back, ChatChannel.ALLIANCE, True, None, ()),
        (ScreenType.PNC_CHAT, back, ChatChannel.ALLIANCE, True, None, ()),
        (ScreenType.PNC_CHAT, input_field, ChatChannel.ALLIANCE, True, None, ()),
        (ScreenType.PNC_CHAT, focused_empty, ChatChannel.ALLIANCE, True, None, ()),
        (ScreenType.PNC_CHAT, focused_empty, ChatChannel.ALLIANCE, True, None, ()),
        (ScreenType.PNC_CHAT, focused_send, ChatChannel.ALLIANCE, False, message, ()),
        (ScreenType.PNC_CHAT, focused_send, ChatChannel.ALLIANCE, False, message, ()),
        (ScreenType.PNC_CHAT, focused_empty, ChatChannel.ALLIANCE, True, None, (receipt,)),
        (ScreenType.PNC_CHAT, focused_empty, ChatChannel.ALLIANCE, True, None, (receipt,)),
        (ScreenType.PNC_CHAT, back, ChatChannel.ALLIANCE, True, None, ()),
        (ScreenType.PNC_CHAT, back, ChatChannel.ALLIANCE, True, None, ()),
        (ScreenType.PNC_HOME_CITY, home, None, None, None, ()),
        (ScreenType.PNC_HOME_CITY, home, None, None, None, ()),
    )
    return tuple(
        _alliance_send_frame(
            start + timedelta(seconds=index),
            screen=screen,
            visible_ids=visible_ids,
            channel=channel,
            draft_empty=draft_empty,
            draft_text=draft_text,
            entries=entries,
        )
        for index, (screen, visible_ids, channel, draft_empty, draft_text, entries) in enumerate(frames)
    )


def _alliance_send_frame(
    captured_at: datetime,
    *,
    screen: ScreenType,
    visible_ids: tuple[UiElementId, ...],
    channel: ChatChannel | None,
    draft_empty: bool | None,
    draft_text: str | None,
    entries: tuple[DetectedListEntry, ...],
) -> Observation:
    """Builds one typed frame with template-backed controls and chat content."""

    return replace(
        make_observation(
            screen,
            visible_ids=visible_ids,
            active_chat_channel=channel,
            chat_draft_empty=draft_empty,
            chat_draft_text=draft_text,
            list_entries=entries,
            artifact_path=Path("alliance-chat.png"),
        ),
        captured_at=captured_at,
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


def _run_ensure_script(*, params: dict[str, object]) -> RunScript:
    """Builds one authored lifecycle script for pre-connect validation tests."""

    return RunScript(
        name="ensure",
        path=Path("ensure.yaml"),
        steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING, params=params),),
    )


def _run_popup_script(
    *,
    params: dict[str, object],
    castle: CastleIdentity | None = None,
) -> RunScript:
    """Builds one authored popup recovery script for pre-connect validation tests."""

    return RunScript(
        name="popup",
        path=Path("popup.yaml"),
        steps=(ScriptStep(task=TaskId.POPUP_RECOVERY, params=params, castle=castle),),
    )


def _run_mail_script() -> RunScript:
    """Builds one authored mail script for ScriptRunner preflight tests."""

    return RunScript(
        name="mail",
        path=Path("mail.yaml"),
        steps=(ScriptStep(task=TaskId.COLLECT_MAIL, params={"mailboxes": ["player"]}),),
    )


def _run_open_building_script(*, building: str) -> RunScript:
    """Builds one authored open-building script for pre-connect validation tests."""

    return RunScript(
        name="open_building",
        path=Path("open_building.yaml"),
        steps=(ScriptStep(task=TaskId.OPEN_BUILDING, params={"building": building}),),
    )


def _run_roster_script() -> RunScript:
    """Builds one authored parameterless roster script for pre-connect validation tests."""

    return RunScript(
        name="roster",
        path=Path("roster.yaml"),
        steps=(ScriptStep(task=TaskId.REFRESH_CASTLE_ROSTER),),
    )


def _minimal_script_runner(
    *,
    archive_store: ChatArchiveStore | None,
    mail_archive_store: MailArchiveStore | None = None,
    castle_roster_store: CastleRosterStore | None = None,
) -> ScriptRunner:
    """Builds the smallest ScriptRunner object needed to test pre-connect validation."""

    runner = ScriptRunner.__new__(ScriptRunner)
    runner.config = SimpleNamespace(find_castle_targets=lambda _account_id: None)
    runner.task_registry = build_default_task_registry()
    runner.castle_roster_store = castle_roster_store
    runner.mail_archive_store = mail_archive_store
    runner.chat_archive_store = archive_store
    runner.match3_component = UnavailableMatch3Component()
    return runner


if __name__ == "__main__":
    unittest.main()
