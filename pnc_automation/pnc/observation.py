"""Typed observations derived from screenshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


@dataclass(frozen=True, slots=True)
class Bounds:
    """Represents one rectangular UI region in screenshot coordinates."""

    x: int
    y: int
    width: int
    height: int

    def center(self) -> tuple[int, int]:
        """Returns the center point of the bounds."""

        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True, slots=True)
class VisibleElement:
    """Represents one detected selector anchored on the current screen."""

    selector_id: UiElementId
    bounds: Bounds
    confidence: float
    extracted_text: str | None = None
    action_point: tuple[int, int] | None = None


class ListEntryKind(StrEnum):
    """Typed list-based collections observed on dynamic screens."""

    CASTLE = "castle"
    BUILDING = "building"
    RESEARCH = "research"
    GATHER_NODE = "gather_node"
    CAMPAIGN_STAGE = "campaign_stage"
    EVENT_ENTRY = "event_entry"
    GIFT_ENTRY = "gift_entry"
    STORE_ENTRY = "store_entry"


@dataclass(frozen=True, slots=True)
class DetectedListEntry:
    """Represents one repeated row or tile extracted from a dynamic screen."""

    kind: ListEntryKind
    bounds: Bounds
    title_text: str | None = None
    subtitle_text: str | None = None
    timer_text: str | None = None
    badge_present: bool = False
    selected: bool = False
    action_point: tuple[int, int] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def require_metadata(self, key: str) -> Any:
        """Returns a required metadata field or fails fast."""

        if key not in self.metadata:
            raise SelectorResolutionError(
                f"Missing required metadata '{key}' for list entry '{self.title_text}'.",
                key=key,
                entry_kind=self.kind,
            )
        return self.metadata[key]


@dataclass(frozen=True, slots=True)
class Observation:
    """Authoritative interpreted state for one screenshot."""

    screen_type: ScreenType
    visible_elements: Mapping[UiElementId, VisibleElement]
    list_entries: tuple[DetectedListEntry, ...] = ()
    artifact_path: Path | None = None
    image_size: tuple[int, int] | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    blocking_popup: bool = False
    current_castle_name: str | None = None
    available_march_slots: int | None = None

    def has(self, selector_id: UiElementId) -> bool:
        """Returns whether one selector is visible in the observation."""

        return selector_id in self.visible_elements

    def get(self, selector_id: UiElementId) -> VisibleElement | None:
        """Returns one visible element when available."""

        return self.visible_elements.get(selector_id)

    def require(self, selector_id: UiElementId) -> VisibleElement:
        """Returns one required visible element or fails fast."""

        element = self.get(selector_id)
        if element is None:
            raise SelectorResolutionError(
                f"Required selector '{selector_id}' is not visible on screen '{self.screen_type}'.",
                selector_id=selector_id,
                screen_type=self.screen_type,
            )
        return element

    def entries(self, kind: ListEntryKind) -> tuple[DetectedListEntry, ...]:
        """Returns all observed entries of the requested dynamic collection kind."""

        return tuple(entry for entry in self.list_entries if entry.kind == kind)
