"""Runs a bounded live production-policy world-map sweep and prints its canonical profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.script_runner import configure_world_map_movement_budget
from pnc_automation.app.automation.engine.task import TaskPreflight
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialObjectQuery, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.world_map_search import (
    TraversalStridePolicy,
    WorldMapCoordinateDomain,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchRequest,
    WorldMapSearchStopPolicy,
)
from pnc_automation.app.pnc.navigation.world_map_sweep import WorldMapSweepPolicy


def main() -> None:
    """Executes one bounded canonical production sweep against the selected live account."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"))
    parser.add_argument("--account", default="testing")
    parser.add_argument("--label", default="world_map_production_sweep")
    parser.add_argument("--radius", type=int, default=6)
    parser.add_argument("--spacing", type=int, default=6)
    parser.add_argument("--max-checkpoints", type=int, default=3)
    parser.add_argument("--max-pending-p2", type=int, default=4)
    parser.add_argument(
        "--diagnostic-synchronous-p2",
        action="store_true",
        help="Use the existing diagnostic exact-checkpoint policy for an A/B timing comparison.",
    )
    arguments = parser.parse_args()
    if arguments.radius <= 0 or arguments.spacing <= 0 or arguments.max_checkpoints <= 0:
        raise ValueError("radius, spacing, and max-checkpoints must be positive.")

    application = build_application_runner(Path(arguments.config))
    prepare_result = application.script_runner.prepare_account_session(account_id=arguments.account)
    if not all(step.status.value == "success" for step in prepare_result.steps):
        raise AssertionError(f"Preparation failed: {prepare_result.steps}")
    account = application.script_runner.config.require_account(arguments.account)
    connected = application.script_runner.build_connected_runtime_bundle(account=account)
    runtime = connected.runtime
    configure_world_map_movement_budget(runtime, movement_step_budget=12)
    start = connected.runner.prove_preflight_state(
        account,
        TaskPreflight.WORLD_MAP,
        label_prefix=f"{arguments.label}_preflight",
        max_steps=20,
    )
    coordinate = start.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate
    if coordinate is None:
        raise AssertionError("Production sweep requires a coordinate-addressable world-map viewport.")
    bounds = WorldMapCoordinateDomain.puzzles_and_conquest().local_bounds_around(
        coordinate,
        radius=arguments.radius,
    )
    result = runtime.world_map_search_service.execute_search(
        WorldMapSearchRequest(
            matcher=SpatialObjectQuery(
                surface_type=SpatialSurfaceType.WORLD_MAP,
                kind=SpatialObjectKind.RESOURCE_NODE,
            ),
            stop_policy=WorldMapSearchStopPolicy(max_checkpoints=arguments.max_checkpoints),
            pattern=WorldMapSearchPattern.serpentine_row_sweep(),
            traversal_stride_policy=TraversalStridePolicy.symmetric(arguments.spacing),
            origin=WorldMapSearchOrigin.explicit_coordinate(coordinate),
            boundary=WorldMapSearchBoundary.rectangle(
                min_coordinate=(bounds.min_x, bounds.min_y),
                max_coordinate=(bounds.max_x, bounds.max_y),
            ),
            sweep_policy=(
                WorldMapSweepPolicy.debug_exact_checkpoint()
                if arguments.diagnostic_synchronous_p2
                else WorldMapSweepPolicy.production_full_map(
                    max_pending_p2_items=arguments.max_pending_p2,
                )
            ),
        ),
        label_prefix=arguments.label,
        start_observation=start,
        runtime_state={},
    )
    if result.execution_profile is None:
        raise AssertionError("Production sweep did not produce an execution profile.")
    print(json.dumps(result.execution_profile.to_document(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
