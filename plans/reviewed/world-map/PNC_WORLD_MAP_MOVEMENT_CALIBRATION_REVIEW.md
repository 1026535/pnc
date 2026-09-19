# PNC World-Map Movement Calibration Review

## Scope

Reviewed commit `9234dbefad6141b6cd4ba695cc1008cfcae233ca` (`Implement world map movement calibration workflow`) against:

- `PNC_WORLD_MAP_SEARCH_SUBPLAN.md`
- `PNC_WORLD_MAP_MOVEMENT_CALIBRATION_SUBPLAN.md`

This review focuses on bugs, behavioral inconsistencies, missing validation, duplication, and clean simplification opportunities in the landed implementation.

## Validation Note

Targeted regression coverage run in the current workspace:

- `py -m unittest tests.test_world_map_movement_calibration tests.test_script_runner tests.test_automation_framework`
- `py -m unittest tests.test_capture_and_vision`
- `py -m unittest tests.test_flows_and_tasks tests.test_live_world_map_movement_calibration_smoke`

All of the above passed. The findings below are therefore primarily gaps in runtime behavior, calibration semantics, or workflow robustness that are not covered by the current tests.

## Findings

### 1. Dead-zone handling should be reactive at runtime; the diagnostic verifier also needs stable probe anchors

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:404-420`
- Problem:
  - Normal world-map search/sweep runtime should not proactively test for dead zones.
  - A calibrated swipe should be expected to move unless the map is at a real boundary.
  - Runtime should classify dead zones only after a swipe unexpectedly produces no coordinate movement.
  - `run_dead_zone_verification(...)` moves to each requested `probe_coordinate` once, then runs all four directional probes in sequence from the evolving `current` observation.
  - That means only the first direction actually starts from the requested anchor.
  - The second, third, and fourth probes start from wherever the previous swipe left the viewport.
- Why this matters:
  - Proactive dead-zone testing during normal runs would add avoidable runtime work and can turn calibration concerns into production behavior.
  - The correct production behavior is fail-fast/reactive: if a swipe yields `(0, 0)`, classify it as expected boundary stop only when the current coordinate is near the expected map edge; otherwise surface an interior-stall or parser-uncertain error.
  - The standalone diagnostic report is still useful, but its current outcome depends on probe order and prior swipes, which can turn one intended interior probe set into mixed interior/edge evidence.
- Clean fix:
  - Keep dead-zone verification as an explicit diagnostic/calibration workflow, not a normal search/runtime step.
  - In production movement, perform dead-zone classification only when a swipe fails to change coordinates.
  - For the diagnostic verifier, re-focus to the requested `probe_coordinate` before every directional probe, not only once per outer loop.
  - Keep the actual before-coordinate in the report, but make the requested anchor deterministic.
  - Add focused tests for both behaviors: runtime classifies only after a zero-delta swipe, and diagnostic probes for one anchor all begin from that same coordinate.

### 2. Cardinal movement should compensate orthogonal drift instead of failing it as an unexpected delta

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:713-733`
- Problem:
  - `_classify_probe(...)` only checks that the active axis moved with the expected sign.
  - It does not reject meaningful motion on the orthogonal axis.
  - A supposedly horizontal probe with a delta like `(6, 9)` is currently classified as a plain `MOVED` result with no explicit correction requirement.
- Why this matters:
  - The calibration workflow is trying to prove clean cardinal movement lanes.
  - Off-axis drift does not necessarily mean the swipe failed, because the intended axis can still move correctly.
  - But if runtime ignores the orthogonal drift, repeated checkpoint traversal can accumulate row/column error.
  - Treating drift as a hard `UNEXPECTED_DELTA` would also be too aggressive, because a simple corrective move in the opposite orthogonal direction can recover cleanly.
- Clean fix:
  - Split primary-axis validation from orthogonal-axis correction.
  - Keep failing only when the intended primary axis does not move with the expected sign, or when parser evidence is unusable.
  - When the primary axis succeeds but the orthogonal axis drifts beyond a small tolerated jitter threshold, classify/report it as moved-with-drift rather than `UNEXPECTED_DELTA`.
  - Add a bounded corrective movement step in the opposite direction of the unintended orthogonal movement.
  - Add unit tests proving horizontal drift is corrected with vertical movement, vertical drift is corrected with horizontal movement, and wrong-sign primary-axis movement still fails.

### 3. Sweep validation is not exercising the same canonical movement path as the real search loop

- Severity: Medium
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:445-469`
  - `pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:621-644`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1310-1316`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1437-1442`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1503-1513`
- Problem:
  - `validate_sweep(...)` uses `search_service.resolve_plan(...)` for planning, but it does not execute checkpoints through the search service's movement path.
  - It calls `self._coordinate_mover().move_to_coordinate(...)` directly, builds a fresh mover instance, and does not pass any shared `runtime_state` across checkpoints.
  - The canonical search loop does pass shared runtime state through `_move_to_checkpoint(...)`, which is where the world-map navigator carries movement calibration state across repeated moves.
- Why this matters:
  - The sweep validator is supposed to prove the same repeated checkpoint movement that search will later depend on.
  - Right now it is validating a similar but not identical execution path.
  - That creates an avoidable "validated in tooling, but not actually the same runtime behavior" risk.
- Clean fix:
  - Make sweep validation reuse one canonical checkpoint-traversal helper from `WorldMapSearchService`.
  - At minimum, thread one shared `runtime_state` through the entire sweep and route movement through the search service's configured `coordinate_mover`.
  - Prefer one shared traversal primitive over parallel implementations.

