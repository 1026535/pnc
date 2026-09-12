"""Exactly-once resource-pack use shared by canary and Daily feature execution."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher, MutationOperation, MutationReconciliation,
)
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyApplicabilitySkipReason, DailyQuestId, DailyTargetOutcome,
    DailyTargetOutcomeStatus, DailyTaskCheckpoint, MutationIntent, MutationIntentState,
)
from pnc_automation.app.pnc.domain.resource_items import (
    ResourceInventory,
    ResourceInventoryStatus,
    ResourceItem,
    smallest_resource_item,
)


class ResourceItemSession(Protocol):
    """Uses canonical observations and visual geometry; offers no buying/bulk-use API."""

    def scan_inventory(self) -> ResourceInventory:
        """Returns an observed full Resource-tab scan or raises on unknown content."""

    def focus_item(self, item: ResourceItem) -> ResourceItem:
        """Returns freshly reselected item semantics before any use action."""

    def use_one(self, item: ResourceItem) -> None:
        """Revalidates the fingerprint and taps only this item's blue single Use."""

    def observe_item(self, item: ResourceItem) -> ResourceItem | None:
        """Returns post-use owned count; absence alone is not consumption proof."""

    def daily_requirement_completed(self) -> bool:
        """Returns whether fresh Daily evidence proves the resource-use requirement."""

    def artifact_paths(self) -> tuple[str, ...]:
        """Returns the inspected pre-action and post-action evidence paths."""


