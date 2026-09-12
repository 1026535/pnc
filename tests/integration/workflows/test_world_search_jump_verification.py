"""World search jump verification: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
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

from tests.support.pnc.observations import make_observation
from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.fake_coordinate_jump_navigator import (
    _FakeCoordinateJumpNavigator,
)
from tests.support.pnc.world_search.no_action_coordinate_jump_navigator import (
    _NoActionCoordinateJumpNavigator,
)
from tests.support.pnc.world_search.make_coordinate_dialog_observation import (
    _make_coordinate_dialog_observation,
)
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchJumpVerificationTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search jump verification."""

    def test_execute_search_fails_coordinate_jump_with_live_status_banner(self) -> None:
        """Surfaces the magnifier invalid-coordinate banner instead of retrying into a generic world-map parse error."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_coordinate_dialog_observation(157, 10, 0),
                _make_coordinate_dialog_observation(157, 10, 0, status_banner_text="Invalid coordinates"),
                _make_coordinate_dialog_observation(157, 10, 0, status_banner_text="Invalid coordinates"),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
                ),
                label_prefix="coordinate_jump_invalid",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["target_coordinate"], (10, 0))
        self.assertEqual(error.exception.details["status_banner"], "Invalid coordinates")
        self.assertEqual(
            observer.requests,
            [
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_jump_follow_up(),
                ObservationRequest.full_runtime_default(),
            ],
        )
        self.assertTrue(observer.labels[-1].endswith("coordinate_jump_invalid_move_0_failure"))

    def test_execute_search_fails_no_action_coordinate_jump_when_not_at_target(self) -> None:
        """Verifies a no-op coordinate jump before treating the current viewport as the checkpoint."""

        service, _observer = self._build_runtime_service(observations=[])
        service.coordinate_navigator = _NoActionCoordinateJumpNavigator()

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
                ),
                label_prefix="coordinate_jump_no_action_wrong",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["target_coordinate"], (10, 0))
        self.assertEqual(error.exception.details["current_coordinate"], (0, 0))

    def test_execute_search_fails_coordinate_jump_that_lands_at_wrong_coordinate(self) -> None:
        """Rejects coordinate-dialog movement when the resulting viewport proves a different coordinate."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_coordinate_dialog_observation(157, 10, 0),
                _make_world_map_observation(8, 0),
                _make_world_map_observation(8, 0),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
                ),
                label_prefix="coordinate_jump_wrong_landing",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["target_coordinate"], (10, 0))
        self.assertEqual(error.exception.details["current_coordinate"], (8, 0))
        self.assertEqual(observer.artifact_selections[-1], observation_artifact_selection(ObservationArtifactKind.SCREENSHOT))
        self.assertTrue(observer.labels[-1].endswith("coordinate_jump_wrong_landing_move_0_failure"))

    def test_execute_search_fails_coordinate_jump_when_landing_lacks_world_map_surface(self) -> None:
        """Requires a proven world-map surface before checkpoint ingestion after coordinate-dialog movement."""

        service, _observer = self._build_runtime_service(
            observations=[
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_coordinate_dialog_observation(157, 10, 0),
                make_observation(ScreenType.PNC_WORLD_MAP),
                make_observation(ScreenType.PNC_WORLD_MAP),
                make_observation(ScreenType.PNC_WORLD_MAP),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        with self.assertRaises(SelectorResolutionError):
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
                ),
                label_prefix="coordinate_jump_missing_surface",
                start_observation=_make_world_map_observation(0, 0),
            )

    def test_execute_search_accepts_coordinate_jump_landing_at_normalized_target(self) -> None:
        """Verifies coordinate-jump landings against the normalized in-domain checkpoint coordinate."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_coordinate_dialog_observation(157, 510, 0),
                _make_world_map_observation(510, 0),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.explicit_coordinate((511, 0)),
                checkpoint_spacing=10,
                movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
            ),
            label_prefix="coordinate_jump_normalized_landing",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(result.visited_checkpoints[0].coordinate, (510, 0))
        self.assertEqual(
            observer.artifact_selections,
            [
                frozenset(),
                frozenset(),
                observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            ],
        )
