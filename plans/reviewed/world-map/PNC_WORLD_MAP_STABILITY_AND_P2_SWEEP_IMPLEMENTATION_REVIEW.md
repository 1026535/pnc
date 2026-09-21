# PNC World Map Stability And P2 Sweep Implementation Review

## Scope

Reviewed the partial implementation from:

- `c0e1b710030c6fbc1ad1e52385224b38606d3e3e` - initial stability/performance plan.
- `21f974ed981b53781c44679df4b7ec508bb2de72` - P1/P2 sweep pipeline, OCR throughput plan, live tools, and fixture-backed regressions.

The focused tests pass with:

```powershell
py -3.13 -m unittest tests.test_world_map_proof_analysis tests.test_world_map_sweep tests.test_world_map_search
```

This review therefore focuses on remaining bugs, acceptance gaps, inconsistencies, duplicated paths, and clean follow-up work.

## Findings

### P0. Production segment starts can skip required row/segment movement

References:

- `pnc_automation/app/pnc/navigation/world_map_search.py:3092`
- `pnc_automation/app/pnc/navigation/world_map_search.py:3112`
- `pnc_automation/app/pnc/navigation/world_map_search.py:3185`

`_move_to_segment_start_work_item()` uses `world_map_sample_gap_exceeds_scan_footprint()` to decide whether to move to the next segment start. If the current viewport is within the modeled scan footprint, it captures the current viewport and treats it as the segment start sample.

That is unsafe for multi-row production sweeps. Example: after finishing row `y=0`, the next serpentine row start might be `(511, 6)`. The vertical delta is only `6`, far below the modeled scan footprint, so the code can skip moving to `(511, 6)`. `_traverse_production_segment_samples()` then builds swipes from the planned row-`6` coordinates while executing them from the previous actual row. The sweep can keep moving along the wrong lane while recording planned row checkpoints as visited.

Clean fix:

1. Separate "coverage sample accepted" from "movement anchor aligned".
2. Require the actual coordinate at a new production segment start to be within movement landing tolerance of `segment.start_coordinate` before lane traversal begins.
3. If a nearby previous viewport covers the new segment start, record it as coverage evidence only; do not use it as the execution anchor for that segment.
4. Add a deterministic two-row production test proving that the segment transition moves or otherwise proves the new row anchor before horizontal lane swipes continue.

### P0. Planned checkpoint identity is conflated with actual sample identity

References:

- `pnc_automation/app/pnc/navigation/world_map_search.py:3029`
- `pnc_automation/app/pnc/navigation/world_map_search.py:3030`
- `pnc_automation/app/pnc/navigation/world_map_search.py:3718`
- `tests/test_world_map_search.py:966`

Production mode appends the planned checkpoint to `visited_checkpoints`, but P2 ingests the actual P1-proven coordinate. The test intentionally accepts a start sample at `(5, 5)` while recording visited checkpoints as `(0, 0), (10, 0), (20, 0)`.

That distinction is useful for coverage, but it is not modeled explicitly. Profiles, visited checkpoints, labels, and route indices can imply that a planned coordinate was sampled exactly when the survey index actually contains a different coordinate. This becomes dangerous for coverage audit, duplicate merge, and inventory attribution.

Clean fix:

1. Introduce one canonical sample record, for example `WorldMapActualSample`, carrying `route_index`, `planned_coordinate`, `actual_coordinate`, `proof`, `screenshot`, `coverage_window`, and optional `projected_frame`.
2. Keep `visited_checkpoints` as route progress only, not sample proof.
3. Persist/profile actual sample coordinates separately from planned route checkpoints.
4. Make coordinator ingest consume the sample record so inventory merge can reason from actual proof instead of inferred route labels.

### P1. Production policy still performs exact P1 OCR proof at every sample

References:

- `pnc_automation/app/pnc/navigation/world_map_search.py:3200`
- `pnc_automation/app/pnc/navigation/world_map_search.py:3209`
- `PNC_WORLD_MAP_OCR_THROUGHPUT_OPTIMIZATION_PLAN.md`

The production row/lane executor avoids synchronous rich P2 treatment, but every planned sample still captures a movement-proof observation and performs exact coordinate OCR. That keeps the measured P1 OCR bottleneck on the hot path and does not yet implement sparse exact anchors, projected intermediate frames, or sampled-frame capture during continuous movement.

Clean fix:

1. Treat the current production policy as "exact-P1 sampled segment mode", not the final under-30 full-map production policy.
2. Implement the active OCR throughput plan first: stage-level P1 benchmark, raw/filtered OCR experiments, and acceptance thresholds.
3. Add a sparse-proof policy only after projection and coverage records can represent uncertainty without pretending every sample is exact.