@dataclass(slots=True)
class ResourceItemExecutor:
    """Owns one resource-use feature mutation through the canonical journal."""

    session: ResourceItemSession
    dispatcher: JournaledMutationDispatcher

    def execute(
        self, *, checkpoint: DailyTaskCheckpoint, allow_empty_skip: bool,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Uses one minimum owned pack or reports an explicit no-mutation outcome."""

        prior = tuple(
            intent for intent in checkpoint.mutation_intents
            if intent.quest_id == DailyQuestId.USE_RESOURCE_ITEM
        )
        if prior:
            if all(intent.state == MutationIntentState.COMMITTED for intent in prior):
                return checkpoint, DailyTargetOutcome(
                    DailyQuestId.USE_RESOURCE_ITEM,
                    DailyTargetOutcomeStatus.SUCCESS,
                    "Previously committed resource use.",
                    artifact_paths=_intent_artifacts(prior),
                )
            if len(prior) == 1 and prior[0].state in {
                MutationIntentState.DISPATCHED,
                MutationIntentState.RECONCILED,
            }:
                return self._reconcile_existing(
                    checkpoint=checkpoint,
                    intent=prior[0],
                )
            return checkpoint, DailyTargetOutcome(
                DailyQuestId.USE_RESOURCE_ITEM,
                DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
                "Unresolved resource use; no replay.",
                artifact_paths=_intent_artifacts(prior),
            )
        inventory = self.session.scan_inventory()
        if inventory.status != ResourceInventoryStatus.COMPLETE:
            return checkpoint, DailyTargetOutcome(
                DailyQuestId.USE_RESOURCE_ITEM,
                DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
                "Resource inventory status is unknown; no pack was selected.",
                artifact_paths=inventory.artifact_paths,
            )
        selected = smallest_resource_item(inventory)
        if selected is None:
            return checkpoint, DailyTargetOutcome(
                DailyQuestId.USE_RESOURCE_ITEM,
                DailyTargetOutcomeStatus.APPLICABILITY_SKIP
                if allow_empty_skip else DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
                "No existing resource pack; no purchase attempted.",
                skip_reason=DailyApplicabilitySkipReason.INSUFFICIENT_INVENTORY if allow_empty_skip else None,
                artifact_paths=inventory.artifact_paths,
            )
        before = self.session.focus_item(selected)
        if before.identity != selected.identity or before.owned != selected.owned:
            raise ValueError("Resource item changed after inventory scan; no use dispatched.")

        def reconcile() -> MutationReconciliation:
            """Requires exactly one consumed pack and fresh Daily completion evidence."""

            after = self.session.observe_item(before)
            same_item = after is not None and after.identity == before.identity
            consumed_one = same_item and after.owned == before.owned - 1
            complete = consumed_one and self.session.daily_requirement_completed()
            return MutationReconciliation(
                postcondition_proven=complete,
                original_precondition_proven=same_item and after.owned == before.owned,
                artifact_paths=self.session.artifact_paths(),
            )

        result = self.dispatcher.execute(
            checkpoint=checkpoint,
            operation=MutationOperation(
                operation_id="resource-item-001",
                quest_id=DailyQuestId.USE_RESOURCE_ITEM,
                expected_precondition=f"{before.item_id}: owned={before.owned}",
                expected_postcondition=f"{before.item_id}: owned={before.owned - 1}; Daily complete",
            ),
            dispatch=lambda: self.session.use_one(before),
            reconcile=reconcile,
        )
        return result.checkpoint, DailyTargetOutcome(
            DailyQuestId.USE_RESOURCE_ITEM,
            DailyTargetOutcomeStatus.SUCCESS if result.committed else DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
            "One resource pack consumed and Daily verified."
            if result.committed else "Resource-use result not proved; no automatic replay.",
            artifact_paths=result.artifact_paths,
        )

    def _reconcile_existing(
        self, *, checkpoint: DailyTaskCheckpoint, intent: MutationIntent,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Reconciles an already-dispatched item without issuing a second use action."""

        item_id, expected_owned = _parse_resource_precondition(intent.expected_precondition)
        inventory = self.session.scan_inventory()
        if inventory.status != ResourceInventoryStatus.COMPLETE:
            result = self.dispatcher.reconcile_existing(
                checkpoint=checkpoint,
                operation_id=intent.operation_id,
                reconcile=lambda: MutationReconciliation(
                    postcondition_proven=False,
                    original_precondition_proven=False,
                    artifact_paths=inventory.artifact_paths,
                ),
            )
            return result.checkpoint, DailyTargetOutcome(
                DailyQuestId.USE_RESOURCE_ITEM,
                DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
                "Previously dispatched resource use remains unresolved; inventory status is unknown.",
                artifact_paths=result.artifact_paths,
            )
        observed = next((item for item in inventory.items if item.item_id == item_id), None)
        consumed_one = observed is not None and observed.owned == expected_owned - 1
        complete = consumed_one and self.session.daily_requirement_completed()
        result = self.dispatcher.reconcile_existing(
            checkpoint=checkpoint,
            operation_id=intent.operation_id,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=complete,
                original_precondition_proven=(
                    observed is not None and observed.owned == expected_owned
                ),
                artifact_paths=self.session.artifact_paths(),
            ),
        )
        return result.checkpoint, DailyTargetOutcome(
            DailyQuestId.USE_RESOURCE_ITEM,
            DailyTargetOutcomeStatus.SUCCESS
            if result.committed else DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
            "Previously dispatched resource use was reconciled and Daily verified."
            if result.committed else "Previously dispatched resource use remains unresolved; no replay.",
            artifact_paths=result.artifact_paths,
        )


_RESOURCE_PRECONDITION = re.compile(r"^(?P<item_id>.+): owned=(?P<owned>\d+)$")


def _parse_resource_precondition(value: str) -> tuple[str, int]:
    """Parses the durable resource identity/count needed for no-replay reconciliation."""

    match = _RESOURCE_PRECONDITION.fullmatch(value)
    if match is None:
        raise ValueError("Resource mutation journal has an invalid precondition.")
    return match.group("item_id"), int(match.group("owned"))


def _intent_artifacts(intents: tuple[MutationIntent, ...]) -> tuple[str, ...]:
    """Returns persisted mutation evidence without fabricating paths."""

    paths: list[str] = []
    for intent in intents:
        for path in intent.metadata.get("artifact_paths", ()):
            if isinstance(path, str) and path not in paths:
                paths.append(path)
    return tuple(paths)
