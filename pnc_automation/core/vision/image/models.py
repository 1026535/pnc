"""Generic image-space models shared across reusable vision services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bounds:
    """Represents one rectangular image-space bounds object."""

    x: int
    y: int
    width: int
    height: int

    def contains_bounds(self, candidate: Bounds) -> bool:
        """Return whether a positive rectangle is wholly inside this rectangle."""

        return (
            self.width > 0 and self.height > 0
            and candidate.width > 0 and candidate.height > 0
            and self.x <= candidate.x and self.y <= candidate.y
            and candidate.x + candidate.width <= self.x + self.width
            and candidate.y + candidate.height <= self.y + self.height
        )

    def contains_point(self, point: tuple[int, int]) -> bool:
        """Return whether a pixel lies inside this half-open rectangle."""

        x, y = point
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def center(self) -> tuple[int, int]:
        """Returns the bounds midpoint in image coordinates."""

        return (self.x + self.width // 2, self.y + self.height // 2)


Region = Bounds
"""Vocabulary alias for image-region APIs that still conceptually operate on crops."""


@dataclass(frozen=True, slots=True)
class TemplateMatch:
    """Represents one template hit within a screenshot."""

    bounds: Bounds
    confidence: float
