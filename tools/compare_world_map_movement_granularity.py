"""Runs live direct-movement comparisons across multiple world-map granularity caps and persists one JSON report."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.script_runner import (
    configure_world_map_movement_budget,
    configure_world_map_movement_granularity,
)
from pnc_automation.app.automation.engine.task import TaskPreflight
from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.navigation.world_map_search import world_map_movement_trace_document

_WORLD_MAP_PREFLIGHT_MAX_STEPS = 20


def main() -> None:
    """Executes the requested live granularity comparison and prints the persisted report path."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"), help="Path to the runtime config file.")
    parser.add_argument("--account", default="157_farm", help="Configured account id to validate.")
    parser.add_argument(
        "--granularities",
        default="5,1",
        help="Comma-separated per-leg axis-delta caps to compare. Use 'none' for the uncapped mover.",
    )
    parser.add_argument("--delta-x", type=int, default=6, help="Requested X delta applied from each proven start viewport.")
    parser.add_argument("--delta-y", type=int, default=0, help="Requested Y delta applied from each proven start viewport.")
    parser.add_argument("--movement-step-budget", type=int, default=20, help="Step budget applied to the shared world-map mover.")
    parser.add_argument("--label", default="world_map_movement_granularity_compare", help="Artifact label stem for this run.")
    arguments = parser.parse_args()

    application = build_application_runner(Path(arguments.config))
    prepare_result = application.script_runner.prepare_account_session(account_id=arguments.account)
    if not all(step.status.value == "success" for step in prepare_result.steps):
        raise AssertionError(f"Preparation failed: {prepare_result.steps}")
    account = application.script_runner.config.require_account(arguments.account)
    connected = application.script_runner.build_connected_runtime_bundle(account=account)
    runtime = connected.runtime
    runner = connected.runner
    configure_world_map_movement_budget(runtime, movement_step_budget=arguments.movement_step_budget)

    comparison_results: list[dict[str, object]] = []
    errors: list[str] = []
    for comparison_index, granularity in enumerate(_parse_granularities(arguments.granularities)):
        configure_world_map_movement_granularity(runtime, max_axis_delta_per_leg=granularity)
        runtime_state: dict[str, object] = {}
        started_at = datetime.now(tz=UTC)
        start = None
        end = None
        start_coordinate = None
        requested_target = None
        end_coordinate = None
        error_message = None
        try:
            start = runner.prove_preflight_state(
                account,
                TaskPreflight.WORLD_MAP,
                label_prefix=f"{arguments.label}_{comparison_index}_start",
                max_steps=_WORLD_MAP_PREFLIGHT_MAX_STEPS,
            )
            start_coordinate = start.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate
            if start_coordinate is None:
                raise AssertionError("World-map granularity comparison requires a coordinate-addressable viewport.")
            requested_target = (start_coordinate[0] + arguments.delta_x, start_coordinate[1] + arguments.delta_y)
            end = runtime.world_map_search_service.coordinate_mover_for_runtime().move_to_coordinate(
                start,
                target_coordinate=requested_target,
                label_prefix=f"{arguments.label}_{comparison_index}_move",
                runtime_state=runtime_state,
            )
            end_coordinate = end.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate
        except Exception as error:  # pragma: no cover - live-only fallback
            error_message = str(error)
            errors.append(f"granularity={granularity}: {error}")
        trace_document = world_map_movement_trace_document(runtime_state)
        comparison_results.append(
            {
                "granularity": granularity,
                "start_coordinate": (
                    None if start_coordinate is None else [start_coordinate[0], start_coordinate[1]]
                ),
                "requested_target": (
                    None if requested_target is None else [requested_target[0], requested_target[1]]
                ),
                "end_coordinate": None if end_coordinate is None else [end_coordinate[0], end_coordinate[1]],
                "delta": (
                    None
                    if start_coordinate is None or end_coordinate is None
                    else [end_coordinate[0] - start_coordinate[0], end_coordinate[1] - start_coordinate[1]]
                ),
                "start_artifact_path": None if start is None or start.artifact_path is None else str(start.artifact_path),
                "end_artifact_path": None if end is None or end.artifact_path is None else str(end.artifact_path),
                "captured_at": started_at.isoformat(),
                "error": error_message,
                "movement_trace": trace_document["step_traces"],
            }
        )

    stored = runtime.world_map_movement_calibration_store.persist(
        artifact_directory=runtime.observation_service.artifact_directory,
        label=arguments.label,
        captured_at=datetime.now(tz=UTC),
        document={
            "account_id": arguments.account,
            "delta_x": arguments.delta_x,
            "delta_y": arguments.delta_y,
            "movement_step_budget": arguments.movement_step_budget,
            "errors": errors,
            "comparisons": comparison_results,
        },
    )
    print(stored.path)
    if errors:
        raise SystemExit(1)


def _parse_granularities(raw_value: str) -> tuple[int | None, ...]:
    """Parses the caller-provided granularity CSV into one ordered tuple of movement caps."""

    values: list[int | None] = []
    for segment in raw_value.split(","):
        normalized = segment.strip().lower()
        if normalized == "":
            continue
        if normalized == "none":
            values.append(None)
            continue
        values.append(int(normalized))
    if not values:
        raise ValueError("At least one movement granularity must be provided.")
    return tuple(values)


if __name__ == "__main__":
    main()
