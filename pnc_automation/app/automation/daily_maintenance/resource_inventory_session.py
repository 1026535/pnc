"""Canonical Resource inventory traversal shared by connected adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.resource_items import (
    ResourceInventory,
    ResourceInventoryStatus,
    ResourceItem,
)


class ResourceInventorySession(ABC):
    """Own one canonical, bounded Resource inventory scan and row conversion."""

    max_viewports: int

    def use_one(self, item: ResourceItem) -> None:
        """Reacquire the exact row fingerprint and dispatch only its single Use action."""

        before = self._observe("resource_use_pre")
        candidates = tuple(candidate for candidate in self._items(before) if candidate.identity == item.identity)
        if len(candidates) != 1 or candidates[0] != item:
            raise ValueError("Resource item fingerprint changed before single Use.")
        if not self._execute_single_use(
            TapListEntryAction(
                reason="use_one_smallest_resource_pack",
                entry_kind=ListEntryKind.RESOURCE_ITEM,
                metadata_key="observation_fingerprint",
                metadata_value=item.fingerprint,
                use_action_point=True,
            ), before,
        ):
            raise RuntimeError("Resource item Use was not executed; its journal prevents replay.")

    @abstractmethod
    def _execute_single_use(self, action: TapListEntryAction, observation: Observation) -> bool:
        """Dispatch the canonical single-row action through the existing observed executor."""

    def scan_inventory(self) -> ResourceInventory:
        """Proves top and bottom with bounded adjusted swipes before selecting any pack."""

        self._open_inventory()
        current = self._stable("resource_scan_start")
        initial_unresolved_reasons = self._require_complete_view(current)
        if initial_unresolved_reasons:
            return ResourceInventory(
                self._best_effort_items(current),
                False,
                self.artifact_paths(),
                ResourceInventoryStatus.UNKNOWN,
                initial_unresolved_reasons,
            )
        collected: dict[tuple[str, str, int], ResourceItem] = {}
        for item in self._items(current):
            collected[item.identity] = item
        current = self._reach_top(current)
        for index in range(self.max_viewports):
            unresolved_reasons = self._require_complete_view(current)
            if unresolved_reasons:
                return ResourceInventory(
                    tuple(collected.values()),
                    False,
                    self.artifact_paths(),
                    ResourceInventoryStatus.UNKNOWN,
                    unresolved_reasons,
                )
            for item in self._items(current):
                previous = collected.get(item.identity)
                if previous is not None and previous.owned != item.owned:
                    raise ValueError("Resource inventory changed during the full scan.")
                collected[item.identity] = item
            after = self._scroll(current, upward=False, adjusted=False)
            after_unresolved_reasons = self._require_complete_view(after)
            if after_unresolved_reasons:
                return ResourceInventory(
                    tuple(collected.values()),
                    False,
                    self.artifact_paths(),
                    ResourceInventoryStatus.UNKNOWN,
                    after_unresolved_reasons,
                )
            if self._signature(after) == self._signature(current):
                adjusted = self._scroll(after, upward=False, adjusted=True)
                adjusted_unresolved_reasons = self._require_complete_view(adjusted)
                if adjusted_unresolved_reasons:
                    return ResourceInventory(
                        tuple(collected.values()),
                        False,
                        self.artifact_paths(),
                        ResourceInventoryStatus.UNKNOWN,
                        adjusted_unresolved_reasons,
                    )
                if self._signature(adjusted) == self._signature(after):
                    return ResourceInventory(tuple(collected.values()), True, self.artifact_paths())
                after = adjusted
            current = after
        raise ValueError("Resource inventory full scan exceeded its viewport budget.")

    def focus_item(self, item: ResourceItem) -> ResourceItem:
        """Moves back through the proved inventory and freshly resolves the chosen item."""

        current = self._stable("resource_focus_start", extra_retries=3)
        for index in range(self.max_viewports):
            selected = next((candidate for candidate in self._items(current) if candidate.identity == item.identity), None)
            if selected is not None:
                return selected
            after = self._scroll(current, upward=True, adjusted=False, fine=True)
            if self._signature(after) == self._signature(current):
                after = self._scroll(after, upward=True, adjusted=True, fine=True)
                if self._signature(after) == self._signature(current):
                    break
            current = after
        raise ValueError("Chosen resource item is no longer present in the proved inventory.")

    def observe_item(self, item: ResourceItem) -> ResourceItem | None:
        """Reads the same item's stock after the one dispatched use."""

        after = self._observe("resource_use_post")
        return next((candidate for candidate in self._items(after) if candidate.identity == item.identity), None)

    @abstractmethod
    def _open_inventory(self) -> None:
        """Open the typed Resource inventory through the connected adapter."""

    @abstractmethod
    def _observe(self, label: str) -> Observation:
        """Capture one fresh, validated Resource inventory observation."""

    @abstractmethod
    def _scroll(
        self,
        before: Observation,
        *,
        upward: bool,
        adjusted: bool,
        fine: bool = False,
    ) -> Observation:
        """Scroll once through the adapter's canonical observed-action path."""

    @abstractmethod
    def artifact_paths(self) -> tuple[str, ...]:
        """Return captured inventory and mutation evidence in observation order."""

    def _stable(self, label: str, *, extra_retries: int = 0) -> Observation:
        """Requires two agreeing frames, with bounded retries for transient live overlays."""

        before = self._observe(f"{label}_first")
        after = self._observe(f"{label}_second")
        for attempt in range(extra_retries + 1):
            if self._signature(before) == self._signature(after):
                return after
            before = after
            suffix = "settled" if attempt == 0 else f"settled_{attempt + 1}"
            after = self._observe(f"{label}_{suffix}")
        if self._signature(before) == self._signature(after):
            return after
        raise ValueError("Resource inventory geometry or stock is unstable.")

    def _reach_top(self, current: Observation) -> Observation:
        """Proves the starting inventory edge instead of assuming the first viewport is top."""

        for index in range(self.max_viewports):
            after = self._scroll(current, upward=True, adjusted=False)
            if self._require_complete_view(after):
                return after
            if self._signature(after) == self._signature(current):
                adjusted = self._scroll(after, upward=True, adjusted=True)
                if self._require_complete_view(adjusted):
                    return adjusted
                if self._signature(adjusted) == self._signature(after):
                    return adjusted
                after = adjusted
            current = after
        raise ValueError("Resource inventory top could not be proved within the swipe budget.")

    @staticmethod
    def _items(observation: Observation) -> tuple[ResourceItem, ...]:
        """Converts only exact resource-row metadata with visual action provenance."""

        items: list[ResourceItem] = []
        identities: set[tuple[str, str, int]] = set()
        for entry in observation.entries(ListEntryKind.RESOURCE_ITEM):
            item = ResourceInventorySession._item_from_entry(entry)
            if item is None:
                raise ValueError("Resource item requires a complete visual single-Use action row.")
            if item.identity in identities:
                raise ValueError("Resource inventory contains duplicate item identities in one observation.")
            identities.add(item.identity)
            items.append(item)
        return tuple(items)

    @staticmethod
    def _best_effort_items(observation: Observation) -> tuple[ResourceItem, ...]:
        """Retain independently valid rows while an inventory remains explicitly unknown."""

        return tuple(
            item
            for entry in observation.entries(ListEntryKind.RESOURCE_ITEM)
            if (item := ResourceInventorySession._item_from_entry(entry)) is not None
        )

    @staticmethod
    def _item_from_entry(entry: object) -> ResourceItem | None:
        """Build one resource item only when all action and identity evidence is present."""

        if not isinstance(entry, DetectedListEntry):
            return None
        if (
            entry.row_status != RowRecognitionStatus.COMPLETE
            or entry.action_point is None
            or entry.action_bounds is None
            or entry.metadata.get("coordinate_provenance") != "visual_geometry"
        ):
            return None
        try:
            return ResourceItem(
                item_id=entry.metadata["item_id"],
                resource=entry.metadata["resource"],
                amount=entry.metadata["amount"],
                owned=entry.metadata["owned"],
                fingerprint=entry.metadata["observation_fingerprint"],
            )
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def _signature(cls, observation: Observation) -> tuple[tuple[object, ...], ...]:
        """Compares row identity, stock and card geometry without noisy full-frame hashing."""

        resources = tuple(
            (
                "resource",
                entry.metadata.get("item_id"),
                entry.metadata.get("resource"),
                entry.metadata.get("amount"),
                entry.metadata.get("owned"),
                entry.row_status,
                entry.bounds,
            )
            for entry in observation.entries(ListEntryKind.RESOURCE_ITEM)
        )
        exclusions = tuple(
            ("exclusion", entry.title_text, entry.metadata.get("owned"), entry.row_status, entry.bounds)
            for entry in observation.entries(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION)
        )
        unresolved = tuple(
            (
                "unresolved",
                entry.title_text,
                entry.metadata.get("unresolved_reason", entry.row_status.value),
                entry.row_status,
                entry.bounds,
            )
            for entry in observation.entries(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED)
        )
        return resources + exclusions + unresolved

    @staticmethod
    def _require_complete_view(observation: Observation) -> tuple[str, ...]:
        """Return explicit unknown reasons from parser rows without reopening screenshots."""

        rows = (
            *observation.entries(ListEntryKind.RESOURCE_ITEM),
            *observation.entries(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION),
            *observation.entries(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED),
        )
        if not rows:
            return ("no_visual_rows",)
        unresolved = observation.entries(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED)
        if unresolved:
            return tuple(
                str(entry.metadata.get("unresolved_reason", entry.row_status.value))
                for entry in unresolved
            )
        incomplete = tuple(
            entry for entry in observation.entries(ListEntryKind.RESOURCE_ITEM)
            if entry.row_status != RowRecognitionStatus.COMPLETE
            or entry.action_point is None
            or entry.action_bounds is None
        )
        if incomplete:
            return ("incomplete_item_row",)
        required_metadata = {
            "item_id",
            "resource",
            "amount",
            "owned",
            "observation_fingerprint",
            "coordinate_provenance",
        }
        if any(
            not required_metadata.issubset(entry.metadata)
            or entry.metadata.get("coordinate_provenance") != "visual_geometry"
            for entry in observation.entries(ListEntryKind.RESOURCE_ITEM)
        ):
            return ("incomplete_item_row",)
        identities = tuple(
            entry.metadata.get("item_id")
            for entry in observation.entries(ListEntryKind.RESOURCE_ITEM)
        )
        duplicate_identities = {
            item_id
            for item_id in identities
            if item_id is not None and identities.count(item_id) > 1
        }
        if duplicate_identities:
            return ("duplicate_item_identity",)
        return ()
