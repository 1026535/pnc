"""Dedicated world-map movement calibration, dead-zone verification, and sweep-validation helpers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pnc_automation.app.pnc.domain.action_requests import SwipeInputSource, resolve_swipe_points_for_action
from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldMapCardinalDirection
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapBounds,
    WorldMapCardinalMovementClassification,
    WorldMapCoordinateMover,
    WorldMapObservedActionExecutor,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchRequest,
    WorldMapSearchService,
    WorldMapSearchStopPolicy,
    WorldMapTraversalCheckpoint,
    classify_world_map_cardinal_delta,
    is_world_map_coordinate_near_boundary,
    _coordinate_within_tolerance,
    _require_proven_world_map_observation,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.core.errors import SelectorResolutionError

if TYPE_CHECKING:
    from pnc_automation.app.pnc.vision.observation_builder import ObservationService


WorldMapSwipeProbeClassification = WorldMapCardinalMovementClassification


@dataclass(frozen=True, slots=True)
class WorldMapObservedCoordinateEvidence:
    """Carries the coordinate-parser evidence captured before or after one probe or sweep checkpoint."""

    coordinate: tuple[int, int] | None
    coordinate_text: str | None
    artifact_path: Path | None

    def to_document(self) -> dict[str, object]:
        """Exports the evidence as a JSON-ready document."""

        return {
            "coordinate": None if self.coordinate is None else [self.coordinate[0], self.coordinate[1]],
            "coordinate_text": self.coordinate_text,
            "artifact_path": None if self.artifact_path is None else str(self.artifact_path),
        }


@dataclass(frozen=True, slots=True)
class WorldMapCanonicalCardinalProfile:
    """Documents the currently wired canonical cardinal world-map swipe profile for one direction."""

    direction: WorldMapCardinalDirection
    lane_center_ratio: float
    input_source: SwipeInputSource

    def to_document(self) -> dict[str, object]:
        """Exports the canonical profile as a JSON-ready document."""

        return {
            "direction": self.direction.value,
            "lane_center_ratio": round(self.lane_center_ratio, 4),
            "input_source": self.input_source.value,
        }


@dataclass(frozen=True, slots=True)
class WorldMapSwipeProbeResult:
    """Records one exact cardinal swipe probe plus the observation evidence surrounding it."""

    direction: WorldMapCardinalDirection
    lane_center_ratio: float
    distance_ratio: float
    input_source: SwipeInputSource
    swipe_points: tuple[int, int, int, int]
    before: WorldMapObservedCoordinateEvidence
    after: WorldMapObservedCoordinateEvidence
    delta: tuple[int, int] | None
    classification: WorldMapSwipeProbeClassification
    near_boundary: bool

    def axis_displacement(self) -> int | None:
        """Returns the signed displacement along the direction's active axis when coordinates were parsed successfully."""

        if self.delta is None:
            return None
        if self.direction in {WorldMapCardinalDirection.LEFT, WorldMapCardinalDirection.RIGHT}:
            return self.delta[0]
        return self.delta[1]

    def to_document(self) -> dict[str, object]:
        """Exports the probe result as a JSON-ready document."""

        return {
            "direction": self.direction.value,
            "lane_center_ratio": round(self.lane_center_ratio, 4),
            "distance_ratio": round(self.distance_ratio, 4),
            "input_source": self.input_source.value,
            "swipe_points": list(self.swipe_points),
            "before": self.before.to_document(),
            "after": self.after.to_document(),
            "delta": None if self.delta is None else [self.delta[0], self.delta[1]],
            "axis_displacement": self.axis_displacement(),
            "classification": self.classification.value,
            "near_boundary": self.near_boundary,
        }


