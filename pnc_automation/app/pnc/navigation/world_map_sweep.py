"""Policy, coverage, projection, and inventory models for canonical world-map sweeping."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pnc_automation.app.pnc.domain.observation import Bounds, SpatialObjectKind
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapBounds, is_integer_pair
from pnc_automation.app.pnc.navigation.world_map_traversal import (
    TraversalSegmentIntent,
    WorldMapTraversalRoutePlan,
)
from pnc_automation.core.errors import SelectorResolutionError


class WorldMapSweepPolicyKind(StrEnum):
    """Defines the supported strictness policies for the one canonical sweep engine."""

    DEBUG_EXACT_CHECKPOINT = "debug_exact_checkpoint"
    PRODUCTION_FULL_MAP = "production_full_map"


class WorldMapSweepSegmentKind(StrEnum):
    """Defines the execution unit represented by one sweep segment."""

    EXACT_CHECKPOINT = "exact_checkpoint"
    ROW_OR_LANE = "row_or_lane"


class WorldMapCoverageStatus(StrEnum):
    """Describes whether one projected coverage window has been parsed yet."""

    PROJECTED = "projected"
    PARSED = "parsed"
    GAP = "gap"


@dataclass(frozen=True, slots=True)
class WorldMapFrameSamplingPolicy:
    """Defines coverage-driven sampled-frame requirements for production full-map sweeping."""

    max_screen_gap_px: int
    min_overlap_ratio: float
    max_projection_uncertainty_units: float
    max_unparsed_coverage_units: int
    duplicate_cluster_radius_units: int
    retain_unknown_elements: bool = True

    def __post_init__(self) -> None:
        """Rejects malformed sampling policies before coverage can be marked complete."""

        if self.max_screen_gap_px <= 0:
            raise SelectorResolutionError("Frame sampling requires a positive max_screen_gap_px.")
        if not 0.0 <= self.min_overlap_ratio < 1.0:
            raise SelectorResolutionError(
                "Frame sampling requires min_overlap_ratio in [0.0, 1.0).",
                min_overlap_ratio=self.min_overlap_ratio,
            )
        if self.max_projection_uncertainty_units <= 0:
            raise SelectorResolutionError("Frame sampling requires a positive max_projection_uncertainty_units.")
        if self.max_unparsed_coverage_units <= 0:
            raise SelectorResolutionError("Frame sampling requires a positive max_unparsed_coverage_units.")
        if self.duplicate_cluster_radius_units < 0:
            raise SelectorResolutionError("Frame sampling requires a non-negative duplicate_cluster_radius_units.")


@dataclass(frozen=True, slots=True)
class WorldMapSparseProofPolicy:
    """Defines exact proof anchors and drift limits for production row/segment traversal."""

    require_segment_start: bool = True
    require_segment_end: bool = True
    periodic_anchor_interval_segments: int | None = None
    max_projection_uncertainty_units: float = 3.0

    def __post_init__(self) -> None:
        """Rejects sparse-proof policies that cannot bound projection drift."""

        if self.periodic_anchor_interval_segments is not None and self.periodic_anchor_interval_segments <= 0:
            raise SelectorResolutionError(
                "Sparse proof periodic anchor intervals must be positive when present.",
                periodic_anchor_interval_segments=self.periodic_anchor_interval_segments,
            )
        if self.max_projection_uncertainty_units <= 0:
            raise SelectorResolutionError(
                "Sparse proof policies require a positive max_projection_uncertainty_units.",
                max_projection_uncertainty_units=self.max_projection_uncertainty_units,
            )


@dataclass(frozen=True, slots=True)
class WorldMapSweepPolicy:
    """Selects one canonical sweep execution policy without introducing a second engine."""

    kind: WorldMapSweepPolicyKind
    sparse_proof_policy: WorldMapSparseProofPolicy
    sampling_policy: WorldMapFrameSamplingPolicy | None = None
    exact_proof_every_checkpoint: bool = False
    max_pending_p2_items: int = 1

    def __post_init__(self) -> None:
        """Rejects inconsistent policy combinations before route planning consumes them."""

        if self.max_pending_p2_items <= 0:
            raise SelectorResolutionError(
                "World-map sweep policies require a positive max_pending_p2_items value.",
                max_pending_p2_items=self.max_pending_p2_items,
            )
        if self.kind == WorldMapSweepPolicyKind.DEBUG_EXACT_CHECKPOINT:
            if not self.exact_proof_every_checkpoint:
                raise SelectorResolutionError("Debug exact sweep policy must require proof at every checkpoint.")
            return
        if self.kind == WorldMapSweepPolicyKind.PRODUCTION_FULL_MAP:
            if self.sampling_policy is None:
                raise SelectorResolutionError("Production full-map sweep policy requires a sampling policy.")
            if self.exact_proof_every_checkpoint:
                raise SelectorResolutionError("Production full-map sweep policy must not require every checkpoint proof.")
            if not self.sparse_proof_policy.require_segment_start or not self.sparse_proof_policy.require_segment_end:
                raise SelectorResolutionError("Production full-map sweep policy requires start and end segment anchors.")
            return
        raise SelectorResolutionError("Unsupported world-map sweep policy kind.", kind=self.kind.value)

    @classmethod
    def debug_exact_checkpoint(cls) -> "WorldMapSweepPolicy":
        """Returns the diagnostic policy that preserves exact checkpoint-by-checkpoint behavior."""

        return cls(
            kind=WorldMapSweepPolicyKind.DEBUG_EXACT_CHECKPOINT,
            sparse_proof_policy=WorldMapSparseProofPolicy(),
            exact_proof_every_checkpoint=True,
        )

    @classmethod
    def production_full_map(
        cls,
        *,
        sampling_policy: WorldMapFrameSamplingPolicy | None = None,
        sparse_proof_policy: WorldMapSparseProofPolicy | None = None,
        max_pending_p2_items: int = 4,
    ) -> "WorldMapSweepPolicy":
        """Returns the exact-P1 sampled production policy while sparse OCR throughput work remains gated."""

        return cls(
            kind=WorldMapSweepPolicyKind.PRODUCTION_FULL_MAP,
            sparse_proof_policy=sparse_proof_policy or WorldMapSparseProofPolicy(),
            sampling_policy=sampling_policy
            or WorldMapFrameSamplingPolicy(
                max_screen_gap_px=180,
                min_overlap_ratio=0.35,
                max_projection_uncertainty_units=3.0,
                max_unparsed_coverage_units=10,
                duplicate_cluster_radius_units=3,
            ),
            exact_proof_every_checkpoint=False,
            max_pending_p2_items=max_pending_p2_items,
        )


@dataclass(frozen=True, slots=True)
class WorldMapElementCoordinateWindow:
    """Represents the coordinate uncertainty window supporting one detected map element."""

    min_coordinate: tuple[int, int]
    max_coordinate: tuple[int, int]

    def __post_init__(self) -> None:
        """Rejects malformed or inverted coordinate windows."""

        if not is_integer_pair(self.min_coordinate) or not is_integer_pair(self.max_coordinate):
            raise SelectorResolutionError(
                "Element coordinate windows require integer min/max coordinate pairs.",
                min_coordinate=self.min_coordinate,
                max_coordinate=self.max_coordinate,
            )
        if self.min_coordinate[0] > self.max_coordinate[0] or self.min_coordinate[1] > self.max_coordinate[1]:
            raise SelectorResolutionError(
                "Element coordinate windows must not be inverted.",
                min_coordinate=self.min_coordinate,
                max_coordinate=self.max_coordinate,
            )

    @classmethod
    def exact(cls, coordinate: tuple[int, int]) -> "WorldMapElementCoordinateWindow":
        """Returns a zero-uncertainty coordinate window for exact proof-backed elements."""

        return cls(min_coordinate=coordinate, max_coordinate=coordinate)


@dataclass(frozen=True, slots=True)
class WorldMapCoverageWindow:
    """Describes one projected or parsed coordinate window produced by sampled-frame coverage."""

    coordinate_window: WorldMapElementCoordinateWindow
    segment_index: int
    status: WorldMapCoverageStatus
    sample_frame_id: str | None = None
    sampling_policy: WorldMapFrameSamplingPolicy | None = None

    def __post_init__(self) -> None:
        """Rejects coverage states that would let a sweep pass without sampled evidence."""

        if self.segment_index < 0:
            raise SelectorResolutionError("Coverage windows require a non-negative segment_index.")
        if self.status == WorldMapCoverageStatus.PARSED:
            if self.sample_frame_id is None or self.sampling_policy is None:
                raise SelectorResolutionError(
                    "Parsed coverage windows require a sample frame id and sampling policy evidence.",
                    segment_index=self.segment_index,
                )
        if self.sample_frame_id is not None and self.sample_frame_id.strip() == "":
            raise SelectorResolutionError("Coverage windows must not use blank sample_frame_id values.")


@dataclass(frozen=True, slots=True)
class WorldMapSweepSegment:
    """Groups checkpoint route coordinates into the policy-specific production unit of work."""

    segment_index: int
    kind: WorldMapSweepSegmentKind
    start_coordinate: tuple[int, int]
    end_coordinate: tuple[int, int]
    checkpoint_route_indices: tuple[int, ...]
    checkpoint_coordinates: tuple[tuple[int, int], ...]
    traversal_segment_intent: TraversalSegmentIntent

    def __post_init__(self) -> None:
        """Rejects malformed sweep segments before live execution can consume them."""

        if self.segment_index < 0:
            raise SelectorResolutionError("Sweep segments require a non-negative segment_index.")
        if not self.checkpoint_route_indices or not self.checkpoint_coordinates:
            raise SelectorResolutionError("Sweep segments require checkpoint route indices and coordinates.")
        if len(self.checkpoint_route_indices) != len(self.checkpoint_coordinates):
            raise SelectorResolutionError(
                "Sweep segment route indices and coordinates must have the same length.",
                route_indices=self.checkpoint_route_indices,
                checkpoint_coordinates=self.checkpoint_coordinates,
            )
        if self.start_coordinate != self.checkpoint_coordinates[0]:
            raise SelectorResolutionError("Sweep segment start_coordinate must match its first checkpoint.")
        if self.end_coordinate != self.checkpoint_coordinates[-1]:
            raise SelectorResolutionError("Sweep segment end_coordinate must match its last checkpoint.")


@dataclass(frozen=True, slots=True)
class WorldMapSweepPlan:
    """Carries policy-specific sweep segments derived from the canonical route plan."""

    policy: WorldMapSweepPolicy
    route_plan: WorldMapTraversalRoutePlan
    segments: tuple[WorldMapSweepSegment, ...]

    def __post_init__(self) -> None:
        """Rejects empty sweep plans and policy/segment mismatches."""

        if not self.segments:
            raise SelectorResolutionError("World-map sweep planning produced no segments.")
        if self.policy.kind == WorldMapSweepPolicyKind.DEBUG_EXACT_CHECKPOINT and any(
            segment.kind != WorldMapSweepSegmentKind.EXACT_CHECKPOINT for segment in self.segments
        ):
            raise SelectorResolutionError("Debug exact sweep plans must contain only exact-checkpoint segments.")
        if self.policy.kind == WorldMapSweepPolicyKind.PRODUCTION_FULL_MAP and any(
            segment.kind != WorldMapSweepSegmentKind.ROW_OR_LANE for segment in self.segments
        ):
            raise SelectorResolutionError("Production full-map sweep plans must contain row/lane segments.")


@dataclass(frozen=True, slots=True)
class WorldMapSampledFrame:
    """Identifies one sampled frame captured during continuous row/segment traversal."""

    frame_id: str
    segment_index: int
    sample_index: int
    progress_ratio: float
    screenshot_artifact_path: Path | None = None

    def __post_init__(self) -> None:
        """Rejects sampled-frame metadata that would break deterministic projection."""

        if self.frame_id.strip() == "":
            raise SelectorResolutionError("Sampled frames require a non-blank frame_id.")
        if self.segment_index < 0 or self.sample_index < 0:
            raise SelectorResolutionError("Sampled frames require non-negative segment and sample indices.")
        if not 0.0 <= self.progress_ratio <= 1.0:
            raise SelectorResolutionError(
                "Sampled frame progress_ratio must be in [0.0, 1.0].",
                progress_ratio=self.progress_ratio,
            )


@dataclass(frozen=True, slots=True)
class WorldMapCoordinateProjectionContext:
    """Projects sampled frames between exact segment anchors into bounded coordinate windows."""

    segment: WorldMapSweepSegment
    start_anchor_coordinate: tuple[int, int]
    end_anchor_coordinate: tuple[int, int]
    max_uncertainty_units: float

    def __post_init__(self) -> None:
        """Rejects projection contexts without exact anchor and uncertainty support."""

        if not is_integer_pair(self.start_anchor_coordinate) or not is_integer_pair(self.end_anchor_coordinate):
            raise SelectorResolutionError(
                "Projection anchors must be exact integer world-map coordinates.",
                start_anchor_coordinate=self.start_anchor_coordinate,
                end_anchor_coordinate=self.end_anchor_coordinate,
            )
        if self.max_uncertainty_units <= 0:
            raise SelectorResolutionError("Projection contexts require a positive max_uncertainty_units.")

    def project_frame(self, frame: WorldMapSampledFrame) -> "WorldMapProjectedFrame":
        """Projects one sampled frame center and coordinate window from exact segment anchors."""

        if frame.segment_index != self.segment.segment_index:
            raise SelectorResolutionError(
                "Sampled frame segment does not match the projection context.",
                frame_segment_index=frame.segment_index,
                context_segment_index=self.segment.segment_index,
            )
        start_x, start_y = self.start_anchor_coordinate
        end_x, end_y = self.end_anchor_coordinate
        center = (
            round(start_x + (end_x - start_x) * frame.progress_ratio),
            round(start_y + (end_y - start_y) * frame.progress_ratio),
        )
        distance_from_start = max(abs(center[0] - start_x), abs(center[1] - start_y))
        distance_from_end = max(abs(center[0] - end_x), abs(center[1] - end_y))
        distance_from_nearest_anchor = min(distance_from_start, distance_from_end)
        uncertainty = max(1.0, distance_from_nearest_anchor * 0.1)
        if uncertainty > self.max_uncertainty_units:
            raise SelectorResolutionError(
                "Projected frame uncertainty exceeds the sparse-proof policy limit.",
                frame_id=frame.frame_id,
                uncertainty_units=uncertainty,
                max_uncertainty_units=self.max_uncertainty_units,
            )
        radius = int(round(uncertainty))
        return WorldMapProjectedFrame(
            sampled_frame=frame,
            estimated_viewport_center=center,
            coordinate_window=WorldMapElementCoordinateWindow(
                min_coordinate=(center[0] - radius, center[1] - radius),
                max_coordinate=(center[0] + radius, center[1] + radius),
            ),
            uncertainty_units=uncertainty,
        )

    def project_frames(self, frames: tuple[WorldMapSampledFrame, ...]) -> tuple["WorldMapProjectedFrame", ...]:
        """Projects sampled frames in monotonic order or fails fast on route-order ambiguity."""

        previous_ratio: float | None = None
        projected: list[WorldMapProjectedFrame] = []
        for frame in frames:
            if previous_ratio is not None and frame.progress_ratio < previous_ratio:
                raise SelectorResolutionError(
                    "Sampled frame progress must be monotonic within a segment.",
                    previous_ratio=previous_ratio,
                    progress_ratio=frame.progress_ratio,
                )
            previous_ratio = frame.progress_ratio
            projected.append(self.project_frame(frame))
        return tuple(projected)


@dataclass(frozen=True, slots=True)
class WorldMapProjectedFrame:
    """Carries one sampled frame with its estimated viewport center and uncertainty window."""

    sampled_frame: WorldMapSampledFrame
    estimated_viewport_center: tuple[int, int]
    coordinate_window: WorldMapElementCoordinateWindow
    uncertainty_units: float

    def __post_init__(self) -> None:
        """Rejects projected frames whose uncertainty cannot be trusted by policy."""

        if not is_integer_pair(self.estimated_viewport_center):
            raise SelectorResolutionError(
                "Projected frames require an integer estimated viewport center.",
                estimated_viewport_center=self.estimated_viewport_center,
            )
        if self.uncertainty_units <= 0:
            raise SelectorResolutionError("Projected frames require positive uncertainty_units.")


@dataclass(frozen=True, slots=True)
class WorldMapElementDetection:
    """Immutable P2 parser output for one coordinate-attributed map element sighting."""

    kind: SpatialObjectKind | None
    screen_bounds: Bounds
    coordinate_window: WorldMapElementCoordinateWindow
    frame_id: str
    segment_index: int
    confidence: float
    dedupe_key: str
    text_evidence: str | None = None
    visual_evidence: str | None = None
    uncertainty_reason: str | None = None

    def __post_init__(self) -> None:
        """Rejects element detections that would silently lose parser uncertainty."""

        if self.frame_id.strip() == "":
            raise SelectorResolutionError("Element detections require a non-blank frame_id.")
        if self.segment_index < 0:
            raise SelectorResolutionError("Element detections require a non-negative segment_index.")
        if not 0.0 <= self.confidence <= 1.0:
            raise SelectorResolutionError("Element detection confidence must be in [0.0, 1.0].")
        if self.dedupe_key.strip() == "":
            raise SelectorResolutionError("Element detections require a non-blank dedupe_key.")
        if self.kind is None and (self.uncertainty_reason is None or self.uncertainty_reason.strip() == ""):
            raise SelectorResolutionError("Unknown element detections must retain an uncertainty reason.")


@dataclass(frozen=True, slots=True)
class WorldMapParserCompletenessMetrics:
    """Summarizes parser coverage and queue health for under-30-minute sweep profiles."""

    sampled_frame_count: int
    parsed_frame_count: int
    dropped_frame_count: int
    detected_element_count: int
    unknown_or_uncertain_element_count: int
    duplicate_merge_count: int
    coverage_window_count: int
    coverage_gap_count: int
    maximum_coordinate_uncertainty: float
    p2_queue_peak_depth: int
    p2_parse_elapsed_ms: float
    merge_elapsed_ms: float

    def __post_init__(self) -> None:
        """Rejects malformed parser metrics before profile persistence."""

        for field_name, value in (
            ("sampled_frame_count", self.sampled_frame_count),
            ("parsed_frame_count", self.parsed_frame_count),
            ("dropped_frame_count", self.dropped_frame_count),
            ("detected_element_count", self.detected_element_count),
            ("unknown_or_uncertain_element_count", self.unknown_or_uncertain_element_count),
            ("duplicate_merge_count", self.duplicate_merge_count),
            ("coverage_window_count", self.coverage_window_count),
            ("coverage_gap_count", self.coverage_gap_count),
            ("p2_queue_peak_depth", self.p2_queue_peak_depth),
        ):
            if value < 0:
                raise SelectorResolutionError("Parser metric counts must be non-negative.", field_name=field_name, value=value)
        for field_name, value in (
            ("maximum_coordinate_uncertainty", self.maximum_coordinate_uncertainty),
            ("p2_parse_elapsed_ms", self.p2_parse_elapsed_ms),
            ("merge_elapsed_ms", self.merge_elapsed_ms),
        ):
            if value < 0:
                raise SelectorResolutionError("Parser metric timings/uncertainty must be non-negative.", field_name=field_name, value=value)
        if self.parsed_frame_count > self.sampled_frame_count:
            raise SelectorResolutionError(
                "Parsed frame count cannot exceed sampled frame count.",
                sampled_frame_count=self.sampled_frame_count,
                parsed_frame_count=self.parsed_frame_count,
            )

    def to_document(self) -> dict[str, object]:
        """Exports parser completeness metrics as a JSON-ready document."""

        return {
            "sampled_frame_count": self.sampled_frame_count,
            "parsed_frame_count": self.parsed_frame_count,
            "dropped_frame_count": self.dropped_frame_count,
            "detected_element_count": self.detected_element_count,
            "unknown_or_uncertain_element_count": self.unknown_or_uncertain_element_count,
            "duplicate_merge_count": self.duplicate_merge_count,
            "coverage_window_count": self.coverage_window_count,
            "coverage_gap_count": self.coverage_gap_count,
            "maximum_coordinate_uncertainty": round(self.maximum_coordinate_uncertainty, 3),
            "p2_queue_peak_depth": self.p2_queue_peak_depth,
            "p2_parse_elapsed_ms": round(self.p2_parse_elapsed_ms, 2),
            "merge_elapsed_ms": round(self.merge_elapsed_ms, 2),
        }


@dataclass(frozen=True, slots=True)
class WorldMapSweepBenchmarkEstimate:
    """Compares exact-checkpoint and production segment estimates for dry-run planning."""

    checkpoint_count: int
    segment_count: int
    estimated_exact_checkpoint_seconds: float
    estimated_production_seconds: float
    parser_budget_seconds: float

    def __post_init__(self) -> None:
        """Rejects negative benchmark estimates before live tooling consumes them."""

        for field_name, value in (
            ("checkpoint_count", self.checkpoint_count),
            ("segment_count", self.segment_count),
            ("estimated_exact_checkpoint_seconds", self.estimated_exact_checkpoint_seconds),
            ("estimated_production_seconds", self.estimated_production_seconds),
            ("parser_budget_seconds", self.parser_budget_seconds),
        ):
            if value < 0:
                raise SelectorResolutionError("Sweep benchmark estimates must be non-negative.", field_name=field_name, value=value)

    def to_document(self) -> dict[str, object]:
        """Exports the dry-run benchmark estimate as a JSON-ready document."""

        return {
            "checkpoint_count": self.checkpoint_count,
            "segment_count": self.segment_count,
            "estimated_exact_checkpoint_seconds": round(self.estimated_exact_checkpoint_seconds, 3),
            "estimated_production_seconds": round(self.estimated_production_seconds, 3),
            "parser_budget_seconds": round(self.parser_budget_seconds, 3),
        }


@dataclass(frozen=True, slots=True)
class WorldMapRouteScanCoverageAudit:
    """Reports whether a checkpoint route's modeled scan footprint can leave stride-sized coverage gaps."""

    coverage_bounds: WorldMapBounds
    horizontal_stride_units: int
    vertical_stride_units: int
    horizontal_scan_footprint_units: int
    vertical_scan_footprint_units: int
    horizontal_gap_units: int
    vertical_gap_units: int

    def __post_init__(self) -> None:
        """Rejects malformed audit values before benchmark/profile consumers trust them."""

        for field_name, value in (
            ("horizontal_stride_units", self.horizontal_stride_units),
            ("vertical_stride_units", self.vertical_stride_units),
            ("horizontal_scan_footprint_units", self.horizontal_scan_footprint_units),
            ("vertical_scan_footprint_units", self.vertical_scan_footprint_units),
            ("horizontal_gap_units", self.horizontal_gap_units),
            ("vertical_gap_units", self.vertical_gap_units),
        ):
            if value < 0:
                raise SelectorResolutionError("Route scan coverage audit values must be non-negative.", field_name=field_name, value=value)

    @property
    def has_gaps(self) -> bool:
        """Returns whether the modeled scan footprint is smaller than the route stride on either axis."""

        return self.horizontal_gap_units > 0 or self.vertical_gap_units > 0

    def to_document(self) -> dict[str, object]:
        """Exports the route coverage audit as one JSON-ready document."""

        return {
            "coverage_bounds": {
                "min_x": self.coverage_bounds.min_x,
                "min_y": self.coverage_bounds.min_y,
                "max_x": self.coverage_bounds.max_x,
                "max_y": self.coverage_bounds.max_y,
            },
            "horizontal_stride_units": self.horizontal_stride_units,
            "vertical_stride_units": self.vertical_stride_units,
            "horizontal_scan_footprint_units": self.horizontal_scan_footprint_units,
            "vertical_scan_footprint_units": self.vertical_scan_footprint_units,
            "horizontal_gap_units": self.horizontal_gap_units,
            "vertical_gap_units": self.vertical_gap_units,
            "has_gaps": self.has_gaps,
        }


