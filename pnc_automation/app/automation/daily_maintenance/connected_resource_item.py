"""Canonical connected Bag adapter for the one-resource-item feature."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnc_automation.app.automation.daily_maintenance.coordinator import DailyMaintenanceCoordinator
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapAction, TapListEntryAction
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, DailyQuestRowState
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
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest


@dataclass(slots=True)
class ConnectedResourceItemSession:
    """Scans Resource inventory and uses only fresh visual single-Use row targets."""

    observation_service: ObservationService
    action_executor: ObservedActionExecutor
    flows: ScreenFlowPlanner
    daily_coordinator: DailyMaintenanceCoordinator
    max_viewports: int = 40
    _artifacts: list[str] = field(default_factory=list, init=False)

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

    def use_one(self, item: ResourceItem) -> None:
        """Revalidates one fingerprint and dispatches no generic or bulk-use selector."""

        before = self._observe("resource_use_pre")
        candidates = tuple(candidate for candidate in self._items(before) if candidate.identity == item.identity)
        if len(candidates) != 1 or candidates[0] != item:
            raise ValueError("Resource item fingerprint changed before single Use.")
        self.action_executor.execute_action(
            TapListEntryAction(
                reason="use_one_smallest_resource_pack",
                entry_kind=ListEntryKind.RESOURCE_ITEM,
                metadata_key="observation_fingerprint",
                metadata_value=item.fingerprint,
                use_action_point=True,
            ),
            before,
        )

    def observe_item(self, item: ResourceItem) -> ResourceItem | None:
        """Reads the same item's stock after the one dispatched use."""

        after = self._observe("resource_use_post")
        return next((candidate for candidate in self._items(after) if candidate.identity == item.identity), None)

    def daily_requirement_completed(self) -> bool:
        """Uses the shared read-only Daily sweep to prove resource-use completion."""

        survey = self.daily_coordinator.survey_read_only()
        self._artifacts.extend(path for path in survey.artifact_paths if path not in self._artifacts)
        return any(
            row.quest_id == DailyQuestId.USE_RESOURCE_ITEM
            and (
                row.state in {DailyQuestRowState.CLAIM, DailyQuestRowState.COMPLETED}
                or (
                    row.progress_current is not None
                    and row.progress_required is not None
                    and row.progress_current >= row.progress_required
                )
            )
            for row in survey.rows
        )

    def artifact_paths(self) -> tuple[str, ...]:
        """Returns all captured scan and mutation evidence in observation order."""

        return tuple(self._artifacts)

    def _open_inventory(self) -> None:
        """Uses typed navigation only, rejecting generic recovery and Android Back."""

        for index in range(8):
            current = self._observe_with_update_recovery(f"resource_open_{index}")
            if current.screen_type == ScreenType.PNC_BAG:
                if (
                    current.entries(ListEntryKind.RESOURCE_ITEM)
                    or current.entries(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION)
                    or current.entries(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED)
                ):
                    return
                action = TapAction(
                    selector_id=UiElementId.PNC_BAG_SUBTAB_RESOURCE,
                    reason="select_resource_tab", observe_after=True,
                )
            elif current.screen_type == ScreenType.PNC_HOME_CITY:
                action = TapAction(
                    selector_id=UiElementId.PNC_BOTTOM_NAV_BAG,
                    reason="open_resource_inventory", observe_after=True,
                )
            elif current.screen_type in {
                ScreenType.PNC_MORE_MENU,
                ScreenType.PNC_SETTINGS,
                ScreenType.PNC_CASTLE_SELECTION,
                ScreenType.PNC_QUEST_DAILY,
            }:
                actions = self.flows.ensure_home_city(current)
                if len(actions) != 1 or not isinstance(actions[0], TapAction):
                    raise ValueError("Resource navigation requires a typed in-game back control.")
                action = actions[0]
                if action.selector_id not in {
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_BOTTOM_NAV_MORE,
                }:
                    raise ValueError("Resource navigation rejected an unrelated action.")
            else:
                raise ValueError("Resource inventory navigation encountered an unexpected screen.")
            self.action_executor.execute_actions(
                (action,), current,
                observe=lambda label, request=None: self.observation_service.observe(
                    f"resource_open_{index}_{label}", request=request,
                ),
            )
        raise ValueError("Resource inventory navigation exceeded its action budget.")

    def _observe(self, label: str) -> Observation:
        """Requires Bag, reopening it after a recovered required update."""

        observation = self._observe_with_update_recovery(
            label, request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
        )
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            self._open_inventory()
            observation = self._observe_with_update_recovery(
                f"{label}_after_update",
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
            )
        if observation.screen_type != ScreenType.PNC_BAG or observation.blocking_popup:
            raise ValueError("Expected typed Resource Bag, not an unknown screen or popup.")
        if observation.artifact_path is not None:
            path = str(observation.artifact_path)
            if path not in self._artifacts:
                self._artifacts.append(path)
        return observation

    def _observe_with_update_recovery(
        self,
        label: str,
        request: ObservationRequest | None = None,
    ) -> Observation:
        """Captures one frame and delegates interruption recovery to the shared executor."""

        observation = self.observation_service.observe(label, request=request)
        recovered = self.action_executor.recover_interruption_if_required(
            observation,
            label_prefix=f"{label}_update",
            observe=lambda follow_up_label, request=None: self.observation_service.observe(
                f"{label}_{follow_up_label}",
                request=request,
            ),
        )
        if recovered is None:
            return observation
        return recovered

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

    def _scroll(
        self,
        before: Observation,
        *,
        upward: bool,
        adjusted: bool,
        fine: bool = False,
    ) -> Observation:
        """Performs one bounded normalized list swipe through the canonical executor."""

        low = 0.64 if fine else (0.78 if adjusted else 0.85)
        high = 0.46 if fine else (0.42 if adjusted else 0.32)
        self.action_executor.execute_action(
            SwipeAction(
                reason=(
                    "resource_inventory_focus_scroll"
                    if fine
                    else "resource_inventory_scroll_adjusted"
                    if adjusted
                    else "resource_inventory_scroll"
                ),
                start_x_ratio=0.5, end_x_ratio=0.5,
                start_y_ratio=high if upward else low,
                end_y_ratio=low if upward else high,
                duration_ms=420 if adjusted else 350,
            ),
            before,
        )
        return self._stable("resource_scroll")

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
            item = ConnectedResourceItemSession._item_from_entry(entry)
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
            if (item := ConnectedResourceItemSession._item_from_entry(entry)) is not None
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
