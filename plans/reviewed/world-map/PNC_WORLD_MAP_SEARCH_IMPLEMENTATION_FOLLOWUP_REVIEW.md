# PNC World-Map Search Implementation Follow-Up Review

## Scope

Reviewed commit `8d25aea2c344c99e383df2a9bde426c72e7f0312` (`PNC_WORLD_MAP_SEARCH_IMPLEMENTATION_PLAN.md`) against:

- `PNC_WORLD_MAP_SEARCH_IMPLEMENTATION_PLAN.md`
- the implemented runtime/search/traversal/diagnostics code paths
- the new route-preview and calibration tooling

## Validation

- Focused offline validation passed:
  - `py -3 -m unittest tests.test_world_map_search tests.test_world_map_traversal tests.test_world_map_movement_calibration tests.test_observation_artifact_policy tests.test_buffered_logging`
  - Result: `94` tests passed.
- Full offline discovery is still not clean in this workspace:
  - `py -3 -m unittest discover -s tests`
  - Result: `2` fixture-file errors in existing artifact-backed tests unrelated to this commit's world-map code paths.

## Findings

### 1. Failure-mode diagnostics are still lost for failing swipe traversal legs

- Severity: High
- Evidence:
  - [pnc_automation/app/runtime/observation_artifacts.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/runtime/observation_artifacts.py:91>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:1170>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:1182>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:1210>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:1255>)
- Problem:
  - The shared policy surface now defines `ObservationArtifactRoutine.FAILURE`, but the swipe traversal path never uses it.
  - Intermediate movement-proof observations are deliberately captured with `WORLD_MAP_MOVEMENT_PROOF`, which resolves to no routine artifacts.
  - If `_require_proven_world_map_observation(...)` fails or the cardinal delta is classified as unusable, the code raises before any failure-specific screenshot persistence or failure log emission happens.
  - `_log_step_timing(...)` only records completed steps, so the exact failing leg is also missing from the buffered diagnostics stream.
- Why it matters:
  - This is the exact case the implementation plan said must stay immediate and preserved.
  - Broad sweep failures now lose the most useful frame and the most useful structured event.
- Clean fix:
  - Wrap one movement leg in `try/except` inside `WorldMapCoordinateMover.move_to_coordinate(...)`.
  - On failure, persist the freshest available observation with `ObservationArtifactRoutine.FAILURE`.
  - Emit one explicit failure diagnostic event before re-raising.
  - Keep the current selective routine behavior for successful intermediate proof steps.

### 2. Buffered-sequence logging is not flushed consistently outside `execute_search(...)`

- Severity: Medium
- Evidence:
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:2264>)
  - [pnc_automation/app/pnc/navigation/world_map_movement_calibration.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:578>)
  - [pnc_automation/app/pnc/navigation/world_map_movement_calibration.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:617>)
  - [tools/preview_world_map_search_route.py](</abs/path/c:/Users/lebel/pnc/tools/preview_world_map_search_route.py:107>)
- Problem:
  - `move_to_checkpoint(...)` now uses `DiagnosticLogMode.BUFFERED_SEQUENCE`.
  - `WorldMapSearchService.execute_search(...)` flushes in `finally`, which is correct.
  - `WorldMapMovementCalibrationService.validate_sweep(...)` flushes only on the success path after the loop.
  - `tools/preview_world_map_search_route.py` executes buffered steps but never flushes the runtime-state buffer at all.
- Why it matters:
  - Calibration failures drop all buffered movement logs from the steps that already happened.
  - The preview tool's optional execution mode silently suppresses the step logs that `--verbose` should expose.
- Clean fix:
  - Put buffered-log flushing in `try/finally` wherever a tool or service executes buffered traversal steps.
  - Reuse one tiny helper so preview, calibration, and future tooling do not each hand-roll flush behavior.

### 3. Broad sweeps still pay avoidable quadratic overhead through compatibility accessors

- Severity: Medium
- Evidence:
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:892>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:2155>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:2190>)
  - [pnc_automation/app/pnc/navigation/world_map_movement_calibration.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:578>)
  - [pnc_automation/app/pnc/navigation/world_map_movement_calibration.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:585>)
- Problem:
  - `WorldMapResolvedSearchPlan.route` rebuilds the flattened checkpoint tuple every time the property is read.
  - `execute_search(...)` passes `plan.route` into `_evaluate_stop_policy(...)` on every analyzed checkpoint, so long sweeps repeatedly rebuild the whole route.
  - `validate_sweep(...)` iterates `plan.route` and then re-scans `plan.execution_plan.steps` with `next(...)` for each checkpoint.
- Why it matters:
  - This is exactly the hot path the implementation was trying to make cheaper.
  - The current compatibility seams reintroduce unnecessary `O(n^2)` work on large sweeps.
- Clean fix:
  - Materialize `steps = plan.execution_plan.steps` once and, if still needed, `route = tuple(step.checkpoint for step in steps)` once.
  - Better yet, make auxiliary consumers iterate execution steps directly so the execution planner stays the single canonical owner.
  - Remove the repeated `next(...)` lookup from sweep validation.

### 4. Coordinate-jump and overview-seed movement still bypass the new selective artifact policy

- Severity: Medium
- Evidence:
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:2245>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:2290>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:2351>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:2384>)
  - [pnc_automation/app/pnc/navigation/world_map_search.py](</abs/path/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/world_map_search.py:2433>)
- Problem:
  - The swipe path uses the new shared routine-based artifact policy.
  - The coordinate-jump and overview-seed paths still call the search-service `_execute_actions(...)` helper, which always observes with the mode default and no routine override.
  - In `DEBUG`, every dialog open/fill/submit or overview open/recenter follow-up can still persist routine screenshots.
- Why it matters:
  - The implementation is no longer using one canonical artifact policy across movement families.
  - Broad searches that prefer non-swipe movement tools will keep the old artifact churn.
- Clean fix:
  - Thread an optional artifact-selection override through the search-service `_execute_actions(...)` helper.
  - Use the same shared routine defaults there that the swipe path already uses.
  - Pair this with finding 1 so failure cases in these paths also use the `FAILURE` routine.

## Recommended Fix Order

1. Fix failure-mode diagnostics first, because it affects the exact cases that are hardest to debug live.
2. Make buffered-log flushing consistent across calibration and preview tooling.
3. Remove the repeated route/step rebuilding in the hot sweep paths.
4. Extend the shared selective artifact policy to coordinate-jump and overview movement.

## DRY / Architecture Check

- Route planning and execution planning are now much cleaner than before.
- The main remaining drift is in auxiliary consumers that still treat checkpoints as the primary executable seam instead of `plan.execution_plan.steps`.
- Diagnostics policy is defined centrally, but failure handling and non-swipe consumers still need to be ported fully to that canonical policy.
