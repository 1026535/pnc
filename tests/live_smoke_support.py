"""Shared helpers for opt-in live BlueStacks smoke tests."""

from __future__ import annotations

from collections.abc import Callable

from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.automation.engine.script_runner import ConnectedAccountRuntime, ScriptRunner
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.authoring.config.models import AccountConfig


def build_live_runtime(*, config_account: AccountConfig, script_runner: ScriptRunner) -> ConnectedAccountRuntime:
    """Builds the canonical connected live runtime used by smoke tests."""

    return script_runner.build_connected_runtime(account=config_account)


def build_live_automation_runner(*, config_account: AccountConfig, script_runner: ScriptRunner) -> AutomationRunner:
    """Builds one connected automation runner from the authoritative script-runner wiring."""

    return script_runner.build_connected_automation_runner(account=config_account)


def execute_live_flow_until(
    *,
    runner: AutomationRunner,
    label_prefix: str,
    planner: Callable[[Observation], list[ActionRequest]],
    done: Callable[[Observation], bool],
    start_observation: Observation | None = None,
    max_steps: int = 6,
) -> Observation:
    """Executes one reusable flow incrementally until the target condition is satisfied or the budget is exhausted."""

    current_observation = start_observation or runner.observation_service.observe(f"{label_prefix}_start")
    for step_index in range(max_steps + 1):
        if done(current_observation):
            return current_observation
        if current_observation.blocking_popup or current_observation.screen_type == ScreenType.PNC_POPUP:
            actions = runner.flow_planner.close_blocking_popup(current_observation)
        elif current_observation.screen_type == ScreenType.UNKNOWN:
            actions = runner.flow_planner.recover_unknown_game_screen(
                current_observation,
                reason=f"{label_prefix}_recover_unknown",
            )
        else:
            actions = planner(current_observation)
        if not actions:
            raise AssertionError(
                f"Live flow '{label_prefix}' produced no actions before reaching the requested condition.",
            )
        execution = runner.action_executor.execute_actions(
            actions,
            current_observation,
            observe=lambda label, request=None: runner.observation_service.observe(
                f"{label_prefix}_step_{step_index}_{label}",
                request,
            ),
        )
        current_observation = execution.observation
    raise AssertionError(f"Live flow '{label_prefix}' did not reach the requested condition within {max_steps} steps.")
