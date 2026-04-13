# PNC Test Codepath Parity Audit Plan

## 1. Purpose

This plan defines how to audit the test suite for a recurring risk:

- a test validates a helper, planner, shim, diagnostic path, or synthetic object graph,
- but the live runtime reaches the behavior through a different orchestration path,
- so the test can pass while production behavior remains unvalidated or drifts.

The original trigger was the world-map sweep validation risk:

- `WorldMapMovementCalibrationService.validate_sweep(...)` previously validated checkpoint movement through calibration-owned direct movement,
- while real search execution moved through `WorldMapSearchService.execute_search(...)`.

That specific gap has since been improved: `validate_sweep(...)` now resolves a `WorldMapSearchRequest` through `WorldMapSearchService`, calls `WorldMapSearchService.move_to_checkpoint(...)`, and carries one shared `runtime_state` across checkpoint movement. `tests/test_world_map_movement_calibration.py::test_validate_sweep_uses_shared_search_checkpoint_mover_runtime_state` protects that behavior.

The audit remains necessary because the broader pattern still exists in other forms:

- direct planner tests can bypass runner preflight, popup recovery, unknown recovery, retry budgets, and follow-up observation policy;
- diagnostic calibration tests can be mistaken for production search tests;
- live tools can build separate connected object graphs that are constructed by the same factory but do not share identity or mutable runtime state;
- task `plan(...)` / `verify(...)` tests can validate local branch logic without proving runner-owned preflight or replan behavior.

## 2. Goal

For each important behavior, prove exactly one of these is true:

1. The test exercises the same production entry point and canonical dependency wiring used by scripts, CLI tools, or live smoke tests.
2. The test is intentionally a lower-level contract test, and a named production-path companion covers the public entry point that consumes that contract.
3. The code under test is diagnostic-only and does not claim production behavior.
4. The helper is obsolete, duplicated, or non-canonical and should be deleted or folded into the production path.

The audit should not force every test to become an end-to-end test. It should ensure every helper-level or diagnostic test has a clear scope and, where needed, production-path coverage above it.

## 3. Current Architecture Snapshot

Use this snapshot when classifying existing tests. Update it as architecture changes.

### 3.1 Production Entry Points

A production entry point is code reached by normal authored scripts, CLI entry points, direct task calls, or live runtime flows.

Current examples:

- `ApplicationRunner.run(...)`
- `ApplicationRunner.prepare_account_session(...)`
- `ApplicationRunner.run_task(...)`
- `ApplicationRunner.run_mail_schedules(...)`
- `ScriptRunner.run(...)`
- `ScriptRunner.prepare_account_session(...)`
- `ScriptRunner.run_task(...)`
- `ScriptRunner.run_mail_schedules(...)`
- `ScriptRunner.build_connected_runtime(...)` for live tools that need feature services
- `ScriptRunner.build_connected_automation_runner(...)` for live tools that need runner orchestration
- `ScriptRunner.build_connected_runtime_bundle(...)` for live tools that need feature services and runner orchestration sharing one object graph
- `AutomationRunner.run(...)`
- `AutomationRunner.prove_preflight_state(...)`
- `AutomationRunner.execute_flow_until(...)`
- task `plan(...)` / `verify(...)` only when reached through runner orchestration
- `WorldMapSearchService.execute_search(...)` for production search behavior
- `ObservedActionExecutor.execute_actions(...)` and `ActionExecutor.execute_actions(...)` when reached through runner/script wiring
- `ObservationService.observe(...)` when reached through connected runtime wiring

### 3.2 Shared Production Subpaths

A shared production subpath is lower than the public operation entry point, but is deliberately used by more than one production or live-support flow.

Current examples:

- `WorldMapSearchService.move_to_checkpoint(...)`
- `WorldMapSearchService.coordinate_mover_for_runtime(...)`
- `WorldMapTraversalPlanner.build_route(...)`
- `WorldMapCoordinateDomain` addressability and route normalization methods
- `WorldMapCoordinateMover.move_to_coordinate(...)`
- `ScreenFlowPlanner` root navigation and recovery increments when consumed by `AutomationRunner`
- `AutomationRunner.prove_preflight_state(...)` as the public runner-owned preflight helper for live tools

Shared subpath tests are valuable, but they should not be described as proof of a broader operation unless the production entry point is also exercised.

