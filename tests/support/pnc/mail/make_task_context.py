"""Synthetic make_task_context fixture."""

from __future__ import annotations

from pnc_automation.app.authoring.scripts.models import ScriptStep
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.app.pnc.domain.castles import CastleIdentity



def _make_task_context(
    case: MailWorkflowTests,
    *,
    params: object,
    task_id: TaskId,
    mail_archive_store: MailArchiveStore | None = None,
    target_castle: CastleIdentity | None = None,
) -> TaskContext:
    """Builds one task context for mail task tests."""

    return TaskContext(
        account=case.account,
        castle_roster_provider=lambda: None,
        defaults=case.defaults,
        step=ScriptStep(task=task_id),
        params=params,
        flows=case.flows,
        logger=case.logger,
        target_castle=target_castle,
        mail_archive_store=mail_archive_store,
    )