def audit_world_map_route_scan_coverage(
    *,
    route_plan: WorldMapTraversalRoutePlan,
    scan_footprint_units: tuple[int, int],
) -> WorldMapRouteScanCoverageAudit:
    """Audits whether route checkpoint spacing can leave modeled viewport-scan gaps."""

    horizontal_scan_footprint_units, vertical_scan_footprint_units = scan_footprint_units
    if horizontal_scan_footprint_units <= 0 or vertical_scan_footprint_units <= 0:
        raise SelectorResolutionError(
            "World-map scan coverage audits require a positive scan footprint on both axes.",
            scan_footprint_units=scan_footprint_units,
        )
    return WorldMapRouteScanCoverageAudit(
        coverage_bounds=route_plan.coverage_bounds,
        horizontal_stride_units=route_plan.stride.horizontal_stride_units,
        vertical_stride_units=route_plan.stride.vertical_stride_units,
        horizontal_scan_footprint_units=horizontal_scan_footprint_units,
        vertical_scan_footprint_units=vertical_scan_footprint_units,
        horizontal_gap_units=max(0, route_plan.stride.horizontal_stride_units - horizontal_scan_footprint_units),
        vertical_gap_units=max(0, route_plan.stride.vertical_stride_units - vertical_scan_footprint_units),
    )


