"""Resource-item feature acceptance tests shared by both canary castles."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.resource_item import (
    ResourceItemExecutor,
)
from pnc_automation.app.pnc.domain.resource_items import (
    ResourceInventory,
    ResourceInventoryStatus,
    ResourceItem,
    smallest_resource_item,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationDispatcher
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId, DailyTargetOutcomeStatus, DailyTaskCheckpoint, MutationIntent, MutationIntentState,
)
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


class ResourceItemCanaryTests(unittest.TestCase):
    """Proves selection, one-use receipts, empty inventory and no ambiguous replay."""

    def setUp(self) -> None:
        """Builds a private journal without game or network access."""

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary.name))
        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-08", game_reset_id="pnc-reset-2026-09-08-00",
            account_id="mega_old_acc", castle=CastleIdentity("K157", "NPC 2", 22),
        )

    def test_smallest_numeric_amount_wins_across_resources(self) -> None:
        """Does not choose a visible Food pack before scanning smaller Gold packs."""

        items = (
            ResourceItem("food-large", "food", 1000, 8, "a"),
            ResourceItem("gold-small", "gold", 100, 2, "b"),
        )
        self.assertEqual("gold-small", smallest_resource_item(self._inventory(items)).item_id)

    def test_ties_follow_food_wood_iron_gold(self) -> None:
        """Applies the exact interview priority independent of list order."""

        items = tuple(ResourceItem(kind, kind, 100, 1, kind) for kind in ("gold", "iron", "wood", "food"))
        for expected in ("food", "wood", "iron", "gold"):
            self.assertEqual(expected, smallest_resource_item(self._inventory(items)).resource)
            items = tuple(item for item in items if item.resource != expected)

    def test_incomplete_scan_cannot_select_or_spend(self) -> None:
        """A partial viewport never establishes the globally smallest pack."""

        with self.assertRaisesRegex(ValueError, "full"):
            smallest_resource_item(ResourceInventory((), False, ("partial.png",)))

    def test_one_use_commits_and_second_run_does_not_use_again(self) -> None:
        """Uses the shared mutation journal instead of a canary-specific retry counter."""

        item = ResourceItem("food", "food", 1000, 3, "before")
        session = Mock()
        session.scan_inventory.return_value = self._inventory((item,))
        session.focus_item.return_value = item
        session.observe_item.return_value = ResourceItem("food", "food", 1000, 2, "after")
        session.daily_requirement_completed.return_value = True
        session.artifact_paths.return_value = ("before.png", "after.png")
        executor = ResourceItemExecutor(session, JournaledMutationDispatcher(self.store))
        checkpoint, result = executor.execute(checkpoint=self.checkpoint, allow_empty_skip=False)
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, result.status)
        session.use_one.assert_called_once_with(item)
        executor.execute(checkpoint=checkpoint, allow_empty_skip=False)
        session.use_one.assert_called_once()

    def test_empty_cookie_inventory_skips_without_purchase(self) -> None:
        """Supports the approved inventory-only free-cookies canary."""

        session = Mock()
        session.scan_inventory.return_value = self._inventory(())
        executor = ResourceItemExecutor(session, JournaledMutationDispatcher(self.store))
        _, result = executor.execute(checkpoint=self.checkpoint, allow_empty_skip=True)
        self.assertEqual(DailyTargetOutcomeStatus.APPLICABILITY_SKIP, result.status)
        session.use_one.assert_not_called()

    def test_empty_npc_inventory_remains_pending(self) -> None:
        """Does not buy a pack or turn missing NPC proof into a successful skip."""

        session = Mock()
        session.scan_inventory.return_value = self._inventory(())
        executor = ResourceItemExecutor(session, JournaledMutationDispatcher(self.store))
        _, result = executor.execute(checkpoint=self.checkpoint, allow_empty_skip=False)
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, result.status)
        session.use_one.assert_not_called()

    def test_unknown_inventory_status_remains_pending_without_selecting_a_pack(self) -> None:
        """Visible unresolved cards cannot be reinterpreted as an empty or spendable inventory."""

        session = Mock()
        session.scan_inventory.return_value = ResourceInventory(
            (), False, ("unknown.png",), ResourceInventoryStatus.UNKNOWN, ("clipped_card",)
        )
        executor = ResourceItemExecutor(session, JournaledMutationDispatcher(self.store))

        _, result = executor.execute(checkpoint=self.checkpoint, allow_empty_skip=True)

        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, result.status)
        session.focus_item.assert_not_called()
        session.use_one.assert_not_called()

    def test_unchanged_inventory_cannot_pass_or_replay(self) -> None:
        """An apparent click without consumption evidence remains unresolved."""

        item = ResourceItem("food", "food", 1000, 3, "before")
        session = Mock()
        session.scan_inventory.return_value = self._inventory((item,))
        session.focus_item.return_value = item
        session.observe_item.return_value = item
        session.daily_requirement_completed.return_value = False
        session.artifact_paths.return_value = ("before.png", "after.png")
        executor = ResourceItemExecutor(session, JournaledMutationDispatcher(self.store))
        checkpoint, result = executor.execute(checkpoint=self.checkpoint, allow_empty_skip=False)
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, result.status)
        executor.execute(checkpoint=checkpoint, allow_empty_skip=False)
        session.use_one.assert_called_once()

    def test_dispatched_use_reconciles_without_replaying(self) -> None:
        """Recovers a crash after dispatch by observing stock and Daily state only."""

        item = ResourceItem("gold:50:normal", "gold", 50, 276, "after")
        intent = MutationIntent(
            operation_id="resource-item-001",
            quest_id=DailyQuestId.USE_RESOURCE_ITEM,
            state=MutationIntentState.DISPATCHED,
            expected_precondition="gold:50:normal: owned=277",
            expected_postcondition="gold:50:normal: owned=276; Daily complete",
        )
        checkpoint = self.checkpoint.__class__(
            maintenance_date=self.checkpoint.maintenance_date,
            game_reset_id=self.checkpoint.game_reset_id,
            account_id=self.checkpoint.account_id,
            castle=self.checkpoint.castle,
            mutation_intents=(intent,),
        )
        session = Mock()
        session.scan_inventory.return_value = self._inventory((item,))
        session.daily_requirement_completed.return_value = True
        session.artifact_paths.return_value = ("post.png", "daily.png")
        executor = ResourceItemExecutor(session, JournaledMutationDispatcher(self.store))

        updated, result = executor.execute(checkpoint=checkpoint, allow_empty_skip=False)

        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, result.status)
        self.assertEqual(MutationIntentState.COMMITTED, updated.mutation_intents[0].state)
        session.use_one.assert_not_called()

    def test_changed_identity_before_use_is_rejected(self) -> None:
        """Does not dispatch after focusing a different inventory item."""

        item = ResourceItem("food", "food", 1000, 3, "before")
        session = Mock()
        session.scan_inventory.return_value = self._inventory((item,))
        session.focus_item.return_value = ResourceItem("wood", "wood", 1000, 3, "other")
        executor = ResourceItemExecutor(session, JournaledMutationDispatcher(self.store))
        with self.assertRaisesRegex(ValueError, "changed"):
            executor.execute(checkpoint=self.checkpoint, allow_empty_skip=False)
        session.use_one.assert_not_called()

    @staticmethod
    def _inventory(items: tuple[ResourceItem, ...]) -> ResourceInventory:
        """Returns a synthetic, explicitly exhausted inventory scan."""

        return ResourceInventory(items, True, ("full-scan.png",))
