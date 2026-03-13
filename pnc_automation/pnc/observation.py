"""Typed observations derived from screenshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pnc_automation.config.models import PncAccountCastleRosterConfig, SelectedCastleConfig
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.chat import ChatChannel
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


class VisibleElementSourceKind(StrEnum):
    """Identifies the canonical runtime source for one visible selector."""

    TEMPLATE = "template"
    OCR = "ocr"
    GEOMETRY = "geometry"


@dataclass(frozen=True, slots=True)
class VisibleElement:
    """Represents one detected selector anchored on the current screen."""

    selector_id: UiElementId
    bounds: Bounds
    confidence: float
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE
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
    current_castle: SelectedCastleConfig | None = None
    current_pnc_account_id: str | None = None
    verified_pnc_account_id: str | None = None
    castle_roster_snapshot: PncAccountCastleRosterConfig | None = None
    available_march_slots: int | None = None
    active_chat_channel: ChatChannel | None = None
    chat_draft_empty: bool | None = None
    chat_draft_text: str | None = None

    @property
    def current_castle_name(self) -> str | None:
        """Returns the currently selected castle name when known."""

        if self.current_castle is None:
            return None
        return self.current_castle.castle_name

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

    def matches_current_castle(self, castle: SelectedCastleConfig) -> bool:
        """Returns whether the observed active castle matches the requested identity."""

        current_castle = self.current_castle
        if current_castle is None:
            return False
        return castle_identities_match(current_castle, castle)

    def find_castle_entry(self, castle: SelectedCastleConfig) -> DetectedListEntry | None:
        """Returns the observed castle-roster entry matching the requested identity when visible."""

        for entry in self.entries(ListEntryKind.CASTLE):
            if castle_entry_matches(entry, castle):
                return entry
        return None

    def is_chat_channel_active(self, channel: ChatChannel) -> bool:
        """Returns whether the observed chat overlay already has the requested channel selected."""

        return self.active_chat_channel == channel


def castle_entry_matches(entry: DetectedListEntry, castle: SelectedCastleConfig) -> bool:
    """Returns whether one detected castle row matches the configured castle identity."""

    if not castle_entry_identity_matches(entry, castle):
        return False
    level = entry.metadata.get("castle_level")
    if castle.castle_level is None or level is None:
        return True
    return level == castle.castle_level


def castle_entry_identity_matches(entry: DetectedListEntry, castle: SelectedCastleConfig) -> bool:
    """Returns whether one detected castle row matches a castle by stable kingdom/name identity."""

    if entry.kind != ListEntryKind.CASTLE:
        return False
    if entry.title_text != castle.castle_name:
        return False
    return entry.metadata.get("kingdom") == castle.kingdom


def castle_identities_match(left: SelectedCastleConfig, right: SelectedCastleConfig) -> bool:
    """Returns whether two castle identities describe the same managed castle."""

    if left.castle_name != right.castle_name:
        return False
    if left.kingdom != "" and right.kingdom != "" and left.kingdom != right.kingdom:
        return False
    if left.castle_level is None or right.castle_level is None:
        return True
    return left.castle_level == right.castle_level
