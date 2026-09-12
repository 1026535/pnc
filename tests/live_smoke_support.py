"""Shared helpers for opt-in live BlueStacks smoke tests."""

from __future__ import annotations

import os
from collections.abc import Callable

from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.automation.engine.script_runner import (
    ConnectedAccountRuntime,
    ConnectedAutomationRuntime,
    ScriptRunner,
)
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.authoring.config.models import AccountConfig, LiveAutomationRole
from pnc_automation.core.infra.emulator.session import BlueStacksSessionCleanupPolicy


def live_session_cleanup_policy_from_environment() -> BlueStacksSessionCleanupPolicy:
    """Returns the agent-selected live-session policy, defaulting to a warm instance."""

    value = os.getenv("PNC_LIVE_SESSION_CLEANUP", "keep_warm").strip().casefold()
    if value == "keep_warm":
        return BlueStacksSessionCleanupPolicy.keep_warm()
    if value == "close_at_phase_end":
        # Selecting this environment mode is the agent's explicit decision to
        # close the managed smoke target even when it was already open.
        return BlueStacksSessionCleanupPolicy.close_at_phase_end(
            close_preexisting_instance=True,
        )
    raise ValueError(
        "PNC_LIVE_SESSION_CLEANUP must be 'keep_warm' or 'close_at_phase_end'."
    )


def build_live_runtime(
    *,
    config_account: AccountConfig,
    script_runner: ScriptRunner,
    session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
) -> ConnectedAccountRuntime:
    """Builds the canonical connected live runtime used by smoke tests."""

    return script_runner.build_connected_runtime(
        account=config_account,
        required_role=LiveAutomationRole.SMOKE_TEST,
        session_cleanup_policy=session_cleanup_policy or live_session_cleanup_policy_from_environment(),
    )


def build_live_automation_runner(
    *,
    config_account: AccountConfig,
    script_runner: ScriptRunner,
    session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
) -> AutomationRunner:
    """Builds one connected automation runner from the authoritative script-runner wiring."""

    return script_runner.build_connected_automation_runner(
        account=config_account,
        required_role=LiveAutomationRole.SMOKE_TEST,
        session_cleanup_policy=session_cleanup_policy or live_session_cleanup_policy_from_environment(),
    )


def build_live_runtime_bundle(
    *,
    config_account: AccountConfig,
    script_runner: ScriptRunner,
    session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
) -> ConnectedAutomationRuntime:
    """Builds one shared live runtime plus runner graph for smoke tests that pass observations between them."""

    return script_runner.build_connected_runtime_bundle(
        account=config_account,
        required_role=LiveAutomationRole.SMOKE_TEST,
        session_cleanup_policy=session_cleanup_policy or live_session_cleanup_policy_from_environment(),
    )


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
