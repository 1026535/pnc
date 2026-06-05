"""Canonical world-map coordinate bounds, addressability, and distance helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pnc_automation.core.errors import SelectorResolutionError


@dataclass(frozen=True, slots=True)
class WorldMapBounds:
    """Defines one inclusive rectangular world-coordinate boundary."""

    min_x: int
    min_y: int
    max_x: int
    max_y: int

    def __post_init__(self) -> None:
        """Rejects invalid bounds before traversal planning consumes them."""

        if min(self.min_x, self.min_y, self.max_x, self.max_y) < 0:
            raise SelectorResolutionError(
                "World-map bounds must use non-negative coordinates.",
                min_x=self.min_x,
                min_y=self.min_y,
                max_x=self.max_x,
                max_y=self.max_y,
            )
        if self.max_x < self.min_x or self.max_y < self.min_y:
            raise SelectorResolutionError(
                "World-map bounds must use max coordinates greater than or equal to min coordinates.",
                min_x=self.min_x,
                min_y=self.min_y,
                max_x=self.max_x,
                max_y=self.max_y,
            )

    def contains(self, coordinate: tuple[int, int]) -> bool:
        """Returns whether the provided world coordinate lies inside the inclusive bounds."""

        return self.min_x <= coordinate[0] <= self.max_x and self.min_y <= coordinate[1] <= self.max_y

    def clamp(self, coordinate: tuple[int, int]) -> tuple[int, int]:
        """Clamps one coordinate into the inclusive bounds for area traversal, not point identity validation."""

        return (
            min(max(coordinate[0], self.min_x), self.max_x),
            min(max(coordinate[1], self.min_y), self.max_y),
        )

    def contains_bounds(self, bounds: "WorldMapBounds") -> bool:
        """Returns whether another inclusive bounds lies fully inside this bounds."""

        return (
            self.min_x <= bounds.min_x
            and self.min_y <= bounds.min_y
            and bounds.max_x <= self.max_x
            and bounds.max_y <= self.max_y
        )

    def clamp_bounds(self, bounds: "WorldMapBounds") -> "WorldMapBounds":
        """Clamps another inclusive bounds into this bounds for coverage truncation."""

        return WorldMapBounds(
            min_x=min(max(bounds.min_x, self.min_x), self.max_x),
            min_y=min(max(bounds.min_y, self.min_y), self.max_y),
            max_x=min(max(bounds.max_x, self.min_x), self.max_x),
            max_y=min(max(bounds.max_y, self.min_y), self.max_y),
        )


@dataclass(frozen=True, slots=True)
class WorldMapCoordinateDomain:
    """Defines the canonical addressable coordinate model for world-map search and magnifier movement."""

    bounds: WorldMapBounds
    addressable_sum_parity: int | None = None

    def __post_init__(self) -> None:
        """Rejects invalid coordinate-domain configuration before traversal planning consumes it."""

        if self.addressable_sum_parity is not None and self.addressable_sum_parity not in {0, 1}:
            raise SelectorResolutionError(
                "World-map coordinate domains require addressable_sum_parity to be 0, 1, or None.",
                addressable_sum_parity=self.addressable_sum_parity,
            )

    @classmethod
    def puzzles_and_conquest(cls) -> "WorldMapCoordinateDomain":
        """Returns the live Puzzles & Conquest kingdom coordinate domain."""

        return cls(
            bounds=WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023),
            addressable_sum_parity=0,
        )

    def contains(self, coordinate: tuple[int, int]) -> bool:
        """Returns whether one coordinate lies inside the known kingdom bounds."""

        return self.bounds.contains(coordinate)

    def contains_bounds(self, bounds: WorldMapBounds) -> bool:
        """Returns whether one search bounds lies inside the coordinate domain."""

        return self.bounds.contains_bounds(bounds)

    def clamp_bounds(self, bounds: WorldMapBounds) -> WorldMapBounds:
        """Clamps one search bounds into the known coordinate domain."""

        return self.bounds.clamp_bounds(bounds)

    def local_bounds_around(self, coordinate: tuple[int, int], *, radius: int) -> WorldMapBounds:
        """Returns one radius-based local bounds window clamped to the coordinate domain edges."""

        if radius < 0:
            raise SelectorResolutionError(
                "World-map local bounds require a non-negative radius.",
                radius=radius,
            )
        center = self.require_inside_bounds(coordinate)
        return WorldMapBounds(
            min_x=max(self.bounds.min_x, center[0] - radius),
            min_y=max(self.bounds.min_y, center[1] - radius),
            max_x=min(self.bounds.max_x, center[0] + radius),
            max_y=min(self.bounds.max_y, center[1] + radius),
        )

    def is_addressable(self, coordinate: tuple[int, int]) -> bool:
        """Returns whether one coordinate can be targeted directly by world-map search/magnifier tools."""

        if not self.bounds.contains(coordinate):
            return False
        if self.addressable_sum_parity is None:
            return True
        return (coordinate[0] + coordinate[1]) % 2 == self.addressable_sum_parity

    def require_inside_bounds(self, coordinate: tuple[int, int]) -> tuple[int, int]:
        """Returns the coordinate when it lies inside the known map domain, otherwise fails fast."""

        if not is_integer_pair(coordinate):
            raise SelectorResolutionError(
                "World-map coordinate validation requires one integer coordinate pair.",
                coordinate=coordinate,
            )
        if self.bounds.contains(coordinate):
            return coordinate
        raise SelectorResolutionError(
            "World-map coordinates must lie inside the configured coordinate domain.",
            coordinate=coordinate,
            domain_bounds=self.bounds,
        )

    def nearest_addressable_in_bounds(self, coordinate: tuple[int, int]) -> tuple[int, int]:
        """Returns the deterministic nearest addressable coordinate after validating map bounds."""

        in_bounds = self.require_inside_bounds(coordinate)
        if self.is_addressable(in_bounds):
            return in_bounds
        for radius in range(1, 3):
            candidates = [
                candidate
                for candidate in _coordinates_within_chebyshev_radius(in_bounds, radius=radius)
                if self.is_addressable(candidate)
            ]
            if candidates:
                return min(candidates, key=lambda candidate: self._addressable_snap_order_key(in_bounds, candidate))
        raise SelectorResolutionError(
            "World-map coordinate domain could not resolve a nearby addressable coordinate.",
            coordinate=coordinate,
            bounds=self.bounds,
        )

    def row_major_coordinates(self, *, bounds: WorldMapBounds, spacing: int) -> tuple[tuple[int, int], ...]:
        """Returns row-major checkpoints aligned to the domain's addressable coordinate grid."""

        self.require_bounds_inside(bounds)
        coordinates: set[tuple[int, int]] = set()
        for y in self.row_samples(bounds=bounds, spacing=spacing):
            for coordinate in self.addressable_coordinates_on_row(bounds=bounds, y=y, spacing=spacing):
                coordinates.add(coordinate)
        for corner in (
            (bounds.min_x, bounds.min_y),
            (bounds.max_x, bounds.min_y),
            (bounds.min_x, bounds.max_y),
            (bounds.max_x, bounds.max_y),
        ):
            addressable_corner = self.nearest_addressable_in_bounds(corner)
            if bounds.contains(addressable_corner):
                coordinates.add(addressable_corner)
        if not coordinates:
            raise SelectorResolutionError(
                "World-map search bounds do not contain any addressable coordinate pair.",
                bounds=bounds,
                domain_bounds=self.bounds,
            )
        return tuple(sorted(coordinates, key=lambda coordinate: (coordinate[1], coordinate[0])))

    def normalize_route_coordinates(
        self,
        coordinates: Iterable[tuple[int, int]],
        *,
        bounds: WorldMapBounds | None = None,
    ) -> tuple[tuple[int, int], ...]:
        """Normalizes generated route coordinates to addressable checkpoints while preserving first-seen order."""

        normalized: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for coordinate in coordinates:
            addressable = self.nearest_addressable_in_bounds(coordinate)
            if bounds is not None and not bounds.contains(addressable):
                continue
            if addressable in seen:
                continue
            seen.add(addressable)
            normalized.append(addressable)
        return tuple(normalized)

    def require_bounds_inside(self, bounds: WorldMapBounds) -> None:
        """Fails fast when a caller asks search to leave the known coordinate domain."""

        if self.contains_bounds(bounds):
            return
        raise SelectorResolutionError(
            "World-map search bounds must lie inside the configured coordinate domain.",
            bounds=bounds,
            domain_bounds=self.bounds,
        )

    def row_samples(self, *, bounds: WorldMapBounds, spacing: int) -> tuple[int, ...]:
        """Returns the deterministic y-samples used when traversing rows inside the bounds."""

        self.require_bounds_inside(bounds)
        values = set(_axis_samples(bounds.min_y, bounds.max_y, self._require_positive_spacing(spacing)))
        values.update(
            self.nearest_addressable_in_bounds(corner)[1]
            for corner in (
                (bounds.min_x, bounds.min_y),
                (bounds.max_x, bounds.min_y),
                (bounds.min_x, bounds.max_y),
                (bounds.max_x, bounds.max_y),
            )
            if bounds.contains(corner)
        )
        return tuple(sorted(values))

    def column_samples(self, *, bounds: WorldMapBounds, spacing: int) -> tuple[int, ...]:
        """Returns the deterministic x-samples used when traversing columns inside the bounds."""

        self.require_bounds_inside(bounds)
        values = set(_axis_samples(bounds.min_x, bounds.max_x, self._require_positive_spacing(spacing)))
        values.update(
            self.nearest_addressable_in_bounds(corner)[0]
            for corner in (
                (bounds.min_x, bounds.min_y),
                (bounds.max_x, bounds.min_y),
                (bounds.min_x, bounds.max_y),
                (bounds.max_x, bounds.max_y),
            )
            if bounds.contains(corner)
        )
        return tuple(sorted(values))

    def addressable_coordinates_on_row(
        self,
        *,
        bounds: WorldMapBounds,
        y: int,
        spacing: int,
        reverse: bool = False,
    ) -> tuple[tuple[int, int], ...]:
        """Returns the addressable coordinates available on one row in the requested traversal direction."""

        self.require_bounds_inside(bounds)
        if not bounds.min_y <= y <= bounds.max_y:
            raise SelectorResolutionError(
                "World-map row traversal requires the requested y to lie inside the bounds.",
                y=y,
                bounds=bounds,
            )
        x_step = self._same_axis_spacing(spacing)
        first_x = self._first_addressable_x(bounds=bounds, y=y)
        if first_x is None:
            return ()
        last_x = self._last_addressable_x(bounds=bounds, y=y)
        assert last_x is not None
        xs = list(range(first_x, last_x + 1, x_step))
        if xs[-1] != last_x:
            xs.append(last_x)
        ordered_xs = list(reversed(xs)) if reverse else xs
        return tuple((x, y) for x in ordered_xs if self.is_addressable((x, y)))

    def addressable_coordinates_on_column(
        self,
        *,
        bounds: WorldMapBounds,
        x: int,
        spacing: int,
        reverse: bool = False,
    ) -> tuple[tuple[int, int], ...]:
        """Returns the addressable coordinates available on one column in the requested traversal direction."""

        self.require_bounds_inside(bounds)
        if not bounds.min_x <= x <= bounds.max_x:
            raise SelectorResolutionError(
                "World-map column traversal requires the requested x to lie inside the bounds.",
                x=x,
                bounds=bounds,
            )
        y_step = self._same_axis_spacing(spacing)
        first_y = self._first_addressable_y(bounds=bounds, x=x)
        if first_y is None:
            return ()
        last_y = self._last_addressable_y(bounds=bounds, x=x)
        assert last_y is not None
        ys = list(range(first_y, last_y + 1, y_step))
        if ys[-1] != last_y:
            ys.append(last_y)
        ordered_ys = list(reversed(ys)) if reverse else ys
        return tuple((x, y) for y in ordered_ys if self.is_addressable((x, y)))

    def _same_axis_spacing(self, spacing: int) -> int:
        """Returns a spacing value that can advance across addressable coordinates on one fixed-axis line."""

        spacing = self._require_positive_spacing(spacing)

        if self.addressable_sum_parity is None:
            return spacing
        if spacing == 1:
            return 2
        return spacing if spacing % 2 == 0 else spacing + 1

    def _require_positive_spacing(self, spacing: int) -> int:
        """Returns the validated spacing used by addressable traversal helpers."""

        if spacing <= 0:
            raise SelectorResolutionError(
                "World-map traversal helpers require a positive spacing value.",
                spacing=spacing,
            )
        return spacing

    def _first_addressable_x(self, *, bounds: WorldMapBounds, y: int) -> int | None:
        """Returns the first addressable x-coordinate on one y row inside the bounds."""

        for x in range(bounds.min_x, bounds.max_x + 1):
            if self.is_addressable((x, y)):
                return x
        return None

    def _last_addressable_x(self, *, bounds: WorldMapBounds, y: int) -> int | None:
        """Returns the last addressable x-coordinate on one y row inside the bounds."""

        for x in range(bounds.max_x, bounds.min_x - 1, -1):
            if self.is_addressable((x, y)):
                return x
        return None

    def _first_addressable_y(self, *, bounds: WorldMapBounds, x: int) -> int | None:
        """Returns the first addressable y-coordinate on one x column inside the bounds."""

        for y in range(bounds.min_y, bounds.max_y + 1):
            if self.is_addressable((x, y)):
                return y
        return None

    def _last_addressable_y(self, *, bounds: WorldMapBounds, x: int) -> int | None:
        """Returns the last addressable y-coordinate on one x column inside the bounds."""

        for y in range(bounds.max_y, bounds.min_y - 1, -1):
            if self.is_addressable((x, y)):
                return y
        return None

    def _addressable_snap_order_key(
        self,
        requested: tuple[int, int],
        candidate: tuple[int, int],
    ) -> tuple[int, int, int, int, int, int, int]:
        """Returns the deterministic tie-breaker that mirrors observed magnifier coordinate correction."""

        return (
            coordinate_chebyshev_distance(requested, candidate),
            coordinate_manhattan_distance(requested, candidate),
            0 if candidate[1] == requested[1] and candidate[0] <= requested[0] else 1,
            0 if candidate[0] == requested[0] and candidate[1] <= requested[1] else 1,
            abs(candidate[0] - requested[0]),
            abs(candidate[1] - requested[1]),
            candidate[0],
            candidate[1],
        )


