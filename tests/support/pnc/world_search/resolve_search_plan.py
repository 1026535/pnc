"""Synthetic resolve_search_plan fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.world_map_search_contracts import (
    WorldMapMovementToolKind,
    WorldMapResolvedSearchPlan,
    WorldMapSearchRequest,
)
from pnc_automation.app.pnc.navigation.world_map_search_planning import resolve_world_map_search_plan

ALL_WORLD_MAP_MOVEMENT_TOOLS: frozenset[WorldMapMovementToolKind] = frozenset(WorldMapMovementToolKind)


def _resolve_search_plan(
    request: WorldMapSearchRequest,
    observation: Observation,
    *,
    supported_movement_tools: frozenset[WorldMapMovementToolKind] = ALL_WORLD_MAP_MOVEMENT_TOOLS,
) -> WorldMapResolvedSearchPlan:
    """Resolves one search request through the pure planning owner with explicit runtime capabilities."""

    surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
    return resolve_world_map_search_plan(
        request,
        surface,
        supported_movement_tools=supported_movement_tools,
    )
