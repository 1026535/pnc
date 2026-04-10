# PNC World-Map Search Partial Review

## Scope

Reviewed commit `feb45b1eeb600bbf0ec2784ceac28207e6bc3f53` against:

- `PNC_WORLD_MAP_SEARCH_SUBPLAN.md`
- `PNC_WORLD_MAP_MOVEMENT_CALIBRATION_SUBPLAN.md`

This review is intentionally scoped as a **pre-calibration partial review**. Items that are clearly blocked on the movement-calibration plan are called out separately from direct code problems.

## Validation Note

Targeted regression coverage was run with:

- `py -m unittest tests.test_world_map_search tests.test_world_map_index tests.test_screen_classifier`
- `py -m unittest tests.test_flows_and_tasks tests.test_capture_and_vision tests.test_emulator_session`

Both runs passed in the current workspace, so the findings below are mostly design/behavioral issues that are not yet covered by the current tests.

## Findings

### 1. Search sweep still depends on diagonal movement, which conflicts with the calibration subplan

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1357`
  - `pnc_automation/app/pnc/navigation/spatial_navigation.py:933`
- Problem:
  - `WorldMapSearchService._move_to_checkpoint(...)` delegates every checkpoint move to `WorldMapNavigator.plan_focus_coordinate(...)`.
  - `WorldMapNavigator._resolve_profile(...)` chooses a diagonal swipe profile whenever both axes still differ.
  - That means row-major and other sweep traversals still depend on diagonal movement during row transitions and larger repositioning steps.
  - The movement calibration subplan explicitly concludes that the canonical sweep/search path should be cardinal-only for now, because diagonal motion is not on the critical path and is not the proven basis for reliable sweep coverage.
- Why this matters before resuming search work:
  - It keeps the search layer coupled to exactly the movement behavior that is still under calibration.
  - It makes sweep failures harder to attribute cleanly, because search correctness and diagonal calibration are still entangled.
- Clean fix:
  - Add a search-owned sweep movement policy that decomposes checkpoint travel into ordered cardinal legs.
  - Keep diagonal support in `WorldMapNavigator` only as an optional lower-level capability, not as the canonical sweep primitive.
  - Make `WorldMapSearchService` choose cardinal movement explicitly for row-major / expanding-ring / edge-band traversal while the calibration plan is still active.

### 2. The checkpoint loop re-captures a second observation after every move instead of ingesting the already-proven post-move frame

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1230`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1364`
  - `pnc_automation/app/pnc/navigation/world_map_survey_recorder.py:60`
- Problem:
  - `_move_to_checkpoint(...)` already executes actions with observation follow-up and returns a proven world-map observation.
  - `execute_search(...)` then immediately calls `survey_recorder.capture_checkpoint(...)`, which performs a brand-new capture instead of ingesting the observation it already has.
- Why this matters:
  - It adds avoidable OCR / classification churn to every checkpoint.
  - It makes movement validation noisier right before the movement calibration plan, because the indexed checkpoint is no longer the exact frame that proved the move.
  - It doubles observation cost for the canonical search loop.
- Clean fix:
  - Add one recorder path that ingests an already-captured / already-observed checkpoint without forcing a second capture.
  - In `WorldMapSearchService.execute_search(...)`, ingest `current_observation` directly after movement.
  - Keep explicit re-capture only as a bounded fallback when the post-move observation is missing required world-map surface data.

### 3. `SELF_TERRITORY` origin can silently degrade to the viewport center, which can mis-center local searches

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1562`
- Problem:
  - `_resolve_self_territory_origin(...)` correctly prefers the self castle's coordinate when present.
  - If the self castle is visible but its coordinate is missing, the code falls back to `surface.viewport.coordinate`.
  - That substitutes "current camera center" for "my territory coordinate", which is not the same concept.
- Why this matters:
  - A proximity search can be centered on the wrong place even though the caller explicitly asked for `SELF_TERRITORY`.
  - This is especially risky for exactly the local-search use case the plan treats as a primary consumer.
- Clean fix:
  - Fail fast unless the self-territory object itself exposes a usable coordinate.
  - If a fallback is absolutely required, gate it behind a stricter rule, for example only when the self castle is clearly centered and the code records that the origin is approximate rather than exact.
  - Do not silently treat viewport center as canonical self-territory origin.

### 4. Edge-band origin semantics are currently accepted but not actually honored by route generation

