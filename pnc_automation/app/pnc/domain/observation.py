"""Typed observations derived from screenshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pnc_automation.app.authoring.config.models import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.text.normalization import normalize_ocr_text


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
    MAIL_THREAD = "mail_thread"
    MAIL_MESSAGE = "mail_message"
    CHAT_MESSAGE = "chat_message"
    ALLIANCE_MEMBER = "alliance_member"
    RANKED_PLAYER = "ranked_player"


class CurrentCastleEvidenceKind(StrEnum):
    """Describes how strongly the current-castle observation identifies the active castle."""

    EXACT = "exact"
    NAME_ONLY = "name_only"


class CurrentCastleMatchStatus(StrEnum):
    """Describes whether current-castle evidence can satisfy an explicit castle target."""

    MATCH = "match"
    MISMATCH = "mismatch"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    AMBIGUOUS_NAME = "ambiguous_name"


@dataclass(frozen=True, slots=True)
class ObservedTextFieldState:
    """Represents one observed reusable selector-backed text field."""

    selector_id: UiElementId
    text: str | None
    empty: bool | None


@dataclass(frozen=True, slots=True)
class CurrentCastleMatch:
    """Summarizes whether current-castle evidence can prove an explicit castle target."""

    status: CurrentCastleMatchStatus
    evidence_kind: CurrentCastleEvidenceKind | None = None

    @property
    def matches(self) -> bool:
        """Returns whether the available current-castle evidence proves the target."""

        return self.status == CurrentCastleMatchStatus.MATCH

    @property
    def ambiguous(self) -> bool:
        """Returns whether a name-only match became ambiguous against the cached roster."""

        return self.status == CurrentCastleMatchStatus.AMBIGUOUS_NAME


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


class SpatialSurfaceType(StrEnum):
    """Typed spatial surfaces that expose camera-relative or coordinate-relative scene objects."""

    WORLD_MAP = "world_map"
    HOME_CITY_SURFACE = "home_city_surface"


class SpatialViewportAddressingKind(StrEnum):
    """Describes how the current spatial viewport can be addressed and navigated."""

    COORDINATE_BAR = "coordinate_bar"
    CAMERA_RELATIVE = "camera_relative"


class SpatialObjectKind(StrEnum):
    """Typed scene-object categories observed on spatial surfaces."""

    CASTLE = "castle"
    ALLIANCE_BUILDING = "alliance_building"
    MONSTER = "monster"
    HELL_FORTRESS = "hell_fortress"
    RESOURCE_NODE = "resource_node"
    ALTAR = "altar"
    DRAGONIA = "dragonia"
    HOME_BUILDING = "home_building"
    HOME_EMPTY_SLOT = "home_empty_slot"


class SpatialObjectRelationship(StrEnum):
    """Describes the semantic ownership or alignment of one spatial object."""

    SELF = "self"
    ALLY = "ally"
    OTHER = "other"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SpatialViewport:
    """Stores the active camera or coordinate context for one spatial surface observation."""

    addressing_kind: SpatialViewportAddressingKind
    x: int | None = None
    y: int | None = None
    zoom_bucket: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects invalid coordinate-addressing combinations before tasks consume them."""

        if self.addressing_kind == SpatialViewportAddressingKind.COORDINATE_BAR:
            if not isinstance(self.x, int) or not isinstance(self.y, int):
                raise SelectorResolutionError(
                    "Coordinate-addressable spatial viewports must expose integer X and Y values.",
                    addressing_kind=self.addressing_kind,
                    x=self.x,
                    y=self.y,
                )
            return
        if self.x is not None or self.y is not None:
            raise SelectorResolutionError(
                "Camera-relative spatial viewports must not expose absolute X/Y coordinates.",
                addressing_kind=self.addressing_kind,
                x=self.x,
                y=self.y,
            )

    @property
    def coordinate(self) -> tuple[int, int] | None:
        """Returns the absolute coordinate pair when the viewport is coordinate-addressable."""

        if self.x is None or self.y is None:
            return None
        return self.x, self.y


