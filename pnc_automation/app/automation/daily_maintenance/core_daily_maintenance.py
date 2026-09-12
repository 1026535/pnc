"""Resource changing Daily Quest workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.automation.daily_maintenance.coordinator import (
    DailyMaintenanceCoordinator,
    DailyMaintenanceResult,
    ForbiddenDailyMutationExecutor,
)
from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyQuestRow,
    DailyTaskCheckpoint,
    DailyTargetOutcome,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


@dataclass(frozen=True, slots=True)
class _CoreDailyQuestSession:
    """Adapts the coordinator's Daily session to the typed core context."""

    context: WorkflowContext

    def open_daily_quest(self) -> None:
        """Navigates to Daily through the reviewed graph."""

        self.context.navigate(ScreenType.PNC_QUEST_DAILY)

    def observe_daily_quest(self, label: str) -> Observation:
        """Captures one fresh, expected Daily observation through the core."""

        del label
        return self.context.observe_content(expected_screen=ScreenType.PNC_QUEST_DAILY)

    def scroll_daily_quest(self, *, adjusted: bool) -> None:
        """Delegates one bounded Daily scroll to the core context."""

        self.context.scroll_daily_quest(adjusted=adjusted)

    def return_to_home(self) -> None:
        """Returns to Home through the typed navigation graph."""

        self.context.navigate(ScreenType.PNC_HOME_CITY)


@dataclass(frozen=True, slots=True)
class _CoreDailyClaimExecutor:
    """Adapts canonical claim execution to the authorized core boundary."""

    context: WorkflowContext

    def claim(
        self,
        *,
        row: DailyQuestRow,
        checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Claims one row through the context's exact-authority mutation seam."""

        return self.context.claim_daily_reward(row, checkpoint)


@dataclass(frozen=True, slots=True)
class CoreDailyMaintenanceWorkflow(CoreWorkflow[DailyMaintenanceResult]):
    """Runs the claim-only Daily lifecycle with typed Home boundaries."""

    target: DailyMaintenanceTargetConfig
    checkpoint: DailyTaskCheckpoint
    journal_store: DailyRunJournalStore

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="daily_maintenance",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.RESOURCE_CHANGING,
        mutation_capability=DailyQuestId.CLAIM_COMPLETED,
    )

    def __post_init__(self) -> None:
        """Rejects action capabilities before entering the connected runtime."""

        if not isinstance(self.target, DailyMaintenanceTargetConfig):
            raise TypeError("CoreDailyMaintenanceWorkflow requires a DailyMaintenanceTargetConfig.")
        if not isinstance(self.checkpoint, DailyTaskCheckpoint):
            raise TypeError("CoreDailyMaintenanceWorkflow requires a DailyTaskCheckpoint.")
        if not isinstance(self.journal_store, DailyRunJournalStore):
            raise TypeError("CoreDailyMaintenanceWorkflow requires a DailyRunJournalStore.")
        if self.target.capabilities:
            raise PermissionError(
                "Core Daily maintenance supports CLAIM_COMPLETED only; action capabilities are not supported."
            )

    @property
    def spec(self) -> WorkflowSpec:
        """Returns the fixed resource-changing Home-to-Home contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> DailyMaintenanceResult:
        """Runs the canonical coordinator without duplicating parsing or retry policy."""

        coordinator = DailyMaintenanceCoordinator(
            session=_CoreDailyQuestSession(context),
            claim_executor=_CoreDailyClaimExecutor(context),
            capability_executor=ForbiddenDailyMutationExecutor(),
            journal_store=self.journal_store,
            catalog=DailyQuestCatalog(),
        )
        return coordinator.run(target=self.target, checkpoint=self.checkpoint)
