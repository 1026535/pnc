"""Canonical observe-plan-act-verify automation runner."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pnc_automation.automation.observed_action_executor import ObservedActionExecutor
from pnc_automation.automation.scripts.models import PreparedRunScript, PreparedScriptStep, ScriptStep
from pnc_automation.automation.scripts.registry import TaskRegistry
from pnc_automation.automation.task import CastleTargetPolicy, TaskId, TaskResult, TaskStatus
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.models import AccountConfig, CastleIdentity, DefaultsConfig, PncAccountCastleRosterConfig
from pnc_automation.errors import TaskVerificationError
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.vision.observation_builder import ObservationService


@dataclass(frozen=True, slots=True)
class StepRunResult:
    """Summarizes one completed script step."""

    task_id: TaskId
    status: TaskStatus
    attempts: int
    message: str
    requested_castle: CastleIdentity | None = None


@dataclass(frozen=True, slots=True)
class RunResult:
    """Summarizes one completed automation run."""

    account_id: str
    script_name: str
    steps: tuple[StepRunResult, ...]
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class StepExecutionPolicy:
    """Centralizes retry and replan limits for one automation runner."""

    max_replans_per_step: int = 5
    max_retries_per_step: int = 1

    def __post_init__(self) -> None:
        """Rejects invalid negative execution-policy limits."""

        if self.max_replans_per_step < 0:
            raise ValueError("StepExecutionPolicy.max_replans_per_step cannot be negative.")
        if self.max_retries_per_step < 0:
            raise ValueError("StepExecutionPolicy.max_retries_per_step cannot be negative.")


@dataclass(frozen=True, slots=True)
class _LoopExecutionResult:
    """Carries one finished task-loop result and the freshest observation."""

    result: TaskResult
    attempts: int
    final_observation: Observation


@dataclass(slots=True)
class AutomationRunner:
    """Executes a run script through the canonical observation loop."""

    defaults: DefaultsConfig
    observation_service: ObservationService
    action_executor: ObservedActionExecutor
    task_registry: TaskRegistry
    flow_planner: ScreenFlowPlanner
    logger: logging.LoggerAdapter
    policy: StepExecutionPolicy = field(default_factory=StepExecutionPolicy)

    def run(
        self,
        account: AccountConfig,
        script: PreparedRunScript,
        *,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None = None,
        castle_roster_store: CastleRosterStore | None = None,
    ) -> RunResult:
        """Runs the provided script for one account target."""

        started_at = datetime.now(tz=UTC)
        step_results = [
            self._run_step(
                account,
                step,
                castle_roster_provider=castle_roster_provider,
                castle_roster_store=castle_roster_store,
            )
            for step in script.steps
        ]
        finished_at = datetime.now(tz=UTC)
        return RunResult(
            account_id=account.id,
            script_name=script.name,
            steps=tuple(step_results),
            started_at=started_at,
            finished_at=finished_at,
        )

    def _run_step(
        self,
        account: AccountConfig,
        step: PreparedScriptStep,
        *,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
    ) -> StepRunResult:
        """Executes one script step until it succeeds or fails."""

        before = self.observation_service.observe(f"{step.task.value}_before")
        before = self._align_step_castle_target(
            account=account,
            step=step,
            before=before,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
        )
        execution = self._execute_step_loop(
            account=account,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            step=step.script_step,
            parsed_params=step.parsed_params,
            target_castle=step.castle,
            before=before,
            allow_popup_recovery=True,
        )
        return StepRunResult(
            task_id=step.task,
            status=execution.result.status,
            attempts=execution.attempts,
            message=execution.result.message,
            requested_castle=step.castle,
        )

    def _align_step_castle_target(
        self,
        *,
        account: AccountConfig,
        step: PreparedScriptStep,
        before: Observation,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
    ) -> Observation:
        """Runs the canonical synthetic pre-step castle alignment when one target was requested."""

        if step.castle is None or step.castle_target_policy != CastleTargetPolicy.OPTIONAL:
            return before
        synthetic_step = ScriptStep(task=TaskId.SELECT_CASTLE, castle=step.castle)
        select_castle_task = self.task_registry.require(TaskId.SELECT_CASTLE)
        execution = self._execute_step_loop(
            account=account,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            step=synthetic_step,
            parsed_params=select_castle_task.parse_params({}),
            target_castle=step.castle,
            before=before,
            allow_popup_recovery=True,
        )
        return execution.final_observation

    def _execute_step_loop(
        self,
        *,
        account: AccountConfig,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
        step: ScriptStep,
        parsed_params: Any,
        target_castle: CastleIdentity | None,
        before: Observation,
        allow_popup_recovery: bool,
    ) -> _LoopExecutionResult:
        """Runs one task through the canonical plan-act-verify loop."""

        task = self.task_registry.require(step.task)
        context = self._build_context(
            account=account,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            step=step,
            parsed_params=parsed_params,
            target_castle=target_castle,
        )
        attempts = 0
        replans = 0
        current_before = before
        while True:
            attempts += 1
            if allow_popup_recovery:
                current_before = self._ensure_no_blocking_popup(
                    current_before,
                    account=account,
                    castle_roster_store=castle_roster_store,
                )
            if not task.is_applicable(context, current_before):
                raise TaskVerificationError(
                    f"Task '{step.task}' is not applicable on screen '{current_before.screen_type}'.",
                    task_id=step.task,
                    screen_type=current_before.screen_type,
                    artifact_path=str(current_before.artifact_path) if current_before.artifact_path else None,
                )

            context.logger.info(
                "Planning task increment.",
                extra={"screen_type": current_before.screen_type, "attempt": attempts},
            )
            actions = task.plan(context, current_before)
            after = current_before
            if actions:
                execution = self.action_executor.execute_actions(
                    actions,
                    current_before,
                    observe=lambda label, request=None: self.observation_service.observe(
                        f"{step.task.value}_{label}",
                        request=request,
                    ),
                )
                after = execution.observation
            result = task.verify(context, current_before, after)
            context.logger.info(
                "Task increment verified.",
                extra={
                    "result": result.status,
                    "screen_type": after.screen_type,
                    "message": result.message,
                },
            )
            if result.succeeded:
                return _LoopExecutionResult(result=result, attempts=attempts, final_observation=after)
            if result.status == TaskStatus.REPLAN:
                replans += 1
                if replans > self.policy.max_replans_per_step:
                    raise TaskVerificationError(
                        f"Task '{step.task}' exceeded the maximum allowed replans.",
                        task_id=step.task,
                        replans=replans,
                    )
                current_before = after
                continue
            if result.retryable and attempts <= self.policy.max_retries_per_step:
                current_before = self.observation_service.observe(f"{step.task.value}_retry_{attempts}")
                continue
            raise TaskVerificationError(
                result.message,
                task_id=step.task,
                screen_type=after.screen_type,
                artifact_path=str(after.artifact_path) if after.artifact_path else None,
            )

    def _build_context(
        self,
        *,
        account: AccountConfig,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
        step: ScriptStep,
        parsed_params: Any,
        target_castle: CastleIdentity | None,
    ) -> TaskContext:
        """Builds the shared task context for one canonical task execution."""

        logger_extra = {**self.logger.extra, "task_id": step.task}
        if target_castle is not None:
            logger_extra["target_castle"] = f"{target_castle.kingdom}/{target_castle.castle_name}"
        return TaskContext(
            account=account,
            castle_roster_provider=castle_roster_provider or (lambda: None),
            defaults=self.defaults,
            step=step,
            params=parsed_params,
            flows=self.flow_planner,
            logger=logging.LoggerAdapter(self.logger.logger, extra=logger_extra),
            target_castle=target_castle,
            castle_roster_store=castle_roster_store,
        )

    def _ensure_no_blocking_popup(
        self,
        observation: Observation,
        *,
        account: AccountConfig,
        castle_roster_store: CastleRosterStore | None,
    ) -> Observation:
        """Executes centralized popup recovery ahead of non-popup tasks."""

        if not observation.blocking_popup:
            return observation
        popup_step = ScriptStep(task=TaskId.POPUP_RECOVERY)
        popup_task = self.task_registry.require(TaskId.POPUP_RECOVERY)
        execution = self._execute_step_loop(
            account=account,
            castle_roster_provider=None,
            castle_roster_store=castle_roster_store,
            step=popup_step,
            parsed_params=popup_task.parse_params({}),
            target_castle=None,
            before=observation,
            allow_popup_recovery=False,
        )
        return execution.final_observation