def coordinate_chebyshev_distance(start: tuple[int, int], end: tuple[int, int]) -> int:
    """Returns the Chebyshev distance between two world coordinates."""

    return max(abs(start[0] - end[0]), abs(start[1] - end[1]))


def coordinate_manhattan_distance(start: tuple[int, int], end: tuple[int, int]) -> int:
    """Returns the Manhattan distance between two world coordinates."""

    return abs(start[0] - end[0]) + abs(start[1] - end[1])


def is_integer_pair(value: object) -> bool:
    """Returns whether the provided value is one two-item integer tuple."""

    return isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], int) and isinstance(value[1], int)


def _axis_samples(min_value: int, max_value: int, spacing: int) -> tuple[int, ...]:
    """Returns inclusive axis samples with the maximum endpoint represented."""

    values = list(range(min_value, max_value + 1, spacing))
    if not values:
        return (max_value,)
    if values[-1] != max_value:
        values.append(max_value)
    return tuple(values)


def _coordinates_within_chebyshev_radius(
    center: tuple[int, int],
    *,
    radius: int,
) -> Iterable[tuple[int, int]]:
    """Yields coordinates around one center within a Chebyshev radius."""

    for y in range(center[1] - radius, center[1] + radius + 1):
        for x in range(center[0] - radius, center[0] + radius + 1):
            yield x, y