@dataclass(frozen=True, slots=True)
class WorldMapCalibrationMatrixEntry:
    """Aggregates repeated probe results for one direction, lane, and distance-ratio combination."""

    direction: WorldMapCardinalDirection
    lane_center_ratio: float
    distance_ratio: float
    input_source: SwipeInputSource
    trial_results: tuple[WorldMapSwipeProbeResult, ...]

    def displacement_distribution(self) -> dict[int | None, int]:
        """Returns the observed signed axis-displacement distribution across the repeated trials."""

        distribution: Counter[int | None] = Counter(result.axis_displacement() for result in self.trial_results)
        return dict(sorted(distribution.items(), key=lambda item: (-999999 if item[0] is None else item[0])))

    def classification_distribution(self) -> dict[str, int]:
        """Returns the observed outcome-classification counts across the repeated trials."""

        counts = Counter(result.classification.value for result in self.trial_results)
        return dict(sorted(counts.items()))

    def to_document(self) -> dict[str, object]:
        """Exports the matrix entry as a JSON-ready document."""

        return {
            "direction": self.direction.value,
            "lane_center_ratio": round(self.lane_center_ratio, 4),
            "distance_ratio": round(self.distance_ratio, 4),
            "input_source": self.input_source.value,
            "repeated_trial_count": len(self.trial_results),
            "displacement_distribution": {
                "null" if displacement is None else str(displacement): count
                for displacement, count in self.displacement_distribution().items()
            },
            "classification_distribution": self.classification_distribution(),
            "trial_results": [result.to_document() for result in self.trial_results],
        }


@dataclass(frozen=True, slots=True)
class WorldMapCalibrationMatrixReport:
    """Summarizes the formal cardinal calibration phase for the currently configured runtime."""

    canonical_profiles: tuple[WorldMapCanonicalCardinalProfile, ...]
    entries: tuple[WorldMapCalibrationMatrixEntry, ...]

    def to_document(self) -> dict[str, object]:
        """Exports the calibration matrix report as a JSON-ready document."""

        return {
            "canonical_profiles": [profile.to_document() for profile in self.canonical_profiles],
            "entries": [entry.to_document() for entry in self.entries],
        }


@dataclass(frozen=True, slots=True)
class WorldMapDeadZoneReport:
    """Summarizes the classified zero-motion and movement results gathered across multiple probe locations."""

    bounds: WorldMapBounds
    probe_results: tuple[WorldMapSwipeProbeResult, ...]

    def to_document(self) -> dict[str, object]:
        """Exports the dead-zone verification report as a JSON-ready document."""

        return {
            "bounds": _serialize_bounds(self.bounds),
            "probe_results": [result.to_document() for result in self.probe_results],
        }


@dataclass(frozen=True, slots=True)
class WorldMapLaneProbeRequest:
    """Defines one focused lane-safe probe sequence anchored to a single coordinate without starting a broad sweep."""

    name: str
    anchor_coordinate: tuple[int, int]
    probe_directions: tuple[WorldMapCardinalDirection, ...]
    distance_ratios: tuple[float, ...]
    lane_center_ratios: Mapping[WorldMapCardinalDirection, float] | None = None
    boundary_bounds: WorldMapBounds | None = None

    def __post_init__(self) -> None:
        """Rejects malformed lane-probe requests before live diagnostics begin."""

        if self.name.strip() == "":
            raise SelectorResolutionError("World-map lane probe requests require a non-empty name.")
        if not (
            isinstance(self.anchor_coordinate, tuple)
            and len(self.anchor_coordinate) == 2
            and all(isinstance(value, int) for value in self.anchor_coordinate)
        ):
            raise SelectorResolutionError(
                "World-map lane probe requests require one integer anchor_coordinate pair.",
                anchor_coordinate=self.anchor_coordinate,
            )
        if not self.probe_directions:
            raise SelectorResolutionError("World-map lane probe requests require at least one probe direction.")
        if not self.distance_ratios:
            raise SelectorResolutionError("World-map lane probe requests require at least one distance ratio.")
        for ratio in self.distance_ratios:
            if ratio <= 0:
                raise SelectorResolutionError(
                    "World-map lane probe requests require positive distance ratios.",
                    distance_ratio=ratio,
                )