- Severity: Medium
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:774`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:921`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1745`
- Problem:
  - `WorldMapSearchRequest` allows edge-band requests to declare origins such as `MAP_EDGE_REFERENCE`.
  - But `_edge_band_coordinates(...)` ignores `origin_coordinate` entirely and always yields a plain row-major filtered route over the whole map bounds.
  - So the API suggests the start edge matters, but the planner does not use it.
- Why this matters:
  - The request model is more expressive than the implementation.
  - Callers can believe they requested "start from this edge" semantics when they did not.
- Clean fix:
  - Either implement origin-aware edge-band visitation order, or reject / narrow the supported origin set for edge-band sweeps until that behavior really exists.
  - Prefer the stricter option for now, because it keeps the API honest while calibration work is still ongoing.

### 5. `EnsureGameRunningTask` gained new unknown-recovery replans, but its task-local replan budget was not increased

- Severity: Medium
- Evidence:
  - `pnc_automation/app/automation/tasks/ensure_game_running_task.py:35`
  - `pnc_automation/app/automation/tasks/ensure_game_running_task.py:67`
  - `pnc_automation/app/automation/tasks/ensure_game_running_task.py:76`
- Problem:
  - The task now spends replans on bounded unknown-state recovery before launch.
  - `max_replans_per_step(...)` still returns `_MAX_LAUNCH_WAIT_ATTEMPTS + 1`, which was tuned for the launch-wait path only.
  - A legitimate `UNKNOWN -> recovery -> Android/Home -> launch -> splash wait` sequence can now consume more replans than the advertised budget.
- Why this matters:
  - The runner can abort a healthy recovery path early and report a framework-level replan-limit failure instead of the task's intended bounded failure.
- Clean fix:
  - Increase the task-local budget to cover both phases, for example:
    - unknown recovery budget
    - launch start transition
    - launch wait budget
  - Add a focused test that exercises the longest intended recovery-plus-launch path.

### 6. Castle inspection can silently skip a candidate when focus planning returns no action but the candidate is still not visible

- Severity: Medium
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1053`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1060`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1087`
- Problem:
  - `_focus_candidate(...)` returns immediately when `plan_focus_coordinate(...)` yields no actions.
  - That path is treated as "good enough" even if `_candidate_is_visible_on_surface(...)` is still false.
  - `_inspect_one_candidate(...)` then just returns `None` because the target is not actually visible.
- Why this matters:
  - It converts a movement / visibility mismatch into a silent skipped candidate.
  - With movement calibration still in progress, this is exactly the kind of hidden failure mode we want to surface, not normalize away.
- Clean fix:
  - If no movement action is available and the candidate is still not visible, fail fast or force one bounded corrective refresh / recenter attempt.
  - Do not silently treat "no planned move" as equivalent to "candidate is ready to inspect".

## Direct Cleanup / Simplification Opportunities

These are lower-risk cleanups, but they are worth doing while touching this area again:

### 7. Runtime wiring for flows / executors is duplicated and will be easy to drift

- Severity: Low
- Evidence:
  - `pnc_automation/app/automation/engine/script_runner.py:169`
  - `pnc_automation/app/automation/engine/script_runner.py:237`
- Problem:
  - `build_connected_runtime(...)` and `_build_runner(...)` both build closely related flow / executor stacks separately.
  - That makes it easy for the search runtime and the automation runner runtime to drift as search integration resumes.
- Clean fix:
  - Factor one canonical runtime wiring helper and reuse it for both the connected runtime and the automation runner.
  - When search consumers are migrated, make sure they use the same canonical flow / observation / action surfaces.

### 8. A few small dead / redundant pieces should be removed once the next pass touches these files

- Severity: Low
- Evidence:
  - `pnc_automation/app/pnc/navigation/spatial_navigation.py:45`
  - `pnc_automation/app/pnc/navigation/spatial_navigation.py:928`
  - `pnc_automation/app/pnc/navigation/screen_flows.py:450`
- Problem:
  - `_WORLD_MAP_HORIZONTAL_SWIPE_Y_RATIO` is unused.
  - `WorldMapNavigator._resolve_profile(...)` still accepts a `state` parameter it does not use.
  - `return_home_city_from_world_map(...)` is now redundant and can be simplified to a single return.
- Clean fix:
  - Remove the dead constant.
  - Drop the unused parameter.
  - Collapse the redundant branch.

## Important Remaining Incomplete Items

These are not framed as bugs in this review because they are either intentionally left incomplete or explicitly blocked by `PNC_WORLD_MAP_MOVEMENT_CALIBRATION_SUBPLAN.md`, but they should stay on the resume checklist:

### A. Search consumers are only partially migrated

- `GatheringTask` now uses the cleaned-up world-map navigator surface, but it still performs only visible-frame interaction and does not yet consume `WorldMapSearchService`.
- That is fine for this partial slice, but resuming `PNC_WORLD_MAP_SEARCH_SUBPLAN.md` should still migrate the real search-consuming features to the shared search service and then delete any remaining feature-local search behavior.

### B. Map-bounds resolution for broad / full-map search is still missing

- Coordinate-jump and overview helpers exist only as placeholders.
- Full-map bounds still have to be supplied externally instead of being resolved by a canonical helper.
- That should remain after movement calibration, but before broad search closeout.

### C. Castle profile validation is still intentionally unimplemented after opening the profile

- The dedicated profile-validation path now exists and fails fast correctly.
- That is a good boundary improvement, but the feature is still incomplete by design and should remain out of the immediate pre-calibration scope.

## Recommended Execution Order

Given the movement blocker plan, the clean order looks like this:

1. Fix finding 1 first so sweep search no longer depends on diagonal movement.
2. Fix findings 2 and 6 next so movement / observation issues surface cleanly during calibration.
3. Fix findings 3 and 4 before resuming local-search correctness work.
4. Fix finding 5 in parallel because it is isolated and low-risk.
5. Resume `PNC_WORLD_MAP_MOVEMENT_CALIBRATION_SUBPLAN.md`.
6. Only then continue the remaining search-plan feature integration work.
