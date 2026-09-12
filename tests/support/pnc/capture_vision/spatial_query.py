"""Synthetic spatial_query fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)



def _spatial_query(
    *,
    surface_type: SpatialSurfaceType,
    kind: SpatialObjectKind,
    relationship: SpatialObjectRelationship | None = None,
    name_text: str | None = None,
    alliance_tag: str | None = None,
    kingdom: str | None = None,
    level: int | None = None,
    metadata_key: str | None = None,
    metadata_value: object | None = None,
) -> SpatialObjectQuery:
    """Builds one typed spatial-object query for observation assertions."""

    return SpatialObjectQuery(
        surface_type=surface_type,
        kind=kind,
        relationship=relationship,
        name_text=name_text,
        alliance_tag=alliance_tag,
        kingdom=kingdom,
        level=level,
        metadata_key=metadata_key,
        metadata_value=metadata_value,
    )
