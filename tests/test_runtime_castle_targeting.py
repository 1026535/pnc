"""Castle-targeting runtime tests for registry, runner, Python API, and CLI surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import unittest
from unittest.mock import patch

from pnc_automation.api import AutomationApi
from pnc_automation.automation.observation_mode import ObservationMode
from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.observed_action_executor import ObservedActionExecutor
from pnc_automation.automation.runner import AutomationRunner, RunResult, StepRunResult
from pnc_automation.scripts.models import RunScript, ScriptStep
from pnc_automation.scripts.registry import TaskRegistry, build_default_task_registry
from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.popup_recovery_task import PopupRecoveryTask
from pnc_automation.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.cli import main as cli_main
from pnc_automation.config.models import (
    AccountConfig,
    AccountCastleTargetsConfig,
    CastleIdentity,
    CastleTargetDefinition,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
)
from pnc_automation.errors import ScriptValidationError
from pnc_automation.pnc.action_requests import ActionRequest
from pnc_automation.pnc.observation import ListEntryKind, Observation
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.selectors import build_default_selector_registry
from tests.test_support import FakeObservationService, FakeSession, build_logger, make_entry, make_observation


class RuntimeCastleTargetingTests(unittest.TestCase):
    """Validates the new runtime castle-targeting contract across all entry points."""

    def setUp(self) -> None:
        """Builds shared account and castle identities for runtime-targeting tests."""

        self.account = AccountConfig(
            id="account_a",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
            credentials=ResolvedCredentials(
                username="user@example.com",
                password="secret",
                source=CredentialSource.INLINE,
            ),
        )
        self.defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        self.target_castle = CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8)

    def test_prepare_script_rejects_castle_for_disallowed_task(self) -> None:
        """Rejects step-level castle targeting on tasks that explicitly disallow it."""

        registry = build_default_task_registry()
        script = RunScript(
            name="invalid",
            path=Path("invalid.yaml"),
            steps=(ScriptStep(task=TaskId.LOGIN, castle=self.target_castle),),
        )

        with self.assertRaises(ScriptValidationError):
            registry.prepare_script(script)

    def test_prepare_script_requires_castle_for_select_castle(self) -> None:
        """Rejects `select_castle` steps that omit their required explicit target."""

        registry = build_default_task_registry()
        script = RunScript(
            name="invalid",
            path=Path("invalid.yaml"),
            steps=(ScriptStep(task=TaskId.SELECT_CASTLE),),
        )

        with self.assertRaises(ScriptValidationError):
            registry.prepare_script(script)

    def test_prepare_script_accepts_castle_for_optional_task(self) -> None:
        """Preserves optional step-level castle targets on normal post-login tasks."""

        registry = build_default_task_registry()
        prepared = registry.prepare_script(
            RunScript(
                name="valid",
                path=Path("valid.yaml"),
                steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE, castle=self.target_castle, params={}),),
            )
        )

        self.assertEqual(prepared.steps[0].castle, self.target_castle)

    def test_prepare_script_resolves_castle_ref_from_account_targets(self) -> None:
        """Resolves authored castle aliases once the selected account's target catalog is available."""

        registry = build_default_task_registry()
        prepared = registry.prepare_script(
            RunScript(
                name="valid",
                path=Path("valid.yaml"),
                steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE, castle_ref="main", params={}),),
            ),
            castle_targets=AccountCastleTargetsConfig(
                account_id=self.account.id,
                targets=(CastleTargetDefinition(target_id="main", castle=self.target_castle),),
            ),
        )

        self.assertEqual(prepared.steps[0].castle, self.target_castle)
        self.assertEqual(prepared.steps[0].castle_ref, "main")

    def test_prepare_script_rejects_unknown_castle_ref(self) -> None:
        """Fails fast when a script references a castle alias absent from the selected account."""

        registry = build_default_task_registry()

        with self.assertRaises(ScriptValidationError):
            registry.prepare_script(
                RunScript(
                    name="invalid",
                    path=Path("invalid.yaml"),
                    steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE, castle_ref="main", params={}),),
                ),
                castle_targets=AccountCastleTargetsConfig(account_id=self.account.id, targets=()),
            )

    def test_runner_auto_selects_explicit_castle_before_optional_task(self) -> None:
        """Runs the canonical select-castle pre-step before an optional castle-targeted task."""

        registry = TaskRegistry(tasks=(PopupRecoveryTask(), SelectCastleTask(), _OptionalCastleTask()))
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    current_castle=CastleIdentity(kingdom="K229", castle_name="Wrong"),
                ),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                    current_castle_name="Wrong",
                ),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,),
                    current_castle_name="Wrong",
                ),
                make_observation(
                    ScreenType.PNC_CASTLE_SELECTION,
                    list_entries=(
                        make_entry(
                            ListEntryKind.CASTLE,
                            title="Main",
                            metadata={"kingdom": "K230", "castle_level": 8},
                        ),
                    ),
                ),
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    current_castle_name="Main",
                ),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=fake_session,
                    stable_click_delay_ms=0,
                    post_action_observe_delay_ms=0,
                    chat_stable_click_delay_ms=0,
                    chat_post_action_observe_delay_ms=0,
                    logger=build_logger(),
                    sleep=lambda _: None,
                ),
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )
        prepared = registry.prepare_script(
            RunScript(
                name="auto_select",
                path=Path("auto_select.yaml"),
                steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE, castle=self.target_castle),),
            )
        )

        result = runner.run(
            self.account,
            prepared,
            castle_roster_provider=lambda: PncAccountCastleRosterConfig(
                pnc_account_id=self.account.pnc_account_id,
                castles=(self.target_castle,),
            ),
        )

        self.assertEqual(result.steps[0].requested_castle, self.target_castle)
        self.assertTrue(any(label.startswith("select_castle_") for label in fake_observer.labels))
        self.assertGreaterEqual(len(fake_session.taps), 4)

    def test_runner_does_not_select_castle_when_optional_task_has_no_target(self) -> None:
        """Leaves optional tasks on current-castle semantics when the step omits `castle`."""

        registry = TaskRegistry(tasks=(PopupRecoveryTask(), SelectCastleTask(), _OptionalCastleTask()))
        fake_observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_HOME_CITY)])
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=FakeSession(),
                    stable_click_delay_ms=0,
                    post_action_observe_delay_ms=0,
                    chat_stable_click_delay_ms=0,
                    chat_post_action_observe_delay_ms=0,
                    logger=build_logger(),
                    sleep=lambda _: None,
                ),
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )
        prepared = registry.prepare_script(
            RunScript(
                name="no_target",
                path=Path("no_target.yaml"),
                steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE),),
            )
        )

        runner.run(self.account, prepared)

        self.assertEqual(fake_observer.labels, ["building_upgrade_before"])

    def test_python_use_account_prepares_session_with_optional_castle(self) -> None:
        """Delegates context entry to the shared session-preparation path."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a", castle=self.target_castle) as session:
            self.assertIsNotNone(session.preparation_result)

        self.assertEqual(fake_runner.prepare_calls, [("account_a", self.target_castle)])

    def test_python_use_account_exit_performs_no_cleanup(self) -> None:
        """Leaves the live session untouched on context exit by default."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a"):
            pass

        self.assertEqual(fake_runner.prepare_calls, [("account_a", None)])
        self.assertEqual(fake_runner.task_calls, [])

    def test_python_direct_task_calls_use_current_castle_semantics(self) -> None:
        """Runs direct task wrappers without injecting hidden castle switching."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        result = api.research(account_id="account_a", priority=["economy"])

        self.assertEqual(result.task_id, TaskId.RESEARCH)
        self.assertEqual(fake_runner.task_calls, [(TaskId.RESEARCH, "account_a", {"priority": ["economy"]})])
        self.assertEqual(fake_runner.prepare_calls, [])

    def test_python_generic_run_task_no_longer_accepts_castle_targeting(self) -> None:
        """Keeps explicit castle alignment out of the public direct-call task API."""

        api = AutomationApi(application=_FakeApplicationRunner())

        with self.assertRaises(TypeError):
            api.run_task(account_id="account_a", task_id=TaskId.RESEARCH, castle=self.target_castle)

    def test_python_direct_task_calls_resolve_account_from_active_context(self) -> None:
        """Allows direct task wrappers to use the currently active `use_account(...)` scope."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a", castle=self.target_castle):
            api.building_upgrade(priority=["castle"])

        self.assertEqual(
            fake_runner.task_calls,
            [(TaskId.BUILDING_UPGRADE, "account_a", {"priority": ["castle"], "allow_speedups": False})],
        )

    def test_python_generic_run_task_resolves_account_from_active_context(self) -> None:
        """Allows the generic direct-call task API to reuse the active prepared session scope."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a"):
            api.run_task(task_id=TaskId.RESEARCH, params={"priority": ["economy"]})

        self.assertEqual(fake_runner.task_calls, [(TaskId.RESEARCH, "account_a", {"priority": ["economy"]})])

    def test_cli_login_without_castle_reuses_session_preparation_service(self) -> None:
        """Calls the shared preparation path without mutating the current castle when no target is given."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(["login", "--account", "account_a", "--config", "config/accounts.yaml"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.prepare_calls, [("account_a", None)])
        self.assertEqual(fake_runner.task_calls, [])

    def test_cli_login_with_castle_reuses_session_preparation_service(self) -> None:
        """Calls the shared preparation path with the explicit CLI castle target when one is provided."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(
                [
                    "login",
                    "--account",
                    "account_a",
                    "--config",
                    "config/accounts.yaml",
                    "--kingdom",
                    "K230",
                    "--castle-name",
                    "Main",
                    "--castle-level",
                    "8",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.prepare_calls, [("account_a", self.target_castle)])
        self.assertEqual(fake_runner.task_calls, [])

    def test_cli_legacy_run_flags_still_route_through_the_shared_run_path(self) -> None:
        """Keeps the flag-only legacy invocation shape while executing the canonical run command path."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(
                ["--account", "account_a", "--config", "config/accounts.yaml", "--script", "scripts/daily.yaml"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.run_calls, [("account_a", "scripts/daily.yaml")])

    def test_cli_passes_observation_mode_override_to_application_builder(self) -> None:
        """Threads the explicit CLI observation-mode override into the canonical application builder."""

        fake_runner = _FakeApplicationRunner()
        with (
            patch("pnc_automation.cli.build_application_runner", return_value=fake_runner) as build_runner,
            patch("builtins.print"),
        ):
            exit_code = cli_main(
                [
                    "run",
                    "--account",
                    "account_a",
                    "--config",
                    "config/accounts.yaml",
                    "--script",
                    "scripts/daily.yaml",
                    "--observation-mode",
                    "light",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(build_runner.call_args.kwargs["observation_mode"], ObservationMode.LIGHT)


@dataclass(slots=True)
class _FakeApplicationRunner:
    """Records Python API and CLI calls without constructing the full runtime."""

    run_calls: list[tuple[str, str]] = field(default_factory=list)
    prepare_calls: list[tuple[str, CastleIdentity | None]] = field(default_factory=list)
    task_calls: list[tuple[TaskId, str, dict[str, object] | None]] = field(default_factory=list)

    def run(self, *, account_id: str, script_path: str) -> RunResult:
        """Records one CLI/script run request and returns a synthetic success result."""

        self.run_calls.append((account_id, script_path))
        return _make_run_result(script_name=script_path)

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
    ) -> RunResult:
        """Records one session-preparation request and returns a synthetic success result."""

        self.prepare_calls.append((account_id, castle))
        return _make_run_result(script_name="prepare_account_session")

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, object] | None = None,
    ) -> StepRunResult:
        """Records one direct task call and returns a synthetic success result."""

        self.task_calls.append((task_id, account_id, params))
        return StepRunResult(
            task_id=task_id,
            status=TaskResult.success("ok").status,
            attempts=1,
            message="ok",
        )


class _OptionalCastleTask(BaseAutomationTask):
    """Minimal optional-target task used to isolate runner pre-step castle alignment."""

    id = TaskId.BUILDING_UPGRADE
    castle_target_policy = CastleTargetPolicy.OPTIONAL

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic optional task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Accepts the settled observation passed through from the runner."""

        del context, observation
        return True

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Runs without additional actions so only the runner pre-step is exercised."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds immediately once the runner hands control to the actual optional task."""

        del context, before, after
        return TaskResult.success("Optional task executed.")


def _make_run_result(*, script_name: str) -> RunResult:
    """Builds one minimal successful run result for API and CLI tests."""

    now = datetime.now(tz=UTC)
    return RunResult(
        account_id="account_a",
        script_name=script_name,
        steps=(
            StepRunResult(
                task_id=TaskId.LOGIN,
                status=TaskResult.success("ok").status,
                attempts=1,
                message="ok",
            ),
        ),
        started_at=now,
        finished_at=now,
    )