### P1. The projection model is a placeholder but is named like a real uncertainty model

References:

- `pnc_automation/app/pnc/navigation/world_map_sweep.py:296`
- `pnc_automation/app/pnc/navigation/world_map_sweep.py:316`
- `pnc_automation/app/pnc/navigation/world_map_search.py:3258`

`WorldMapCoordinateProjectionContext.project_frame()` currently computes a fixed uncertainty value from policy max, independent of anchor distance, time, movement direction, calibration error, or frame spacing. Production traversal then uses `progress_ratio=1.0`, so the projected frame is effectively the exact P1-proven endpoint with a synthetic uncertainty window.

Clean fix:

1. Either rename this as an exact-sample window helper and remove projection claims, or implement true projection semantics.
2. A real projection context should consume exact anchors, frame order/timing, movement direction, calibrated viewport footprint, and policy uncertainty limits.
3. It must fail fast when uncertainty exceeds policy instead of always manufacturing a bounded-looking window.
4. Add tests where uncertainty grows with anchor distance and rejects over-wide projected windows.

### P1. P2 treatment kind is modeled but not actually applied

References:

- `pnc_automation/app/pnc/navigation/world_map_analysis.py:35`
- `pnc_automation/app/pnc/navigation/world_map_analysis.py:146`
- `pnc_automation/app/pnc/vision/observation_request.py:115`

`WorldMapViewportAnalysisTreatmentKind` defines `INVENTORY_ONLY` and `CHECKPOINT_SEARCH`, but `WorldMapViewportAnalyzer.analyze()` ignores the treatment kind and always builds `ObservationRequest.world_map_checkpoint_analysis()`. The `artifact_selection` field is also unused.

This means there is not yet a real inventory-only P2 profile, and the code cannot express the planned split between diagnostic/full treatment and production inventory treatment.

Clean fix:

1. Add one canonical method that maps a work item's treatment kind to an `ObservationRequest`.
2. Implement a narrower inventory-only request only when its behavior is defined and tested.
3. Wire `artifact_selection` through or remove it until P2 artifact persistence exists.
4. Add tests proving inventory-only P2 skips any checkpoint-search-only work.

### P1. Inventory-only P2 work can be constructed without proof

References:

- `pnc_automation/app/pnc/navigation/world_map_analysis.py:72`
- `pnc_automation/app/pnc/navigation/world_map_analysis.py:74`

For `INVENTORY_ONLY`, `WorldMapViewportAnalysisWorkItem` only validates proof if one is present. That permits a caller to create a P2 work item with an arbitrary `checkpoint_coordinate`, a screenshot, no proof, and no projected frame. The analyzer will still seed the observation request from that coordinate.

Clean fix:

1. Require every P2 work item to carry either an exact proof matching the screenshot or a future explicit projected-frame evidence object that includes source anchors and screenshot identity.
2. Do not allow bare `checkpoint_coordinate` to be the authority for P2 analysis.
3. Add a regression test that `INVENTORY_ONLY` without proof/projected evidence fails fast.

### P1. Queue order guarantees are inconsistent across drain methods

References:

- `pnc_automation/app/pnc/navigation/world_map_analysis.py:208`
- `pnc_automation/app/pnc/navigation/world_map_analysis.py:217`
- `pnc_automation/app/pnc/navigation/world_map_analysis.py:225`
- `tests/test_world_map_proof_analysis.py:111`

`drain_all()` sorts pending work by `route_index`, but `drain_ready()` and `drain_next()` operate on submission order. Current runtime appears to submit monotonically, but the queue contract says route-order result application. If callers ever submit out of order, or if a future multi-worker path changes submission behavior, backpressure can apply a later route result before an earlier one.

Clean fix:

1. Either enforce strictly increasing `route_index` on `submit()` or keep `_pending` sorted by route index.
2. Make `drain_ready()`, `drain_next()`, and `drain_all()` share the same order invariant.
3. Add tests for out-of-order submissions against all three drain methods, not only `drain_all()`.

### P1. P2 queue/backpressure metrics are too shallow for the active throughput plan

References:

- `pnc_automation/app/pnc/navigation/world_map_search.py:1088`
- `pnc_automation/app/pnc/navigation/world_map_search.py:1139`
- `PNC_WORLD_MAP_OCR_THROUGHPUT_OPTIMIZATION_PLAN.md`

Profiles expose submission count, peak depth, overlap count, drain time, and P1 fallback count. They do not yet expose queue wait time, worker run time, backpressure block count/duration, P2 OCR-stage time, duplicate coordinate OCR count, recapture count, parser merge time, or overlap duration.