### 3.3 Helper Paths

A helper path is lower-level code called by production code, but not itself the canonical feature entry point.

Current examples:

- `ScreenFlowPlanner.ensure_world_map_ready(...)`
- `ScreenFlowPlanner.ensure_home_city(...)`
- `ScreenFlowPlanner.recover_unknown_game_screen(...)`
- `WorldMapSearchService.resolve_plan(...)`
- navigator planning methods such as `plan_focus_coordinate(...)`
- direct survey recorder methods such as `capture_checkpoint(...)` and `record_checkpoint(...)`
- direct task `plan(...)` / `verify(...)` calls with synthetic observations

Helper tests are useful contract tests. They are insufficient when the runtime also depends on runner-owned preflight, action execution, popup recovery, unknown recovery, follow-up observation requests, retry budgets, artifact policy, or shared runtime state.

### 3.4 Diagnostic Paths

A diagnostic path is tooling intended for calibration, exploration, or live debugging, not normal production execution.

Current examples:

- `WorldMapMovementCalibrationService.probe_swipe(...)`
- `WorldMapMovementCalibrationService.run_cardinal_calibration(...)`
- `WorldMapMovementCalibrationService.run_dead_zone_verification(...)`
- `WorldMapMovementCalibrationService.validate_sweep(...)`
- `tools/run_world_map_movement_calibration.py`
- selector discovery and selector validation tools unless the test specifically targets their production wiring

Diagnostic tests should not be treated as proof of production search/runtime behavior unless they deliberately invoke the relevant production entry point. `validate_sweep(...)` is now a diagnostic traversal contract over the search checkpoint mover; it is still not a substitute for `execute_search(...)` tests because it does not exercise matching, search stop-policy evaluation, castle enrichment, or task/runner entry behavior.

## 4. Classification Method

For each feature area, create a small parity table with these columns:

- Behavior under test
- Production entry point
- Current test entry point
- Shared lower-level implementation
- Classification
- Existing production-path companion
- Missing production-path coverage
- Required follow-up

Classify each test as:

- `Production-path`: enters the same top-level path as real runtime for the claimed behavior.
- `Production-subpath-contract`: tests a shared lower-level implementation and asserts the contract production depends on.
- `Helper-contract`: tests a lower-level helper that production consumes indirectly.
- `Diagnostic-only`: validates a calibration, exploration, smoke, or debugging path.
- `Wiring-contract`: proves canonical connected construction, dependency identity, artifact policy, or observation/action policy.
- `Bypass-risk`: passes through a meaningfully different path while claiming production coverage.

Every `Helper-contract`, `Diagnostic-only`, or `Bypass-risk` item must either:

- name a production-path companion test,
- be documented as intentionally helper-only or diagnostic-only,
- or drive a refactor that removes the duplicate path.

Do not solve parity gaps by adding parallel support for old behavior. Port tests, tools, and authored config to the current model and delete obsolete paths.

## 5. Current High-Risk Audit Targets

### 5.1 World-Map Sweep And Search Movement

Current state:

- `WorldMapSearchService.execute_search(...)` is the production search entry point.
- `WorldMapMovementCalibrationService.validate_sweep(...)` now delegates checkpoint movement through `WorldMapSearchService.move_to_checkpoint(...)`.
- `tests/test_world_map_search.py` contains production-path search coverage for checkpoint ingestion, coordinate-jump failures, cardinal sweep movement, drift correction, zero-delta classification, missing-surface refresh, and avoiding per-checkpoint root readiness.
- `tests/test_world_map_movement_calibration.py` contains diagnostic sweep coverage plus a shared-mover runtime-state regression.
- `tests/test_live_world_map_movement_calibration_smoke.py` validates live probe and sweep stability, not full production search semantics.

Remaining risk:

- A future change could add new direct movement loops in calibration or tools and bypass `WorldMapSearchService.move_to_checkpoint(...)`.
- A test or plan could overstate `validate_sweep(...)` as proof of `execute_search(...)`.
- Movement-policy changes could be covered only in calibration diagnostics and miss production search behavior.

Required follow-up:

