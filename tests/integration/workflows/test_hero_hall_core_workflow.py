"""Focused offline coverage for the typed Hero Hall workflow."""

from __future__ import annotations

from dataclasses import dataclass
import unittest

from pnc_automation.app.automation.daily_maintenance.core_hero_hall import (
    CoreHeroHallWorkflow,
)
from pnc_automation.app.automation.engine.core_workflow import WorkflowEffect
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
)
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from tests.support.pnc.observations import make_observation


class CoreHeroHallWorkflowTests(unittest.TestCase):
    """Proves the bounded Home route and one delegated canonical mutation call."""

    def setUp(self) -> None:
        """Build one typed checkpoint and successful fake outcome."""

        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-13",
            game_reset_id="2026-09-13T00",
            account_id="account",
            castle=CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22),
        )

    def test_spec_is_home_to_home_resource_changing_hero_hall(self) -> None:
        """Declares the exact mutation capability required by the core boundary."""

        spec = CoreHeroHallWorkflow(self.checkpoint).spec

        self.assertEqual("hero_hall", spec.name)
        self.assertEqual(ScreenType.PNC_HOME_CITY, spec.entry_screen)
        self.assertEqual(ScreenType.PNC_HOME_CITY, spec.exit_screen)
        self.assertEqual(WorkflowEffect.RESOURCE_CHANGING, spec.effect)
        self.assertEqual(DailyQuestId.HERO_HALL, spec.mutation_capability)

    def test_opens_hero_hall_and_delegates_once(self) -> None:
        """Uses the typed building route and delegates the mutation exactly once."""

        context = _FakeHeroHallContext()

        result = CoreHeroHallWorkflow(self.checkpoint).execute(context)

        self.assertEqual(self.checkpoint, result[0])
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, result[1].status)
        self.assertEqual(
            [
                ("open_building", HomeCityObjectId.HERO_HALL),
                ("recruit", self.checkpoint),
            ],
            context.calls,
        )

    def test_recruit_failure_propagates_without_replay(self) -> None:
        """Leaves canonical mutation failures visible and never invokes the seam twice."""

        context = _FakeHeroHallContext(recruit_error=RuntimeError("Hero Hall receipt ambiguous"))

        with self.assertRaisesRegex(RuntimeError, "receipt ambiguous"):
            CoreHeroHallWorkflow(self.checkpoint).execute(context)
        self.assertEqual(1, context.recruit_calls)

    def test_unrelated_outcome_is_rejected(self) -> None:
        """Rejects a context that returns an outcome for another mutation capability."""

        context = _FakeHeroHallContext(
            outcome=DailyTargetOutcome(
                quest_id=DailyQuestId.UPGRADE_RESEARCH,
                status=DailyTargetOutcomeStatus.SUCCESS,
                message="wrong capability",
            )
        )

        with self.assertRaisesRegex(ValueError, "unrelated mutation outcome"):
            CoreHeroHallWorkflow(self.checkpoint).execute(context)
        self.assertEqual(1, context.recruit_calls)


@dataclass
class _FakeHeroHallContext:
    """Supplies only the typed Hero Hall seams owned by the replacement core."""

    recruit_error: Exception | None = None
    outcome: DailyTargetOutcome | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.recruit_calls = 0

    def open_building(self, target: HomeCityObjectId) -> Observation:
        """Records the exact Hero Hall building route."""

        self.calls.append(("open_building", target))
        return make_observation(ScreenType.PNC_HERO_HALL)

    def recruit_hero_hall(
        self, checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Returns one canonical result or propagates its failure unchanged."""

        self.recruit_calls += 1
        self.calls.append(("recruit", checkpoint))
        if self.recruit_error is not None:
            raise self.recruit_error
        return checkpoint, self.outcome or DailyTargetOutcome(
            quest_id=DailyQuestId.HERO_HALL,
            status=DailyTargetOutcomeStatus.SUCCESS,
            message="Hero Hall complete",
        )


if __name__ == "__main__":
    unittest.main()
