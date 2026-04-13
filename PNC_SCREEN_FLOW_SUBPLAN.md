# Step 4: Puzzles & Conquest Screen Flow Sub-Plan

## Status

Closed.

The screen-flow subplan no longer has a concrete executable backlog. The codebase already has one canonical implementation for reusable screen navigation:

- [`ScreenFlowPlanner`](/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/screen_flows.py)

The durable target architecture and promotion rules now live in:

- [PNC_SCREEN_FLOW_ARCHITECTURE.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_ARCHITECTURE.md)

## Closure Rationale

This plan used to carry both implementation intent and architectural ownership rules. That made it look active even after the concrete work moved into code and downstream feature plans.

Current state:

- reusable flow implementation is centralized in `ScreenFlowPlanner`,
- runner-owned task entry is centralized through `TaskPreflight`,
- world-map search/traversal is owned by the world-map search and spatial-navigation layers,
- selector maturity is owned by selector refinement,
- feature-specific behavior remains in feature plans and task implementations.

Keeping this as an active subplan would create a false backlog. The right artifact is an architecture note, not another plan to execute.

## Remaining Work

None in this subplan.

Future reusable navigation changes should be driven by concrete feature or bug work. When a reusable path is promoted, update [PNC_SCREEN_FLOW_ARCHITECTURE.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_ARCHITECTURE.md) and the relevant tests instead of reopening this plan.

## Validation

The closure was checked against the current codebase:

- live `context.flows.*` task calls resolve against `ScreenFlowPlanner`,
- the stale `GatheringTask` fallback call to nonexistent `ensure_world_map(...)` was replaced with `ensure_world_map_ready(...)`,
- focused flow/task coverage was added for the corrected gathering fallback,
- the full offline suite passed.