- Keep `validate_sweep(...)` classified as `Diagnostic-only` plus `Production-subpath-contract`, not as a full production search test.
- Maintain at least one `execute_search(...)` test for each production movement policy: cardinal decomposition, orthogonal drift correction, zero-delta classification, wrong-sign movement failure, landing proof, and parsed-surface refresh.
- If checkpoint movement changes, update the shared `WorldMapSearchService.move_to_checkpoint(...)` contract first, then keep both `execute_search(...)` and `validate_sweep(...)` aligned through that method.
- Audit for direct calls to private `_coordinate_mover(...)`; keep it as a delegating compatibility alias only while needed, and do not add new behavior behind it.

### 5.2 Traversal Planning And Coordinate Domain

Current state:

- `WorldMapTraversalPlanner` owns route generation.
- `WorldMapCoordinateDomain` owns coordinate bounds, addressable-pair parity, nearest addressable normalization, and route coordinate normalization.
- Search planning tests cover row-major, expanding-ring, edge-band, invalid parity, impossible rectangles, full-map corner normalization, and invalid origins.

Remaining risk:

- Tests that assert route shapes through `WorldMapSearchService.resolve_plan(...)` prove planning contracts, not runtime movement.
- If authored scripts or tools build route-like coordinate lists independently, route parity can drift from the canonical planner.

Required follow-up:

- Treat route-shape tests as `Production-subpath-contract`.
- Search for ad hoc route, parity, coordinate snapping, or bounds helpers outside `world_map_traversal.py` and `world_map_coordinate_domain.py`; delete or port them to the canonical APIs.
- If a tool needs a route preview, make it call `WorldMapTraversalPlanner` or `WorldMapSearchService.resolve_plan(...)` rather than reimplementing traversal.

### 5.3 Movement Calibration Diagnostics

Current state:

- `probe_swipe(...)`, `run_cardinal_calibration(...)`, and `run_dead_zone_verification(...)` are diagnostic paths.
- They use the same `WorldMapCoordinateMover` family for reset/refocus behavior, but their purpose is to classify live movement behavior and generate calibration evidence.
- Production search movement behavior is covered separately in `tests/test_world_map_search.py`.

Remaining risk:

- Diagnostic tests can pass while production search still fails if production entry coverage is missing for a policy change.
- Live calibration tools catch broad live instability but are not deterministic production search tests.

Required follow-up:

- Keep probe/calibration tests explicitly diagnostic in test docstrings and parity inventory.
- Add or update `execute_search(...)` tests whenever a diagnostic finding changes production movement policy.
- Ensure diagnostic results feed reports or authored config through explicit interfaces. Do not hide production heuristics only inside calibration loops.

### 5.4 Runner Preflight And Workflow Ownership

Current state:

- `TaskPreflight` declares runner-owned root preflight.
- `AutomationRunner.prove_preflight_state(...)` exposes the same root preflight proof to external live tools.
- `tests/test_automation_framework.py` covers runner-owned Home City preflight, World Map preflight, unknown-world-map recovery through public preflight, external step budgets, popup recovery, observed-action unknown retry policy, task-local replan budgets, and failure artifacts.
- `tests/test_flows_and_tasks.py` checks that root-owned tasks such as `ResearchTask` and `GatheringTask` declare the expected preflight.
- `reviewed_plans/PNC_OPERATION_PREFLIGHT_WORKFLOW_VALIDATION_PLAN.md` defines the separate workflow ownership model.

Remaining risk:

- Direct task tests can accidentally claim runner-owned preflight behavior.
- Direct `ScreenFlowPlanner` tests can bypass runner retry loops and popup recovery.
- Subflow-owned tasks such as building/open-building flows should not be mechanically converted to root preflight just for test convenience.

Required follow-up:

- Classify direct `ScreenFlowPlanner` tests as `Helper-contract` unless they are consumed through `AutomationRunner`.
- For every task with `TaskPreflight.HOME_CITY` or `TaskPreflight.WORLD_MAP`, keep at least one runner-level test or public preflight-helper test proving that root entry happens before task-body planning.
- Use the workflow validation plan to decide ownership before adding tests: root preflight belongs to the runner; intermediate proof and done-state proof belong to the task or domain service.

### 5.5 Connected Runtime And Live Tool Wiring

Current state:

