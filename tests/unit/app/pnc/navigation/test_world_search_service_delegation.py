"""World search service delegation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation import (
    world_map_search,
    world_map_search_contracts,
    world_map_search_planning,
)
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapSearchService
from pnc_automation.app.pnc.navigation.world_map_search_contracts import (
    WorldMapMovementPreferences,
    WorldMapMovementToolKind,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request
from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures


class WorldSearchServiceDelegationTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves world search service delegation."""

    def test_preview_rejects_nonpositive_limits_before_plan_resolution(self) -> None:
        """Keeps the direct service contract on the same pure limit validator."""

        service = WorldMapSearchService(screen_flows=self.flows)
        with patch.object(WorldMapSearchService, "resolve_plan") as resolve_plan:
            with self.assertRaises(SelectorResolutionError):
                service.preview_route(None, None, head=0, tail=1)  # type: ignore[arg-type]

        resolve_plan.assert_not_called()

    def test_resolve_plan_delegates_to_pure_owner_with_runtime_capabilities(self) -> None:
        """Forwards the observed surface, runtime capability set, and injected traversal planners."""

        service = WorldMapSearchService(screen_flows=self.flows)
        request = _search_request(
            matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
            pattern=WorldMapSearchPattern.row_major_sweep(),
            origin=WorldMapSearchOrigin.current_viewport(),
            boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
            checkpoint_spacing=10,
        )
        observation = _make_world_map_observation(0, 0)
        with patch.object(
            world_map_search, "resolve_world_map_search_plan",
            wraps=world_map_search_planning.resolve_world_map_search_plan,
        ) as resolver:
            result = service.resolve_plan(request, observation)

        self.assertIsInstance(result, world_map_search_contracts.WorldMapResolvedSearchPlan)
        self.assertIs(result.request, request)
        self.assertEqual(result.origin_coordinate, (0, 0))
        self.assertEqual([checkpoint.coordinate for checkpoint in result.route], [(0, 0), (10, 0)])
        resolver.assert_called_once()
        call = resolver.call_args
        self.assertIs(call.args[0], request)
        self.assertIs(call.args[1], observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP))
        self.assertEqual(
            call.kwargs["supported_movement_tools"],
            frozenset(WorldMapMovementToolKind),
        )
        self.assertIs(call.kwargs["traversal_planner"], service.traversal_planner)
        self.assertIs(call.kwargs["traversal_execution_planner"], service.traversal_execution_planner)

    def test_execution_rechecks_capabilities_after_the_plan_was_resolved(self) -> None:
        """A stored plan cannot retain a movement tool whose runtime support was removed."""

        service = WorldMapSearchService(screen_flows=self.flows)
        request = _search_request(
            matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
            pattern=WorldMapSearchPattern.row_major_sweep(),
            origin=WorldMapSearchOrigin.current_viewport(),
            boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
            checkpoint_spacing=10,
            movement_preferences=WorldMapMovementPreferences((
                WorldMapMovementToolKind.COORDINATE_JUMP, WorldMapMovementToolKind.SWIPE,
            )),
        )
        observation = _make_world_map_observation(0, 0)

        plan = service.resolve_plan(request, observation)
        self.assertEqual(plan.movement_tool, WorldMapMovementToolKind.COORDINATE_JUMP)
        service.coordinate_navigator.supported = False
        self.assertEqual(
            service._movement_tool_for_step(plan=plan, step=plan.execution_plan.steps[0]),
            WorldMapMovementToolKind.SWIPE,
        )

    def test_preview_delegates_real_plan_to_pure_formatter(self) -> None:
        """The runtime preview preserves the pure formatter's schema and requested limits."""

        service = WorldMapSearchService(screen_flows=self.flows)
        request = _search_request(
            matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
            pattern=WorldMapSearchPattern.row_major_sweep(),
            origin=WorldMapSearchOrigin.current_viewport(),
            boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(20, 0)),
            checkpoint_spacing=10,
        )
        observation = _make_world_map_observation(0, 0)
        with patch.object(
            world_map_search, "format_world_map_route_preview",
            wraps=world_map_search_planning.format_world_map_route_preview,
        ) as formatter:
            preview = service.preview_route(request, observation, head=1, tail=2)

        formatter.assert_called_once()
        plan = formatter.call_args.args[0]
        self.assertIsInstance(plan, world_map_search_contracts.WorldMapResolvedSearchPlan)
        self.assertEqual(formatter.call_args.kwargs, {"head": 1, "tail": 2})
        self.assertEqual(preview["checkpoint_count"], 3)
        self.assertEqual([item["coordinate"] for item in preview["head_checkpoints"]], [[0, 0]])
        self.assertEqual([item["coordinate"] for item in preview["tail_checkpoints"]], [[10, 0], [20, 0]])

    def test_legacy_world_map_search_symbols_are_neutral_module_objects(self) -> None:
        """Retains same-object compatibility aliases for every moved contract and planning symbol."""

        contracts_names = (
            "AllOfWorldMapSearchMatcher",
            "AnyOfWorldMapSearchMatcher",
            "CallableWorldMapSearchMatcher",
            "CastleProfileValidationSearchMatcher",
            "CastleQuerySearchMatcher",
            "NotWorldMapSearchMatcher",
            "SpatialObjectSearchMatcher",
            "WorldMapCastleEnrichmentPolicy",
            "WorldMapCastleEnrichmentPolicyKind",
            "WorldMapCastleProfileQuery",
            "WorldMapMapCorner",
            "WorldMapMovementPreferences",
            "WorldMapMovementToolKind",
            "WorldMapResolvedSearchPlan",
            "WorldMapSearchBoundary",
            "WorldMapSearchMatcher",
            "WorldMapSearchOrigin",
            "WorldMapSearchOriginKind",
            "WorldMapSearchPattern",
            "WorldMapSearchRequest",
            "WorldMapSearchStopPolicy",
            "WorldMapSearchStopReason",
            "adapt_world_map_search_matcher",
            "all_of_world_map_search",
            "any_of_world_map_search",
            "not_world_map_search",
            "_known_world_map_bounds",
            "_object_coordinate",
            "_require_map_bounds",
            "_validate_boundary_within_coordinate_domain",
        )
        planning_names = (
            "format_world_map_route_preview",
            "resolve_world_map_movement_tool_for_action_family",
            "resolve_world_map_search_plan",
            "validate_world_map_preview_limits",
            "_coordinate_for_corner",
            "_resolve_self_territory_origin",
        )
        for name in contracts_names:
            with self.subTest(symbol=name):
                self.assertIs(getattr(world_map_search, name), getattr(world_map_search_contracts, name))
        for name in planning_names:
            with self.subTest(symbol=name):
                self.assertIs(getattr(world_map_search, name), getattr(world_map_search_planning, name))
