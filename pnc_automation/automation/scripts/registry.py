"""Task registry for concrete automation task implementations."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnc_automation.automation.scripts.models import PreparedRunScript, PreparedScriptStep, RunScript
from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId
from pnc_automation.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.automation.tasks.campaign_task import CampaignTask
from pnc_automation.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.automation.tasks.gathering_task import GatheringTask
from pnc_automation.automation.tasks.login_task import LoginTask
from pnc_automation.automation.tasks.popup_recovery_task import PopupRecoveryTask
from pnc_automation.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask
from pnc_automation.automation.tasks.research_task import ResearchTask
from pnc_automation.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.automation.tasks.send_chat_message_task import (
    SendAllianceChatMessageTask,
    SendWorldChatMessageTask,
)
from pnc_automation.errors import ScriptValidationError


@dataclass(frozen=True, slots=True)
class TaskRegistry:
    """Owns concrete task lookup by canonical task id."""

    tasks: tuple[BaseAutomationTask, ...]
    _tasks_by_id: dict[TaskId, BaseAutomationTask] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Builds the canonical task lookup table and rejects duplicate ids."""

        tasks_by_id: dict[TaskId, BaseAutomationTask] = {}
        duplicates: list[TaskId] = []
        for task in self.tasks:
            if task.id in tasks_by_id:
                duplicates.append(task.id)
                continue
            tasks_by_id[task.id] = task
        if duplicates:
            duplicate_labels = ", ".join(str(task_id) for task_id in duplicates)
            raise ValueError(f"TaskRegistry received duplicate task ids: {duplicate_labels}.")
        object.__setattr__(self, "_tasks_by_id", tasks_by_id)

    def require(self, task_id: TaskId) -> BaseAutomationTask:
        """Returns a registered task or fails fast."""

        try:
            return self._tasks_by_id[task_id]
        except KeyError as error:
            raise KeyError(f"Task '{task_id}' is not registered.") from error

    def prepare_script(self, script: RunScript) -> PreparedRunScript:
        """Converts a raw run script into an execution-ready script with typed params."""

        prepared_steps: list[PreparedScriptStep] = []
        for index, step in enumerate(script.steps):
            try:
                task = self.require(step.task)
            except KeyError as error:
                raise ScriptValidationError(
                    f"Task '{step.task}' is not registered in the active task registry.",
                    step_index=index,
                    task=step.task,
                ) from error
            _validate_castle_target_policy(task, step_index=index, step=step)
            try:
                parsed_params = task.parse_params(step.params)
            except ScriptValidationError as error:
                details = dict(error.details)
                details.setdefault("step_index", index)
                details.setdefault("task", step.task)
                raise ScriptValidationError(error.message, **details) from error
            prepared_steps.append(
                PreparedScriptStep(
                    script_step=step,
                    parsed_params=parsed_params,
                    castle_target_policy=task.castle_target_policy,
                )
            )
        return PreparedRunScript(name=script.name, path=script.path, steps=tuple(prepared_steps))


def _validate_castle_target_policy(task: BaseAutomationTask, *, step_index: int, step: object) -> None:
    """Rejects script steps whose castle targeting does not match the task contract."""

    task_id = getattr(step, "task", None)
    target_castle = getattr(step, "castle", None)
    if task.castle_target_policy == CastleTargetPolicy.DISALLOWED and target_castle is not None:
        raise ScriptValidationError(
            f"Task '{task.id}' does not accept a step-level castle target.",
            step_index=step_index,
            task=task_id,
            castle=target_castle,
        )
    if task.castle_target_policy == CastleTargetPolicy.REQUIRED and target_castle is None:
        raise ScriptValidationError(
            f"Task '{task.id}' requires a step-level castle target.",
            step_index=step_index,
            task=task_id,
        )


def build_default_task_registry() -> TaskRegistry:
    """Builds the default concrete task registry for the platform."""

    return TaskRegistry(
        tasks=(
            EnsureGameRunningTask(),
            PopupRecoveryTask(),
            LoginTask(),
            SelectCastleTask(),
            RefreshCastleRosterTask(),
            SendAllianceChatMessageTask(),
            SendWorldChatMessageTask(),
            BuildingUpgradeTask(),
            ResearchTask(),
            GatheringTask(),
            CampaignTask(),
        )
    )