- `ScriptRunner._build_connected_runtime_services(...)` is the canonical factory for connected session, observation service, flow planner, world-map survey recorder, world-map search service, movement calibration service, movement calibration store, and observed action executor.
- `ScriptRunner.build_connected_runtime(...)` exposes feature services plus the canonical observed-action executor for tools that do not need runner orchestration.
- `ScriptRunner.build_connected_automation_runner(...)` exposes runner orchestration through a separately constructed but equivalent canonical graph.
- `ScriptRunner.build_connected_runtime_bundle(...)` exposes both feature services and runner orchestration from one shared graph when a tool passes observations or mutable service state between them.
- `tests/test_script_runner.py` verifies canonical observation service wiring, shared flow planner and survey recorder identity inside one runtime, movement calibration/search service wiring, the shared runtime-plus-runner bundle, and recorder artifact policy.

Remaining risk:

- Calling `build_connected_runtime(...)` and `build_connected_automation_runner(...)` separately still constructs separate sessions and service instances. They are equivalent by construction, but not the same object graph.
- Tools that pass observations between feature services and runner helpers must use `build_connected_runtime_bundle(...)`.
- Tests that assert equivalent wiring should not imply identity sharing across separate builder calls.

Required follow-up:

- Add a parity inventory row for each live tool that builds both runtime and runner.
- If a tool needs identity sharing, use `build_connected_runtime_bundle(...)` instead of calling both builders independently.
- Add a targeted wiring test if a tool begins sharing mutable state between a runtime service and a runner service.
- Avoid `object()` placeholders in wiring tests when the test claims behavior beyond simple dependency identity; use minimal fakes that expose the actual interface being wired.

### 5.6 Screen-Flow Planner Helper Tests

Current state:

- `tests/test_flows_and_tasks.py` contains many direct `ScreenFlowPlanner` tests for planned action sequences and follow-up requests.
- Separate runner tests cover broad preflight, popup recovery, unknown recovery, and retry/replan behavior.

Remaining risk:

- Direct planner tests validate action contracts but not runner execution behavior.
- Planner tests can miss failures in `execute_flow_until(...)`, `run(...)`, `ObservedActionExecutor`, or task replan loops.

Required follow-up:

- Keep direct planner tests focused on action contract details.
- For each root navigation behavior that matters to runtime, ensure a runner-level companion exists through `AutomationRunner.run(...)`, `AutomationRunner.prove_preflight_state(...)`, or `AutomationRunner.execute_flow_until(...)`.
- Mark direct planner tests as helper-contract tests in the parity inventory when they are not runtime proof.

### 5.7 Task Unit Tests Versus Full Runner Execution

Current state:

- Many task tests call task `plan(...)`, `verify(...)`, or helper methods directly with synthetic observations.
- Generic runner tests cover execution loops, retry budgets, task-local replan budgets, popup recovery, unknown handling, and failure artifacts.
- Preflight declaration tests now clarify which tasks rely on runner-owned root entry.

Remaining risk:

- Direct task tests can pass while runner-owned preflight, popup recovery, unknown recovery, task-local replan budgets, artifact policy, or observed-action policy fails.
- State-rich tasks can accumulate local runtime-state conventions that are not verified through the runner.

Required follow-up:

- For each stateful task, maintain direct unit tests for local decision logic plus at least one runner-level scenario for its entry/preflight/replan/verify lifecycle.
- Prioritize `GatheringTask`, `ResearchTask`, `BuildingUpgradeTask`, `OpenBuildingTask`, chat tasks, mail tasks, and account/castle selection tasks.
- Encapsulate task runtime-state keys inside the owning task or shared helper. Tests should not create parallel conventions for the same state concept.

### 5.8 Observation, Action Executor, And Artifact Policy

Current state:

- `tests/test_automation_framework.py` has detailed `ObservedActionExecutor` coverage for narrow follow-up requests, OCR retry, unknown transitions, popup handoff, status banners, and selector interaction policy.
- `tests/test_script_runner.py` and observation/artifact tests cover connected wiring and artifact policy in focused places.

Remaining risk:

- Direct executor tests are good unit coverage, but production behavior also depends on the exact executor policy and observation mode passed through `ScriptRunner`.
- Capture/vision tests that instantiate `ObservationBuilder` or `ObservationService` directly are not proof of CLI/runtime artifact policy unless they use the connected builder.

Required follow-up:

