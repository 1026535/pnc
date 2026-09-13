"""Typed Hero Hall workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTaskCheckpoint,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType


@dataclass(frozen=True, slots=True)
class CoreHeroHallWorkflow(CoreWorkflow[tuple[DailyTaskCheckpoint, DailyTargetOutcome]]):
    """Open Hero Hall and delegate one authorized canonical Hero Hall run."""

    checkpoint: DailyTaskCheckpoint

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="hero_hall",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.RESOURCE_CHANGING,
        mutation_capability=DailyQuestId.HERO_HALL,
    )

    def __post_init__(self) -> None:
        """Reject malformed checkpoints before navigation or mutation."""

        if not isinstance(self.checkpoint, DailyTaskCheckpoint):
            raise TypeError("CoreHeroHallWorkflow requires a DailyTaskCheckpoint.")

    @property
    def spec(self) -> WorkflowSpec:
        """Return the fixed resource-changing Home-to-Home contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Open the typed Hero Hall route, then delegate exactly once to the boundary."""

        context.open_building(HomeCityObjectId.HERO_HALL)
        checkpoint, outcome = context.recruit_hero_hall(self.checkpoint)
        if outcome.quest_id != DailyQuestId.HERO_HALL:
            raise ValueError("WorkflowContext.recruit_hero_hall returned an unrelated mutation outcome.")
        return checkpoint, outcome
