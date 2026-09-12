"""Synthetic overview_marker_point_for_coordinate fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.world_map_overview_projection import (
    project_world_coordinate_to_overview_point,
)
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapCoordinateDomain

from tests.support.pnc.observations import make_visible



def _overview_marker_point_for_coordinate(coordinate: tuple[int, int]) -> tuple[int, int]:
    """Returns the synthetic overview marker point for one world coordinate in the shared test fixture."""

    return project_world_coordinate_to_overview_point(
        coordinate=coordinate,
        bounds=WorldMapCoordinateDomain.puzzles_and_conquest().bounds,
        map_region_bounds=make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION,
            x=20,
            y=40,
            width=160,
            height=120,
        ).bounds,
    )