def require_world_map_route_scan_coverage(
    *,
    route_plan: WorldMapTraversalRoutePlan,
    scan_footprint_units: tuple[int, int],
) -> WorldMapRouteScanCoverageAudit:
    """Returns the route scan coverage audit or fails fast when modeled scan gaps are possible."""

    audit = audit_world_map_route_scan_coverage(
        route_plan=route_plan,
        scan_footprint_units=scan_footprint_units,
    )
    if audit.has_gaps:
        raise SelectorResolutionError(
            "World-map route stride can leave modeled viewport-scan coverage gaps.",
            audit=audit.to_document(),
        )
    return audit


def world_map_sample_gap_exceeds_scan_footprint(
    *,
    previous_coordinate: tuple[int, int],
    current_coordinate: tuple[int, int],
    scan_footprint_units: tuple[int, int],
) -> bool:
    """Returns whether adjacent actual sampled viewports can leave an unobserved map gap."""

    horizontal_scan_footprint_units, vertical_scan_footprint_units = scan_footprint_units
    if horizontal_scan_footprint_units <= 0 or vertical_scan_footprint_units <= 0:
        raise SelectorResolutionError(
            "World-map sample gap checks require positive scan footprints.",
            scan_footprint_units=scan_footprint_units,
        )
    return (
        abs(current_coordinate[0] - previous_coordinate[0]) > horizontal_scan_footprint_units
        or abs(current_coordinate[1] - previous_coordinate[1]) > vertical_scan_footprint_units
    )