- Keep executor and observation tests direct for policy details.
- Add wiring tests whenever a production service changes follow-up request policy, observation mode, artifact selection, selector registry source, or observed-action policy.
- Classify capture/vision tests as helper or wiring tests based on whether they build through `ScriptRunner`/`ApplicationRunner`.

## 6. Verified Static Audit Findings

This pass inspected all `tests/test_*.py` modules plus the live-smoke helpers and tool entry points for calls into production entry points, shared subpaths, helpers, diagnostics, and wiring factories.

High-signal findings:

- Strongest fake-device production-path coverage:
  - `tests/test_runner_end_to_end.py` runs `AutomationRunner.run(...)` with the default registry across the daily maintenance path: game launch, login, castle selection, building upgrade, research, gathering, and campaign.
  - `tests/test_automation_framework.py` covers the runner loop itself, including preflight, popup recovery, unknown recovery, observed-action follow-up policy, task-local replan budgets, and failure artifacts.
  - `tests/test_runtime_castle_targeting.py` covers registry preparation, runner-owned synthetic castle alignment, Python API delegation, and CLI delegation for castle-targeted tasks.
- Strongest world-map production-path coverage:
  - `tests/test_world_map_search.py` is the canonical deterministic coverage for `WorldMapSearchService.execute_search(...)`.
  - `tests/test_world_map_movement_calibration.py` is diagnostic coverage plus a shared-subpath regression for `validate_sweep(...) -> WorldMapSearchService.move_to_checkpoint(...)`.
- Helper-heavy areas:
  - `tests/test_flows_and_tasks.py`, `tests/test_mail_workflow.py`, and `tests/test_chat_monitor.py` deliberately call task `plan(...)` / `verify(...)`, `ScreenFlowPlanner`, persistence stores, and observation builders directly.
  - These tests are valuable, but they are not full runner-path proof unless paired with `AutomationRunner.run(...)`, `ScriptRunner.run(...)`, or public API/CLI delegation coverage.
- Live-smoke shape:
  - `tests/test_live_account_navigation_smoke.py` calls `ApplicationRunner.run(...)` and is true opt-in production-path smoke for the account-navigation script.
  - `tests/test_live_chat_workflow_smoke.py`, `tests/test_live_home_city_map_smoke.py`, `tests/test_live_spatial_surface_smoke.py`, and `tests/test_live_world_map_movement_calibration_smoke.py` use connected runtime services, `execute_flow_until(...)`, direct planner/executor loops, or diagnostic services. They prove live behavior for those paths, but they should not be described as full scripted task coverage unless they call `ApplicationRunner.run(...)` or `AutomationRunner.run(...)`.
- Tool shape:
  - `tools/run_world_map_movement_calibration.py` is diagnostic. It uses a shared connected runtime bundle for runner preflight, then direct coordinate recentering and `validate_sweep(...)`.
  - `tools/validate_navigation_selectors.py` and `tools/discover_selector_registry.py` are tool-runtime wiring/diagnostic paths. Their tests should prove canonical builder inputs and fail-fast behavior, not automation task behavior.
- Main uncovered parity risks to track:
  - `SendMailTask`, `CollectMailTask`, and `CollectKingdomChatTask` have rich unit/helper coverage but less fake-device runner-path coverage than daily maintenance tasks.
  - Direct chat-send tasks now have a fake-device runner-path companion in `tests/test_runner_end_to_end.py`; detailed chat action-policy coverage remains in `tests/test_flows_and_tasks.py` and `tests/test_automation_framework.py`.
  - Live chat smoke uses the canonical connected `ScreenFlowPlanner` and `ObservedActionExecutor` from `ScriptRunner.build_connected_runtime(...)`. It remains reusable-workflow smoke, not proof that the send-chat tasks run through the script runner.
  - Separate calls to `build_connected_runtime(...)` and `build_connected_automation_runner(...)` remain equivalent-by-factory rather than identity-shared; callers that need identity sharing must use `build_connected_runtime_bundle(...)`.

## 7. Verified Test Inventory

This inventory records what each test module actually proves. Update it when tests move between direct-helper and production-entry coverage.

