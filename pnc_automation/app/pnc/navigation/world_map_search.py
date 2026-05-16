"""Canonical world-map search contracts and runtime orchestration."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from pnc_automation.app.pnc.domain.action_requests import (
    ActionRequest,
    InputTextAction,
    KeyEventAction,
    TapAction,
    TapPointAction,
)
from pnc_automation.app.pnc.domain.mail import PlayerProfileRoute
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.mail import PlayerProfileRouteKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    WorldCoordinate,
    WorldMapCardinalDirection,
    WorldMapNavigator,
)
from pnc_automation.app.pnc.navigation.world_map_index import (
    WorldMapCastleQuery,
    WorldMapObjectKey,
    WorldMapObjectSighting,
    WorldMapSurveyIndex,
    build_world_map_object_key,
)
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import (
    WorldMapBounds,
    WorldMapCoordinateDomain,
    is_integer_pair,
)
from pnc_automation.app.pnc.navigation.world_map_overview_projection import (
    project_overview_marker_to_world_coordinate,
    project_world_coordinate_to_overview_point,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.pnc.navigation.world_map_traversal import (
    WorldMapEdge,
    WorldMapSearchBoundaryKind,
    WorldMapSearchPatternKind,
    WorldMapTraversalCheckpoint,
    WorldMapTraversalEdgeBand,
    WorldMapTraversalPlanner,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.world_map_coordinates import parse_world_coordinate_dialog_field_text
from pnc_automation.core.errors import SelectorResolutionError

if TYPE_CHECKING:
    from pnc_automation.app.pnc.vision.observation_builder import ObservationService


class WorldMapObservedActionExecutor(Protocol):
    """Defines the narrow action-execution contract the search layer needs without importing the automation package."""

    def execute_actions(
        self,
        actions: Sequence[ActionRequest],
        initial_observation: Observation,
        *,
        observe: Any,
    ) -> Any:
        """Executes actions and returns an object exposing the freshest observation."""


class WorldMapSearchOriginKind(StrEnum):
    """Defines the supported origin-resolution modes for one search request."""

    SELF_TERRITORY = "self_territory"
    CURRENT_VIEWPORT = "current_viewport"
    EXPLICIT_COORDINATE = "explicit_coordinate"
    MAP_CORNER = "map_corner"
    MAP_EDGE_REFERENCE = "map_edge_reference"


class WorldMapMapCorner(StrEnum):
    """Defines one exact map-corner reference used by origin resolution."""

    UPPER_LEFT = "upper_left"
    UPPER_RIGHT = "upper_right"
    LOWER_LEFT = "lower_left"
    LOWER_RIGHT = "lower_right"


class WorldMapMovementToolKind(StrEnum):
    """Defines the low-level movement primitives the search engine may choose from."""

    SWIPE = "swipe"
    COORDINATE_JUMP = "coordinate_jump"
    OVERVIEW_SEED = "overview_seed"


class WorldMapCardinalMovementClassification(StrEnum):
    """Classifies one observed cardinal world-map movement increment."""

    MOVED = "moved"
    MOVED_WITH_DRIFT = "moved_with_drift"
    EXPECTED_BOUNDARY_STOP = "expected_boundary_stop"
    INTERIOR_STALL = "interior_stall"
    PARSER_UNCERTAIN = "parser_uncertain"
    UNEXPECTED_DELTA = "unexpected_delta"


class WorldMapCastleEnrichmentPolicyKind(StrEnum):
    """Defines when the search engine may inspect castles beyond map-side evidence."""

    DISABLED = "disabled"
    WHEN_REQUIRED = "when_required"


class WorldMapSearchStopReason(StrEnum):
    """Defines why one world-map search terminated."""

    FIRST_CONFIRMED_MATCH = "first_confirmed_match"
    MATCH_LIMIT_REACHED = "match_limit_reached"
    CHECKPOINT_BUDGET_EXHAUSTED = "checkpoint_budget_exhausted"
    RADIUS_LIMIT_REACHED = "radius_limit_reached"
    BOUNDARY_EXHAUSTED = "boundary_exhausted"
    ROUTE_EXHAUSTED = "route_exhausted"


@dataclass(frozen=True, slots=True)
class WorldMapSearchPattern:
    """Defines one canonical world-map traversal pattern."""

    kind: WorldMapSearchPatternKind

    @classmethod
    def row_major_sweep(cls) -> "WorldMapSearchPattern":
        """Returns the canonical row-major sweep pattern."""

        return cls(WorldMapSearchPatternKind.ROW_MAJOR_SWEEP)

    @classmethod
    def expanding_ring(cls) -> "WorldMapSearchPattern":
        """Returns the canonical expanding-ring pattern."""

        return cls(WorldMapSearchPatternKind.EXPANDING_RING)

    @classmethod
    def edge_band_sweep(cls) -> "WorldMapSearchPattern":
        """Returns the canonical edge-band sweep pattern."""

        return cls(WorldMapSearchPatternKind.EDGE_BAND_SWEEP)


@dataclass(frozen=True, slots=True)
class WorldMapSearchOrigin:
    """Defines how one search request should resolve its traversal origin."""

    kind: WorldMapSearchOriginKind
    coordinate: tuple[int, int] | None = None
    corner: WorldMapMapCorner | None = None
    edge: WorldMapEdge | None = None

    def __post_init__(self) -> None:
        """Rejects inconsistent origin payloads before planning begins."""

        if self.coordinate is not None and not is_integer_pair(self.coordinate):
            raise SelectorResolutionError(
                "World-map search origins require one integer coordinate pair when coordinate is present.",
                coordinate=self.coordinate,
            )
        if self.kind == WorldMapSearchOriginKind.EXPLICIT_COORDINATE:
            if self.coordinate is None:
                raise SelectorResolutionError("Explicit-coordinate search origins require one coordinate pair.")
            if self.corner is not None or self.edge is not None:
                raise SelectorResolutionError("Explicit-coordinate origins must not also declare corner or edge hints.")
            return
        if self.kind == WorldMapSearchOriginKind.MAP_CORNER:
            if self.corner is None:
                raise SelectorResolutionError("Map-corner search origins require one exact map corner.")
            if self.coordinate is not None or self.edge is not None:
                raise SelectorResolutionError("Map-corner origins must not also declare coordinate or edge values.")
            return
        if self.kind == WorldMapSearchOriginKind.MAP_EDGE_REFERENCE:
            if self.edge is None:
                raise SelectorResolutionError("Map-edge-reference origins require one exact map edge.")
            if self.coordinate is not None or self.corner is not None:
                raise SelectorResolutionError("Map-edge-reference origins must not also declare coordinate or corner values.")
            return
        if self.coordinate is not None or self.corner is not None or self.edge is not None:
            raise SelectorResolutionError(
                "Viewport- and self-derived search origins must not carry explicit coordinate, corner, or edge payloads.",
                kind=self.kind.value,
            )

    @classmethod
    def self_territory(cls) -> "WorldMapSearchOrigin":
        """Returns the canonical self-territory origin."""

        return cls(WorldMapSearchOriginKind.SELF_TERRITORY)

    @classmethod
    def current_viewport(cls) -> "WorldMapSearchOrigin":
        """Returns the canonical current-viewport origin."""

        return cls(WorldMapSearchOriginKind.CURRENT_VIEWPORT)

    @classmethod
    def explicit_coordinate(cls, coordinate: tuple[int, int]) -> "WorldMapSearchOrigin":
        """Returns the canonical explicit-coordinate origin."""

        return cls(WorldMapSearchOriginKind.EXPLICIT_COORDINATE, coordinate=coordinate)

    @classmethod
    def map_corner(cls, corner: WorldMapMapCorner) -> "WorldMapSearchOrigin":
        """Returns the canonical map-corner origin."""

        return cls(WorldMapSearchOriginKind.MAP_CORNER, corner=corner)

    @classmethod
    def map_edge_reference(cls, edge: WorldMapEdge) -> "WorldMapSearchOrigin":
        """Returns the canonical map-edge reference origin."""

        return cls(WorldMapSearchOriginKind.MAP_EDGE_REFERENCE, edge=edge)


@dataclass(frozen=True, slots=True)
class WorldMapSearchBoundary:
    """Defines the allowed coverage region for one world-map search."""

    kind: WorldMapSearchBoundaryKind
    radius_units: int | None = None
    rectangle_bounds: WorldMapBounds | None = None
    map_bounds: WorldMapBounds | None = None
    edges: tuple[WorldMapEdge, ...] = ()
    band_width_units: int | None = None

    def __post_init__(self) -> None:
        """Rejects inconsistent boundary payloads before traversal planning begins."""

        if self.kind == WorldMapSearchBoundaryKind.RADIUS_FROM_ORIGIN:
            if self.radius_units is None or self.radius_units <= 0:
                raise SelectorResolutionError(
                    "Radius-from-origin boundaries require a positive radius_units value.",
                    radius_units=self.radius_units,
                )
            if self.rectangle_bounds is not None or self.map_bounds is not None or self.edges or self.band_width_units is not None:
                raise SelectorResolutionError("Radius boundaries must not declare rectangle, map-bounds, or edge-band payloads.")
            return
        if self.kind == WorldMapSearchBoundaryKind.RECTANGLE:
            if self.rectangle_bounds is None:
                raise SelectorResolutionError("Rectangle search boundaries require explicit rectangular bounds.")
            if self.radius_units is not None or self.map_bounds is not None or self.edges or self.band_width_units is not None:
                raise SelectorResolutionError("Rectangle boundaries must not declare radius, full-map, or edge-band payloads.")
            return
        if self.kind == WorldMapSearchBoundaryKind.FULL_MAP:
            if self.map_bounds is None:
                raise SelectorResolutionError("Full-map search boundaries require resolvable world-map bounds.")
            if self.radius_units is not None or self.rectangle_bounds is not None or self.edges or self.band_width_units is not None:
                raise SelectorResolutionError("Full-map boundaries must not declare radius, rectangle, or edge-band payloads.")
            return
        if self.kind == WorldMapSearchBoundaryKind.EDGE_BAND:
            if self.map_bounds is None:
                raise SelectorResolutionError("Edge-band search boundaries require resolvable world-map bounds.")
            if self.band_width_units is None or self.band_width_units <= 0:
                raise SelectorResolutionError(
                    "Edge-band search boundaries require a positive band_width_units value.",
                    band_width_units=self.band_width_units,
                )
            if not self.edges:
                raise SelectorResolutionError("Edge-band search boundaries require at least one requested edge.")
            if len(frozenset(self.edges)) != len(self.edges):
                raise SelectorResolutionError("Edge-band search boundaries must not repeat edges.", edges=self.edges)
            if self.radius_units is not None or self.rectangle_bounds is not None:
                raise SelectorResolutionError("Edge-band boundaries must not also declare radius or rectangle payloads.")
            return
        raise SelectorResolutionError("Unsupported world-map search boundary kind.", kind=self.kind.value)

    @classmethod
    def radius_from_origin(cls, radius_units: int) -> "WorldMapSearchBoundary":
        """Returns one radius-bounded search boundary."""

        return cls(WorldMapSearchBoundaryKind.RADIUS_FROM_ORIGIN, radius_units=radius_units)

    @classmethod
    def rectangle(cls, *, min_coordinate: tuple[int, int], max_coordinate: tuple[int, int]) -> "WorldMapSearchBoundary":
        """Returns one explicit rectangular search boundary."""

        return cls(
            WorldMapSearchBoundaryKind.RECTANGLE,
            rectangle_bounds=WorldMapBounds(
                min_x=min_coordinate[0],
                min_y=min_coordinate[1],
                max_x=max_coordinate[0],
                max_y=max_coordinate[1],
            ),
        )

    @classmethod
    def full_map(cls, map_bounds: WorldMapBounds) -> "WorldMapSearchBoundary":
        """Returns one full-map search boundary."""

        return cls(WorldMapSearchBoundaryKind.FULL_MAP, map_bounds=map_bounds)

    @classmethod
    def edge_band(
        cls,
        *,
        map_bounds: WorldMapBounds,
        band_width_units: int,
        edges: Sequence[WorldMapEdge],
    ) -> "WorldMapSearchBoundary":
        """Returns one edge-band search boundary."""

        return cls(
            WorldMapSearchBoundaryKind.EDGE_BAND,
            map_bounds=map_bounds,
            band_width_units=band_width_units,
            edges=tuple(edges),
        )


@dataclass(frozen=True, slots=True)
class WorldMapSearchStopPolicy:
    """Defines the explicit stop controls for one search request."""

    max_matches: int | None = None
    max_radius_units: int | None = None
    max_checkpoints: int | None = None
    stop_on_first_confirmed_match: bool = False

    def __post_init__(self) -> None:
        """Rejects invalid stop-policy payloads before traversal begins."""

        if self.max_matches is not None and self.max_matches <= 0:
            raise SelectorResolutionError(
                "World-map search stop policies require positive max_matches when present.",
                max_matches=self.max_matches,
            )
        if self.max_radius_units is not None and self.max_radius_units <= 0:
            raise SelectorResolutionError(
                "World-map search stop policies require positive max_radius_units when present.",
                max_radius_units=self.max_radius_units,
            )
        if self.max_checkpoints is not None and self.max_checkpoints <= 0:
            raise SelectorResolutionError(
                "World-map search stop policies require positive max_checkpoints when present.",
                max_checkpoints=self.max_checkpoints,
            )


@dataclass(frozen=True, slots=True)
class WorldMapMovementPreferences:
    """Defines the ordered low-level movement tools allowed for one search request."""

    allowed_tools: tuple[WorldMapMovementToolKind, ...] = (WorldMapMovementToolKind.SWIPE,)

    def __post_init__(self) -> None:
        """Rejects empty or duplicate movement-tool preferences."""

        if not self.allowed_tools:
            raise SelectorResolutionError("World-map movement preferences must allow at least one movement tool.")
        if len(self.allowed_tools) != len(frozenset(self.allowed_tools)):
            raise SelectorResolutionError(
                "World-map movement preferences must not repeat movement tools.",
                allowed_tools=tuple(tool.value for tool in self.allowed_tools),
            )


@dataclass(frozen=True, slots=True)
class WorldMapCastleEnrichmentPolicy:
    """Defines when the search engine may inspect castles after map-side surveying."""

    kind: WorldMapCastleEnrichmentPolicyKind = WorldMapCastleEnrichmentPolicyKind.WHEN_REQUIRED
    max_candidates: int = 3

    def __post_init__(self) -> None:
        """Rejects invalid enrichment budgets."""

        if self.max_candidates <= 0:
            raise SelectorResolutionError(
                "World-map castle enrichment policies require a positive max_candidates budget.",
                max_candidates=self.max_candidates,
            )


class WorldMapSearchMatcher(ABC):
    """Canonical matcher seam used by the world-map search engine."""

    @abstractmethod
    def matches_visible_object(self, object_: DetectedSpatialObject) -> bool:
        """Returns whether one visible world-map object satisfies the matcher."""

    @abstractmethod
    def matches_sighting(self, sighting: WorldMapObjectSighting) -> bool:
        """Returns whether one indexed sighting satisfies the matcher."""

    def supports_castle_enrichment(self) -> bool:
        """Returns whether this matcher requires castle candidate inspection beyond map-side label matching."""

        return False

    def rank_castle_candidate(self, sighting: WorldMapObjectSighting) -> int:
        """Returns a higher-is-better candidate score, or `-1` when the sighting should not be inspected."""

        return -1

    def supports_castle_profile_validation(self) -> bool:
        """Returns whether this matcher needs the remote lord profile opened for additional validation."""

        return False

    def validate_castle_profile(
        self,
        *,
        sighting: WorldMapObjectSighting,
        observation: Observation,
    ) -> bool:
        """Returns whether the opened lord profile validates the candidate sighting."""

        del sighting, observation
        raise SelectorResolutionError("This world-map matcher does not support castle-profile validation.")


@dataclass(frozen=True, slots=True)
class WorldMapCastleProfileQuery:
    """Defines one future castle-profile validation request anchored by a map-side castle label query."""

    castle: WorldMapCastleQuery


@dataclass(frozen=True, slots=True)
class SpatialObjectSearchMatcher(WorldMapSearchMatcher):
    """Adapts one visible/indexed `SpatialObjectQuery` into the canonical search matcher seam."""

    query: SpatialObjectQuery

    def __post_init__(self) -> None:
        """Rejects queries that cannot apply to world-map search."""

        if self.query.surface_type not in {None, SpatialSurfaceType.WORLD_MAP}:
            raise SelectorResolutionError(
                "World-map object search matchers can only use world-map or surface-agnostic queries.",
                surface_type=None if self.query.surface_type is None else self.query.surface_type.value,
            )

    def matches_visible_object(self, object_: DetectedSpatialObject) -> bool:
        """Returns whether the visible object satisfies the underlying spatial-object query."""

        return object_.matches(self.query)

    def matches_sighting(self, sighting: WorldMapObjectSighting) -> bool:
        """Returns whether the indexed sighting satisfies the underlying spatial-object query."""

        return sighting.matches_object_query(self.query)


@dataclass(frozen=True, slots=True)
class CastleQuerySearchMatcher(WorldMapSearchMatcher):
    """Adapts one castle-specific high-level query into the canonical matcher seam."""

    query: WorldMapCastleQuery

    def matches_visible_object(self, object_: DetectedSpatialObject) -> bool:
        """Returns whether the visible object already satisfies the full castle query."""

        if object_.kind != SpatialObjectKind.CASTLE:
            return False
        if self.query.player_name is not None and object_.name_text != self.query.player_name:
            return False
        if self.query.label_text is not None and object_.name_text != self.query.label_text:
            return False
        if self.query.kingdom is not None and object_.kingdom != self.query.kingdom:
            return False
        if self.query.alliance_tag is not None and object_.alliance_tag != self.query.alliance_tag:
            return False
        if self.query.level is not None and object_.level != self.query.level:
            return False
        if self.query.coordinate is not None and _object_coordinate(object_) != self.query.coordinate:
            return False
        return True

    def matches_sighting(self, sighting: WorldMapObjectSighting) -> bool:
        """Returns whether the indexed sighting satisfies the full castle query."""

        return sighting.matches_castle_query(self.query)

    def supports_castle_enrichment(self) -> bool:
        """Returns `False` because castle-name matching relies on the visible world-map label only."""

        return False

    def rank_castle_candidate(self, sighting: WorldMapObjectSighting) -> int:
        """Returns a deterministic ranking score for one castle candidate based on map-side evidence."""

        if not sighting.is_castle:
            return -1
        if self.query.player_name is not None and sighting.object_.relationship == SpatialObjectRelationship.SELF:
            return -1
        score = 0
        if self.query.coordinate is not None:
            if sighting.key.coordinate != self.query.coordinate:
                return -1
            score += 100
        if self.query.kingdom is not None:
            if sighting.object_.kingdom != self.query.kingdom:
                return -1
            score += 25
        if self.query.alliance_tag is not None:
            if sighting.object_.alliance_tag != self.query.alliance_tag:
                return -1
            score += 15
        if self.query.level is not None:
            if sighting.object_.level != self.query.level:
                return -1
            score += 10
        if self.query.label_text is not None:
            if sighting.object_.name_text != self.query.label_text:
                return -1
            score += 20
        if self.query.player_name is not None and sighting.object_.name_text == self.query.player_name:
            score += 200
        if sighting.resolved_player_name is not None:
            score += 5
        return score


@dataclass(frozen=True, slots=True)
class CastleProfileValidationSearchMatcher(WorldMapSearchMatcher):
    """Anchors one future lord-profile validation flow behind a map-side castle label query."""

    query: WorldMapCastleProfileQuery

    def matches_visible_object(self, object_: DetectedSpatialObject) -> bool:
        """Returns `False` because the final match cannot be confirmed from map-side evidence alone."""

        del object_
        return False

    def matches_sighting(self, sighting: WorldMapObjectSighting) -> bool:
        """Returns `False` because lord-profile validation is intentionally unimplemented today."""

        del sighting
        return False

    def supports_castle_enrichment(self) -> bool:
        """Returns whether the runtime should open candidate lord profiles for later validation."""

        return True

    def supports_castle_profile_validation(self) -> bool:
        """Returns whether the matcher needs the candidate's lord profile opened."""

        return True

    def rank_castle_candidate(self, sighting: WorldMapObjectSighting) -> int:
        """Ranks candidates using the canonical map-side castle label query before opening lord profile."""

        return CastleQuerySearchMatcher(self.query.castle).rank_castle_candidate(sighting)

    def validate_castle_profile(
        self,
        *,
        sighting: WorldMapObjectSighting,
        observation: Observation,
    ) -> bool:
        """Fails fast after the lord profile is opened because gear validation is not implemented yet."""

        raise SelectorResolutionError(
            "Castle lord-profile gear validation is not implemented yet.",
            screen_type=observation.screen_type,
            coordinate=sighting.key.coordinate,
        )