@dataclass(frozen=True, slots=True)
class SpatialObjectQuery:
    """Defines one semantic query used to resolve a visible spatial object."""

    surface_type: SpatialSurfaceType | None = None
    kind: SpatialObjectKind | None = None
    relationship: SpatialObjectRelationship | None = None
    name_text: str | None = None
    alliance_tag: str | None = None
    kingdom: str | None = None
    level: int | None = None
    metadata_key: str | None = None
    metadata_value: Any = None

    def __post_init__(self) -> None:
        """Rejects empty or internally inconsistent spatial-object queries."""

        if self.metadata_key is None and self.metadata_value is not None:
            raise SelectorResolutionError(
                "Spatial-object queries cannot constrain metadata_value without metadata_key.",
                metadata_value=self.metadata_value,
            )
        if all(
            value is None
            for value in (
                self.surface_type,
                self.kind,
                self.relationship,
                self.name_text,
                self.alliance_tag,
                self.kingdom,
                self.level,
                self.metadata_key,
            )
        ):
            raise SelectorResolutionError("Spatial-object queries must constrain at least one identifying field.")


@dataclass(frozen=True, slots=True)
class DetectedSpatialObject:
    """Represents one visible scene object extracted from a spatial surface."""

    kind: SpatialObjectKind
    bounds: Bounds
    relationship: SpatialObjectRelationship = SpatialObjectRelationship.UNKNOWN
    name_text: str | None = None
    alliance_tag: str | None = None
    level: int | None = None
    kingdom: str | None = None
    action_point: tuple[int, int] | None = None
    viewport_offset: tuple[int, int] | None = None
    viewport_offset_ratio: tuple[float, float] | None = None
    estimated_world_coordinate: tuple[int, int] | None = None
    confirmed_world_coordinate: tuple[int, int] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects invalid typed metadata so spatial parsing fails fast during tests and runtime."""

        if self.name_text is not None and self.name_text.strip() == "":
            raise SelectorResolutionError("Spatial objects must not carry blank name_text values.", object_kind=self.kind)
        if self.alliance_tag is not None and self.alliance_tag.strip() == "":
            raise SelectorResolutionError(
                "Spatial objects must not carry blank alliance tags.",
                object_kind=self.kind,
            )
        if self.kingdom is not None and self.kingdom.strip() == "":
            raise SelectorResolutionError(
                "Spatial objects must not carry blank kingdom values.",
                object_kind=self.kind,
            )
        if self.level is not None and (not isinstance(self.level, int) or self.level <= 0):
            raise SelectorResolutionError(
                "Spatial objects must use positive integer levels when a level is present.",
                object_kind=self.kind,
                level=self.level,
            )
        if self.viewport_offset is not None and not _is_integer_pair(self.viewport_offset):
            raise SelectorResolutionError(
                "Spatial objects must use integer viewport offsets when present.",
                object_kind=self.kind,
                viewport_offset=self.viewport_offset,
            )
        if self.viewport_offset_ratio is not None and not _is_numeric_pair(self.viewport_offset_ratio):
            raise SelectorResolutionError(
                "Spatial objects must use numeric viewport offset ratios when present.",
                object_kind=self.kind,
                viewport_offset_ratio=self.viewport_offset_ratio,
            )
        if self.estimated_world_coordinate is not None and not _is_integer_pair(self.estimated_world_coordinate):
            raise SelectorResolutionError(
                "Spatial objects must use integer estimated world coordinates when present.",
                object_kind=self.kind,
                estimated_world_coordinate=self.estimated_world_coordinate,
            )
        if self.confirmed_world_coordinate is not None and not _is_integer_pair(self.confirmed_world_coordinate):
            raise SelectorResolutionError(
                "Spatial objects must use integer confirmed world coordinates when present.",
                object_kind=self.kind,
                confirmed_world_coordinate=self.confirmed_world_coordinate,
            )

    def require_metadata(self, key: str) -> Any:
        """Returns a required spatial-object metadata field or fails fast."""

        if key not in self.metadata:
            raise SelectorResolutionError(
                f"Missing required metadata '{key}' for spatial object '{self.name_text}'.",
                key=key,
                object_kind=self.kind,
            )
        return self.metadata[key]

    def matches(self, query: SpatialObjectQuery) -> bool:
        """Returns whether the visible object satisfies the requested semantic query."""

        if query.kind is not None and self.kind != query.kind:
            return False
        if query.relationship is not None and self.relationship != query.relationship:
            return False
        if query.name_text is not None and self.name_text != query.name_text:
            return False
        if query.alliance_tag is not None and self.alliance_tag != query.alliance_tag:
            return False
        if query.kingdom is not None and self.kingdom != query.kingdom:
            return False
        if query.level is not None and self.level != query.level:
            return False
        if query.metadata_key is not None and self.metadata.get(query.metadata_key) != query.metadata_value:
            return False
        return True


@dataclass(frozen=True, slots=True)
class SpatialSurfaceObservation:
    """Stores the current spatial-surface viewport plus all visible scene objects."""

    surface_type: SpatialSurfaceType
    viewport: SpatialViewport
    objects: tuple[DetectedSpatialObject, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def objects_of_kind(self, kind: SpatialObjectKind) -> tuple[DetectedSpatialObject, ...]:
        """Returns every visible spatial object of the requested kind."""

        return tuple(object_ for object_ in self.objects if object_.kind == kind)

    def find_object(self, query: SpatialObjectQuery) -> DetectedSpatialObject | None:
        """Returns the single visible spatial object matching the semantic query when available."""

        if query.surface_type is not None and query.surface_type != self.surface_type:
            return None
        for object_ in self.objects:
            if object_.matches(query):
                return object_
        return None

    def require_object(self, query: SpatialObjectQuery) -> DetectedSpatialObject:
        """Returns one required visible spatial object or fails fast."""

        object_ = self.find_object(query)
        if object_ is not None:
            return object_
        raise SelectorResolutionError(
            "The requested spatial object is not visible on the active surface.",
            surface_type=self.surface_type,
            object_kind=query.kind,
            relationship=query.relationship,
            name_text=query.name_text,
            alliance_tag=query.alliance_tag,
            kingdom=query.kingdom,
            level=query.level,
            metadata_key=query.metadata_key,
            metadata_value=query.metadata_value,
        )

    def require_visible_object(self, target: DetectedSpatialObject) -> DetectedSpatialObject:
        """Returns one exact visible spatial object instance or fails fast when it is no longer present."""

        if target in self.objects:
            return target
        raise SelectorResolutionError(
            "The requested spatial object instance is not visible on the active surface.",
            surface_type=self.surface_type,
            object_kind=target.kind,
            name_text=target.name_text,
            action_point=target.action_point,
        )


@dataclass(frozen=True, slots=True)
class Observation:
    """Authoritative interpreted state for one screenshot."""

    screen_type: ScreenType
    visible_elements: Mapping[UiElementId, VisibleElement]
    list_entries: tuple[DetectedListEntry, ...] = ()
    spatial_surface: SpatialSurfaceObservation | None = None
    artifact_path: Path | None = None
    image_size: tuple[int, int] | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    blocking_popup: bool = False
    current_castle: CastleIdentity | None = None
    current_castle_evidence: CurrentCastleEvidenceKind | None = None
    current_pnc_account_id: str | None = None
    verified_pnc_account_id: str | None = None
    castle_roster_snapshot: PncAccountCastleRosterConfig | None = None
    available_march_slots: int | None = None
    active_chat_channel: ChatChannel | None = None
    profile_player_name: str | None = None
    mailbox_type: MailboxType | None = None
    mailbox_empty: bool | None = None
    text_field_states: Mapping[UiElementId, ObservedTextFieldState] = field(default_factory=dict)
    chat_draft_empty: bool | None = None
    chat_draft_text: str | None = None

    @property
    def current_castle_name(self) -> str | None:
        """Returns the currently selected castle name when known."""

        if self.current_castle is None:
            return None
        return self.current_castle.castle_name

    @property
    def resolved_current_castle_evidence(self) -> CurrentCastleEvidenceKind | None:
        """Returns the canonical current-castle evidence kind, inferring legacy fixtures when needed."""

        if self.current_castle is None:
            return None
        if self.current_castle_evidence is not None:
            return self.current_castle_evidence
        return CurrentCastleEvidenceKind.NAME_ONLY if self.current_castle.kingdom == "" else CurrentCastleEvidenceKind.EXACT

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

    def require_spatial_surface(self, surface_type: SpatialSurfaceType | None = None) -> SpatialSurfaceObservation:
        """Returns the active spatial surface or fails fast when it is missing or mismatched."""

        if self.spatial_surface is None:
            raise SelectorResolutionError(
                "The current observation does not expose a spatial-surface model.",
                screen_type=self.screen_type,
            )
        if surface_type is not None and self.spatial_surface.surface_type != surface_type:
            raise SelectorResolutionError(
                "The current observation exposes a different spatial surface than requested.",
                requested_surface_type=surface_type,
                surface_type=self.spatial_surface.surface_type,
                screen_type=self.screen_type,
            )
        return self.spatial_surface

    def spatial_objects(self, kind: SpatialObjectKind | None = None) -> tuple[DetectedSpatialObject, ...]:
        """Returns every visible spatial object, optionally filtered to one kind."""

        if self.spatial_surface is None:
            return ()
        if kind is None:
            return self.spatial_surface.objects
        return self.spatial_surface.objects_of_kind(kind)

    def find_spatial_object(self, query: SpatialObjectQuery) -> DetectedSpatialObject | None:
        """Returns one visible spatial object satisfying the semantic query when present."""

        if self.spatial_surface is None:
            return None
        return self.spatial_surface.find_object(query)

    def require_spatial_object(self, query: SpatialObjectQuery) -> DetectedSpatialObject:
        """Returns one required visible spatial object or fails fast."""

        if self.spatial_surface is None:
            raise SelectorResolutionError(
                "The current observation does not expose a spatial-surface model.",
                screen_type=self.screen_type,
            )
        return self.spatial_surface.require_object(query)

    def text_field_state(self, selector_id: UiElementId) -> ObservedTextFieldState | None:
        """Returns the observed reusable text-field state for one selector when available."""

        return self.text_field_states.get(selector_id)

    def require_text_field_state(self, selector_id: UiElementId) -> ObservedTextFieldState:
        """Returns one required observed text-field state or fails fast."""

        state = self.text_field_state(selector_id)
        if state is not None:
            return state
        raise SelectorResolutionError(
            "The requested text-field state was not observed for the current screen.",
            selector_id=selector_id,
            screen_type=self.screen_type,
        )

    def current_castle_match(
        self,
        castle: CastleIdentity,
        *,
        roster: PncAccountCastleRosterConfig | None = None,
    ) -> CurrentCastleMatch:
        """Returns whether current-castle evidence is strong enough to prove the requested castle."""

        active_roster = self.castle_roster_snapshot if roster is None else roster
        return resolve_current_castle_match(
            current_castle=self.current_castle,
            evidence_kind=self.resolved_current_castle_evidence,
            target=castle,
            roster=active_roster,
        )

    def matches_current_castle(
        self,
        castle: CastleIdentity,
        *,
        roster: PncAccountCastleRosterConfig | None = None,
    ) -> bool:
        """Returns whether the observed active castle matches the requested identity."""

        return self.current_castle_match(castle, roster=roster).matches

    def find_castle_entry(self, castle: CastleIdentity) -> DetectedListEntry | None:
        """Returns the observed castle-roster entry matching the requested identity when visible."""

        for entry in self.entries(ListEntryKind.CASTLE):
            if castle_entry_matches(entry, castle):
                return entry
        return None

    def is_chat_channel_active(self, channel: ChatChannel) -> bool:
        """Returns whether the observed chat overlay already has the requested channel selected."""

        return self.active_chat_channel == channel


def list_entry_matches(
    entry: DetectedListEntry,
    *,
    title_text: str | None = None,
    metadata_key: str | None = None,
    metadata_value: str | int | bool | None = None,
    selected: bool | None = None,
) -> bool:
    """Returns whether one observed list entry satisfies one dynamic-entry resolution request."""

    if title_text is not None and not _list_entry_title_matches(entry, title_text):
        return False
    if metadata_key is not None and entry.metadata.get(metadata_key) != metadata_value:
        return False
    if selected is not None and entry.selected != selected:
        return False
    return True


def castle_identity_from_entry(entry: DetectedListEntry) -> CastleIdentity:
    """Converts one observed castle row into the canonical shared castle identity model."""

    if entry.kind != ListEntryKind.CASTLE:
        raise SelectorResolutionError("Only castle list entries can produce a castle identity.", entry_kind=entry.kind)
    if entry.title_text is None or entry.title_text.strip() == "":
        raise SelectorResolutionError("Observed castle entry is missing its castle name.", entry_kind=entry.kind)
    kingdom = entry.require_metadata("kingdom")
    castle_level = entry.metadata.get("castle_level")
    if not isinstance(kingdom, str) or kingdom.strip() == "":
        raise SelectorResolutionError("Observed castle entry is missing a valid kingdom.", entry_kind=entry.kind)
    if castle_level is not None and not isinstance(castle_level, int):
        raise SelectorResolutionError(
            "Observed castle entry contains a non-integer castle level.",
            entry_kind=entry.kind,
            castle_level=castle_level,
        )
    return CastleIdentity(
        kingdom=kingdom,
        castle_name=entry.title_text,
        castle_level=castle_level,
    )


def castle_entry_matches(entry: DetectedListEntry, castle: CastleIdentity) -> bool:
    """Returns whether one detected castle row matches the requested castle identity."""

    if not castle_entry_identity_matches(entry, castle):
        return False
    level = entry.metadata.get("castle_level")
    if castle.castle_level is None or level is None:
        return True
    return level == castle.castle_level


def castle_entry_identity_matches(entry: DetectedListEntry, castle: CastleIdentity) -> bool:
    """Returns whether one detected castle row matches a castle by stable kingdom/name identity."""

    if entry.kind != ListEntryKind.CASTLE:
        return False
    if not castle_names_match(entry.title_text, castle.castle_name):
        return False
    return entry.metadata.get("kingdom") == castle.kingdom


def castle_identities_match(left: CastleIdentity, right: CastleIdentity) -> bool:
    """Returns whether two castle identities describe the same managed castle."""

    if not castle_names_match(left.castle_name, right.castle_name):
        return False
    if left.kingdom != "" and right.kingdom != "" and left.kingdom != right.kingdom:
        return False
    if left.castle_level is None or right.castle_level is None:
        return True
    return left.castle_level == right.castle_level


def castle_names_match(left: str, right: str) -> bool:
    """Returns whether two castle names match exactly or through stable OCR normalization."""

    if left == right:
        return True
    return normalize_ocr_text(left) == normalize_ocr_text(right)


def resolve_unambiguous_castle_identity(
    candidates: tuple[CastleIdentity, ...],
    *,
    preferred_name: str | None = None,
) -> CastleIdentity | None:
    """Returns one canonical castle when all candidates collapse to the same semantic identity."""

    groups = _group_semantic_castle_identities(candidates)
    if preferred_name is not None:
        exact_groups = tuple(
            group for group in groups if any(candidate.castle_name == preferred_name for candidate in group)
        )
        if len(exact_groups) == 1:
            return next(candidate for candidate in exact_groups[0] if candidate.castle_name == preferred_name)
        if len(exact_groups) > 1:
            return None
    if len(groups) == 1:
        return groups[0][0]
    return None


def resolve_current_castle_match(
    *,
    current_castle: CastleIdentity | None,
    evidence_kind: CurrentCastleEvidenceKind | None,
    target: CastleIdentity,
    roster: PncAccountCastleRosterConfig | None,
) -> CurrentCastleMatch:
    """Returns whether the current-castle evidence can deterministically satisfy the explicit target."""

    if current_castle is None or evidence_kind is None:
        return CurrentCastleMatch(status=CurrentCastleMatchStatus.INSUFFICIENT_EVIDENCE)
    if evidence_kind == CurrentCastleEvidenceKind.EXACT:
        if _castle_identities_match_exact(current_castle, target):
            return CurrentCastleMatch(status=CurrentCastleMatchStatus.MATCH, evidence_kind=evidence_kind)
        return CurrentCastleMatch(status=CurrentCastleMatchStatus.MISMATCH, evidence_kind=evidence_kind)
    if not castle_names_match(current_castle.castle_name, target.castle_name):
        return CurrentCastleMatch(status=CurrentCastleMatchStatus.MISMATCH, evidence_kind=evidence_kind)
    if roster is None:
        return CurrentCastleMatch(status=CurrentCastleMatchStatus.INSUFFICIENT_EVIDENCE, evidence_kind=evidence_kind)
    matching_castles = tuple(
        castle for castle in roster.castles if castle_names_match(castle.castle_name, current_castle.castle_name)
    )
    if not matching_castles:
        return CurrentCastleMatch(status=CurrentCastleMatchStatus.INSUFFICIENT_EVIDENCE, evidence_kind=evidence_kind)
    matched_castle = resolve_unambiguous_castle_identity(
        matching_castles,
        preferred_name=current_castle.castle_name,
    )
    if matched_castle is None:
        return CurrentCastleMatch(status=CurrentCastleMatchStatus.AMBIGUOUS_NAME, evidence_kind=evidence_kind)
    if not _castle_levels_match(current_castle, matched_castle):
        return CurrentCastleMatch(status=CurrentCastleMatchStatus.MISMATCH, evidence_kind=evidence_kind)
    if _castle_identities_match_exact(matched_castle, target):
        return CurrentCastleMatch(status=CurrentCastleMatchStatus.MATCH, evidence_kind=evidence_kind)
    return CurrentCastleMatch(status=CurrentCastleMatchStatus.MISMATCH, evidence_kind=evidence_kind)


def _castle_identities_match_exact(left: CastleIdentity, right: CastleIdentity) -> bool:
    """Returns whether two castle identities match without wildcard kingdom behavior."""

    return (
        left.kingdom == right.kingdom
        and castle_names_match(left.castle_name, right.castle_name)
        and _castle_levels_match(left, right)
    )


def _castle_levels_match(left: CastleIdentity, right: CastleIdentity) -> bool:
    """Returns whether two castle identities remain compatible after optional level enrichment."""

    if left.castle_level is None or right.castle_level is None:
        return True
    return left.castle_level == right.castle_level


def _group_semantic_castle_identities(candidates: tuple[CastleIdentity, ...]) -> tuple[tuple[CastleIdentity, ...], ...]:
    """Groups castles by shared semantic identity while preserving roster order."""

    groups: list[list[CastleIdentity]] = []
    for candidate in candidates:
        for group in groups:
            if castle_identities_match(group[0], candidate):
                group.append(candidate)
                break
        else:
            groups.append([candidate])
    return tuple(tuple(group) for group in groups)


def _list_entry_title_matches(entry: DetectedListEntry, title_text: str) -> bool:
    """Returns whether one observed title satisfies the canonical matching policy for its entry kind."""

    if entry.title_text is None:
        return False
    if entry.kind == ListEntryKind.CASTLE:
        return castle_names_match(entry.title_text, title_text)
    return entry.title_text == title_text


def _is_integer_pair(value: object) -> bool:
    """Returns whether one object is a 2-tuple of integers."""

    return (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], int)
        and isinstance(value[1], int)
    )


def _is_numeric_pair(value: object) -> bool:
    """Returns whether one object is a 2-tuple of numeric values."""

    return (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], int | float)
        and isinstance(value[1], int | float)
    )
