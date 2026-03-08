"""Canonical observe-plan-act-verify automation runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.scripts.models import RunScript, ScriptStep
from pnc_automation.automation.scripts.registry import TaskRegistry
from pnc_automation.automation.task import TaskId, TaskStatus
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.config.models import AccountConfig, DefaultsConfig
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


@dataclass(frozen=True, slots=True)
class RunResult:
    """Summarizes one completed automation run."""

    account_id: str
    script_name: str
    steps: tuple[StepRunResult, ...]
    started_at: datetime
    finished_at: datetime


@dataclass(slots=True)
class AutomationRunner:
    """Executes a run script through the canonical observation loop."""

    defaults: DefaultsConfig
    observation_service: ObservationService
    action_executor: ActionExecutor
    task_registry: TaskRegistry
    flow_planner: ScreenFlowPlanner
    logger: logging.LoggerAdapter
    max_replans_per_step: int = 5
    max_retries_per_step: int = 1

    def run(self, account: AccountConfig, script: RunScript) -> RunResult:
        """Runs the provided script for one account target."""

        started_at = datetime.now(tz=UTC)
        step_results = [self._run_step(account, step) for step in script.steps]
        finished_at = datetime.now(tz=UTC)
        return RunResult(
            account_id=account.id,
            script_name=script.name,
            steps=tuple(step_results),
            started_at=started_at,
            finished_at=finished_at,
        )

    def _run_step(self, account: AccountConfig, step: ScriptStep) -> StepRunResult:
        """Executes one script step until it succeeds or fails."""

        task = self.task_registry.require(step.task)
        params = task.parse_params(step.params)
        task_logger = logging.LoggerAdapter(
            self.logger.logger,
            extra={**self.logger.extra, "task_id": step.task},
        )
        context = TaskContext(
            account=account,
            defaults=self.defaults,
            step=step,
            params=params,
            flows=self.flow_planner,
            logger=task_logger,
        )

        attempts = 0
        replans = 0
        before = self.observation_service.observe(f"{step.task.value}_before")
        while True:
            attempts += 1
            before = self._ensure_no_blocking_popup(before, account=account)
            if not task.is_applicable(context, before):
                raise TaskVerificationError(
                    f"Task '{step.task}' is not applicable on screen '{before.screen_type}'.",
                    task_id=step.task,
                    screen_type=before.screen_type,
                    artifact_path=str(before.artifact_path) if before.artifact_path else None,
                )

            task_logger.info("Planning task increment.", extra={"screen_type": before.screen_type, "attempt": attempts})
            actions = task.plan(context, before)
            after = before if not actions else self.action_executor.execute_actions(
                actions,
                before,
                observe=lambda label: self.observation_service.observe(f"{step.task.value}_{label}"),
            )
            result = task.verify(context, before, after)
            task_logger.info(
                "Task increment verified.",
                extra={
                    "result": result.status,
                    "screen_type": after.screen_type,
                    "message": result.message,
                },
            )
            if result.succeeded:
                return StepRunResult(task_id=step.task, status=result.status, attempts=attempts, message=result.message)
            if result.status == TaskStatus.REPLAN:
                replans += 1
                if replans > self.max_replans_per_step:
                    raise TaskVerificationError(
                        f"Task '{step.task}' exceeded the maximum allowed replans.",
                        task_id=step.task,
                        replans=replans,
                    )
                before = after
                continue
            if result.retryable and attempts <= self.max_retries_per_step:
                before = self.observation_service.observe(f"{step.task.value}_retry_{attempts}")
                continue
            raise TaskVerificationError(
                result.message,
                task_id=step.task,
                screen_type=after.screen_type,
                artifact_path=str(after.artifact_path) if after.artifact_path else None,
            )

    def _ensure_no_blocking_popup(self, observation: Observation, *, account: AccountConfig) -> Observation:
        """Executes centralized popup recovery ahead of non-popup tasks."""

        if not observation.blocking_popup:
            return observation
        popup_task = self.task_registry.require(TaskId.POPUP_RECOVERY)
        popup_step = ScriptStep(task=TaskId.POPUP_RECOVERY, params={})
        popup_context = TaskContext(
            account=account,
            defaults=self.defaults,
            step=popup_step,
            params=popup_task.parse_params({}),
            flows=self.flow_planner,
            logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, "task_id": TaskId.POPUP_RECOVERY}),
        )
        actions = popup_task.plan(popup_context, observation)
        after = self.action_executor.execute_actions(
            actions,
            observation,
            observe=lambda label: self.observation_service.observe(f"popup_recovery_{label}"),
        )
        result = popup_task.verify(popup_context, observation, after)
        if not result.succeeded:
            raise TaskVerificationError(result.message, task_id=TaskId.POPUP_RECOVERY)
        return after
