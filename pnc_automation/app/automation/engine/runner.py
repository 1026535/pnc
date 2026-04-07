"""Canonical observe-plan-act-verify automation runner."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.authoring.scripts.models import PreparedRunScript, PreparedScriptStep, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import CastleTargetPolicy, TaskId, TaskResult, TaskStatus
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.authoring.config.models import AccountConfig, CastleIdentity, DefaultsConfig, PncAccountCastleRosterConfig
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.runtime.observation_artifacts import ObservationArtifactKind, observation_artifact_selection


@dataclass(frozen=True, slots=True)
class StepRunResult:
    """Summarizes one completed script step."""

    task_id: TaskId
    status: TaskStatus
    attempts: int
    message: str
    requested_castle: CastleIdentity | None = None
    provenance: dict[str, object] = field(default_factory=dict)


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
    world_map_survey_recorder: WorldMapSurveyRecorder | None = None
    policy: StepExecutionPolicy = field(default_factory=StepExecutionPolicy)

    def run(
        self,
        account: AccountConfig,
        script: PreparedRunScript,
        *,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None = None,
        castle_roster_store: CastleRosterStore | None = None,
        mail_archive_store: MailArchiveStore | None = None,
        chat_archive_store: ChatArchiveStore | None = None,
    ) -> RunResult:
        """Runs the provided script for one account target."""

        started_at = datetime.now(tz=UTC)
        step_results = [
            self._run_step(
                account,
                step,
                castle_roster_provider=castle_roster_provider,
                castle_roster_store=castle_roster_store,
                mail_archive_store=mail_archive_store,
                chat_archive_store=chat_archive_store,
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
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
    ) -> StepRunResult:
        """Executes one script step until it succeeds or fails."""

        before = self.observation_service.observe(f"{step.task.value}_before")
        before = self._align_step_castle_target(
            account=account,
            step=step,
            before=before,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
        )
        execution = self._execute_step_loop(
            account=account,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
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
            provenance=dict(step.provenance),
        )

    def _align_step_castle_target(
        self,
        *,
        account: AccountConfig,
        step: PreparedScriptStep,
        before: Observation,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
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
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
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
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
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
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
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
                    mail_archive_store=mail_archive_store,
                    chat_archive_store=chat_archive_store,
                )
            if not task.is_applicable(context, current_before):
                self._raise_task_verification_error(
                    f"Task '{step.task}' is not applicable on screen '{current_before.screen_type}'.",
                    task_id=step.task,
                    observation=current_before,
                    screen_type=current_before.screen_type,
                    label=f"{step.task.value}_failure_not_applicable",
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
                max_replans = task.max_replans_per_step(context)
                if max_replans is None:
                    max_replans = self.policy.max_replans_per_step
                if replans > max_replans:
                    self._raise_task_verification_error(
                        f"Task '{step.task}' exceeded the maximum allowed replans.",
                        task_id=step.task,
                        observation=after,
                        screen_type=after.screen_type,
                        label=f"{step.task.value}_failure_replan_limit",
                        replans=replans,
                    )
                current_before = after
                continue
            if result.retryable and attempts <= self.policy.max_retries_per_step:
                current_before = self.observation_service.observe(f"{step.task.value}_retry_{attempts}")
                continue
            self._raise_task_verification_error(
                result.message,
                task_id=step.task,
                observation=after,
                screen_type=after.screen_type,
                label=f"{step.task.value}_failure_result",
            )

    def _build_context(
        self,
        *,
        account: AccountConfig,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
        step: ScriptStep,
        parsed_params: Any,
        target_castle: CastleIdentity | None,
    ) -> TaskContext:
        """Builds the shared task context for one canonical task execution."""

        logger_extra = {**self.logger.extra, "task_id": step.task}
        if target_castle is not None:
            logger_extra["target_castle"] = f"{target_castle.kingdom}/{target_castle.castle_name}"
        mail_id = step.provenance.get("mail_id")
        if isinstance(mail_id, str) and mail_id.strip() != "":
            logger_extra["mail_id"] = mail_id
        schedule_id = step.provenance.get("schedule_id")
        if isinstance(schedule_id, str) and schedule_id.strip() != "":
            logger_extra["schedule_id"] = schedule_id
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
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
            observation_service=self.observation_service,
            world_map_survey_recorder=self.world_map_survey_recorder,
        )

    def _ensure_no_blocking_popup(
        self,
        observation: Observation,
        *,
        account: AccountConfig,
        castle_roster_store: CastleRosterStore | None,
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
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
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
            step=popup_step,
            parsed_params=popup_task.parse_params({}),
            target_castle=None,
            before=observation,
            allow_popup_recovery=False,
        )
        return execution.final_observation

    def _raise_task_verification_error(
        self,
        message: str,
        *,
        task_id: TaskId,
        observation: Observation | None,
        screen_type: object | None,
        label: str,
        **details: object,
    ) -> None:
        """Raises one task verification error after forcing a persisted failure artifact when needed."""

        artifact_path = None if observation is None or observation.artifact_path is None else str(observation.artifact_path)
        if artifact_path is None:
            failure_observation = self._capture_failure_observation(label)
            if failure_observation is not None and failure_observation.artifact_path is not None:
                artifact_path = str(failure_observation.artifact_path)
        raise TaskVerificationError(
            message,
            task_id=task_id,
            screen_type=screen_type,
            artifact_path=artifact_path,
            **details,
        )

    def _capture_failure_observation(self, label: str) -> Observation | None:
        """Captures one persisted full-runtime failure observation when the current one was ephemeral."""

        try:
            return self.observation_service.observe(
                label,
                request=ObservationRequest.full_runtime_default(),
                artifact_selection=observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            )
        except Exception:
            self.logger.exception("Failed to persist a debug artifact for task failure.")
            return None