| Test module | Current classification | Production path proved | Follow-up |
| --- | --- | --- | --- |
| `tests/test_app.py` | Wiring-contract | `build_application_runner(...)` top-level wiring for selector registry, archive stores, and BlueStacks resolver config | Keep as application factory coverage; add rows when factory-owned dependencies are added |
| `tests/test_automation_framework.py` | Production-path plus executor-policy contract | `AutomationRunner.run(...)`, `prove_preflight_state(...)`, `ObservedActionExecutor.execute_actions(...)`, generic action execution | Keep runner/executor policy coverage here; use it as the companion for direct planner/task tests |
| `tests/test_bluestacks_instance_resolver.py` | Helper-contract | `BlueStacksInstanceResolver.resolve(...)` and config parsing, not runner execution | No runner companion required unless session resolution wiring changes |
| `tests/test_capture_and_vision.py` | Vision helper-contract plus observation-service contract | `ObservationBuilder`, `ObservationService`, OCR/screen/spatial enrichment; selected executor/chat flows | Do not treat direct builder tests as application wiring proof; pair artifact/selector-source changes with `test_app.py` or `test_script_runner.py` |
| `tests/test_castle_roster_store.py` | Persistence contract | `CastleRosterStore` merge/order behavior | Covered as store contract; runner uses store through `test_runtime_castle_targeting.py` and live account smoke |
| `tests/test_chat_monitor.py` | Task-unit plus persistence contract | `CollectKingdomChatTask.plan/verify(...)`, `ChatArchiveStore` | Add runner-path companion if Kingdom Chat heartbeat becomes critical scripted coverage beyond helper/unit scope |
| `tests/test_chat_transcript_cleanup.py` | Tool/helper contract | Manual transcript cleanup parser | No automation runtime claim |
| `tests/test_config_loader.py` | Authoring/config contract | `load_app_config(...)` schema validation and canonical config shape | No runner companion required; keep rejecting old config shapes here |
| `tests/test_discover_selector_registry_tool.py` | Tool wiring-contract | Discovery tool passes one catalog path to runtime and analyzer | Keep scoped to tool wiring |
| `tests/test_emulator_session.py` | Low-level session contract | `BlueStacksSession` ADB commands and swipe behavior | Covered below runtime; `test_script_runner.py` covers connected session construction |
| `tests/test_flows_and_tasks.py` | Helper-contract plus task-unit coverage | `ScreenFlowPlanner` methods and direct task `plan(...)` / `verify(...)` for most task bodies | Treat as local decision coverage; pair stateful task claims with `test_runner_end_to_end.py`, `test_automation_framework.py`, or new runner scenarios |
| `tests/test_live_account_navigation_smoke.py` | Opt-in live production-path smoke | `ApplicationRunner.run(...)` on `scripts/smoke/account_navigation_smoke.yaml` plus live roster verification | This is the live smoke that proves scripted account-navigation path |
| `tests/test_live_chat_workflow_smoke.py` | Opt-in live helper/workflow smoke | Connected observation/session plus direct `ScreenFlowPlanner.send_chat_message(...)` and manually constructed executor | Do not treat as send-chat task proof; add script-run smoke if task/runner parity is needed |
| `tests/test_live_home_city_map_smoke.py` | Opt-in live flow-subpath smoke | Connected runner, `execute_flow_until(...)`, home-city atlas focus/opening helpers | Good live proof of home-city spatial helper path, not full task proof |
| `tests/test_live_spatial_surface_smoke.py` | Opt-in live flow-subpath smoke | Connected runner and `execute_flow_until(...)` for home/world root navigation and world-map coordinate focus | Uses shared flow execution, not full script/task coverage |
| `tests/test_live_world_map_movement_calibration_smoke.py` | Opt-in live diagnostic smoke | Runner preflight plus calibration `probe_swipe(...)` and `validate_sweep(...)` | Live movement stability only; production search proof remains in `tests/test_world_map_search.py` |
| `tests/test_mail_workflow.py` | Task-unit, workflow-helper, vision, and persistence contracts | `SendMailTask`/`CollectMailTask` direct logic, mail flows, OCR enrichment, archive store, selected action executor behavior | Add fake-device runner scenario for send/collect mail if mail runtime parity becomes a target |
| `tests/test_navigation_selector_validator.py` | Tool diagnostic contract | `NavigationSelectorValidator` and reviewed selector outcome matching with fakes | Keep separate from normal runner navigation proof |
| `tests/test_observation_artifact_policy.py` | Artifact-policy and recorder contract | Artifact resolver, `ObservationService`, `WorldMapSurveyRecorder`, fake observation artifact parity | `tests/test_script_runner.py` covers connected recorder wiring; keep both layers aligned |
| `tests/test_ocr_service.py` | OCR helper contract | OCR service helpers | No automation runtime claim |
| `tests/test_package_architecture.py` | Architecture invariant | Package import boundaries and removal of obsolete top-level packages | No runner claim; keep as structural DRY enforcement |
| `tests/test_runner_end_to_end.py` | Production-path fake-device scenario | `AutomationRunner.run(...)` with default registry across daily maintenance tasks plus direct world-chat send task execution | Add new scenario or extend only when a task needs runner-path proof and cannot be represented by current daily flow |
| `tests/test_runtime_castle_targeting.py` | Production-path plus API/CLI delegation contract | Registry preparation, `AutomationRunner.run(...)` synthetic castle alignment, `AutomationApi`, CLI delegation | Keep as canonical castle-targeting parity coverage |
| `tests/test_scheduled_mail.py` | Authoring/runtime/API/CLI contract | Scheduled-mail catalog, generated script construction, `ScriptRunner.run_mail_schedules(...)`, API/CLI delegation | Generated script execution is patched at `_run_script_for_account(...)`; add runner-path mail task coverage separately if needed |
| `tests/test_screen_classifier.py` | Vision helper contract | `ScreenClassifier` evidence integration | No runner claim |
| `tests/test_script_loader.py` | Authoring contract | Run-script YAML loader and fail-fast schema validation | Registry preparation/runtime coverage lives elsewhere |
| `tests/test_script_runner.py` | Wiring-contract | Connected session/runtime/runner builders, shared runtime-plus-runner bundle, observation service, survey recorder, debug artifacts | Keep bundle identity tests aligned with live tools that pass observations or mutable service state between feature services and runner helpers |
| `tests/test_selector_discovery.py` | Selector-discovery helper contract | Offline selector artifact analysis and draft generation | Tool wiring companion is `tests/test_discover_selector_registry_tool.py` |
| `tests/test_selector_registry_updater.py` | Offline update helper contract | Registry updater, enum updates, schema rejection | No runtime claim; keep old schema rejection here |
| `tests/test_selectors.py` | Selector registry contract | Default selector registry, catalog validation, legacy schema rejection | Runtime use is wired through `test_app.py`/`test_script_runner.py` and executor tests |
| `tests/test_support.py` | Shared test harness | Fakes/builders used by the offline suite | Keep fake behavior aligned with production contracts; artifact-mode parity is checked in `tests/test_observation_artifact_policy.py` |
| `tests/test_text_anchors.py` | OCR text helper contract | Text anchor detection | No automation runtime claim |
| `tests/test_world_map_index.py` | World-map index contract | `WorldMapSurveyIndex` ingestion, matching, profile annotation | Production search companion is `tests/test_world_map_search.py` |
| `tests/test_world_map_movement_calibration.py` | Diagnostic plus production-subpath contract | Calibration probes/sweeps; `validate_sweep(...)` shared search checkpoint mover | Keep diagnostic claims explicit |
| `tests/test_world_map_search.py` | Production-path plus shared-subpath contract | `WorldMapSearchService.execute_search(...)`, route planning, coordinate movement, stop policies, castle enrichment | Canonical deterministic production search coverage |

