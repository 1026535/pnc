"""Runs the dedicated live world-map movement calibration workflow and persists one JSON report."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.automation.engine.task import TaskPreflight
from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldMapCardinalDirection
from pnc_automation.app.pnc.navigation.world_map_movement_calibration import (
    WorldMapMovementCalibrationReport,
    WorldMapSweepValidationRequest,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapBounds,
    WorldMapEdge,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
)

_WORLD_MAP_PREFLIGHT_MAX_STEPS = 20


def main() -> None:
    """Executes the requested live calibration run and prints the persisted report path."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"), help="Path to the runtime config file.")
    parser.add_argument("--account", default="mega_old_acc", help="Configured account id to validate.")
    parser.add_argument("--label", default="world_map_movement_calibration", help="Artifact label stem for this run.")
    parser.add_argument("--repeats", type=int, default=1, help="Probe repeats per direction/lane/ratio combination.")
    parser.add_argument("--ratios", default="0.10,0.20", help="Comma-separated swipe ratios for the live cardinal calibration matrix.")
    parser.add_argument("--local-radius", type=int, default=6, help="Local radius used for dead-zone and sweep validation.")
    parser.add_argument("--checkpoint-spacing", type=int, default=6, help="Checkpoint spacing for dead-zone and sweep validation.")
    arguments = parser.parse_args()

    application = build_application_runner(Path(arguments.config))
    prepare_result = application.script_runner.prepare_account_session(account_id=arguments.account)
    if not all(step.status.value == "success" for step in prepare_result.steps):
        raise AssertionError(f"Preparation failed: {prepare_result.steps}")
    account = application.script_runner.config.require_account(arguments.account)
    runtime = application.script_runner.build_connected_runtime(account=account)
    runner = application.script_runner.build_connected_automation_runner(account=account)
    runtime.world_map_movement_calibration_service.movement_step_budget = 12
    try:
        world_map = _ensure_world_map(runner=runner, account=account, label_prefix=f"{arguments.label}_ensure_world_map")
    except Exception as error:  # pragma: no cover - live-only fallback
        document = {"calibration_matrix": None, "dead_zone_report": None, "sweep_results": [], "errors": [f"ensure_world_map: {error}"]}
        stored = runtime.world_map_movement_calibration_store.persist(
            artifact_directory=runtime.observation_service.artifact_directory,
            label=arguments.label,
            captured_at=datetime.now(tz=UTC),
            document=document,
        )
        print(stored.path)
        raise SystemExit(1)
    viewport_coordinate = world_map.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate
    if viewport_coordinate is None:
        raise AssertionError("World-map calibration requires a coordinate-addressable viewport.")
    local_bounds = WorldMapBounds(
        min_x=max(0, viewport_coordinate[0] - arguments.local_radius),
        min_y=max(0, viewport_coordinate[1] - arguments.local_radius),
        max_x=viewport_coordinate[0] + arguments.local_radius,
        max_y=viewport_coordinate[1] + arguments.local_radius,
    )
    probe_coordinates = (
        (local_bounds.min_x, local_bounds.min_y),
        (viewport_coordinate[0], viewport_coordinate[1]),
        (local_bounds.max_x, local_bounds.max_y),
    )
    ratios = tuple(float(segment.strip()) for segment in arguments.ratios.split(",") if segment.strip() != "")
    lane_candidates = _canonical_lane_candidates(runtime)
    errors: list[str] = []
    calibration_matrix = None
    dead_zone_report = None
    sweep_results: list[object] = []
    current = world_map
    try:
        calibration_matrix, current = runtime.world_map_movement_calibration_service.run_cardinal_calibration(
            current,
            label_prefix=f"{arguments.label}_cardinal",
            repeats_per_combination=arguments.repeats,
            ratios=ratios,
            lane_candidates=lane_candidates,
        )
    except Exception as error:  # pragma: no cover - live-only fallback
        errors.append(f"cardinal_calibration: {error}")
        current = _ensure_world_map(runner=runner, account=account, label_prefix=f"{arguments.label}_recover_after_cardinal")
    try:
        dead_zone_report, current = runtime.world_map_movement_calibration_service.run_dead_zone_verification(
            current,
            label_prefix=f"{arguments.label}_dead_zone",
            probe_coordinates=probe_coordinates,
            distance_ratio=ratios[0],
            bounds=local_bounds,
            lane_center_ratios={direction: candidates[0] for direction, candidates in lane_candidates.items()},
        )
    except Exception as error:  # pragma: no cover - live-only fallback
        errors.append(f"dead_zone_verification: {error}")
        current = _ensure_world_map(runner=runner, account=account, label_prefix=f"{arguments.label}_recover_after_dead_zone")
    for name, pattern, origin, boundary in (
        (
            "row_major",
            WorldMapSearchPattern.row_major_sweep(),
            WorldMapSearchOrigin.current_viewport(),
            WorldMapSearchBoundary.rectangle(
                min_coordinate=(local_bounds.min_x, local_bounds.min_y),
                max_coordinate=(local_bounds.max_x, local_bounds.max_y),
            ),
        ),
        (
            "expanding_ring",
            WorldMapSearchPattern.expanding_ring(),
            WorldMapSearchOrigin.current_viewport(),
            WorldMapSearchBoundary.radius_from_origin(arguments.local_radius),
        ),
        (
            "edge_band",
            WorldMapSearchPattern.edge_band_sweep(),
            WorldMapSearchOrigin.map_edge_reference(WorldMapEdge.LEFT),
            WorldMapSearchBoundary.edge_band(
                map_bounds=local_bounds,
                band_width_units=arguments.checkpoint_spacing,
                edges=(WorldMapEdge.LEFT, WorldMapEdge.TOP),
            ),
        ),
    ):
        try:
            current = _ensure_world_map(
                runner=runner,
                account=account,
                label_prefix=f"{arguments.label}_recover_before_{name}",
                start_observation=current,
            )
            sweep_result, current = runtime.world_map_movement_calibration_service.validate_sweep(
                current,
                request=WorldMapSweepValidationRequest(
                    name=name,
                    pattern=pattern,
                    origin=origin,
                    boundary=boundary,
                    checkpoint_spacing=arguments.checkpoint_spacing,
                    max_checkpoints=3,
                ),
                label_prefix=f"{arguments.label}_{name}",
            )
            sweep_results.append(sweep_result)
        except Exception as error:  # pragma: no cover - live-only fallback
            errors.append(f"{name}: {error}")
            current = _ensure_world_map(runner=runner, account=account, label_prefix=f"{arguments.label}_recover_after_{name}")
    if calibration_matrix is not None and dead_zone_report is not None and len(sweep_results) == 3 and not errors:
        document = WorldMapMovementCalibrationReport(
            calibration_matrix=calibration_matrix,
            dead_zone_report=dead_zone_report,
            sweep_results=tuple(sweep_results),
        ).to_document()
    else:
        document = {
            "calibration_matrix": None if calibration_matrix is None else calibration_matrix.to_document(),
            "dead_zone_report": None if dead_zone_report is None else dead_zone_report.to_document(),
            "sweep_results": [result.to_document() for result in sweep_results],
            "errors": errors,
        }
    stored = runtime.world_map_movement_calibration_store.persist(
        artifact_directory=runtime.observation_service.artifact_directory,
        label=arguments.label,
        captured_at=datetime.now(tz=UTC),
        document=document,
    )
    print(stored.path)
    if errors:
        raise SystemExit(1)