@dataclass(frozen=True, slots=True)
class WorldMapLaneProbeReport:
    """Summarizes one focused anchored lane-probe sequence for live movement diagnosis."""

    name: str
    anchor_coordinate: tuple[int, int]
    probe_results: tuple[WorldMapSwipeProbeResult, ...]

    def to_document(self) -> dict[str, object]:
        """Exports the lane-probe report as a JSON-ready document."""

        return {
            "name": self.name,
            "anchor_coordinate": [self.anchor_coordinate[0], self.anchor_coordinate[1]],
            "probe_results": [result.to_document() for result in self.probe_results],
        }


@dataclass(frozen=True, slots=True)
class WorldMapSweepValidationRequest:
    """Defines one bounded sweep-validation run used to prove movement-plus-observation stability."""

    name: str
    pattern: WorldMapSearchPattern
    checkpoint_spacing: int
    origin: WorldMapSearchOrigin | None = None
    boundary: WorldMapSearchBoundary | None = None
    max_checkpoints: int | None = None

    def __post_init__(self) -> None:
        """Rejects invalid validation requests before traversal begins."""

        if self.name.strip() == "":
            raise SelectorResolutionError("World-map sweep validation requests require a non-empty name.")
        if self.checkpoint_spacing <= 0:
            raise SelectorResolutionError(
                "World-map sweep validation requests require a positive checkpoint spacing.",
                checkpoint_spacing=self.checkpoint_spacing,
            )
        if self.max_checkpoints is not None and self.max_checkpoints <= 0:
            raise SelectorResolutionError(
                "World-map sweep validation requests require positive max_checkpoints when present.",
                max_checkpoints=self.max_checkpoints,
            )


@dataclass(frozen=True, slots=True)
class WorldMapSweepCheckpointResult:
    """Records whether one sweep checkpoint finished with a usable world-map observation and parser evidence."""

    checkpoint: WorldMapTraversalCheckpoint
    evidence: WorldMapObservedCoordinateEvidence
    usable_observation: bool
    delta_from_checkpoint: tuple[int, int] | None
    within_tolerance: bool

    def to_document(self) -> dict[str, object]:
        """Exports the checkpoint result as a JSON-ready document."""

        return {
            "checkpoint": {
                "coordinate": [self.checkpoint.coordinate[0], self.checkpoint.coordinate[1]],
                "distance_from_origin": self.checkpoint.distance_from_origin,
                "route_index": self.checkpoint.route_index,
            },
            "usable_observation": self.usable_observation,
            "requested_coordinate": [self.checkpoint.coordinate[0], self.checkpoint.coordinate[1]],
            "observed_coordinate": (
                None
                if self.evidence.coordinate is None
                else [self.evidence.coordinate[0], self.evidence.coordinate[1]]
            ),
            "delta_from_checkpoint": (
                None
                if self.delta_from_checkpoint is None
                else [self.delta_from_checkpoint[0], self.delta_from_checkpoint[1]]
            ),
            "within_tolerance": self.within_tolerance,
            "evidence": self.evidence.to_document(),
        }


@dataclass(frozen=True, slots=True)
class WorldMapSweepValidationResult:
    """Summarizes one bounded sweep-validation execution over a canonical traversal pattern."""

    name: str
    pattern: WorldMapSearchPattern
    coverage_bounds: WorldMapBounds
    stop_reason: str
    checkpoint_results: tuple[WorldMapSweepCheckpointResult, ...]

    def to_document(self) -> dict[str, object]:
        """Exports the sweep-validation result as a JSON-ready document."""

        return {
            "name": self.name,
            "pattern": self.pattern.kind.value,
            "coverage_bounds": _serialize_bounds(self.coverage_bounds),
            "stop_reason": self.stop_reason,
            "checkpoint_results": [result.to_document() for result in self.checkpoint_results],
        }


@dataclass(frozen=True, slots=True)
class WorldMapMovementCalibrationReport:
    """Carries the combined artifacts produced by the movement-calibration phases."""

    calibration_matrix: WorldMapCalibrationMatrixReport
    dead_zone_report: WorldMapDeadZoneReport | None = None
    lane_probe_reports: tuple[WorldMapLaneProbeReport, ...] = ()
    sweep_results: tuple[WorldMapSweepValidationResult, ...] = ()

    def to_document(self) -> dict[str, object]:
        """Exports the full movement-calibration report as a JSON-ready document."""

        return {
            "calibration_matrix": self.calibration_matrix.to_document(),
            "dead_zone_report": None if self.dead_zone_report is None else self.dead_zone_report.to_document(),
            "lane_probe_reports": [report.to_document() for report in self.lane_probe_reports],
            "sweep_results": [result.to_document() for result in self.sweep_results],
        }