@dataclass(frozen=True, slots=True)
class AllOfWorldMapSearchMatcher(WorldMapSearchMatcher):
    """Combines multiple matchers through logical conjunction."""

    matchers: tuple[WorldMapSearchMatcher, ...]

    def __post_init__(self) -> None:
        """Rejects empty matcher groups."""

        if not self.matchers:
            raise SelectorResolutionError("all_of world-map matchers require at least one child matcher.")

    def matches_visible_object(self, object_: DetectedSpatialObject) -> bool:
        """Returns whether every child matcher accepts the visible object."""

        return all(matcher.matches_visible_object(object_) for matcher in self.matchers)

    def matches_sighting(self, sighting: WorldMapObjectSighting) -> bool:
        """Returns whether every child matcher accepts the indexed sighting."""

        return all(matcher.matches_sighting(sighting) for matcher in self.matchers)

    def supports_castle_enrichment(self) -> bool:
        """Returns whether any conjunct needs castle inspection after all map-side constraints are eligible."""

        return any(matcher.supports_castle_enrichment() for matcher in self.matchers)

    def rank_castle_candidate(self, sighting: WorldMapObjectSighting) -> int:
        """Ranks candidates that satisfy every map-side child and every enrichment child's candidate policy."""

        if not self.supports_castle_enrichment():
            return -1
        score = 0
        for matcher in self.matchers:
            if matcher.supports_castle_enrichment():
                child_score = matcher.rank_castle_candidate(sighting)
                if child_score < 0:
                    return -1
                score += child_score
                continue
            if not matcher.matches_sighting(sighting):
                return -1
            child_score = matcher.rank_castle_candidate(sighting)
            if child_score > 0:
                score += child_score
        return score

    def supports_castle_profile_validation(self) -> bool:
        """Returns whether any child requires a lord-profile validation step."""

        return any(matcher.supports_castle_profile_validation() for matcher in self.matchers)

    def validate_castle_profile(
        self,
        *,
        sighting: WorldMapObjectSighting,
        observation: Observation,
    ) -> bool:
        """Validates every profile-aware child while preserving map-side conjunct constraints."""

        for matcher in self.matchers:
            if matcher.supports_castle_profile_validation():
                if not matcher.validate_castle_profile(sighting=sighting, observation=observation):
                    return False
                continue
            if not matcher.matches_sighting(sighting):
                return False
        return True


