"""Canonical session-scoped task observe-plan-act-verify executor."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.task import AutomationTask, TaskResult, TaskStatus
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.domain.observation_policy import ObservationArtifactKind, observation_artifact_selection
from pnc_automation.core.errors import TaskVerificationError


@dataclass(frozen=True, slots=True)
class TaskExecutionResult:
    """Carries one finished canonical task-loop result and freshest observation."""

    result: TaskResult
    attempts: int
    final_observation: Observation


@dataclass(slots=True)
class TaskExecutor:
    """Runs tasks through the repository's single plan-act-observe-verify loop."""

    observation_service: ObservationService
    action_executor: ObservedActionExecutor
    logger: logging.LoggerAdapter
    max_replans_per_step: int
    max_retries_per_step: int

    def execute(
        self,
        *,
        task: AutomationTask,
        context: TaskContext,
        before: Observation,
    ) -> TaskExecutionResult:
        """Executes one already-preflighted task with global required-update recovery."""

        attempts = 0
        replans = 0
        current_before = before
        while True:
            recovered = self.action_executor.recover_interruption_if_required(
                current_before,
                label_prefix=f"{task.id.value}_pre_action_update",
                observe=lambda label, request=None: self.observation_service.observe(
                    f"{task.id.value}_{label}",
                    request=request,
                ),
            )
            if recovered is not None:
                current_before = recovered
            attempts += 1
            if not task.is_applicable(context, current_before):
                self._raise_failure(
                    context=context,
                    observation=current_before,
                    message=(
                        f"Task '{task.id}' is not applicable on screen "
                        f"'{current_before.screen_type}'."
                    ),
                    label=f"{task.id.value}_failure_not_applicable",
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
                        f"{task.id.value}_{label}",
                        request=request,
                    ),
                )
                after = execution.observation
                if execution.update_recovered:
                    self._raise_failure(
                        context=context,
                        observation=after,
                        message=(
                            "A required game update interrupted the task after an action. "
                            "Typed Home was restored, but the action result is ambiguous and will not be replayed."
                        ),
                        label=f"{task.id.value}_failure_update_interruption",
                    )
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
                return TaskExecutionResult(result=result, attempts=attempts, final_observation=after)
            if result.status == TaskStatus.REPLAN:
                replans += 1
                max_replans = task.max_replans_per_step(context)
                if max_replans is None:
                    max_replans = self.max_replans_per_step
                if replans > max_replans:
                    self._raise_failure(
                        context=context,
                        observation=after,
                        message=f"Task '{task.id}' exceeded the maximum allowed replans.",
                        label=f"{task.id.value}_failure_replan_limit",
                        replans=replans,
                    )
                current_before = after
                continue
            if result.retryable and attempts <= self.max_retries_per_step:
                current_before = self.observation_service.observe(f"{task.id.value}_retry_{attempts}")
                continue
            self._raise_failure(
                context=context,
                observation=after,
                message=result.message,
                label=f"{task.id.value}_failure_result",
            )

    def _raise_failure(
        self,
        *,
        context: TaskContext,
        observation: Observation,
        message: str,
        label: str,
        **details: object,
    ) -> None:
        """Persists failure evidence when needed and raises one structured error."""

        artifact_path = None if observation.artifact_path is None else str(observation.artifact_path)
        if artifact_path is None:
            try:
                failure_observation = self.observation_service.observe(
                    label,
                    request=ObservationRequest.full_runtime_default(),
                    artifact_selection=observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
                )
                if failure_observation.artifact_path is not None:
                    artifact_path = str(failure_observation.artifact_path)
            except Exception:
                self.logger.exception("Failed to persist a debug artifact for task failure.")
        raise TaskVerificationError(
            message,
            task_id=context.step.task,
            screen_type=observation.screen_type,
            artifact_path=artifact_path,
            **details,
        )