@dataclass(slots=True)
class WorldMapMovementCalibrationService:
    """Runs the dedicated cardinal calibration, dead-zone verification, and sweep-observation validation loops."""

    screen_flows: ScreenFlowPlanner
    observation_service: "ObservationService | None" = None
    action_executor: WorldMapObservedActionExecutor | None = None
    survey_recorder: WorldMapSurveyRecorder | None = None
    search_service: WorldMapSearchService | None = None
    movement_step_budget: int = 8
    default_probe_ratios: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40)
    default_horizontal_lane_candidates: tuple[float, ...] = (0.50, 0.60, 0.70)
    default_vertical_lane_candidates: tuple[float, ...] = (0.40, 0.46, 0.52)

    def probe_swipe(
        self,
        observation: Observation,
        *,
        direction: WorldMapCardinalDirection,
        distance_ratio: float,
        label_prefix: str,
        lane_center_ratio: float | None = None,
        boundary_bounds: WorldMapBounds | None = None,
    ) -> tuple[WorldMapSwipeProbeResult, Observation]:
        """Executes one exact swipe probe and returns the classified result plus the freshest proven follow-up observation."""

        return self._probe_swipe(
            observation,
            direction=direction,
            distance_ratio=distance_ratio,
            label_prefix=label_prefix,
            lane_center_ratio=lane_center_ratio,
            boundary_bounds=boundary_bounds,
        )

    def run_cardinal_calibration(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        repeats_per_combination: int = 2,
        ratios: Sequence[float] | None = None,
        lane_candidates: Mapping[WorldMapCardinalDirection, Sequence[float]] | None = None,
    ) -> tuple[WorldMapCalibrationMatrixReport, Observation]:
        """Runs the formal cardinal calibration matrix from one stable starting viewport, returning to that viewport between trials."""

        if repeats_per_combination <= 0:
            raise SelectorResolutionError(
                "Cardinal calibration requires a positive repeats_per_combination value.",
                repeats_per_combination=repeats_per_combination,
            )
        current = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=observation,
            label_prefix=f"{label_prefix}_start",
        )
        origin_coordinate = _require_coordinate(current)
        entries: list[WorldMapCalibrationMatrixEntry] = []
        for direction in WorldMapCardinalDirection:
            resolved_lane_candidates = tuple(
                self._default_lane_candidates(direction)
                if lane_candidates is None or direction not in lane_candidates
                else lane_candidates[direction]
            )
            for lane_index, lane_center_ratio in enumerate(resolved_lane_candidates):
                for ratio_index, ratio in enumerate(self.default_probe_ratios if ratios is None else ratios):
                    trial_results: list[WorldMapSwipeProbeResult] = []
                    for trial_index in range(repeats_per_combination):
                        current = self._coordinate_mover().move_to_coordinate(
                            current,
                            target_coordinate=origin_coordinate,
                            label_prefix=f"{label_prefix}_reset_{direction.value}_{lane_index}_{ratio_index}_{trial_index}",
                        )
                        probe, current = self._probe_swipe(
                            current,
                            direction=direction,
                            distance_ratio=float(ratio),
                            lane_center_ratio=lane_center_ratio,
                            label_prefix=f"{label_prefix}_{direction.value}_{lane_index}_{ratio_index}_{trial_index}",
                        )
                        trial_results.append(probe)
                    entries.append(
                        WorldMapCalibrationMatrixEntry(
                            direction=direction,
                            lane_center_ratio=lane_center_ratio,
                            distance_ratio=float(ratio),
                            input_source=trial_results[0].input_source,
                            trial_results=tuple(trial_results),
                        )
                    )
        current = self._coordinate_mover().move_to_coordinate(
            current,
            target_coordinate=origin_coordinate,
            label_prefix=f"{label_prefix}_finish_reset",
        )
        return WorldMapCalibrationMatrixReport(
            canonical_profiles=tuple(self._canonical_profiles()),
            entries=tuple(entries),
        ), current

    def run_dead_zone_verification(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        probe_coordinates: Sequence[tuple[int, int]],
        distance_ratio: float,
        bounds: WorldMapBounds,
        lane_center_ratios: Mapping[WorldMapCardinalDirection, float] | None = None,
    ) -> tuple[WorldMapDeadZoneReport, Observation]:
        """Runs dead-zone verification from multiple interior or boundary coordinates and classifies every zero-motion result."""

        current = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=observation,
            label_prefix=f"{label_prefix}_start",
        )
        probe_results: list[WorldMapSwipeProbeResult] = []
        for coordinate_index, probe_coordinate in enumerate(probe_coordinates):
            for direction_index, direction in enumerate(WorldMapCardinalDirection):
                current = self._coordinate_mover().move_to_coordinate(
                    current,
                    target_coordinate=probe_coordinate,
                    label_prefix=f"{label_prefix}_probe_start_{coordinate_index}_{direction_index}",
                )
                lane_center_ratio = None if lane_center_ratios is None else lane_center_ratios.get(direction)
                probe, current = self._probe_swipe(
                    current,
                    direction=direction,
                    distance_ratio=distance_ratio,
                    lane_center_ratio=lane_center_ratio,
                    boundary_bounds=bounds,
                    label_prefix=f"{label_prefix}_{coordinate_index}_{direction.value}",
                )
                probe_results.append(probe)
        return WorldMapDeadZoneReport(bounds=bounds, probe_results=tuple(probe_results)), current

    def run_lane_probe_sequence(
        self,
        observation: Observation,
        *,
        request: WorldMapLaneProbeRequest,
        label_prefix: str,
    ) -> tuple[WorldMapLaneProbeReport, Observation]:
        """Runs one anchored lane probe sequence by recentring before every probe to isolate lane-specific movement behavior."""

        current = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=observation,
            label_prefix=f"{label_prefix}_start",
        )
        probe_results: list[WorldMapSwipeProbeResult] = []
        for direction_index, direction in enumerate(request.probe_directions):
            for ratio_index, ratio in enumerate(request.distance_ratios):
                current = self._coordinate_mover().move_to_coordinate(
                    current,
                    target_coordinate=request.anchor_coordinate,
                    label_prefix=f"{label_prefix}_anchor_{direction_index}_{ratio_index}",
                    boundary_bounds=request.boundary_bounds,
                )
                lane_center_ratio = None
                if request.lane_center_ratios is not None:
                    lane_center_ratio = request.lane_center_ratios.get(direction)
                probe, current = self._probe_swipe(
                    current,
                    direction=direction,
                    distance_ratio=ratio,
                    lane_center_ratio=lane_center_ratio,
                    boundary_bounds=request.boundary_bounds,
                    label_prefix=f"{label_prefix}_{direction.value}_{ratio_index}",
                )
                probe_results.append(probe)
        return (
            WorldMapLaneProbeReport(
                name=request.name,
                anchor_coordinate=request.anchor_coordinate,
                probe_results=tuple(probe_results),
            ),
            current,
        )

    def validate_sweep(
        self,
        observation: Observation,
        *,
        request: WorldMapSweepValidationRequest,
        label_prefix: str,
    ) -> tuple[WorldMapSweepValidationResult, Observation]:
        """Validates that repeated checkpoint movement plus observation stays stable over one bounded sweep route."""

        current = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=observation,
            label_prefix=f"{label_prefix}_start",
        )
        search_request = WorldMapSearchRequest(
            matcher=lambda _sighting: False,
            stop_policy=WorldMapSearchStopPolicy(max_checkpoints=request.max_checkpoints),
            pattern=request.pattern,
            checkpoint_spacing=request.checkpoint_spacing,
            origin=request.origin,
            boundary=request.boundary,
        )
        search_service = self._search_service()
        plan = search_service.resolve_plan(search_request, current)
        runtime_state: dict[str, object] = {}
        checkpoint_results: list[WorldMapSweepCheckpointResult] = []
        stop_reason = "route_exhausted"
        for checkpoint in plan.route:
            if request.max_checkpoints is not None and len(checkpoint_results) >= request.max_checkpoints:
                stop_reason = "checkpoint_budget_exhausted"
                break
            current = search_service.move_to_checkpoint(
                current,
                plan=plan,
                checkpoint=checkpoint,
                label_prefix=f"{label_prefix}_move_{checkpoint.route_index}",
                runtime_state=runtime_state,
            )
            recorded_observation = self._record_checkpoint(
                label=f"{label_prefix}_checkpoint_{checkpoint.route_index}",
                observation=current,
            )
            evidence = _coordinate_evidence(recorded_observation)
            delta_from_checkpoint = _checkpoint_delta(
                requested_coordinate=checkpoint.coordinate,
                observed_coordinate=evidence.coordinate,
            )
            within_tolerance = (
                False
                if evidence.coordinate is None
                else _coordinate_within_tolerance(
                    evidence.coordinate,
                    checkpoint.coordinate,
                    tolerance=search_service.coordinate_mover_for_runtime().navigator.focus_tolerance,
                )
            )
            checkpoint_results.append(
                WorldMapSweepCheckpointResult(
                    checkpoint=checkpoint,
                    evidence=evidence,
                    usable_observation=evidence.coordinate is not None,
                    delta_from_checkpoint=delta_from_checkpoint,
                    within_tolerance=within_tolerance,
                )
            )
            current = recorded_observation
        return WorldMapSweepValidationResult(
            name=request.name,
            pattern=request.pattern,
            coverage_bounds=plan.coverage_bounds,
            stop_reason=stop_reason,
            checkpoint_results=tuple(checkpoint_results),
        ), current

    def run_full_calibration(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        dead_zone_probe_coordinates: Sequence[tuple[int, int]] = (),
        dead_zone_bounds: WorldMapBounds | None = None,
        dead_zone_distance_ratio: float = 0.20,
        lane_probe_requests: Sequence[WorldMapLaneProbeRequest] = (),
        sweep_requests: Sequence[WorldMapSweepValidationRequest] = (),
    ) -> tuple[WorldMapMovementCalibrationReport, Observation]:
        """Runs the implemented movement-calibration phases and returns one combined report plus the freshest observation."""

        calibration_matrix, current = self.run_cardinal_calibration(
            observation,
            label_prefix=f"{label_prefix}_cardinal",
        )
        dead_zone_report: WorldMapDeadZoneReport | None = None
        lane_probe_reports: list[WorldMapLaneProbeReport] = []
        if dead_zone_probe_coordinates:
            if dead_zone_bounds is None:
                raise SelectorResolutionError(
                    "Dead-zone verification requires explicit bounds whenever probe coordinates are requested."
                )
            dead_zone_report, current = self.run_dead_zone_verification(
                current,
                label_prefix=f"{label_prefix}_dead_zone",
                probe_coordinates=dead_zone_probe_coordinates,
                distance_ratio=dead_zone_distance_ratio,
                bounds=dead_zone_bounds,
            )
        for lane_probe_index, lane_probe_request in enumerate(lane_probe_requests):
            lane_probe_report, current = self.run_lane_probe_sequence(
                current,
                request=lane_probe_request,
                label_prefix=f"{label_prefix}_lane_probe_{lane_probe_index}_{lane_probe_request.name}",
            )
            lane_probe_reports.append(lane_probe_report)
        sweep_results: list[WorldMapSweepValidationResult] = []
        for sweep_index, sweep_request in enumerate(sweep_requests):
            sweep_result, current = self.validate_sweep(
                current,
                request=sweep_request,
                label_prefix=f"{label_prefix}_sweep_{sweep_index}_{sweep_request.name}",
            )
            sweep_results.append(sweep_result)
        return WorldMapMovementCalibrationReport(
            calibration_matrix=calibration_matrix,
            dead_zone_report=dead_zone_report,
            lane_probe_reports=tuple(lane_probe_reports),
            sweep_results=tuple(sweep_results),
        ), current

    def _probe_swipe(
        self,
        observation: Observation,
        *,
        direction: WorldMapCardinalDirection,
        distance_ratio: float,
        label_prefix: str,
        lane_center_ratio: float | None = None,
        boundary_bounds: WorldMapBounds | None = None,
    ) -> tuple[WorldMapSwipeProbeResult, Observation]:
        """Executes the underlying single-swipe probe and returns the classified result plus the freshest proven observation."""

        if distance_ratio <= 0:
            raise SelectorResolutionError(
                "World-map swipe probes require a positive distance ratio.",
                distance_ratio=distance_ratio,
            )
        current = _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=observation,
            label_prefix=f"{label_prefix}_before",
        )
        action = self.screen_flows.world_map_navigator.build_cardinal_probe_action(
            direction,
            distance_ratio=distance_ratio,
            lane_center_ratio=lane_center_ratio,
            reason=f"{label_prefix}_{direction.value}_probe",
            observe_after=True,
        )
        if current.image_size is None:
            raise SelectorResolutionError(
                "World-map swipe probes require observations that expose image_size so exact swipe points can be recorded."
            )
        after = self._execute_probe_action(
            current,
            action=action,
            label_prefix=label_prefix,
        )
        before_evidence = _coordinate_evidence(current)
        after_evidence = _coordinate_evidence(after)
        delta = _delta(before_evidence.coordinate, after_evidence.coordinate)
        return (
            WorldMapSwipeProbeResult(
                direction=direction,
                lane_center_ratio=_resolved_lane_center_ratio(direction=direction, action=action),
                distance_ratio=distance_ratio,
                input_source=action.input_source,
                swipe_points=resolve_swipe_points_for_action(
                    width=current.image_size[0],
                    height=current.image_size[1],
                    action=action,
                ),
                before=before_evidence,
                after=after_evidence,
                delta=delta,
                classification=classify_world_map_cardinal_delta(
                    direction=direction,
                    before_coordinate=before_evidence.coordinate,
                    delta=delta,
                    boundary_bounds=boundary_bounds,
                ),
                near_boundary=is_world_map_coordinate_near_boundary(
                    direction=direction,
                    coordinate=before_evidence.coordinate,
                    bounds=boundary_bounds,
                ),
            ),
            after,
        )

    def _execute_probe_action(
        self,
        observation: Observation,
        *,
        action: object,
        label_prefix: str,
    ) -> Observation:
        """Executes the probe action and refreshes the follow-up observation into a proven world-map surface."""

        if self.action_executor is None or self.observation_service is None:
            raise SelectorResolutionError("World-map movement calibration requires observation_service and action_executor.")
        after = self.action_executor.execute_actions(
            [action],
            observation,
            observe=lambda label, request=None: self.observation_service.observe(f"{label_prefix}_{label}", request=request),
        ).observation
        return _require_proven_world_map_observation(
            observation_service=self.observation_service,
            observation=after,
            label_prefix=f"{label_prefix}_after",
        )

    def _record_checkpoint(self, *, label: str, observation: Observation) -> Observation:
        """Records one checkpoint through the canonical recorder without forcing a redundant recapture when the observation is already usable."""

        if self.survey_recorder is None:
            raise SelectorResolutionError("World-map movement calibration requires a survey recorder for sweep validation.")
        recorded = self.survey_recorder.record_checkpoint(label, observation)
        return observation if recorded.capture is None else recorded.capture.observation

    def _coordinate_mover(self) -> WorldMapCoordinateMover:
        """Returns the canonical coordinate mover shared with the reusable search engine."""

        search_service = self._search_service()
        if search_service.coordinate_mover is None:
            search_service.movement_step_budget = self.movement_step_budget
        return search_service.coordinate_mover_for_runtime()

    def _search_service(self) -> WorldMapSearchService:
        """Returns the wired search service or one temporary search service sharing the same runtime dependencies."""

        if self.search_service is not None:
            if self.search_service.coordinate_mover is None:
                self.search_service.movement_step_budget = self.movement_step_budget
            return self.search_service
        if self.survey_recorder is None:
            raise SelectorResolutionError("World-map movement calibration requires a survey recorder for sweep planning.")
        return WorldMapSearchService(
            screen_flows=self.screen_flows,
            observation_service=self.observation_service,
            action_executor=self.action_executor,
            survey_recorder=self.survey_recorder,
            movement_step_budget=self.movement_step_budget,
        )

    def _canonical_profiles(self) -> Sequence[WorldMapCanonicalCardinalProfile]:
        """Returns the currently wired canonical cardinal profiles so the report documents the active runtime defaults."""

        profiles: list[WorldMapCanonicalCardinalProfile] = []
        for direction in WorldMapCardinalDirection:
            action = self.screen_flows.world_map_navigator.build_cardinal_probe_action(
                direction,
                distance_ratio=0.20,
                reason=f"document_{direction.value}_profile",
                observe_after=False,
            )
            profiles.append(
                WorldMapCanonicalCardinalProfile(
                    direction=direction,
                    lane_center_ratio=_resolved_lane_center_ratio(direction=direction, action=action),
                    input_source=action.input_source,
                )
            )
        return profiles

    def _default_lane_candidates(self, direction: WorldMapCardinalDirection) -> Sequence[float]:
        """Returns the default lane candidates for the requested direction's active axis."""

        if direction in {WorldMapCardinalDirection.LEFT, WorldMapCardinalDirection.RIGHT}:
            return self.default_horizontal_lane_candidates
        return self.default_vertical_lane_candidates