@dataclass(frozen=True, slots=True)
class AnyOfWorldMapSearchMatcher(WorldMapSearchMatcher):
    """Combines multiple matchers through logical disjunction."""

    matchers: tuple[WorldMapSearchMatcher, ...]

    def __post_init__(self) -> None:
        """Rejects empty matcher groups."""

        if not self.matchers:
            raise SelectorResolutionError("any_of world-map matchers require at least one child matcher.")

    def matches_visible_object(self, object_: DetectedSpatialObject) -> bool:
        """Returns whether at least one child matcher accepts the visible object."""

        return any(matcher.matches_visible_object(object_) for matcher in self.matchers)

    def matches_sighting(self, sighting: WorldMapObjectSighting) -> bool:
        """Returns whether at least one child matcher accepts the indexed sighting."""

        return any(matcher.matches_sighting(sighting) for matcher in self.matchers)

    def supports_castle_enrichment(self) -> bool:
        """Returns whether any disjunct can benefit from castle inspection."""

        return any(matcher.supports_castle_enrichment() for matcher in self.matchers)

    def rank_castle_candidate(self, sighting: WorldMapObjectSighting) -> int:
        """Returns the best eligible castle-inspection score among child matchers."""

        scores = [
            matcher.rank_castle_candidate(sighting)
            for matcher in self.matchers
            if matcher.supports_castle_enrichment()
        ]
        return max(scores, default=-1)

    def supports_castle_profile_validation(self) -> bool:
        """Returns whether any child requires a lord-profile validation step."""

        return any(matcher.supports_castle_profile_validation() for matcher in self.matchers)

    def validate_castle_profile(
        self,
        *,
        sighting: WorldMapObjectSighting,
        observation: Observation,
    ) -> bool:
        """Accepts a profile when any profile-aware child validates it."""

        for matcher in self.matchers:
            if matcher.supports_castle_profile_validation() and matcher.validate_castle_profile(
                sighting=sighting,
                observation=observation,
            ):
                return True
        return False


@dataclass(frozen=True, slots=True)
class NotWorldMapSearchMatcher(WorldMapSearchMatcher):
    """Negates one child matcher."""

    matcher: WorldMapSearchMatcher

    def matches_visible_object(self, object_: DetectedSpatialObject) -> bool:
        """Returns whether the child matcher rejects the visible object."""

        return not self.matcher.matches_visible_object(object_)

    def matches_sighting(self, sighting: WorldMapObjectSighting) -> bool:
        """Returns whether the child matcher rejects the indexed sighting."""

        return not self.matcher.matches_sighting(sighting)


@dataclass(frozen=True, slots=True)
class CallableWorldMapSearchMatcher(WorldMapSearchMatcher):
    """Adapts one indexed-sighting predicate into the canonical matcher seam for bounded experimentation."""

    predicate: Any

    def __post_init__(self) -> None:
        """Rejects non-callable predicate adapters."""

        if not callable(self.predicate):
            raise SelectorResolutionError("Callable world-map search matchers require a callable predicate.")

    def matches_visible_object(self, object_: DetectedSpatialObject) -> bool:
        """Returns `False` because callable adapters intentionally operate on indexed sightings only."""

        return False

    def matches_sighting(self, sighting: WorldMapObjectSighting) -> bool:
        """Returns whether the predicate accepts the indexed sighting."""

        return bool(self.predicate(sighting))


def adapt_world_map_search_matcher(
    matcher: WorldMapSearchMatcher | SpatialObjectQuery | WorldMapCastleQuery | WorldMapCastleProfileQuery | Any,
) -> WorldMapSearchMatcher:
    """Returns the canonical matcher adapter for one supported matcher input."""

    if isinstance(matcher, WorldMapSearchMatcher):
        return matcher
    if isinstance(matcher, SpatialObjectQuery):
        return SpatialObjectSearchMatcher(matcher)
    if isinstance(matcher, WorldMapCastleQuery):
        return CastleQuerySearchMatcher(matcher)
    if isinstance(matcher, WorldMapCastleProfileQuery):
        return CastleProfileValidationSearchMatcher(matcher)
    if callable(matcher):
        return CallableWorldMapSearchMatcher(matcher)
    raise SelectorResolutionError(
        "Unsupported world-map search matcher input.",
        matcher_type=type(matcher).__name__,
    )


def all_of_world_map_search(
    *matchers: WorldMapSearchMatcher | SpatialObjectQuery | WorldMapCastleQuery | WorldMapCastleProfileQuery | Any,
) -> WorldMapSearchMatcher:
    """Returns one canonical logical-AND matcher composition."""

    return AllOfWorldMapSearchMatcher(tuple(adapt_world_map_search_matcher(matcher) for matcher in matchers))


def any_of_world_map_search(
    *matchers: WorldMapSearchMatcher | SpatialObjectQuery | WorldMapCastleQuery | WorldMapCastleProfileQuery | Any,
) -> WorldMapSearchMatcher:
    """Returns one canonical logical-OR matcher composition."""

    return AnyOfWorldMapSearchMatcher(tuple(adapt_world_map_search_matcher(matcher) for matcher in matchers))


def not_world_map_search(
    matcher: WorldMapSearchMatcher | SpatialObjectQuery | WorldMapCastleQuery | WorldMapCastleProfileQuery | Any,
) -> WorldMapSearchMatcher:
    """Returns one canonical logical-NOT matcher composition."""

    return NotWorldMapSearchMatcher(adapt_world_map_search_matcher(matcher))


@dataclass(frozen=True, slots=True)
class WorldMapSearchRequest:
    """Defines one canonical world-map search request."""

    matcher: WorldMapSearchMatcher | SpatialObjectQuery | WorldMapCastleQuery | WorldMapCastleProfileQuery | Any
    stop_policy: WorldMapSearchStopPolicy
    pattern: WorldMapSearchPattern
    checkpoint_spacing: int
    coordinate_domain: WorldMapCoordinateDomain = field(
        default_factory=WorldMapCoordinateDomain.puzzles_and_conquest,
    )
    origin: WorldMapSearchOrigin | None = None
    boundary: WorldMapSearchBoundary | None = None
    movement_preferences: WorldMapMovementPreferences = field(default_factory=WorldMapMovementPreferences)
    castle_enrichment_policy: WorldMapCastleEnrichmentPolicy = field(default_factory=WorldMapCastleEnrichmentPolicy)

    def __post_init__(self) -> None:
        """Canonicalizes the matcher and rejects unsupported request combinations."""

        object.__setattr__(self, "matcher", adapt_world_map_search_matcher(self.matcher))
        if self.checkpoint_spacing <= 0:
            raise SelectorResolutionError(
                "World-map search requests require a positive checkpoint_spacing value.",
                checkpoint_spacing=self.checkpoint_spacing,
            )
        _validate_boundary_within_coordinate_domain(self.boundary, self.coordinate_domain)
        if self.pattern.kind == WorldMapSearchPatternKind.EDGE_BAND_SWEEP:
            if self.boundary is None or self.boundary.kind != WorldMapSearchBoundaryKind.EDGE_BAND:
                raise SelectorResolutionError(
                    "Edge-band sweep patterns require one edge-band boundary.",
                    pattern=self.pattern.kind.value,
                    boundary_kind=None if self.boundary is None else self.boundary.kind.value,
                )
        if self.origin is not None and self.origin.kind == WorldMapSearchOriginKind.MAP_EDGE_REFERENCE:
            if self.pattern.kind != WorldMapSearchPatternKind.EDGE_BAND_SWEEP:
                raise SelectorResolutionError(
                    "Map-edge-reference origins only make sense for edge-band traversal.",
                    origin_kind=self.origin.kind.value,
                    pattern=self.pattern.kind.value,
                )
        if self.boundary is not None and self.boundary.kind == WorldMapSearchBoundaryKind.EDGE_BAND:
            if self.origin is not None and self.origin.kind not in {
                WorldMapSearchOriginKind.SELF_TERRITORY,
                WorldMapSearchOriginKind.CURRENT_VIEWPORT,
                WorldMapSearchOriginKind.MAP_CORNER,
                WorldMapSearchOriginKind.MAP_EDGE_REFERENCE,
            }:
                raise SelectorResolutionError(
                    "Edge-band boundaries do not support explicit-coordinate origins outside the configured map context.",
                    origin_kind=self.origin.kind.value,
                )


@dataclass(frozen=True, slots=True)
class WorldMapResolvedSearchPlan:
    """Carries the fully resolved planning inputs for one world-map search request."""

    request: WorldMapSearchRequest
    origin_coordinate: tuple[int, int]
    coverage_bounds: WorldMapBounds
    movement_tool: WorldMapMovementToolKind
    route: tuple[WorldMapTraversalCheckpoint, ...]


@dataclass(frozen=True, slots=True)
class WorldMapSearchResult:
    """Summarizes the completed world-map search plus accumulated indexed state."""

    matches: tuple[WorldMapObjectSighting, ...]
    stop_reason: WorldMapSearchStopReason
    visited_checkpoints: tuple[WorldMapTraversalCheckpoint, ...]
    coverage_bounds: WorldMapBounds
    movement_tool: WorldMapMovementToolKind
    castle_enrichment_used: bool
    survey_index: WorldMapSurveyIndex


@dataclass(slots=True)
class WorldMapCoordinateMover:
    """Moves an already-open world-map viewport to one target coordinate using the canonical cardinal-only swipe model."""

    observation_service: "ObservationService | None"
    action_executor: WorldMapObservedActionExecutor | None
    navigator: WorldMapNavigator
    coordinate_domain: WorldMapCoordinateDomain = field(default_factory=WorldMapCoordinateDomain.puzzles_and_conquest)
    movement_step_budget: int = 8
    orthogonal_drift_tolerance: int = 1

    def move_to_coordinate(
        self,
        observation: Observation,
        *,
        target_coordinate: tuple[int, int],
        label_prefix: str,
        runtime_state: dict[str, Any] | None = None,
        boundary_bounds: WorldMapBounds | None = None,
        coordinate_domain: WorldMapCoordinateDomain | None = None,
    ) -> Observation:
        """Moves toward the requested coordinate using bounded cardinal legs and returns the freshest proven world-map observation."""

        active_coordinate_domain = self.coordinate_domain if coordinate_domain is None else coordinate_domain
        addressable_target_coordinate = active_coordinate_domain.nearest_addressable_in_bounds(target_coordinate)
        current = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=observation,
            label_prefix=f"{label_prefix}_start",
        )
        movement_state = _mutable_runtime_state(runtime_state, "world_map_search_swipe_navigation")
        for step_index in range(self.movement_step_budget):
            preferred_axis = _consume_preferred_cardinal_axis(movement_state)
            leg_target = _resolve_cardinal_sweep_leg_target(
                current=current,
                target_coordinate=addressable_target_coordinate,
                focus_tolerance=self.navigator.focus_tolerance,
                preferred_axis=preferred_axis,
            )
            if leg_target is None:
                return current
            before_coordinate = _require_world_map_viewport_coordinate(current)
            actions = self.navigator.plan_focus_coordinate(
                current,
                leg_target,
                runtime_state=movement_state,
            )
            if not actions:
                current_coordinate = _require_world_map_viewport_coordinate(current)
                if _coordinate_within_tolerance(
                    current_coordinate,
                    addressable_target_coordinate,
                    tolerance=self.navigator.focus_tolerance,
                ):
                    continue
                raise SelectorResolutionError(
                    "World-map movement could not derive a cardinal swipe while the requested coordinate remained unresolved.",
                    target_coordinate=addressable_target_coordinate,
                    requested_coordinate=target_coordinate,
                    current_coordinate=current_coordinate,
                    leg_target=(leg_target.x, leg_target.y),
                )
            after = _require_proven_world_map_observation(
                observation_service=self.observation_service,
                observation=self._execute_actions(actions, current, label_prefix=f"{label_prefix}_{step_index}"),
                label_prefix=f"{label_prefix}_refresh_{step_index}",
            )
            after_coordinate = _require_world_map_viewport_coordinate(after)
            direction = _direction_for_cardinal_leg(from_coordinate=before_coordinate, leg_target=leg_target)
            delta = after_coordinate[0] - before_coordinate[0], after_coordinate[1] - before_coordinate[1]
            classification = classify_world_map_cardinal_delta(
                direction=direction,
                before_coordinate=before_coordinate,
                delta=delta,
                boundary_bounds=boundary_bounds,
                orthogonal_drift_tolerance=self.orthogonal_drift_tolerance,
            )
            if classification in {
                WorldMapCardinalMovementClassification.PARSER_UNCERTAIN,
                WorldMapCardinalMovementClassification.UNEXPECTED_DELTA,
                WorldMapCardinalMovementClassification.INTERIOR_STALL,
                WorldMapCardinalMovementClassification.EXPECTED_BOUNDARY_STOP,
            }:
                raise SelectorResolutionError(
                    "World-map movement produced an unusable cardinal swipe delta.",
                    target_coordinate=addressable_target_coordinate,
                    requested_coordinate=target_coordinate,
                    before_coordinate=before_coordinate,
                    after_coordinate=after_coordinate,
                    delta=delta,
                    direction=direction.value,
                    classification=classification.value,
                )
            if classification == WorldMapCardinalMovementClassification.MOVED_WITH_DRIFT:
                _remember_orthogonal_drift_correction(
                    movement_state=movement_state,
                    direction=direction,
                    current_coordinate=after_coordinate,
                    target_coordinate=addressable_target_coordinate,
                    focus_tolerance=self.navigator.focus_tolerance,
                )
            current = after
        raise SelectorResolutionError(
            "World-map movement exhausted its bounded coordinate-focus budget.",
            target_coordinate=addressable_target_coordinate,
            requested_coordinate=target_coordinate,
        )

    def _execute_actions(
        self,
        actions: Sequence[ActionRequest],
        observation: Observation,
        *,
        label_prefix: str,
    ) -> Observation:
        """Executes one movement increment and returns the freshest observed result."""

        if self.action_executor is None or self.observation_service is None:
            raise SelectorResolutionError("World-map coordinate movement requires observation_service and action_executor.")
        return self.action_executor.execute_actions(
            actions,
            observation,
            observe=lambda label, request=None: self.observation_service.observe(f"{label_prefix}_{label}", request=request),
        ).observation