## 8. Audit Checklist

For every test file or test group, answer:

- What behavior does this test claim to prove?
- Does it call the production entry point, a shared production subpath, a helper, or a diagnostic tool?
- If helper-only or diagnostic-only, where is the production entry point covered?
- Does it instantiate dependencies the same way as `ApplicationRunner`, `ScriptRunner`, or `AutomationRunner`?
- Does it bypass task preflight, popup recovery, unknown recovery, follow-up observation, retry/replan budget, or artifact policy?
- Does it pass direct observations where production would re-observe?
- Does it validate the same runtime-state ownership and sharing as production?
- Does it assert only output shape, or also that the canonical dependency was used?
- Does it duplicate any parser, predicate, route generator, formatter, movement rule, or coordinate-domain rule?
- Is there obsolete compatibility code left after a refactor?

## 9. Recommended Implementation Steps

### Step 1. Maintain The Verified Parity Inventory

Keep the inventory in section 7 current whenever test files, public entry points, or live tools change.

When adding or changing tests, update the row to name:

- the production path actually proved;
- whether the test is helper, diagnostic, wiring, or production-path coverage;
- the companion production-path test when the test is helper or diagnostic only.

### Step 2. Lock The Closed World-Map Sweep Gap

Keep the current design:

- `validate_sweep(...)` resolves through `WorldMapSearchService`;
- checkpoint execution goes through `WorldMapSearchService.move_to_checkpoint(...)`;
- movement state is shared across checkpoints;
- checkpoint observations are recorded without forced duplicate recapture when the post-move observation is already usable.

