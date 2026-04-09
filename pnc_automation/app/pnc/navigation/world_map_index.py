"""Canonical survey/index helpers for repeated world-map viewport observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
)


class WorldMapObjectAddressingKind(StrEnum):
    """Describes how one indexed world-map object key was derived."""

    ESTIMATED_WORLD = "estimated_world"
    CONFIRMED_WORLD = "confirmed_world"
    VIEWPORT_RELATIVE = "viewport_relative"


@dataclass(frozen=True, slots=True)
class WorldMapObjectKey:
    """Identifies one world-map object across repeated viewport observations."""

    kind: SpatialObjectKind
    addressing_kind: WorldMapObjectAddressingKind
    coordinate: tuple[int, int]
    viewport_offset_ratio: tuple[float, float] | None = None
    label_text: str | None = None
    alliance_tag: str | None = None
    kingdom: str | None = None
    level: int | None = None

    def __post_init__(self) -> None:
        """Rejects incomplete or malformed world-map object keys before indexing begins."""

        if len(self.coordinate) != 2 or not all(isinstance(value, int) for value in self.coordinate):
            raise SelectorResolutionError(
                "World-map object keys require one integer coordinate pair.",
                coordinate=self.coordinate,
                addressing_kind=self.addressing_kind,
            )
        if self.viewport_offset_ratio is not None:
            if len(self.viewport_offset_ratio) != 2 or not all(
                isinstance(value, int | float) for value in self.viewport_offset_ratio
            ):
                raise SelectorResolutionError(
                    "World-map object keys require numeric viewport_offset_ratio values when present.",
                    viewport_offset_ratio=self.viewport_offset_ratio,
                )
        if self.label_text is not None and self.label_text.strip() == "":
            raise SelectorResolutionError("World-map object keys must not use blank label_text values.")
        if self.kingdom is not None and self.kingdom.strip() == "":
            raise SelectorResolutionError("World-map object keys must not use blank kingdom values.")


@dataclass(frozen=True, slots=True)
class WorldMapObjectSighting:
    """Stores the latest indexed evidence for one typed world-map object."""

    key: WorldMapObjectKey
    object_: DetectedSpatialObject
    viewport_coordinate: tuple[int, int]
    artifact_path: Path | None = None
    captured_at: datetime | None = None
    resolved_player_name: str | None = None
    profile_artifact_path: Path | None = None

    def __post_init__(self) -> None:
        """Rejects incomplete world-map sightings so the index always stays queryable."""

        if len(self.viewport_coordinate) != 2 or not all(isinstance(value, int) for value in self.viewport_coordinate):
            raise SelectorResolutionError(
                "World-map sightings require one integer viewport coordinate pair.",
                viewport_coordinate=self.viewport_coordinate,
            )
        if self.resolved_player_name is not None and self.resolved_player_name.strip() == "":
            raise SelectorResolutionError("World-map sightings must not use blank resolved_player_name values.")

    @property
    def is_castle(self) -> bool:
        """Returns whether the indexed sighting is a castle candidate."""

        return self.object_.kind == SpatialObjectKind.CASTLE

    def matches_player_name(self, player_name: str) -> bool:
        """Returns whether the visible world-map castle label exposes the requested exact player name."""

        normalized_name = player_name.strip()
        return self.object_.name_text == normalized_name

    def matches_castle_query(self, query: "WorldMapCastleQuery") -> bool:
        """Returns whether the castle sighting satisfies the requested high-level lookup constraints."""

        if not self.is_castle:
            return False
        if query.player_name is not None and not self.matches_player_name(query.player_name):
            return False
        if query.label_text is not None and self.object_.name_text != query.label_text:
            return False
        if query.kingdom is not None and self.object_.kingdom != query.kingdom:
            return False
        if query.alliance_tag is not None and self.object_.alliance_tag != query.alliance_tag:
            return False
        if query.level is not None and self.object_.level != query.level:
            return False
        if query.coordinate is not None and self.key.coordinate != query.coordinate:
            return False
        return True

    def matches_object_query(self, query: SpatialObjectQuery) -> bool:
        """Returns whether the indexed sighting satisfies the requested generic spatial-object query."""

        if query.surface_type not in {None, SpatialSurfaceType.WORLD_MAP}:
            return False
        return self.object_.matches(query)


@dataclass(frozen=True, slots=True)
class WorldMapCastleQuery:
    """Defines one high-level castle lookup against indexed world-map sightings."""

    player_name: str | None = None
    label_text: str | None = None
    kingdom: str | None = None
    alliance_tag: str | None = None
    level: int | None = None
    coordinate: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        """Rejects blank or empty castle queries so runtime lookups stay explicit and deterministic."""

        if self.player_name is not None and self.player_name.strip() == "":
            raise SelectorResolutionError("World-map castle queries must not use blank player_name values.")
        if self.label_text is not None and self.label_text.strip() == "":
            raise SelectorResolutionError("World-map castle queries must not use blank label_text values.")
        if self.kingdom is not None and self.kingdom.strip() == "":
            raise SelectorResolutionError("World-map castle queries must not use blank kingdom values.")
        if self.alliance_tag is not None and self.alliance_tag.strip() == "":
            raise SelectorResolutionError("World-map castle queries must not use blank alliance_tag values.")
        if self.level is not None and self.level <= 0:
            raise SelectorResolutionError("World-map castle queries must use a positive level when present.", level=self.level)
        if self.coordinate is not None:
            if len(self.coordinate) != 2 or not all(isinstance(value, int) for value in self.coordinate):
                raise SelectorResolutionError(
                    "World-map castle queries require one integer coordinate pair when coordinate is provided.",
                    coordinate=self.coordinate,
                )
        if all(
            value is None
            for value in (
                self.player_name,
                self.label_text,
                self.kingdom,
                self.alliance_tag,
                self.level,
                self.coordinate,
            )
        ):
            raise SelectorResolutionError("World-map castle queries must constrain at least one identifying field.")


@dataclass(slots=True)
class WorldMapSurveyIndex:
    """Indexes typed world-map object sightings across repeated viewport captures without conflating evidence classes."""

    _ordered_keys: list[WorldMapObjectKey] = field(default_factory=list)
    _sightings_by_key: dict[WorldMapObjectKey, WorldMapObjectSighting] = field(default_factory=dict)

    @property
    def sightings(self) -> tuple[WorldMapObjectSighting, ...]:
        """Returns every indexed sighting in first-seen order."""

        return tuple(self._sightings_by_key[key] for key in self._ordered_keys)

    def ingest_observation(self, observation: Observation) -> tuple[WorldMapObjectSighting, ...]:
        """Indexes the visible objects from one world-map observation."""

        surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        return self.ingest_surface(
            surface,
            artifact_path=observation.artifact_path,
            captured_at=observation.captured_at,
        )

    def ingest_surface(
        self,
        surface: SpatialSurfaceObservation,
        *,
        artifact_path: Path | None = None,
        captured_at: datetime | None = None,
    ) -> tuple[WorldMapObjectSighting, ...]:
        """Indexes the visible objects from one world-map spatial surface."""

        if surface.surface_type != SpatialSurfaceType.WORLD_MAP:
            raise SelectorResolutionError(
                "WorldMapSurveyIndex can only ingest world-map spatial surfaces.",
                surface_type=surface.surface_type,
            )
        viewport_coordinate = surface.viewport.coordinate
        if viewport_coordinate is None:
            raise SelectorResolutionError(
                "World-map survey indexing requires a coordinate-addressable viewport.",
                surface_type=surface.surface_type,
            )
        updated_sightings: list[WorldMapObjectSighting] = []
        for object_ in surface.objects:
            key = build_world_map_object_key(surface=surface, object_=object_)
            existing = self._sightings_by_key.get(key)
            if existing is None:
                self._ordered_keys.append(key)
                sighting = WorldMapObjectSighting(
                    key=key,
                    object_=object_,
                    viewport_coordinate=viewport_coordinate,
                    artifact_path=artifact_path,
                    captured_at=captured_at,
                )
            else:
                sighting = replace(
                    existing,
                    object_=object_,
                    viewport_coordinate=viewport_coordinate,
                    artifact_path=artifact_path if artifact_path is not None else existing.artifact_path,
                    captured_at=captured_at if captured_at is not None else existing.captured_at,
                )
            self._sightings_by_key[key] = sighting
            updated_sightings.append(sighting)
        return tuple(updated_sightings)

    def annotate_castle_player_name(
        self,
        key: WorldMapObjectKey,
        *,
        player_name: str,
        profile_artifact_path: Path | None = None,
    ) -> WorldMapObjectSighting:
        """Attaches one resolved player-profile name to an indexed castle sighting."""

        normalized_name = player_name.strip()
        if normalized_name == "":
            raise SelectorResolutionError("World-map castle annotations require a non-blank player_name.")
        sighting = self.require_sighting(key)
        if not sighting.is_castle:
            raise SelectorResolutionError(
                "Only castle sightings can be annotated with player-profile names.",
                object_kind=sighting.object_.kind,
                key=key,
            )
        if (
            sighting.object_.relationship != SpatialObjectRelationship.SELF
            and sighting.object_.name_text is not None
            and sighting.object_.name_text != normalized_name
        ):
            raise SelectorResolutionError(
                "Non-self castle profile names must stay consistent with the visible world-map castle label.",
                key=key,
                label_text=sighting.object_.name_text,
                player_name=normalized_name,
            )
        updated = replace(
            sighting,
            resolved_player_name=normalized_name,
            profile_artifact_path=profile_artifact_path if profile_artifact_path is not None else sighting.profile_artifact_path,
        )
        self._sightings_by_key[key] = updated
        return updated

    def require_sighting(self, key: WorldMapObjectKey) -> WorldMapObjectSighting:
        """Returns one indexed sighting or fails fast when the requested key is absent."""

        sighting = self._sightings_by_key.get(key)
        if sighting is not None:
            return sighting
        raise SelectorResolutionError("The requested world-map sighting key is not indexed.", key=key)

    def castle_sightings(self) -> tuple[WorldMapObjectSighting, ...]:
        """Returns every indexed castle sighting in first-seen order."""

        return tuple(sighting for sighting in self.sightings if sighting.is_castle)

    def unresolved_castle_sightings(self) -> tuple[WorldMapObjectSighting, ...]:
        """Returns every indexed castle sighting whose player-profile name is still unresolved."""

        return tuple(sighting for sighting in self.castle_sightings() if sighting.resolved_player_name is None)

    def find_object(self, query: SpatialObjectQuery) -> WorldMapObjectSighting | None:
        """Returns the indexed world-map sighting satisfying the requested generic spatial-object query when available."""

        for sighting in self.sightings:
            if sighting.matches_object_query(query):
                return sighting
        return None

    def find_objects(self, query: SpatialObjectQuery) -> tuple[WorldMapObjectSighting, ...]:
        """Returns every indexed world-map sighting satisfying the requested generic spatial-object query."""

        return tuple(sighting for sighting in self.sightings if sighting.matches_object_query(query))

    def require_object(self, query: SpatialObjectQuery) -> WorldMapObjectSighting:
        """Returns one required indexed world-map sighting or fails fast when the query does not resolve."""

        sighting = self.find_object(query)
        if sighting is not None:
            return sighting
        raise SelectorResolutionError(
            "The requested world-map object sighting is not indexed.",
            object_kind=None if query.kind is None else query.kind.value,
            relationship=None if query.relationship is None else query.relationship.value,
            name_text=query.name_text,
            alliance_tag=query.alliance_tag,
            kingdom=query.kingdom,
            level=query.level,
            metadata_key=query.metadata_key,
            metadata_value=query.metadata_value,
        )

    def find_castle(self, query: WorldMapCastleQuery) -> WorldMapObjectSighting | None:
        """Returns the indexed castle sighting satisfying the requested high-level lookup when available."""

        for sighting in self.castle_sightings():
            if sighting.matches_castle_query(query):
                return sighting
        return None

    def require_castle(self, query: WorldMapCastleQuery) -> WorldMapObjectSighting:
        """Returns one required indexed castle sighting or fails fast when the query does not resolve."""

        sighting = self.find_castle(query)
        if sighting is not None:
            return sighting
        raise SelectorResolutionError(
            "The requested world-map castle sighting is not indexed.",
            player_name=query.player_name,
            label_text=query.label_text,
            kingdom=query.kingdom,
            alliance_tag=query.alliance_tag,
            level=query.level,
            coordinate=query.coordinate,
        )

    def find_castle_by_player_name(self, player_name: str) -> WorldMapObjectSighting | None:
        """Returns the indexed castle sighting whose visible world-map label matches the requested player name."""

        return self.find_castle(WorldMapCastleQuery(player_name=player_name))

    def snapshot(
        self,
        *,
        artifact_directory: str,
        label: str,
        captured_at: datetime,
        artifact_path: Path | None,
        surface: SpatialSurfaceObservation,
    ) -> dict[str, object]:
        """Exports the exact indexed survey state plus one explicit checkpoint context as a JSON-ready document."""

        if surface.surface_type != SpatialSurfaceType.WORLD_MAP:
            raise SelectorResolutionError(
                "World-map survey snapshots require a world-map spatial surface.",
                surface_type=surface.surface_type,
            )
        return {
            "schema_version": 1,
            "checkpoint": {
                "artifact_directory": artifact_directory,
                "label": label,
                "captured_at": captured_at.isoformat(),
                "surface_type": surface.surface_type.value,
                "screenshot_artifact_path": None if artifact_path is None else str(artifact_path),
                "viewport": _serialize_viewport(surface),
            },
            "sightings": [_serialize_sighting(sighting) for sighting in self.sightings],
        }


def build_world_map_object_key(
    *,
    surface: SpatialSurfaceObservation,
    object_: DetectedSpatialObject,
) -> WorldMapObjectKey:
    """Builds the canonical reusable index key for one visible world-map object while keeping coordinate evidence explicit."""

    if surface.surface_type != SpatialSurfaceType.WORLD_MAP:
        raise SelectorResolutionError(
            "World-map object keys can only be built from world-map spatial surfaces.",
            surface_type=surface.surface_type,
        )
    if object_.confirmed_world_coordinate is not None:
        return WorldMapObjectKey(
            kind=object_.kind,
            addressing_kind=WorldMapObjectAddressingKind.CONFIRMED_WORLD,
            coordinate=object_.confirmed_world_coordinate,
            label_text=object_.name_text,
            alliance_tag=object_.alliance_tag,
            kingdom=object_.kingdom,
            level=object_.level,
        )
    if object_.estimated_world_coordinate is not None:
        return WorldMapObjectKey(
            kind=object_.kind,
            addressing_kind=WorldMapObjectAddressingKind.ESTIMATED_WORLD,
            coordinate=object_.estimated_world_coordinate,
            label_text=object_.name_text,
            alliance_tag=object_.alliance_tag,
            kingdom=object_.kingdom,
            level=object_.level,
        )
    viewport_coordinate = surface.viewport.coordinate
    if viewport_coordinate is None:
        raise SelectorResolutionError(
            "Viewport-relative world-map object keys require a coordinate-addressable viewport.",
            surface_type=surface.surface_type,
        )
    if object_.viewport_offset_ratio is None and object_.name_text is None:
        raise SelectorResolutionError(
            "Viewport-relative world-map object keys require either viewport_offset_ratio or name_text evidence.",
            object_kind=object_.kind,
            viewport_coordinate=viewport_coordinate,
        )
    return WorldMapObjectKey(
        kind=object_.kind,
        addressing_kind=WorldMapObjectAddressingKind.VIEWPORT_RELATIVE,
        coordinate=viewport_coordinate,
        viewport_offset_ratio=_rounded_ratio_pair(object_.viewport_offset_ratio),
        label_text=object_.name_text,
        alliance_tag=object_.alliance_tag,
        kingdom=object_.kingdom,
        level=object_.level,
    )


def _rounded_ratio_pair(value: tuple[float, float] | None) -> tuple[float, float] | None:
    """Rounds normalized viewport ratios so repeated sightings hash together consistently."""

    if value is None:
        return None
    return (round(float(value[0]), 4), round(float(value[1]), 4))


def _serialize_sighting(sighting: WorldMapObjectSighting) -> dict[str, object]:
    """Serializes one indexed world-map sighting without dropping evidence distinctions."""

    return {
        "key": _serialize_key(sighting.key),
        "object": _serialize_spatial_object(sighting.object_),
        "viewport_coordinate": _serialize_int_pair(sighting.viewport_coordinate),
        "artifact_path": None if sighting.artifact_path is None else str(sighting.artifact_path),
        "captured_at": None if sighting.captured_at is None else sighting.captured_at.isoformat(),
        "resolved_player_name": sighting.resolved_player_name,
        "profile_artifact_path": None if sighting.profile_artifact_path is None else str(sighting.profile_artifact_path),
    }


def _serialize_key(key: WorldMapObjectKey) -> dict[str, object]:
    """Serializes one stable world-map object key exactly as indexed."""

    return {
        "kind": key.kind.value,
        "addressing_kind": key.addressing_kind.value,
        "coordinate": _serialize_int_pair(key.coordinate),
        "viewport_offset_ratio": _serialize_float_pair(key.viewport_offset_ratio),
        "label_text": key.label_text,
        "alliance_tag": key.alliance_tag,
        "kingdom": key.kingdom,
        "level": key.level,
    }


def _serialize_spatial_object(object_: DetectedSpatialObject) -> dict[str, object]:
    """Serializes one typed spatial object with its full stored evidence payload."""

    return {
        "kind": object_.kind.value,
        "bounds": {
            "x": object_.bounds.x,
            "y": object_.bounds.y,
            "width": object_.bounds.width,
            "height": object_.bounds.height,
        },
        "relationship": object_.relationship.value,
        "name_text": object_.name_text,
        "alliance_tag": object_.alliance_tag,
        "level": object_.level,
        "kingdom": object_.kingdom,
        "action_point": _serialize_int_pair(object_.action_point),
        "viewport_offset": _serialize_int_pair(object_.viewport_offset),
        "viewport_offset_ratio": _serialize_float_pair(object_.viewport_offset_ratio),
        "estimated_world_coordinate": _serialize_int_pair(object_.estimated_world_coordinate),
        "confirmed_world_coordinate": _serialize_int_pair(object_.confirmed_world_coordinate),
        "metadata": _serialize_mapping(object_.metadata),
    }


def _serialize_viewport(surface: SpatialSurfaceObservation) -> dict[str, object]:
    """Serializes the checkpoint viewport context without inventing coordinate evidence."""

    return {
        "addressing_kind": surface.viewport.addressing_kind.value,
        "coordinate": _serialize_int_pair(surface.viewport.coordinate),
        "x": surface.viewport.x,
        "y": surface.viewport.y,
        "zoom_bucket": surface.viewport.zoom_bucket,
        "metadata": _serialize_mapping(surface.viewport.metadata),
    }


def _serialize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Returns a JSON-safe shallow copy of one mapping payload."""

    return {
        key: _serialize_value(item)
        for key, item in value.items()
    }


def _serialize_value(value: Any) -> Any:
    """Serializes one arbitrary snapshot value into a JSON-safe primitive tree."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return _serialize_mapping(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


def _serialize_int_pair(value: tuple[int, int] | None) -> dict[str, int] | None:
    """Serializes one integer pair into an explicit named coordinate object."""

    if value is None:
        return None
    return {
        "x": value[0],
        "y": value[1],
    }


def _serialize_float_pair(value: tuple[float, float] | None) -> dict[str, float] | None:
    """Serializes one float pair into an explicit named ratio object."""

    if value is None:
        return None
    return {
        "x": float(value[0]),
        "y": float(value[1]),
    }