### 4. World-map search traversal must not re-run screen-flow world-map readiness at every checkpoint

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1274-1294`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1310-1320`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1422-1442`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1752-1785`
- Problem:
  - The intended ownership model is one proven world-map entry before search/traversal starts.
  - After that, checkpoint traversal is an in-surface world-map operation, not a repeated screen-flow transition.
  - Per-checkpoint movement may need to re-prove that the post-action observation is still a parsed world-map surface, but it should not invoke root screen-flow readiness/navigation as a normal step.
- Why this matters:
  - Re-running root readiness at every checkpoint would blur the screen-flow/search boundary that the world-map search plan is trying to enforce.
  - It can hide movement bugs behind repeated recovery/navigation behavior.
  - It also adds avoidable runtime cost during long sweeps.
- Clean fix:
  - Keep `TaskPreflight.WORLD_MAP` or explicit live-tool preflight as the single world-map entry proof before search starts.
  - Keep `WorldMapSearchService.execute_search(...)` fail-fast when the caller has not supplied or captured a proven world-map observation.
  - Inside checkpoint traversal, use only spatial-navigation/search-owned movement and bounded post-action world-map surface refresh.
  - Add a focused production-path test that proves a multi-checkpoint search does not call `ScreenFlowPlanner.ensure_world_map_ready(...)` per checkpoint.

### 5. The live calibration tool can lose the partial report if recovery after a failed phase also fails

- Severity: Medium
- Evidence:
  - `tools/run_world_map_movement_calibration.py:95-109`
  - `tools/run_world_map_movement_calibration.py:137-159`
- Problem:
  - Each phase is wrapped in `try/except`, but the recovery step inside the `except` block calls `_ensure_world_map(...)` directly.
  - If that recovery call also fails, the exception escapes before the final document is persisted.
  - The tool therefore has a failure mode where exactly the most interesting broken runs do not leave the intended partial calibration JSON behind.
- Why this matters:
  - This tool exists to make live calibration debuggable.
  - Losing the partial artifact on compound failure makes the workflow materially harder to diagnose.
- Clean fix:
  - Move persistence into one outer `try/finally` so a document is always written.
  - Wrap recovery itself in a helper that appends a recovery error instead of aborting the whole script.
  - Keep `current` nullable or preserve the last known observation when recovery fails.

### 6. The live sweep validations drift away from the original local test origin between phases

- Severity: Medium
- Evidence:
  - `tools/run_world_map_movement_calibration.py:110-159`
  - `tests/test_live_world_map_movement_calibration_smoke.py:88-127`
- Problem:
  - The tool captures one initial local area, but then it runs row-major, expanding-ring, and edge-band validations sequentially from the evolving `current` observation.
  - The row-major and ring phases both use `WorldMapSearchOrigin.current_viewport()`, so each later phase is centered on wherever the previous phase happened to end.
  - The edge-band phase also rebuilds its bounds from the already-shifted `current`.
- Why this matters:
  - The workflow reads like a comparison of traversal patterns over one shared local region.
  - In reality, the later sweeps are validating different origins and sometimes different local windows.
  - That makes the results less comparable and can hide pattern-specific problems behind starting-position drift.
- Clean fix:
  - Capture one canonical starting coordinate at the beginning of the run and use explicit origins and bounds for every sweep phase.
  - Or, re-center to that original coordinate before each validation segment.
  - Mirror the same behavior in the live smoke test so the test exercises the intended workflow.

## Direct Cleanup / Simplification Opportunities

### 7. The calibration service still has duplicate ownership for checkpoint traversal wiring

- Severity: Low
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:621-644`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1503-1513`
- Problem:
  - `WorldMapMovementCalibrationService` can be given a `search_service`, but it still rebuilds its own `WorldMapCoordinateMover` instead of reusing the search layer's canonical one.
  - That means any future injected mover customization can silently affect search but not calibration, or vice versa.
- Clean fix:
  - Promote the coordinate mover to an explicitly injected shared dependency, or expose one public canonical accessor from the search service and reuse it everywhere.
  - Keep exactly one canonical implementation per concept, especially for movement primitives under calibration.

### 8. Sweep validation diagnostics are weaker than they need to be for calibration work

- Severity: Low
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_movement_calibration.py:461-467`
- Problem:
  - A checkpoint is currently considered usable if it merely produced any parsed coordinate.
  - The result document does not explicitly record whether the observed coordinate matched the requested checkpoint within tolerance.
- Clean fix:
  - Add explicit checkpoint verification data such as:
    - observed coordinate
    - requested coordinate
    - delta from checkpoint
    - within-tolerance flag
  - Keep `usable_observation` for parser health, but also report movement correctness directly.

## Recommended Execution Order

1. Fix finding 1 first so runtime dead-zone handling is reactive and diagnostic dead-zone evidence is trustworthy.
2. Fix finding 2 next so bad lanes are not misreported as successful movement.
3. Fix finding 3 before relying on sweep validation as proof for broader search readiness.
4. Fix finding 4 so world-map search preserves the one-time preflight plus in-surface traversal ownership model.
5. Fix findings 5 and 6 together in the live tooling layer so calibration runs remain comparable and always leave artifacts.
5. Apply the cleanup items while touching the calibration/search seam again so the movement primitive stays canonical and DRY.
