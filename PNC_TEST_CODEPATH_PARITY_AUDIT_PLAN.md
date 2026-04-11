# PNC Test Codepath Parity Audit Plan

## 1. Purpose

This plan defines how to audit the test suite for a recurring risk:

- a test validates a helper, planner, shim, or diagnostic path,
- but the real runtime uses a different orchestration path,
- so the test can pass while production behavior remains unvalidated or drifts.

The immediate trigger is the world-map sweep validation issue:

- `WorldMapMovementCalibrationService.validate_sweep(...)` validates checkpoint movement through its own direct `WorldMapCoordinateMover` usage,
- while real search execution moves through `WorldMapSearchService.execute_search(...) -> _move_to_checkpoint(...) -> _coordinate_mover().move_to_coordinate(...)`.

That pattern is critical enough that we should audit all tests for similar self-validating or bypassed codepaths.

## 2. Goal

For each important behavior, prove one of these is true:

1. The test exercises the exact production entry point and canonical dependency wiring.
2. The test is intentionally a unit test for a lower-level helper, and a separate integration/contract test covers the production entry point that consumes that helper.
3. The helper is obsolete or non-canonical and should be deleted or converted into the production path.

The audit should not force every test to become an end-to-end test. It should ensure every unit-level helper test has production-path coverage above it.

## 3. Definitions

### 3.1 Production Path

A production path is the code entered by real automation scripts, tools, or live runtime flows.

Examples:

- `AutomationRunner.run(...)`
- `AutomationRunner.prove_preflight_state(...)`
- `ScriptRunner.build_connected_runtime(...)`
- `ScriptRunner.build_connected_automation_runner(...)`
- `WorldMapSearchService.execute_search(...)`
- task `plan(...)` / `verify(...)` through runner orchestration
- `ActionExecutor` / `ObservedActionExecutor` execution loops

### 3.2 Helper Path

A helper path is lower-level code called by production code, but not itself the canonical feature entry point.

Examples:

- `ScreenFlowPlanner.ensure_world_map_ready(...)`
- `WorldMapSearchService.resolve_plan(...)`
- `WorldMapCoordinateMover.move_to_coordinate(...)`
- navigator `plan_focus_coordinate(...)`
- direct recorder methods like `capture_checkpoint(...)` or `record_checkpoint(...)`

Helper tests are good, but they are not enough when runtime behavior depends on orchestration around the helper.

### 3.3 Diagnostic Path

A diagnostic path is tooling intended for calibration, exploration, or live debugging, not normal production execution.

Examples:

- `WorldMapMovementCalibrationService.probe_swipe(...)`
- `WorldMapMovementCalibrationService.run_cardinal_calibration(...)`
- `WorldMapMovementCalibrationService.run_dead_zone_verification(...)`
- `tools/run_world_map_movement_calibration.py`

Diagnostic tests should not be treated as proof that production search/runtime paths behave correctly unless they deliberately invoke the same production entry point.

## 4. Audit Method

For each feature area, create a small parity table with these columns:

- Behavior under test
- Production entry point
- Current test entry point
- Shared lower-level implementation
- Missing production-path coverage
- Required follow-up

Classify each test as:

- `Production-path`: enters the same top-level path as real runtime.
- `Contract`: tests a lower-level helper but also asserts the contract production depends on.
- `Helper-only`: useful unit coverage, but not proof of runtime behavior.
- `Diagnostic-only`: validates a tool/calibration path, not production behavior.
- `Bypass-risk`: test passes through a path that is meaningfully different from production.

Every `Helper-only`, `Diagnostic-only`, or `Bypass-risk` item must either:

- gain a production-path companion test,
- be explicitly documented as helper-only with no production claim,
- or drive a refactor that removes the duplicate path.

## 5. Initial High-Risk Audit Targets

### 5.1 World-map sweep and search movement

- Production entry point:
  - `WorldMapSearchService.execute_search(...)`
- Current related test paths:
  - `tests/test_world_map_search.py` uses `execute_search(...)` for several cases.
  - `tests/test_world_map_movement_calibration.py` uses `validate_sweep(...)`, which directly calls `WorldMapCoordinateMover`.
  - `tests/test_live_world_map_movement_calibration_smoke.py` uses `validate_sweep(...)`, not `execute_search(...)`.
- Risk:
  - Calibration sweep validation can pass while the real search loop uses a different runtime state and traversal orchestration.
- Required follow-up:
  - Add or update tests so sweep validation delegates checkpoint execution through the same canonical movement seam as `execute_search(...)`.
  - Add one production-path test proving `execute_search(...)` and any sweep validator share the same configured mover/runtime state.
  - Consider exposing a single public/internal traversal method instead of duplicating movement loops.

### 5.2 World-map movement calibration versus production movement

- Production entry point:
  - `WorldMapSearchService.execute_search(...)`
  - `WorldMapCoordinateMover.move_to_coordinate(...)` when used through search
- Current related test paths:
  - direct `probe_swipe(...)`
  - direct `run_cardinal_calibration(...)`
  - direct `run_dead_zone_verification(...)`
- Risk:
  - Diagnostic movement probes validate emitted gestures and parser evidence, but not necessarily the real corrective movement policy used during search.
- Required follow-up:
  - Keep probe/calibration tests as diagnostic-only.
  - Add production-path tests for reactive zero-delta handling and orthogonal-drift correction after those behaviors are implemented.
  - Ensure diagnostic results feed configuration or reporting, not hidden production heuristics.

### 5.3 Runner preflight and live tooling