def build_world_map_sweep_plan(
    *,
    route_plan: WorldMapTraversalRoutePlan,
    policy: WorldMapSweepPolicy,
) -> WorldMapSweepPlan:
    """Builds policy-specific sweep segments from the canonical checkpoint route plan."""

    segments: list[WorldMapSweepSegment] = []
    route_index = 0
    for route_segment in route_plan.segments:
        coordinates = route_segment.analyzed_checkpoint_coordinates
        if policy.kind == WorldMapSweepPolicyKind.DEBUG_EXACT_CHECKPOINT:
            for coordinate in coordinates:
                segments.append(
                    WorldMapSweepSegment(
                        segment_index=len(segments),
                        kind=WorldMapSweepSegmentKind.EXACT_CHECKPOINT,
                        start_coordinate=coordinate,
                        end_coordinate=coordinate,
                        checkpoint_route_indices=(route_index,),
                        checkpoint_coordinates=(coordinate,),
                        traversal_segment_intent=route_segment.traversal_segment_intent,
                    )
                )
                route_index += 1
            continue
        indices = tuple(range(route_index, route_index + len(coordinates)))
        segments.append(
            WorldMapSweepSegment(
                segment_index=len(segments),
                kind=WorldMapSweepSegmentKind.ROW_OR_LANE,
                start_coordinate=coordinates[0],
                end_coordinate=coordinates[-1],
                checkpoint_route_indices=indices,
                checkpoint_coordinates=coordinates,
                traversal_segment_intent=route_segment.traversal_segment_intent,
            )
        )
        route_index += len(coordinates)
    return WorldMapSweepPlan(policy=policy, route_plan=route_plan, segments=tuple(segments))


