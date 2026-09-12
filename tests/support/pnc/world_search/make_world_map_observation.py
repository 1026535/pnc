"""Synthetic make_world_map_observation fixture."""

from __future__ import annotations

from pathlib import Path

from pnc_automation.app.pnc.domain.observation import (
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_surface



def _make_world_map_observation(
    x: int,
    y: int,
    *,
    objects: tuple[object, ...] = (),
    coordinate_addressable: bool = True,
    artifact_path: Path | None = None,
) -> object:
    """Builds one synthetic world-map observation with the requested viewport and objects."""

    if coordinate_addressable:
        spatial_surface = make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=x,
            y=y,
            objects=objects,
            metadata={"coordinate_text": f"X:{x} Y:{y}"},
        )
    else:
        spatial_surface = SpatialSurfaceObservation(
            surface_type=SpatialSurfaceType.WORLD_MAP,
            viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
            objects=objects,
        )
    return make_observation(
        ScreenType.PNC_WORLD_MAP,
        visible_ids=(
            UiElementId.PNC_WORLD_HOME_NAV,
            UiElementId.PNC_WORLD_SEARCH_BUTTON,
            UiElementId.PNC_WORLD_EXPAND_BUTTON,
        ),
        spatial_surface=spatial_surface,
        artifact_path=artifact_path,
    )
