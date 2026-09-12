"""World search entry: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapCoordinateDomain,
    WorldMapMovementToolKind,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchStopPolicy,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.fake_coordinate_jump_navigator import (
    _FakeCoordinateJumpNavigator,
)
from tests.support.pnc.world_search.make_coordinate_dialog_observation import (
    _make_coordinate_dialog_observation,
)
from tests.support.pnc.world_search.make_incomplete_coordinate_dialog_observation import (
    _make_incomplete_coordinate_dialog_observation,
)
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchEntryTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search entry."""

    def test_execute_full_map_entry_uses_coordinate_jump_then_local_swipe(self) -> None:
        """Keeps primitive dispatch per itinerary step so the entry jump does not force local checkpoints to jump."""

        domain = WorldMapCoordinateDomain.puzzles_and_conquest()
        service, observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_coordinate_dialog_observation(157, 334, 510),
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.full_map(domain.bounds),
                checkpoint_spacing=10,
                stop_policy=WorldMapSearchStopPolicy(max_checkpoints=2),
            ),
            label_prefix="full_map_entry_then_swipe",
            start_observation=_make_world_map_observation(334, 510),
        )

        self.assertEqual([checkpoint.coordinate for checkpoint in result.visited_checkpoints], [(0, 0), (10, 0)])
        self.assertEqual(len(session.swipes), 1)
        self.assertIsNotNone(result.execution_profile)
        assert result.execution_profile is not None
        profile_document = result.execution_profile.to_document()
        self.assertEqual(profile_document["first_step_movement_tool"], WorldMapMovementToolKind.COORDINATE_JUMP.value)
        self.assertEqual(profile_document["checkpoint_profiles"][0]["movement_tool"], "coordinate_jump")
        self.assertEqual(profile_document["checkpoint_profiles"][0]["movement_phase"], "non_local_entry")
        self.assertEqual(profile_document["checkpoint_profiles"][1]["movement_tool"], "swipe")
        self.assertEqual(profile_document["checkpoint_profiles"][1]["movement_phase"], "steady_state")
        self.assertEqual(
            observer.requests,
            [
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_jump_follow_up(),
                ObservationRequest.world_map_movement_proof_follow_up(),
            ],
        )

    def test_coordinate_jump_refreshes_dialog_once_when_field_state_is_transiently_missing(self) -> None:
        """Recovers the live dialog proof case where the screen is recognized but one zero field is absent."""

        domain = WorldMapCoordinateDomain.puzzles_and_conquest()
        service, observer, _session = self._build_runtime_service_bundle(
            observations=[
                _make_incomplete_coordinate_dialog_observation(157, x=334, y=None),
                _make_coordinate_dialog_observation(157, 334, 510),
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_world_map_observation(0, 0),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.full_map(domain.bounds),
                checkpoint_spacing=10,
                stop_policy=WorldMapSearchStopPolicy(max_checkpoints=1),
            ),
            label_prefix="coordinate_dialog_missing_field_refresh",
            start_observation=_make_world_map_observation(334, 510),
        )

        self.assertEqual([checkpoint.coordinate for checkpoint in result.visited_checkpoints], [(0, 0)])
        self.assertEqual(
            observer.requests,
            [
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_jump_follow_up(),
            ],
        )
        self.assertEqual(
            observer.labels[1],
            "coordinate_dialog_missing_field_refresh_move_0_open_dialog_refresh",
        )
