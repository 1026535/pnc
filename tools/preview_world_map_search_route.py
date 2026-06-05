"""Live-safe route preview and optional bounded execution for world-map traversal plans."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.task import TaskPreflight
from pnc_automation.app.pnc.navigation.world_map_search import (
    TraversalRotation,
    TraversalStridePolicy,
    WorldMapCoordinateDomain,
    WorldMapMapCorner,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchRequest,
    WorldMapSearchStopPolicy,
    WorldMapTraversalCorner,
)
from pnc_automation.core.errors import SelectorResolutionError

_WORLD_MAP_PREFLIGHT_MAX_STEPS = 8


def main() -> int:
    """Parses arguments, previews one route, and optionally executes the first bounded portion live."""

    parser = argparse.ArgumentParser(description="Preview and optionally execute a world-map traversal route.")
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"), help="Path to the runtime config file.")
    parser.add_argument("--account", required=True, help="Configured account id to use for the preview.")
    parser.add_argument(
        "--pattern",
        choices=("row_major", "serpentine", "expanding_ring", "perimeter", "shrinking_perimeter"),
        default="row_major",
        help="Traversal pattern to preview.",
    )
    parser.add_argument(
        "--origin",
        choices=("current_viewport", "self_territory", "explicit_coordinate", "map_corner"),
        default="current_viewport",
        help="Origin strategy for route planning.",
    )
    parser.add_argument("--origin-x", type=int, help="Explicit origin X when --origin=explicit_coordinate.")
    parser.add_argument("--origin-y", type=int, help="Explicit origin Y when --origin=explicit_coordinate.")
    parser.add_argument(
        "--corner",
        choices=("upper_left", "upper_right", "lower_left", "lower_right"),
        default="upper_left",
        help="Corner used by map-corner origins and perimeter patterns.",
    )
    parser.add_argument("--radius", type=int, help="Radius boundary around the resolved origin.")
    parser.add_argument("--full-map", action="store_true", help="Use the full known kingdom bounds as the search boundary.")
    parser.add_argument("--min-x", type=int, help="Rectangle boundary minimum X.")
    parser.add_argument("--min-y", type=int, help="Rectangle boundary minimum Y.")
    parser.add_argument("--max-x", type=int, help="Rectangle boundary maximum X.")
    parser.add_argument("--max-y", type=int, help="Rectangle boundary maximum Y.")
    parser.add_argument("--stride", type=int, help="Symmetric analyzed-checkpoint stride override.")
    parser.add_argument("--horizontal-stride", type=int, help="Horizontal analyzed-checkpoint stride override.")
    parser.add_argument("--vertical-stride", type=int, help="Vertical analyzed-checkpoint stride override.")
    parser.add_argument("--inset-x", type=int, help="Horizontal inset used by shrinking perimeter traversal.")
    parser.add_argument("--inset-y", type=int, help="Vertical inset used by shrinking perimeter traversal.")
    parser.add_argument(
        "--rotation",
        choices=("clockwise", "counterclockwise"),
        default="clockwise",
        help="Perimeter rotation direction.",
    )
    parser.add_argument("--head", type=int, default=8, help="Number of leading checkpoints to print.")
    parser.add_argument("--tail", type=int, default=8, help="Number of trailing checkpoints to print.")
    parser.add_argument(
        "--execute-first",
        type=int,
        default=0,
        help="Optionally execute the first N route steps after printing the preview.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose structured logging.")
    arguments = parser.parse_args()

    application = build_application_runner(Path(arguments.config), verbose=arguments.verbose)
    script_runner = application.script_runner
    account = script_runner.config.require_account(arguments.account)
    connected = script_runner.build_connected_runtime_bundle(account=account)
    observation = connected.runner.prove_preflight_state(
        account,
        TaskPreflight.WORLD_MAP,
        label_prefix="preview_world_map_search_route",
        max_steps=_WORLD_MAP_PREFLIGHT_MAX_STEPS,
    )
    request = _build_request(arguments)
    preview = connected.runtime.world_map_search_service.preview_route(
        request,
        observation,
        head=arguments.head,
        tail=arguments.tail,
    )
    print(json.dumps(preview, indent=2, sort_keys=True))

    if arguments.execute_first <= 0:
        return 0
    plan = connected.runtime.world_map_search_service.resolve_plan(request, observation)
    current = observation
    runtime_state: dict[str, object] = {}
    executed = []
    for step in plan.execution_plan.steps[: arguments.execute_first]:
        current = connected.runtime.world_map_search_service.move_to_checkpoint(
            current,
            plan=plan,
            step=step,
            label_prefix=f"preview_execute_{step.step_index}",
            runtime_state=runtime_state,
        )
        executed.append(
            {
                "step_index": step.step_index,
                "coordinate": [step.checkpoint.coordinate[0], step.checkpoint.coordinate[1]],
                "intent": step.traversal_segment_intent.value,
            }
        )
    print(json.dumps({"executed_steps": executed}, indent=2, sort_keys=True))
    return 0


def _build_request(arguments: argparse.Namespace) -> WorldMapSearchRequest:
    """Builds one route-preview search request from the parsed CLI arguments."""

    return WorldMapSearchRequest(
        matcher=lambda _sighting: False,
        stop_policy=WorldMapSearchStopPolicy(),
        pattern=_build_pattern(arguments),
        traversal_stride_policy=_build_stride_policy(arguments),
        origin=_build_origin(arguments),
        boundary=_build_boundary(arguments),
        coordinate_domain=WorldMapCoordinateDomain.puzzles_and_conquest(),
    )


def _build_pattern(arguments: argparse.Namespace) -> WorldMapSearchPattern:
    """Builds the requested high-level traversal pattern from CLI arguments."""

    corner = WorldMapTraversalCorner(arguments.corner)
    rotation = TraversalRotation(arguments.rotation)
    if arguments.pattern == "row_major":
        return WorldMapSearchPattern.row_major_sweep()
    if arguments.pattern == "serpentine":
        return WorldMapSearchPattern.serpentine_row_sweep()
    if arguments.pattern == "expanding_ring":
        return WorldMapSearchPattern.expanding_ring()
    if arguments.pattern == "perimeter":
        return WorldMapSearchPattern.perimeter_ring_sweep(start_corner=corner, rotation=rotation)
    return WorldMapSearchPattern.shrinking_perimeter_sweep(
        start_corner=corner,
        rotation=rotation,
        inset_x=arguments.inset_x,
        inset_y=arguments.inset_y,
    )


def _build_stride_policy(arguments: argparse.Namespace) -> TraversalStridePolicy:
    """Builds the requested stride override from CLI arguments."""

    if arguments.stride is not None:
        return TraversalStridePolicy.symmetric(arguments.stride)
    if arguments.horizontal_stride is not None or arguments.vertical_stride is not None:
        if arguments.horizontal_stride is None or arguments.vertical_stride is None:
            raise SelectorResolutionError(
                "Axis-specific stride overrides require both --horizontal-stride and --vertical-stride."
            )
        return TraversalStridePolicy.axis_specific(
            horizontal_stride_units=arguments.horizontal_stride,
            vertical_stride_units=arguments.vertical_stride,
        )
    return TraversalStridePolicy.viewport_default()


def _build_origin(arguments: argparse.Namespace) -> WorldMapSearchOrigin:
    """Builds the requested origin strategy from CLI arguments."""

    if arguments.origin == "current_viewport":
        return WorldMapSearchOrigin.current_viewport()
    if arguments.origin == "self_territory":
        return WorldMapSearchOrigin.self_territory()
    if arguments.origin == "map_corner":
        return WorldMapSearchOrigin.map_corner(WorldMapMapCorner(arguments.corner))
    if arguments.origin_x is None or arguments.origin_y is None:
        raise SelectorResolutionError(
            "Explicit-coordinate origins require both --origin-x and --origin-y."
        )
    return WorldMapSearchOrigin.explicit_coordinate((arguments.origin_x, arguments.origin_y))


def _build_boundary(arguments: argparse.Namespace) -> WorldMapSearchBoundary:
    """Builds the requested search boundary from CLI arguments."""

    if arguments.radius is not None:
        return WorldMapSearchBoundary.radius_from_origin(arguments.radius)
    if arguments.full_map:
        return WorldMapSearchBoundary.full_map(WorldMapCoordinateDomain.puzzles_and_conquest().bounds)
    rectangle_values = (arguments.min_x, arguments.min_y, arguments.max_x, arguments.max_y)
    if any(value is not None for value in rectangle_values):
        if any(value is None for value in rectangle_values):
            raise SelectorResolutionError(
                "Rectangle boundaries require --min-x, --min-y, --max-x, and --max-y together."
            )
        return WorldMapSearchBoundary.rectangle(
            min_coordinate=(arguments.min_x, arguments.min_y),
            max_coordinate=(arguments.max_x, arguments.max_y),
        )
    raise SelectorResolutionError(
        "Route preview requires one boundary: --radius, --full-map, or the explicit rectangle coordinates."
    )


if __name__ == "__main__":
    raise SystemExit(main())
