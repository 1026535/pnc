"""World map swipe planning."""

from __future__ import annotations

import unittest

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeGesturePrimitive,
    SwipeAction,
    SwipeInputSource,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldCoordinate
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class WorldMapSwipePlanningTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves world map swipe planning."""

    def test_world_map_navigator_plans_one_coordinate_driven_swipe(self) -> None:
        """Uses the dedicated world-map navigator instead of screen-flow-owned swipe helpers."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=100,
                y=120,
            ),
        )

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            observation,
            WorldCoordinate(x=150, y=120),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "left")
        self.assertEqual(actions[0].duration_ms, 700)
        self.assertAlmostEqual(actions[0].start_y_ratio, 0.60)
        self.assertAlmostEqual(actions[0].end_y_ratio, 0.60)
        self.assertAlmostEqual(actions[0].start_x_ratio, 0.68)
        self.assertAlmostEqual(actions[0].end_x_ratio, 0.28)
        self.assertTrue(actions[0].observe_after)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_movement_follow_up())

    def test_world_map_navigator_prefers_native_diagonal_profile_when_both_axes_are_unresolved(self) -> None:
        """Uses the reviewed diagonal swipe profile directly instead of decomposing diagonal movement into cardinals."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=100,
                y=120,
            ),
        )

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            observation,
            WorldCoordinate(x=150, y=170),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up_left")
        self.assertEqual(actions[0].duration_ms, 700)
        self.assertAlmostEqual(actions[0].start_x_ratio, 0.68)
        self.assertAlmostEqual(actions[0].start_y_ratio, 0.72)
        self.assertAlmostEqual(actions[0].end_x_ratio, 0.28)
        self.assertAlmostEqual(actions[0].end_y_ratio, 0.28)
        self.assertIsNotNone(actions[0].start_x_ratio)
        self.assertIsNotNone(actions[0].end_x_ratio)
        self.assertTrue(actions[0].observe_after)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_movement_follow_up())

    def test_world_map_navigator_uses_live_backed_vertical_swipe_lane(self) -> None:
        """Keeps vertical world-map swipes on the reviewed X lane that moves reliably in live probing."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=100,
                y=120,
            ),
        )

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            observation,
            WorldCoordinate(x=100, y=170),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertAlmostEqual(actions[0].start_x_ratio, 0.46)
        self.assertAlmostEqual(actions[0].end_x_ratio, 0.46)
        self.assertAlmostEqual(actions[0].start_y_ratio, 0.70)
        self.assertAlmostEqual(actions[0].end_y_ratio, 0.30)

    def test_world_map_navigator_rejects_small_coordinate_jitter_as_meaningful_movement(self) -> None:
        """Carries stagnant movement across replans so tiny OCR drift cannot masquerade as a real world-map pan."""

        runtime_state: dict[str, object] = {}
        self.flows.world_map_navigator.plan_focus_coordinate(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.WORLD_MAP,
                    x=100,
                    y=100,
                ),
            ),
            WorldCoordinate(x=150, y=100),
            runtime_state=runtime_state,
        )

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.WORLD_MAP,
                    x=101,
                    y=100,
                ),
            ),
            WorldCoordinate(x=150, y=100),
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 1)
        navigation_state = runtime_state["world_map_navigation"]
        assert isinstance(navigation_state, dict)
        pending_swipe = navigation_state["pending_swipe"]
        assert isinstance(pending_swipe, dict)
        self.assertEqual(pending_swipe["stagnant_attempts"], 1)
        self.assertGreater(pending_swipe["horizontal_distance_ratio"], 0.10)

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.WORLD_MAP,
                    x=101,
                    y=100,
                ),
            ),
            WorldCoordinate(x=150, y=100),
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)

        with self.assertRaises(SelectorResolutionError):
            self.flows.world_map_navigator.plan_focus_coordinate(
                make_observation(
                    ScreenType.PNC_WORLD_MAP,
                    spatial_surface=make_spatial_surface(
                        SpatialSurfaceType.WORLD_MAP,
                        x=101,
                        y=100,
                    ),
                ),
                WorldCoordinate(x=150, y=100),
                runtime_state=runtime_state,
            )

    def test_world_map_navigator_keeps_correcting_when_horizontal_error_is_still_two_units(self) -> None:
        """Does not stop early on a residual two-unit horizontal miss, so exact-focus can issue a correction swipe."""

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.WORLD_MAP,
                    x=108,
                    y=100,
                ),
            ),
            WorldCoordinate(x=106, y=100),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "right")

    def test_world_map_navigator_uses_plain_input_source_for_reverse_horizontal_corrections(self) -> None:
        """Uses the reviewed plain-input right lane because live probing showed the small reverse quantum is asymmetric."""

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.WORLD_MAP,
                    x=108,
                    y=100,
                ),
            ),
            WorldCoordinate(x=100, y=100),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "right")
        self.assertEqual(actions[0].input_source, SwipeInputSource.DEFAULT)

    def test_world_map_navigator_can_emit_press_move_release_gestures(self) -> None:
        """Lets world-map movement opt into a desktop-like press-drag-release primitive without changing other flows."""

        planner = ScreenFlowPlanner()
        planner.world_map_navigator.gesture_primitive = SwipeGesturePrimitive.PRESS_MOVE_RELEASE

        actions = planner.world_map_navigator.plan_focus_coordinate(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.WORLD_MAP,
                    x=100,
                    y=100,
                ),
            ),
            WorldCoordinate(x=110, y=100),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].gesture_primitive, SwipeGesturePrimitive.PRESS_MOVE_RELEASE)

    def test_world_map_navigator_preserves_selected_duplicate_resource_identity(self) -> None:
        """Keeps the chosen world-map duplicate target instead of retargeting by a broad semantic query."""

        first = make_spatial_object(
            SpatialObjectKind.RESOURCE_NODE,
            name_text="Food Farm",
            metadata={"resource_type": "food"},
            action_point=(41, 51),
        )
        second = make_spatial_object(
            SpatialObjectKind.RESOURCE_NODE,
            name_text="Food Farm",
            metadata={"resource_type": "food"},
            action_point=(88, 99),
        )
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=253,
                y=447,
                objects=(first, second),
            ),
        )

        actions = self.flows.world_map_navigator.tap_visible_object(observation, second, reason="open_duplicate_food")

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].target_point, (88, 99))
