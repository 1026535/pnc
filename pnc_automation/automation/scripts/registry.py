"""Task registry for concrete automation task implementations."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.automation.task import BaseAutomationTask, TaskId
from pnc_automation.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.automation.tasks.campaign_task import CampaignTask
from pnc_automation.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.automation.tasks.gathering_task import GatheringTask
from pnc_automation.automation.tasks.login_task import LoginTask
from pnc_automation.automation.tasks.popup_recovery_task import PopupRecoveryTask
from pnc_automation.automation.tasks.research_task import ResearchTask
from pnc_automation.automation.tasks.select_castle_task import SelectCastleTask


@dataclass(frozen=True, slots=True)
class TaskRegistry:
    """Owns concrete task lookup by canonical task id."""

    tasks: tuple[BaseAutomationTask, ...]

    def require(self, task_id: TaskId) -> BaseAutomationTask:
        """Returns a registered task or fails fast."""

        for task in self.tasks:
            if task.id == task_id:
                return task
        raise KeyError(f"Task '{task_id}' is not registered.")


def build_default_task_registry() -> TaskRegistry:
    """Builds the default concrete task registry for the platform."""

    return TaskRegistry(
        tasks=(
            EnsureGameRunningTask(),
            PopupRecoveryTask(),
            LoginTask(),
            SelectCastleTask(),
            BuildingUpgradeTask(),
            ResearchTask(),
            GatheringTask(),
            CampaignTask(),
        )
    )
