"""Composition of the default concrete automation tasks."""

from __future__ import annotations

from functools import partial

from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.automation.tasks.building_construction_task import BuildingConstructionTask
from pnc_automation.app.automation.tasks.campaign_task import CampaignTask
from pnc_automation.app.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.app.automation.tasks.gathering_task import GatheringTask
from pnc_automation.app.automation.tasks.login_task import LoginTask
from pnc_automation.app.automation.tasks.open_building_task import OpenBuildingTask
from pnc_automation.app.automation.tasks.popup_recovery_task import PopupRecoveryTask
from pnc_automation.app.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask
from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.app.automation.tasks.send_chat_message_task import (
    SendAllianceChatMessageTask,
    SendWorldChatMessageTask,
)
from pnc_automation.app.automation.tasks.send_mail_task import SendMailTask
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import (
    CastleTargetPolicy,
    CoreWorkflowTaskDefinition,
    TaskId,
    require_no_params,
)
from pnc_automation.app.pnc.domain.mail import parse_collect_mail_params


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
            SendMailTask(),
            CoreWorkflowTaskDefinition(
                id=TaskId.COLLECT_MAIL,
                castle_target_policy=CastleTargetPolicy.OPTIONAL,
                parameter_parser=partial(parse_collect_mail_params, task_label=TaskId.COLLECT_MAIL),
            ),
            CoreWorkflowTaskDefinition(
                id=TaskId.COLLECT_KINGDOM_CHAT,
                castle_target_policy=CastleTargetPolicy.OPTIONAL,
                parameter_parser=partial(require_no_params, TaskId.COLLECT_KINGDOM_CHAT),
            ),
            OpenBuildingTask(),
            BuildingConstructionTask(),
            BuildingUpgradeTask(),
            ResearchTask(),
            GatheringTask(),
            CampaignTask(),
        )
    )
