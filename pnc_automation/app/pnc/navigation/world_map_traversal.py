"""Canonical world-map traversal route and execution planning."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import (
    WorldMapBounds,
    WorldMapCoordinateDomain,
    coordinate_chebyshev_distance,
    is_integer_pair,
)
from pnc_automation.core.errors import SelectorResolutionError


class WorldMapSearchPatternKind(StrEnum):
    """Defines the canonical checkpoint visitation order families for world-map search."""

    ROW_MAJOR_SWEEP = "row_major_sweep"
    SERPENTINE_ROW_SWEEP = "serpentine_row_sweep"
    EXPANDING_RING = "expanding_ring"
    PERIMETER_RING_SWEEP = "perimeter_ring_sweep"
    SHRINKING_PERIMETER_SWEEP = "shrinking_perimeter_sweep"


class WorldMapEdge(StrEnum):
    """Defines one exact world-map rectangle edge used by perimeter decomposition."""

    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class WorldMapSearchBoundaryKind(StrEnum):
    """Defines the allowed coverage region for one world-map search request."""

    FULL_MAP = "full_map"
    RADIUS_FROM_ORIGIN = "radius_from_origin"
    RECTANGLE = "rectangle"


class WorldMapTraversalCorner(StrEnum):
    """Defines one named rectangle corner used by perimeter traversal patterns."""

    UPPER_LEFT = "upper_left"
    UPPER_RIGHT = "upper_right"
    LOWER_LEFT = "lower_left"
    LOWER_RIGHT = "lower_right"


class TraversalRotation(StrEnum):
    """Defines the ordered perimeter rotation."""

    CLOCKWISE = "clockwise"
    COUNTERCLOCKWISE = "counterclockwise"


class TraversalSegmentIntent(StrEnum):
    """Defines the movement semantics needed to enter one route segment."""

    LOCAL_TRAVERSE = "local_traverse"
    NON_LOCAL_RESET = "non_local_reset"


class WorldMapTraversalActionFamily(StrEnum):
    """Defines the movement action family selected for one execution step."""

    LOCAL_DIRECT = "local_direct"
    NON_LOCAL_DIRECT = "non_local_direct"


@dataclass(frozen=True, slots=True)
class WorldMapViewportStrideProfile:
    """Owns the reviewed default viewport-sized stride values shared by traversal patterns."""

    default_horizontal_viewport_stride_units: int = 10
    default_vertical_viewport_stride_units: int = 10

    def __post_init__(self) -> None:
        """Rejects invalid default stride values before planning consumes them."""

        if self.default_horizontal_viewport_stride_units <= 0:
            raise SelectorResolutionError(
                "World-map viewport stride profiles require a positive horizontal stride.",
                default_horizontal_viewport_stride_units=self.default_horizontal_viewport_stride_units,
            )
        if self.default_vertical_viewport_stride_units <= 0:
            raise SelectorResolutionError(
                "World-map viewport stride profiles require a positive vertical stride.",
                default_vertical_viewport_stride_units=self.default_vertical_viewport_stride_units,
            )


@dataclass(frozen=True, slots=True)
class ResolvedTraversalStride:
    """Carries the fully resolved horizontal and vertical checkpoint strides for one route."""

    horizontal_stride_units: int
    vertical_stride_units: int

    def __post_init__(self) -> None:
        """Rejects non-positive resolved stride values."""

        if self.horizontal_stride_units <= 0 or self.vertical_stride_units <= 0:
            raise SelectorResolutionError(
                "Resolved traversal strides must stay positive on both axes.",
                horizontal_stride_units=self.horizontal_stride_units,
                vertical_stride_units=self.vertical_stride_units,
            )


@dataclass(frozen=True, slots=True)
class TraversalStridePolicy:
    """Defines the canonical analyzed-checkpoint stride overrides for traversal patterns."""

    horizontal_stride_units: int | None = None
    vertical_stride_units: int | None = None

    def __post_init__(self) -> None:
        """Rejects invalid authored stride overrides before route planning begins."""

        if self.horizontal_stride_units is not None and self.horizontal_stride_units <= 0:
            raise SelectorResolutionError(
                "Traversal stride policies require a positive horizontal_stride_units value when present.",
                horizontal_stride_units=self.horizontal_stride_units,
            )
        if self.vertical_stride_units is not None and self.vertical_stride_units <= 0:
            raise SelectorResolutionError(
                "Traversal stride policies require a positive vertical_stride_units value when present.",
                vertical_stride_units=self.vertical_stride_units,
            )

    @classmethod
    def viewport_default(cls) -> "TraversalStridePolicy":
        """Returns the canonical default policy that resolves through the shared viewport profile."""

        return cls()

    @classmethod
    def symmetric(cls, stride_units: int) -> "TraversalStridePolicy":
        """Returns one symmetric override applied to both axes."""

        return cls(horizontal_stride_units=stride_units, vertical_stride_units=stride_units)

    @classmethod
    def axis_specific(cls, *, horizontal_stride_units: int, vertical_stride_units: int) -> "TraversalStridePolicy":
        """Returns one explicit axis-specific stride override."""

        return cls(
            horizontal_stride_units=horizontal_stride_units,
            vertical_stride_units=vertical_stride_units,
        )

    def resolve(self, *, profile: WorldMapViewportStrideProfile) -> ResolvedTraversalStride:
        """Returns the fully resolved stride values after applying profile defaults."""

        return ResolvedTraversalStride(
            horizontal_stride_units=(
                profile.default_horizontal_viewport_stride_units
                if self.horizontal_stride_units is None
                else self.horizontal_stride_units
            ),
            vertical_stride_units=(
                profile.default_vertical_viewport_stride_units
                if self.vertical_stride_units is None
                else self.vertical_stride_units
            ),
        )


@dataclass(frozen=True, slots=True)
class WorldMapTraversalCheckpoint:
    """Defines one deterministic analyzed checkpoint coordinate in the planned traversal route."""

    coordinate: tuple[int, int]
    distance_from_origin: int
    route_index: int

    def __post_init__(self) -> None:
        """Rejects malformed checkpoints before runtime execution consumes them."""

        if not is_integer_pair(self.coordinate):
            raise SelectorResolutionError(
                "World-map traversal checkpoints require one integer coordinate pair.",
                coordinate=self.coordinate,
            )
        if self.distance_from_origin < 0:
            raise SelectorResolutionError(
                "World-map traversal checkpoints must use non-negative distance_from_origin values.",
                distance_from_origin=self.distance_from_origin,
            )
        if self.route_index < 0:
            raise SelectorResolutionError(
                "World-map traversal checkpoints must use non-negative route_index values.",
                route_index=self.route_index,
            )


@dataclass(frozen=True, slots=True)
class WorldMapTraversalRouteSegment:
    """Defines one ordered traversal segment plus the analyzed checkpoints it contributes."""

    segment_index: int
    polyline_vertices: tuple[tuple[int, int], ...]
    start_coordinate: tuple[int, int]
    end_coordinate: tuple[int, int]
    traversal_segment_intent: TraversalSegmentIntent
    analyzed_checkpoint_coordinates: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        """Rejects malformed route segments before execution planning consumes them."""

        if self.segment_index < 0:
            raise SelectorResolutionError(
                "World-map traversal route segments require a non-negative segment_index.",
                segment_index=self.segment_index,
            )
        if not self.polyline_vertices:
            raise SelectorResolutionError("World-map traversal route segments require at least one polyline vertex.")
        if self.start_coordinate != self.polyline_vertices[0]:
            raise SelectorResolutionError(
                "World-map traversal route segments require start_coordinate to match the first polyline vertex.",
                start_coordinate=self.start_coordinate,
                first_polyline_vertex=self.polyline_vertices[0],
            )
        if self.end_coordinate != self.polyline_vertices[-1]:
            raise SelectorResolutionError(
                "World-map traversal route segments require end_coordinate to match the last polyline vertex.",
                end_coordinate=self.end_coordinate,
                last_polyline_vertex=self.polyline_vertices[-1],
            )
        if not self.analyzed_checkpoint_coordinates:
            raise SelectorResolutionError(
                "World-map traversal route segments require at least one analyzed checkpoint coordinate.",
                segment_index=self.segment_index,
            )


@dataclass(frozen=True, slots=True)
class WorldMapTraversalRoutePlan:
    """Carries the canonical ordered route geometry resolved from one traversal pattern."""

    pattern_kind: WorldMapSearchPatternKind
    coverage_bounds: WorldMapBounds
    stride: ResolvedTraversalStride
    segments: tuple[WorldMapTraversalRouteSegment, ...]

    def __post_init__(self) -> None:
        """Rejects empty route plans before execution planning consumes them."""

        if not self.segments:
            raise SelectorResolutionError(
                "World-map traversal route plans require at least one route segment.",
                pattern=self.pattern_kind.value,
                coverage_bounds=self.coverage_bounds,
            )

    @property
    def checkpoints(self) -> tuple[tuple[int, int], ...]:
        """Returns the flattened analyzed checkpoint coordinates in route order."""

        ordered: list[tuple[int, int]] = []
        for segment in self.segments:
            ordered.extend(segment.analyzed_checkpoint_coordinates)
        return tuple(ordered)


@dataclass(frozen=True, slots=True)
class WorldMapTraversalExecutionStep:
    """Defines one executable traversal step compiled from route geometry plus intent semantics."""

    step_index: int
    segment_index: int
    checkpoint: WorldMapTraversalCheckpoint
    traversal_segment_intent: TraversalSegmentIntent
    action_family: WorldMapTraversalActionFamily

    def __post_init__(self) -> None:
        """Rejects malformed execution steps before runtime movement consumes them."""

        if self.step_index < 0 or self.segment_index < 0:
            raise SelectorResolutionError(
                "World-map traversal execution steps require non-negative step and segment indices.",
                step_index=self.step_index,
                segment_index=self.segment_index,
            )


@dataclass(frozen=True, slots=True)
class WorldMapTraversalExecutionPlan:
    """Carries the executable checkpoint-oriented plan compiled from one route plan."""

    route_plan: WorldMapTraversalRoutePlan
    steps: tuple[WorldMapTraversalExecutionStep, ...]

    def __post_init__(self) -> None:
        """Rejects empty execution plans before runtime traversal begins."""

        if not self.steps:
            raise SelectorResolutionError(
                "World-map traversal execution planning produced no executable steps.",
                pattern=self.route_plan.pattern_kind.value,
                coverage_bounds=self.route_plan.coverage_bounds,
            )

    def steps_to_checkpoints(self) -> tuple[WorldMapTraversalCheckpoint, ...]:
        """Returns the ordered checkpoints carried by the compiled execution plan."""

        return tuple(step.checkpoint for step in self.steps)


@dataclass(slots=True)
class WorldMapTraversalPlanner:
    """Builds canonical route geometry for world-map traversal patterns."""

    viewport_stride_profile: WorldMapViewportStrideProfile = WorldMapViewportStrideProfile()

    def build_route_plan(
        self,
        *,
        pattern_kind: WorldMapSearchPatternKind,
        coordinate_domain: WorldMapCoordinateDomain,
        origin_coordinate: tuple[int, int],
        coverage_bounds: WorldMapBounds,
        stride_policy: TraversalStridePolicy,
        perimeter_start_corner: WorldMapTraversalCorner = WorldMapTraversalCorner.UPPER_LEFT,
        perimeter_rotation: TraversalRotation = TraversalRotation.CLOCKWISE,
        inset_x: int | None = None,
        inset_y: int | None = None,
    ) -> WorldMapTraversalRoutePlan:
        """Returns the deterministic route geometry implied by the pattern and resolved traversal policy."""

        stride = stride_policy.resolve(profile=self.viewport_stride_profile)
        if pattern_kind == WorldMapSearchPatternKind.ROW_MAJOR_SWEEP:
            segments = _row_segments(
                coordinate_domain=coordinate_domain,
                bounds=coverage_bounds,
                stride=stride,
                serpentine=False,
            )
        elif pattern_kind == WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP:
            segments = _row_segments(
                coordinate_domain=coordinate_domain,
                bounds=coverage_bounds,
                stride=stride,
                serpentine=True,
            )
        elif pattern_kind == WorldMapSearchPatternKind.EXPANDING_RING:
            segments = _expanding_ring_segments(
                coordinate_domain=coordinate_domain,
                bounds=coverage_bounds,
                origin_coordinate=origin_coordinate,
                stride=stride,
            )
        elif pattern_kind == WorldMapSearchPatternKind.PERIMETER_RING_SWEEP:
            segments = _perimeter_segments(
                coordinate_domain=coordinate_domain,
                bounds=coverage_bounds,
                stride=stride,
                start_corner=perimeter_start_corner,
                rotation=perimeter_rotation,
            )
        elif pattern_kind == WorldMapSearchPatternKind.SHRINKING_PERIMETER_SWEEP:
            segments = _shrinking_perimeter_segments(
                coordinate_domain=coordinate_domain,
                bounds=coverage_bounds,
                stride=stride,
                start_corner=perimeter_start_corner,
                rotation=perimeter_rotation,
                inset_x=inset_x,
                inset_y=inset_y,
            )
        else:
            raise SelectorResolutionError("Unsupported world-map search pattern.", pattern=pattern_kind.value)
        return WorldMapTraversalRoutePlan(
            pattern_kind=pattern_kind,
            coverage_bounds=coverage_bounds,
            stride=stride,
            segments=segments,
        )

    def build_route(
        self,
        *,
        pattern_kind: WorldMapSearchPatternKind,
        coordinate_domain: WorldMapCoordinateDomain,
        origin_coordinate: tuple[int, int],
        coverage_bounds: WorldMapBounds,
        stride_policy: TraversalStridePolicy,
        perimeter_start_corner: WorldMapTraversalCorner = WorldMapTraversalCorner.UPPER_LEFT,
        perimeter_rotation: TraversalRotation = TraversalRotation.CLOCKWISE,
        inset_x: int | None = None,
        inset_y: int | None = None,
    ) -> tuple[WorldMapTraversalCheckpoint, ...]:
        """Returns the flattened analyzed checkpoints for compatibility call sites."""

        route_plan = self.build_route_plan(
            pattern_kind=pattern_kind,
            coordinate_domain=coordinate_domain,
            origin_coordinate=origin_coordinate,
            coverage_bounds=coverage_bounds,
            stride_policy=stride_policy,
            perimeter_start_corner=perimeter_start_corner,
            perimeter_rotation=perimeter_rotation,
            inset_x=inset_x,
            inset_y=inset_y,
        )
        return WorldMapTraversalExecutionPlanner().build_execution_plan(
            route_plan=route_plan,
            origin_coordinate=origin_coordinate,
        ).steps_to_checkpoints()


@dataclass(slots=True)
class WorldMapTraversalExecutionPlanner:
    """Compiles route geometry into executable checkpoint-oriented traversal steps."""

    def build_execution_plan(
        self,
        *,
        route_plan: WorldMapTraversalRoutePlan,
        origin_coordinate: tuple[int, int],
    ) -> WorldMapTraversalExecutionPlan:
        """Returns the executable traversal steps implied by the ordered route geometry."""

        steps: list[WorldMapTraversalExecutionStep] = []
        route_index = 0
        for segment in route_plan.segments:
            for checkpoint_index, coordinate in enumerate(segment.analyzed_checkpoint_coordinates):
                checkpoint = WorldMapTraversalCheckpoint(
                    coordinate=coordinate,
                    distance_from_origin=coordinate_chebyshev_distance(origin_coordinate, coordinate),
                    route_index=route_index,
                )
                intent = (
                    segment.traversal_segment_intent
                    if checkpoint_index == 0
                    else TraversalSegmentIntent.LOCAL_TRAVERSE
                )
                steps.append(
                    WorldMapTraversalExecutionStep(
                        step_index=route_index,
                        segment_index=segment.segment_index,
                        checkpoint=checkpoint,
                        traversal_segment_intent=intent,
                        action_family=(
                            WorldMapTraversalActionFamily.NON_LOCAL_DIRECT
                            if intent == TraversalSegmentIntent.NON_LOCAL_RESET
                            else WorldMapTraversalActionFamily.LOCAL_DIRECT
                        ),
                    )
                )
                route_index += 1
        return WorldMapTraversalExecutionPlan(route_plan=route_plan, steps=tuple(steps))


def _row_segments(
    *,
    coordinate_domain: WorldMapCoordinateDomain,
    bounds: WorldMapBounds,
    stride: ResolvedTraversalStride,
    serpentine: bool,
) -> tuple[WorldMapTraversalRouteSegment, ...]:
    """Builds row-oriented traversal segments using one canonical row sampling helper."""

    segments: list[WorldMapTraversalRouteSegment] = []
    for row_index, y in enumerate(coordinate_domain.row_samples(bounds=bounds, spacing=stride.vertical_stride_units)):
        coordinates = coordinate_domain.addressable_coordinates_on_row(
            bounds=bounds,
            y=y,
            spacing=stride.horizontal_stride_units,
            reverse=serpentine and row_index % 2 == 1,
        )
        if not coordinates:
            continue
        segments.append(
            WorldMapTraversalRouteSegment(
                segment_index=len(segments),
                polyline_vertices=coordinates,
                start_coordinate=coordinates[0],
                end_coordinate=coordinates[-1],
                traversal_segment_intent=(
                    TraversalSegmentIntent.LOCAL_TRAVERSE
                    if serpentine or not segments
                    else TraversalSegmentIntent.NON_LOCAL_RESET
                ),
                analyzed_checkpoint_coordinates=coordinates,
            )
        )
    if not segments:
        raise SelectorResolutionError(
            "World-map row traversal produced no addressable checkpoints.",
            bounds=bounds,
        )
    return tuple(segments)


def _expanding_ring_segments(
    *,
    coordinate_domain: WorldMapCoordinateDomain,
    bounds: WorldMapBounds,
    origin_coordinate: tuple[int, int],
    stride: ResolvedTraversalStride,
) -> tuple[WorldMapTraversalRouteSegment, ...]:
    """Builds deterministic expanding-ring traversal segments centered on the resolved origin."""

    ring_step = min(stride.horizontal_stride_units, stride.vertical_stride_units)
    raw_coordinates = coordinate_domain.normalize_route_coordinates(
        _expanding_ring_coordinates(bounds=bounds, origin=origin_coordinate, spacing=ring_step),
        bounds=bounds,
    )
    if not raw_coordinates:
        raise SelectorResolutionError(
            "World-map expanding-ring traversal produced no addressable checkpoints.",
            bounds=bounds,
            origin_coordinate=origin_coordinate,
        )
    segments: list[WorldMapTraversalRouteSegment] = []
    current_ring: list[tuple[int, int]] = []
    clamped_origin = bounds.clamp(origin_coordinate)
    previous_radius: int | None = None
    for coordinate in raw_coordinates:
        radius = coordinate_chebyshev_distance(clamped_origin, coordinate)
        if previous_radius is None:
            previous_radius = radius
        if previous_radius != radius and current_ring:
            segments.append(
                _build_segment(
                    segment_index=len(segments),
                    coordinates=tuple(current_ring),
                    intent=TraversalSegmentIntent.LOCAL_TRAVERSE,
                )
            )
            current_ring = []
            previous_radius = radius
        current_ring.append(coordinate)
    if current_ring:
        segments.append(
            _build_segment(
                segment_index=len(segments),
                coordinates=tuple(current_ring),
                intent=TraversalSegmentIntent.LOCAL_TRAVERSE,
            )
        )
    return tuple(segments)


def _perimeter_segments(
    *,
    coordinate_domain: WorldMapCoordinateDomain,
    bounds: WorldMapBounds,
    stride: ResolvedTraversalStride,
    start_corner: WorldMapTraversalCorner,
    rotation: TraversalRotation,
) -> tuple[WorldMapTraversalRouteSegment, ...]:
    """Builds one deterministic perimeter traversal broken into ordered edge segments."""

    edge_specs = _ordered_perimeter_edge_specs(start_corner=start_corner, rotation=rotation)
    first_coordinate: tuple[int, int] | None = None
    previous_coordinate: tuple[int, int] | None = None
    segments: list[WorldMapTraversalRouteSegment] = []
    for edge, reverse in edge_specs:
        coordinates = _edge_coordinates(
            coordinate_domain=coordinate_domain,
            bounds=bounds,
            edge=edge,
            stride=stride,
            reverse=reverse,
        )
        if previous_coordinate is not None and coordinates and coordinates[0] == previous_coordinate:
            coordinates = coordinates[1:]
        if first_coordinate is None and coordinates:
            first_coordinate = coordinates[0]
        if previous_coordinate is not None and first_coordinate is not None and coordinates and coordinates[-1] == first_coordinate:
            coordinates = coordinates[:-1]
        if not coordinates:
            continue
        segments.append(
            _build_segment(
                segment_index=len(segments),
                coordinates=coordinates,
                intent=TraversalSegmentIntent.LOCAL_TRAVERSE,
            )
        )
        previous_coordinate = coordinates[-1]
    if not segments:
        raise SelectorResolutionError(
            "World-map perimeter traversal produced no addressable perimeter checkpoints.",
            bounds=bounds,
        )
    return tuple(segments)


def _shrinking_perimeter_segments(
    *,
    coordinate_domain: WorldMapCoordinateDomain,
    bounds: WorldMapBounds,
    stride: ResolvedTraversalStride,
    start_corner: WorldMapTraversalCorner,
    rotation: TraversalRotation,
    inset_x: int | None,
    inset_y: int | None,
) -> tuple[WorldMapTraversalRouteSegment, ...]:
    """Builds repeated inward perimeter loops until no valid addressable perimeter remains."""

    resolved_inset_x = stride.horizontal_stride_units if inset_x is None else inset_x
    resolved_inset_y = stride.vertical_stride_units if inset_y is None else inset_y
    if resolved_inset_x <= 0 or resolved_inset_y <= 0:
        raise SelectorResolutionError(
            "Shrinking perimeter traversal requires positive inset_x and inset_y values.",
            inset_x=resolved_inset_x,
            inset_y=resolved_inset_y,
        )
    segments: list[WorldMapTraversalRouteSegment] = []
    current_bounds: WorldMapBounds | None = bounds
    while current_bounds is not None:
        loop_segments = _perimeter_segments(
            coordinate_domain=coordinate_domain,
            bounds=current_bounds,
            stride=stride,
            start_corner=start_corner,
            rotation=rotation,
        )
        for segment in loop_segments:
            segments.append(
                WorldMapTraversalRouteSegment(
                    segment_index=len(segments),
                    polyline_vertices=segment.polyline_vertices,
                    start_coordinate=segment.start_coordinate,
                    end_coordinate=segment.end_coordinate,
                    traversal_segment_intent=TraversalSegmentIntent.LOCAL_TRAVERSE,
                    analyzed_checkpoint_coordinates=segment.analyzed_checkpoint_coordinates,
                )
            )
        current_bounds = _inset_bounds(
            current_bounds,
            inset_x=resolved_inset_x,
            inset_y=resolved_inset_y,
        )
    if not segments:
        raise SelectorResolutionError(
            "World-map shrinking perimeter traversal produced no addressable perimeter checkpoints.",
            bounds=bounds,
        )
    return tuple(segments)


def _edge_coordinates(
    *,
    coordinate_domain: WorldMapCoordinateDomain,
    bounds: WorldMapBounds,
    edge: WorldMapEdge,
    stride: ResolvedTraversalStride,
    reverse: bool,
) -> tuple[tuple[int, int], ...]:
    """Returns the ordered addressable coordinates for one perimeter edge."""

    if edge == WorldMapEdge.TOP:
        return coordinate_domain.addressable_coordinates_on_row(
            bounds=bounds,
            y=bounds.min_y,
            spacing=stride.horizontal_stride_units,
            reverse=reverse,
        )
    if edge == WorldMapEdge.BOTTOM:
        return coordinate_domain.addressable_coordinates_on_row(
            bounds=bounds,
            y=bounds.max_y,
            spacing=stride.horizontal_stride_units,
            reverse=reverse,
        )
    if edge == WorldMapEdge.RIGHT:
        return coordinate_domain.addressable_coordinates_on_column(
            bounds=bounds,
            x=bounds.max_x,
            spacing=stride.vertical_stride_units,
            reverse=reverse,
        )
    return coordinate_domain.addressable_coordinates_on_column(
        bounds=bounds,
        x=bounds.min_x,
        spacing=stride.vertical_stride_units,
        reverse=reverse,
    )


def _ordered_perimeter_edge_specs(
    *,
    start_corner: WorldMapTraversalCorner,
    rotation: TraversalRotation,
) -> tuple[tuple[WorldMapEdge, bool], ...]:
    """Returns the ordered perimeter-edge traversal specification for one corner and rotation."""

    clockwise_specs = {
        WorldMapTraversalCorner.UPPER_LEFT: (
            (WorldMapEdge.TOP, False),
            (WorldMapEdge.RIGHT, False),
            (WorldMapEdge.BOTTOM, True),
            (WorldMapEdge.LEFT, True),
        ),
        WorldMapTraversalCorner.UPPER_RIGHT: (
            (WorldMapEdge.RIGHT, False),
            (WorldMapEdge.BOTTOM, True),
            (WorldMapEdge.LEFT, True),
            (WorldMapEdge.TOP, False),
        ),
        WorldMapTraversalCorner.LOWER_RIGHT: (
            (WorldMapEdge.BOTTOM, True),
            (WorldMapEdge.LEFT, True),
            (WorldMapEdge.TOP, False),
            (WorldMapEdge.RIGHT, False),
        ),
        WorldMapTraversalCorner.LOWER_LEFT: (
            (WorldMapEdge.LEFT, True),
            (WorldMapEdge.TOP, False),
            (WorldMapEdge.RIGHT, False),
            (WorldMapEdge.BOTTOM, True),
        ),
    }
    if rotation == TraversalRotation.CLOCKWISE:
        return clockwise_specs[start_corner]
    counterclockwise_specs = {
        WorldMapTraversalCorner.UPPER_LEFT: (
            (WorldMapEdge.LEFT, False),
            (WorldMapEdge.BOTTOM, False),
            (WorldMapEdge.RIGHT, True),
            (WorldMapEdge.TOP, True),
        ),
        WorldMapTraversalCorner.UPPER_RIGHT: (
            (WorldMapEdge.TOP, True),
            (WorldMapEdge.LEFT, False),
            (WorldMapEdge.BOTTOM, False),
            (WorldMapEdge.RIGHT, True),
        ),
        WorldMapTraversalCorner.LOWER_RIGHT: (
            (WorldMapEdge.RIGHT, True),
            (WorldMapEdge.TOP, True),
            (WorldMapEdge.LEFT, False),
            (WorldMapEdge.BOTTOM, False),
        ),
        WorldMapTraversalCorner.LOWER_LEFT: (
            (WorldMapEdge.BOTTOM, False),
            (WorldMapEdge.RIGHT, True),
            (WorldMapEdge.TOP, True),
            (WorldMapEdge.LEFT, False),
        ),
    }
    return counterclockwise_specs[start_corner]


def _inset_bounds(bounds: WorldMapBounds, *, inset_x: int, inset_y: int) -> WorldMapBounds | None:
    """Returns the next inner rectangle or `None` when no rectangle remains."""

    min_x = bounds.min_x + inset_x
    min_y = bounds.min_y + inset_y
    max_x = bounds.max_x - inset_x
    max_y = bounds.max_y - inset_y
    if min_x > max_x or min_y > max_y:
        return None
    return WorldMapBounds(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


def _build_segment(
    *,
    segment_index: int,
    coordinates: tuple[tuple[int, int], ...],
    intent: TraversalSegmentIntent,
) -> WorldMapTraversalRouteSegment:
    """Returns one validated route segment from one ordered coordinate sequence."""

    if not coordinates:
        raise SelectorResolutionError(
            "World-map traversal segments require at least one coordinate.",
            segment_index=segment_index,
        )
    return WorldMapTraversalRouteSegment(
        segment_index=segment_index,
        polyline_vertices=coordinates,
        start_coordinate=coordinates[0],
        end_coordinate=coordinates[-1],
        traversal_segment_intent=intent,
        analyzed_checkpoint_coordinates=coordinates,
    )


def _expanding_ring_coordinates(
    *,
    bounds: WorldMapBounds,
    origin: tuple[int, int],
    spacing: int,
) -> Iterable[tuple[int, int]]:
    """Yields coordinates in deterministic expanding-ring order while staying inside the inclusive bounds."""

    yielded: set[tuple[int, int]] = set()
    clamped_origin = bounds.clamp(origin)
    yielded.add(clamped_origin)
    yield clamped_origin
    max_radius = max(
        abs(bounds.min_x - clamped_origin[0]),
        abs(bounds.max_x - clamped_origin[0]),
        abs(bounds.min_y - clamped_origin[1]),
        abs(bounds.max_y - clamped_origin[1]),
    )
    ring = spacing
    while ring <= max_radius:
        min_x = clamped_origin[0] - ring
        max_x = clamped_origin[0] + ring
        min_y = clamped_origin[1] - ring
        max_y = clamped_origin[1] + ring
        top_xs = range(min_x, max_x + 1, spacing)
        right_ys = range(min_y + spacing, max_y + 1, spacing)
        bottom_xs = range(max_x - spacing, min_x - 1, -spacing)
        left_ys = range(max_y - spacing, min_y, -spacing)
        for coordinate in (
            *((x, min_y) for x in top_xs),
            *((max_x, y) for y in right_ys),
            *((x, max_y) for x in bottom_xs),
            *((min_x, y) for y in left_ys),
        ):
            if not bounds.contains(coordinate) or coordinate in yielded:
                continue
            yielded.add(coordinate)
            yield coordinate
        ring += spacing