@dataclass(slots=True)
class WorldMapCoordinateDialogState:
    """Captures the committed kingdom/X/Y values visible in the world-map coordinate dialog."""

    kingdom: int
    coordinate: tuple[int, int]


@dataclass(frozen=True, slots=True)
class WorldMapCoordinateJumpPlan:
    """Carries one staged coordinate-dialog jump plan plus the normalized landing target."""

    normalized_target_coordinate: tuple[int, int]
    open_action: ActionRequest | None = None
    fill_actions: tuple[ActionRequest, ...] = ()
    submit_action: ActionRequest | None = None

    def __post_init__(self) -> None:
        """Rejects partially specified jump plans before runtime execution begins."""

        if self.open_action is None and (self.fill_actions or self.submit_action is not None):
            raise SelectorResolutionError("Coordinate-jump plans must open the dialog before editing or submitting.")
        if self.open_action is not None and self.submit_action is None:
            raise SelectorResolutionError("Coordinate-jump plans must include one submit action when they open the dialog.")

    @property
    def requires_execution(self) -> bool:
        """Returns whether the jump still needs dialog execution instead of simple landing verification."""

        return self.open_action is not None


@dataclass(frozen=True, slots=True)
class WorldMapOverviewContext:
    """Carries parsed overview-map evidence needed for bounds/context validation."""

    map_bounds: WorldMapBounds
    current_viewport_coordinate: tuple[int, int]
    map_region_bounds: Bounds
    viewport_marker_point: tuple[int, int]
    kingdom: int | None = None
    kingdom_name: str | None = None


@dataclass(frozen=True, slots=True)
class _ParsedWorldMapOverviewBounds:
    """Carries marker-independent overview evidence shared by bounds and context parsing."""

    map_bounds: WorldMapBounds
    map_region_bounds: Bounds
    kingdom: int | None = None
    kingdom_name: str | None = None


@dataclass(slots=True)
class WorldMapCoordinateNavigator:
    """Owns coordinate-dialog world-map repositioning and committed-field proof."""

    supported: bool = True
    coordinate_domain: WorldMapCoordinateDomain = field(default_factory=WorldMapCoordinateDomain.puzzles_and_conquest)

    def is_supported(self) -> bool:
        """Returns whether coordinate-dialog movement is available in this runtime."""

        return self.supported

    def plan_jump(self, *, target: tuple[int, int], current_observation: Observation) -> WorldMapCoordinateJumpPlan:
        """Plans one staged coordinate jump and exposes the normalized landing target."""

        if not self.is_supported():
            raise SelectorResolutionError(
                "Coordinate-dialog world-map navigation is not configured in this runtime yet.",
                target=target,
                screen_type=current_observation.screen_type,
            )
        current_observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        normalized_target = self.coordinate_domain.nearest_addressable_in_bounds(target)
        current_coordinate = _world_map_viewport_coordinate_or_none(current_observation)
        if current_coordinate == normalized_target:
            return WorldMapCoordinateJumpPlan(normalized_target_coordinate=normalized_target)
        return WorldMapCoordinateJumpPlan(
            normalized_target_coordinate=normalized_target,
            open_action=TapAction(
                selector_id=UiElementId.PNC_WORLD_SEARCH_BUTTON,
                reason="open_world_coordinate_dialog",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            ),
            fill_actions=(
                InputTextAction(
                    selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                    text=str(normalized_target[0]),
                    replace_existing=True,
                    reason="set_world_coordinate_x",
                ),
                KeyEventAction(
                    key_code="KEYCODE_ENTER",
                    reason="commit_world_coordinate_x",
                ),
                InputTextAction(
                    selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
                    text=str(normalized_target[1]),
                    replace_existing=True,
                    reason="set_world_coordinate_y",
                ),
                KeyEventAction(
                    key_code="KEYCODE_ENTER",
                    reason="commit_world_coordinate_y",
                    observe_after=True,
                    follow_up_request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ),
            ),
            submit_action=TapAction(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON,
                reason="submit_world_coordinate_jump",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_coordinate_jump_follow_up(),
            ),
        )

    def require_dialog_state(self, observation: Observation) -> WorldMapCoordinateDialogState:
        """Returns the committed dialog values from one proven coordinate-dialog observation."""

        if observation.screen_type != ScreenType.PNC_WORLD_COORDINATE_DIALOG:
            raise SelectorResolutionError(
                "Coordinate-jump dialog proof requires the coordinate dialog observation.",
                screen_type=observation.screen_type,
            )
        kingdom = _parse_required_dialog_field(
            observation,
            selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
        )
        x = _parse_required_dialog_field(
            observation,
            selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
        )
        y = _parse_required_dialog_field(
            observation,
            selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
        )
        return WorldMapCoordinateDialogState(kingdom=kingdom, coordinate=(x, y))

    def require_pre_submit_state(
        self,
        observation: Observation,
        *,
        plan: WorldMapCoordinateJumpPlan,
        initial_state: WorldMapCoordinateDialogState,
    ) -> WorldMapCoordinateDialogState:
        """Fails fast unless the filled dialog still preserves kingdom and shows the normalized target."""

        current_state = self.require_dialog_state(observation)
        if current_state.kingdom != initial_state.kingdom:
            raise SelectorResolutionError(
                "World-map coordinate jump unexpectedly changed kingdoms before submit.",
                initial_kingdom=initial_state.kingdom,
                current_kingdom=current_state.kingdom,
            )
        if current_state.coordinate != plan.normalized_target_coordinate:
            raise SelectorResolutionError(
                "World-map coordinate jump did not commit the intended X/Y values before submit.",
                expected_coordinate=plan.normalized_target_coordinate,
                current_coordinate=current_state.coordinate,
                kingdom=current_state.kingdom,
            )
        return current_state


@dataclass(slots=True)
class WorldMapOverviewNavigator:
    """Owns overview parsing plus close/recenter choreography without enabling search seeding prematurely."""

    bounds_parsing_supported: bool = True
    movement_supported: bool = True
    coordinate_domain: WorldMapCoordinateDomain = field(default_factory=WorldMapCoordinateDomain.puzzles_and_conquest)

    def is_supported(self) -> bool:
        """Returns whether overview-based movement seeding is available in this runtime."""

        return self.bounds_parsing_supported and self.movement_supported

    def supports_bounds_parsing(self) -> bool:
        """Returns whether parse-only overview bounds/context extraction is available."""

        return self.bounds_parsing_supported

    def plan_open(self, current_observation: Observation) -> tuple[ActionRequest, ...]:
        """Plans opening the overview from one proven world-map observation and carries the current viewport coordinate as detector context."""

        current_observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        return (
            TapAction(
                selector_id=UiElementId.PNC_WORLD_EXPAND_BUTTON,
                reason="open_world_map_overview",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_overview_follow_up(
                    expected_coordinate=_world_map_viewport_coordinate_or_none(current_observation)
                ),
            ),
        )

    def plan_close_in_place(self, observation: Observation) -> tuple[ActionRequest, ...]:
        """Plans closing the overview through the top-right close control."""

        self._require_overview_control(observation, UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON)
        return (
            TapAction(
                selector_id=UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,
                reason="close_world_map_overview",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_overview_exit_follow_up(),
            ),
        )

    def plan_recenter(self, observation: Observation, *, target_coordinate: tuple[int, int]) -> tuple[ActionRequest, ...]:
        """Plans clicking the overview map so it closes and recenters onto the requested target."""

        context = self.parse_context(observation)
        normalized_target = self.normalize_target_coordinate(target_coordinate)
        recenter_region = observation.require(UiElementId.PNC_WORLD_OVERVIEW_RECENTER_REGION).bounds
        tap_point = project_world_coordinate_to_overview_point(
            coordinate=normalized_target,
            bounds=context.map_bounds,
            map_region_bounds=recenter_region,
        )
        return (
            TapPointAction(
                x=tap_point[0],
                y=tap_point[1],
                reason="recenter_world_map_from_overview",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_overview_exit_follow_up(),
            ),
        )

    def normalize_target_coordinate(self, target_coordinate: tuple[int, int]) -> tuple[int, int]:
        """Returns the in-bounds addressable coordinate the overview recenter action should verify."""

        return self.coordinate_domain.nearest_addressable_in_bounds(target_coordinate)

    def plan_open_kingdom_list(self, observation: Observation) -> tuple[ActionRequest, ...]:
        """Plans opening the kingdom-list screen from overview through the left world icon."""

        self._require_overview_control(observation, UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON)
        return (
            TapAction(
                selector_id=UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON,
                reason="open_world_kingdom_list",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_overview_exit_follow_up(),
            ),
        )

    def resolve_world_bounds(self, observation: Observation) -> WorldMapBounds:
        """Returns the parsed world bounds or fails fast when parse-only overview support is unavailable."""

        return self._parse_bounds(observation).map_bounds

    def _require_overview_control(self, observation: Observation, selector_id: UiElementId) -> None:
        """Fails fast unless the requested overview control is visible on one proven overview observation."""

        if observation.screen_type != ScreenType.PNC_WORLD_MAP_OVERVIEW:
            raise SelectorResolutionError(
                "Overview action planning requires a proven world-map overview observation.",
                screen_type=observation.screen_type,
                selector_id=selector_id,
            )
        observation.require(selector_id)

    def parse_context(self, observation: Observation) -> WorldMapOverviewContext:
        """Returns the parsed overview bounds and current viewport marker context."""

        parsed_bounds = self._parse_bounds(observation)
        marker_element = observation.get(UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER)
        if marker_element is None:
            raise SelectorResolutionError(
                "Overview viewport-context parsing requires the current viewport marker to be visible.",
                screen_type=observation.screen_type,
            )
        marker_point = marker_element.action_point if marker_element.action_point is not None else marker_element.bounds.center()
        if not _bounds_contains_point(parsed_bounds.map_region_bounds, marker_point):
            raise SelectorResolutionError(
                "Overview viewport-context parsing requires the viewport marker to remain inside the overview map region.",
                marker_point=marker_point,
                map_region_bounds=parsed_bounds.map_region_bounds,
            )
        coordinate = project_overview_marker_to_world_coordinate(
            marker_point=marker_point,
            map_region_bounds=parsed_bounds.map_region_bounds,
            bounds=parsed_bounds.map_bounds,
        )
        return WorldMapOverviewContext(
            map_bounds=parsed_bounds.map_bounds,
            current_viewport_coordinate=coordinate,
            map_region_bounds=parsed_bounds.map_region_bounds,
            viewport_marker_point=marker_point,
            kingdom=parsed_bounds.kingdom,
            kingdom_name=parsed_bounds.kingdom_name,
        )

    def _parse_bounds(self, observation: Observation) -> _ParsedWorldMapOverviewBounds:
        """Returns marker-independent overview bounds and header evidence from one proven overview observation."""

        if not self.supports_bounds_parsing():
            raise SelectorResolutionError(
                "World-map overview support is not configured in this runtime yet.",
                screen_type=observation.screen_type,
            )
        if observation.screen_type != ScreenType.PNC_WORLD_MAP_OVERVIEW:
            raise SelectorResolutionError(
                "Overview parsing requires a proven world-map overview observation.",
                screen_type=observation.screen_type,
            )
        map_region = observation.require(UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION).bounds
        kingdom: int | None = None
        kingdom_name: str | None = None
        header_element = observation.get(UiElementId.PNC_WORLD_OVERVIEW_HEADER)
        if header_element is not None:
            parsed_header = _parse_world_overview_header_text(header_element.extracted_text)
            if parsed_header is not None:
                kingdom, kingdom_name = parsed_header
        return _ParsedWorldMapOverviewBounds(
            map_bounds=self.coordinate_domain.bounds,
            map_region_bounds=map_region,
            kingdom=kingdom,
            kingdom_name=kingdom_name,
        )


