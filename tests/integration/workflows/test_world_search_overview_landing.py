"""World search overview landing: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapMovementPreferences,
    WorldMapMovementToolKind,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.domain.observation_policy import (
    ObservationArtifactKind,
    observation_artifact_selection,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.make_world_map_overview_observation import (
    _make_world_map_overview_observation,
)
from tests.support.pnc.world_search.overview_marker_point_for_coordinate import (
    _overview_marker_point_for_coordinate,
)
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchOverviewLandingTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search overview landing."""

    def test_execute_search_moves_with_overview_seed_and_verifies_landing(self) -> None:
        """Executes the full overview open-plus-recenter flow and proves the landed world-map coordinate."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_overview_observation(marker_point=_overview_marker_point_for_coordinate((0, 0))),
                _make_world_map_observation(10, 0),
            ]
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
                movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.OVERVIEW_SEED,)),
            ),
            label_prefix="overview_seed_move",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(result.visited_checkpoints[0].coordinate, (10, 0))
        self.assertEqual(
            observer.requests,
            [
                ObservationRequest.world_map_overview_follow_up(expected_coordinate=(0, 0)),
                ObservationRequest.world_map_overview_exit_follow_up(),
            ],
        )
        self.assertEqual(
            observer.artifact_selections,
            [
                frozenset(),
                observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            ],
        )

    def test_execute_search_rejects_overview_seed_when_landing_is_wrong(self) -> None:
        """Fails overview-assisted movement when the returned world-map viewport proves the wrong landing coordinate."""

        service, _observer = self._build_runtime_service(
            observations=[
                _make_world_map_overview_observation(marker_point=_overview_marker_point_for_coordinate((0, 0))),
                _make_world_map_observation(8, 0),
            ]
        )

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.OVERVIEW_SEED,)),
                ),
                label_prefix="overview_seed_wrong_landing",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["target_coordinate"], (10, 0))
        self.assertEqual(error.exception.details["current_coordinate"], (8, 0))
