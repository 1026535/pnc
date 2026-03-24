"""Shared helpers for opt-in live BlueStacks smoke tests."""

from __future__ import annotations

from collections.abc import Callable

from pnc_automation.automation.runner import AutomationRunner
from pnc_automation.pnc.action_requests import ActionRequest
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.config.models import AccountConfig
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.vision.observation_builder import ObservationService


def build_live_session(*, config_account: AccountConfig, script_runner: object) -> BlueStacksSession:
    """Creates and connects one live BlueStacks session using the authoritative runtime wiring."""

    build_connected_session = getattr(script_runner, "build_connected_session", None)
    if not callable(build_connected_session):
        raise AssertionError("Live smoke tests require ScriptRunner.build_connected_session().")
    session = build_connected_session(account=config_account)
    if not isinstance(session, BlueStacksSession):
        raise AssertionError("Live smoke tests require ScriptRunner.build_connected_session() to return a BlueStacksSession.")
    return session


def build_observation_service(
    *,
    config_account: AccountConfig,
    script_runner: object,
    session: BlueStacksSession,
) -> ObservationService:
    """Builds one live observation service from the same runtime components used by the application."""

    return ObservationService(
        screenshot_service=require_screenshot_service(script_runner),
        observation_builder=script_runner.observation_builder,
        session=session,
        artifact_directory=config_account.artifact_directory_name,
        pnc_account_id=config_account.pnc_account_id,
        castle_roster_store=script_runner.castle_roster_store,
    )


def require_screenshot_service(script_runner: object) -> ScreenshotService:
    """Returns the configured screenshot service or fails fast when the runner shape changes."""

    screenshot_service = getattr(script_runner, "screenshot_service", None)
    if not isinstance(screenshot_service, ScreenshotService):
        raise AssertionError("Live smoke tests require ScriptRunner.screenshot_service.")
    return screenshot_service


def build_live_automation_runner(*, config_account: AccountConfig, script_runner: object) -> AutomationRunner:
    """Builds one connected automation runner from the authoritative script-runner wiring."""

    build_runner = getattr(script_runner, "_build_runner", None)
    if not callable(build_runner):
        raise AssertionError("Live smoke tests require ScriptRunner._build_runner().")
    runner, _ = build_runner(config_account)
    if not isinstance(runner, AutomationRunner):
        raise AssertionError("Live smoke tests require ScriptRunner._build_runner() to return an AutomationRunner.")
    return runner


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