class WorldMapCastleInspector(Protocol):
    """Defines the candidate-inspection seam used by castle enrichment."""

    def inspect_candidates(
        self,
        *,
        matcher: WorldMapSearchMatcher,
        candidates: Sequence[WorldMapObjectSighting],
        current_observation: Observation,
        label_prefix: str,
        runtime_state: dict[str, Any] | None = None,
    ) -> tuple[Observation, tuple[WorldMapObjectSighting, ...]]:
        """Inspects the candidates and returns the latest observation plus any updated sightings."""


@dataclass(slots=True)
class ObservationBackedWorldMapCastleInspector:
    """Inspects indexed castle candidates by opening their territory/profile screens and annotating the shared index."""

    screen_flows: ScreenFlowPlanner
    action_executor: WorldMapObservedActionExecutor
    observation_service: "ObservationService"
    survey_recorder: WorldMapSurveyRecorder
    movement_step_budget: int = 8
    world_map_navigator: WorldMapNavigator | None = None

    def inspect_candidates(
        self,
        *,
        matcher: WorldMapSearchMatcher,
        candidates: Sequence[WorldMapObjectSighting],
        current_observation: Observation,
        label_prefix: str,
        runtime_state: dict[str, Any] | None = None,
    ) -> tuple[Observation, tuple[WorldMapObjectSighting, ...]]:
        """Inspects the candidates in ranking order and annotates any castles whose remote profile exposes a player name."""

        latest_observation = current_observation
        updated_sightings: list[WorldMapObjectSighting] = []
        navigator = self.screen_flows.world_map_navigator if self.world_map_navigator is None else self.world_map_navigator
        for index, candidate in enumerate(candidates):
            latest_observation = self._ensure_world_map(latest_observation, label_prefix=f"{label_prefix}_return_world_{index}")
            latest_observation = self._focus_candidate(
                latest_observation,
                candidate,
                navigator=navigator,
                label_prefix=f"{label_prefix}_focus_{index}",
                runtime_state=runtime_state,
            )
            latest_observation, updated = self._inspect_one_candidate(
                latest_observation,
                candidate,
                matcher=matcher,
                label_prefix=f"{label_prefix}_candidate_{index}",
            )
            if updated is not None:
                updated_sightings.append(updated)
                if matcher.matches_sighting(updated):
                    break
        return latest_observation, tuple(updated_sightings)

    def _ensure_world_map(self, observation: Observation, *, label_prefix: str) -> Observation:
        """Returns a world-map-ready observation through the canonical shared screen-flow entry seam."""

        current = observation
        for step_index in range(self.movement_step_budget):
            if current.blocking_popup or current.screen_type == ScreenType.PNC_POPUP:
                actions = self.screen_flows.close_blocking_popup(current)
                if not actions:
                    raise SelectorResolutionError(
                        "Castle inspection could not derive a popup-dismissal action while returning to world map.",
                        screen_type=current.screen_type,
                    )
                current = self._execute_actions(actions, current, label_prefix=f"{label_prefix}_close_popup_{step_index}")
                continue
            if current.screen_type == ScreenType.UNKNOWN:
                actions = self.screen_flows.recover_unknown_game_screen(
                    current,
                    reason=f"{label_prefix}_recover_unknown",
                )
                if not actions:
                    raise SelectorResolutionError(
                        "Castle inspection could not derive an unknown-screen recovery action while returning to world map.",
                        screen_type=current.screen_type,
                    )
                current = self._execute_actions(actions, current, label_prefix=f"{label_prefix}_recover_unknown_{step_index}")
                continue
            if current.screen_type == ScreenType.PNC_WORLD_MAP:
                return _require_proven_world_map_observation(
                    observation_service=self.observation_service,
                    observation=current,
                    label_prefix=f"{label_prefix}_refresh_surface_{step_index}",
                )
            actions = self.screen_flows.ensure_world_map_ready(current)
            if not actions:
                raise SelectorResolutionError(
                    "Castle inspection could not derive a world-map return action.",
                    screen_type=current.screen_type,
                )
            current = self._execute_actions(actions, current, label_prefix=f"{label_prefix}_{step_index}")
        raise SelectorResolutionError(
            "Castle inspection exhausted its bounded world-map return budget.",
            screen_type=current.screen_type,
        )

    def _focus_candidate(
        self,
        observation: Observation,
        candidate: WorldMapObjectSighting,
        *,
        navigator: WorldMapNavigator,
        label_prefix: str,
        runtime_state: dict[str, Any] | None,
    ) -> Observation:
        """Moves the viewport toward the candidate coordinate before inspection."""

        current = observation
        movement_state = _mutable_runtime_state(runtime_state, "world_map_castle_inspector_swipe_navigation")
        for step_index in range(self.movement_step_budget):
            current = self._ensure_world_map(current, label_prefix=f"{label_prefix}_ready_{step_index}")
            if _candidate_is_visible_on_surface(observation=current, candidate=candidate):
                return current
            actions = navigator.plan_focus_coordinate(
                current,
                WorldCoordinate(x=candidate.key.coordinate[0], y=candidate.key.coordinate[1]),
                runtime_state=movement_state,
            )
            if not actions:
                if _candidate_is_visible_on_surface(observation=current, candidate=candidate):
                    return current
                raise SelectorResolutionError(
                    "Castle candidate focus could not derive a movement action before the target became visible.",
                    coordinate=candidate.key.coordinate,
                )
            current = self._execute_actions(actions, current, label_prefix=f"{label_prefix}_{step_index}")
        raise SelectorResolutionError(
            "Castle candidate inspection exhausted its bounded coordinate-focus budget.",
            coordinate=candidate.key.coordinate,
        )

    def _inspect_one_candidate(
        self,
        observation: Observation,
        candidate: WorldMapObjectSighting,
        *,
        matcher: WorldMapSearchMatcher,
        label_prefix: str,
    ) -> tuple[Observation, WorldMapObjectSighting | None]:
        """Attempts to open the candidate, inspect the remote player profile, annotate the index, and return to world map."""

        surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        visible_target = next(
            (
                object_
                for object_ in surface.objects
                if build_world_map_object_key(surface=surface, object_=object_) == candidate.key
            ),
            None,
        )
        if visible_target is None:
            return observation, None
        opened = self._execute_actions(
            self.screen_flows.world_map_navigator.tap_visible_object(
                observation,
                visible_target,
                reason="inspect_world_map_castle_candidate",
            ),
            observation,
            label_prefix=f"{label_prefix}_open",
        )
        if opened.screen_type != ScreenType.PNC_PLAYER_TERRITORY:
            return opened, None
        profiled = self._execute_actions(
            self.screen_flows.open_player_profile(
                opened,
                PlayerProfileRoute(kind=PlayerProfileRouteKind.PLAYER_TERRITORY),
            ),
            opened,
            label_prefix=f"{label_prefix}_profile",
        )
        updated: WorldMapObjectSighting | None = None
        profile_validation_error: SelectorResolutionError | None = None
        if profiled.screen_type == ScreenType.PNC_PLAYER_PROFILE and matcher.supports_castle_profile_validation():
            try:
                matcher.validate_castle_profile(sighting=candidate, observation=profiled)
            except SelectorResolutionError as error:
                profile_validation_error = error
        elif profiled.screen_type == ScreenType.PNC_PLAYER_PROFILE and profiled.profile_player_name is not None:
            updated = self.survey_recorder.annotate_castle_player_name(
                candidate.key,
                player_name=profiled.profile_player_name,
                profile_artifact_path=profiled.artifact_path,
            )
        latest = self._execute_actions(
            [KeyEventAction(key_code="KEYCODE_BACK", reason="leave_player_profile", observe_after=True)],
            profiled,
            label_prefix=f"{label_prefix}_back_profile",
        )
        if latest.screen_type != ScreenType.PNC_WORLD_MAP:
            latest = self._execute_actions(
                [KeyEventAction(key_code="KEYCODE_BACK", reason="leave_player_territory", observe_after=True)],
                latest,
                label_prefix=f"{label_prefix}_back_territory",
            )
        if profile_validation_error is not None:
            raise profile_validation_error
        return latest, updated

    def _execute_actions(
        self,
        actions: Sequence[ActionRequest],
        observation: Observation,
        *,
        label_prefix: str,
    ) -> Observation:
        """Executes the actions and returns the freshest observed result."""

        return self.action_executor.execute_actions(
            actions,
            observation,
            observe=lambda label, request=None: self.observation_service.observe(f"{label_prefix}_{label}", request=request),
        ).observation


