"""Synthetic FakeCoordinateJumpNavigator fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.action_requests import KeyEventAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapCoordinateJumpPlan,
    WorldMapCoordinateNavigator,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest



class _FakeCoordinateJumpNavigator(WorldMapCoordinateNavigator):
    """Plans one synthetic coordinate jump action for search error-handling tests."""

    def is_supported(self) -> bool:
        """Returns that the fake coordinate-jump primitive is available."""

        return True

    def plan_jump(self, *, target: tuple[int, int], current_observation: Observation) -> WorldMapCoordinateJumpPlan:
        """Returns one synthetic staged jump plan for search error-handling tests."""

        del current_observation
        return WorldMapCoordinateJumpPlan(
            normalized_target_coordinate=target,
            open_action=KeyEventAction(
                key_code="KEYCODE_ENTER",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            ),
            fill_actions=(
                KeyEventAction(
                    key_code="KEYCODE_ENTER",
                    observe_after=True,
                    follow_up_request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ),
            ),
            submit_action=KeyEventAction(
                key_code="KEYCODE_ENTER",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_coordinate_jump_follow_up(),
            ),
        )