Clean fix:

1. Add a typed queue telemetry record owned by `WorldMapViewportAnalysisQueue`.
2. Record submit time, worker start/end, result application time, backpressure drain time, and first failure.
3. Feed those records into `WorldMapSearchExecutionProfile`.
4. Keep the current counters as derived totals rather than independently maintained state.

### P2. Checkpoint-loop async P2 code is now unreachable duplication

References:

- `pnc_automation/app/pnc/navigation/world_map_search.py:2673`
- `pnc_automation/app/pnc/navigation/world_map_search.py:2686`
- `pnc_automation/app/pnc/navigation/world_map_search.py:2696`

When `asynchronous_p2` is true, `execute_search()` immediately returns through `_execute_production_segment_search()`. The later checkpoint-loop `p2_queue` setup and branches therefore always run with `p2_queue is None`.

Clean fix:

1. Delete the unreachable async queue branch from the checkpoint loop and make that path explicitly synchronous diagnostic checkpoint analysis.
2. Keep the production async implementation only in `_execute_production_segment_search()`.
3. If async exact-checkpoint diagnostics are still desired, expose that as a deliberate policy with tests, not dead generic branches.

### P2. Lazy P2 observation-builder ownership is not thread-safe if workers are increased

References:

- `pnc_automation/app/automation/engine/script_runner.py:206`
- `pnc_automation/app/automation/engine/script_runner.py:208`
- `pnc_automation/app/pnc/navigation/world_map_analysis.py:173`

The queue type supports `max_workers`, but `ScriptRunner` lazily caches one `p2_observation_builder` variable without a lock or thread-local ownership. The default queue uses one worker today, so this is dormant. It becomes a bug as soon as P2 throughput work increases workers.

Clean fix:

1. Keep `max_workers=1` as an explicit invariant until OCR services/builders are proven safe.
2. If multiple workers are needed, use a thread-local builder factory or a locked pool of independent builders.
3. Add a test that concurrent P2 analysis does not share mutable OCR/cache state accidentally.

### P2. P1 fallback capture metrics undercount recaptures

References:

- `pnc_automation/app/pnc/navigation/world_map_search.py:3678`
- `pnc_automation/app/pnc/navigation/world_map_search.py:3693`

`p1_fallback_capture_count` increments only when `p1_captures` is non-empty but no capture matches the current observation. If no capture was recorded at all and the code recaptures, the profile still reports zero fallback captures.

Clean fix:

1. Count every recapture in `_resolve_p1_movement_proof_capture()`.
2. If useful, split the metric into `missing_p1_capture_count` and `mismatched_p1_capture_count`.
3. Add a test for the empty-capture fallback path.

### P2. Parser/inventory completion is still modeled, not implemented

References:

- `pnc_automation/app/pnc/navigation/world_map_sweep.py:382`
- `pnc_automation/app/pnc/navigation/world_map_sweep.py:412`
- `pnc_automation/app/pnc/navigation/world_map_search.py:3746`

The sweep module defines element detections, coverage windows, parser completeness metrics, and duplicate merge fields, but P2 runtime still applies a rich observation through `WorldMapSurveyRecorder.ingest_checkpoint_observation()`. There is no deterministic coordinate-attributed inventory merge for sampled frames yet.

Clean fix:

1. Keep `WorldMapSurveyRecorder` as the single writer, but add an ingest method for immutable sample-analysis results.
2. Represent parsed, unknown, uncertain, duplicate, and coverage-gap records explicitly.
3. Add replay tests proving the same ordered screenshots produce the same persisted inventory and coverage outputs.

## Suggested Cleanup Order

1. Fix production segment start alignment before any multi-row live validation.
2. Introduce explicit actual-sample records and update profiles/visited semantics.
3. Strengthen P2 work item proof/projected-evidence validation.
4. Remove unreachable checkpoint-loop async branches.
5. Make P2 treatment-to-request mapping real or remove the unused treatment distinction until implemented.
6. Extend queue/profile telemetry to satisfy the OCR throughput plan.
7. Implement true projection and inventory merge only after the actual-sample ownership is clean.

## DRY / Ownership Check

- Canonical coordinate parsing remains in `world_map_coordinates.py`.
- Canonical exact/root proof now mostly lives in `world_map_proof.py`.
- P2 queueing has one main implementation in `world_map_analysis.py`.
- The main remaining DRY risk is semantic duplication: planned route checkpoints, actual P1 samples, projected frames, and survey-ingested observations are currently overlapping concepts without one canonical sample model.
