"""Focused coverage for production world-map sweep policy, coverage, and projection models."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import Bounds, SpatialObjectKind
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapBounds, WorldMapCoordinateDomain
from pnc_automation.app.pnc.navigation.world_map_sweep import (
    WorldMapCoordinateProjectionContext,
    WorldMapCoverageStatus,
    WorldMapCoverageWindow,
    WorldMapElementCoordinateWindow,
    WorldMapElementDetection,
    WorldMapFrameSamplingPolicy,
    WorldMapParserCompletenessMetrics,
    WorldMapSampledFrame,
    WorldMapSweepPolicy,
    WorldMapSweepPolicyKind,
    WorldMapSweepSegmentKind,
    audit_world_map_route_scan_coverage,
    build_world_map_sweep_plan,
    estimate_world_map_sweep_performance,
    require_world_map_route_scan_coverage,
    world_map_sample_gap_exceeds_scan_footprint,
)
from pnc_automation.app.pnc.navigation.world_map_traversal import (
    TraversalStridePolicy,
    WorldMapSearchPatternKind,
    WorldMapTraversalPlanner,
)
from pnc_automation.app.pnc.vision.spatial_surfaces import estimated_world_map_visible_scan_footprint_units
from pnc_automation.core.errors import SelectorResolutionError


class WorldMapSweepTests(unittest.TestCase):
    """Validates the Phase 3 sweep architecture without requiring a live emulator."""

    def setUp(self) -> None:
        """Builds shared route fixtures for sweep-policy tests."""

        self.domain = WorldMapCoordinateDomain.puzzles_and_conquest()
        self.planner = WorldMapTraversalPlanner()

    def test_debug_policy_groups_each_checkpoint_as_exact_segment(self) -> None:
        """Keeps the current exact-checkpoint behavior available as a diagnostic policy."""

        route_plan = self._small_serpentine_route()
        sweep_plan = build_world_map_sweep_plan(
            route_plan=route_plan,
            policy=WorldMapSweepPolicy.debug_exact_checkpoint(),
        )

        self.assertEqual(len(sweep_plan.segments), len(route_plan.checkpoints))
        self.assertTrue(all(segment.kind == WorldMapSweepSegmentKind.EXACT_CHECKPOINT for segment in sweep_plan.segments))

    def test_production_policy_groups_route_into_row_segments(self) -> None:
        """Uses the same route owner while changing the production unit of work to row/lane segments."""

        route_plan = self._small_serpentine_route()
        sweep_plan = build_world_map_sweep_plan(
            route_plan=route_plan,
            policy=WorldMapSweepPolicy.production_full_map(),
        )

        self.assertEqual(sweep_plan.policy.kind, WorldMapSweepPolicyKind.PRODUCTION_FULL_MAP)
        self.assertEqual(len(sweep_plan.segments), len(route_plan.segments))
        self.assertEqual(sweep_plan.segments[0].checkpoint_coordinates, ((0, 0), (10, 0), (20, 0)))
        self.assertTrue(all(segment.kind == WorldMapSweepSegmentKind.ROW_OR_LANE for segment in sweep_plan.segments))

    def test_full_map_serpentine_route_and_production_segments_keep_reviewed_coverage(self) -> None:
        """Proves the production grouping covers the same full-map route envelope as exact checkpoints."""

        route_plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023),
            stride_policy=TraversalStridePolicy.symmetric(10),
        )
        sweep_plan = build_world_map_sweep_plan(
            route_plan=route_plan,
            policy=WorldMapSweepPolicy.production_full_map(),
        )

        self.assertEqual(len(route_plan.checkpoints), 5460)
        self.assertEqual(sweep_plan.segments[0].start_coordinate, (0, 0))
        self.assertEqual(sweep_plan.segments[-1].end_coordinate, (511, 1023))
        self.assertLess(len(sweep_plan.segments), len(route_plan.checkpoints))

    def test_default_stride_has_no_modeled_viewport_scan_gaps(self) -> None:
        """Anchors the canonical conservative default against the visible-world scan footprint model."""

        route_plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023),
            stride_policy=TraversalStridePolicy.viewport_default(),
        )

        audit = require_world_map_route_scan_coverage(
            route_plan=route_plan,
            scan_footprint_units=estimated_world_map_visible_scan_footprint_units(),
        )

        self.assertFalse(audit.has_gaps)
        self.assertEqual(audit.horizontal_stride_units, 6)
        self.assertEqual(audit.vertical_stride_units, 6)
        self.assertEqual(audit.horizontal_gap_units, 0)
        self.assertEqual(audit.vertical_gap_units, 0)

    def test_legacy_benchmark_stride_ten_remains_modeled_safe_when_explicitly_requested(self) -> None:
        """Documents that the old benchmark stride is an override, not the conservative default."""

        route_plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023),
            stride_policy=TraversalStridePolicy.symmetric(10),
        )

        audit = require_world_map_route_scan_coverage(
            route_plan=route_plan,
            scan_footprint_units=estimated_world_map_visible_scan_footprint_units(),
        )

        self.assertFalse(audit.has_gaps)
        self.assertEqual(audit.horizontal_stride_units, 10)
        self.assertEqual(audit.vertical_stride_units, 10)

    def test_route_scan_coverage_audit_fails_when_stride_exceeds_modeled_footprint(self) -> None:
        """Prevents future stride tuning from silently creating projected viewport coverage gaps."""

        route_plan = self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023),
            stride_policy=TraversalStridePolicy.symmetric(950),
        )
        audit = audit_world_map_route_scan_coverage(
            route_plan=route_plan,
            scan_footprint_units=estimated_world_map_visible_scan_footprint_units(),
        )

        self.assertTrue(audit.has_gaps)
        with self.assertRaises(SelectorResolutionError):
            require_world_map_route_scan_coverage(
                route_plan=route_plan,
                scan_footprint_units=estimated_world_map_visible_scan_footprint_units(),
            )

    def test_actual_sample_gap_check_only_flags_distance_beyond_viewport_footprint(self) -> None:
        """Defines when production movement must correct because actual sampled coverage can have a gap."""

        self.assertFalse(
            world_map_sample_gap_exceeds_scan_footprint(
                previous_coordinate=(100, 100),
                current_coordinate=(160, 120),
                scan_footprint_units=(900, 876),
            )
        )
        self.assertTrue(
            world_map_sample_gap_exceeds_scan_footprint(
                previous_coordinate=(100, 100),
                current_coordinate=(100, 1000),
                scan_footprint_units=(900, 876),
            )
        )
        with self.assertRaises(SelectorResolutionError):
            world_map_sample_gap_exceeds_scan_footprint(
                previous_coordinate=(0, 0),
                current_coordinate=(1, 1),
                scan_footprint_units=(0, 10),
            )

    def test_parsed_coverage_requires_sampled_frame_and_sampling_policy(self) -> None:
        """Prevents production sweep acceptance from marking coverage complete without parser evidence."""

        with self.assertRaises(SelectorResolutionError):
            WorldMapCoverageWindow(
                coordinate_window=WorldMapElementCoordinateWindow.exact((10, 0)),
                segment_index=0,
                status=WorldMapCoverageStatus.PARSED,
            )

        window = WorldMapCoverageWindow(
            coordinate_window=WorldMapElementCoordinateWindow.exact((10, 0)),
            segment_index=0,
            status=WorldMapCoverageStatus.PARSED,
            sample_frame_id="row0_frame0",
            sampling_policy=WorldMapSweepPolicy.production_full_map().sampling_policy,
        )
        self.assertEqual(window.status, WorldMapCoverageStatus.PARSED)

    def test_projection_context_interpolates_frames_and_rejects_non_monotonic_samples(self) -> None:
        """Projects sampled frames between sparse exact anchors with deterministic uncertainty windows."""

        segment = build_world_map_sweep_plan(
            route_plan=self._small_serpentine_route(),
            policy=WorldMapSweepPolicy.production_full_map(),
        ).segments[0]
        projection = WorldMapCoordinateProjectionContext(
            segment=segment,
            start_anchor_coordinate=(0, 0),
            end_anchor_coordinate=(20, 0),
            max_uncertainty_units=3.0,
        )

        projected = projection.project_frames(
            (
                WorldMapSampledFrame(frame_id="a", segment_index=0, sample_index=0, progress_ratio=0.0),
                WorldMapSampledFrame(frame_id="b", segment_index=0, sample_index=1, progress_ratio=0.5),
            )
        )
        self.assertEqual(projected[1].estimated_viewport_center, (10, 0))
        with self.assertRaises(SelectorResolutionError):
            projection.project_frames(
                (
                    WorldMapSampledFrame(frame_id="b", segment_index=0, sample_index=1, progress_ratio=0.5),
                    WorldMapSampledFrame(frame_id="a", segment_index=0, sample_index=0, progress_ratio=0.0),
                )
            )

    def test_projection_context_uses_actual_sparse_anchor_coordinates(self) -> None:
        """Projects through real proven anchors when live movement lands inside the accepted tolerance band."""

        segment = build_world_map_sweep_plan(
            route_plan=self._small_serpentine_route(),
            policy=WorldMapSweepPolicy.production_full_map(),
        ).segments[0]
        projection = WorldMapCoordinateProjectionContext(
            segment=segment,
            start_anchor_coordinate=(0, 4),
            end_anchor_coordinate=(20, 4),
            max_uncertainty_units=3.0,
        )

        projected = projection.project_frame(
            WorldMapSampledFrame(frame_id="middle", segment_index=0, sample_index=1, progress_ratio=0.5)
        )

        self.assertEqual(projected.estimated_viewport_center, (10, 4))

    def test_projection_context_rejects_windows_over_policy_uncertainty(self) -> None:
        """Fails fast when a projected frame is too far from exact anchors to stay inside policy."""

        segment = build_world_map_sweep_plan(
            route_plan=self._small_serpentine_route(),
            policy=WorldMapSweepPolicy.production_full_map(),
        ).segments[0]
        projection = WorldMapCoordinateProjectionContext(
            segment=segment,
            start_anchor_coordinate=(0, 0),
            end_anchor_coordinate=(100, 0),
            max_uncertainty_units=3.0,
        )

        with self.assertRaises(SelectorResolutionError):
            projection.project_frame(
                WorldMapSampledFrame(frame_id="middle", segment_index=0, sample_index=1, progress_ratio=0.5)
            )

    def test_unknown_element_detection_must_retain_uncertainty_reason(self) -> None:
        """Keeps seen-but-unclassified content instead of silently dropping parser uncertainty."""

        with self.assertRaises(SelectorResolutionError):
            WorldMapElementDetection(
                kind=None,
                screen_bounds=Bounds(x=1, y=1, width=10, height=10),
                coordinate_window=WorldMapElementCoordinateWindow.exact((10, 0)),
                frame_id="frame0",
                segment_index=0,
                confidence=0.2,
                dedupe_key="unknown:10:0",
            )

        detection = WorldMapElementDetection(
            kind=SpatialObjectKind.MONSTER,
            screen_bounds=Bounds(x=1, y=1, width=10, height=10),
            coordinate_window=WorldMapElementCoordinateWindow.exact((10, 0)),
            frame_id="frame0",
            segment_index=0,
            confidence=0.9,
            dedupe_key="monster:10:0",
        )
        self.assertEqual(detection.kind, SpatialObjectKind.MONSTER)

    def test_parser_metrics_and_estimator_are_json_ready(self) -> None:
        """Produces structured metrics needed for under-30-minute benchmark acceptance."""

        metrics = WorldMapParserCompletenessMetrics(
            sampled_frame_count=10,
            parsed_frame_count=9,
            dropped_frame_count=1,
            detected_element_count=4,
            unknown_or_uncertain_element_count=1,
            duplicate_merge_count=2,
            coverage_window_count=10,
            coverage_gap_count=1,
            maximum_coordinate_uncertainty=2.5,
            p2_queue_peak_depth=3,
            p2_parse_elapsed_ms=120.0,
            merge_elapsed_ms=5.0,
        )
        estimate = estimate_world_map_sweep_performance(
            sweep_plan=build_world_map_sweep_plan(
                route_plan=self._small_serpentine_route(),
                policy=WorldMapSweepPolicy.production_full_map(),
            ),
            exact_checkpoint_seconds=13.785,
            production_segment_seconds=17.5,
            parser_budget_seconds=600.0,
        )

        self.assertEqual(metrics.to_document()["coverage_gap_count"], 1)
        self.assertEqual(estimate.to_document()["segment_count"], 3)

    def test_sampling_policy_rejects_invalid_overlap(self) -> None:
        """Fails fast on malformed sampling policies before production coverage planning."""

        with self.assertRaises(SelectorResolutionError):
            WorldMapFrameSamplingPolicy(
                max_screen_gap_px=100,
                min_overlap_ratio=1.0,
                max_projection_uncertainty_units=3.0,
                max_unparsed_coverage_units=10,
                duplicate_cluster_radius_units=3,
            )

    def _small_serpentine_route(self):
        """Builds a compact three-row route for policy and projection tests."""

        return self.planner.build_route_plan(
            pattern_kind=WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP,
            coordinate_domain=self.domain,
            origin_coordinate=(0, 0),
            coverage_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
            stride_policy=TraversalStridePolicy.symmetric(10),
        )


if __name__ == "__main__":
    unittest.main()
