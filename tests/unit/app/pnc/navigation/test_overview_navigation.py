"""Overview navigation."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import TapPointAction
from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapBounds,
    WorldMapCoordinateNavigator,
    WorldMapMovementPreferences,
    WorldMapMovementToolKind,
    WorldMapOverviewNavigator,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.observations import make_observation
from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.make_world_map_overview_observation import (
    _make_world_map_overview_observation,
)
from tests.support.pnc.world_search.overview_marker_point_for_coordinate import (
    _overview_marker_point_for_coordinate,
)
from tests.support.pnc.world_search.search_request import _search_request


class OverviewNavigationTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves overview navigation."""

    def test_overview_parse_support_does_not_enable_overview_seed(self) -> None:
        """Keeps parse-only overview support separate from overview-seed movement selection."""

        service = WorldMapSearchService(screen_flows=self.flows)
        service.overview_navigator = WorldMapOverviewNavigator(bounds_parsing_supported=True, movement_supported=False)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.OVERVIEW_SEED,)),
                ),
                _make_world_map_observation(0, 0),
            )

    def test_overview_navigator_parses_bounds_and_corner_marker_context(self) -> None:
        """Projects known-corner overview marker fixtures back into the world-map coordinate domain."""

        navigator = WorldMapOverviewNavigator()

        upper_left = navigator.parse_context(_make_world_map_overview_observation(marker_point=(20, 40)))
        lower_right = navigator.parse_context(_make_world_map_overview_observation(marker_point=(179, 159)))

        self.assertEqual(navigator.resolve_world_bounds(_make_world_map_overview_observation(marker_point=(100, 100))), WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023))
        self.assertEqual(upper_left.current_viewport_coordinate, (0, 0))
        self.assertEqual(lower_right.current_viewport_coordinate, (511, 1023))

    def test_overview_navigator_open_follow_up_carries_current_coordinate_hint(self) -> None:
        """Carries the current world coordinate into the overview follow-up so live marker detection can prefer the expected cluster."""

        navigator = WorldMapOverviewNavigator()
        observation = _make_world_map_observation(256, 512)

        actions = navigator.plan_open(observation)

        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.world_map_overview_follow_up(expected_coordinate=(256, 512)),
        )

    def test_overview_navigator_open_follow_up_keeps_coordinate_hint_optional(self) -> None:
        """Keeps overview opening usable when the map surface is proven but its coordinate bar is temporarily unreadable."""

        navigator = WorldMapOverviewNavigator()
        observation = _make_world_map_observation(0, 0, coordinate_addressable=False)

        actions = navigator.plan_open(observation)

        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_overview_follow_up())

    def test_coordinate_jump_plan_does_not_require_current_coordinate_for_non_noop_move(self) -> None:
        """Keeps coordinate-dialog planning available when the world map is proven but the viewport coordinate is unavailable."""

        navigator = WorldMapCoordinateNavigator()

        plan = navigator.plan_jump(
            target=(10, 0),
            current_observation=_make_world_map_observation(0, 0, coordinate_addressable=False),
        )

        self.assertTrue(plan.requires_execution)
        self.assertIsNotNone(plan.open_action)

    def test_overview_navigator_projects_interior_marker_and_recenter_click(self) -> None:
        """Uses the same marker calibration for interior parse evidence and click-to-recenter planning."""

        navigator = WorldMapOverviewNavigator()
        marker_point = _overview_marker_point_for_coordinate((256, 512))
        context = navigator.parse_context(_make_world_map_overview_observation(marker_point=marker_point))
        actions = navigator.plan_recenter(
            _make_world_map_overview_observation(marker_point=marker_point),
            target_coordinate=(256, 512),
        )

        self.assertLessEqual(abs(context.current_viewport_coordinate[0] - 256), 1)
        self.assertLessEqual(abs(context.current_viewport_coordinate[1] - 512), 4)
        self.assertIsInstance(actions[0], TapPointAction)

    def test_overview_navigator_recenter_uses_dedicated_click_region(self) -> None:
        """Projects recenter clicks through the reviewed click region instead of the tighter marker-projection region."""

        navigator = WorldMapOverviewNavigator()
        observation = _make_world_map_overview_observation(
            marker_point=(100, 100),
            recenter_region_bounds=(0, 0, 200, 200),
        )

        actions = navigator.plan_recenter(observation, target_coordinate=(511, 0))

        self.assertEqual((actions[0].x, actions[0].y), (199, 0))

    def test_overview_navigator_resolves_bounds_without_marker(self) -> None:
        """Keeps parse-only overview bounds support independent from temporary marker-detection failures."""

        navigator = WorldMapOverviewNavigator()

        bounds = navigator.resolve_world_bounds(_make_world_map_overview_observation(marker_point=None))

        self.assertEqual(bounds, WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023))

    def test_overview_navigator_context_requires_marker(self) -> None:
        """Fails marker-aware context parsing when the viewport marker is absent from the overview evidence."""

        navigator = WorldMapOverviewNavigator()

        with self.assertRaises(SelectorResolutionError):
            navigator.parse_context(_make_world_map_overview_observation(marker_point=None))

    def test_overview_navigator_distinguishes_close_recenter_and_kingdom_list_exit_paths(self) -> None:
        """Keeps the three reviewed overview exits on distinct declarative plans."""

        navigator = WorldMapOverviewNavigator()
        observation = _make_world_map_overview_observation(marker_point=(100, 100))

        close_actions = navigator.plan_close_in_place(observation)
        kingdom_list_actions = navigator.plan_open_kingdom_list(observation)

        self.assertEqual(close_actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON)
        self.assertEqual(kingdom_list_actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON)

    def test_overview_close_and_kingdom_list_paths_do_not_require_marker_parse(self) -> None:
        """Keeps non-recenter overview exits usable even when marker parsing evidence is temporarily absent."""

        navigator = WorldMapOverviewNavigator()
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP_OVERVIEW,
            visible_ids=(
                UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,
                UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON,
            ),
        )

        close_actions = navigator.plan_close_in_place(observation)
        kingdom_list_actions = navigator.plan_open_kingdom_list(observation)

        self.assertEqual(close_actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON)
        self.assertEqual(kingdom_list_actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON)