@dataclass(slots=True)
class WorldMapSearchService:
    """Canonical owner for world-map request validation, traversal planning, checkpoint ingestion, and search execution."""

    screen_flows: ScreenFlowPlanner
    traversal_planner: WorldMapTraversalPlanner = field(default_factory=WorldMapTraversalPlanner)
    coordinate_navigator: WorldMapCoordinateNavigator = field(default_factory=WorldMapCoordinateNavigator)
    overview_navigator: WorldMapOverviewNavigator = field(default_factory=WorldMapOverviewNavigator)
    observation_service: "ObservationService | None" = None
    action_executor: WorldMapObservedActionExecutor | None = None
    survey_recorder: WorldMapSurveyRecorder | None = None
    castle_inspector: WorldMapCastleInspector | None = None
    coordinate_mover: WorldMapCoordinateMover | None = None
    world_map_entry_step_budget: int = 6
    movement_step_budget: int = 8

    def resolve_plan(self, request: WorldMapSearchRequest, observation: Observation) -> WorldMapResolvedSearchPlan:
        """Resolves one request against the current world-map surface into a deterministic traversal plan."""

        surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        origin = self._resolve_origin_coordinate(request=request, surface=surface)
        coverage_bounds = self._resolve_coverage_bounds(request=request, origin_coordinate=origin)
        movement_tool = self._select_movement_tool(request=request)
        route = self.traversal_planner.build_route(
            pattern_kind=request.pattern.kind,
            coordinate_domain=request.coordinate_domain,
            origin_coordinate=origin,
            coverage_bounds=coverage_bounds,
            spacing=request.checkpoint_spacing,
            edge_band=_traversal_edge_band(request),
        )
        return WorldMapResolvedSearchPlan(
            request=request,
            origin_coordinate=origin,
            coverage_bounds=coverage_bounds,
            movement_tool=movement_tool,
            route=route,
        )

    def execute_search(
        self,
        request: WorldMapSearchRequest,
        *,
        label_prefix: str,
        start_observation: Observation | None = None,
        runtime_state: dict[str, Any] | None = None,
    ) -> WorldMapSearchResult:
        """Runs the canonical world-map search loop end to end using the configured runtime services."""

        if self.observation_service is None or self.action_executor is None or self.survey_recorder is None:
            raise SelectorResolutionError(
                "World-map search execution requires observation_service, action_executor, and survey_recorder dependencies."
            )
        current_observation = start_observation or self.observation_service.observe(f"{label_prefix}_start")
        if current_observation.screen_type != ScreenType.PNC_WORLD_MAP or current_observation.spatial_surface is None:
            raise SelectorResolutionError(
                "World-map search execution requires the caller to provide or capture a proven world-map observation first.",
                screen_type=current_observation.screen_type,
            )
        plan = self.resolve_plan(request, current_observation)
        matched_keys: list[WorldMapObjectKey] = []
        matched_by_key: dict[WorldMapObjectKey, WorldMapObjectSighting] = {}
        visited_checkpoints: list[WorldMapTraversalCheckpoint] = []
        castle_enrichment_used = False
        route = plan.route
        for checkpoint in route:
            if request.stop_policy.max_radius_units is not None and checkpoint.distance_from_origin > request.stop_policy.max_radius_units:
                return self._build_result(
                    matched_keys=matched_keys,
                    matched_by_key=matched_by_key,
                    stop_reason=WorldMapSearchStopReason.RADIUS_LIMIT_REACHED,
                    visited_checkpoints=visited_checkpoints,
                    plan=plan,
                    castle_enrichment_used=castle_enrichment_used,
                )
            current_observation = self.move_to_checkpoint(
                current_observation,
                plan=plan,
                checkpoint=checkpoint,
                label_prefix=f"{label_prefix}_move_{checkpoint.route_index}",
                runtime_state=runtime_state,
            )
            current_observation = self._ingest_checkpoint_observation(
                current_observation,
                label=f"{label_prefix}_checkpoint_{checkpoint.route_index}",
            )
            visited_checkpoints.append(checkpoint)
            self._collect_checkpoint_matches(
                request=request,
                observation=current_observation,
                matched_keys=matched_keys,
                matched_by_key=matched_by_key,
            )
            stop_reason = self._evaluate_stop_policy(
                request=request,
                route=route,
                checkpoint=checkpoint,
                matched_count=len(matched_keys),
                visited_count=len(visited_checkpoints),
            )
            if stop_reason is not None:
                return self._build_result(
                    matched_keys=matched_keys,
                    matched_by_key=matched_by_key,
                    stop_reason=stop_reason,
                    visited_checkpoints=visited_checkpoints,
                    plan=plan,
                    castle_enrichment_used=castle_enrichment_used,
                )
            if (
                request.castle_enrichment_policy.kind == WorldMapCastleEnrichmentPolicyKind.WHEN_REQUIRED
                and request.matcher.supports_castle_enrichment()
                and self.castle_inspector is not None
                and not matched_keys
            ):
                candidates = tuple(
                    _rank_castle_candidates(
                        matcher=request.matcher,
                        index=self.survey_recorder.index,
                    )[: request.castle_enrichment_policy.max_candidates]
                )
                if candidates:
                    castle_enrichment_used = True
                    current_observation, _ = self.castle_inspector.inspect_candidates(
                        matcher=request.matcher,
                        candidates=candidates,
                        current_observation=current_observation,
                        label_prefix=f"{label_prefix}_castle_enrichment_{checkpoint.route_index}",
                        runtime_state=runtime_state,
                    )
                    self._collect_index_matches(
                        matcher=request.matcher,
                        matched_keys=matched_keys,
                        matched_by_key=matched_by_key,
                    )
                    stop_reason = self._evaluate_stop_policy(
                        request=request,
                        route=route,
                        checkpoint=checkpoint,
                        matched_count=len(matched_keys),
                        visited_count=len(visited_checkpoints),
                    )
                    if stop_reason is not None:
                        return self._build_result(
                            matched_keys=matched_keys,
                            matched_by_key=matched_by_key,
                            stop_reason=stop_reason,
                            visited_checkpoints=visited_checkpoints,
                            plan=plan,
                            castle_enrichment_used=castle_enrichment_used,
                        )
        return self._build_result(
            matched_keys=matched_keys,
            matched_by_key=matched_by_key,
            stop_reason=(
                WorldMapSearchStopReason.BOUNDARY_EXHAUSTED
                if request.boundary is not None
                else WorldMapSearchStopReason.ROUTE_EXHAUSTED
            ),
            visited_checkpoints=visited_checkpoints,
            plan=plan,
            castle_enrichment_used=castle_enrichment_used,
        )

    def _build_result(
        self,
        *,
        matched_keys: Sequence[WorldMapObjectKey],
        matched_by_key: Mapping[WorldMapObjectKey, WorldMapObjectSighting],
        stop_reason: WorldMapSearchStopReason,
        visited_checkpoints: Sequence[WorldMapTraversalCheckpoint],
        plan: WorldMapResolvedSearchPlan,
        castle_enrichment_used: bool,
    ) -> WorldMapSearchResult:
        """Builds one canonical search result from the accumulated runtime state."""

        assert self.survey_recorder is not None
        return WorldMapSearchResult(
            matches=tuple(matched_by_key[key] for key in matched_keys),
            stop_reason=stop_reason,
            visited_checkpoints=tuple(visited_checkpoints),
            coverage_bounds=plan.coverage_bounds,
            movement_tool=plan.movement_tool,
            castle_enrichment_used=castle_enrichment_used,
            survey_index=self.survey_recorder.index,
        )

    def move_to_checkpoint(
        self,
        observation: Observation,
        *,
        plan: WorldMapResolvedSearchPlan,
        checkpoint: WorldMapTraversalCheckpoint,
        label_prefix: str,
        runtime_state: dict[str, Any] | None = None,
    ) -> Observation:
        """Moves toward the requested checkpoint using the selected low-level movement primitive."""

        if plan.movement_tool == WorldMapMovementToolKind.COORDINATE_JUMP:
            return self._move_with_coordinate_jump(observation, checkpoint=checkpoint, label_prefix=label_prefix)
        if plan.movement_tool == WorldMapMovementToolKind.OVERVIEW_SEED:
            return self._move_with_overview_seed(observation, checkpoint=checkpoint, label_prefix=label_prefix)
        return self.coordinate_mover_for_runtime().move_to_coordinate(
            observation,
            target_coordinate=checkpoint.coordinate,
            label_prefix=label_prefix,
            runtime_state=runtime_state,
            boundary_bounds=_known_world_map_bounds(plan.request),
            coordinate_domain=plan.request.coordinate_domain,
        )

    def _move_with_coordinate_jump(
        self,
        observation: Observation,
        *,
        checkpoint: WorldMapTraversalCheckpoint,
        label_prefix: str,
    ) -> Observation:
        """Executes one coordinate-jump move or fails fast when the runtime lacks the required primitive."""

        plan = self.coordinate_navigator.plan_jump(target=checkpoint.coordinate, current_observation=observation)
        if not plan.requires_execution:
            proven = _require_proven_world_map_observation(
                observation_service=self.observation_service,
                observation=observation,
                label_prefix=f"{label_prefix}_already_at_target",
            )
            self._require_checkpoint_landing(
                proven,
                checkpoint=checkpoint,
                requested_coordinate=plan.normalized_target_coordinate,
            )
            return proven
        assert plan.open_action is not None and plan.submit_action is not None
        opened = self._execute_actions([plan.open_action], observation, label_prefix=f"{label_prefix}_open")
        initial_dialog_state = self.coordinate_navigator.require_dialog_state(opened)
        filled = opened
        if plan.fill_actions:
            filled = self._execute_actions(plan.fill_actions, opened, label_prefix=f"{label_prefix}_fill")
        self.coordinate_navigator.require_pre_submit_state(
            filled,
            plan=plan,
            initial_state=initial_dialog_state,
        )
        after = self._execute_actions([plan.submit_action], filled, label_prefix=f"{label_prefix}_submit")
        _raise_if_world_map_coordinate_jump_status_banner(after, target_coordinate=checkpoint.coordinate)
        proven = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=after,
            label_prefix=f"{label_prefix}_verify_landing",
        )
        self._require_checkpoint_landing(
            proven,
            checkpoint=checkpoint,
            requested_coordinate=plan.normalized_target_coordinate,
        )
        return proven

    def _require_checkpoint_landing(
        self,
        observation: Observation,
        *,
        checkpoint: WorldMapTraversalCheckpoint,
        requested_coordinate: tuple[int, int],
    ) -> None:
        """Fails fast unless the proven world-map viewport is focused on the requested checkpoint."""

        current_coordinate = _require_world_map_viewport_coordinate(observation)
        tolerance = self.screen_flows.world_map_navigator.focus_tolerance
        if _coordinate_within_tolerance(current_coordinate, checkpoint.coordinate, tolerance=tolerance):
            return
        raise SelectorResolutionError(
            "World-map coordinate jump did not land at the requested checkpoint.",
            target_coordinate=checkpoint.coordinate,
            requested_coordinate=requested_coordinate,
            current_coordinate=current_coordinate,
            focus_tolerance=tolerance,
        )

    def _move_with_overview_seed(
        self,
        observation: Observation,
        *,
        checkpoint: WorldMapTraversalCheckpoint,
        label_prefix: str,
    ) -> Observation:
        """Executes one overview-assisted move or fails fast when the runtime lacks the required primitive."""

        if not self.overview_navigator.is_supported():
            raise SelectorResolutionError(
                "Overview-assisted world-map movement is not configured in this runtime yet.",
                screen_type=observation.screen_type,
                label_prefix=label_prefix,
            )
        normalized_target = self.overview_navigator.normalize_target_coordinate(checkpoint.coordinate)
        opened = self._execute_actions(
            self.overview_navigator.plan_open(observation),
            observation,
            label_prefix=f"{label_prefix}_overview_open",
        )
        after = self._execute_actions(
            self.overview_navigator.plan_recenter(opened, target_coordinate=checkpoint.coordinate),
            opened,
            label_prefix=f"{label_prefix}_overview_recenter",
        )
        proven = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=after,
            label_prefix=f"{label_prefix}_verify_landing",
        )
        self._require_checkpoint_landing(
            proven,
            checkpoint=checkpoint,
            requested_coordinate=normalized_target,
        )
        return proven

    def _execute_actions(
        self,
        actions: Sequence[ActionRequest],
        observation: Observation,
        *,
        label_prefix: str,
    ) -> Observation:
        """Executes the provided actions and returns the freshest observed result."""

        if self.action_executor is None or self.observation_service is None:
            raise SelectorResolutionError("World-map search action execution requires observation_service and action_executor.")
        return self.action_executor.execute_actions(
            actions,
            observation,
            observe=lambda label, request=None: self.observation_service.observe(f"{label_prefix}_{label}", request=request),
        ).observation

    def _ingest_checkpoint_observation(
        self,
        observation: Observation,
        *,
        label: str,
    ) -> Observation:
        """Indexes the already-proven checkpoint observation and only falls back to recapture when the surface is still missing."""

        assert self.survey_recorder is not None
        checkpoint_capture = self.survey_recorder.record_checkpoint(label, observation)
        return observation if checkpoint_capture.capture is None else checkpoint_capture.capture.observation

    def coordinate_mover_for_runtime(self) -> WorldMapCoordinateMover:
        """Returns the canonical coordinate mover shared by sweep traversal and calibration helpers."""

        if self.coordinate_mover is not None:
            return self.coordinate_mover
        return WorldMapCoordinateMover(
            observation_service=self.observation_service,
            action_executor=self.action_executor,
            navigator=self.screen_flows.world_map_navigator,
            coordinate_domain=WorldMapCoordinateDomain.puzzles_and_conquest(),
            movement_step_budget=self.movement_step_budget,
        )

    def _coordinate_mover(self) -> WorldMapCoordinateMover:
        """Returns the canonical coordinate mover for legacy private call sites."""

        return self.coordinate_mover_for_runtime()

    def _resolve_origin_coordinate(
        self,
        *,
        request: WorldMapSearchRequest,
        surface: SpatialSurfaceObservation,
    ) -> tuple[int, int]:
        """Returns the resolved origin coordinate for the request against the active world-map surface."""

        origin = request.origin or WorldMapSearchOrigin.self_territory()
        if origin.kind == WorldMapSearchOriginKind.CURRENT_VIEWPORT:
            coordinate = surface.viewport.coordinate
            if coordinate is None:
                raise SelectorResolutionError(
                    "Current-viewport origin resolution requires a coordinate-addressable world-map viewport.",
                    surface_type=surface.surface_type.value,
                )
            return request.coordinate_domain.nearest_addressable_in_bounds(coordinate)
        if origin.kind == WorldMapSearchOriginKind.EXPLICIT_COORDINATE:
            assert origin.coordinate is not None
            return request.coordinate_domain.nearest_addressable_in_bounds(origin.coordinate)
        if origin.kind == WorldMapSearchOriginKind.SELF_TERRITORY:
            return request.coordinate_domain.nearest_addressable_in_bounds(_resolve_self_territory_origin(surface))
        if origin.kind == WorldMapSearchOriginKind.MAP_CORNER:
            bounds = _require_map_bounds(request)
            assert origin.corner is not None
            return request.coordinate_domain.nearest_addressable_in_bounds(_coordinate_for_corner(bounds, origin.corner))
        if origin.kind == WorldMapSearchOriginKind.MAP_EDGE_REFERENCE:
            bounds = _require_map_bounds(request)
            assert origin.edge is not None
            return request.coordinate_domain.nearest_addressable_in_bounds(_coordinate_for_edge(bounds, origin.edge))
        raise SelectorResolutionError("Unsupported world-map search origin.", origin_kind=origin.kind.value)

    def _resolve_coverage_bounds(
        self,
        *,
        request: WorldMapSearchRequest,
        origin_coordinate: tuple[int, int],
    ) -> WorldMapBounds:
        """Returns the concrete inclusive coverage bounds implied by the request and resolved origin."""

        boundary = request.boundary
        if boundary is None:
            return WorldMapBounds(
                min_x=origin_coordinate[0],
                min_y=origin_coordinate[1],
                max_x=origin_coordinate[0],
                max_y=origin_coordinate[1],
            )
        if boundary.kind == WorldMapSearchBoundaryKind.RADIUS_FROM_ORIGIN:
            radius = boundary.radius_units or 0
            return request.coordinate_domain.clamp_bounds(
                WorldMapBounds(
                    min_x=max(0, origin_coordinate[0] - radius),
                    min_y=max(0, origin_coordinate[1] - radius),
                    max_x=origin_coordinate[0] + radius,
                    max_y=origin_coordinate[1] + radius,
                )
            )
        if boundary.kind == WorldMapSearchBoundaryKind.RECTANGLE:
            assert boundary.rectangle_bounds is not None
            request.coordinate_domain.require_bounds_inside(boundary.rectangle_bounds)
            return boundary.rectangle_bounds
        if boundary.kind == WorldMapSearchBoundaryKind.FULL_MAP:
            assert boundary.map_bounds is not None
            request.coordinate_domain.require_bounds_inside(boundary.map_bounds)
            return boundary.map_bounds
        if boundary.kind == WorldMapSearchBoundaryKind.EDGE_BAND:
            assert boundary.map_bounds is not None
            request.coordinate_domain.require_bounds_inside(boundary.map_bounds)
            return boundary.map_bounds
        raise SelectorResolutionError("Unsupported world-map search boundary kind.", boundary_kind=boundary.kind.value)

    def _select_movement_tool(self, *, request: WorldMapSearchRequest) -> WorldMapMovementToolKind:
        """Returns the first allowed movement tool supported by the current runtime."""

        for tool in request.movement_preferences.allowed_tools:
            if tool == WorldMapMovementToolKind.SWIPE:
                return tool
            if tool == WorldMapMovementToolKind.COORDINATE_JUMP and self.coordinate_navigator.is_supported():
                return tool
            if tool == WorldMapMovementToolKind.OVERVIEW_SEED and self.overview_navigator.is_supported():
                return tool
        raise SelectorResolutionError(
            "The requested world-map movement preferences cannot be satisfied by the current runtime.",
            allowed_tools=tuple(tool.value for tool in request.movement_preferences.allowed_tools),
        )

    def _collect_checkpoint_matches(
        self,
        *,
        request: WorldMapSearchRequest,
        observation: Observation,
        matched_keys: list[WorldMapObjectKey],
        matched_by_key: dict[WorldMapObjectKey, WorldMapObjectSighting],
    ) -> None:
        """Collects visible and indexed matches after one checkpoint capture."""

        assert self.survey_recorder is not None
        surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        for object_ in surface.objects:
            if not request.matcher.matches_visible_object(object_):
                continue
            sighting = self.survey_recorder.index.require_sighting(build_world_map_object_key(surface=surface, object_=object_))
            _remember_match(sighting=sighting, matched_keys=matched_keys, matched_by_key=matched_by_key)
        self._collect_index_matches(
            matcher=request.matcher,
            matched_keys=matched_keys,
            matched_by_key=matched_by_key,
        )

    def _collect_index_matches(
        self,
        *,
        matcher: WorldMapSearchMatcher,
        matched_keys: list[WorldMapObjectKey],
        matched_by_key: dict[WorldMapObjectKey, WorldMapObjectSighting],
    ) -> None:
        """Collects every indexed match currently satisfying the matcher."""

        assert self.survey_recorder is not None
        for sighting in self.survey_recorder.index.sightings:
            if matcher.matches_sighting(sighting):
                _remember_match(sighting=sighting, matched_keys=matched_keys, matched_by_key=matched_by_key)

    def _evaluate_stop_policy(
        self,
        *,
        request: WorldMapSearchRequest,
        route: Sequence[WorldMapTraversalCheckpoint],
        checkpoint: WorldMapTraversalCheckpoint,
        matched_count: int,
        visited_count: int,
    ) -> WorldMapSearchStopReason | None:
        """Returns the stop reason once the request's explicit stop policy has been satisfied."""

        stop_policy = request.stop_policy
        if matched_count > 0 and stop_policy.stop_on_first_confirmed_match:
            return WorldMapSearchStopReason.FIRST_CONFIRMED_MATCH
        if stop_policy.max_matches is not None and matched_count >= stop_policy.max_matches:
            return WorldMapSearchStopReason.MATCH_LIMIT_REACHED
        if stop_policy.max_checkpoints is not None and visited_count >= stop_policy.max_checkpoints and checkpoint.route_index < len(route) - 1:
            return WorldMapSearchStopReason.CHECKPOINT_BUDGET_EXHAUSTED
        return None


