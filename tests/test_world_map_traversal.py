"""Focused route and execution planner coverage for world-map traversal."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapBounds, WorldMapCoordinateDomain
from pnc_automation.app.pnc.navigation.world_map_traversal import (
    TraversalRotation,
    TraversalSegmentIntent,
    TraversalStridePolicy,
    WorldMapSearchPatternKind,
    WorldMapTraversalActionFamily,
    WorldMapTraversalCorner,
    WorldMapTraversalExecutionPlanner,
    WorldMapTraversalPlanner,
    WorldMapViewportStrideProfile,
)


class WorldMapTraversalPlannerTests(unittest.TestCase):
    """Validates the dedicated route and execution planner layers beneath the search service."""

    def setUp(self) -> None:
        """Builds the shared planner fixtures used by the traversal-focused tests."""

        self.domain = WorldMapCoordinateDomain.puzzles_and_conquest()
        self.planner = WorldMapTraversalPlanner()
        self.execution_planner = WorldMapTraversalExecutionPlanner()

    def test_stride_policy_resolves_profile_defaults_and_axis_overrides(self) -> None:
        """Keeps one canonical stride-policy seam for default and axis-specific traversal spacing."""

        profile = WorldMapViewportStrideProfile(
            default_horizontal_viewport_stride_units=8,
            default_vertical_viewport_stride_units=12,
        )

        resolved_default = TraversalStridePolicy.viewport_default().resolve(profile=profile)
        self.assertEqual(resolved_default.horizontal_stride_units, 8)
        self.assertEqual(resolved_default.vertical_stride_units, 12)
        resolved = TraversalStridePolicy.axis_specific(horizontal_stride_units=6, vertical_stride_units=14).resolve(
            profile=profile
        )
        self.assertEqual(resolved.horizontal_stride_units, 6)
        self.assertEqual(resolved.vertical_stride_units, 14)

    def test_row_major_route_emits_non_local_reset_segment_intent_between_rows(self) -> None:
        """Marks row transitions explicitly instead of leaving broad reset behavior implicit in checkpoint order."""

        plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.ROW_MAJOR_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
            stride_policy=TraversalStridePolicy.symmetric(10),
        )

        self.assertEqual([segment.traversal_segment_intent for segment in plan.segments], [
            TraversalSegmentIntent.LOCAL_TRAVERSE,
            TraversalSegmentIntent.NON_LOCAL_RESET,
            TraversalSegmentIntent.NON_LOCAL_RESET,
        ])
        self.assertEqual(plan.checkpoints[:3], ((0, 0), (10, 0), (20, 0)))

    def test_serpentine_route_alternates_row_direction_and_keeps_row_transitions_local(self) -> None:
        """Represents serpentine traversal directly in the planner instead of hiding it inside row-major ordering."""

        plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
            stride_policy=TraversalStridePolicy.symmetric(10),
        )

        self.assertTrue(all(segment.traversal_segment_intent == TraversalSegmentIntent.LOCAL_TRAVERSE for segment in plan.segments))
        self.assertEqual(plan.segments[1].analyzed_checkpoint_coordinates, ((20, 10), (10, 10), (0, 10)))

    def test_execution_planner_tags_only_segment_entry_steps_with_non_local_reset(self) -> None:
        """Compiles route geometry into checkpoint steps without duplicating transition semantics on every checkpoint."""

        route_plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.ROW_MAJOR_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=10),
            stride_policy=TraversalStridePolicy.symmetric(10),
        )

        execution_plan = self.execution_planner.build_execution_plan(route_plan=route_plan, origin_coordinate=(0, 0))

        self.assertEqual(execution_plan.steps[0].action_family, WorldMapTraversalActionFamily.LOCAL_DIRECT)
        self.assertEqual(execution_plan.steps[3].traversal_segment_intent, TraversalSegmentIntent.NON_LOCAL_RESET)
        self.assertEqual(execution_plan.steps[4].traversal_segment_intent, TraversalSegmentIntent.LOCAL_TRAVERSE)

    def test_perimeter_ring_route_is_explicit_and_clockwise(self) -> None:
        """Builds one auditable perimeter loop instead of relying on the removed edge-band semantics."""

        plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.PERIMETER_RING_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
            stride_policy=TraversalStridePolicy.symmetric(10),
            perimeter_start_corner=WorldMapTraversalCorner.UPPER_LEFT,
            perimeter_rotation=TraversalRotation.CLOCKWISE,
        )

        self.assertEqual(
            plan.checkpoints,
            ((0, 0), (10, 0), (20, 0), (20, 10), (20, 20), (10, 20), (0, 20), (0, 10)),
        )

    def test_shrinking_perimeter_route_runs_outer_loop_then_inner_coordinate(self) -> None:
        """Keeps shrinking-perimeter traversal under the same canonical planner and stride-policy seam."""

        plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.SHRINKING_PERIMETER_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
            stride_policy=TraversalStridePolicy.symmetric(10),
            inset_x=10,
            inset_y=10,
        )

        self.assertEqual(plan.checkpoints[-1], (10, 10))


if __name__ == "__main__":
    unittest.main()
