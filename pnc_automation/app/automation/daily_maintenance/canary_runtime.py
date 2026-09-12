"""Shared read-only identity verification for explicitly named Daily canaries."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from pnc_automation.app.automation.daily_maintenance.canaries import CanaryEvidenceStore, CanaryResult
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.script_runner import ConnectedAutomationRuntime, ScriptRunner
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.authoring.scripts.models import ScriptStep
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapAction, WaitAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask


@dataclass(frozen=True, slots=True)
class VerifiedCanaryRuntime:
    """Carries the connected services after the requested canary identity is proved."""

    observation: Observation
    action_executor: ObservedActionExecutor


def persist_canary_result(*, artifact_root: Path, result: CanaryResult) -> Path:
    """Persists one current canary result through the canonical evidence store."""

    return CanaryEvidenceStore(artifact_root).save(result)


def verify_canary_identity(
    *,
    script_runner: ScriptRunner,
    connected: ConnectedAutomationRuntime,
    target: DailyMaintenanceTargetConfig,
) -> VerifiedCanaryRuntime:
    """Proves the exact active canary without switching or mutating game state."""

    observer = connected.runtime.observation_service
    actions = connected.runtime.require_observed_action_executor(
        "Canary identity verification requires the canonical observed action executor."
    )
    current = observer.observe("canary_identity_start")
    recovered = actions.recover_interruption_if_required(
        current,
        label_prefix="canary_identity_update",
        observe=lambda label, request=None: observer.observe(label, request=request),
    )
    if recovered is not None:
        current = recovered
    if current.screen_type in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
        bootstrap = script_runner.run_task(
            account_id=target.account_id,
            task_id=TaskId.ENSURE_GAME_RUNNING,
        )
        if bootstrap.status == TaskStatus.FAILED:
            raise ValueError(f"Canary bootstrap could not foreground P&C: {bootstrap.message}")
        current = observer.observe("canary_identity_after_bootstrap")
    roster_scan = RefreshCastleRosterTask()
    context = TaskContext(
        account=script_runner.config.require_account(target.account_id),
        castle_roster_provider=lambda: None,
        defaults=script_runner.config.defaults,
        step=ScriptStep(TaskId.REFRESH_CASTLE_ROSTER),
        params=None,
        flows=connected.runner.flow_planner,
        logger=script_runner.logger,
    )
    unknown_reobservations = 0
    for index in range(8):
        recovered = actions.recover_interruption_if_required(
            current,
            label_prefix=f"canary_identity_{index}_interruption",
            observe=lambda label, request=None: observer.observe(label, request=request),
        )
        if recovered is not None:
            current = recovered
            continue
        if current.screen_type == ScreenType.UNKNOWN:
            if unknown_reobservations >= 2:
                raise ValueError("Canary identity remained unclassified after bounded capture retries.")
            unknown_reobservations += 1
            time.sleep(1.5)
            current = observer.observe(f"canary_identity_unknown_retry_{unknown_reobservations}")
            continue
        if current.screen_type == ScreenType.PNC_CASTLE_SELECTION:
            entry = current.find_castle_entry(target.castle)
            if entry is not None and not entry.selected:
                raise ValueError("Requested canary is not proved selected; no castle switch or mutation was sent.")
            if entry is not None:
                return VerifiedCanaryRuntime(current, actions)
            planned = roster_scan.plan(context, current)
        elif current.screen_type in {
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_SETTINGS,
            ScreenType.PNC_QUEST_DAILY,
            ScreenType.PNC_MIGHT_RANK,
            ScreenType.PNC_EVENT_CENTER,
        }:
            planned = (
                connected.runner.flow_planner.ensure_home_city(current)
                if current.screen_type in {
                    ScreenType.PNC_QUEST_DAILY,
                    ScreenType.PNC_MIGHT_RANK,
                    ScreenType.PNC_EVENT_CENTER,
                }
                else connected.runner.flow_planner.open_castle_selection(current)
            )
        elif current.screen_type == ScreenType.PNC_HOME_CITY_ROOT:
            planned = connected.runner.flow_planner.ensure_home_city(current)
        elif current.screen_type == ScreenType.PNC_WORLD_MAP:
            planned = connected.runner.flow_planner.ensure_home_city(current)
        elif current.screen_type == ScreenType.PNC_BAG:
            planned = connected.runner.flow_planner.ensure_home_city(current)
        elif current.screen_type == ScreenType.PNC_GODDESS_STATUE:
            planned = connected.runner.flow_planner.ensure_home_city(current)
        elif current.screen_type == ScreenType.PNC_VIP_DAILY_RESET:
            planned = connected.runner.flow_planner.close_blocking_popup(current)
        elif current.screen_type == ScreenType.PNC_POPUP and (
            current.has(UiElementId.PNC_POPUP_CLOSE_BUTTON)
            or current.has(UiElementId.PNC_RECONNECT_CONFIRM_BUTTON)
            or current.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON)
        ):
            planned = connected.runner.flow_planner.close_blocking_popup(current)
        elif current.screen_type == ScreenType.PNC_POPUP:
            raise ValueError("A blocking popup has no typed safe dismissal control; resolve it before the canary.")
        else:
            raise ValueError("Unexpected screen while verifying the active canary; stopped before mutation.")
        if not planned:
            raise ValueError("Canary identity navigation produced no safe action.")
        action = planned[0]
        allowed_scroll = isinstance(action, SwipeAction) and current.screen_type == ScreenType.PNC_CASTLE_SELECTION
        allowed_wait = isinstance(action, WaitAction) and current.screen_type == ScreenType.PNC_HOME_CITY_ROOT
        allowed_tap = isinstance(action, TapAction) and action.selector_id in {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_BOTTOM_NAV_MORE,
            UiElementId.PNC_MORE_SETTINGS,
            UiElementId.PNC_MORE_MANAGE_CHAR,
            UiElementId.PNC_MORE_OVERLAY_MANAGE_CHAR,
            UiElementId.PNC_WORLD_HOME_NAV,
            UiElementId.PNC_POPUP_CLOSE_BUTTON,
            UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
            UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
            UiElementId.PNC_RECONNECT_CONFIRM_BUTTON,
        }
        if not (allowed_scroll or allowed_wait or allowed_tap):
            raise ValueError("Canary identity navigation rejected a non-read-only action.")
        before = current
        current = actions.execute_actions(
            (action,),
            current,
            observe=lambda label, request=None: observer.observe(
                f"canary_identity_{index}_{label}", request=request,
            ),
        ).observation
        if allowed_scroll and current.find_castle_entry(target.castle) is None:
            result = roster_scan.verify(context, before, current)
            if result.status == TaskStatus.FAILED:
                raise ValueError("Read-only roster navigation could not prove the canary identity.")
    raise ValueError("Active canary identity could not be verified within eight transitions.")