def _resolve_self_territory_origin(surface: SpatialSurfaceObservation) -> tuple[int, int]:
    """Returns the self-territory origin coordinate from the active world-map surface or fails fast."""

    for object_ in surface.objects:
        if object_.kind != SpatialObjectKind.CASTLE or object_.relationship != SpatialObjectRelationship.SELF:
            continue
        coordinate = _object_coordinate(object_)
        if coordinate is None:
            raise SelectorResolutionError(
                "World-map search requires the visible self territory to expose its own world coordinate.",
                surface_type=surface.surface_type.value,
            )
        return coordinate
    raise SelectorResolutionError(
        "World-map search could not resolve the self-territory origin from the active surface.",
        surface_type=surface.surface_type.value,
    )


def _require_map_bounds(request: WorldMapSearchRequest) -> WorldMapBounds:
    """Returns the map bounds required by the request or fails fast when they are unavailable."""

    boundary = request.boundary
    if boundary is None or boundary.map_bounds is None:
        raise SelectorResolutionError(
            "This world-map search request requires resolvable map bounds.",
            boundary_kind=None if boundary is None else boundary.kind.value,
        )
    return boundary.map_bounds


def _coordinate_for_corner(bounds: WorldMapBounds, corner: WorldMapMapCorner) -> tuple[int, int]:
    """Returns the exact coordinate implied by the requested map corner."""

    if corner == WorldMapMapCorner.UPPER_LEFT:
        return bounds.min_x, bounds.min_y
    if corner == WorldMapMapCorner.UPPER_RIGHT:
        return bounds.max_x, bounds.min_y
    if corner == WorldMapMapCorner.LOWER_LEFT:
        return bounds.min_x, bounds.max_y
    return bounds.max_x, bounds.max_y


def _coordinate_for_edge(bounds: WorldMapBounds, edge: WorldMapEdge) -> tuple[int, int]:
    """Returns one deterministic coordinate centered on the requested edge."""

    center_x = (bounds.min_x + bounds.max_x) // 2
    center_y = (bounds.min_y + bounds.max_y) // 2
    if edge == WorldMapEdge.LEFT:
        return bounds.min_x, center_y
    if edge == WorldMapEdge.RIGHT:
        return bounds.max_x, center_y
    if edge == WorldMapEdge.TOP:
        return center_x, bounds.min_y
    return center_x, bounds.max_y


def _rank_castle_candidates(
    *,
    matcher: WorldMapSearchMatcher,
    index: WorldMapSurveyIndex,
) -> list[WorldMapObjectSighting]:
    """Returns unresolved castle sightings sorted by descending candidate-likelihood score."""

    ranked = [
        (matcher.rank_castle_candidate(candidate), candidate)
        for candidate in index.unresolved_castle_sightings()
    ]
    return [
        candidate
        for score, candidate in sorted(ranked, key=lambda item: (-item[0], item[1].key.coordinate))
        if score >= 0
    ]


def _remember_match(
    *,
    sighting: WorldMapObjectSighting,
    matched_keys: list[WorldMapObjectKey],
    matched_by_key: dict[WorldMapObjectKey, WorldMapObjectSighting],
) -> None:
    """Remembers one matched sighting while preserving first-found order and latest evidence."""

    if sighting.key not in matched_by_key:
        matched_keys.append(sighting.key)
    matched_by_key[sighting.key] = sighting


def _candidate_is_visible_on_surface(*, observation: Observation, candidate: WorldMapObjectSighting) -> bool:
    """Returns whether the indexed candidate is already visible on the current world-map surface."""

    surface = observation.spatial_surface
    if surface is None or surface.surface_type != SpatialSurfaceType.WORLD_MAP:
        return False
    return any(build_world_map_object_key(surface=surface, object_=object_) == candidate.key for object_ in surface.objects)


def _require_proven_world_map_observation(
    *,
    observation_service: "ObservationService | None",
    observation: Observation,
    label_prefix: str,
    refresh_budget: int = 2,
) -> Observation:
    """Returns one proven world-map observation, allowing bounded refresh across strict, coarse, and transient unknown post-action frames."""

    current = observation
    for refresh_index in range(refresh_budget + 1):
        if current.spatial_surface is not None and current.spatial_surface.surface_type == SpatialSurfaceType.WORLD_MAP:
            return current
        if current.screen_type not in {ScreenType.PNC_WORLD_MAP, ScreenType.PNC_WORLD_MAP_ROOT, ScreenType.UNKNOWN}:
            raise SelectorResolutionError(
                "World-map operations require an already-proven world-map observation.",
                screen_type=current.screen_type,
            )
        if observation_service is None or refresh_index >= refresh_budget:
            raise SelectorResolutionError(
                "World-map operations require a parsed world-map surface, but the latest observation did not expose one.",
                screen_type=current.screen_type,
            )
        request = (
            ObservationRequest.full_runtime_default()
            if current.screen_type == ScreenType.UNKNOWN
            else ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP)
        )
        current = observation_service.observe(
            f"{label_prefix}_{refresh_index}",
            request=request,
        )
    raise AssertionError("Unreachable world-map surface refresh fallthrough.")


