# PNC Test Codepath Parity Audit Implementation Review

## Review Scope

Reviewed commit `8b004e0510da1fd074b4cb64559fe8e03d7f1a9f` (`Implement test codepath parity audit`) against its parent.

Validation performed:

- `py -3 -m unittest tests.test_script_runner tests.test_runner_end_to_end tests.test_discover_selector_registry_tool`
- `py -3 -m unittest discover -s tests`

Both commands passed. The plain `python` command currently resolves to the Windows Store alias on this machine, so `py -3` is the working Python launcher.

## Findings

### 1. `ConnectedAccountRuntime` And `_ConnectedRuntimeServices` Now Duplicate The Same Concept

Files:

- `pnc_automation/app/automation/engine/script_runner.py`

`ConnectedAccountRuntime` now includes `observed_action_executor`, making it effectively the same service graph as `_ConnectedRuntimeServices`. The private type and public type carry the same dependencies, and `_connected_account_runtime_from_services(...)` only copies fields from one dataclass into another.

Why this matters:

- The project guidelines call for one canonical implementation per concept.
- Adding future connected services now requires updating two dataclasses plus the projection helper.
- A missed field in the projection would create exactly the kind of tool/runtime parity drift this audit is trying to prevent.

Clean fix:

- Delete `_ConnectedRuntimeServices`.
- Make `_build_connected_runtime_services(...)` return `ConnectedAccountRuntime` directly, or rename it to `_build_connected_runtime_graph(...)` if the current name feels too internal.
- Change `_build_automation_runner_from_services(...)` to accept `ConnectedAccountRuntime`.
- Delete `_connected_account_runtime_from_services(...)`.
- Keep `ConnectedAutomationRuntime` as the small wrapper that pairs one `ConnectedAccountRuntime` with the runner built over that same object graph.

### 2. Required Observed-Executor Checks Are Repeated Across Live Tools

Files:

- `pnc_automation/app/automation/engine/script_runner.py`
- `tests/test_live_chat_workflow_smoke.py`
- `tools/discover_selector_registry.py`
- `tools/validate_navigation_selectors.py`

The commit exposes `observed_action_executor` on `ConnectedAccountRuntime`, then each live caller repeats the same nullable check before it can use the executor. The messages differ by caller, but the invariant is the same: some connected runtime operations require selector-backed observed actions.

Why this matters:

- It duplicates a fail-fast predicate and spreads ownership of the invariant to consumers.
- New live tools can forget the check and fail later with less useful errors.
- The optional default on `ConnectedAccountRuntime.observed_action_executor` makes manually constructed invalid runtimes easy in tests.

Clean fix:

- Add a canonical method on `ConnectedAccountRuntime`, for example `require_observed_action_executor(reason: str) -> ObservedActionExecutor`.
- Have live chat smoke, selector discovery, selector validation, and runner construction call that method.
- If all production `build_application_runner(...)` runtimes are expected to have a selector registry, consider splitting the recorder-only test setup from the connected live runtime contract instead of keeping the executor broadly optional.

### 3. Live Movement Calibration Smoke Uses A Different Search Movement Budget Than The Tool

Files:

- `tests/test_live_world_map_movement_calibration_smoke.py`
- `tools/run_world_map_movement_calibration.py`

The tool sets both movement budgets:

- `runtime.world_map_movement_calibration_service.movement_step_budget = 12`
- `runtime.world_map_search_service.movement_step_budget = 12`

The live smoke sets only the calibration service budget, then its `_move_to_coordinate(...)` helper directly calls `runtime.world_map_search_service.coordinate_mover_for_runtime().move_to_coordinate(...)`. That direct search-service move will use the search service's default budget of `8`, not the intended `12`.

Why this matters:

- The smoke and tool are meant to validate the same live calibration workflow shape.
- Recenter failures in the smoke can be caused by a smaller budget than the tool uses.
- The mismatch is subtle because calibration methods sometimes propagate their own budget to the shared search service, but the smoke's direct recenter helper bypasses that path.

Clean fix:

- In `LiveWorldMapMovementCalibrationSmokeTests.setUpClass`, also set `cls.runtime.world_map_search_service.movement_step_budget = 12`.
- Better yet, introduce one small runtime helper for "configure live world-map movement budget" and use it in both the tool and smoke test.
- Keep direct recentering through `WorldMapSearchService` if that is the intended production subpath, but configure the shared service explicitly.

### 4. The Audit Inventory Has A Stale Live-Chat Description

File:

- `PNC_TEST_CODEPATH_PARITY_AUDIT_PLAN.md`

Section 6 correctly says live chat smoke uses the canonical connected `ScreenFlowPlanner` and `ObservedActionExecutor`. Section 7 still describes `tests/test_live_chat_workflow_smoke.py` as using a "manually constructed executor".

Why this matters:

