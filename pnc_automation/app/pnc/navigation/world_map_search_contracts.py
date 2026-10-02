"""Canonical world-map search request/plan contracts and matcher seam, free of runtime composition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import (
    WorldMapBounds,
    WorldMapCoordinateDomain,
    is_integer_pair,
)
from pnc_automation.app.pnc.navigation.world_map_index import (
    WorldMapCastleQuery,
    WorldMapObjectSighting,
)
from pnc_automation.app.pnc.navigation.world_map_sweep import (
    WorldMapSweepPlan,
    WorldMapSweepPolicy,
)
from pnc_automation.app.pnc.navigation.world_map_traversal import (
    ResolvedTraversalStride,
    TraversalRotation,
    TraversalStridePolicy,
    WorldMapSearchBoundaryKind,
    WorldMapSearchPatternKind,
    WorldMapTraversalCheckpoint,
    WorldMapTraversalCorner,
    WorldMapTraversalExecutionPlan,
    WorldMapTraversalRoutePlan,
)
from pnc_automation.core.errors import SelectorResolutionError


class WorldMapSearchOriginKind(StrEnum):
    """Defines the supported origin-resolution modes for one search request."""

    SELF_TERRITORY = "self_territory"
    CURRENT_VIEWPORT = "current_viewport"
    EXPLICIT_COORDINATE = "explicit_coordinate"
    MAP_CORNER = "map_corner"


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
    perimeter_start_corner: WorldMapTraversalCorner = WorldMapTraversalCorner.UPPER_LEFT
    perimeter_rotation: TraversalRotation = TraversalRotation.CLOCKWISE
    inset_x: int | None = None
    inset_y: int | None = None

    def __post_init__(self) -> None:
        """Rejects pattern-local parameters that do not apply to the selected traversal family."""

        if self.kind in {
            WorldMapSearchPatternKind.ROW_MAJOR_SWEEP,
            WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP,
            WorldMapSearchPatternKind.EXPANDING_RING,
        }:
            if self.inset_x is not None or self.inset_y is not None:
                raise SelectorResolutionError(
                    "Only shrinking perimeter traversal may declare inset_x or inset_y.",
                    pattern=self.kind.value,
                    inset_x=self.inset_x,
                    inset_y=self.inset_y,
                )
        if self.kind != WorldMapSearchPatternKind.SHRINKING_PERIMETER_SWEEP:
            return
        if self.inset_x is not None and self.inset_x <= 0:
            raise SelectorResolutionError(
                "Shrinking perimeter traversal requires a positive inset_x value when present.",
                inset_x=self.inset_x,
            )
        if self.inset_y is not None and self.inset_y <= 0:
            raise SelectorResolutionError(
                "Shrinking perimeter traversal requires a positive inset_y value when present.",
                inset_y=self.inset_y,
            )

    @classmethod
    def row_major_sweep(cls) -> "WorldMapSearchPattern":
        """Returns the canonical row-major sweep pattern."""

        return cls(WorldMapSearchPatternKind.ROW_MAJOR_SWEEP)

    @classmethod
    def serpentine_row_sweep(cls) -> "WorldMapSearchPattern":
        """Returns the canonical serpentine row sweep pattern."""

        return cls(WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP)

    @classmethod
    def expanding_ring(cls) -> "WorldMapSearchPattern":
        """Returns the canonical expanding-ring pattern."""

        return cls(WorldMapSearchPatternKind.EXPANDING_RING)

    @classmethod
    def perimeter_ring_sweep(
        cls,
        *,
        start_corner: WorldMapTraversalCorner = WorldMapTraversalCorner.UPPER_LEFT,
        rotation: TraversalRotation = TraversalRotation.CLOCKWISE,
    ) -> "WorldMapSearchPattern":
        """Returns the canonical single-perimeter traversal pattern."""

        return cls(
            WorldMapSearchPatternKind.PERIMETER_RING_SWEEP,
            perimeter_start_corner=start_corner,
            perimeter_rotation=rotation,
        )

    @classmethod
    def shrinking_perimeter_sweep(
        cls,
        *,
        start_corner: WorldMapTraversalCorner = WorldMapTraversalCorner.UPPER_LEFT,
        rotation: TraversalRotation = TraversalRotation.CLOCKWISE,
        inset_x: int | None = None,
        inset_y: int | None = None,
    ) -> "WorldMapSearchPattern":
        """Returns the canonical inward-perimeter traversal pattern."""

        return cls(
            WorldMapSearchPatternKind.SHRINKING_PERIMETER_SWEEP,
            perimeter_start_corner=start_corner,
            perimeter_rotation=rotation,
            inset_x=inset_x,
            inset_y=inset_y,
        )


@dataclass(frozen=True, slots=True)
class WorldMapSearchOrigin:
    """Defines how one search request should resolve its traversal origin."""

    kind: WorldMapSearchOriginKind
    coordinate: tuple[int, int] | None = None
    corner: WorldMapMapCorner | None = None

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
            if self.corner is not None:
                raise SelectorResolutionError("Explicit-coordinate origins must not also declare corner hints.")
            return
        if self.kind == WorldMapSearchOriginKind.MAP_CORNER:
            if self.corner is None:
                raise SelectorResolutionError("Map-corner search origins require one exact map corner.")
            if self.coordinate is not None:
                raise SelectorResolutionError("Map-corner origins must not also declare coordinate values.")
            return
        if self.coordinate is not None or self.corner is not None:
            raise SelectorResolutionError(
                "Viewport- and self-derived search origins must not carry explicit coordinate or corner payloads.",
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


@dataclass(frozen=True, slots=True)
class WorldMapSearchBoundary:
    """Defines the allowed coverage region for one world-map search."""

    kind: WorldMapSearchBoundaryKind
    radius_units: int | None = None
    rectangle_bounds: WorldMapBounds | None = None
    map_bounds: WorldMapBounds | None = None

    def __post_init__(self) -> None:
        """Rejects inconsistent boundary payloads before traversal planning begins."""

        if self.kind == WorldMapSearchBoundaryKind.RADIUS_FROM_ORIGIN:
            if self.radius_units is None or self.radius_units <= 0:
                raise SelectorResolutionError(
                    "Radius-from-origin boundaries require a positive radius_units value.",
                    radius_units=self.radius_units,
                )
            if self.rectangle_bounds is not None or self.map_bounds is not None:
                raise SelectorResolutionError("Radius boundaries must not declare rectangle or map-bounds payloads.")
            return
        if self.kind == WorldMapSearchBoundaryKind.RECTANGLE:
            if self.rectangle_bounds is None:
                raise SelectorResolutionError("Rectangle search boundaries require explicit rectangular bounds.")
            if self.radius_units is not None or self.map_bounds is not None:
                raise SelectorResolutionError("Rectangle boundaries must not declare radius or full-map payloads.")
            return
        if self.kind == WorldMapSearchBoundaryKind.FULL_MAP:
            if self.map_bounds is None:
                raise SelectorResolutionError("Full-map search boundaries require resolvable world-map bounds.")
            if self.radius_units is not None or self.rectangle_bounds is not None:
                raise SelectorResolutionError("Full-map boundaries must not declare radius or rectangle payloads.")
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
    traversal_stride_policy: TraversalStridePolicy = field(default_factory=TraversalStridePolicy.viewport_default)
    coordinate_domain: WorldMapCoordinateDomain = field(
        default_factory=WorldMapCoordinateDomain.puzzles_and_conquest,
    )
    origin: WorldMapSearchOrigin | None = None
    boundary: WorldMapSearchBoundary | None = None
    movement_preferences: WorldMapMovementPreferences = field(default_factory=WorldMapMovementPreferences)
    castle_enrichment_policy: WorldMapCastleEnrichmentPolicy = field(default_factory=WorldMapCastleEnrichmentPolicy)
    sweep_policy: WorldMapSweepPolicy = field(default_factory=WorldMapSweepPolicy.debug_exact_checkpoint)

    def __post_init__(self) -> None:
        """Canonicalizes the matcher and rejects unsupported request combinations."""

        object.__setattr__(self, "matcher", adapt_world_map_search_matcher(self.matcher))
        _validate_boundary_within_coordinate_domain(self.boundary, self.coordinate_domain)
        if self.pattern.kind in {
            WorldMapSearchPatternKind.PERIMETER_RING_SWEEP,
            WorldMapSearchPatternKind.SHRINKING_PERIMETER_SWEEP,
        }:
            if self.boundary is None or self.boundary.kind not in {
                WorldMapSearchBoundaryKind.RECTANGLE,
                WorldMapSearchBoundaryKind.FULL_MAP,
            }:
                raise SelectorResolutionError(
                    "Perimeter traversal requires a rectangle or full-map boundary.",
                    pattern=self.pattern.kind.value,
                    boundary_kind=None if self.boundary is None else self.boundary.kind.value,
                )


@dataclass(frozen=True, slots=True)
class WorldMapResolvedSearchPlan:
    """Carries the fully resolved planning inputs for one world-map search request."""

    request: WorldMapSearchRequest
    origin_coordinate: tuple[int, int]
    coverage_bounds: WorldMapBounds
    stride: ResolvedTraversalStride
    movement_tool: WorldMapMovementToolKind
    execution_start_coordinate: tuple[int, int]
    first_step_movement_tool: WorldMapMovementToolKind
    route_plan: WorldMapTraversalRoutePlan
    execution_plan: WorldMapTraversalExecutionPlan
    sweep_plan: WorldMapSweepPlan
    route: tuple[WorldMapTraversalCheckpoint, ...] = field(init=False)

    def __post_init__(self) -> None:
        """Caches the flattened checkpoint route once for compatibility consumers."""

        object.__setattr__(self, "route", tuple(step.checkpoint for step in self.execution_plan.steps))


def _object_coordinate(object_: DetectedSpatialObject) -> tuple[int, int] | None:
    """Returns the strongest available world coordinate for one visible object."""

    if object_.confirmed_world_coordinate is not None:
        return object_.confirmed_world_coordinate
    return object_.estimated_world_coordinate


def _require_map_bounds(request: WorldMapSearchRequest) -> WorldMapBounds:
    """Returns the map bounds required by the request or fails fast when they are unavailable."""

    boundary = request.boundary
    if boundary is None or boundary.map_bounds is None:
        raise SelectorResolutionError(
            "This world-map search request requires resolvable map bounds.",
            boundary_kind=None if boundary is None else boundary.kind.value,
        )
    return boundary.map_bounds


def _known_world_map_bounds(request: WorldMapSearchRequest) -> WorldMapBounds | None:
    """Returns true map bounds when the request carries them, avoiding local search bounds as edge evidence."""

    if request.boundary is None:
        return request.coordinate_domain.bounds
    if request.boundary.kind == WorldMapSearchBoundaryKind.FULL_MAP:
        return request.boundary.map_bounds
    return request.coordinate_domain.bounds


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
