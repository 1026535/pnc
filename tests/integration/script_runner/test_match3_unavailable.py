"""Match-3 unavailable guards at the real ScriptRunner and AutomationRunner boundaries."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.automation.engine.script_runner import ScriptRunner
from pnc_automation.app.automation.engine.task import CastleTargetPolicy, TaskId
from pnc_automation.app.automation.match3 import (
    Match3Component,
    Match3UnavailableError,
    UnavailableMatch3Component,
)
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    DefaultsConfig,
    LiveAutomationRole,
)
from pnc_automation.app.authoring.scripts.models import (
    PreparedRunScript,
    PreparedScriptStep,
    RunScript,
    ScriptStep,
)
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.pnc.domain.match3 import (
    Match3Availability,
    Match3AvailabilityStatus,
    Match3Context,
    Match3Mode,
)
from pnc_automation.app.pnc.domain.policy_models import CampaignPolicy
from pnc_automation.core.errors import ScriptValidationError, TaskVerificationError

from tests.support.core.logging import build_logger


class ScriptRunnerMatch3GuardTests(unittest.TestCase):
    """Proves explicit battle requests stop before any connected runtime is built."""

    def test_authored_campaign_battle_mode_fails_before_connection(self) -> None:
        """An authored campaign step with battle_mode refuses before _build_runner."""

        script_runner = _script_runner()
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaises(Match3UnavailableError) as raised:
                script_runner.run_script(
                    account_id="account",
                    script=_campaign_script(params={"battle_mode": "solver"}),
                )

        build_runner.assert_not_called()
        error = raised.exception
        self.assertIs(error.availability.context, Match3Context.CAMPAIGN)
        self.assertIs(error.availability.mode, Match3Mode.SOLVER)
        self.assertEqual(error.availability.status, Match3AvailabilityStatus.NOT_IMPLEMENTED)
        self.assertEqual(error.details["task"], "campaign")

    def test_direct_run_task_battle_mode_fails_before_connection(self) -> None:
        """A direct run_task campaign request carries the same preflight refusal."""

        script_runner = _script_runner()
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaises(Match3UnavailableError):
                script_runner.run_task(
                    account_id="account",
                    task_id=TaskId.CAMPAIGN,
                    params={"battle_mode": "daily_exit"},
                )

        build_runner.assert_not_called()

    def test_invalid_battle_mode_fails_validation_before_connection(self) -> None:
        """Misspelled or unknown campaign params are parse errors, not capability refusals."""

        script_runner = _script_runner()
        for params in ({"battle_mode": "cheat"}, {"battle_mode": None}, {"battle_modes": ["solver"]}):
            with self.subTest(params=params):
                with patch.object(ScriptRunner, "_build_runner") as build_runner:
                    with self.assertRaises(ScriptValidationError):
                        script_runner.run_script(
                            account_id="account",
                            script=_campaign_script(params=params),
                        )
                build_runner.assert_not_called()

    def test_available_component_without_task_binding_refuses_before_connection(self) -> None:
        """An available policy cannot make the preparation-only dispatcher run a battle."""

        script_runner = _script_runner()
        component = _available_component(Match3Mode.SOLVER)
        script_runner.match3_component = component
        with patch.object(ScriptRunner, "_build_runner") as build_runner:
            with self.assertRaises(Match3UnavailableError) as raised:
                script_runner.run_task(
                    account_id="account",
                    task_id=TaskId.CAMPAIGN,
                    params={"battle_mode": "solver"},
                )

        build_runner.assert_not_called()
        component.execute.assert_not_called()
        self.assertIs(raised.exception.availability.status, Match3AvailabilityStatus.NOT_IMPLEMENTED)

    def test_omitted_battle_mode_reaches_runner_construction(self) -> None:
        """A campaign step without battle_mode keeps the existing dispatch path."""

        script_runner = _script_runner()
        fake_runner = Mock()
        fake_runner.run.return_value = Mock()

        with patch.object(
            ScriptRunner,
            "_build_runner",
            return_value=(fake_runner, lambda: None),
        ) as build_runner:
            script_runner.run_script(
                account_id="account",
                script=_campaign_script(params={"enabled_modes": ["standard"]}),
            )

        build_runner.assert_called_once()
        fake_runner.run.assert_called_once()
        fake_runner.close.assert_called_once_with()


class RunnerMatch3GuardTests(unittest.TestCase):
    """Proves already-connected prepared-step dispatch refuses before observe/input."""

    def test_available_component_cannot_fall_through_to_legacy_preparation(self) -> None:
        """Already-connected callers need an execution adapter even if a policy is available."""

        observation_service = Mock()
        runner = _runner(observation_service=observation_service)
        component = _available_component(Match3Mode.SOLVER)
        runner.match3_component = component
        step = _prepared_campaign_step(params={"battle_mode": "solver"})

        with self.assertRaises(Match3UnavailableError):
            runner.run(_account(), PreparedRunScript(name="campaign", path=Path("campaign.yaml"), steps=(step,)))

        observation_service.observe.assert_not_called()
        runner.action_executor.execute_actions.assert_not_called()
        component.execute.assert_not_called()

    def test_prepared_campaign_battle_step_refuses_before_observe(self) -> None:
        """Direct prepared-step dispatch cannot fall into the legacy CampaignTask."""

        observation_service = Mock()
        runner = _runner(observation_service=observation_service)
        step = _prepared_campaign_step(params={"battle_mode": "game_auto"})

        with self.assertRaises(Match3UnavailableError) as raised:
            runner.run(_account(), PreparedRunScript(name="campaign", path=Path("campaign.yaml"), steps=(step,)))

        observation_service.observe.assert_not_called()
        runner.action_executor.execute_actions.assert_not_called()
        self.assertIs(raised.exception.availability.mode, Match3Mode.GAME_AUTO)

    def test_campaign_step_without_battle_mode_proceeds_to_legacy_dispatch(self) -> None:
        """A prepared campaign step without battle_mode still reaches the legacy task path."""

        observation_service = Mock()
        runner = _runner(observation_service=observation_service)
        runner.action_executor.recover_interruption_if_required.return_value = None
        step = _prepared_campaign_step(params={"enabled_modes": ["standard"]})

        with self.assertRaises(TaskVerificationError) as raised:
            runner.run(_account(), PreparedRunScript(name="campaign", path=Path("campaign.yaml"), steps=(step,)))

        self.assertNotIsInstance(raised.exception, Match3UnavailableError)
        observation_service.observe.assert_called()


def _available_component(mode: Match3Mode) -> Mock:
    """Reports an available policy through the real component interface."""

    component = Mock(spec=Match3Component)
    component.availability.return_value = Match3Availability(
        context=Match3Context.CAMPAIGN,
        mode=mode,
        status=Match3AvailabilityStatus.AVAILABLE,
    )
    return component


def _account() -> AccountConfig:
    """Builds one offline account binding with the live-testing role."""

    return AccountConfig(
        id="account",
        instance_id="instance",
        pnc_account_id="pnc-account",
        live_roles=frozenset({LiveAutomationRole.LIVE_TESTING}),
    )


def _script_runner() -> ScriptRunner:
    """Builds the smallest ScriptRunner needed to test the pre-connect match-3 guard."""

    runner = ScriptRunner.__new__(ScriptRunner)
    runner.config = SimpleNamespace(
        require_account=lambda account_id: _account(),
        find_castle_targets=lambda _account_id: None,
    )
    runner.task_registry = build_default_task_registry()
    runner.castle_roster_store = None
    runner.mail_archive_store = None
    runner.chat_archive_store = None
    runner.match3_component = UnavailableMatch3Component()
    return runner


def _runner(*, observation_service: Mock) -> AutomationRunner:
    """Builds an offline runner with only the dependencies used by step dispatch."""

    return AutomationRunner(
        defaults=DefaultsConfig(),
        observation_service=observation_service,
        action_executor=Mock(),
        task_registry=build_default_task_registry(),
        flow_planner=Mock(),
        logger=build_logger(),
    )


def _campaign_script(*, params: dict[str, object]) -> RunScript:
    """Builds one authored campaign script for ScriptRunner preflight tests."""

    return RunScript(
        name="campaign",
        path=Path("campaign.yaml"),
        steps=(ScriptStep(task=TaskId.CAMPAIGN, params=params),),
    )


def _prepared_campaign_step(*, params: dict[str, object]) -> PreparedScriptStep:
    """Builds one already-prepared campaign step as the dispatcher would emit it."""

    return PreparedScriptStep(
        script_step=ScriptStep(task=TaskId.CAMPAIGN, params=params),
        parsed_params=CampaignPolicy.from_params(params),
        castle_target_policy=CastleTargetPolicy.OPTIONAL,
        resolved_castle=None,
    )


if __name__ == "__main__":
    unittest.main()