- The document is now the parity inventory. A stale row can send future reviewers toward a gap that was already closed.
- This is especially confusing because nearby sections already state the opposite.

Clean fix:

- Update the Section 7 row for `tests/test_live_chat_workflow_smoke.py` to say it uses the connected runtime observation service, flow planner, and observed-action executor, while still remaining a reusable workflow smoke rather than send-chat task proof.

### 5. Tool Rewiring Lacks Focused Tests For The New Live Runtime Contract

Files:

- `tools/discover_selector_registry.py`
- `tools/validate_navigation_selectors.py`
- `tests/test_discover_selector_registry_tool.py`

The commit changes selector discovery and selector validation to consume `observed_action_executor` and `flow_planner` from `ScriptRunner.build_connected_runtime(...)`. The existing discovery tool test only covers `_build_runtime(...)` catalog wiring. There is no focused test proving that live discovery/validation use the connected runtime's executor and planner, or that they fail fast when the runtime lacks an observed executor.

Why this matters:

- These are exactly the tool-runtime parity paths the audit was meant to protect.
- Without tests, a future edit could reintroduce manual `ActionExecutor` or `ScreenFlowPlanner` construction and the offline suite would likely stay green.

Clean fix:

- Add discovery-tool tests around `_run_live_discovery(...)` using a fake application/script runner that returns a connected runtime with sentinel `observed_action_executor` and `flow_planner` objects.
- Add a fail-fast test where `observed_action_executor` is `None`.
- Add a small validation-tool test, or extract its builder logic into a helper that can be tested without running the full CLI, asserting that `NavigationSelectorValidator` receives the runtime executor and planner identities.

### 6. Script-Runner Tests Do Not Lock The Executor Timing Policy

Files:

- `pnc_automation/app/automation/engine/script_runner.py`
- `tests/test_script_runner.py`

The tests now assert that the runtime, runner, world-map search service, and calibration service share the same observed executor. They do not assert that the underlying `ActionExecutor` receives all timing defaults from `DefaultsConfig`, especially the chat-specific delays that live chat smoke now inherits from canonical runtime wiring.

Why this matters:

- The commit removes manual executor construction from live chat smoke and tools, so `ScriptRunner._build_observed_action_executor(...)` is now the single place preserving timing semantics.
- A future regression could accidentally wire normal delays but not chat delays, and the new parity tests would still pass.

Clean fix:

- In `tests/test_script_runner.py`, build the `AppConfig` with distinctive non-zero values for `stable_click_delay_ms`, `post_action_observe_delay_ms`, `chat_stable_click_delay_ms`, and `chat_post_action_observe_delay_ms`.
- Assert those exact values on `runtime.observed_action_executor.action_executor`.
- Keep the identity assertions, because they cover a different and still valuable parity property.

### 7. The End-To-End Runner Helper Accepts Defaults But Hardcodes Executor Delays

File:

- `tests/test_runner_end_to_end.py`

The new `_make_runner(...)` helper takes a `DefaultsConfig`, passes it into `AutomationRunner`, but constructs the underlying `ActionExecutor` with all delays hardcoded to `0`.

Why this matters:

- The helper is named and documented as a fake-device production runner.
- If a future end-to-end parity scenario uses non-zero defaults to validate timing-sensitive behavior, the runner defaults and executor behavior will disagree.
- It is a small duplication of production runner construction policy.

Clean fix:

- Pass `defaults.stable_click_delay_ms`, `defaults.post_action_observe_delay_ms`, `defaults.chat_stable_click_delay_ms`, and `defaults.chat_post_action_observe_delay_ms` into `ActionExecutor`.
- If all end-to-end tests must remain zero-delay, make the caller supply a zero-delay `DefaultsConfig` as it does today.

### 8. Minor Style Cleanup In Selector Discovery

File:

- `tools/discover_selector_registry.py`

The `_run_live_discovery(...)` signature has a closing parenthesis indented with one extra leading space.

Why this matters:

- It is not a runtime bug, but it is visual noise in a touched live tool.
- This file is part of the parity audit surface, so keeping it tidy helps future review.

Clean fix:

- Align the closing parenthesis with the `def` line.

## Suggested Fix Order

1. Collapse `ConnectedAccountRuntime` and `_ConnectedRuntimeServices` into one canonical runtime graph.
2. Add a runtime-owned `require_observed_action_executor(...)` helper and port the repeated fail-fast checks.
3. Add the missing focused tests for tool rewiring and executor timing defaults.
4. Align the world-map movement smoke budget with the calibration tool.
5. Update the stale inventory row and minor selector-discovery formatting.

## DRY Closeout Notes

- The main DRY concern is the duplicated connected-runtime dataclass pair.
- The main duplicated predicate is the repeated nullable observed-executor requirement.
- No obsolete legacy serialization support was introduced.
- The offline suite passed after review, so the findings are cleanup/parity-hardening items rather than currently failing behavior.
