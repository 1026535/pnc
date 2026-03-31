"""Generic image-space models shared across reusable vision services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Region:
    """Defines one rectangular image region."""

    x: int
    y: int
    width: int
    height: int

    def center(self) -> tuple[int, int]:
        """Returns the region midpoint in image coordinates."""

        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True, slots=True)
class Bounds:
    """Represents one rectangular image-space bounds object."""

    x: int
    y: int
    width: int
    height: int

    def center(self) -> tuple[int, int]:
        """Returns the bounds midpoint in image coordinates."""

        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True, slots=True)
class TemplateMatch:
    """Represents one template hit within a screenshot."""

    bounds: Bounds
    confidence: float

