"""Shared helpers for opt-in live BlueStacks smoke tests."""

from __future__ import annotations

from collections.abc import Callable

from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.automation.engine.script_runner import ConnectedAccountRuntime, ScriptRunner
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation
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

    return runner.execute_flow_until(
        label_prefix=label_prefix,
        planner=planner,
        done=done,
        start_observation=start_observation,
        max_steps=max_steps,
    )