def _raise_if_world_map_coordinate_jump_status_banner(
    observation: Observation,
    *,
    target_coordinate: tuple[int, int],
) -> None:
    """Fails coordinate-jump navigation with the live in-game rejection banner when OCR captured one."""

    status_banner = observation.get(UiElementId.PNC_STATUS_BANNER)
    if status_banner is None:
        return
    raise SelectorResolutionError(
        "World-map coordinate jump was rejected by an in-game status banner.",
        target_coordinate=target_coordinate,
        status_banner=status_banner.extracted_text,
        screen_type=observation.screen_type,
    )


def _parse_required_dialog_field(observation: Observation, *, selector_id: UiElementId) -> int:
    """Returns one required committed numeric coordinate-dialog field value."""

    state = observation.require_text_field_state(selector_id)
    value = parse_world_coordinate_dialog_field_text(selector_id=selector_id, text=state.text)
    if value is None:
        raise SelectorResolutionError(
            "World-map coordinate dialog proof requires parseable numeric field text.",
            selector_id=selector_id,
            field_text=state.text,
            screen_type=observation.screen_type,
        )
    return value


def _bounds_contains_point(bounds: Bounds, point: tuple[int, int]) -> bool:
    """Returns whether one point lies inside the inclusive rectangle bounds."""

    return (
        bounds.x <= point[0] <= bounds.x + bounds.width
        and bounds.y <= point[1] <= bounds.y + bounds.height
    )


def _parse_world_overview_header_text(text: str | None) -> tuple[int, str | None] | None:
    """Returns the parsed overview kingdom id/name when the header exposes them."""

    if text is None:
        return None
    match = re.search(r"K\s*[:\uff1a]?\s*(\d+)(?:\s+(.*))?", text.strip(), re.IGNORECASE)
    if match is None:
        return None
    kingdom_name = match.group(2).strip() if match.group(2) is not None and match.group(2).strip() != "" else None
    return int(match.group(1)), kingdom_name


def classify_world_map_cardinal_delta(
    *,
    direction: WorldMapCardinalDirection,
    before_coordinate: tuple[int, int] | None,
    delta: tuple[int, int] | None,
    boundary_bounds: WorldMapBounds | None,
    orthogonal_drift_tolerance: int = 1,
) -> WorldMapCardinalMovementClassification:
    """Classifies one observed cardinal movement delta using the shared runtime/calibration semantics."""

    if before_coordinate is None or delta is None:
        return WorldMapCardinalMovementClassification.PARSER_UNCERTAIN
    if delta == (0, 0):
        if is_world_map_coordinate_near_boundary(
            direction=direction,
            coordinate=before_coordinate,
            bounds=boundary_bounds,
        ):
            return WorldMapCardinalMovementClassification.EXPECTED_BOUNDARY_STOP
        return WorldMapCardinalMovementClassification.INTERIOR_STALL
    expected_delta = expected_world_map_cardinal_delta(direction)
    if expected_delta[0] != 0:
        if delta[0] == 0 or (1 if delta[0] > 0 else -1) != expected_delta[0]:
            return WorldMapCardinalMovementClassification.UNEXPECTED_DELTA
        if abs(delta[1]) > orthogonal_drift_tolerance:
            return WorldMapCardinalMovementClassification.MOVED_WITH_DRIFT
        return WorldMapCardinalMovementClassification.MOVED
    if delta[1] == 0 or (1 if delta[1] > 0 else -1) != expected_delta[1]:
        return WorldMapCardinalMovementClassification.UNEXPECTED_DELTA
    if abs(delta[0]) > orthogonal_drift_tolerance:
        return WorldMapCardinalMovementClassification.MOVED_WITH_DRIFT
    return WorldMapCardinalMovementClassification.MOVED


def is_world_map_coordinate_near_boundary(
    *,
    direction: WorldMapCardinalDirection,
    coordinate: tuple[int, int] | None,
    bounds: WorldMapBounds | None,
) -> bool:
    """Returns whether a coordinate lies on the known world-map edge that can legitimately stop the direction."""

    if coordinate is None or bounds is None:
        return False
    expected_delta = expected_world_map_cardinal_delta(direction)
    if expected_delta[0] > 0:
        return coordinate[0] >= bounds.max_x
    if expected_delta[0] < 0:
        return coordinate[0] <= bounds.min_x
    if expected_delta[1] > 0:
        return coordinate[1] >= bounds.max_y
    return coordinate[1] <= bounds.min_y


def expected_world_map_cardinal_delta(direction: WorldMapCardinalDirection) -> tuple[int, int]:
    """Returns the expected signed coordinate delta for one canonical finger-swipe direction."""

    if direction == WorldMapCardinalDirection.LEFT:
        return 1, 0
    if direction == WorldMapCardinalDirection.RIGHT:
        return -1, 0
    if direction == WorldMapCardinalDirection.UP:
        return 0, 1
    return 0, -1


def _object_coordinate(object_: DetectedSpatialObject) -> tuple[int, int] | None:
    """Returns the strongest available world coordinate for one visible object."""

    if object_.confirmed_world_coordinate is not None:
        return object_.confirmed_world_coordinate
    return object_.estimated_world_coordinate


def _require_world_map_viewport_coordinate(observation: Observation) -> tuple[int, int]:
    """Returns the active world-map viewport coordinate or fails fast when the observation is not addressable."""

    coordinate = _world_map_viewport_coordinate_or_none(observation)
    if coordinate is None:
        raise SelectorResolutionError(
            "World-map search movement requires a coordinate-addressable viewport.",
            screen_type=observation.screen_type,
        )
    return coordinate


def _world_map_viewport_coordinate_or_none(observation: Observation) -> tuple[int, int] | None:
    """Returns the active world-map viewport coordinate when the proven surface exposes one."""

    return observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate


def _resolve_cardinal_sweep_leg_target(
    *,
    current: Observation,
    target_coordinate: tuple[int, int],
    focus_tolerance: int,
    preferred_axis: str | None = None,
) -> WorldCoordinate | None:
    """Returns the next canonical cardinal leg, honoring one-shot drift correction before normal axis order."""

    current_coordinate = _require_world_map_viewport_coordinate(current)
    if preferred_axis == "x" and abs(target_coordinate[0] - current_coordinate[0]) > focus_tolerance:
        return WorldCoordinate(x=target_coordinate[0], y=current_coordinate[1])
    if preferred_axis == "y" and abs(target_coordinate[1] - current_coordinate[1]) > focus_tolerance:
        return WorldCoordinate(x=current_coordinate[0], y=target_coordinate[1])
    delta_x = target_coordinate[0] - current_coordinate[0]
    if abs(delta_x) > focus_tolerance:
        return WorldCoordinate(x=target_coordinate[0], y=current_coordinate[1])
    delta_y = target_coordinate[1] - current_coordinate[1]
    if abs(delta_y) > focus_tolerance:
        return WorldCoordinate(x=current_coordinate[0], y=target_coordinate[1])
    return None


def _coordinate_within_tolerance(
    current_coordinate: tuple[int, int],
    target_coordinate: tuple[int, int],
    *,
    tolerance: int,
) -> bool:
    """Returns whether both axes are already inside the requested movement tolerance."""

    return (
        abs(current_coordinate[0] - target_coordinate[0]) <= tolerance
        and abs(current_coordinate[1] - target_coordinate[1]) <= tolerance
    )


def _direction_for_cardinal_leg(
    *,
    from_coordinate: tuple[int, int],
    leg_target: WorldCoordinate,
) -> WorldMapCardinalDirection:
    """Returns the canonical swipe direction implied by one single-axis coordinate leg."""

    delta_x = leg_target.x - from_coordinate[0]
    delta_y = leg_target.y - from_coordinate[1]
    if delta_x != 0 and delta_y != 0:
        raise SelectorResolutionError(
            "Cardinal world-map movement legs must resolve exactly one axis.",
            from_coordinate=from_coordinate,
            leg_target=(leg_target.x, leg_target.y),
        )
    if delta_x > 0:
        return WorldMapCardinalDirection.LEFT
    if delta_x < 0:
        return WorldMapCardinalDirection.RIGHT
    if delta_y > 0:
        return WorldMapCardinalDirection.UP
    if delta_y < 0:
        return WorldMapCardinalDirection.DOWN
    raise SelectorResolutionError(
        "Cardinal world-map movement legs require a non-zero target delta.",
        from_coordinate=from_coordinate,
        leg_target=(leg_target.x, leg_target.y),
    )


def _remember_orthogonal_drift_correction(
    *,
    movement_state: dict[str, Any],
    direction: WorldMapCardinalDirection,
    current_coordinate: tuple[int, int],
    target_coordinate: tuple[int, int],
    focus_tolerance: int,
) -> None:
    """Prioritizes the next leg on the axis opposite the successful but drifting cardinal move."""

    axis = "y" if direction in {WorldMapCardinalDirection.LEFT, WorldMapCardinalDirection.RIGHT} else "x"
    target_axis_value = target_coordinate[1] if axis == "y" else target_coordinate[0]
    current_axis_value = current_coordinate[1] if axis == "y" else current_coordinate[0]
    if abs(target_axis_value - current_axis_value) > focus_tolerance:
        movement_state["preferred_cardinal_axis"] = axis


def _consume_preferred_cardinal_axis(movement_state: dict[str, Any]) -> str | None:
    """Returns and clears the one-shot axis preference produced by orthogonal-drift correction."""

    value = movement_state.pop("preferred_cardinal_axis", None)
    if value in {"x", "y"}:
        return str(value)
    if value is not None:
        raise SelectorResolutionError("Unexpected world-map movement correction axis.", preferred_axis=value)
    return None


def _known_world_map_bounds(request: WorldMapSearchRequest) -> WorldMapBounds | None:
    """Returns true map bounds when the request carries them, avoiding local search bounds as edge evidence."""

    if request.boundary is None:
        return request.coordinate_domain.bounds
    if request.boundary.kind in {WorldMapSearchBoundaryKind.FULL_MAP, WorldMapSearchBoundaryKind.EDGE_BAND}:
        return request.boundary.map_bounds
    return request.coordinate_domain.bounds


def _traversal_edge_band(request: WorldMapSearchRequest) -> WorldMapTraversalEdgeBand | None:
    """Adapts an edge-band search boundary to the traversal module's request-independent payload."""

    boundary = request.boundary
    if boundary is None or boundary.kind != WorldMapSearchBoundaryKind.EDGE_BAND:
        return None
    return WorldMapTraversalEdgeBand(
        edges=boundary.edges,
        band_width_units=boundary.band_width_units or 0,
    )


def _validate_boundary_within_coordinate_domain(
    boundary: WorldMapSearchBoundary | None,
    coordinate_domain: WorldMapCoordinateDomain,
) -> None:
    """Fails fast when explicit search bounds exceed the configured world-map coordinate domain."""

    if boundary is None or boundary.kind == WorldMapSearchBoundaryKind.RADIUS_FROM_ORIGIN:
        return
    bounds = boundary.rectangle_bounds if boundary.kind == WorldMapSearchBoundaryKind.RECTANGLE else boundary.map_bounds
    if bounds is None:
        return
    coordinate_domain.require_bounds_inside(bounds)


def _mutable_runtime_state(runtime_state: dict[str, Any] | None, key: str) -> dict[str, Any]:
    """Returns one mutable nested runtime-state mapping when a caller provided shared runtime state."""

    if runtime_state is None:
        return {}
    nested = runtime_state.get(key)
    if isinstance(nested, dict):
        return nested
    nested = {}
    runtime_state[key] = nested
    return nested
