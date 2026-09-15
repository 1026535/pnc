"""Focused offline coverage for the typed Resource Item workflow."""

from __future__ import annotations

from dataclasses import dataclass
import unittest

from pnc_automation.app.automation.daily_maintenance.core_resource_item import CoreResourceItemWorkflow
from pnc_automation.app.automation.engine.core_workflow import WorkflowEffect
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType


class CoreResourceItemWorkflowTests(unittest.TestCase):
    """Prove the exact mutation spec and one delegated context operation."""

    def setUp(self) -> None:
        """Build one typed checkpoint used by each workflow invocation."""

        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-13",
            game_reset_id="2026-09-13T00",
            account_id="account",
            castle=CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22),
        )

    def test_spec_is_home_to_home_resource_changing_resource_item(self) -> None:
        """Declares the exact USE_RESOURCE_ITEM mutation capability."""

        spec = CoreResourceItemWorkflow(self.checkpoint).spec

        self.assertEqual("resource_item", spec.name)
        self.assertEqual(ScreenType.PNC_HOME_CITY, spec.entry_screen)
        self.assertEqual(ScreenType.PNC_HOME_CITY, spec.exit_screen)
        self.assertEqual(WorkflowEffect.RESOURCE_CHANGING, spec.effect)
        self.assertEqual(DailyQuestId.USE_RESOURCE_ITEM, spec.mutation_capability)

    def test_delegates_once_with_empty_skip_policy(self) -> None:
        """Passes the explicit empty-inventory policy unchanged to the context."""

        context = _FakeResourceItemContext()

        result = CoreResourceItemWorkflow(self.checkpoint, allow_empty_skip=True).execute(context)

        self.assertEqual(self.checkpoint, result[0])
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, result[1].status)
        self.assertEqual([("use_resource_item", self.checkpoint, True)], context.calls)

    def test_failure_propagates_without_replay(self) -> None:
        """Leaves a canonical mutation failure visible and never retries it."""

        context = _FakeResourceItemContext(error=RuntimeError("resource receipt ambiguous"))

        with self.assertRaisesRegex(RuntimeError, "receipt ambiguous"):
            CoreResourceItemWorkflow(self.checkpoint).execute(context)
        self.assertEqual(1, context.calls_count)

    def test_unrelated_outcome_is_rejected(self) -> None:
        """Rejects a context result for another Daily capability."""

        context = _FakeResourceItemContext(
            outcome=DailyTargetOutcome(
                quest_id=DailyQuestId.HERO_HALL,
                status=DailyTargetOutcomeStatus.SUCCESS,
                message="wrong capability",
            )
        )

        with self.assertRaisesRegex(ValueError, "unrelated mutation outcome"):
            CoreResourceItemWorkflow(self.checkpoint).execute(context)
        self.assertEqual(1, context.calls_count)


@dataclass
class _FakeResourceItemContext:
    """Supplies only the typed Resource Item context seam."""

    error: Exception | None = None
    outcome: DailyTargetOutcome | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.calls_count = 0

    def use_resource_item(
        self,
        checkpoint: DailyTaskCheckpoint,
        *,
        allow_empty_skip: bool,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Return one canonical result or propagate its failure unchanged."""

        self.calls_count += 1
        self.calls.append(("use_resource_item", checkpoint, allow_empty_skip))
        if self.error is not None:
            raise self.error
        return checkpoint, self.outcome or DailyTargetOutcome(
            quest_id=DailyQuestId.USE_RESOURCE_ITEM,
            status=DailyTargetOutcomeStatus.SUCCESS,
            message="resource use complete",
        )


if __name__ == "__main__":
    unittest.main()