def _coordinate_evidence(observation: Observation) -> WorldMapObservedCoordinateEvidence:
    """Builds one reusable coordinate-parser evidence record from the observation when world-map viewport data is available."""

    surface = observation.spatial_surface
    if surface is None or surface.surface_type != SpatialSurfaceType.WORLD_MAP:
        return WorldMapObservedCoordinateEvidence(
            coordinate=None,
            coordinate_text=None,
            artifact_path=observation.artifact_path,
        )
    coordinate_text = surface.metadata.get("coordinate_text")
    return WorldMapObservedCoordinateEvidence(
        coordinate=surface.viewport.coordinate,
        coordinate_text=None if coordinate_text is None else str(coordinate_text),
        artifact_path=observation.artifact_path,
    )


def _require_coordinate(observation: Observation) -> tuple[int, int]:
    """Returns the required parsed viewport coordinate from one proven world-map observation."""

    surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
    coordinate = surface.viewport.coordinate
    if coordinate is None:
        raise SelectorResolutionError("World-map movement calibration requires coordinate-addressable world-map observations.")
    return coordinate


def _delta(
    before_coordinate: tuple[int, int] | None,
    after_coordinate: tuple[int, int] | None,
) -> tuple[int, int] | None:
    """Returns the parsed viewport delta when both observations exposed usable coordinates."""

    if before_coordinate is None or after_coordinate is None:
        return None
    return after_coordinate[0] - before_coordinate[0], after_coordinate[1] - before_coordinate[1]


def _checkpoint_delta(
    *,
    requested_coordinate: tuple[int, int],
    observed_coordinate: tuple[int, int] | None,
) -> tuple[int, int] | None:
    """Returns the observed-minus-requested checkpoint delta when parser evidence is available."""

    if observed_coordinate is None:
        return None
    return observed_coordinate[0] - requested_coordinate[0], observed_coordinate[1] - requested_coordinate[1]


def _resolved_lane_center_ratio(*, direction: WorldMapCardinalDirection, action: object) -> float:
    """Returns the lane ratio encoded on the emitted probe action for the direction's orthogonal safe lane."""

    if direction in {WorldMapCardinalDirection.LEFT, WorldMapCardinalDirection.RIGHT}:
        return float(getattr(action, "start_y_ratio"))
    return float(getattr(action, "start_x_ratio"))


def _serialize_bounds(bounds: WorldMapBounds) -> dict[str, int]:
    """Exports one inclusive bounds object as a JSON-ready mapping."""

    return {
        "min_x": bounds.min_x,
        "min_y": bounds.min_y,
        "max_x": bounds.max_x,
        "max_y": bounds.max_y,
    }