Do not add a new sweep-specific movement loop. If the current structure becomes awkward, refactor the shared search checkpoint movement method instead of adding a parallel helper.

### Step 3. Clarify Connected Runtime Identity Rules

Decide and document which tools need:

- equivalent canonical construction only, or
- a single shared object graph with identity sharing.

Where identity sharing is required, introduce one connected bundle that exposes both runner behavior and feature services. Where equivalent construction is enough, tests should assert canonical wiring rather than object identity across separate builder calls.

Current implementation:

- `ScriptRunner.build_connected_runtime_bundle(...)` is the canonical shared-object-graph API.
- `tools/run_world_map_movement_calibration.py` and `tests/test_live_world_map_movement_calibration_smoke.py` use the shared bundle because runner preflight and calibration services exchange observations.
- `tools/validate_navigation_selectors.py`, `tools/discover_selector_registry.py`, and `tests/test_live_chat_workflow_smoke.py` use the observed-action executor and flow planner exposed by the connected runtime instead of reconstructing duplicate executor/planner wiring.

### Step 4. Add Production-Path Companions For High-Risk Helpers

Prioritize helpers that control runtime orchestration:

- runner preflight proof;
- unknown recovery;
- popup recovery;
- world-map movement;
- checkpoint ingestion;
- observed-action follow-up policy;
- task-local replan budget;
- artifact and observation mode policy.

### Step 5. Audit Task Workflow Claims Against Ownership

Use `reviewed_plans/PNC_OPERATION_PREFLIGHT_WORKFLOW_VALIDATION_PLAN.md` when deciding whether a test should be runner-level or task-level.

- Root-owned tasks need runner/preflight coverage.
- Subflow-owned tasks need direct subflow contract tests and runner scenarios for lifecycle behavior.
- In-surface operations need tests that prove they do not re-enter broad root navigation inside movement loops.

### Step 6. Mark Diagnostic Tests Explicitly

Update docstrings or inventory notes for calibration, selector-discovery, and live-smoke tests so they do not read as production runtime proof unless they call the relevant production entry point.

### Step 7. Remove Duplicate Paths

When the inventory exposes duplicate implementations, refactor toward one canonical implementation:

- one traversal planner;
- one coordinate domain/addressability model;
- one checkpoint movement implementation;
- one runner-owned preflight implementation;
- one observed-action follow-up policy;
- one artifact policy for connected runtime captures.

Delete obsolete paths after the refactor. Do not keep parallel APIs for old tests, old serialized shapes, or old tool assumptions.

## 10. Success Criteria

This audit is complete when:

- every important helper-level test has a named production-path companion test or is clearly documented as helper-only;
- no diagnostic workflow is treated as full production search/runtime proof;
- world-map sweep validation and production search checkpoint movement continue to share `WorldMapSearchService.move_to_checkpoint(...)`;
- production search movement policies remain covered through `WorldMapSearchService.execute_search(...)`;
- connected tooling has explicit rules for equivalent construction versus shared object identity;
- runner-owned preflight, popup recovery, unknown recovery, observed-action follow-up policy, and task-local replan budgets have production-path coverage;
- no duplicated predicates, parsers, formatters, route generators, coordinate rules, movement loops, or artifact policies remain;
- future reviews can quickly answer: "Which production path does this test actually prove?"

## 11. DRY Enforcement Closeout

Before finishing an audit batch, confirm:

- there is exactly one canonical implementation per concept;
- every lower-level helper has either a clear owner or a production-path consumer;
- no duplicated predicates, formatters, parsers, traversal generators, coordinate rules, or movement policies were introduced;
- obsolete code paths and interfaces were removed;
- naming reflects ownership, such as runner-owned preflight versus task-owned done-state proof;
- tests and tools have been ported to the current schema rather than supporting old formats.
