"""Canonical connected Bag adapter for the one-resource-item feature."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from pnc_automation.app.automation.daily_maintenance.coordinator import DailyMaintenanceCoordinator
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapAction, TapListEntryAction
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, DailyQuestRowState
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation
from pnc_automation.app.pnc.domain.resource_items import ResourceInventory, ResourceItem
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.resource_inventory import detect_resource_card_bounds
from pnc_automation.core.vision.image.models import Bounds


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
        current = self._reach_top(current)
        collected: dict[tuple[str, str, int], ResourceItem] = {}
        for index in range(self.max_viewports):
            self._require_complete_view(current)
            for item in self._items(current):
                previous = collected.get(item.identity)
                if previous is not None and previous.owned != item.owned:
                    raise ValueError("Resource inventory changed during the full scan.")
                collected[item.identity] = item
            after = self._scroll(current, upward=False, adjusted=False)
            if self._signature(after) == self._signature(current):
                adjusted = self._scroll(after, upward=False, adjusted=True)
                if self._signature(adjusted) == self._signature(after):
                    return ResourceInventory(tuple(collected.values()), True, self.artifact_paths())
                after = adjusted
            current = after
        raise ValueError("Resource inventory full scan exceeded its viewport budget.")

    def focus_item(self, item: ResourceItem) -> ResourceItem:
        """Moves back through the proved inventory and freshly resolves the chosen item."""

        current = self._stable("resource_focus_start")
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
                if current.entries(ListEntryKind.RESOURCE_ITEM) or current.entries(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION):
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
        """Captures one frame and globally recovers an exact required-update popup."""

        observation = self.observation_service.observe(label, request=request)
        if not observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON):
            return observation
        recovered = self.action_executor.recover_update_if_required(
            observation,
            label_prefix=f"{label}_update",
            observe=lambda follow_up_label, request=None: self.observation_service.observe(
                f"{label}_{follow_up_label}",
                request=request,
            ),
        )
        if recovered is None:
            raise AssertionError("Required-update recovery returned no observation for a detected Confirm control.")
        return recovered

    def _stable(self, label: str) -> Observation:
        """Requires two agreeing semantic/geometry frames before a scan or scroll decision."""

        before = self._observe(f"{label}_first")
        after = self._observe(f"{label}_second")
        if self._signature(before) != self._signature(after):
            before = after
            after = self._observe(f"{label}_settled")
        if self._signature(before) != self._signature(after):
            raise ValueError("Resource inventory geometry or stock is unstable.")
        return after

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
            if self._signature(after) == self._signature(current):
                adjusted = self._scroll(after, upward=True, adjusted=True)
                if self._signature(adjusted) == self._signature(after):
                    return adjusted
                after = adjusted
            current = after
        raise ValueError("Resource inventory top could not be proved within the swipe budget.")

    @staticmethod
    def _items(observation: Observation) -> tuple[ResourceItem, ...]:
        """Converts only exact resource-row metadata with visual action provenance."""

        items: list[ResourceItem] = []
        for entry in observation.entries(ListEntryKind.RESOURCE_ITEM):
            if entry.require_metadata("coordinate_provenance") != "visual_geometry" or entry.action_point is None:
                raise ValueError("Resource item requires a visual single-Use action point.")
            items.append(ResourceItem(
                item_id=entry.require_metadata("item_id"),
                resource=entry.require_metadata("resource"),
                amount=entry.require_metadata("amount"),
                owned=entry.require_metadata("owned"),
                fingerprint=entry.require_metadata("observation_fingerprint"),
            ))
        return tuple(items)

    @classmethod
    def _signature(cls, observation: Observation) -> tuple[tuple[object, ...], ...]:
        """Compares row identity, stock and card geometry without noisy full-frame hashing."""

        resources = tuple(
            (item.identity, item.owned, entry.bounds)
            for item, entry in zip(cls._items(observation), observation.entries(ListEntryKind.RESOURCE_ITEM), strict=True)
        )
        exclusions = tuple(
            (entry.title_text, entry.require_metadata("owned"), entry.bounds)
            for entry in observation.entries(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION)
        )
        return resources + exclusions

    @staticmethod
    def _require_complete_view(observation: Observation) -> None:
        """Rejects missing OCR semantics rather than silently overlooking a smaller pack."""

        if observation.artifact_path is None:
            raise ValueError("Full inventory scan requires a saved screenshot.")
        with Image.open(observation.artifact_path) as image:
            card_bounds = detect_resource_card_bounds(image)
            image_height = image.height
        parsed_count = len(observation.entries(ListEntryKind.RESOURCE_ITEM)) + len(
            observation.entries(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION)
        )
        parsed_bounds = {
            entry.bounds
            for entry in (
                *observation.entries(ListEntryKind.RESOURCE_ITEM),
                *observation.entries(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION),
            )
        }
        missing_bounds = tuple(bounds for bounds in card_bounds if bounds not in parsed_bounds)
        edge_missing = tuple(
            bounds for bounds in missing_bounds
            if _is_edge_clipped_card(bounds, image_height=image_height)
        )
        if parsed_count + len(edge_missing) != len(card_bounds):
            raise ValueError("Resource inventory contains an unparsed card; full scan is unproved.")


def _is_edge_clipped_card(bounds: Bounds, *, image_height: int) -> bool:
    """Returns whether a card touches the fixed viewport edge where its title may be clipped."""

    top_edge = int(image_height * 0.17) + 32
    bottom_edge = image_height - 12
    return bounds.y <= top_edge or bounds.y + bounds.height >= bottom_edge