- Production entry point:
  - `AutomationRunner.run(...)`
  - `AutomationRunner.prove_preflight_state(...)`
- Current related test paths:
  - `tests/test_automation_framework.py` covers `prove_preflight_state(...)`.
  - `tools/run_world_map_movement_calibration.py` builds both `ConnectedAccountRuntime` and a separate connected runner.
  - `tests/live_smoke_support.py` wraps runtime/runner construction.
- Risk:
  - Live tools can validate runner preflight while executing feature work through a separately built runtime object.
  - If runner/runtime wiring drifts, tests may prove navigation with one object graph and feature execution with another.
- Required follow-up:
  - Add a wiring parity test proving `build_connected_runtime(...)` and `build_connected_automation_runner(...)` share equivalent canonical dependencies where they are expected to.
  - Prefer one connected runtime bundle that exposes both feature services and runner execution, instead of rebuilding parallel runtime stacks.

### 5.4 Screen-flow planner helper tests versus task/runner execution

- Production entry point:
  - `AutomationRunner.run(...)`
  - task `plan(...)` and `verify(...)` through runner orchestration
- Current related test paths:
  - many `tests/test_flows_and_tasks.py` tests call `ScreenFlowPlanner` methods directly.
  - separate runner tests cover some preflight/recovery behavior.
- Risk:
  - Direct planner tests validate action lists, but not runner popup handling, unknown recovery, follow-up observation requests, retry budgets, or verification loops.
- Required follow-up:
  - Keep direct planner tests for action-contract details.
  - For each root navigation behavior, ensure at least one runner-level test proves the planner action is consumed through `execute_flow_until(...)` or `run(...)`.
  - Mark direct planner tests as helper-contract tests in comments/docstrings when they are not runtime proof.

### 5.5 Task unit tests versus full runner execution

- Production entry point:
  - `AutomationRunner.run(...)`
- Current related test paths:
  - task tests often call task `plan(...)` or `verify(...)` directly with synthetic observations.
  - some framework tests exercise runner orchestration with synthetic tasks.
- Risk:
  - Direct task tests can pass while runner preflight, retry, popup recovery, or task-local replan budgets fail.
- Required follow-up:
  - For each task with meaningful stateful flow, maintain:
    - direct task unit tests for local decision logic,
    - at least one runner-level scenario for the task's entry/preflight/replan/verify lifecycle.
  - Prioritize `GatheringTask`, `ResearchTask`, `BuildingUpgradeTask`, `OpenBuildingTask`, and chat/mail tasks.

### 5.6 Observation and action executor follow-up behavior

- Production entry point:
  - `ObservedActionExecutor.execute_actions(...)`
  - `ActionExecutor.execute_actions(...)`
  - `ObservationService.observe(...)`
- Current related test paths:
  - many tests instantiate executor classes directly with fakes.
  - capture/vision tests instantiate `ObservationBuilder` or `ObservationService` directly.
- Risk:
  - Direct executor tests are usually correct unit tests, but production behavior depends on the precise follow-up request and observation service mode passed by runner/script wiring.
- Required follow-up:
  - Keep unit tests direct.
  - Add targeted wiring tests whenever a production service changes follow-up request policy, artifact mode, or observed-action policy.
  - Audit tests that use `object()` placeholders for runtime dependencies and make sure they are not claiming production wiring coverage.

## 6. Concrete Test-Audit Checklist

For every test file, answer:

- Does this test call the production entry point or a helper?
- If helper-only, where is the production entry point covered?
- Does the test instantiate dependencies in the same way as `ScriptRunner` or `AutomationRunner`?
- Does it bypass popup recovery, unknown recovery, follow-up observation, retry budget, or artifact policy?
- Does it pass direct observations where production would recapture/re-observe?
- Does it validate the same runtime state sharing as production?
- Does it assert only the output shape, or also that the canonical dependency was used?

## 7. Recommended Implementation Steps

### Step 1. Add a test parity inventory

Create a document or generated table listing major test modules and their classification:

- production-path
- helper-contract
- diagnostic-only
- bypass-risk

Start with:

- `tests/test_world_map_search.py`
- `tests/test_world_map_movement_calibration.py`
- `tests/test_live_world_map_movement_calibration_smoke.py`
- `tests/test_automation_framework.py`
- `tests/test_flows_and_tasks.py`
- `tests/test_script_runner.py`
- `tests/test_capture_and_vision.py`

### Step 2. Fix the critical world-map sweep parity gap

Refactor so `validate_sweep(...)` and `execute_search(...)` share the same checkpoint movement implementation.

Then add a test that fails if `validate_sweep(...)` bypasses the search service's configured movement seam.

### Step 3. Add production-path companion tests for high-risk helpers

Prioritize helpers that control runtime orchestration:

- preflight proof
- unknown recovery
- world-map movement
- checkpoint ingestion
- popup recovery
- task-local replan budget

### Step 4. Mark diagnostic tests explicitly

Update docstrings for calibration/live diagnostic tests so they do not read as production search validation unless they call the production search path.

### Step 5. Remove or collapse duplicate execution paths

When a helper test exposes a duplicate path, prefer refactoring to one canonical implementation instead of adding more tests around both paths.

## 8. Success Criteria

This audit is complete when:

- every important helper-level test has a named production-path companion test or is clearly documented as helper-only,
- no diagnostic workflow is treated as production search/runtime proof,
- world-map sweep validation and search execution share the same checkpoint movement seam,
- runtime wiring tests prove connected tooling does not construct divergent object graphs,
- and future reviews can quickly answer: "Which production path does this test actually prove?"
