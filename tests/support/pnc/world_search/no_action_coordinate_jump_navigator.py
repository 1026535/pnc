"""Synthetic NoActionCoordinateJumpNavigator fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapCoordinateJumpPlan,
    WorldMapCoordinateNavigator,
)



class _NoActionCoordinateJumpNavigator(WorldMapCoordinateNavigator):
    """Models a supported coordinate-jump runtime that reports the target is already focused."""

    def is_supported(self) -> bool:
        """Returns that the fake coordinate-jump primitive is available."""

        return True

    def plan_jump(self, *, target: tuple[int, int], current_observation: Observation) -> WorldMapCoordinateJumpPlan:
        """Returns a no-op plan so the search service must verify the current viewport."""

        del current_observation
        return WorldMapCoordinateJumpPlan(normalized_target_coordinate=target)