def _canonical_lane_candidates(runtime: object) -> dict[WorldMapCardinalDirection, tuple[float, ...]]:
    """Returns the currently wired canonical lane ratio for each cardinal direction as a one-candidate calibration set."""

    lanes: dict[WorldMapCardinalDirection, tuple[float, ...]] = {}
    for direction in WorldMapCardinalDirection:
        action = runtime.flow_planner.world_map_navigator.build_cardinal_probe_action(
            direction,
            distance_ratio=0.20,
            reason=f"document_{direction.value}_lane",
            observe_after=False,
        )
        lane_ratio = float(action.start_y_ratio) if direction in {WorldMapCardinalDirection.LEFT, WorldMapCardinalDirection.RIGHT} else float(action.start_x_ratio)
        lanes[direction] = (lane_ratio,)
    return lanes


def _ensure_world_map(
    *,
    runner: AutomationRunner,
    account: object,
    label_prefix: str,
    start_observation: Observation | None = None,
) -> Observation:
    """Returns a fresh world-map observation whose spatial viewport parsed successfully."""

    return runner.prove_preflight_state(
        account,
        TaskPreflight.WORLD_MAP,
        label_prefix=label_prefix,
        start_observation=start_observation,
        max_steps=_WORLD_MAP_PREFLIGHT_MAX_STEPS,
    )
if __name__ == "__main__":
    main()
