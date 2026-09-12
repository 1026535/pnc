"""Synthetic fixtures owned by pnc.spatial."""

from __future__ import annotations

from typing import Any

from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
)



def make_spatial_object(
    kind: SpatialObjectKind,
    *,
    name_text: str | None = None,
    relationship: SpatialObjectRelationship = SpatialObjectRelationship.UNKNOWN,
    kingdom: str | None = None,
    level: int | None = None,
    metadata: dict[str, Any] | None = None,
    action_point: tuple[int, int] = (50, 50),
    viewport_offset: tuple[int, int] | None = None,
    viewport_offset_ratio: tuple[float, float] | None = None,
    estimated_world_coordinate: tuple[int, int] | None = None,
    confirmed_world_coordinate: tuple[int, int] | None = None,
) -> DetectedSpatialObject:
    """Builds a spatial object with deterministic bounds for tests."""

    return DetectedSpatialObject(
        kind=kind,
        bounds=Bounds(x=40, y=40, width=20, height=20),
        relationship=relationship,
        name_text=name_text,
        kingdom=kingdom,
        level=level,
        action_point=action_point,
        viewport_offset=viewport_offset,
        viewport_offset_ratio=viewport_offset_ratio,
        estimated_world_coordinate=estimated_world_coordinate,
        confirmed_world_coordinate=confirmed_world_coordinate,
        metadata=metadata or {},
    )


def make_spatial_surface(
    surface_type: SpatialSurfaceType,
    *,
    objects: tuple[DetectedSpatialObject, ...] = (),
    x: int | None = None,
    y: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> SpatialSurfaceObservation:
    """Builds a spatial surface with deterministic viewport defaults for tests."""

    if surface_type == SpatialSurfaceType.WORLD_MAP:
        return SpatialSurfaceObservation(
            surface_type=surface_type,
            viewport=SpatialViewport(
                addressing_kind=SpatialViewportAddressingKind.COORDINATE_BAR,
                x=0 if x is None else x,
                y=0 if y is None else y,
            ),
            objects=objects,
            metadata={} if metadata is None else metadata,
        )
    return SpatialSurfaceObservation(
        surface_type=surface_type,
        viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
        objects=objects,
        metadata={} if metadata is None else metadata,
    )
