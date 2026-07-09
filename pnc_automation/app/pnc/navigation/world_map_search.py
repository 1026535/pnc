"""Canonical world-map search contracts and runtime orchestration."""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from pnc_automation.app.pnc.domain.action_requests import (
    ActionRequest,
    InputTextAction,
    KeyEventAction,
    SwipeGesturePrimitive,
    SwipeAction,
    TapAction,
    TapPointAction,
    resolve_swipe_points_for_action,
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
from pnc_automation.app.pnc.navigation.world_map_analysis import (
    WorldMapActualSample,
    WorldMapViewportAnalysisTelemetryRecord,
    WorldMapViewportAnalysisQueue,
    WorldMapViewportAnalysisResult,
    WorldMapViewportAnalysisTreatmentKind,
    WorldMapViewportAnalysisWorkItem,
    WorldMapViewportAnalyzer,
)
from pnc_automation.app.pnc.navigation.world_map_proof import (
    WorldMapMovementProofPolicy,
    WorldMapProofStrength,
    WorldMapViewportProof,
    require_exact_world_map_observation,
    require_exact_world_map_proof,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.pnc.navigation.world_map_sweep import (
    WorldMapCoordinateProjectionContext,
    WorldMapProjectedFrame,
    WorldMapSampledFrame,
    WorldMapSweepSegment,
    WorldMapSweepPlan,
    WorldMapSweepPolicy,
    WorldMapSweepPolicyKind,
    build_world_map_sweep_plan,
    world_map_sample_gap_exceeds_scan_footprint,
)
from pnc_automation.app.pnc.navigation.world_map_traversal import (
    ResolvedTraversalStride,
    TraversalRotation,
    TraversalSegmentIntent,
    TraversalStridePolicy,
    WorldMapEdge,
    WorldMapSearchBoundaryKind,
    WorldMapSearchPatternKind,
    WorldMapTraversalActionFamily,
    WorldMapTraversalCheckpoint,
    WorldMapTraversalCorner,
    WorldMapTraversalExecutionPlan,
    WorldMapTraversalExecutionPlanner,
    WorldMapTraversalExecutionStep,
    WorldMapTraversalPlanner,
    WorldMapTraversalRoutePlan,
    WorldMapViewportStrideProfile,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.spatial_surfaces import estimated_world_map_visible_scan_footprint_units
from pnc_automation.app.pnc.vision.world_map_coordinates import parse_world_coordinate_dialog_field_text
from pnc_automation.app.runtime.observation_artifacts import (
    ObservationArtifactRoutine,
    ObservationArtifactSelection,
    resolve_routine_artifact_selection,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.diagnostics.buffered_logging import (
    DiagnosticLogMode,
    emit_diagnostic_log,
    flush_buffered_diagnostic_logs,
)

if TYPE_CHECKING:
    from pnc_automation.app.pnc.vision.observation_builder import CapturedObservation, ObservationService


class WorldMapObservedActionExecutor(Protocol):
    """Defines the narrow action-execution contract the search layer needs without importing the automation package."""

    def execute_action(self, action: ActionRequest, observation: Observation) -> bool:
        """Executes one action without forcing an observation follow-up."""

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


class WorldMapProductionSampleProofMode(StrEnum):
    """Defines the proof contract used by production segment sampling."""

    EXACT_P1_SAMPLED_SEGMENT = "exact_p1_sampled_segment"


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


@dataclass(frozen=True, slots=True)
class WorldMapSearchCheckpointProfile:
    """Captures one analyzed checkpoint's stage timings inside the canonical search loop."""

    checkpoint_route_index: int
    checkpoint_coordinate: tuple[int, int]
    action_family: str
    movement_tool: str
    movement_phase: str
    move_elapsed_ms: float
    ingest_elapsed_ms: float
    match_elapsed_ms: float
    stop_policy_elapsed_ms: float
    enrichment_elapsed_ms: float
    p2_analysis_elapsed_ms: float
    total_elapsed_ms: float
    status: str
    failure_stage: str | None = None

    def __post_init__(self) -> None:
        """Rejects malformed checkpoint profiles so benchmark consumers can trust the schema."""

        for field_name, value in (
            ("move_elapsed_ms", self.move_elapsed_ms),
            ("ingest_elapsed_ms", self.ingest_elapsed_ms),
            ("match_elapsed_ms", self.match_elapsed_ms),
            ("stop_policy_elapsed_ms", self.stop_policy_elapsed_ms),
            ("enrichment_elapsed_ms", self.enrichment_elapsed_ms),
            ("p2_analysis_elapsed_ms", self.p2_analysis_elapsed_ms),
            ("total_elapsed_ms", self.total_elapsed_ms),
        ):
            if value < 0:
                raise SelectorResolutionError(
                    "World-map search checkpoint timing fields must stay non-negative.",
                    field_name=field_name,
                    value=value,
                )
        if self.status not in {"completed", "failed"}:
            raise SelectorResolutionError(
                "World-map search checkpoint profiles require a supported status.",
                status=self.status,
            )
        if self.movement_phase not in {"non_local_entry", "steady_state"}:
            raise SelectorResolutionError(
                "World-map search checkpoint profiles require a supported movement phase.",
                movement_phase=self.movement_phase,
            )
        if self.status == "failed" and self.failure_stage is None:
            raise SelectorResolutionError(
                "Failed world-map search checkpoint profiles must declare their failure_stage.",
                checkpoint_route_index=self.checkpoint_route_index,
            )
        if self.status == "completed" and self.failure_stage is not None:
            raise SelectorResolutionError(
                "Completed world-map search checkpoint profiles must not declare a failure_stage.",
                checkpoint_route_index=self.checkpoint_route_index,
                failure_stage=self.failure_stage,
            )

    def to_document(self) -> dict[str, object]:
        """Exports the checkpoint timing profile as one JSON-ready document."""

        return {
            "checkpoint_route_index": self.checkpoint_route_index,
            "checkpoint_coordinate": [self.checkpoint_coordinate[0], self.checkpoint_coordinate[1]],
            "action_family": self.action_family,
            "movement_tool": self.movement_tool,
            "movement_phase": self.movement_phase,
            "move_elapsed_ms": round(self.move_elapsed_ms, 2),
            "ingest_elapsed_ms": round(self.ingest_elapsed_ms, 2),
            "match_elapsed_ms": round(self.match_elapsed_ms, 2),
            "stop_policy_elapsed_ms": round(self.stop_policy_elapsed_ms, 2),
            "enrichment_elapsed_ms": round(self.enrichment_elapsed_ms, 2),
            "p2_analysis_elapsed_ms": round(self.p2_analysis_elapsed_ms, 2),
            "total_elapsed_ms": round(self.total_elapsed_ms, 2),
            "status": self.status,
            "failure_stage": self.failure_stage,
        }


@dataclass(frozen=True, slots=True)
class WorldMapSearchSegmentProfile:
    """Captures one production row/lane segment's movement, sampling, and proof timings."""

    segment_index: int
    start_coordinate: tuple[int, int]
    end_coordinate: tuple[int, int]
    checkpoint_count: int
    sampled_frame_count: int
    move_elapsed_ms: float
    start_anchor_elapsed_ms: float
    end_anchor_elapsed_ms: float
    ingest_elapsed_ms: float
    total_elapsed_ms: float
    status: str
    failure_stage: str | None = None

    def __post_init__(self) -> None:
        """Rejects malformed segment profiles before benchmark consumers trust them."""

        if self.segment_index < 0:
            raise SelectorResolutionError("World-map segment profiles require a non-negative segment_index.")
        for field_name, value in (
            ("checkpoint_count", self.checkpoint_count),
            ("sampled_frame_count", self.sampled_frame_count),
        ):
            if value < 0:
                raise SelectorResolutionError("World-map segment profile counts must be non-negative.", field_name=field_name)
        for field_name, value in (
            ("move_elapsed_ms", self.move_elapsed_ms),
            ("start_anchor_elapsed_ms", self.start_anchor_elapsed_ms),
            ("end_anchor_elapsed_ms", self.end_anchor_elapsed_ms),
            ("ingest_elapsed_ms", self.ingest_elapsed_ms),
            ("total_elapsed_ms", self.total_elapsed_ms),
        ):
            if value < 0:
                raise SelectorResolutionError("World-map segment profile timings must be non-negative.", field_name=field_name)
        if self.status not in {"completed", "failed"}:
            raise SelectorResolutionError("World-map segment profiles require a supported status.", status=self.status)
        if self.status == "failed" and self.failure_stage is None:
            raise SelectorResolutionError("Failed world-map segment profiles must declare a failure_stage.")
        if self.status == "completed" and self.failure_stage is not None:
            raise SelectorResolutionError("Completed world-map segment profiles must not declare a failure_stage.")

    def to_document(self) -> dict[str, object]:
        """Exports the production segment timing profile as one JSON-ready document."""

        return {
            "segment_index": self.segment_index,
            "start_coordinate": [self.start_coordinate[0], self.start_coordinate[1]],
            "end_coordinate": [self.end_coordinate[0], self.end_coordinate[1]],
            "checkpoint_count": self.checkpoint_count,
            "sampled_frame_count": self.sampled_frame_count,
            "move_elapsed_ms": round(self.move_elapsed_ms, 2),
            "start_anchor_elapsed_ms": round(self.start_anchor_elapsed_ms, 2),
            "end_anchor_elapsed_ms": round(self.end_anchor_elapsed_ms, 2),
            "ingest_elapsed_ms": round(self.ingest_elapsed_ms, 2),
            "total_elapsed_ms": round(self.total_elapsed_ms, 2),
            "status": self.status,
            "failure_stage": self.failure_stage,
        }


@dataclass(frozen=True, slots=True)
class WorldMapSearchExecutionProfile:
    """Summarizes canonical search-stage timings so live sweeps can be benchmarked without parallel flows."""

    movement_tool: WorldMapMovementToolKind | None
    execution_start_coordinate: tuple[int, int] | None
    first_step_movement_tool: WorldMapMovementToolKind | None
    plan_elapsed_ms: float
    persist_summary_elapsed_ms: float
    total_elapsed_ms: float
    stop_reason: WorldMapSearchStopReason | None
    checkpoint_profiles: tuple[WorldMapSearchCheckpointProfile, ...]
    segment_profiles: tuple[WorldMapSearchSegmentProfile, ...] = ()
    p2_queue_submission_count: int = 0
    p2_queue_peak_depth: int = 0
    p2_movement_overlap_count: int = 0
    p2_queue_drain_elapsed_ms: float = 0.0
    p1_fallback_capture_count: int = 0
    p1_missing_capture_count: int = 0
    p1_mismatched_capture_count: int = 0
    p2_queue_backpressure_block_count: int = 0
    p2_queue_backpressure_block_elapsed_ms: float = 0.0
    p2_queue_first_failure: WorldMapViewportAnalysisTelemetryRecord | None = None
    p2_queue_telemetry: tuple[WorldMapViewportAnalysisTelemetryRecord, ...] = ()
    production_samples: tuple[WorldMapActualSample, ...] = ()
    production_sample_proof_mode: WorldMapProductionSampleProofMode | None = None

    def __post_init__(self) -> None:
        """Rejects malformed aggregate search timings before callers consume them."""

        for field_name, value in (
            ("plan_elapsed_ms", self.plan_elapsed_ms),
            ("persist_summary_elapsed_ms", self.persist_summary_elapsed_ms),
            ("total_elapsed_ms", self.total_elapsed_ms),
            ("p2_queue_drain_elapsed_ms", self.p2_queue_drain_elapsed_ms),
            ("p2_queue_backpressure_block_elapsed_ms", self.p2_queue_backpressure_block_elapsed_ms),
        ):
            if value < 0:
                raise SelectorResolutionError(
                    "World-map search execution timing fields must stay non-negative.",
                    field_name=field_name,
                    value=value,
                )
        for field_name, value in (
            ("p2_queue_submission_count", self.p2_queue_submission_count),
            ("p2_queue_peak_depth", self.p2_queue_peak_depth),
            ("p2_movement_overlap_count", self.p2_movement_overlap_count),
            ("p1_fallback_capture_count", self.p1_fallback_capture_count),
            ("p1_missing_capture_count", self.p1_missing_capture_count),
            ("p1_mismatched_capture_count", self.p1_mismatched_capture_count),
            ("p2_queue_backpressure_block_count", self.p2_queue_backpressure_block_count),
        ):
            if value < 0:
                raise SelectorResolutionError(
                    "World-map search execution count fields must stay non-negative.",
                    field_name=field_name,
                    value=value,
                )
        if self.p2_queue_first_failure is not None and not self.p2_queue_first_failure.failed:
            raise SelectorResolutionError("World-map P2 first-failure telemetry must describe a failed item.")

    def to_document(self) -> dict[str, object]:
        """Exports the aggregate benchmark profile as one JSON-ready document."""

        return {
            "movement_tool": None if self.movement_tool is None else self.movement_tool.value,
            "execution_start_coordinate": (
                None
                if self.execution_start_coordinate is None
                else [self.execution_start_coordinate[0], self.execution_start_coordinate[1]]
            ),
            "first_step_movement_tool": (
                None if self.first_step_movement_tool is None else self.first_step_movement_tool.value
            ),
            "plan_elapsed_ms": round(self.plan_elapsed_ms, 2),
            "persist_summary_elapsed_ms": round(self.persist_summary_elapsed_ms, 2),
            "total_elapsed_ms": round(self.total_elapsed_ms, 2),
            "stop_reason": None if self.stop_reason is None else self.stop_reason.value,
            "p2_pipeline": {
                "submission_count": self.p2_queue_submission_count,
                "peak_depth": self.p2_queue_peak_depth,
                "movement_overlap_count": self.p2_movement_overlap_count,
                "drain_elapsed_ms": round(self.p2_queue_drain_elapsed_ms, 2),
                "p1_fallback_capture_count": self.p1_fallback_capture_count,
                "p1_missing_capture_count": self.p1_missing_capture_count,
                "p1_mismatched_capture_count": self.p1_mismatched_capture_count,
                "backpressure_block_count": self.p2_queue_backpressure_block_count,
                "backpressure_block_elapsed_ms": round(self.p2_queue_backpressure_block_elapsed_ms, 2),
                "first_failure": (
                    None if self.p2_queue_first_failure is None else self.p2_queue_first_failure.to_document()
                ),
                "telemetry": [record.to_document() for record in self.p2_queue_telemetry],
            },
            "production_sample_proof_mode": (
                None if self.production_sample_proof_mode is None else self.production_sample_proof_mode.value
            ),
            "production_samples": [sample.to_document() for sample in self.production_samples],
            "stage_totals": {
                "move_elapsed_ms": round(sum(profile.move_elapsed_ms for profile in self.checkpoint_profiles), 2),
                "segment_move_elapsed_ms": round(sum(profile.move_elapsed_ms for profile in self.segment_profiles), 2),
                "segment_anchor_elapsed_ms": round(
                    sum(
                        profile.start_anchor_elapsed_ms + profile.end_anchor_elapsed_ms
                        for profile in self.segment_profiles
                    ),
                    2,
                ),
                "ingest_elapsed_ms": round(sum(profile.ingest_elapsed_ms for profile in self.checkpoint_profiles), 2),
                "segment_ingest_elapsed_ms": round(sum(profile.ingest_elapsed_ms for profile in self.segment_profiles), 2),
                "match_elapsed_ms": round(sum(profile.match_elapsed_ms for profile in self.checkpoint_profiles), 2),
                "stop_policy_elapsed_ms": round(
                    sum(profile.stop_policy_elapsed_ms for profile in self.checkpoint_profiles), 2
                ),
                "enrichment_elapsed_ms": round(
                    sum(profile.enrichment_elapsed_ms for profile in self.checkpoint_profiles), 2
                ),
                "p2_analysis_elapsed_ms": round(
                    sum(profile.p2_analysis_elapsed_ms for profile in self.checkpoint_profiles), 2
                ),
                "non_local_entry_move_elapsed_ms": round(
                    sum(
                        profile.move_elapsed_ms
                        for profile in self.checkpoint_profiles
                        if profile.movement_phase == "non_local_entry"
                    ),
                    2,
                ),
                "steady_state_move_elapsed_ms": round(
                    sum(
                        profile.move_elapsed_ms
                        for profile in self.checkpoint_profiles
                        if profile.movement_phase == "steady_state"
                    ),
                    2,
                ),
            },
            "checkpoint_profiles": [profile.to_document() for profile in self.checkpoint_profiles],
            "segment_profiles": [profile.to_document() for profile in self.segment_profiles],
        }


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
    execution_profile: WorldMapSearchExecutionProfile | None = None


class WorldMapMovementMode(StrEnum):
    """Defines the active direct-movement behavior used for one coordinate-movement leg."""

    TRAVERSE = "traverse"
    FINE_CORRECTION = "fine_correction"


@dataclass(frozen=True, slots=True)
class WorldMapMovementPolicy:
    """Defines the canonical gesture and traverse-vs-correction policy for direct world-map movement."""

    gesture_primitive: SwipeGesturePrimitive = SwipeGesturePrimitive.SWIPE
    arrival_tolerance_units: int = 2
    overshoot_tolerance_units: int = 4
    correction_threshold_units: int = 10
    traverse_max_axis_delta_per_leg: int | None = None
    correction_max_axis_delta_per_leg: int | None = None

    def __post_init__(self) -> None:
        """Rejects malformed movement-policy combinations before runtime execution begins."""

        if self.arrival_tolerance_units <= 0:
            raise SelectorResolutionError(
                "World-map movement policies require a positive arrival_tolerance_units value.",
                arrival_tolerance_units=self.arrival_tolerance_units,
            )
        if self.overshoot_tolerance_units < self.arrival_tolerance_units:
            raise SelectorResolutionError(
                "World-map movement policies require overshoot_tolerance_units to cover arrival_tolerance_units.",
                arrival_tolerance_units=self.arrival_tolerance_units,
                overshoot_tolerance_units=self.overshoot_tolerance_units,
            )
        if self.correction_threshold_units <= 0:
            raise SelectorResolutionError(
                "World-map movement policies require a positive correction_threshold_units value.",
                correction_threshold_units=self.correction_threshold_units,
            )
        for field_name, value in (
            ("traverse_max_axis_delta_per_leg", self.traverse_max_axis_delta_per_leg),
            ("correction_max_axis_delta_per_leg", self.correction_max_axis_delta_per_leg),
        ):
            if value is not None and value <= 0:
                raise SelectorResolutionError(
                    "World-map movement policy leg caps must be positive when configured.",
                    field_name=field_name,
                    value=value,
                )

    @property
    def maximum_accepted_landing_delta_units(self) -> int:
        """Returns the largest landing delta accepted after canonical movement validation."""

        return self.overshoot_tolerance_units

    def mode_for_remaining_delta(
        self,
        *,
        current_coordinate: tuple[int, int],
        target_coordinate: tuple[int, int],
        action_family: WorldMapTraversalActionFamily,
    ) -> WorldMapMovementMode:
        """Returns whether the next leg should use broad traversal or near-target correction behavior."""

        remaining_x = abs(target_coordinate[0] - current_coordinate[0])
        remaining_y = abs(target_coordinate[1] - current_coordinate[1])
        if action_family == WorldMapTraversalActionFamily.NON_LOCAL_DIRECT:
            return WorldMapMovementMode.TRAVERSE
        if max(remaining_x, remaining_y) >= self.correction_threshold_units:
            return WorldMapMovementMode.TRAVERSE
        return WorldMapMovementMode.FINE_CORRECTION

    def max_axis_delta_for_mode(self, mode: WorldMapMovementMode) -> int | None:
        """Returns the active per-leg granularity cap for the selected movement mode."""

        if mode == WorldMapMovementMode.TRAVERSE:
            return self.traverse_max_axis_delta_per_leg
        return self.correction_max_axis_delta_per_leg


@dataclass(frozen=True, slots=True)
class WorldMapMovementStepTrace:
    """Captures one observed direct-movement leg plus its timing and coordinate proof details."""

    step_index: int
    before_coordinate: tuple[int, int]
    leg_target: tuple[int, int]
    after_coordinate: tuple[int, int]
    requested_coordinate: tuple[int, int]
    normalized_target_coordinate: tuple[int, int]
    action_family: str
    movement_mode: str
    max_axis_delta_per_leg: int | None
    gesture_primitive: str
    plan_elapsed_ms: float
    action_elapsed_ms: float
    action_follow_up_observe_elapsed_ms: float
    action_executor_overhead_elapsed_ms: float
    action_follow_up_observation_count: int
    prove_elapsed_ms: float
    total_elapsed_ms: float
    classification: str
    before_artifact_path: str | None
    after_artifact_path: str | None

    def to_document(self) -> dict[str, object]:
        """Exports the movement leg as a JSON-ready trace document."""

        return {
            "step_index": self.step_index,
            "before_coordinate": [self.before_coordinate[0], self.before_coordinate[1]],
            "leg_target": [self.leg_target[0], self.leg_target[1]],
            "after_coordinate": [self.after_coordinate[0], self.after_coordinate[1]],
            "requested_coordinate": [self.requested_coordinate[0], self.requested_coordinate[1]],
            "normalized_target_coordinate": [
                self.normalized_target_coordinate[0],
                self.normalized_target_coordinate[1],
            ],
            "action_family": self.action_family,
            "movement_mode": self.movement_mode,
            "max_axis_delta_per_leg": self.max_axis_delta_per_leg,
            "gesture_primitive": self.gesture_primitive,
            "plan_elapsed_ms": round(self.plan_elapsed_ms, 2),
            "action_elapsed_ms": round(self.action_elapsed_ms, 2),
            "action_follow_up_observe_elapsed_ms": round(self.action_follow_up_observe_elapsed_ms, 2),
            "action_executor_overhead_elapsed_ms": round(self.action_executor_overhead_elapsed_ms, 2),
            "action_follow_up_observation_count": self.action_follow_up_observation_count,
            "prove_elapsed_ms": round(self.prove_elapsed_ms, 2),
            "total_elapsed_ms": round(self.total_elapsed_ms, 2),
            "classification": self.classification,
            "before_artifact_path": self.before_artifact_path,
            "after_artifact_path": self.after_artifact_path,
        }


@dataclass(frozen=True, slots=True)
class WorldMapMovementActionTiming:
    """Carries the movement-action result plus the benchmark split measured at the live observation seam."""

    observation: Observation
    total_elapsed_ms: float
    follow_up_observe_elapsed_ms: float
    follow_up_observation_count: int

    @property
    def executor_overhead_elapsed_ms(self) -> float:
        """Returns action execution time outside the observation callback."""

        return max(0.0, self.total_elapsed_ms - self.follow_up_observe_elapsed_ms)


@dataclass(slots=True)
class WorldMapCoordinateMover:
    """Moves an already-open world-map viewport to one target coordinate using the canonical cardinal-only swipe model."""

    observation_service: "ObservationService | None"
    action_executor: WorldMapObservedActionExecutor | None
    navigator: WorldMapNavigator
    coordinate_domain: WorldMapCoordinateDomain = field(default_factory=WorldMapCoordinateDomain.puzzles_and_conquest)
    movement_policy: WorldMapMovementPolicy = field(default_factory=WorldMapMovementPolicy)
    movement_step_budget: int = 8
    orthogonal_drift_tolerance: int = 1
    logger: logging.LoggerAdapter | None = None

    def __post_init__(self) -> None:
        """Rejects invalid movement policy combinations before runtime execution begins."""

        _require_valid_world_map_step_budget(
            self.movement_step_budget,
            field_name="movement_step_budget",
        )
        if self.movement_policy.correction_threshold_units <= self.navigator.focus_tolerance:
            raise SelectorResolutionError(
                "World-map movement correction_threshold_units must be greater than the navigator focus_tolerance.",
                correction_threshold_units=self.movement_policy.correction_threshold_units,
                focus_tolerance=self.navigator.focus_tolerance,
            )
        for field_name, value in (
            ("traverse_max_axis_delta_per_leg", self.movement_policy.traverse_max_axis_delta_per_leg),
            ("correction_max_axis_delta_per_leg", self.movement_policy.correction_max_axis_delta_per_leg),
        ):
            if value is not None and value <= self.navigator.focus_tolerance:
                raise SelectorResolutionError(
                    "World-map movement granularity must be greater than the navigator focus_tolerance, otherwise capped legs are treated as already in tolerance and no swipe can be planned.",
                    field_name=field_name,
                    value=value,
                    focus_tolerance=self.navigator.focus_tolerance,
                )

    @property
    def max_axis_delta_per_leg(self) -> int | None:
        """Returns the broad-traverse leg cap for compatibility call sites and diagnostics."""

        return self.movement_policy.traverse_max_axis_delta_per_leg

    @max_axis_delta_per_leg.setter
    def max_axis_delta_per_leg(self, value: int | None) -> None:
        """Updates the broad-traverse leg cap while preserving the rest of the movement policy."""

        if value is not None and value <= self.navigator.focus_tolerance:
            raise SelectorResolutionError(
                "World-map movement granularity must be greater than the navigator focus_tolerance, otherwise capped legs are treated as already in tolerance and no swipe can be planned.",
                traverse_max_axis_delta_per_leg=value,
                focus_tolerance=self.navigator.focus_tolerance,
            )
        self.movement_policy = WorldMapMovementPolicy(
            gesture_primitive=self.movement_policy.gesture_primitive,
            arrival_tolerance_units=self.movement_policy.arrival_tolerance_units,
            overshoot_tolerance_units=self.movement_policy.overshoot_tolerance_units,
            correction_threshold_units=self.movement_policy.correction_threshold_units,
            traverse_max_axis_delta_per_leg=value,
            correction_max_axis_delta_per_leg=self.movement_policy.correction_max_axis_delta_per_leg,
        )

    def move_to_coordinate(
        self,
        observation: Observation,
        *,
        target_coordinate: tuple[int, int],
        label_prefix: str,
        runtime_state: dict[str, Any] | None = None,
        boundary_bounds: WorldMapBounds | None = None,
        coordinate_domain: WorldMapCoordinateDomain | None = None,
        movement_family: WorldMapTraversalActionFamily = WorldMapTraversalActionFamily.LOCAL_DIRECT,
        arrival_observation_request: ObservationRequest | None = None,
        movement_proof_artifact_selection: ObservationArtifactSelection | None = None,
        arrival_artifact_selection: ObservationArtifactSelection | None = None,
        logging_mode: DiagnosticLogMode = DiagnosticLogMode.IMMEDIATE,
        p1_capture_sink: Callable[["CapturedObservation"], None] | None = None,
    ) -> Observation:
        """Moves toward the requested coordinate using bounded cardinal legs and returns the freshest proven world-map observation."""

        active_coordinate_domain = self.coordinate_domain if coordinate_domain is None else coordinate_domain
        addressable_target_coordinate = active_coordinate_domain.nearest_addressable_in_bounds(target_coordinate)
        current = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=observation,
            label_prefix=f"{label_prefix}_start",
            p1_capture_sink=p1_capture_sink,
            artifact_selection=movement_proof_artifact_selection,
        )
        if _coordinate_within_tolerance(
            _require_world_map_viewport_coordinate(current),
            addressable_target_coordinate,
            tolerance=self.movement_policy.arrival_tolerance_units,
        ):
            return current
        movement_state = _mutable_runtime_state(runtime_state, "world_map_search_swipe_navigation")
        for step_index in range(self.movement_step_budget):
            step_started_at = time.perf_counter()
            preferred_axis = _consume_preferred_cardinal_axis(movement_state)
            plan_started_at = time.perf_counter()
            leg_target = _resolve_cardinal_sweep_leg_target(
                current=current,
                target_coordinate=addressable_target_coordinate,
                focus_tolerance=self.navigator.focus_tolerance,
                preferred_axis=preferred_axis,
                max_axis_delta_per_leg=self._active_max_axis_delta(
                    current=current,
                    target_coordinate=addressable_target_coordinate,
                    movement_family=movement_family,
                ),
            )
            plan_elapsed_ms = (time.perf_counter() - plan_started_at) * 1000.0
            if leg_target is None:
                return current
            before_coordinate = _require_world_map_viewport_coordinate(current)
            movement_mode = self.movement_policy.mode_for_remaining_delta(
                current_coordinate=before_coordinate,
                target_coordinate=addressable_target_coordinate,
                action_family=movement_family,
            )
            active_max_axis_delta_per_leg = self.movement_policy.max_axis_delta_for_mode(movement_mode)
            freshest_observation = current
            try:
                try:
                    actions = self.navigator.plan_focus_coordinate(
                        current,
                        leg_target,
                        runtime_state=movement_state,
                    )
                except SelectorResolutionError as error:
                    exhausted = _build_stagnant_retry_exhausted_error(
                        error=error,
                        movement_state=movement_state,
                        target_coordinate=addressable_target_coordinate,
                        requested_coordinate=target_coordinate,
                    )
                    if exhausted is not None:
                        raise exhausted from error
                    raise
                if not actions:
                    current_coordinate = _require_world_map_viewport_coordinate(current)
                    if _coordinate_within_tolerance(
                        current_coordinate,
                        addressable_target_coordinate,
                        tolerance=self.movement_policy.arrival_tolerance_units,
                    ):
                        continue
                    raise SelectorResolutionError(
                        "World-map movement could not derive a cardinal swipe while the requested coordinate remained unresolved.",
                        target_coordinate=addressable_target_coordinate,
                        requested_coordinate=target_coordinate,
                        current_coordinate=current_coordinate,
                        leg_target=(leg_target.x, leg_target.y),
                    )
                actions = self._prepare_step_actions(
                    actions=actions,
                    leg_target=(leg_target.x, leg_target.y),
                    target_coordinate=addressable_target_coordinate,
                    arrival_observation_request=arrival_observation_request,
                )
                action_timing = self._execute_actions(
                    actions,
                    current,
                    label_prefix=f"{label_prefix}_{step_index}",
                    artifact_selection=(
                        arrival_artifact_selection
                        if arrival_observation_request is not None and (leg_target.x, leg_target.y) == addressable_target_coordinate
                        else movement_proof_artifact_selection
                    ),
                    p1_capture_sink=p1_capture_sink,
                )
                freshest_observation = intermediate_after = action_timing.observation
                action_elapsed_ms = action_timing.total_elapsed_ms
                action_follow_up_observe_elapsed_ms = action_timing.follow_up_observe_elapsed_ms
                action_executor_overhead_elapsed_ms = action_timing.executor_overhead_elapsed_ms
                prove_started_at = time.perf_counter()
                freshest_observation = after = _require_proven_world_map_observation(
                    observation_service=self.observation_service,
                    observation=intermediate_after,
                    label_prefix=f"{label_prefix}_refresh_{step_index}",
                    p1_capture_sink=p1_capture_sink,
                    artifact_selection=movement_proof_artifact_selection,
                )
                prove_elapsed_ms = (time.perf_counter() - prove_started_at) * 1000.0
                after_coordinate = _require_world_map_viewport_coordinate(after)
                direction = _direction_for_cardinal_leg(from_coordinate=before_coordinate, leg_target=leg_target)
                delta = after_coordinate[0] - before_coordinate[0], after_coordinate[1] - before_coordinate[1]
                attempt_details = _build_cardinal_move_attempt_details(
                    action=actions[0],
                    before_observation=current,
                    after_observation=after,
                    before_coordinate=before_coordinate,
                    after_coordinate=after_coordinate,
                    target_coordinate=addressable_target_coordinate,
                    requested_coordinate=target_coordinate,
                    leg_target=(leg_target.x, leg_target.y),
                    delta=delta,
                    direction=direction.value,
                )
                classification = classify_world_map_cardinal_delta(
                    direction=direction,
                    before_coordinate=before_coordinate,
                    delta=delta,
                    boundary_bounds=boundary_bounds,
                    orthogonal_drift_tolerance=self.orthogonal_drift_tolerance,
                )
                self._log_step_timing(
                    step_index=step_index,
                    before_coordinate=before_coordinate,
                    leg_target=(leg_target.x, leg_target.y),
                    after_coordinate=after_coordinate,
                    requested_coordinate=target_coordinate,
                    normalized_target_coordinate=addressable_target_coordinate,
                    action_family=movement_family,
                    movement_mode=movement_mode,
                    max_axis_delta_per_leg=active_max_axis_delta_per_leg,
                    plan_elapsed_ms=plan_elapsed_ms,
                    action_elapsed_ms=action_elapsed_ms,
                    action_follow_up_observe_elapsed_ms=action_follow_up_observe_elapsed_ms,
                    action_executor_overhead_elapsed_ms=action_executor_overhead_elapsed_ms,
                    action_follow_up_observation_count=action_timing.follow_up_observation_count,
                    prove_elapsed_ms=prove_elapsed_ms,
                    total_elapsed_ms=(time.perf_counter() - step_started_at) * 1000.0,
                    classification=classification,
                    runtime_state=runtime_state,
                    logging_mode=logging_mode,
                )
                _record_movement_step_trace(
                    movement_state=movement_state,
                    trace=WorldMapMovementStepTrace(
                        step_index=step_index,
                        before_coordinate=before_coordinate,
                        leg_target=(leg_target.x, leg_target.y),
                        after_coordinate=after_coordinate,
                        requested_coordinate=target_coordinate,
                        normalized_target_coordinate=addressable_target_coordinate,
                        action_family=movement_family.value,
                        movement_mode=movement_mode.value,
                        max_axis_delta_per_leg=active_max_axis_delta_per_leg,
                        gesture_primitive=(
                            actions[0].gesture_primitive.value if isinstance(actions[0], SwipeAction) else "unknown"
                        ),
                        plan_elapsed_ms=plan_elapsed_ms,
                        action_elapsed_ms=action_elapsed_ms,
                        action_follow_up_observe_elapsed_ms=action_follow_up_observe_elapsed_ms,
                        action_executor_overhead_elapsed_ms=action_executor_overhead_elapsed_ms,
                        action_follow_up_observation_count=action_timing.follow_up_observation_count,
                        prove_elapsed_ms=prove_elapsed_ms,
                        total_elapsed_ms=(time.perf_counter() - step_started_at) * 1000.0,
                        classification=classification.value,
                        before_artifact_path=None if current.artifact_path is None else str(current.artifact_path),
                        after_artifact_path=None if after.artifact_path is None else str(after.artifact_path),
                    ),
                )
                _remember_last_cardinal_move_attempt(
                    movement_state=movement_state,
                    attempt_details=attempt_details,
                    classification=classification,
                )
                if _coordinate_within_tolerance(
                    after_coordinate,
                    addressable_target_coordinate,
                    tolerance=self.movement_policy.arrival_tolerance_units,
                ) or _coordinate_overshot_within_tolerance(
                    before_coordinate=before_coordinate,
                    after_coordinate=after_coordinate,
                    target_coordinate=addressable_target_coordinate,
                    tolerance=self.movement_policy.overshoot_tolerance_units,
                ):
                    return after
                if classification in {
                    WorldMapCardinalMovementClassification.PARSER_UNCERTAIN,
                    WorldMapCardinalMovementClassification.UNEXPECTED_DELTA,
                    WorldMapCardinalMovementClassification.EXPECTED_BOUNDARY_STOP,
                }:
                    raise SelectorResolutionError(
                        "World-map movement produced an unusable cardinal swipe delta.",
                        **attempt_details,
                        classification=classification.value,
                    )
                if classification == WorldMapCardinalMovementClassification.INTERIOR_STALL:
                    current = after
                    continue
                if classification == WorldMapCardinalMovementClassification.MOVED_WITH_DRIFT:
                    _remember_orthogonal_drift_correction(
                        movement_state=movement_state,
                        direction=direction,
                        current_coordinate=after_coordinate,
                        target_coordinate=addressable_target_coordinate,
                        focus_tolerance=self.navigator.focus_tolerance,
                    )
                current = after
            except Exception as error:
                self._record_failed_step_diagnostics(
                    error=error,
                    step_index=step_index,
                    current_observation=freshest_observation,
                    before_coordinate=before_coordinate,
                    leg_target=(leg_target.x, leg_target.y),
                    requested_coordinate=target_coordinate,
                    normalized_target_coordinate=addressable_target_coordinate,
                    action_family=movement_family,
                    movement_mode=movement_mode,
                    max_axis_delta_per_leg=active_max_axis_delta_per_leg,
                    runtime_state=runtime_state,
                    logging_mode=logging_mode,
                    label_prefix=label_prefix,
                )
                raise
        raise SelectorResolutionError(
            "World-map movement exhausted its bounded coordinate-focus budget.",
            target_coordinate=addressable_target_coordinate,
            requested_coordinate=target_coordinate,
        )

    def _record_failed_step_diagnostics(
        self,
        *,
        error: Exception,
        step_index: int,
        current_observation: Observation,
        before_coordinate: tuple[int, int],
        leg_target: tuple[int, int],
        requested_coordinate: tuple[int, int],
        normalized_target_coordinate: tuple[int, int],
        action_family: WorldMapTraversalActionFamily,
        movement_mode: WorldMapMovementMode,
        max_axis_delta_per_leg: int | None,
        runtime_state: dict[str, Any] | None,
        logging_mode: DiagnosticLogMode,
        label_prefix: str,
    ) -> None:
        """Persists one failure screenshot and emits one explicit movement-leg failure diagnostic."""

        self.persist_failure_observation(
            observation=current_observation,
            label=f"{label_prefix}_failure_{step_index}",
            error=error,
        )
        self._log_step_failure(
            error=error,
            step_index=step_index,
            before_coordinate=before_coordinate,
            leg_target=leg_target,
            requested_coordinate=requested_coordinate,
            normalized_target_coordinate=normalized_target_coordinate,
            action_family=action_family,
            movement_mode=movement_mode,
            max_axis_delta_per_leg=max_axis_delta_per_leg,
            runtime_state=runtime_state,
            logging_mode=logging_mode,
        )

    def persist_failure_observation(
        self,
        *,
        observation: Observation,
        label: str,
        error: Exception,
    ) -> None:
        """Captures one failure screenshot so the latest failed movement frame is retained."""

        artifact_selection = self._failure_artifact_selection()
        if self.observation_service is None or not artifact_selection:
            return
        try:
            self.observation_service.capture_observation(
                label,
                request=ObservationRequest.full_runtime_default(),
                artifact_selection=artifact_selection,
            )
        except Exception as persist_error:
            error.add_note(f"Failure observation persistence also failed: {persist_error!r}")

    def _failure_artifact_selection(self) -> ObservationArtifactSelection | None:
        """Returns the canonical artifact selection used for failed movement diagnostics."""

        if self.observation_service is None:
            return None
        return resolve_routine_artifact_selection(
            mode=self.observation_service.mode,
            routine=ObservationArtifactRoutine.FAILURE,
        )

    def _log_step_failure(
        self,
        *,
        error: Exception,
        step_index: int,
        before_coordinate: tuple[int, int],
        leg_target: tuple[int, int],
        requested_coordinate: tuple[int, int],
        normalized_target_coordinate: tuple[int, int],
        action_family: WorldMapTraversalActionFamily,
        movement_mode: WorldMapMovementMode,
        max_axis_delta_per_leg: int | None,
        runtime_state: dict[str, Any] | None,
        logging_mode: DiagnosticLogMode,
    ) -> None:
        """Emits one explicit failed-leg diagnostic event before the error is re-raised."""

        error_details = error.details if isinstance(error, SelectorResolutionError) else None
        emit_diagnostic_log(
            logger=self.logger,
            runtime_state=runtime_state,
            mode=logging_mode,
            level=logging.ERROR,
            message="World-map movement step failed.",
            extra={
                "step_index": step_index,
                "before_coordinate": before_coordinate,
                "leg_target": leg_target,
                "requested_coordinate": requested_coordinate,
                "normalized_target_coordinate": normalized_target_coordinate,
                "action_family": action_family.value,
                "movement_mode": movement_mode.value,
                "max_axis_delta_per_leg": max_axis_delta_per_leg,
                "gesture_primitive": self.movement_policy.gesture_primitive.value,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "error_details": error_details,
            },
        )

    def _log_step_timing(
        self,
        *,
        step_index: int,
        before_coordinate: tuple[int, int],
        leg_target: tuple[int, int],
        after_coordinate: tuple[int, int],
        requested_coordinate: tuple[int, int],
        normalized_target_coordinate: tuple[int, int],
        action_family: WorldMapTraversalActionFamily,
        movement_mode: WorldMapMovementMode,
        max_axis_delta_per_leg: int | None,
        plan_elapsed_ms: float,
        action_elapsed_ms: float,
        action_follow_up_observe_elapsed_ms: float,
        action_executor_overhead_elapsed_ms: float,
        action_follow_up_observation_count: int,
        prove_elapsed_ms: float,
        total_elapsed_ms: float,
        classification: "WorldMapCardinalMovementClassification",
        runtime_state: dict[str, Any] | None,
        logging_mode: DiagnosticLogMode,
    ) -> None:
        """Logs one timing breakdown for the completed movement leg when a runtime logger is available."""

        emit_diagnostic_log(
            logger=self.logger,
            runtime_state=runtime_state,
            mode=logging_mode,
            level=logging.INFO,
            message="World-map movement step completed.",
            extra={
                "step_index": step_index,
                "before_coordinate": before_coordinate,
                "leg_target": leg_target,
                "after_coordinate": after_coordinate,
                "requested_coordinate": requested_coordinate,
                "normalized_target_coordinate": normalized_target_coordinate,
                "action_family": action_family.value,
                "movement_mode": movement_mode.value,
                "max_axis_delta_per_leg": max_axis_delta_per_leg,
                "gesture_primitive": self.movement_policy.gesture_primitive.value,
                "plan_elapsed_ms": round(plan_elapsed_ms, 2),
                "action_elapsed_ms": round(action_elapsed_ms, 2),
                "action_follow_up_observe_elapsed_ms": round(action_follow_up_observe_elapsed_ms, 2),
                "action_executor_overhead_elapsed_ms": round(action_executor_overhead_elapsed_ms, 2),
                "action_follow_up_observation_count": action_follow_up_observation_count,
                "prove_elapsed_ms": round(prove_elapsed_ms, 2),
                "total_elapsed_ms": round(total_elapsed_ms, 2),
                "classification": classification.value,
            },
        )

    def _execute_actions(
        self,
        actions: Sequence[ActionRequest],
        observation: Observation,
        *,
        label_prefix: str,
        artifact_selection: ObservationArtifactSelection | None = None,
        p1_capture_sink: Callable[["CapturedObservation"], None] | None = None,
    ) -> WorldMapMovementActionTiming:
        """Executes one movement increment and returns its freshest observation plus benchmark timing."""

        if self.action_executor is None or self.observation_service is None:
            raise SelectorResolutionError("World-map coordinate movement requires observation_service and action_executor.")

        follow_up_observe_elapsed_ms = 0.0
        follow_up_observation_count = 0

        def observe_follow_up(label: str, request: ObservationRequest | None = None) -> Observation:
            """Captures and times one P1 follow-up while preserving its screenshot for P2."""

            nonlocal follow_up_observe_elapsed_ms, follow_up_observation_count
            follow_up_observation_count += 1
            started_at = time.perf_counter()
            try:
                capture = self.observation_service.capture_observation(
                    f"{label_prefix}_{label}",
                    request=request,
                    artifact_selection=artifact_selection,
                )
                if p1_capture_sink is not None:
                    p1_capture_sink(capture)
                return capture.observation
            finally:
                follow_up_observe_elapsed_ms += (time.perf_counter() - started_at) * 1000.0

        started_at = time.perf_counter()
        execution = self.action_executor.execute_actions(
            actions,
            observation,
            observe=observe_follow_up,
        )
        return WorldMapMovementActionTiming(
            observation=execution.observation,
            total_elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            follow_up_observe_elapsed_ms=follow_up_observe_elapsed_ms,
            follow_up_observation_count=follow_up_observation_count,
        )

    def _active_max_axis_delta(
        self,
        *,
        current: Observation,
        target_coordinate: tuple[int, int],
        movement_family: WorldMapTraversalActionFamily,
    ) -> int | None:
        """Returns the active per-leg movement cap implied by the current delta and movement policy."""

        current_coordinate = _require_world_map_viewport_coordinate(current)
        movement_mode = self.movement_policy.mode_for_remaining_delta(
            current_coordinate=current_coordinate,
            target_coordinate=target_coordinate,
            action_family=movement_family,
        )
        return self.movement_policy.max_axis_delta_for_mode(movement_mode)

    def _prepare_step_actions(
        self,
        *,
        actions: Sequence[ActionRequest],
        leg_target: tuple[int, int],
        target_coordinate: tuple[int, int],
        arrival_observation_request: ObservationRequest | None,
    ) -> Sequence[ActionRequest]:
        """Applies the reviewed gesture primitive and final-arrival observation mode to one planned movement leg."""

        prepared_actions = [
            replace(action, gesture_primitive=self.movement_policy.gesture_primitive)
            if isinstance(action, SwipeAction)
            else action
            for action in actions
        ]
        if arrival_observation_request is None or leg_target != target_coordinate or not prepared_actions:
            return tuple(prepared_actions)
        last_action = prepared_actions[-1]
        if not isinstance(last_action, SwipeAction):
            return tuple(prepared_actions)
        prepared_actions[-1] = replace(last_action, follow_up_request=arrival_observation_request)
        return tuple(prepared_actions)


def world_map_movement_trace_document(runtime_state: dict[str, Any] | None) -> dict[str, object]:
    """Exports any recorded direct-movement traces from runtime state as one JSON-ready document."""

    if runtime_state is None:
        return {"step_traces": []}
    movement_state = _mutable_runtime_state(runtime_state, "world_map_search_swipe_navigation")
    return {
        "step_traces": [
            trace.to_document()
            for trace in _movement_step_traces(movement_state)
        ]
    }


def world_map_search_execution_profile_document(runtime_state: dict[str, Any] | None) -> dict[str, object]:
    """Exports the canonical search execution benchmark profile from runtime state as one JSON-ready document."""

    if runtime_state is None:
        return _build_search_execution_profile_from_state({}).to_document()
    return _build_search_execution_profile_from_state(
        _mutable_runtime_state(runtime_state, "world_map_search_execution_profile")
    ).to_document()


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

    def __post_init__(self) -> None:
        """Rejects invalid movement budget values before inspection begins."""

        _require_valid_world_map_step_budget(
            self.movement_step_budget,
            field_name="movement_step_budget",
        )

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
    traversal_execution_planner: WorldMapTraversalExecutionPlanner = field(default_factory=WorldMapTraversalExecutionPlanner)
    coordinate_navigator: WorldMapCoordinateNavigator = field(default_factory=WorldMapCoordinateNavigator)
    overview_navigator: WorldMapOverviewNavigator = field(default_factory=WorldMapOverviewNavigator)
    observation_service: "ObservationService | None" = None
    action_executor: WorldMapObservedActionExecutor | None = None
    survey_recorder: WorldMapSurveyRecorder | None = None
    castle_inspector: WorldMapCastleInspector | None = None
    coordinate_mover: WorldMapCoordinateMover | None = None
    viewport_analyzer: WorldMapViewportAnalyzer = field(default_factory=WorldMapViewportAnalyzer)
    world_map_entry_step_budget: int = 6
    movement_step_budget: int = 8

    def __post_init__(self) -> None:
        """Rejects invalid step-budget wiring before the shared runtime service is used."""

        _require_valid_world_map_step_budget(
            self.movement_step_budget,
            field_name="movement_step_budget",
        )

    def resolve_plan(self, request: WorldMapSearchRequest, observation: Observation) -> WorldMapResolvedSearchPlan:
        """Resolves one request against the current world-map surface into a deterministic traversal plan."""

        surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        origin = self._resolve_origin_coordinate(request=request, surface=surface)
        coverage_bounds = self._resolve_coverage_bounds(request=request, origin_coordinate=origin)
        movement_tool = self._select_movement_tool(request=request)
        route_plan = self.traversal_planner.build_route_plan(
            pattern_kind=request.pattern.kind,
            coordinate_domain=request.coordinate_domain,
            origin_coordinate=origin,
            coverage_bounds=coverage_bounds,
            stride_policy=request.traversal_stride_policy,
            perimeter_start_corner=request.pattern.perimeter_start_corner,
            perimeter_rotation=request.pattern.perimeter_rotation,
            inset_x=request.pattern.inset_x,
            inset_y=request.pattern.inset_y,
        )
        execution_plan = self.traversal_execution_planner.build_execution_plan(
            route_plan=route_plan,
            origin_coordinate=origin,
        )
        sweep_plan = build_world_map_sweep_plan(
            route_plan=route_plan,
            policy=request.sweep_policy,
        )
        first_step_movement_tool = self._movement_tool_for_action_family(
            request=request,
            action_family=execution_plan.steps[0].action_family,
        )
        return WorldMapResolvedSearchPlan(
            request=request,
            origin_coordinate=origin,
            coverage_bounds=coverage_bounds,
            stride=route_plan.stride,
            movement_tool=movement_tool,
            execution_start_coordinate=surface.viewport.coordinate or origin,
            first_step_movement_tool=first_step_movement_tool,
            route_plan=route_plan,
            execution_plan=execution_plan,
            sweep_plan=sweep_plan,
        )

    def preview_route(
        self,
        request: WorldMapSearchRequest,
        observation: Observation,
        *,
        head: int = 5,
        tail: int = 5,
    ) -> dict[str, object]:
        """Builds one route-preview document suitable for dry-run auditing before live sweep execution."""

        if head <= 0 or tail <= 0:
            raise SelectorResolutionError(
                "World-map route preview requires positive head and tail sizes.",
                head=head,
                tail=tail,
            )
        plan = self.resolve_plan(request, observation)
        checkpoints = plan.route
        preview_head = checkpoints[:head]
        preview_tail = checkpoints[-tail:] if len(checkpoints) > tail else checkpoints
        return {
            "pattern": plan.request.pattern.kind.value,
            "origin_coordinate": [plan.origin_coordinate[0], plan.origin_coordinate[1]],
            "coverage_bounds": {
                "min_x": plan.coverage_bounds.min_x,
                "min_y": plan.coverage_bounds.min_y,
                "max_x": plan.coverage_bounds.max_x,
                "max_y": plan.coverage_bounds.max_y,
            },
            "stride": {
                "horizontal_stride_units": plan.stride.horizontal_stride_units,
                "vertical_stride_units": plan.stride.vertical_stride_units,
            },
            "checkpoint_count": len(checkpoints),
            "sweep_policy": plan.sweep_plan.policy.kind.value,
            "sweep_segment_count": len(plan.sweep_plan.segments),
            "head_checkpoints": [
                {
                    "route_index": checkpoint.route_index,
                    "coordinate": [checkpoint.coordinate[0], checkpoint.coordinate[1]],
                    "distance_from_origin": checkpoint.distance_from_origin,
                }
                for checkpoint in preview_head
            ],
            "tail_checkpoints": [
                {
                    "route_index": checkpoint.route_index,
                    "coordinate": [checkpoint.coordinate[0], checkpoint.coordinate[1]],
                    "distance_from_origin": checkpoint.distance_from_origin,
                }
                for checkpoint in preview_tail
            ],
            "segments": [
                {
                    "segment_index": segment.segment_index,
                    "intent": segment.traversal_segment_intent.value,
                    "start_coordinate": [segment.start_coordinate[0], segment.start_coordinate[1]],
                    "end_coordinate": [segment.end_coordinate[0], segment.end_coordinate[1]],
                    "checkpoint_count": len(segment.analyzed_checkpoint_coordinates),
                }
                for segment in plan.route_plan.segments
            ],
        }

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
        active_runtime_state = {} if runtime_state is None else runtime_state
        profile_state = _mutable_runtime_state(active_runtime_state, "world_map_search_execution_profile")
        search_started_at = time.perf_counter()
        current_observation = start_observation or self.observation_service.observe(f"{label_prefix}_start")
        if current_observation.screen_type != ScreenType.PNC_WORLD_MAP or current_observation.spatial_surface is None:
            raise SelectorResolutionError(
                "World-map search execution requires the caller to provide or capture a proven world-map observation first.",
                screen_type=current_observation.screen_type,
            )
        plan_started_at = time.perf_counter()
        plan = self.resolve_plan(request, current_observation)
        profile_state["movement_tool"] = plan.movement_tool
        profile_state["execution_start_coordinate"] = plan.execution_start_coordinate
        profile_state["first_step_movement_tool"] = plan.first_step_movement_tool
        profile_state["plan_elapsed_ms"] = (time.perf_counter() - plan_started_at) * 1000.0
        matched_keys: list[WorldMapObjectKey] = []
        matched_by_key: dict[WorldMapObjectKey, WorldMapObjectSighting] = {}
        visited_checkpoints: list[WorldMapTraversalCheckpoint] = []
        castle_enrichment_used = False
        asynchronous_p2 = request.sweep_policy.kind == WorldMapSweepPolicyKind.PRODUCTION_FULL_MAP
        if asynchronous_p2 and (
            request.stop_policy.stop_on_first_confirmed_match
            or request.stop_policy.max_matches is not None
            or (
                request.castle_enrichment_policy.kind == WorldMapCastleEnrichmentPolicyKind.WHEN_REQUIRED
                and request.matcher.supports_castle_enrichment()
            )
        ):
            raise SelectorResolutionError(
                "Production full-map P2 overlap requires exhaustive checkpoint treatment; "
                "match-driven stopping and castle enrichment require synchronous result application."
            )
        if asynchronous_p2:
            return self._execute_production_segment_search(
                request=request,
                label_prefix=label_prefix,
                current_observation=current_observation,
                runtime_state=active_runtime_state,
                profile_state=profile_state,
                search_started_at=search_started_at,
                plan=plan,
            )

        def apply_p2_result(result: WorldMapViewportAnalysisResult) -> Observation:
            """Applies one worker result and performs matching on the coordinator thread."""

            rich_observation = self._apply_checkpoint_analysis_result(result)
            self._collect_checkpoint_matches(
                request=request,
                observation=rich_observation,
                matched_keys=matched_keys,
                matched_by_key=matched_by_key,
            )
            return rich_observation

        def finish(stop_reason: WorldMapSearchStopReason) -> WorldMapSearchResult:
            """Builds the final result and persists one sequence summary when checkpoints were analyzed."""

            persist_summary_started_at = time.perf_counter()
            self._persist_sequence_summary(
                label=f"{label_prefix}_summary",
                visited_checkpoints=visited_checkpoints,
            )
            profile_state["persist_summary_elapsed_ms"] = (time.perf_counter() - persist_summary_started_at) * 1000.0
            profile_state["stop_reason"] = stop_reason
            profile_state["total_elapsed_ms"] = (time.perf_counter() - search_started_at) * 1000.0
            return self._build_result(
                matched_keys=matched_keys,
                matched_by_key=matched_by_key,
                stop_reason=stop_reason,
                visited_checkpoints=visited_checkpoints,
                plan=plan,
                castle_enrichment_used=castle_enrichment_used,
                execution_profile=_build_search_execution_profile_from_state(profile_state),
            )

        try:
            steps = plan.execution_plan.steps
            route_length = len(steps)
            for step in steps:
                checkpoint = step.checkpoint
                if request.stop_policy.max_radius_units is not None and checkpoint.distance_from_origin > request.stop_policy.max_radius_units:
                    return finish(WorldMapSearchStopReason.RADIUS_LIMIT_REACHED)
                checkpoint_started_at = time.perf_counter()
                move_elapsed_ms = 0.0
                ingest_elapsed_ms = 0.0
                match_elapsed_ms = 0.0
                stop_policy_elapsed_ms = 0.0
                enrichment_elapsed_ms = 0.0
                p2_analysis_elapsed_ms = 0.0
                checkpoint_status = "completed"
                failure_stage: str | None = None
                pending_stop_reason: WorldMapSearchStopReason | None = None
                movement_tool = self._movement_tool_for_step(plan=plan, step=step)
                p1_captures: list[CapturedObservation] = []
                try:
                    move_started_at = time.perf_counter()
                    failure_stage = "move"
                    current_observation = self.move_to_checkpoint(
                        current_observation,
                        plan=plan,
                        step=step,
                        label_prefix=f"{label_prefix}_move_{checkpoint.route_index}",
                        runtime_state=active_runtime_state,
                        p1_capture_sink=p1_captures.append,
                    )
                    move_elapsed_ms = (time.perf_counter() - move_started_at) * 1000.0

                    ingest_started_at = time.perf_counter()
                    failure_stage = "p2_analysis"
                    current_observation, work_item = self._build_checkpoint_analysis_work_item(
                        current_observation,
                        p1_captures=p1_captures,
                        label=f"{label_prefix}_checkpoint_{checkpoint.route_index}",
                        checkpoint=checkpoint,
                        profile_state=profile_state,
                    )
                    result = self.viewport_analyzer.analyze(work_item)
                    current_observation = apply_p2_result(result)
                    p2_analysis_elapsed_ms = result.elapsed_ms
                    ingest_elapsed_ms = (time.perf_counter() - ingest_started_at) * 1000.0

                    visited_checkpoints.append(checkpoint)

                    match_started_at = time.perf_counter()
                    failure_stage = "match"
                    match_elapsed_ms = (time.perf_counter() - match_started_at) * 1000.0

                    stop_policy_started_at = time.perf_counter()
                    failure_stage = "stop_policy"
                    stop_reason = self._evaluate_stop_policy(
                        request=request,
                        route_length=route_length,
                        checkpoint=checkpoint,
                        matched_count=len(matched_keys),
                        visited_count=len(visited_checkpoints),
                    )
                    stop_policy_elapsed_ms = (time.perf_counter() - stop_policy_started_at) * 1000.0
                    if stop_reason is not None:
                        pending_stop_reason = stop_reason

                    if (
                        pending_stop_reason is None
                        and
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
                            enrichment_started_at = time.perf_counter()
                            failure_stage = "castle_enrichment"
                            castle_enrichment_used = True
                            current_observation, _ = self.castle_inspector.inspect_candidates(
                                matcher=request.matcher,
                                candidates=candidates,
                                current_observation=current_observation,
                                label_prefix=f"{label_prefix}_castle_enrichment_{checkpoint.route_index}",
                                runtime_state=active_runtime_state,
                            )
                            self._collect_index_matches(
                                matcher=request.matcher,
                                matched_keys=matched_keys,
                                matched_by_key=matched_by_key,
                            )
                            stop_reason = self._evaluate_stop_policy(
                                request=request,
                                route_length=route_length,
                                checkpoint=checkpoint,
                                matched_count=len(matched_keys),
                                visited_count=len(visited_checkpoints),
                            )
                            enrichment_elapsed_ms = (time.perf_counter() - enrichment_started_at) * 1000.0
                            if stop_reason is not None:
                                pending_stop_reason = stop_reason
                    failure_stage = None
                except Exception:
                    checkpoint_status = "failed"
                    raise
                finally:
                    _record_search_checkpoint_profile(
                        profile_state=profile_state,
                        profile=WorldMapSearchCheckpointProfile(
                            checkpoint_route_index=checkpoint.route_index,
                            checkpoint_coordinate=checkpoint.coordinate,
                            action_family=step.action_family.value,
                            movement_tool=movement_tool.value,
                            movement_phase=_movement_phase_for_step(step),
                            move_elapsed_ms=move_elapsed_ms,
                            ingest_elapsed_ms=ingest_elapsed_ms,
                            match_elapsed_ms=match_elapsed_ms,
                            stop_policy_elapsed_ms=stop_policy_elapsed_ms,
                            enrichment_elapsed_ms=enrichment_elapsed_ms,
                            p2_analysis_elapsed_ms=p2_analysis_elapsed_ms,
                            total_elapsed_ms=(time.perf_counter() - checkpoint_started_at) * 1000.0,
                            status=checkpoint_status,
                            failure_stage=failure_stage,
                        ),
                    )
                if pending_stop_reason is not None:
                    return finish(pending_stop_reason)
            return finish(
                WorldMapSearchStopReason.BOUNDARY_EXHAUSTED
                if request.boundary is not None
                else WorldMapSearchStopReason.ROUTE_EXHAUSTED
            )
        finally:
            profile_state.setdefault("total_elapsed_ms", (time.perf_counter() - search_started_at) * 1000.0)
            self.flush_runtime_diagnostics(runtime_state=active_runtime_state)

    def _execute_production_segment_search(
        self,
        *,
        request: WorldMapSearchRequest,
        label_prefix: str,
        current_observation: Observation,
        runtime_state: dict[str, Any],
        profile_state: dict[str, Any],
        search_started_at: float,
        plan: WorldMapResolvedSearchPlan,
    ) -> WorldMapSearchResult:
        """Runs exact-P1 sampled production traversal by row/lane segments."""

        profile_state["production_sample_proof_mode"] = WorldMapProductionSampleProofMode.EXACT_P1_SAMPLED_SEGMENT
        p2_queue = WorldMapViewportAnalysisQueue(
            analyzer=self.viewport_analyzer.analyze,
            max_pending=request.sweep_policy.max_pending_p2_items,
        )
        matched_keys: list[WorldMapObjectKey] = []
        matched_by_key: dict[WorldMapObjectKey, WorldMapObjectSighting] = {}
        visited_checkpoints: list[WorldMapTraversalCheckpoint] = []
        step_by_route_index = {
            step.checkpoint.route_index: step
            for step in plan.execution_plan.steps
        }
        sampled_budget = request.stop_policy.max_checkpoints

        def apply_p2_result(result: WorldMapViewportAnalysisResult) -> Observation:
            """Applies one segment-sample result on the coordinator thread."""

            rich_observation = self._apply_checkpoint_analysis_result(result)
            self._collect_checkpoint_matches(
                request=request,
                observation=rich_observation,
                matched_keys=matched_keys,
                matched_by_key=matched_by_key,
            )
            return rich_observation

        def drain_ready_p2() -> None:
            """Applies any completed segment-sample prefix without blocking movement."""

            for result in p2_queue.drain_ready():
                apply_p2_result(result)

        def submit_p2(work_item: WorldMapViewportAnalysisWorkItem) -> None:
            """Submits one sample, applying backpressure through the canonical queue."""

            if work_item.actual_sample is not None:
                _record_production_sample(profile_state=profile_state, sample=work_item.actual_sample)
            if p2_queue.pending_count >= request.sweep_policy.max_pending_p2_items:
                apply_p2_result(p2_queue.drain_next(blocking_reason="backpressure"))
            p2_queue.submit(work_item)

        def drain_all_p2() -> None:
            """Drains queued samples and records aggregate P2 evidence."""

            drain_started_at = time.perf_counter()
            try:
                for result in p2_queue.drain_all():
                    apply_p2_result(result)
            finally:
                profile_state["p2_queue_drain_elapsed_ms"] = (
                    profile_state.get("p2_queue_drain_elapsed_ms", 0.0)
                    + (time.perf_counter() - drain_started_at) * 1000.0
                )
                _record_p2_queue_profile(profile_state=profile_state, queue=p2_queue)

        def finish(stop_reason: WorldMapSearchStopReason) -> WorldMapSearchResult:
            """Builds the final production result after deterministic P2 drain."""

            drain_all_p2()
            persist_summary_started_at = time.perf_counter()
            self._persist_sequence_summary(
                label=f"{label_prefix}_summary",
                visited_checkpoints=visited_checkpoints,
            )
            profile_state["persist_summary_elapsed_ms"] = (time.perf_counter() - persist_summary_started_at) * 1000.0
            profile_state["stop_reason"] = stop_reason
            profile_state["total_elapsed_ms"] = (time.perf_counter() - search_started_at) * 1000.0
            return self._build_result(
                matched_keys=matched_keys,
                matched_by_key=matched_by_key,
                stop_reason=stop_reason,
                visited_checkpoints=visited_checkpoints,
                plan=plan,
                castle_enrichment_used=False,
                execution_profile=_build_search_execution_profile_from_state(profile_state),
            )

        try:
            active_observation = current_observation
            for segment in plan.sweep_plan.segments:
                if sampled_budget is not None and len(visited_checkpoints) >= sampled_budget:
                    return finish(WorldMapSearchStopReason.CHECKPOINT_BUDGET_EXHAUSTED)
                segment_started_at = time.perf_counter()
                status = "completed"
                failure_stage: str | None = None
                move_elapsed_ms = 0.0
                start_anchor_elapsed_ms = 0.0
                end_anchor_elapsed_ms = 0.0
                ingest_elapsed_ms = 0.0
                sampled_frame_count = 0
                pending_stop_reason: WorldMapSearchStopReason | None = None
                try:
                    failure_stage = "start_anchor"
                    start_anchor_started_at = time.perf_counter()
                    active_observation, start_work_item = self._move_to_segment_start_work_item(
                        observation=active_observation,
                        plan=plan,
                        segment=segment,
                        step_by_route_index=step_by_route_index,
                        label_prefix=label_prefix,
                        runtime_state=runtime_state,
                        profile_state=profile_state,
                    )
                    start_anchor_elapsed_ms = (time.perf_counter() - start_anchor_started_at) * 1000.0
                    ingest_started_at = time.perf_counter()
                    submit_p2(start_work_item)
                    first_checkpoint = step_by_route_index[segment.checkpoint_route_indices[0]].checkpoint
                    visited_checkpoints.append(first_checkpoint)
                    sampled_frame_count += 1
                    ingest_elapsed_ms += (time.perf_counter() - ingest_started_at) * 1000.0

                    pending_stop_reason = self._evaluate_stop_policy(
                        request=request,
                        route_length=len(plan.execution_plan.steps),
                        checkpoint=first_checkpoint,
                        matched_count=len(matched_keys),
                        visited_count=len(visited_checkpoints),
                    )
                    if pending_stop_reason is None:
                        active_observation, move_elapsed_ms, end_anchor_elapsed_ms, sampled_count, pending_stop_reason = (
                            self._traverse_production_segment_samples(
                                observation=active_observation,
                                request=request,
                                plan=plan,
                                segment=segment,
                                step_by_route_index=step_by_route_index,
                                label_prefix=label_prefix,
                                runtime_state=runtime_state,
                                visited_checkpoints=visited_checkpoints,
                                start_anchor_coordinate=start_work_item.checkpoint_coordinate,
                                submit_p2=submit_p2,
                                drain_ready_p2=drain_ready_p2,
                                p2_pending_count=lambda: p2_queue.pending_count,
                            )
                        )
                        sampled_frame_count += sampled_count
                except Exception:
                    status = "failed"
                    raise
                finally:
                    _record_search_segment_profile(
                        profile_state=profile_state,
                        profile=WorldMapSearchSegmentProfile(
                            segment_index=segment.segment_index,
                            start_coordinate=segment.start_coordinate,
                            end_coordinate=segment.end_coordinate,
                            checkpoint_count=len(segment.checkpoint_coordinates),
                            sampled_frame_count=sampled_frame_count,
                            move_elapsed_ms=move_elapsed_ms,
                            start_anchor_elapsed_ms=start_anchor_elapsed_ms,
                            end_anchor_elapsed_ms=end_anchor_elapsed_ms,
                            ingest_elapsed_ms=ingest_elapsed_ms,
                            total_elapsed_ms=(time.perf_counter() - segment_started_at) * 1000.0,
                            status=status,
                            failure_stage=failure_stage if status == "failed" else None,
                        ),
                    )
                if pending_stop_reason is not None:
                    return finish(pending_stop_reason)
            return finish(
                WorldMapSearchStopReason.BOUNDARY_EXHAUSTED
                if request.boundary is not None
                else WorldMapSearchStopReason.ROUTE_EXHAUSTED
            )
        finally:
            p2_queue.close()
            profile_state.setdefault("total_elapsed_ms", (time.perf_counter() - search_started_at) * 1000.0)
            self.flush_runtime_diagnostics(runtime_state=runtime_state)

    def _move_to_segment_start_work_item(
        self,
        *,
        observation: Observation,
        plan: WorldMapResolvedSearchPlan,
        segment: WorldMapSweepSegment,
        step_by_route_index: Mapping[int, WorldMapTraversalExecutionStep],
        label_prefix: str,
        runtime_state: dict[str, Any],
        profile_state: dict[str, Any],
    ) -> tuple[Observation, WorldMapViewportAnalysisWorkItem]:
        """Samples a segment start only after the movement anchor is aligned to the planned lane."""

        if self.observation_service is None:
            raise SelectorResolutionError("Production segment starts require observation_service.")
        start_route_index = segment.checkpoint_route_indices[0]
        start_step = step_by_route_index[start_route_index]
        current_coordinate = _require_world_map_viewport_coordinate(observation)
        sample_label = f"{label_prefix}_segment_{segment.segment_index}_sample_{start_route_index}"
        if not _coordinate_within_tolerance(
            current_coordinate,
            start_step.checkpoint.coordinate,
            tolerance=self.coordinate_mover_for_runtime().movement_policy.maximum_accepted_landing_delta_units,
        ):
            p1_captures: list[CapturedObservation] = []
            observation = self.move_to_checkpoint(
                observation,
                plan=plan,
                step=start_step,
                label_prefix=f"{sample_label}_anchor_alignment",
                runtime_state=runtime_state,
                p1_capture_sink=p1_captures.append,
            )
            observation, capture = self._resolve_p1_movement_proof_capture(
                observation,
                p1_captures=p1_captures,
                label=sample_label,
                profile_state=profile_state,
            )
        else:
            capture = self.observation_service.capture_observation(
                sample_label,
                request=ObservationRequest.world_map_movement_proof_follow_up(),
                artifact_selection=self._routine_artifact_selection(
                    ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF
                ),
            )
            observation = capture.observation
        return observation, self._build_production_sample_analysis_work_item(
            capture=capture,
            route_index=start_route_index,
            planned_coordinate=start_step.checkpoint.coordinate,
            label=sample_label,
            projected_frame=None,
        )

    def _traverse_production_segment_samples(
        self,
        *,
        observation: Observation,
        request: WorldMapSearchRequest,
        plan: WorldMapResolvedSearchPlan,
        segment: WorldMapSweepSegment,
        step_by_route_index: Mapping[int, WorldMapTraversalExecutionStep],
        label_prefix: str,
        runtime_state: dict[str, Any],
        visited_checkpoints: list[WorldMapTraversalCheckpoint],
        start_anchor_coordinate: tuple[int, int],
        submit_p2: Any,
        drain_ready_p2: Any,
        p2_pending_count: Any,
    ) -> tuple[Observation, float, float, int, WorldMapSearchStopReason | None]:
        """Traverses one row/lane by actual coverage, correcting only when adjacent samples can leave a gap."""

        if self.observation_service is None or self.action_executor is None:
            raise SelectorResolutionError("Production segment traversal requires observation_service and action_executor.")
        if len(segment.checkpoint_coordinates) == 1:
            return observation, 0.0, 0.0, 0, None
        current = observation
        move_elapsed_ms = 0.0
        end_anchor_elapsed_ms = 0.0
        sampled_count = 0
        previous_coordinate = start_anchor_coordinate
        scan_footprint_units = estimated_world_map_visible_scan_footprint_units()
        for sample_index, (route_index, coordinate) in enumerate(
            zip(segment.checkpoint_route_indices[1:], segment.checkpoint_coordinates[1:]),
            start=1,
        ):
            if request.stop_policy.max_checkpoints is not None and len(visited_checkpoints) >= request.stop_policy.max_checkpoints:
                return current, move_elapsed_ms, end_anchor_elapsed_ms, sampled_count, WorldMapSearchStopReason.CHECKPOINT_BUDGET_EXHAUSTED
            checkpoint = step_by_route_index[route_index].checkpoint
            if request.stop_policy.max_radius_units is not None and checkpoint.distance_from_origin > request.stop_policy.max_radius_units:
                return current, move_elapsed_ms, end_anchor_elapsed_ms, sampled_count, WorldMapSearchStopReason.RADIUS_LIMIT_REACHED
            action = self._build_segment_swipe_action(
                planned_from_coordinate=segment.checkpoint_coordinates[sample_index - 1],
                planned_to_coordinate=coordinate,
            )
            if p2_pending_count() > 0:
                profile_state = _mutable_runtime_state(runtime_state, "world_map_search_execution_profile")
                profile_state["p2_movement_overlap_count"] = profile_state.get("p2_movement_overlap_count", 0) + 1
            move_started_at = time.perf_counter()
            self.action_executor.execute_action(
                action,
                _observation_with_world_map_coordinate(current, previous_coordinate),
            )
            move_elapsed_ms += (time.perf_counter() - move_started_at) * 1000.0
            sample_label = f"{label_prefix}_segment_{segment.segment_index}_sample_{route_index}"
            proof_started_at = time.perf_counter()
            capture = self.observation_service.capture_observation(
                sample_label,
                request=ObservationRequest.world_map_movement_proof_follow_up(),
                artifact_selection=self._routine_artifact_selection(
                    ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF
                ),
            )
            current = capture.observation
            end_anchor_elapsed_ms += (time.perf_counter() - proof_started_at) * 1000.0
            proof = WorldMapViewportProof.from_capture(capture)
            if proof.strength != WorldMapProofStrength.EXACT or proof.coordinate is None:
                raise SelectorResolutionError(
                    "Production segment samples require exact P1 coordinate proof.",
                    proof_strength=proof.strength.value,
                )
            if world_map_sample_gap_exceeds_scan_footprint(
                previous_coordinate=previous_coordinate,
                current_coordinate=proof.coordinate,
                scan_footprint_units=scan_footprint_units,
            ):
                correction_started_at = time.perf_counter()
                p1_captures: list[CapturedObservation] = []
                current = self.move_to_checkpoint(
                    current,
                    plan=plan,
                    step=step_by_route_index[route_index],
                    label_prefix=f"{sample_label}_coverage_correction",
                    runtime_state=runtime_state,
                    p1_capture_sink=p1_captures.append,
                )
                end_anchor_elapsed_ms += (time.perf_counter() - correction_started_at) * 1000.0
                corrected_capture = self._find_matching_p1_capture(observation=current, captures=p1_captures)
                if corrected_capture is None:
                    corrected_capture = self.observation_service.capture_observation(
                        f"{sample_label}_coverage_correction_capture",
                        request=ObservationRequest.world_map_movement_proof_follow_up(),
                        artifact_selection=self._routine_artifact_selection(
                            ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF
                        ),
                    )
                    current = corrected_capture.observation
                capture = corrected_capture
                proof = WorldMapViewportProof.from_capture(capture)
                if proof.coordinate is None or world_map_sample_gap_exceeds_scan_footprint(
                    previous_coordinate=previous_coordinate,
                    current_coordinate=proof.coordinate,
                    scan_footprint_units=scan_footprint_units,
                ):
                    raise SelectorResolutionError(
                        "Production segment coverage correction did not restore contiguous sampled coverage.",
                        previous_coordinate=previous_coordinate,
                        current_coordinate=proof.coordinate,
                        scan_footprint_units=scan_footprint_units,
                    )
            work_item = self._build_production_sample_analysis_work_item(
                capture=capture,
                route_index=route_index,
                planned_coordinate=coordinate,
                label=sample_label,
                projected_frame=WorldMapCoordinateProjectionContext(
                    segment=segment,
                    start_anchor_coordinate=previous_coordinate,
                    end_anchor_coordinate=proof.coordinate,
                    max_uncertainty_units=request.sweep_policy.sparse_proof_policy.max_projection_uncertainty_units,
                ).project_frame(
                    WorldMapSampledFrame(
                        frame_id=sample_label,
                        segment_index=segment.segment_index,
                        sample_index=sample_index,
                        progress_ratio=1.0,
                        screenshot_artifact_path=capture.screenshot.artifact_path,
                    )
                ),
            )
            submit_p2(work_item)
            drain_ready_p2()
            visited_checkpoints.append(checkpoint)
            sampled_count += 1
            previous_coordinate = proof.coordinate
            stop_reason = self._evaluate_stop_policy(
                request=request,
                route_length=len(plan.execution_plan.steps),
                checkpoint=checkpoint,
                matched_count=0,
                visited_count=len(visited_checkpoints),
            )
            if stop_reason is not None:
                return current, move_elapsed_ms, end_anchor_elapsed_ms, sampled_count, stop_reason
        return current, move_elapsed_ms, end_anchor_elapsed_ms, sampled_count, None

    def _build_segment_swipe_action(
        self,
        *,
        planned_from_coordinate: tuple[int, int],
        planned_to_coordinate: tuple[int, int],
    ) -> SwipeAction:
        """Builds one no-observe cardinal lane swipe for a production segment leg."""

        direction = _direction_for_planned_segment_leg(
            from_coordinate=planned_from_coordinate,
            to_coordinate=planned_to_coordinate,
        )
        action = self.coordinate_mover_for_runtime().navigator.build_default_cardinal_navigation_action(
            direction,
            reason=f"production_segment_lane_{direction.value}",
            observe_after=False,
            follow_up_request=None,
        )
        return replace(
            action,
            observe_after=False,
            follow_up_request=None,
            gesture_primitive=self.coordinate_mover_for_runtime().movement_policy.gesture_primitive,
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
        execution_profile: WorldMapSearchExecutionProfile | None,
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
            execution_profile=execution_profile,
        )

    def move_to_checkpoint(
        self,
        observation: Observation,
        *,
        plan: WorldMapResolvedSearchPlan,
        step: WorldMapTraversalExecutionStep,
        label_prefix: str,
        runtime_state: dict[str, Any] | None = None,
        p1_capture_sink: Callable[["CapturedObservation"], None] | None = None,
    ) -> Observation:
        """Moves toward the requested checkpoint using the step's resolved low-level movement primitive."""

        checkpoint = step.checkpoint
        movement_tool = self._movement_tool_for_step(plan=plan, step=step)
        if movement_tool == WorldMapMovementToolKind.COORDINATE_JUMP:
            return self._move_with_coordinate_jump(
                observation,
                checkpoint=checkpoint,
                label_prefix=label_prefix,
                p1_capture_sink=p1_capture_sink,
            )
        if movement_tool == WorldMapMovementToolKind.OVERVIEW_SEED:
            return self._move_with_overview_seed(
                observation,
                checkpoint=checkpoint,
                label_prefix=label_prefix,
                p1_capture_sink=p1_capture_sink,
            )
        return self.coordinate_mover_for_runtime().move_to_coordinate(
            observation,
            target_coordinate=checkpoint.coordinate,
            label_prefix=label_prefix,
            runtime_state=runtime_state,
            boundary_bounds=_known_world_map_bounds(plan.request),
            coordinate_domain=plan.request.coordinate_domain,
            movement_family=step.action_family,
            movement_proof_artifact_selection=self._routine_artifact_selection(
                ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF
            ),
            logging_mode=DiagnosticLogMode.BUFFERED_SEQUENCE,
            p1_capture_sink=p1_capture_sink,
        )

    def _move_with_coordinate_jump(
        self,
        observation: Observation,
        *,
        checkpoint: WorldMapTraversalCheckpoint,
        label_prefix: str,
        p1_capture_sink: Callable[["CapturedObservation"], None] | None = None,
    ) -> Observation:
        """Executes one coordinate-jump move or fails fast when the runtime lacks the required primitive."""

        plan = self.coordinate_navigator.plan_jump(target=checkpoint.coordinate, current_observation=observation)
        freshest_observation = observation
        try:
            if not plan.requires_execution:
                freshest_observation = proven = _require_proven_world_map_observation(
                    observation_service=self.observation_service,
                    observation=observation,
                    label_prefix=f"{label_prefix}_already_at_target",
                    p1_capture_sink=p1_capture_sink,
                    artifact_selection=self._routine_artifact_selection(
                        ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF
                    ),
                )
                self._require_checkpoint_landing(
                    proven,
                    checkpoint=checkpoint,
                    requested_coordinate=plan.normalized_target_coordinate,
                )
                return proven
            assert plan.open_action is not None and plan.submit_action is not None
            freshest_observation = opened = self._execute_actions(
                [plan.open_action],
                observation,
                label_prefix=f"{label_prefix}_open",
                artifact_selection=self._routine_artifact_selection(ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF),
                p1_capture_sink=p1_capture_sink,
            )
            initial_dialog_state = self._require_coordinate_dialog_state(
                opened,
                label_prefix=f"{label_prefix}_open_dialog_refresh",
            )
            filled = opened
            if plan.fill_actions:
                freshest_observation = filled = self._execute_actions(
                    plan.fill_actions,
                    opened,
                    label_prefix=f"{label_prefix}_fill",
                    artifact_selection=self._routine_artifact_selection(ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF),
                    p1_capture_sink=p1_capture_sink,
                )
            self._require_coordinate_dialog_pre_submit_state(
                filled,
                label_prefix=f"{label_prefix}_fill_dialog_refresh",
                plan=plan,
                initial_state=initial_dialog_state,
            )
            freshest_observation = after = self._execute_actions(
                [plan.submit_action],
                filled,
                label_prefix=f"{label_prefix}_submit",
                artifact_selection=self._routine_artifact_selection(ObservationArtifactRoutine.WORLD_MAP_ANALYZED_CHECKPOINT),
                p1_capture_sink=p1_capture_sink,
            )
            _raise_if_world_map_coordinate_jump_status_banner(after, target_coordinate=checkpoint.coordinate)
            freshest_observation = proven = _require_proven_world_map_observation(
                observation_service=self.observation_service,
                observation=after,
                label_prefix=f"{label_prefix}_verify_landing",
                p1_capture_sink=p1_capture_sink,
                artifact_selection=self._routine_artifact_selection(
                    ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF
                ),
            )
            self._require_checkpoint_landing(
                proven,
                checkpoint=checkpoint,
                requested_coordinate=plan.normalized_target_coordinate,
            )
            return proven
        except Exception as error:
            self._record_checkpoint_movement_failure(
                error=error,
                observation=freshest_observation,
                checkpoint=checkpoint,
                label=f"{label_prefix}_failure",
                movement_tool=WorldMapMovementToolKind.COORDINATE_JUMP,
            )
            raise

    def _require_coordinate_dialog_state(
        self,
        observation: Observation,
        *,
        label_prefix: str,
    ) -> WorldMapCoordinateDialogState:
        """Returns coordinate-dialog state, retrying once for transient missing field OCR."""

        try:
            return self.coordinate_navigator.require_dialog_state(observation)
        except SelectorResolutionError as error:
            if not _coordinate_dialog_field_refresh_is_allowed(error=error, observation=observation):
                raise
            refreshed = self._refresh_coordinate_dialog_observation(label_prefix=label_prefix)
            return self.coordinate_navigator.require_dialog_state(refreshed)

    def _require_coordinate_dialog_pre_submit_state(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        plan: WorldMapCoordinateJumpPlan,
        initial_state: WorldMapCoordinateDialogState,
    ) -> WorldMapCoordinateDialogState:
        """Returns pre-submit dialog state, retrying once for transient missing field OCR."""

        try:
            return self.coordinate_navigator.require_pre_submit_state(
                observation,
                plan=plan,
                initial_state=initial_state,
            )
        except SelectorResolutionError as error:
            if not _coordinate_dialog_field_refresh_is_allowed(error=error, observation=observation):
                raise
            refreshed = self._refresh_coordinate_dialog_observation(label_prefix=label_prefix)
            return self.coordinate_navigator.require_pre_submit_state(
                refreshed,
                plan=plan,
                initial_state=initial_state,
            )

    def _refresh_coordinate_dialog_observation(self, *, label_prefix: str) -> Observation:
        """Captures one fresh coordinate-dialog proof using the canonical narrow request."""

        if self.observation_service is None:
            raise SelectorResolutionError("Coordinate-dialog proof refresh requires observation_service.")
        return self.observation_service.observe(
            label_prefix,
            request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            artifact_selection=self._routine_artifact_selection(ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF),
        )

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
        p1_capture_sink: Callable[["CapturedObservation"], None] | None = None,
    ) -> Observation:
        """Executes one overview-assisted move or fails fast when the runtime lacks the required primitive."""

        if not self.overview_navigator.is_supported():
            raise SelectorResolutionError(
                "Overview-assisted world-map movement is not configured in this runtime yet.",
                screen_type=observation.screen_type,
                label_prefix=label_prefix,
            )
        normalized_target = self.overview_navigator.normalize_target_coordinate(checkpoint.coordinate)
        freshest_observation = observation
        try:
            freshest_observation = opened = self._execute_actions(
                self.overview_navigator.plan_open(observation),
                observation,
                label_prefix=f"{label_prefix}_overview_open",
                artifact_selection=self._routine_artifact_selection(ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF),
                p1_capture_sink=p1_capture_sink,
            )
            freshest_observation = after = self._execute_actions(
                self.overview_navigator.plan_recenter(opened, target_coordinate=checkpoint.coordinate),
                opened,
                label_prefix=f"{label_prefix}_overview_recenter",
                artifact_selection=self._routine_artifact_selection(ObservationArtifactRoutine.WORLD_MAP_ANALYZED_CHECKPOINT),
                p1_capture_sink=p1_capture_sink,
            )
            freshest_observation = proven = _require_proven_world_map_observation(
                observation_service=self.observation_service,
                observation=after,
                label_prefix=f"{label_prefix}_verify_landing",
                p1_capture_sink=p1_capture_sink,
                artifact_selection=self._routine_artifact_selection(
                    ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF
                ),
            )
            self._require_checkpoint_landing(
                proven,
                checkpoint=checkpoint,
                requested_coordinate=normalized_target,
            )
            return proven
        except Exception as error:
            self._record_checkpoint_movement_failure(
                error=error,
                observation=freshest_observation,
                checkpoint=checkpoint,
                label=f"{label_prefix}_failure",
                movement_tool=WorldMapMovementToolKind.OVERVIEW_SEED,
            )
            raise

    def _execute_actions(
        self,
        actions: Sequence[ActionRequest],
        observation: Observation,
        *,
        label_prefix: str,
        artifact_selection: ObservationArtifactSelection | None = None,
        p1_capture_sink: Callable[["CapturedObservation"], None] | None = None,
    ) -> Observation:
        """Executes the provided actions and returns the freshest observed result."""

        if self.action_executor is None or self.observation_service is None:
            raise SelectorResolutionError("World-map search action execution requires observation_service and action_executor.")
        def observe(label: str, request: ObservationRequest | None = None) -> Observation:
            """Captures one action follow-up and exposes its screenshot to the P1 coordinator."""

            capture = self.observation_service.capture_observation(
                f"{label_prefix}_{label}",
                request=request,
                artifact_selection=artifact_selection,
            )
            if p1_capture_sink is not None:
                p1_capture_sink(capture)
            return capture.observation

        return self.action_executor.execute_actions(
            actions,
            observation,
            observe=observe,
        ).observation

    def _build_checkpoint_analysis_work_item(
        self,
        observation: Observation,
        *,
        p1_captures: Sequence["CapturedObservation"],
        label: str,
        checkpoint: WorldMapTraversalCheckpoint,
        profile_state: dict[str, Any],
    ) -> tuple[Observation, WorldMapViewportAnalysisWorkItem]:
        """Builds an observation-free P2 item from the exact screenshot P1 used for movement proof."""

        observation, capture = self._resolve_p1_movement_proof_capture(
            observation,
            p1_captures=p1_captures,
            label=label,
            profile_state=profile_state,
        )
        proof = WorldMapViewportProof.from_capture(capture)
        if proof.strength != WorldMapProofStrength.EXACT or proof.coordinate is None:
            raise SelectorResolutionError(
                "P2 checkpoint submission requires exact P1 movement proof.",
                proof_strength=proof.strength.value,
            )
        if not _coordinate_within_tolerance(
            proof.coordinate,
            checkpoint.coordinate,
            tolerance=(
                self.coordinate_mover_for_runtime().movement_policy.maximum_accepted_landing_delta_units
            ),
        ):
            raise SelectorResolutionError(
                "P1 checkpoint screenshot does not prove the requested checkpoint landing.",
                checkpoint_coordinate=checkpoint.coordinate,
                proof_coordinate=proof.coordinate,
            )
        return observation, WorldMapViewportAnalysisWorkItem(
            route_index=checkpoint.route_index,
            checkpoint_coordinate=proof.coordinate,
            screenshot=capture.screenshot,
            proof=proof,
            label=label,
            treatment_kind=WorldMapViewportAnalysisTreatmentKind.CHECKPOINT_SEARCH,
        )

    def _resolve_p1_movement_proof_capture(
        self,
        observation: Observation,
        *,
        p1_captures: Sequence["CapturedObservation"],
        label: str,
        profile_state: dict[str, Any],
    ) -> tuple[Observation, "CapturedObservation"]:
        """Returns the P1 capture matching movement state, recapturing narrowly when executor capture identity is absent."""

        capture = self._find_matching_p1_capture(observation=observation, captures=p1_captures)
        if capture is not None:
            return observation, capture
        if self.observation_service is None:
            raise SelectorResolutionError("P1 movement-proof capture requires observation_service.")
        profile_state["p1_fallback_capture_count"] = profile_state.get("p1_fallback_capture_count", 0) + 1
        if p1_captures:
            profile_state["p1_mismatched_capture_count"] = profile_state.get("p1_mismatched_capture_count", 0) + 1
        else:
            profile_state["p1_missing_capture_count"] = profile_state.get("p1_missing_capture_count", 0) + 1
        capture = self.observation_service.capture_observation(
            f"{label}_p1_capture",
            request=ObservationRequest.world_map_movement_proof_follow_up(),
            artifact_selection=self._routine_artifact_selection(ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF),
        )
        return capture.observation, capture

    @staticmethod
    def _build_production_sample_analysis_work_item(
        *,
        capture: "CapturedObservation",
        route_index: int,
        planned_coordinate: tuple[int, int],
        label: str,
        projected_frame: WorldMapProjectedFrame | None,
    ) -> WorldMapViewportAnalysisWorkItem:
        """Builds the canonical P2 inventory work item for one actual-coordinate production sample."""

        proof = WorldMapViewportProof.from_capture(capture)
        if proof.strength != WorldMapProofStrength.EXACT or proof.coordinate is None:
            raise SelectorResolutionError(
                "Production segment samples require exact P1 coordinate proof.",
                proof_strength=proof.strength.value,
            )
        actual_sample = WorldMapActualSample(
            route_index=route_index,
            planned_coordinate=planned_coordinate,
            actual_coordinate=proof.coordinate,
            proof=proof,
            screenshot=capture.screenshot,
            projected_frame=projected_frame,
        )
        return WorldMapViewportAnalysisWorkItem(
            route_index=route_index,
            checkpoint_coordinate=proof.coordinate,
            screenshot=capture.screenshot,
            proof=proof,
            label=label,
            treatment_kind=WorldMapViewportAnalysisTreatmentKind.INVENTORY_ONLY,
            projected_frame=projected_frame,
            actual_sample=actual_sample,
        )

    @staticmethod
    def _find_matching_p1_capture(
        *,
        observation: Observation,
        captures: Sequence["CapturedObservation"],
    ) -> "CapturedObservation | None":
        """Returns the newest P1 capture whose minimal observation is the current movement state."""

        for capture in reversed(captures):
            if capture.observation is observation:
                return capture
            if (
                capture.observation.captured_at == observation.captured_at
                and capture.observation.artifact_path == observation.artifact_path
            ):
                return capture
        return None

    def _apply_checkpoint_analysis_result(self, result: WorldMapViewportAnalysisResult) -> Observation:
        """Applies one immutable P2 result to the survey on the coordinator thread."""

        assert self.survey_recorder is not None
        checkpoint_capture = self.survey_recorder.ingest_analysis_result(result)
        return result.observation if checkpoint_capture.capture is None else checkpoint_capture.capture.observation

    def coordinate_mover_for_runtime(self) -> WorldMapCoordinateMover:
        """Returns the canonical coordinate mover shared by sweep traversal and calibration helpers."""

        if self.coordinate_mover is not None:
            self.coordinate_mover.movement_step_budget = self.movement_step_budget
            if hasattr(self.coordinate_mover, "movement_policy"):
                self.coordinate_mover.movement_policy = WorldMapMovementPolicy(
                    gesture_primitive=self.screen_flows.world_map_navigator.gesture_primitive,
                    arrival_tolerance_units=self.coordinate_mover.movement_policy.arrival_tolerance_units,
                    overshoot_tolerance_units=self.coordinate_mover.movement_policy.overshoot_tolerance_units,
                    correction_threshold_units=self.coordinate_mover.movement_policy.correction_threshold_units,
                    traverse_max_axis_delta_per_leg=self.coordinate_mover.movement_policy.traverse_max_axis_delta_per_leg,
                    correction_max_axis_delta_per_leg=self.coordinate_mover.movement_policy.correction_max_axis_delta_per_leg,
                )
            return self.coordinate_mover
        self.coordinate_mover = WorldMapCoordinateMover(
            observation_service=self.observation_service,
            action_executor=self.action_executor,
            navigator=self.screen_flows.world_map_navigator,
            coordinate_domain=WorldMapCoordinateDomain.puzzles_and_conquest(),
            movement_policy=WorldMapMovementPolicy(
                gesture_primitive=self.screen_flows.world_map_navigator.gesture_primitive,
            ),
            movement_step_budget=self.movement_step_budget,
            logger=None if self.action_executor is None else getattr(self.action_executor, "logger", None),
        )
        return self.coordinate_mover

    def _coordinate_mover(self) -> WorldMapCoordinateMover:
        """Returns the canonical coordinate mover for legacy private call sites."""

        return self.coordinate_mover_for_runtime()

    def _routine_artifact_selection(self, routine: ObservationArtifactRoutine) -> ObservationArtifactSelection | None:
        """Returns the shared routine artifact selection for the current observation mode when available."""

        if self.observation_service is None:
            return None
        return resolve_routine_artifact_selection(mode=self.observation_service.mode, routine=routine)

    def flush_runtime_diagnostics(self, *, runtime_state: dict[str, Any] | None) -> None:
        """Flushes any buffered traversal diagnostics for the provided shared runtime state."""

        flush_buffered_diagnostic_logs(
            logger=None if self.action_executor is None else getattr(self.action_executor, "logger", None),
            runtime_state=runtime_state,
        )

    def _record_checkpoint_movement_failure(
        self,
        *,
        error: Exception,
        observation: Observation,
        checkpoint: WorldMapTraversalCheckpoint,
        label: str,
        movement_tool: WorldMapMovementToolKind,
    ) -> None:
        """Persists one failure screenshot and logs one explicit non-swipe checkpoint-movement failure."""

        if self.coordinate_mover is not None:
            self.coordinate_mover.persist_failure_observation(
                observation=observation,
                label=label,
                error=error,
            )
        elif self.observation_service is not None and (
            artifact_selection := self._routine_artifact_selection(ObservationArtifactRoutine.FAILURE)
        ):
            try:
                self.observation_service.capture_observation(
                    label,
                    request=ObservationRequest.full_runtime_default(),
                    artifact_selection=artifact_selection,
                )
            except Exception as persist_error:
                error.add_note(f"Failure observation persistence also failed: {persist_error!r}")
        emit_diagnostic_log(
            logger=None if self.action_executor is None else getattr(self.action_executor, "logger", None),
            runtime_state=None,
            mode=DiagnosticLogMode.IMMEDIATE,
            level=logging.ERROR,
            message="World-map checkpoint movement failed.",
            extra={
                "movement_tool": movement_tool.value,
                "checkpoint_coordinate": checkpoint.coordinate,
                "route_index": checkpoint.route_index,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "error_details": error.details if isinstance(error, SelectorResolutionError) else None,
            },
        )

    def _persist_sequence_summary(
        self,
        *,
        label: str,
        visited_checkpoints: Sequence[WorldMapTraversalCheckpoint],
    ) -> None:
        """Persists one end-of-sequence survey summary when the configured artifact policy requests it."""

        if self.survey_recorder is None or not visited_checkpoints:
            return
        if not hasattr(self.survey_recorder.observation_service, "artifact_directory"):
            return
        artifact_selection = self._routine_artifact_selection(ObservationArtifactRoutine.WORLD_MAP_SEQUENCE_SUMMARY)
        if not artifact_selection:
            return
        self.survey_recorder.persist_checkpoint(
            label,
            artifact_selection=artifact_selection,
        )

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

    def _movement_tool_for_step(
        self,
        *,
        plan: WorldMapResolvedSearchPlan,
        step: WorldMapTraversalExecutionStep,
    ) -> WorldMapMovementToolKind:
        """Returns the supported movement primitive for one executable itinerary step."""

        return self._movement_tool_for_action_family(
            request=plan.request,
            action_family=step.action_family,
        )

    def _movement_tool_for_action_family(
        self,
        *,
        request: WorldMapSearchRequest,
        action_family: WorldMapTraversalActionFamily,
    ) -> WorldMapMovementToolKind:
        """Resolves movement per step so non-local entry does not force local checkpoints to jump."""

        if action_family == WorldMapTraversalActionFamily.NON_LOCAL_DIRECT:
            for tool in (
                WorldMapMovementToolKind.COORDINATE_JUMP,
                WorldMapMovementToolKind.OVERVIEW_SEED,
                WorldMapMovementToolKind.SWIPE,
            ):
                if self._movement_tool_allowed_for_step(request=request, tool=tool) and self._movement_tool_supported(tool):
                    return tool
        for tool in request.movement_preferences.allowed_tools:
            if self._movement_tool_supported(tool):
                return tool
        raise SelectorResolutionError(
            "The requested world-map movement preferences cannot be satisfied by the current runtime.",
            allowed_tools=tuple(tool.value for tool in request.movement_preferences.allowed_tools),
            action_family=action_family.value,
        )

    def _movement_tool_supported(self, tool: WorldMapMovementToolKind) -> bool:
        """Returns whether the runtime can execute one low-level world-map movement primitive."""

        if tool == WorldMapMovementToolKind.SWIPE:
            return True
        if tool == WorldMapMovementToolKind.COORDINATE_JUMP:
            return self.coordinate_navigator.is_supported()
        if tool == WorldMapMovementToolKind.OVERVIEW_SEED:
            return self.overview_navigator.is_supported()
        raise SelectorResolutionError("Unsupported world-map movement tool.", movement_tool=tool.value)

    def _movement_tool_allowed_for_step(
        self,
        *,
        request: WorldMapSearchRequest,
        tool: WorldMapMovementToolKind,
    ) -> bool:
        """Returns whether a primitive is available to this step without broadening local checkpoint movement."""

        if tool in request.movement_preferences.allowed_tools:
            return True
        return request.boundary is not None and request.boundary.kind == WorldMapSearchBoundaryKind.FULL_MAP

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
        route_length: int,
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
        if stop_policy.max_checkpoints is not None and visited_count >= stop_policy.max_checkpoints and checkpoint.route_index < route_length - 1:
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
    p1_capture_sink: Callable[["CapturedObservation"], None] | None = None,
    artifact_selection: ObservationArtifactSelection | None = None,
) -> Observation:
    """Returns one exact P1-proven world-map observation using the canonical proof seam."""

    return require_exact_world_map_observation(
        observation_service=observation_service,
        observation=observation,
        label_prefix=label_prefix,
        policy=WorldMapMovementProofPolicy(
            refresh_budget=refresh_budget,
            capture_sink=p1_capture_sink,
            artifact_selection=artifact_selection,
        ),
    )


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
    max_axis_delta_per_leg: int | None = None,
) -> WorldCoordinate | None:
    """Returns the next canonical cardinal leg, honoring one-shot drift correction before normal axis order."""

    current_coordinate = _require_world_map_viewport_coordinate(current)
    if preferred_axis == "x" and abs(target_coordinate[0] - current_coordinate[0]) > focus_tolerance:
        return _bounded_axis_leg_target(
            current_coordinate=current_coordinate,
            target_coordinate=target_coordinate,
            axis="x",
            max_axis_delta_per_leg=max_axis_delta_per_leg,
        )
    if preferred_axis == "y" and abs(target_coordinate[1] - current_coordinate[1]) > focus_tolerance:
        return _bounded_axis_leg_target(
            current_coordinate=current_coordinate,
            target_coordinate=target_coordinate,
            axis="y",
            max_axis_delta_per_leg=max_axis_delta_per_leg,
        )
    delta_x = target_coordinate[0] - current_coordinate[0]
    if abs(delta_x) > focus_tolerance:
        return _bounded_axis_leg_target(
            current_coordinate=current_coordinate,
            target_coordinate=target_coordinate,
            axis="x",
            max_axis_delta_per_leg=max_axis_delta_per_leg,
        )
    delta_y = target_coordinate[1] - current_coordinate[1]
    if abs(delta_y) > focus_tolerance:
        return _bounded_axis_leg_target(
            current_coordinate=current_coordinate,
            target_coordinate=target_coordinate,
            axis="y",
            max_axis_delta_per_leg=max_axis_delta_per_leg,
        )
    return None


def _bounded_axis_leg_target(
    *,
    current_coordinate: tuple[int, int],
    target_coordinate: tuple[int, int],
    axis: str,
    max_axis_delta_per_leg: int | None,
) -> WorldCoordinate:
    """Returns one single-axis leg target, capped when movement granularity is configured."""

    current_axis_value = current_coordinate[0] if axis == "x" else current_coordinate[1]
    target_axis_value = target_coordinate[0] if axis == "x" else target_coordinate[1]
    delta = target_axis_value - current_axis_value
    if max_axis_delta_per_leg is not None and abs(delta) > max_axis_delta_per_leg:
        target_axis_value = current_axis_value + (max_axis_delta_per_leg if delta > 0 else -max_axis_delta_per_leg)
    if axis == "x":
        return WorldCoordinate(x=target_axis_value, y=current_coordinate[1])
    return WorldCoordinate(x=current_coordinate[0], y=target_axis_value)


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


def _coordinate_dialog_field_refresh_is_allowed(
    *,
    error: SelectorResolutionError,
    observation: Observation,
) -> bool:
    """Returns whether one coordinate-dialog proof miss is safe to refresh once."""

    return (
        observation.screen_type == ScreenType.PNC_WORLD_COORDINATE_DIALOG
        and error.message == "The requested text-field state was not observed for the current screen."
    )


def _coordinate_overshot_within_tolerance(
    *,
    before_coordinate: tuple[int, int],
    after_coordinate: tuple[int, int],
    target_coordinate: tuple[int, int],
    tolerance: int,
) -> bool:
    """Returns whether one cardinal swipe crossed the target and landed in the accepted overshoot band."""

    if _coordinate_within_tolerance(after_coordinate, target_coordinate, tolerance=tolerance):
        crossed_x = _axis_crossed_target(before_coordinate[0], after_coordinate[0], target_coordinate[0])
        crossed_y = _axis_crossed_target(before_coordinate[1], after_coordinate[1], target_coordinate[1])
        moved_x = before_coordinate[0] != after_coordinate[0]
        moved_y = before_coordinate[1] != after_coordinate[1]
        return (moved_x and crossed_x and after_coordinate[1] == target_coordinate[1]) or (
            moved_y and crossed_y and after_coordinate[0] == target_coordinate[0]
        )
    return False


def _axis_crossed_target(before_axis_value: int, after_axis_value: int, target_axis_value: int) -> bool:
    """Returns whether a one-dimensional movement segment includes the target value."""

    return min(before_axis_value, after_axis_value) <= target_axis_value <= max(before_axis_value, after_axis_value)


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


def _direction_for_planned_segment_leg(
    *,
    from_coordinate: tuple[int, int],
    to_coordinate: tuple[int, int],
) -> WorldMapCardinalDirection:
    """Returns the lane direction for two adjacent planned production segment checkpoints."""

    return _direction_for_cardinal_leg(
        from_coordinate=from_coordinate,
        leg_target=WorldCoordinate(*to_coordinate),
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


def _movement_step_traces(movement_state: dict[str, Any]) -> list[WorldMapMovementStepTrace]:
    """Returns the mutable list that stores recorded direct-movement traces on runtime state."""

    traces = movement_state.get("step_traces")
    if isinstance(traces, list) and all(isinstance(trace, WorldMapMovementStepTrace) for trace in traces):
        return traces
    traces = []
    movement_state["step_traces"] = traces
    return traces


def _record_movement_step_trace(*, movement_state: dict[str, Any], trace: WorldMapMovementStepTrace) -> None:
    """Appends one recorded direct-movement trace to the shared runtime state."""

    _movement_step_traces(movement_state).append(trace)


def _search_checkpoint_profiles(profile_state: dict[str, Any]) -> list[WorldMapSearchCheckpointProfile]:
    """Returns the mutable list that stores canonical per-checkpoint benchmark records on runtime state."""

    profiles = profile_state.get("checkpoint_profiles")
    if isinstance(profiles, list) and all(isinstance(profile, WorldMapSearchCheckpointProfile) for profile in profiles):
        return profiles
    profiles = []
    profile_state["checkpoint_profiles"] = profiles
    return profiles


def _record_search_checkpoint_profile(
    *,
    profile_state: dict[str, Any],
    profile: WorldMapSearchCheckpointProfile,
) -> None:
    """Appends one canonical checkpoint benchmark record to runtime state."""

    _search_checkpoint_profiles(profile_state).append(profile)


def _search_segment_profiles(profile_state: dict[str, Any]) -> list[WorldMapSearchSegmentProfile]:
    """Returns the mutable list that stores production segment benchmark records on runtime state."""

    profiles = profile_state.get("segment_profiles")
    if isinstance(profiles, list) and all(isinstance(profile, WorldMapSearchSegmentProfile) for profile in profiles):
        return profiles
    profiles = []
    profile_state["segment_profiles"] = profiles
    return profiles


def _record_search_segment_profile(
    *,
    profile_state: dict[str, Any],
    profile: WorldMapSearchSegmentProfile,
) -> None:
    """Appends one production segment benchmark record to runtime state."""

    _search_segment_profiles(profile_state).append(profile)


def _record_production_sample(
    *,
    profile_state: dict[str, Any],
    sample: WorldMapActualSample,
) -> None:
    """Appends one canonical production sample identity to runtime profile state."""

    samples = profile_state.get("production_samples")
    if samples is None:
        samples = []
        profile_state["production_samples"] = samples
    if not isinstance(samples, list):
        raise SelectorResolutionError("World-map production sample profile state must be list-backed.")
    samples.append(sample)


def _record_p2_queue_profile(
    *,
    profile_state: dict[str, Any],
    queue: WorldMapViewportAnalysisQueue,
) -> None:
    """Copies canonical P2 queue counters and telemetry into runtime profile state."""

    profile_state["p2_queue_submission_count"] = queue.submission_count
    profile_state["p2_queue_peak_depth"] = queue.peak_depth
    profile_state["p2_queue_backpressure_block_count"] = queue.backpressure_block_count
    profile_state["p2_queue_backpressure_block_elapsed_ms"] = queue.backpressure_block_elapsed_ms
    profile_state["p2_queue_first_failure"] = queue.first_failure
    profile_state["p2_queue_telemetry"] = queue.telemetry_records


def _build_search_execution_profile_from_state(profile_state: Mapping[str, Any]) -> WorldMapSearchExecutionProfile:
    """Builds one canonical aggregate benchmark profile from runtime state."""

    movement_tool = profile_state.get("movement_tool")
    if movement_tool is not None and not isinstance(movement_tool, WorldMapMovementToolKind):
        raise SelectorResolutionError(
            "World-map search execution profiling requires a valid movement_tool enum when present.",
            movement_tool=movement_tool,
        )
    execution_start_coordinate = profile_state.get("execution_start_coordinate")
    if execution_start_coordinate is not None and not is_integer_pair(execution_start_coordinate):
        raise SelectorResolutionError(
            "World-map search execution profiling requires a valid execution_start_coordinate pair when present.",
            execution_start_coordinate=execution_start_coordinate,
        )
    first_step_movement_tool = profile_state.get("first_step_movement_tool")
    if first_step_movement_tool is not None and not isinstance(first_step_movement_tool, WorldMapMovementToolKind):
        raise SelectorResolutionError(
            "World-map search execution profiling requires a valid first_step_movement_tool enum when present.",
            first_step_movement_tool=first_step_movement_tool,
        )
    stop_reason = profile_state.get("stop_reason")
    if stop_reason is not None and not isinstance(stop_reason, WorldMapSearchStopReason):
        raise SelectorResolutionError(
            "World-map search execution profiling requires a valid stop_reason enum when present.",
            stop_reason=stop_reason,
        )
    checkpoint_profiles = profile_state.get("checkpoint_profiles", ())
    if not isinstance(checkpoint_profiles, tuple | list) or not all(
        isinstance(profile, WorldMapSearchCheckpointProfile) for profile in checkpoint_profiles
    ):
        raise SelectorResolutionError(
            "World-map search execution profiling requires checkpoint_profiles to contain only canonical checkpoint records."
        )
    segment_profiles = profile_state.get("segment_profiles", ())
    if not isinstance(segment_profiles, tuple | list) or not all(
        isinstance(profile, WorldMapSearchSegmentProfile) for profile in segment_profiles
    ):
        raise SelectorResolutionError(
            "World-map search execution profiling requires segment_profiles to contain only canonical segment records."
        )
    p2_queue_first_failure = profile_state.get("p2_queue_first_failure")
    if p2_queue_first_failure is not None and not isinstance(
        p2_queue_first_failure,
        WorldMapViewportAnalysisTelemetryRecord,
    ):
        raise SelectorResolutionError("World-map search execution profiling requires typed P2 first-failure telemetry.")
    p2_queue_telemetry = profile_state.get("p2_queue_telemetry", ())
    if not isinstance(p2_queue_telemetry, tuple | list) or not all(
        isinstance(record, WorldMapViewportAnalysisTelemetryRecord) for record in p2_queue_telemetry
    ):
        raise SelectorResolutionError("World-map search execution profiling requires typed P2 queue telemetry.")
    production_samples = profile_state.get("production_samples", ())
    if not isinstance(production_samples, tuple | list) or not all(
        isinstance(sample, WorldMapActualSample) for sample in production_samples
    ):
        raise SelectorResolutionError("World-map search execution profiling requires typed production samples.")
    production_sample_proof_mode = profile_state.get("production_sample_proof_mode")
    if production_sample_proof_mode is not None and not isinstance(
        production_sample_proof_mode,
        WorldMapProductionSampleProofMode,
    ):
        raise SelectorResolutionError(
            "World-map search execution profiling requires a valid production sample proof mode.",
            production_sample_proof_mode=production_sample_proof_mode,
        )
    return WorldMapSearchExecutionProfile(
        movement_tool=movement_tool,
        execution_start_coordinate=execution_start_coordinate,
        first_step_movement_tool=first_step_movement_tool,
        plan_elapsed_ms=_coerce_profile_elapsed_ms(profile_state.get("plan_elapsed_ms", 0.0), field_name="plan_elapsed_ms"),
        persist_summary_elapsed_ms=_coerce_profile_elapsed_ms(
            profile_state.get("persist_summary_elapsed_ms", 0.0),
            field_name="persist_summary_elapsed_ms",
        ),
        total_elapsed_ms=_coerce_profile_elapsed_ms(
            profile_state.get("total_elapsed_ms", 0.0),
            field_name="total_elapsed_ms",
        ),
        stop_reason=stop_reason,
        checkpoint_profiles=tuple(checkpoint_profiles),
        segment_profiles=tuple(segment_profiles),
        p2_queue_submission_count=_coerce_profile_count(
            profile_state.get("p2_queue_submission_count", 0),
            field_name="p2_queue_submission_count",
        ),
        p2_queue_peak_depth=_coerce_profile_count(
            profile_state.get("p2_queue_peak_depth", 0),
            field_name="p2_queue_peak_depth",
        ),
        p2_movement_overlap_count=_coerce_profile_count(
            profile_state.get("p2_movement_overlap_count", 0),
            field_name="p2_movement_overlap_count",
        ),
        p2_queue_drain_elapsed_ms=_coerce_profile_elapsed_ms(
            profile_state.get("p2_queue_drain_elapsed_ms", 0.0),
            field_name="p2_queue_drain_elapsed_ms",
        ),
        p1_fallback_capture_count=_coerce_profile_count(
            profile_state.get("p1_fallback_capture_count", 0),
            field_name="p1_fallback_capture_count",
        ),
        p1_missing_capture_count=_coerce_profile_count(
            profile_state.get("p1_missing_capture_count", 0),
            field_name="p1_missing_capture_count",
        ),
        p1_mismatched_capture_count=_coerce_profile_count(
            profile_state.get("p1_mismatched_capture_count", 0),
            field_name="p1_mismatched_capture_count",
        ),
        p2_queue_backpressure_block_count=_coerce_profile_count(
            profile_state.get("p2_queue_backpressure_block_count", 0),
            field_name="p2_queue_backpressure_block_count",
        ),
        p2_queue_backpressure_block_elapsed_ms=_coerce_profile_elapsed_ms(
            profile_state.get("p2_queue_backpressure_block_elapsed_ms", 0.0),
            field_name="p2_queue_backpressure_block_elapsed_ms",
        ),
        p2_queue_first_failure=p2_queue_first_failure,
        p2_queue_telemetry=tuple(p2_queue_telemetry),
        production_samples=tuple(production_samples),
        production_sample_proof_mode=production_sample_proof_mode,
    )


def _coerce_profile_elapsed_ms(value: object, *, field_name: str) -> float:
    """Normalizes one internal timing value to float milliseconds or fails fast on malformed state."""

    if not isinstance(value, int | float):
        raise SelectorResolutionError(
            "World-map search execution profiling requires numeric millisecond values.",
            field_name=field_name,
            value=value,
        )
    normalized = float(value)
    if normalized < 0:
        raise SelectorResolutionError(
            "World-map search execution profiling requires non-negative millisecond values.",
            field_name=field_name,
            value=value,
        )
    return normalized


def _coerce_profile_count(value: object, *, field_name: str) -> int:
    """Normalizes one internal non-negative integer profile count or fails fast."""

    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SelectorResolutionError(
            "World-map search execution profiling requires non-negative integer counts.",
            field_name=field_name,
            value=value,
        )
    return value


def _movement_phase_for_step(step: WorldMapTraversalExecutionStep) -> str:
    """Returns the profile phase for one executable checkpoint step."""

    if step.step_index == 0 and step.action_family == WorldMapTraversalActionFamily.NON_LOCAL_DIRECT:
        return "non_local_entry"
    return "steady_state"


def _build_cardinal_move_attempt_details(
    *,
    action: ActionRequest,
    before_observation: Observation,
    after_observation: Observation,
    before_coordinate: tuple[int, int],
    after_coordinate: tuple[int, int],
    target_coordinate: tuple[int, int],
    requested_coordinate: tuple[int, int],
    leg_target: tuple[int, int],
    delta: tuple[int, int],
    direction: str,
) -> dict[str, Any]:
    """Builds one canonical movement-error payload from the latest cardinal swipe attempt."""

    details: dict[str, Any] = {
        "target_coordinate": target_coordinate,
        "requested_coordinate": requested_coordinate,
        "before_coordinate": before_coordinate,
        "after_coordinate": after_coordinate,
        "delta": delta,
        "direction": direction,
        "leg_target": leg_target,
        "artifact_path": None if after_observation.artifact_path is None else str(after_observation.artifact_path),
        "coordinate_text": _world_map_coordinate_text_or_none(after_observation),
    }
    if isinstance(action, SwipeAction) and before_observation.image_size is not None:
        details["swipe_points"] = resolve_swipe_points_for_action(
            width=before_observation.image_size[0],
            height=before_observation.image_size[1],
            action=action,
        )
    return details


def _remember_last_cardinal_move_attempt(
    *,
    movement_state: dict[str, Any],
    attempt_details: Mapping[str, Any],
    classification: WorldMapCardinalMovementClassification,
) -> None:
    """Stores the latest classified cardinal swipe attempt so retry exhaustion can raise with full evidence."""

    movement_state["last_cardinal_move_attempt"] = {
        **attempt_details,
        "classification": classification.value,
    }


def _build_stagnant_retry_exhausted_error(
    *,
    error: SelectorResolutionError,
    movement_state: Mapping[str, Any],
    target_coordinate: tuple[int, int],
    requested_coordinate: tuple[int, int],
) -> SelectorResolutionError | None:
    """Re-wraps navigator stagnant-retry exhaustion with the last concrete swipe evidence when available."""

    if error.message != "World-map navigation swipe did not produce meaningful coordinate movement.":
        return None
    attempt_details = movement_state.get("last_cardinal_move_attempt")
    if not isinstance(attempt_details, Mapping):
        return None
    details = dict(attempt_details)
    details.setdefault("target_coordinate", target_coordinate)
    details.setdefault("requested_coordinate", requested_coordinate)
    details["stagnant_retry_failure"] = dict(error.details)
    return SelectorResolutionError(
        "World-map movement exhausted its bounded stagnant-swipe retry budget.",
        **details,
    )


def _require_valid_world_map_step_budget(
    step_budget: int,
    *,
    field_name: str,
) -> None:
    """Rejects invalid world-map step budgets before runtime loops consume them."""

    if step_budget <= 0:
        raise SelectorResolutionError(
            "World-map step budgets must be positive integers.",
            field_name=field_name,
            step_budget=step_budget,
        )


def _world_map_coordinate_text_or_none(observation: Observation) -> str | None:
    """Returns the parsed coordinate-bar text from a proven world-map observation when the metadata exposed it."""

    surface = observation.spatial_surface
    if surface is None or surface.surface_type != SpatialSurfaceType.WORLD_MAP:
        return None
    coordinate_text = surface.metadata.get("coordinate_text")
    if coordinate_text is None:
        return None
    return str(coordinate_text)


def _observation_with_world_map_coordinate(
    observation: Observation,
    coordinate: tuple[int, int],
) -> Observation:
    """Returns a planning-only observation with the same screenshot metadata and a synthetic viewport coordinate."""

    surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
    viewport = replace(surface.viewport, x=coordinate[0], y=coordinate[1])
    return replace(
        observation,
        spatial_surface=replace(
            surface,
            viewport=viewport,
            metadata={**surface.metadata, "coordinate_text": f"X:{coordinate[0]} Y:{coordinate[1]}"},
        ),
    )
