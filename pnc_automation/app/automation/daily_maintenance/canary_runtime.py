"""Shared read-only identity verification for explicitly named Daily canaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pnc_automation.app.automation.daily_maintenance.canaries import CanaryEvidenceStore, CanaryResult
from pnc_automation.app.automation.engine.core_runtime import assemble_core_runtime
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.script_runner import ConnectedAutomationRuntime, ScriptRunner
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    CurrentCastleMatchStatus,
    Observation,
    resolve_current_castle_match,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType


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
    """Proves the exact active canary through the canonical nonselecting core preflight."""

    account = script_runner.config.require_account(target.account_id)
    core_runtime = assemble_core_runtime(
        script_runner=script_runner,
        connected_runtime=connected.runtime,
        account=account,
        artifact_directory=account.artifact_directory_name,
        policy=None,
        trace_path=None,
    )
    active_castle = core_runtime.preflight_active_castle_identity()
    match = resolve_current_castle_match(
        current_castle=active_castle,
        evidence_kind=CurrentCastleEvidenceKind.EXACT,
        target=target.castle,
        roster=None,
    )
    if match.status != CurrentCastleMatchStatus.MATCH:
        raise ValueError("Canary preflight proved a different active castle than the requested target.")
    observation = core_runtime.last_observation
    if observation is None or observation.blocking_popup or observation.screen_type != ScreenType.PNC_HOME_CITY:
        raise ValueError("Canary identity preflight did not leave a fresh, unblocked Home City observation.")
    actions = connected.runtime.require_observed_action_executor(
        "Canary identity verification requires the canonical observed action executor."
    )
    return VerifiedCanaryRuntime(observation, actions)
