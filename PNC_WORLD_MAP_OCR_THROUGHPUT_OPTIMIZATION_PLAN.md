# PNC World-Map OCR Throughput Optimization Plan

## Status

Active as of July 8, 2026. This plan supersedes the remaining performance slice from [PNC_WORLD_MAP_PROOF_STABILITY_AND_LONG_SWEEP_PERFORMANCE_PLAN.md](PNC_WORLD_MAP_PROOF_STABILITY_AND_LONG_SWEEP_PERFORMANCE_PLAN.md).

## Purpose

Optimize the two measured OCR throughput bottlenecks on the canonical world-map production path:

1. P1 coordinate proof speed, especially alternate coordinate OCR preprocessing/crop strategies.
2. P2 checkpoint/sampled-frame builder throughput, especially avoiding queue backpressure during long production sweeps.

The work is benchmark-first. No implementation change is accepted without before/after evidence showing where time moved and proving correctness did not regress.

## Current Baseline

### P1 Granular Baseline

Command:

```powershell
python tools\benchmark_world_map_p1_capture.py --account serious_stuff --iterations 10 --label serious_stuff_p1_speed_baseline_10it --skip-prepare
```

Live instance/account:

- account: `serious_stuff`
- preflight coordinate: `(134, 538)`
- movement-proof artifact selection: `[]`

Mean timings:

- `ObservationService.capture_observation(...movement_proof...)`: `1310.82ms`
- internal screenshot capture: `593.16ms`, `45.3%`
- internal coordinate-only builder/proof: `717.56ms`, `54.7%`
- residual service side effects: `0.11ms`, effectively `0.0%`
- raw ADB screenshot bytes: `397.21ms`
- `ScreenshotService.capture(...persist=False)`: `472.65ms`
- coordinate-bar OCR only: `766.58ms`
- coordinate-only builder on existing screenshot: `1054.86ms`
- P2 checkpoint builder on existing screenshot: `5945.57ms`

Validated conclusions:

- `ObservationService` wrapper overhead is not a bottleneck.
- Routine movement-proof artifact persistence is disabled and is not a bottleneck.
- P1 cost is dominated by screenshot capture plus coordinate OCR/proof.
- P2 builder cost is off the immediate P1 movement-critical path only while the bounded queue has spare capacity.

### Focused Coordinate/Screenshot Microbenchmark

The live microbenchmark split the suspicious P1 pieces further on the same coordinate `(134, 538)`.

Mean timings over `8` iterations:

- raw ADB screenshot bytes: `435.61ms`
- PNG decode: `15.92ms`
- `ScreenshotService.capture(...persist=False)`: `367.72ms`
- coordinate crop/filter preprocessing: `1.66ms`
- raw coordinate-region OCR: `508.99ms`
- canonical filtered coordinate text OCR: `565.62ms`
- coordinate parse: `0.02ms`
- canonical coordinate viewport proof: `535.19ms`
- coordinate-only builder: `544.61ms`
- full service movement-proof capture: `937.95ms`

Observed OCR text on that viewport:

- raw region OCR: `X:134` and `Y:538`
- filtered OCR: `X:134` and `Y-538`
- both parsed to `(134, 538)`

Validated conclusions:

- `ScreenshotService` is not adding a large copy; capture comparisons are noisy because they are separate live captures. Added local decode work is around `15-20ms`.
- Coordinate parsing is effectively free.
- Crop/filter preprocessing is effectively free.
- RapidOCR runtime on the coordinate crop is the P1 proof hotspot.
- Raw coordinate-region OCR was faster and cleaner than filtered OCR for this viewport, but filtered/fallback behavior exists because prior live screenshots needed it. Any change must prove stability on hard fixtures.

## Non-Goals

- Do not remove `ObservationService` or `CapturedObservation` for performance unless a benchmark first shows residual overhead above `1%`.
- Do not add a second "fast sweep" mode or a parallel parser.
- Do not move coordinate parsing out of `world_map_coordinates.py`.
- Do not widen coordinate parser tolerance to hide OCR source defects.
- Do not optimize P2 by recapturing screenshots or dropping P1 screenshot/proof identity.
- Do not rely on dry estimates as acceptance evidence for live throughput.

## Phase 0. Benchmark Harness And Evidence

Before behavior changes, make benchmark evidence reproducible and granular enough to diagnose regressions.

Required work:

1. Extend or add a saved-screenshot coordinate proof benchmark that reports:
   - crop bounds materialization
   - crop/filter preprocessing
   - OCR image encode
   - OCR backend time
   - parse time
   - primary OCR success/failure
   - fallback OCR success/failure
2. Extend or add a live coordinate proof benchmark using the same stage names.
3. Extend or add a P2 builder benchmark that reports:
   - queue wait
   - builder wall time
   - selector detection time
   - full-frame or map-region OCR time
   - extra region OCR time
   - coordinate OCR repeat count
   - spatial surface/object parsing time
   - artifact/debug sidecar time
4. Persist benchmark JSON artifacts when they are used as acceptance evidence.
5. Add a comparison helper or documented command that prints before/after deltas.

Acceptance gates:

- Benchmarks run offline on saved screenshots without BlueStacks.
- Live benchmark can run against a prepared English account.
- Benchmark output identifies whether time belongs to P1 screenshot capture, P1 coordinate OCR/proof, P2 rich builder work, or queue/backpressure.

## Phase 1. P1 Coordinate OCR Strategy Experiments

