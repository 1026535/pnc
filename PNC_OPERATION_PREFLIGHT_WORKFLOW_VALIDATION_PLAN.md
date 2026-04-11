# PNC Operation Preflight Workflow Validation Plan

## 1. Purpose

This plan validates that every automation operation follows the intended workflow ownership model:

- screen/root entry is proven once before the operation body starts,
- the operation body performs only the work it owns,
- in-surface movement stays below screen flow,
- post-action observation proof is allowed,
- repeated root navigation inside operation loops is avoided unless the operation truly leaves its root screen.

This is separate from `PNC_TEST_CODEPATH_PARITY_AUDIT_PLAN.md`.

The parity audit asks:

- "Does the test exercise the same codepath as production?"

This workflow validation plan asks:

- "Does each operation use the correct preflight and ownership model?"

## 2. Canonical Workflow

### 2.1 Root-owned operations

For operations whose body truly starts from a stable root screen:

1. The task/tool declares or requests a preflight state.
2. The runner/tool proves that state before the operation body starts.
3. The operation body assumes that root contract and fails fast if it is violated.
4. Repeated internal loops do not call screen-flow root entry on every iteration.

Examples:

- `ResearchTask` starts from Home City.
- `GatheringTask` starts from World Map.
- world-map search starts from a proven `PNC_WORLD_MAP` observation.

### 2.2 Subflow-owned operations

For operations that may resume from meaningful in-progress screens:

1. The operation does not force unconditional root preflight.
2. The operation owns its subflow boundary explicitly.
3. It may navigate to a root only when that is the correct recovery or completion path.

Examples:

- `BuildingUpgradeTask`
- `OpenBuildingTask`

These should not be mechanically migrated to root preflight unless their ownership changes.

### 2.3 In-surface operations

For operations already inside a spatial surface:

1. Entry to the screen/surface is proven before traversal begins.
2. Movement and interaction are owned by spatial navigation or feature-specific in-surface logic.
3. The operation can refresh/re-prove the post-action observation as the same surface.
4. It should not repeatedly invoke screen-flow entry/readiness per movement step.

Examples:

- world-map checkpoint movement
- world-map search sweeps
- world-map visible-object tapping
- home-city camera/object focus once Home City surface ownership is established

## 3. World-Map Search Workflow Requirement

World-map search is the most important immediate case.

Required model:

1. Caller or runner proves `PNC_WORLD_MAP` before search starts.
2. `WorldMapSearchService.execute_search(...)` requires a proven world-map observation.
3. Checkpoint traversal uses search/spatial-navigation movement only.
4. After each swipe, the search layer may use bounded post-action refresh to prove a parsed world-map surface.
5. The checkpoint loop must not call `ScreenFlowPlanner.ensure_world_map_ready(...)` as routine per-step navigation.

Clean validation:

- Add a multi-checkpoint production-path test for `WorldMapSearchService.execute_search(...)`.
- Instrument or fake the screen-flow planner so the test fails if `ensure_world_map_ready(...)` is called during checkpoint traversal.
- Still allow `_require_proven_world_map_observation(...)` or equivalent post-action surface refresh when the follow-up frame is coarse/unknown/transient.

## 4. Operation Inventory To Validate

### 4.1 Runner-owned root preflight

Validate these operations use runner/tool preflight before the body:

- `ResearchTask`: `TaskPreflight.HOME_CITY`
- `GatheringTask`: `TaskPreflight.WORLD_MAP`
- external live calibration tool: explicit world-map preflight before calibration phases
- future world-map search consumers: explicit or runner-owned `WORLD_MAP` preflight

Expected tests:

- runner-level test proving the body receives the required root observation,
- negative test proving the body fails fast or runner preflight activates when the root is absent,
- no repeated root-entry call inside the operation's inner loop.

### 4.2 Not-root-owned subflow tasks

Validate these operations do not force root preflight unless redesigned:

- `BuildingUpgradeTask`
- `OpenBuildingTask`

Expected tests:

- can continue from owned in-progress screens,
- does not discard valid subflow state by forcing Home City first,
- uses root navigation only for completion/recovery when appropriate.

### 4.3 World-map in-surface operations

Validate these operations use one-time world-map entry plus in-surface movement:

- `WorldMapSearchService.execute_search(...)`
- `WorldMapMovementCalibrationService.validate_sweep(...)`
- `WorldMapMovementCalibrationService.run_cardinal_calibration(...)`
- `WorldMapMovementCalibrationService.run_dead_zone_verification(...)`
- `GatheringTask` visible-node interaction
- future relic/castle search consumers

Expected tests:

- start from proven `PNC_WORLD_MAP`,
- no routine per-checkpoint `ensure_world_map_ready(...)`,
- bounded post-action observation refresh is allowed,
- movement failures surface as movement/parser issues, not hidden root-navigation churn.

### 4.4 Home-city in-surface operations

Validate these operations use one-time Home City entry plus home-city spatial/navigation ownership:

- opening visible home-city objects,
- home-city object focus/search,
- building/research entry after root preflight.

Expected tests:

- screen-flow proves Home City before root-owned tasks,
- home-city camera movement/object focus does not become generic root navigation,
- missing home-city surface can trigger bounded same-root refresh, not broad recovery loops.

## 5. Audit Checklist

For each operation, record:

- Operation name
- Required preflight state, if any
- Whether it can resume from subflow screens
- Production entry point
- Inner loop owner
- Whether inner loop calls screen-flow root entry
- Whether post-action same-surface refresh exists
- Tests proving the intended workflow
- Missing tests or refactors

## 6. Required New Tests

### 6.1 World-map search does not re-enter world map per checkpoint

Add a test around `WorldMapSearchService.execute_search(...)` with multiple checkpoints.

The test should:

- start from a proven world-map observation,
- use a screen-flow planner test double that records calls to `ensure_world_map_ready(...)`,
- execute at least two checkpoint moves,
- assert the call count remains zero during traversal,
- assert post-action observations were still refreshed/proven through the search movement path.

### 6.2 Sweep validation uses the same in-surface traversal contract

After refactoring `validate_sweep(...)` to share the search checkpoint movement seam:

- assert sweep validation starts from a proven world-map observation,
- assert it does not invoke screen-flow root entry per checkpoint,
- assert it uses the same configured coordinate mover/runtime state as search.

### 6.3 Root-owned task bodies receive preflighted observations

For each root-owned task:

- build a runner scenario where the initial observation is not the required root,
- prove the runner reaches the required root,
- assert the task body only starts after the preflight proof.

### 6.4 Subflow-owned tasks are not forced back to root

For each subflow-owned task:

- start from an owned in-progress screen,
- assert the task can continue without root preflight,
- assert no unconditional root-navigation action is emitted first.

## 7. Refactor Guidance

When an operation violates the workflow:

- do not patch around it with another special case,
- decide who owns the boundary,
- move root entry to runner/tool preflight when the body starts from a root,
- keep in-surface traversal below screen flow,
- delete obsolete compatibility paths after migration.

## 8. Success Criteria

This workflow validation is complete when:

- every operation has an explicit entry/preflight contract,
- root-owned operations use runner/tool preflight once before the body,
- subflow-owned operations keep their subflow ownership and are not forced to root,
- world-map search checkpoint traversal never performs routine screen-flow world-map entry,
- in-surface movement failures surface as movement/parser failures,
- and tests exist for each operation category proving the workflow contract.
