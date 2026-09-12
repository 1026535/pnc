"""Synthetic search_request fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.navigation.world_map_search import (
    TraversalStridePolicy,
    WorldMapMovementPreferences,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchStopPolicy,
)
from pnc_automation.app.pnc.navigation.world_map_sweep import WorldMapSweepPolicy



def _search_request(
    *,
    matcher: object,
    pattern: WorldMapSearchPattern,
    checkpoint_spacing: int,
    origin: WorldMapSearchOrigin | None = None,
    boundary: WorldMapSearchBoundary | None = None,
    movement_preferences: WorldMapMovementPreferences | None = None,
    stop_policy: WorldMapSearchStopPolicy | None = None,
    sweep_policy: WorldMapSweepPolicy | None = None,
) -> object:
    """Builds one search request with concise defaults for tests."""

    from pnc_automation.app.pnc.navigation.world_map_search import WorldMapSearchRequest

    return WorldMapSearchRequest(
        matcher=matcher,
        stop_policy=WorldMapSearchStopPolicy() if stop_policy is None else stop_policy,
        pattern=pattern,
        traversal_stride_policy=TraversalStridePolicy.symmetric(checkpoint_spacing),
        origin=origin,
        boundary=boundary,
        movement_preferences=WorldMapMovementPreferences() if movement_preferences is None else movement_preferences,
        sweep_policy=WorldMapSweepPolicy.debug_exact_checkpoint() if sweep_policy is None else sweep_policy,
    )
