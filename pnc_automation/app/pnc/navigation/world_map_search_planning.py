"""Deterministic world-map search planning and preview formatting, free of runtime composition."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialSurfaceObservation,
)
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapBounds
from pnc_automation.app.pnc.navigation.world_map_search_contracts import (
    WorldMapMapCorner,
    WorldMapMovementToolKind,
    WorldMapResolvedSearchPlan,
    WorldMapSearchOrigin,
    WorldMapSearchOriginKind,
    WorldMapSearchRequest,
    _object_coordinate,
    _require_map_bounds,
)
from pnc_automation.app.pnc.navigation.world_map_sweep import build_world_map_sweep_plan
from pnc_automation.app.pnc.navigation.world_map_traversal import (
    WorldMapSearchBoundaryKind,
    WorldMapTraversalActionFamily,
    WorldMapTraversalExecutionPlanner,
    WorldMapTraversalPlanner,
)
from pnc_automation.core.errors import SelectorResolutionError


def resolve_world_map_search_plan(
    request: WorldMapSearchRequest,
    surface: SpatialSurfaceObservation,
    *,
    supported_movement_tools: frozenset[WorldMapMovementToolKind],
    traversal_planner: WorldMapTraversalPlanner | None = None,
    traversal_execution_planner: WorldMapTraversalExecutionPlanner | None = None,
) -> WorldMapResolvedSearchPlan:
    """Resolves one request against an immutable world-map surface into a deterministic traversal plan."""

    planner = WorldMapTraversalPlanner() if traversal_planner is None else traversal_planner
    execution_planner = (
        WorldMapTraversalExecutionPlanner() if traversal_execution_planner is None else traversal_execution_planner
    )
    origin = _resolve_origin_coordinate(request=request, surface=surface)
    coverage_bounds = _resolve_coverage_bounds(request=request, origin_coordinate=origin)
    movement_tool = select_world_map_search_movement_tool(
        request=request,
        supported_movement_tools=supported_movement_tools,
    )
    route_plan = planner.build_route_plan(
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
    execution_plan = execution_planner.build_execution_plan(
        route_plan=route_plan,
        origin_coordinate=origin,
    )
    sweep_plan = build_world_map_sweep_plan(
        route_plan=route_plan,
        policy=request.sweep_policy,
    )
    first_step_movement_tool = resolve_world_map_movement_tool_for_action_family(
        request=request,
        action_family=execution_plan.steps[0].action_family,
        supported_movement_tools=supported_movement_tools,
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


def format_world_map_route_preview(
    plan: WorldMapResolvedSearchPlan,
    *,
    head: int = 5,
    tail: int = 5,
) -> dict[str, object]:
    """Builds one route-preview document suitable for dry-run auditing before live sweep execution."""

    validate_world_map_preview_limits(head=head, tail=tail)
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


def validate_world_map_preview_limits(*, head: int, tail: int) -> None:
    """Rejects non-positive route-preview checkpoint limits without runtime services."""

    if head <= 0 or tail <= 0:
        raise SelectorResolutionError(
            "World-map route preview requires positive head and tail sizes.",
            head=head,
            tail=tail,
        )


def select_world_map_search_movement_tool(
    *,
    request: WorldMapSearchRequest,
    supported_movement_tools: frozenset[WorldMapMovementToolKind],
) -> WorldMapMovementToolKind:
    """Returns the first allowed movement tool supported by the provided capability set."""

    for tool in request.movement_preferences.allowed_tools:
        if tool in supported_movement_tools:
            return tool
    raise SelectorResolutionError(
        "The requested world-map movement preferences cannot be satisfied by the current runtime.",
        allowed_tools=tuple(tool.value for tool in request.movement_preferences.allowed_tools),
    )


def resolve_world_map_movement_tool_for_action_family(
    *,
    request: WorldMapSearchRequest,
    action_family: WorldMapTraversalActionFamily,
    supported_movement_tools: frozenset[WorldMapMovementToolKind],
) -> WorldMapMovementToolKind:
    """Resolves movement per action family so non-local entry does not force local checkpoints to jump."""

    if action_family == WorldMapTraversalActionFamily.NON_LOCAL_DIRECT:
        for tool in (
            WorldMapMovementToolKind.COORDINATE_JUMP,
            WorldMapMovementToolKind.OVERVIEW_SEED,
            WorldMapMovementToolKind.SWIPE,
        ):
            if _movement_tool_allowed_for_step(request=request, tool=tool) and tool in supported_movement_tools:
                return tool
    for tool in request.movement_preferences.allowed_tools:
        if tool in supported_movement_tools:
            return tool
    raise SelectorResolutionError(
        "The requested world-map movement preferences cannot be satisfied by the current runtime.",
        allowed_tools=tuple(tool.value for tool in request.movement_preferences.allowed_tools),
        action_family=action_family.value,
    )


def _movement_tool_allowed_for_step(*, request: WorldMapSearchRequest, tool: WorldMapMovementToolKind) -> bool:
    """Returns whether a primitive is available to this step without broadening local checkpoint movement."""

    if tool in request.movement_preferences.allowed_tools:
        return True
    return request.boundary is not None and request.boundary.kind == WorldMapSearchBoundaryKind.FULL_MAP


def _resolve_origin_coordinate(
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


def _coordinate_for_corner(bounds: WorldMapBounds, corner: WorldMapMapCorner) -> tuple[int, int]:
    """Returns the exact coordinate implied by the requested map corner."""

    if corner == WorldMapMapCorner.UPPER_LEFT:
        return bounds.min_x, bounds.min_y
    if corner == WorldMapMapCorner.UPPER_RIGHT:
        return bounds.max_x, bounds.min_y
    if corner == WorldMapMapCorner.LOWER_LEFT:
        return bounds.min_x, bounds.max_y
    return bounds.max_x, bounds.max_y
