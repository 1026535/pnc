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

    if not _bounds_contains_point(map_region_bounds, marker_point):
        raise SelectorResolutionError(
            "Overview marker calibration requires one marker inside the overview map region.",
            marker_point=marker_point,
            map_region_bounds=map_region_bounds,
        )
    relative_x = _relative_point_within_span(
        point=marker_point[0],
        origin=map_region_bounds.x,
        span=map_region_bounds.width,
    )
    relative_y = _relative_point_within_span(
        point=marker_point[1],
        origin=map_region_bounds.y,
        span=map_region_bounds.height,
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
        _point_within_span(
            origin=map_region_bounds.x,
            span=map_region_bounds.width,
            relative=relative_x,
        ),
        _point_within_span(
            origin=map_region_bounds.y,
            span=map_region_bounds.height,
            relative=relative_y,
        ),
    )


def _bounds_contains_point(bounds: Bounds, point: tuple[int, int]) -> bool:
    """Returns whether one point lies inside the bounds' pixel span."""

    return (
        bounds.x <= point[0] < bounds.x + max(1, bounds.width)
        and bounds.y <= point[1] < bounds.y + max(1, bounds.height)
    )


def _relative_point_within_span(*, point: int, origin: int, span: int) -> float:
    """Returns the normalized relative position for one point inside a span-sized pixel interval."""

    pixel_span = _inclusive_pixel_span(span)
    if pixel_span == 0:
        return 0.0
    return (point - origin) / pixel_span


def _point_within_span(*, origin: int, span: int, relative: float) -> int:
    """Returns one in-bounds pixel position for a normalized relative coordinate."""

    return origin + round(relative * _inclusive_pixel_span(span))


def _inclusive_pixel_span(span: int) -> int:
    """Returns the distance between the first and last valid pixel in one span-sized interval."""

    return max(0, max(1, span) - 1)
