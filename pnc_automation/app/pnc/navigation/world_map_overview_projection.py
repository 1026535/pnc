"""Shared projection helpers for the world-map overview surface."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import Bounds
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapBounds
from pnc_automation.core.errors import SelectorResolutionError


def project_overview_marker_to_world_coordinate(
    *,
    marker_point: tuple[int, int],
    map_region_bounds: Bounds,
    bounds: WorldMapBounds,
) -> tuple[int, int]:
    """Projects one overview marker point back into inclusive world coordinates."""

    width = max(1, map_region_bounds.width)
    height = max(1, map_region_bounds.height)
    relative_x = (marker_point[0] - map_region_bounds.x) / width
    relative_y = (marker_point[1] - map_region_bounds.y) / height
    if not 0 <= relative_x <= 1 or not 0 <= relative_y <= 1:
        raise SelectorResolutionError(
            "Overview marker calibration requires one marker inside the overview map region.",
            marker_point=marker_point,
            map_region_bounds=map_region_bounds,
        )
    return (
        bounds.min_x + round(relative_x * (bounds.max_x - bounds.min_x)),
        bounds.min_y + round(relative_y * (bounds.max_y - bounds.min_y)),
    )


def project_world_coordinate_to_overview_point(
    *,
    coordinate: tuple[int, int],
    bounds: WorldMapBounds,
    map_region_bounds: Bounds,
) -> tuple[int, int]:
    """Projects one inclusive world coordinate into the overview map region."""

    relative_x = 0.0 if bounds.max_x == bounds.min_x else (coordinate[0] - bounds.min_x) / (bounds.max_x - bounds.min_x)
    relative_y = 0.0 if bounds.max_y == bounds.min_y else (coordinate[1] - bounds.min_y) / (bounds.max_y - bounds.min_y)
    if not 0 <= relative_x <= 1 or not 0 <= relative_y <= 1:
        raise SelectorResolutionError(
            "Overview recentering requires one coordinate inside the known world-map bounds.",
            coordinate=coordinate,
            bounds=bounds,
        )
    return (
        map_region_bounds.x + round(relative_x * map_region_bounds.width),
        map_region_bounds.y + round(relative_y * map_region_bounds.height),
    )