def estimate_world_map_sweep_performance(
    *,
    sweep_plan: WorldMapSweepPlan,
    exact_checkpoint_seconds: float,
    production_segment_seconds: float,
    parser_budget_seconds: float,
) -> WorldMapSweepBenchmarkEstimate:
    """Builds the canonical offline estimator comparing exact and production sweep budgets."""

    if exact_checkpoint_seconds <= 0 or production_segment_seconds <= 0 or parser_budget_seconds < 0:
        raise SelectorResolutionError(
            "Sweep performance estimates require positive movement costs and a non-negative parser budget.",
            exact_checkpoint_seconds=exact_checkpoint_seconds,
            production_segment_seconds=production_segment_seconds,
            parser_budget_seconds=parser_budget_seconds,
        )
    checkpoint_count = len(sweep_plan.route_plan.checkpoints)
    return WorldMapSweepBenchmarkEstimate(
        checkpoint_count=checkpoint_count,
        segment_count=len(sweep_plan.segments),
        estimated_exact_checkpoint_seconds=checkpoint_count * exact_checkpoint_seconds,
        estimated_production_seconds=len(sweep_plan.segments) * production_segment_seconds + parser_budget_seconds,
        parser_budget_seconds=parser_budget_seconds,
    )


def coverage_bounds_for_window(window: WorldMapElementCoordinateWindow) -> WorldMapBounds:
    """Converts an element coordinate window into the shared world-map bounds model."""

    return WorldMapBounds(
        min_x=window.min_coordinate[0],
        min_y=window.min_coordinate[1],
        max_x=window.max_coordinate[0],
        max_y=window.max_coordinate[1],
    )
