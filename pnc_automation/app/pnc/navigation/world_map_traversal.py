"""Canonical world-map traversal pattern generation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import (
    WorldMapBounds,
    WorldMapCoordinateDomain,
    coordinate_chebyshev_distance,
    coordinate_manhattan_distance,
    is_integer_pair,
)
from pnc_automation.core.errors import SelectorResolutionError


class WorldMapSearchPatternKind(StrEnum):
    """Defines the canonical checkpoint visitation order families for world-map search."""

    ROW_MAJOR_SWEEP = "row_major_sweep"
    EXPANDING_RING = "expanding_ring"
    EDGE_BAND_SWEEP = "edge_band_sweep"


class WorldMapEdge(StrEnum):
    """Defines one exact world-map edge."""

    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class WorldMapSearchBoundaryKind(StrEnum):
    """Defines the allowed coverage region for one search request."""

    FULL_MAP = "full_map"
    RADIUS_FROM_ORIGIN = "radius_from_origin"
    RECTANGLE = "rectangle"
    EDGE_BAND = "edge_band"


@dataclass(frozen=True, slots=True)
class WorldMapTraversalEdgeBand:
    """Carries the edge-band traversal payload without depending on search-request classes."""

    edges: tuple[WorldMapEdge, ...]
    band_width_units: int

    def __post_init__(self) -> None:
        """Rejects malformed edge-band traversal payloads before route generation."""

        if not self.edges:
            raise SelectorResolutionError("Edge-band traversal requires at least one edge.")
        if len(frozenset(self.edges)) != len(self.edges):
            raise SelectorResolutionError("Edge-band traversal must not repeat edges.", edges=self.edges)
        if self.band_width_units <= 0:
            raise SelectorResolutionError(
                "Edge-band traversal requires a positive band_width_units value.",
                band_width_units=self.band_width_units,
            )


@dataclass(frozen=True, slots=True)
class WorldMapTraversalCheckpoint:
    """Defines one deterministic checkpoint coordinate in the planned world-map traversal route."""

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


@dataclass(slots=True)
class WorldMapTraversalPlanner:
    """Converts resolved traversal inputs into a deterministic ordered checkpoint route."""

    def build_route(
        self,
        *,
        pattern_kind: WorldMapSearchPatternKind,
        coordinate_domain: WorldMapCoordinateDomain,
        origin_coordinate: tuple[int, int],
        coverage_bounds: WorldMapBounds,
        spacing: int,
        edge_band: WorldMapTraversalEdgeBand | None = None,
    ) -> tuple[WorldMapTraversalCheckpoint, ...]:
        """Returns the deterministic route implied by the pattern, origin, and resolved coverage bounds."""

        if spacing <= 0:
            raise SelectorResolutionError(
                "World-map traversal planning requires a positive checkpoint spacing.",
                checkpoint_spacing=spacing,
            )
        coordinates: tuple[tuple[int, int], ...]
        if pattern_kind == WorldMapSearchPatternKind.ROW_MAJOR_SWEEP:
            if edge_band is not None:
                raise SelectorResolutionError("Row-major traversal must not receive edge-band payloads.")
            coordinates = coordinate_domain.row_major_coordinates(bounds=coverage_bounds, spacing=spacing)
        elif pattern_kind == WorldMapSearchPatternKind.EXPANDING_RING:
            if edge_band is not None:
                raise SelectorResolutionError("Expanding-ring traversal must not receive edge-band payloads.")
            coordinates = coordinate_domain.normalize_route_coordinates(
                _expanding_ring_coordinates(bounds=coverage_bounds, origin=origin_coordinate, spacing=spacing),
                bounds=coverage_bounds,
            )
        elif pattern_kind == WorldMapSearchPatternKind.EDGE_BAND_SWEEP:
            if edge_band is None:
                raise SelectorResolutionError(
                    "Edge-band sweep route generation requires one edge-band payload.",
                    pattern=pattern_kind.value,
                )
            coordinates = coordinate_domain.normalize_route_coordinates(
                _edge_band_coordinates(
                    map_bounds=coverage_bounds,
                    spacing=spacing,
                    edge_band=edge_band,
                    origin_coordinate=origin_coordinate,
                    coordinate_domain=coordinate_domain,
                ),
                bounds=coverage_bounds,
            )
        else:
            raise SelectorResolutionError("Unsupported world-map search pattern.", pattern=pattern_kind.value)
        if not coordinates:
            raise SelectorResolutionError(
                "World-map traversal planning produced no addressable checkpoints.",
                pattern=pattern_kind.value,
                coverage_bounds=coverage_bounds,
            )
        return tuple(
            WorldMapTraversalCheckpoint(
                coordinate=coordinate,
                distance_from_origin=coordinate_chebyshev_distance(origin_coordinate, coordinate),
                route_index=index,
            )
            for index, coordinate in enumerate(coordinates)
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


def _edge_band_coordinates(
    *,
    map_bounds: WorldMapBounds,
    spacing: int,
    edge_band: WorldMapTraversalEdgeBand,
    origin_coordinate: tuple[int, int],
    coordinate_domain: WorldMapCoordinateDomain,
) -> Iterable[tuple[int, int]]:
    """Yields deterministic edge-band coordinates ordered from the resolved request origin."""

    coordinates = [
        coordinate
        for coordinate in coordinate_domain.row_major_coordinates(bounds=map_bounds, spacing=spacing)
        if _coordinate_in_edge_band(coordinate, map_bounds=map_bounds, edge_band=edge_band)
    ]
    yield from sorted(coordinates, key=lambda coordinate: _edge_band_coordinate_order_key(coordinate, origin_coordinate))


def _coordinate_in_edge_band(
    coordinate: tuple[int, int],
    *,
    map_bounds: WorldMapBounds,
    edge_band: WorldMapTraversalEdgeBand,
) -> bool:
    """Returns whether the coordinate lies inside the configured edge band."""

    for edge in edge_band.edges:
        if edge == WorldMapEdge.LEFT and coordinate[0] <= map_bounds.min_x + edge_band.band_width_units:
            return True
        if edge == WorldMapEdge.RIGHT and coordinate[0] >= map_bounds.max_x - edge_band.band_width_units:
            return True
        if edge == WorldMapEdge.TOP and coordinate[1] <= map_bounds.min_y + edge_band.band_width_units:
            return True
        if edge == WorldMapEdge.BOTTOM and coordinate[1] >= map_bounds.max_y - edge_band.band_width_units:
            return True
    return False


def _edge_band_coordinate_order_key(
    coordinate: tuple[int, int],
    origin_coordinate: tuple[int, int],
) -> tuple[int, int, int]:
    """Returns the deterministic origin-aware ordering key for one edge-band checkpoint."""

    return coordinate_manhattan_distance(origin_coordinate, coordinate), coordinate[1], coordinate[0]
