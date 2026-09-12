"""Synthetic CountingScreenFlowPlanner fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner



class _CountingScreenFlowPlanner(ScreenFlowPlanner):
    """Tracks root world-map readiness calls while preserving normal screen-flow behavior."""

    def __init__(self) -> None:
        """Initializes the counter and base planner dependencies."""

        super().__init__()
        self.ensure_world_map_ready_calls = 0

    def ensure_world_map_ready(self, observation: object) -> list[object]:
        """Counts calls to the root readiness seam."""

        self.ensure_world_map_ready_calls += 1
        return super().ensure_world_map_ready(observation)