Goal: reduce exact coordinate proof time while preserving the hard-won stability of world-map coordinate proof.

Candidate experiments:

1. Try raw coordinate-region OCR first when it parses strictly, then fall back to filtered OCR.
2. Benchmark smaller/tighter crops around the actual coordinate text inside the coordinate bar.
3. Benchmark alternate scale factors for `build_world_coordinate_bar_ocr_image`.
4. Benchmark grayscale/threshold preprocessing against the current blue/cyan isolation.
5. Benchmark OCR input format and encoded crop size, because `RapidOcrService` encodes the crop before OCR.
6. Benchmark whether cached selector bounds/materialized coordinate regions are measurable on hot P1 paths.
7. Keep top-HUD fallback as a bounded fallback only, never as routine work.

Correctness gates:

- All existing coordinate proof unit tests pass.
- Hard live fixture screenshots still parse the expected coordinates.
- Out-of-domain or malformed OCR still fails fast.
- Raw-first or alternate preprocessing must not silently accept unrelated world labels as coordinates.

Performance gates:

- Coordinate-only proof on existing screenshots improves by at least `20%` mean on the live benchmark before we accept the change.
- Live P1 service capture improves by a measurable amount consistent with the coordinate-proof improvement.
- The benchmark must report fallback counts so a speedup is not hiding a stability regression.

## Phase 2. P2 Builder Throughput And Backpressure

Goal: keep P2 from becoming the long-sweep limiter once P1/movement can outrun rich analysis.

Current risk:

- P2 checkpoint builder measured about `5945.57ms` mean on an existing screenshot.
- P2 is asynchronous in production through `WorldMapViewportAnalysisQueue`.
- It is off the P1 critical path only while the bounded queue has room.
- If P2 remains slower than the P1-plus-movement cadence, the queue fills and production movement blocks on `drain_next()`.

Candidate optimizations:

1. Add a proof-aware P2 analysis context seeded by:
   - known screen type `PNC_WORLD_MAP`
   - P1 exact coordinate proof or projected coordinate window
   - P1 screenshot identity
   - inventory/checkpoint treatment kind
2. Avoid routine P2 coordinate-bar OCR when P1 proof is exact and fresh.
3. Avoid broad generic screen-classifier probes for already-proven world-map screenshots.
4. Add screenshot-scoped OCR reuse inside one P2 work item.
5. Limit routine inventory P2 OCR to the map scene/object region, not static top HUD, bottom nav, popup guards, or debug sidecars.
6. Split P2 treatment profiles:
   - inventory-only
   - checkpoint-search
   - diagnostic/full guarded
7. Report queue backpressure explicitly:
   - queue wait time
   - worker run time
   - drain time
   - peak depth
   - times movement blocked because pending P2 reached max depth

Correctness gates:

- P2 must consume the P1 screenshot, not recapture.
- P2 must not duplicate P1 coordinate OCR except through explicit counted validation/fallback policy.
- P2 workers remain analysis-only; coordinator remains the single writer for survey/index state.
- Replaying the same ordered screenshots produces deterministic inventory output.

Performance gates:

- P2 builder mean improves by at least `30%` before a P2 optimization is accepted as meaningful.
- Production row benchmark reports no routine queue-backpressure blocking at the configured queue depth, or reports exactly where blocking occurs.
- P2 drain is bounded and visible in the profile.

## Phase 3. Production Row Validation

After Phase 1 or Phase 2 changes, validate on the canonical production path rather than only in isolated microbenchmarks.

Required live sequence:

1. Run P1 granular benchmark before change.
2. Run targeted saved-screenshot tests/benchmarks.
3. Implement the smallest canonical change.
4. Run the same P1/P2 benchmark after change.
5. Run a bounded production row/segment benchmark.
6. Stop on the first proof, parser, coverage, queue, or determinism regression.

Production metrics required:

- exact P1 proof count
- projected/intermediate frame count if sparse proof is used
- P1 screenshot capture time
- P1 coordinate proof time
- P2 queue submissions
- P2 worker run time
- P2 queue wait/drain time
- P2 peak depth
- P2 backpressure block count and duration
- P2 recapture count
- duplicate coordinate OCR count
- parsed inventory count
- unknown/uncertain element count
- coverage-gap count

## Definition Of Done

This plan is done only when all of the following are true:

1. P1 coordinate proof benchmarks identify stage timings and fallback counts.
2. A P1 OCR strategy change improves live coordinate proof by at least `20%` without losing fixture/live proof stability.
3. P2 builder benchmarks identify OCR, selector, parsing, and artifact/debug costs.
4. A P2 throughput change improves P2 builder time by at least `30%` or proves P2 is no longer causing row-level backpressure.
5. Production row/segment benchmark shows movement/P2 overlap with bounded queue depth and no unreported backpressure.
6. P2 still reuses P1 screenshot/proof identity and does not routine-recapture.
7. Full offline tests pass.
8. Live validation artifacts and benchmark JSON are retained for before/after comparison.

## Immediate Next Step

Implement Phase 0 first:

1. Convert the focused coordinate microbenchmark into a reusable tool or extend `tools/benchmark_world_map_p1_capture.py`.
2. Add saved-screenshot benchmark fixtures for normal and hard coordinate-bar cases.
3. Add P2 builder stage instrumentation so the `~5.9s` checkpoint-builder cost is split before changing P2 behavior.

Only after those benchmarks exist should Phase 1 or Phase 2 implementation changes begin.
