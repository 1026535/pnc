# PNC World-Map Proof Stability And Long-Sweep Performance Plan

> Status: **closed / superseded as of July 8, 2026**.
>
> This document is retained as historical context for the world-map proof, traversal, and long-sweep work already completed or partially implemented. New active performance work is tracked in [PNC_WORLD_MAP_OCR_THROUGHPUT_OPTIMIZATION_PLAN.md](../../PNC_WORLD_MAP_OCR_THROUGHPUT_OPTIMIZATION_PLAN.md), which narrows the next implementation slice to benchmark-proven P1 coordinate OCR/proof speed and P2 checkpoint-builder throughput.

## Purpose

Define one clean implementation plan for the next three world-map priorities:

1. a short stability gate for edge/corner world-map proof
2. performance work on the canonical long-sweep search path
3. production full-map sweeping under `30 minutes` with coordinate-attributed parsed inventory

This document intentionally treats those as one ordered program instead of two unrelated fixes. Broad sweep performance is not worth tuning until the world-map proof seam is stable at the exact edge/corner states the sweep must traverse.

## Current Implementation Status And Definition Of Done

This document was the canonical plan for the broader proof-stability and long-sweep program. It is now closed because the remaining work has been narrowed to measured OCR throughput bottlenecks in [PNC_WORLD_MAP_OCR_THROUGHPUT_OPTIMIZATION_PLAN.md](../../PNC_WORLD_MAP_OCR_THROUGHPUT_OPTIMIZATION_PLAN.md).

As of June 25, 2026, the plan is partially implemented and is explicitly **not complete**. The canonical production search now executes bounded asynchronous P1-screenshot/P2 treatment and has a live-smoked production segment executor, but real sampled-frame inventory/coverage merge, complete profiling, live multi-row calibration, and the required live sequence remain unfinished.

### Completion Vocabulary

The following terms are intentionally distinct and must not be used interchangeably:

- `modeled`: typed contracts, policies, or queue classes exist
- `offline-wired`: deterministic tests exercise a path with fakes or saved screenshots
- `production-wired`: the canonical live exhaustive-sweep entry point executes that path without a tool-only or test-only bypass
- `live-validated`: reviewed live artifacts and profiles prove the production path's behavior
- `done`: every required offline, production-wiring, live-behavior, inventory, and duration gate below passes

A phase or the overall plan must never be called complete because its models exist, its queue class has isolated unit tests, or a synchronous substitute passes. Intermediate milestones may be recorded as `modeled` or `offline-wired` only.

### Verified So Far

Implemented and live-validated:

- edge/corner coordinate proof stability was improved with fixture-backed OCR and dialog-proof regressions
- broad full-map entry can use the coordinate-jump primitive instead of hundreds of local swipe legs
- itinerary steps can carry per-step movement intent so the non-local entry leg and local checkpoint legs are dispatched differently
- the search path records movement timing profiles, including the cost of synchronous movement follow-up observation
- a live English-account benchmark completed `25` exact checkpoints from `(0, 0)` through `(240, 0)` on the canonical diagnostic search path

Production-wired and offline-validated, but **not yet live-validated**:

- `world_map_proof.py` owns exact/root proof vocabulary and bounded proof refresh policy
- ordinary movement captures and validates narrow coordinate proof in P1, retaining the exact screenshot for P2 without rich object treatment
- `world_map_analysis.py` defines screenshot-only P2 work items, immutable results, deterministic bounded backpressure, and first-failure propagation
- production full-map policy submits P2 work through the queue owned by `WorldMapSearchService`; the coordinator alone ingests ordered results
- P2 builds the rich observation from the exact P1 screenshot and P1-proven coordinate, without passing an Observation through the queue or repeating coordinate OCR
- the live runtime owns independent P1 and lazily initialized P2 OCR/observation pipelines
- deterministic integration tests prove nonzero movement/P2 overlap, bounded depth, screenshot identity reuse, and worker-failure propagation

Modeled or offline-wired, but **not production-complete evidence**:

- `world_map_sweep.py` defines sweep policies, route-to-segment grouping, sampled-frame projection, coverage windows, element-detection records, parser metrics, and an offline estimator
- offline tests prove route and segment geometry over `(0, 0)` through `(511, 1023)`
- the production full-map policy now branches to a canonical row/lane segment executor instead of reusing exact-checkpoint traversal
- production row/lane traversal now follows actual proven coordinates rather than forcing every sample back to planned route coordinates
- every production sample is a narrow P1 coordinate-proof capture; P2 receives the exact screenshot plus the actual P1-proven coordinate and no Observation object
- correction is a coverage-gap fallback only: if adjacent actual sampled coordinates are within the modeled visible scan footprint, movement continues along the trajectory without snapping to the planned checkpoint
- production segment profiles report segment movement, start/end anchor proof, sample count, queue depth, drain, and movement/P2 overlap count

Still required:

- complete queue wait/run, P1 proof, OCR-stage, coordinator-merge, and overlap-duration profiling beyond the current count/depth/drain metrics
- live multi-row trajectory calibration with coverage-gap fallback counts and actual-coordinate inventory output
- sampled-frame parsing into real coordinate-attributed map-element inventory with deterministic duplicate merge and coverage-gap accounting
- the row, three-row, 10-minute soak, and full under-30-minute English-account live validation sequence

Live validation attempted on June 19, 2026, but the escalated shell did not launch either the bounded Python benchmark or the lower-level `HD-Adb.exe devices` preflight: no process, console output, or new artifact was observable. This was infrastructure-blocked evidence, not a passing or failing application benchmark.

On June 22, 2026, the production P1/P2 checkpoint pipeline was live-validated on `157_farm` after fixing inaccessible Windows process-metadata fallback and unifying P1-to-P2 landing validation with the canonical movement tolerance policy:

- bounded 3-checkpoint production run: `35.26s` search time, `3` P2 submissions, peak depth `2`, movement/P2 overlap count `2`, zero P1 fallback captures, and `3.03s` final drain
- bounded 10-checkpoint production run: `55.49s` search time, `10` P2 submissions, peak depth `2`, movement/P2 overlap count `9`, zero P1 fallback captures, and `2.65s` final drain
- the 10-checkpoint movement total was `52.80s`; excluding the `13.13s` non-local entry, the nine steady-state checkpoints averaged about `4.41s` each
- P2 kept up with movement at this cadence, but extrapolating exact checkpoint treatment over `5,460` checkpoints is about `6.7 hours`, so this evidence validates the P1/P2 split and simultaneously confirms that Phase 3 continuous segment traversal remains required

The same `157_farm`, radius-`12`, stride-`6`, 10-checkpoint geometry was then run with the existing diagnostic synchronous-P2 policy for an apples-to-apples comparison:

- movement was effectively identical: `52.80s` async versus `52.82s` synchronous
- synchronous rich P2 treatment added about `26.34s` inside the checkpoint loop
- asynchronous execution replaced that inline cost with a `2.65s` final drain and completed the canonical search in `55.49s`
- therefore the asynchronous pipeline was about `30%` faster overall for this sample; it did not measurably slow movement, although movement remains the dominant bottleneck

On June 23, 2026, the first production row/segment live smoke passed on `157_farm` after two live-discovered fixes:

- sparse sample projection now uses actual proven anchor coordinates instead of planned route coordinates
- endpoint correction was demoted from normal behavior to a fallback and then reworked toward the June 25 coverage-first model
- bounded 3-sample segment run: `26.46s` total, `3` P2 submissions, peak depth `2`, movement/P2 overlap count `2`, and stop reason `checkpoint_budget_exhausted`
- the raw segment movement cost was only about `3.05s`, proving the row/segment direction is promising; the next performance target is reducing P1 proof/correction overhead without losing coverage

### Hard Definition Of Done

The plan is done only when every item below is true. A later item cannot be waived because an earlier benchmark passed.

1. Exact/root world-map proof is stable at interior, edge, and corner states with deterministic saved-screenshot regressions.
2. The canonical route and coverage audit cover the full reviewed domain `(0, 0)` through `(511, 1023)` without gaps beyond policy.
3. Non-local route entry is the first itinerary leg and uses coordinate jump when available and verified.
4. Ordinary movement follow-up uses one canonical P1 capture/proof implementation. P1 captures the settled screenshot, proves the coordinate, and emits a typed immutable payload for P2.
5. P1 does not perform rich object inventory, broad selector probing, or full-frame P2 OCR on the ordinary critical path. Any fallback is bounded, explicit, counted, and visible in profiles.
6. Rich checkpoint and sampled-frame analysis uses one canonical P2 implementation. Exact checkpoint work receives the exact P1 screenshot/proof payload; production sampled-frame work receives the P1 screenshot plus the actual P1-proven coordinate and any bounded projection/uncertainty context. P2 does not recapture that viewport or re-OCR P1 coordinate facts except through explicit measured validation policy.
7. The canonical production exhaustive-sweep entry point submits P2 work to a bounded worker queue. Merely constructing a queue, testing it in isolation, or offering an unused async option does not satisfy this item.
8. Production exhaustive execution demonstrably overlaps movement and P2: while P2 work for screenshot `N` is pending or running, P1 is allowed to capture/prove a later safe screenshot. Both a deterministic integration test and a live profile must prove non-zero overlap.
9. Queue behavior is fail-fast and deterministic: depth is bounded, the first worker exception reaches the search boundary, completion drains or cancels deterministically, and outputs are applied in route/sample order.
10. P2 workers return immutable results only. `WorldMapSurveyRecorder` and `WorldMapSurveyIndex` remain coordinator-thread single-writer owners.
11. Replaying the same ordered screenshot inputs produces the same inventory, unknown/uncertain records, coverage windows, and duplicate merges.
12. Production full-map execution uses trajectory-based row/segment traversal with actual-coordinate P1 samples, deterministic coverage-gap checks, and explicit uncertainty limits. Correction is allowed only when adjacent actual samples can leave an unobserved coverage gap. Exact-checkpoint traversal remains diagnostic only.
13. The completed sweep produces a coordinate-attributed inventory of parsed, unknown, and uncertain map elements plus explicit coverage-gap metrics; movement-only success is failure.
14. The production profile reports P1 capture/proof time, P2 queue wait/run/drain time, queue peak depth, overlap time/count, OCR/analysis time, coordinator ingest/merge time, dropped frames, and recapture/re-OCR fallback counts.
15. The reviewed English-account validation sequence passes in order: one row, three rows, 10-minute parsed soak, then full parsed map.
16. The production full parsed map, including final P2 drain, deterministic merge, coverage audit, and persistence, completes in under `30 minutes`.
17. Focused tests, the full offline suite, production-wiring integration tests, and all required live validations pass with retained profiles/artifacts.

### Explicit Non-Completion Conditions

The plan or P1/P2 phase is **not done** if any of the following is true:

- only P1/P2 models, a queue class, or isolated queue tests exist
- P2 is invoked synchronously inside the movement loop for exhaustive production execution
- the production exhaustive path calls the analyzer directly instead of submitting through the bounded queue policy
- P2 receives an observation produced by recapturing the viewport instead of the P1 screenshot payload
- movement waits for rich element OCR/analysis when only P1 coordinate proof is required for the next safe move
- a profile omits queue depth, overlap, drain, P2 failure, recapture, or fallback metrics
- the live profile has no P2 work, zero queue activity, or no demonstrated movement/P2 overlap
- a benchmark covers movement but does not parse, merge, and persist coordinate-attributed element inventory
- an estimator predicts under `30 minutes` but the reviewed full live parsed sweep has not passed
- only the exact-checkpoint diagnostic policy passes

### Required Acceptance Evidence

| Gate | Required automated evidence | Required live evidence |
| --- | --- | --- |
| P1 critical path | Test proves ordinary movement emits one typed screenshot/proof payload without rich P2 treatment | Profile separates P1 capture/proof and shows no unreviewed full-runtime fallback |
| P2 screenshot reuse | Test proves P2 receives the same screenshot identity and performs no recapture | Profile reports zero routine P2 recaptures and zero duplicate coordinate OCR |
| Production queue wiring | Integration test invokes the canonical exhaustive entry point and observes queue submission | Profile reports submissions, peak depth, wait/run/drain timings |
| Real overlap | Deterministic blocking-worker test proves movement advances while earlier P2 work remains incomplete | Timeline/profile shows positive movement/P2 overlap |
| Deterministic single-writer merge | Repeated input replay produces byte-equivalent ordered inventory output | Soak/full run completes without worker-side index mutation or ordering drift |
| Parsed coverage | Fixture/integration tests retain parsed, unknown, uncertain, duplicate, and gap records | Row, three-row, soak, and full runs report coverage and inventory metrics |
| Runtime target | Estimator and profile schema are complete | Full parsed map including P2 drain and persistence is under `30 minutes` |

## Current Context

### Runtime Architecture Today

The current world-map stack is already much cleaner than the earlier search prototypes:

- `pnc_automation/app/pnc/vision/world_map_coordinates.py`
  - canonical owner for coordinate-bar OCR filtering and coordinate parsing
- `pnc_automation/app/pnc/vision/pnc_observation_enricher.py`
  - canonical owner for building `PNC_WORLD_MAP` and `PNC_WORLD_MAP_ROOT` observation additions
- `pnc_automation/app/pnc/vision/observation_builder.py`
  - canonical owner for selector-region OCR and final observation assembly/classification
- `pnc_automation/app/pnc/navigation/world_map_traversal.py`
  - canonical owner for route geometry and execution-step planning
- `pnc_automation/app/pnc/navigation/world_map_search.py`
  - canonical owner for search orchestration, checkpoint traversal, movement proof integration, checkpoint ingestion, and stop-policy evaluation

That ownership model is the right base. The next work should preserve it rather than creating new task-local helpers or alternate sweep implementations.

### June 6, 2026 Live Evidence

On June 6, 2026, live validation on the `serious_stuff` BlueStacks instance established two important truths:

1. The canonical full-map serpentine route is real and large.
   - The resolved `SERPENTINE_ROW_SWEEP` full-map route produced `5460` checkpoints.
   - A successful long-budget run with `movement_step_budget=500` did reach `(0, 0)` from an arbitrary starting viewport and then advanced through multiple early checkpoints.
   - Observed timings from that successful pass:
     - start coordinate: `(393, 701)`
     - step `0` to `(0, 0)`: about `584.96s`
     - steps `1` through `5`: about `20.18s`, `13.92s`, `13.77s`, `13.62s`, `12.47s`
     - post-initial sampled pace: about `14.79s` per checkpoint across those early local steps

2. The same path is still not live-stable enough after restart.
   - After restarting BlueStacks and the game, the same broad serpentine repro started from proven `PNC_WORLD_MAP` at `(134, 538)`.
   - The initial reposition toward `(0, 0)` failed near `(0, 26)`.
   - The thrown runtime error was not "left world map"; it was "could not prove a parsed world-map surface."
   - The failure screenshot still visibly showed a valid world-map frame with coordinate text `X:0 Y:4`.
   - The key artifact was:
     - `artifacts/2026-06-06/serious_stuff/20260606T164436Z_live_serpentine_restart_confirm_step_0_failure_51.png`

That combination is decisive:

- the broad route shape is correct enough to validate,
- the current blocker is no longer just "movement budget too small,"
- the next gating issue is exact proof stability near edge/corner traversal states,
- and the biggest performance defect is that the first full-map entry/reset is still being treated like ordinary local swipe traversal.

### June 7, 2026 Benchmark Evidence

After widening and validating the canonical coordinate-bar proof path, the same bounded full-map serpentine benchmark was rerun on the `testing` BlueStacks/account target because `serious_stuff` was on a small account that could not reliably access the world map.

The run proved the coordinate-truncation blocker was removed:

- account: `testing`
- resolved route size: `5460` checkpoints
- start coordinate: `(334, 510)`
- requested bounded validation: `max_checkpoints=1`
- result: reached and ingested checkpoint `(0, 0)`
- stop reason: `checkpoint_budget_exhausted`
- profile artifact:
  - `artifacts/2026-06-07/testing/20260607T202016Z_testing_live_serpentine_after_y_truncation_fix_1cp_profile.json`

The benchmark also clarified the true movement bottleneck:

- total measured search time: `530.70s`
- movement trace count: `88` swipe legs
- summed action time: `530.68s`
- average action time per leg: about `6.03s`
- route planning time: about `17ms`
- persistence time: less than `1ms`
- all recorded movement classifications were `moved`

So the dominant cost is not route planning, matching, ingestion, or persistence. It is the initial long-distance local swipe entry to the first checkpoint. The benchmark spent essentially all runtime moving from `(334, 510)` to `(0, 0)` by ordinary swipe legs.

That benchmark also exposed a route-entry semantics correction:

- full-map mapping must cover the entire known P&C coordinate domain from `(0, 0)` through `(511, 1023)`
- the itinerary can be constructed by the requested pattern and geometry, and must include an initial entry leg from the current/original viewport, usually the castle/self position, to the first itinerary checkpoint
- that entry leg is just another itinerary step with non-local/jump intent, for example `(my_position) -> (0, 0)`, not a clunky executor-owned pre-step
- ordinary checkpoint traversal begins after the itinerary has executed the entry leg and sampled the first checkpoint through the normal checkpoint ingestion path
- the current code already has a coordinate-dialog jump primitive using the world-map coordinate/search button, but the broad search plan must require or prefer it for route entry instead of silently falling back to hundreds of local swipes

### June 7, 2026 Single-Viewport Movement Benchmark Evidence

After the route-entry benchmark, a focused single-viewport movement benchmark was run on the same `testing` BlueStacks/account target to isolate why ordinary viewport-to-viewport movement is slow.

The canonical no-artifact movement-proof run moved from `(362, 510)` to `(372, 510)`:

- profile artifact:
  - `artifacts/2026-06-07/testing/20260607T205728Z_testing_single_viewport_move_canonical_proof_benchmark.json`
- total move time: `31.67s`
- movement cycles: `5`
- raw ADB swipes: `4.82s` total, about `0.96s` per swipe
- screenshot capture bytes: `4.35s` total, about `0.87s` per capture
- observation builder time: `21.74s` total, about `4.35s` per post-swipe observation
- full-frame OCR: `12.57s` total
- extra region OCR: `8.40s` total
- selector detection: `5.29s` total
- configured movement delays were only `50ms` stable delay plus `50ms` post-action observe delay per cycle

The movement path itself also needed too many cycles for a `10`-coordinate horizontal move:

- `(362, 510)` to `(364, 510)`
- `(364, 510)` to `(368, 510)`
- `(368, 510)` to `(374, 510)`
- `(374, 510)` to `(374, 510)` with an interior stall
- `(374, 510)` to `(372, 510)`

This makes the current bottleneck more precise:

- the large cost is not route planning
- the large cost is not configured sleeps
- the large cost is not screenshot persistence, because the canonical movement-proof run used no screenshot artifact persistence for movement proof
- the large cost is synchronous post-swipe observation work, especially full-frame OCR and repeated coordinate-region OCR
- that cost is multiplied by movement calibration/step sizing that turns one small local move into several proof cycles

The performance plan must therefore optimize two independent axes:

1. reduce synchronous per-cycle movement proof cost
2. reduce the number of movement-proof cycles required per local viewport move

### July 8, 2026 Granular P1 Capture/Proof Benchmark Evidence

The June 7 benchmark is now partially superseded for P1 diagnosis. The current implementation no longer runs rich full-frame world-map analysis on ordinary P1 movement proof: `ObservationRequest.world_map_movement_proof_follow_up()` uses coordinate-only proof, skips broad selector detection, disables routine movement-proof screenshot artifacts, and does not promote movement-proof misses to `full_runtime_default()`.

A granular live benchmark was added as:

- `tools/benchmark_world_map_p1_capture.py`

It was run on the live English `serious_stuff` account/instance on July 8, 2026 with `5` iterations:

- command:
  - `python tools/benchmark_world_map_p1_capture.py --account serious_stuff --iterations 5 --label serious_stuff_p1_granular_baseline --skip-prepare`
- preflight coordinate: `(141, 501)`
- movement-proof artifact selection: `[]`
- `ObservationService.capture_observation(...world_map_movement_proof_follow_up...)`: `973.99ms` mean
- internal screenshot capture inside `ObservationService`: `402.82ms` mean, `41.4%`
- internal coordinate-only observation build/proof: `571.13ms` mean, `58.6%`
- residual `ObservationService` wrapper/side effects: `0.04ms` mean, effectively `0.0%`
- raw ADB screenshot bytes: `359.14ms` mean
- PNG decode from existing payload: `13.71ms` mean
- debug-only screenshot artifact persistence from existing payload: `2.64ms` mean
- coordinate-bar OCR only on an existing screenshot: `651.98ms` mean
- coordinate-only `ObservationBuilder` on an existing screenshot: `616.26ms` mean
- P2 checkpoint builder on an existing screenshot: `3177.00ms` mean, but this is off the P1 movement-critical path when the P2 queue is active

This benchmark disproves the hypothesis that the `CapturedObservation` wrapper or `ObservationService` side effects are a meaningful P1 bottleneck. Removing the wrapper without changing screenshot capture or coordinate OCR would be noise.

The current P1 bottleneck is therefore:

1. screenshot transport/acquisition, about `0.34s` to `0.40s` per proof sample
2. coordinate-bar OCR/proof, about `0.57s` to `0.65s` per proof sample
3. the number of exact P1 proof samples required by the production trajectory

The under-30-minute target cannot be met by shaving milliseconds from service wrappers. At the current measured `~0.97s` per exact P1 sample, even `14,878` stride-`6` samples would spend about `4.0 hours` in P1 proof alone. The P1 speed plan must combine cheaper coordinate proof with fewer exact coordinate-proof samples, while preserving coverage and coordinate-attribution evidence.

## Vision

We want one world-map runtime that behaves like this:

1. Any operation that depends on exact world coordinates uses one canonical exact world-map proof seam.
2. That proof seam remains stable at normal interior states and at edge/corner states.
3. Long sweeps represent broad start positioning as an explicit non-local itinerary leg, not as hundreds of ordinary local swipe legs and not as an executor special case.
4. Once broad entry/reset is fixed, steady-state sweep traversal is measured and optimized on the same canonical search engine rather than through sidecar tooling or special-case search scripts.
5. Production full-map sweeps use policy-driven continuous segment traversal, sparse proof anchors, and parsed sampled frames to produce a complete coordinate-attributed inventory under the reviewed runtime budget.

## Goals

### Goal A. Stability Gate

Before broad performance work, make exact world-map proof stable enough that edge/corner traversal does not collapse into `UNKNOWN` simply because the coordinate bar is temporarily hard to prove.

### Goal B. Performance Work

After the proof seam is stable, improve the canonical long-sweep path in two ordered layers:

1. fix broad entry/reset cost first
2. then optimize steady-state checkpoint execution

## Non-Goals

This plan does not try to:

- redesign matcher semantics
- redesign stop-policy semantics
- add task-local search loops
- add legacy compatibility paths for older coordinate proof formats
- broaden parser heuristics indefinitely instead of improving the canonical proof source

## Architecture Requirements

The implementation must preserve these constraints:

- single canonical implementation per concept
- no duplicated logic across search, calibration, and live tooling
- fail-fast validation for invalid proof states and invalid movement states
- minimal boilerplate
- no fake "world-map surface" objects invented from weak evidence

## Core Problem Statement

### Problem 1. Exact world-map proof is still too fragile at edge/corner states

Today, broad traversal ultimately depends on exact proof of `SpatialSurfaceType.WORLD_MAP`, not merely a visual guess that "the map is probably still visible."

That is correct in principle, but the current proof seam still has three weaknesses:

1. coordinate-bar acquisition is still too dependent on one narrow OCR-region crop
2. the exact-proof refresh loop is search-owned instead of being a reusable proof owner
3. the system does not yet model proof strength explicitly enough for exact-vs-root decisions

The June 6 failure demonstrated this precisely:

- the game was still on world map,
- the screenshot still showed `X:0 Y:4`,
- but the runtime failed to produce an exact `WORLD_MAP` spatial surface,
- so movement failed even though the visual state still looked map-owned.

### Problem 2. The first full-map itinerary leg is mis-modeled as ordinary local traversal

The successful June 6 run also showed that the search engine can, in principle, progress with a larger budget.

But the timing makes the architectural defect obvious:

- a single initial move from arbitrary start to `(0, 0)` took about `585s`
- later local checkpoint progression settled closer to `13s` to `15s` per checkpoint

This is not a pure micro-optimization issue. It means the first itinerary leg is using the wrong movement family.

The broad full-map sweep start should not be modeled as:

- "just do local direct traversal enough times until we happen to reach the first checkpoint."

It should be modeled as:

- "construct one complete itinerary from the current/original viewport through the requested map pattern, where the first itinerary leg from `(my_position)` to the pattern start, such as `(0, 0)`, is tagged as non-local/jump-capable."

For the reviewed full-map mapping scenario, the full coordinate domain is `(0, 0)` through `(511, 1023)`. The current route planner produces a deterministic full-map row/serpentine pattern over that domain; the missing performance seam is that the final itinerary should prepend the current/castle-to-start leg as a normal itinerary step with non-local intent.

### Problem 3. Performance work must stay on the canonical execution path

The right performance target is not a side tool or a special live repro script.

The right performance target is:

- `WorldMapSearchService.execute_search(...)`
- with one resolved `WorldMapResolvedSearchPlan`
- iterating one canonical `execution_plan.steps`

Any optimization that bypasses that path will create a parallel implementation and break the architecture.

### Problem 3a. Itinerary construction must include entry while itinerary execution stays agnostic

The route/itinerary should continue to be constructed from input geometry:

- pattern kind
- origin semantics
- boundary geometry
- stride policy
- perimeter corner/rotation or pattern-specific parameters
- coordinate-domain addressability

The current code already centralizes that construction in `world_map_traversal.py`, with `WorldMapSearchService.resolve_plan(...)` passing the request pattern, origin, bounds, stride, and pattern parameters into the traversal planner.

Validated current behavior:

- `WorldMapCoordinateDomain.puzzles_and_conquest()` defines the known full-map domain as `(0, 0)` through `(511, 1023)`.
- Full-map row-major and serpentine route construction produced `5460` addressable checkpoints in the reviewed benchmark configuration using an explicit `10`-unit stride.
- The canonical no-override viewport stride is now `6` units so production coverage biases toward overlap and live landing tolerance instead of replaying the older performance-benchmark stride by default.
- The existing traversal tests validate row-major, serpentine, perimeter, shrinking-perimeter, execution-step tagging, and stride resolution.
- The current full-map row/serpentine itinerary starts at `(0, 0)` and ends at `(511, 1023)` under the live parity/addressability model.

The important missing concept is not "how to build the pattern." It is that itinerary construction must compose the pattern route with the current start:

- the planner/search-plan layer identifies the first pattern checkpoint,
- prepends one itinerary leg from the current/original viewport to that checkpoint,
- tags that leg with non-local/jump-capable intent,
- and hands the executor one ordered itinerary.

The executor should remain agnostic: it iterates itinerary steps and dispatches each step according to its movement intent. For the entry leg, that dispatch should prefer the existing coordinate-dialog jump primitive when available. That primitive already opens the world-map coordinate/search button, fills the coordinate dialog, commits X/Y, and presses Go. The plan should therefore focus on representing the entry leg in the itinerary and routing its non-local intent through that existing primitive, not reinventing it.

### Problem 4. Movement proof and viewport analysis are currently coupled too tightly

A movement cycle needs a fast answer to a narrow question:

- after the swipe, are we still on the world map?
- what exact viewport coordinate did the world map settle on?

It does not need the full rich observation payload required for checkpoint sampling:

- full-frame OCR lines
- broad selector probe results
- object/resource/castle extraction
- internal-map viewport indexing
- debug sidecars

Today the movement proof path still pays much of the same observation cost as richer viewport analysis. That makes every correction leg expensive, and it prevents the sweep from overlapping expensive viewport analysis with movement to the next checkpoint.

The correct architecture is not a C++ rewrite or a parallel search loop. The correct architecture is one canonical two-phase observation pipeline:

- `P1`: synchronous movement proof
- `P2`: asynchronous viewport analysis and internal-map ingestion

`P1` remains on the critical path because the next movement leg depends on the post-swipe coordinate. `P2` can run behind the movement loop because checkpoint analysis does not always need to block the next physical move once the screenshot and coordinate proof have been captured.

### Problem 5. Code review shows implementation seams that must be corrected before P1/P2 work

The existing code already contains much of the intended architecture, but a review of the concerned implementation shows several seams that need to be made explicit in the target architecture.

First, movement-tool selection is currently too global:

- `WorldMapTraversalExecutionStep` already carries per-step movement semantics through `action_family`.
- `WorldMapSearchService.resolve_plan(...)` still resolves one plan-wide `movement_tool`.
- `WorldMapSearchService.move_to_checkpoint(...)` branches on the plan-wide movement tool before it considers the step action family.

That is compatible with "all swipe" or "all coordinate jump" runs, but it is the wrong shape for the desired route-entry behavior. The first itinerary leg may need coordinate jump while later local serpentine steps should stay swipe/local-direct. Therefore movement primitive selection must become per executable step.

Second, final checkpoint analysis is currently hidden inside the mover:

- `WorldMapCoordinateMover.move_to_coordinate(...)` accepts `arrival_observation_request`.
- The search service passes `ObservationRequest.world_map_checkpoint_analysis()` for the final leg.
- That avoids a second capture today, but it couples movement proof and rich checkpoint analysis inside the movement loop.

That coupling conflicts with the P1/P2 target. P1 should always produce a cheap movement proof plus the screenshot/proof payload. Checkpoint treatment should be a separate P2 work item built from that same payload, not an alternate final-leg follow-up hidden inside the mover.

Third, async P2 must respect single-writer indexing:

- `WorldMapSurveyRecorder` owns the mutable `WorldMapSurveyIndex`.
- Today checkpoint ingestion is deterministic because it happens synchronously in route order.
- A background P2 worker that mutates the recorder/index directly would make ordering, cancellation, and stop-policy behavior nondeterministic.

P2 workers should therefore build immutable analysis results. The search coordinator should be the only component that mutates the canonical survey inventory, and it should consume P2 results in route-index order unless a reviewed stop policy explicitly allows safe cancellation.

Fourth, observation requests currently do not constrain the initial selector probe enough:

- `ObservationRequest` carries `candidate_screen_types`, but `ObservationBuilder.build(...)` still starts by detecting `ScreenClassifier.probe_selector_ids()` across the broad classifier set.
- The broad probe set can invoke OCR-region and template selectors unrelated to a known world-map P2 treatment.
- `PillowTemplateMatcher.find_best_match(...)` is a naive full-image sliding scan, so every unnecessary template selector can be very expensive.

The target architecture should add one canonical selector-detection planning seam. The detection plan should derive the minimal selector ids from the analysis context, candidate screens, known screen proof, and required fallback guards. This should narrow the existing selector engine calls; it should not introduce a second selector engine.

Fifth, `ObservationRequest` is currently a screen-family permission model, not a complete cost profile:

- `world_map_checkpoint_analysis()` includes popup and loading guards.
- Those guards make sense when capturing an unknown post-action state.
- They are redundant for a P2 work item whose input is already a P1-proven world-map screenshot.

P2 should use an explicit observation treatment/profile that says what work is needed: coordinate proof reuse, world-map object inventory, selector/chrome enrichment, popup/loading guards, debug sidecars, and OCR scope. This can be represented as an extension of `ObservationRequest` or as an analysis-context field, but there must be one canonical owner for these cost choices.

Sixth, the action follow-up retry policy can accidentally defeat P1 performance:

- `ActionExecutor.observe_action_follow_up(...)` promotes many narrow `UNKNOWN` observations to `ObservationRequest.full_runtime_default()`.
- That is a good general navigation safety net.
- It is too expensive for the P1 movement-proof contract if every narrow proof miss immediately turns into full runtime OCR.

The P1 movement-proof path needs its own bounded retry/fallback policy: retry the narrow coordinate proof or fail with movement-proof diagnostics before falling back to full rich observation. Full-runtime retry should be explicit and measured, not an implicit side effect of a generic action follow-up.

Seventh, screenshot/OCR transport costs need first-class measurement:

- `ScreenshotService` captures full PNG bytes through `adb exec-out screencap -p`.
- `RapidOcrService` encodes every full image or crop to PNG bytes before invoking OCR.
- `read_world_coordinate_bar_text(...)` builds a filtered image crop before OCR.

Those costs are acceptable seams, but they must be separately measurable. Before considering lower-level transport changes, the canonical profile should distinguish screenshot transport, image decode, crop/filter preprocessing, OCR image encode, OCR backend runtime, selector detection, and artifact persistence.

These are not reasons to abandon the current architecture. They are the exact seams the current architecture is asking us to formalize.

## Proposed Solution

## Phase 1. Short Stability Gate For Edge/Corner World-Map Proof

### 1.1 Introduce one canonical world-map proof module

Extract the proof semantics now hidden inside `_require_proven_world_map_observation(...)` into a dedicated canonical helper module, for example:

- `pnc_automation/app/pnc/navigation/world_map_proof.py`

This module should become the single owner for:

- exact world-map proof
- root-level world-map proof
- proof-strength evaluation
- proof-strength-aware failure reporting

The goal is not to add a large service class. The lean design is:

- one small proof-strength enum
- one small proof-result dataclass
- one canonical pure proof evaluator that accepts an existing observation or P1 screenshot-derived facts
- one canonical refresh/capture helper that receives an observation callable instead of importing search orchestration

Suggested model:

- `WorldMapProofStrength.EXACT`
  - requires `observation.spatial_surface.surface_type == WORLD_MAP`
- `WorldMapProofStrength.ROOT`
  - accepts `PNC_WORLD_MAP_ROOT` style evidence without inventing a coordinate-bearing surface

Important constraint:

- `ROOT` must not synthesize a fake `SpatialSurfaceObservation`
- exact coordinate-bearing operations must still require `EXACT`

This keeps the domain model honest while still giving the runtime a cleaner proof vocabulary.

Important ownership split:

- `navigation/world_map_proof.py` owns the proof vocabulary and pure exact/root validation.
- `world_map_coordinates.py` owns coordinate OCR/parsing.
- `ObservationService` owns screenshot capture and movement-proof capture helpers.
- Navigation/search code consumes proof results but does not parse coordinates or implement private refresh loops.

This avoids moving search-local duplication into a new vision-local god helper. The proof module should be canonical, but not responsible for every action that happens before a proof can be evaluated.

### 1.2 Keep `world_map_coordinates.py` as the single coordinate-bar owner

The coordinate bar should continue to have one canonical owner:

- `world_map_coordinates.py`

Do not reintroduce alternate coordinate grammars in:

- the enricher
- search
- root fallback code
- live tooling

Instead, the proof gate should tighten the canonical acquisition stack in this order:

1. selector-region filtered OCR
2. selector-region raw OCR line fallback
3. bounded top-HUD canonical line parsing when exact crop proof is unavailable but the frame is still plausibly map-owned

That keeps one parser while giving it a better proof source.

### 1.3 Distinguish exact proof from retryable root proof

The key behavioral change is not "accept weaker proof forever."

The real change is:

- allow root-level evidence to keep the runtime inside the retryable world-map family during refresh,
- but require exact proof before coordinate-bearing movement or checkpoint ingestion continues.

That means:

- movement and checkpoint ingestion still fail fast if exact proof cannot be restored
- but the failure path becomes accurate: "map-owned but exact viewport proof unavailable" instead of a generic `UNKNOWN`

### 1.4 Add one canonical proof refresh policy

The proof helper should own the refresh strategy now duplicated implicitly across search-local behavior.

Suggested rules:

1. If the current observation already has exact world-map surface proof, return immediately.
2. If the current observation is root-visible or `UNKNOWN` but still retryable, perform bounded refresh using the existing observation service.
3. If the current observation is clearly not world-map-owned, fail immediately.
4. If refresh ends without exact proof, raise one fail-fast error that carries:
   - final `screen_type`
   - proof strength achieved
   - any visible coordinate text that was partially parsed

This preserves strictness while making the failure diagnostically correct.

### 1.5 Fix selector ownership instead of piling on parser tolerance

The June 6 evidence strongly suggests that `PNC_WORLD_COORDINATE_BAR` region ownership must remain reviewed and current for live layouts.

So the stability gate should explicitly include:

- validating the canonical selector crop against edge/corner live fixtures
- keeping the region in the reviewed selector registry
- adding fixture-backed tests for crop drift

This should stay in the selector/vision layer, not be patched in search.

### 1.6 Stability-gate implementation steps

1. Create `world_map_proof.py` and move canonical proof semantics there.
2. Replace `_require_proven_world_map_observation(...)` call sites with the shared helper.
3. Keep `world_map_coordinates.py` as the single coordinate-bar parse owner.
4. Extend proof acquisition to support:
   - filtered selector OCR
   - raw selector OCR lines
   - bounded top-HUD fallback using the same parser
5. Ensure `PNC_WORLD_MAP_ROOT` detection uses the same canonical coordinate-text matcher and proof vocabulary.
6. Improve fail-fast proof errors so they distinguish:
   - not world map
   - world-map root only
   - exact coordinate surface unavailable

### 1.7 Stability-gate test plan

Add deterministic fixture-backed tests under `tests/data/world_map/` and `tests/test_capture_and_vision.py`.

Required cases:

1. reviewed live edge/corner screenshot with visible `X:0 Y:4`
   - exact world-map proof should succeed
2. selector-region filtered OCR loses Y but raw OCR lines recover exact pair
3. selector-region OCR fails but bounded top-HUD fallback still recovers exact pair
4. root-visible world-map frame without exact coordinate pair
   - `ROOT` proof should succeed
   - `EXACT` proof should fail clearly
5. clearly non-world-map frame
   - proof should fail immediately

Use copied fixtures committed under `tests/data/` rather than relying on `artifacts/`.

### 1.8 Stability-gate acceptance criteria

This phase is done when all of the following are true:

1. Search, movement calibration, and live tools consume one canonical proof helper.
2. Exact proof no longer collapses into generic `UNKNOWN` on the reviewed June 6 edge/corner frame.
3. Root-vs-exact proof behavior is explicit and tested.
4. There is still exactly one coordinate-bar parser owner.
5. Full offline `unittest discover -s tests` remains green.

## Phase 2. Performance Work On The Canonical Long-Sweep Path

This phase starts only after Phase 1 lands.

### 2.1 Represent broad entry as the first itinerary leg

The central performance fix is architectural:

- the first move from arbitrary current viewport to the first sweep checkpoint is part of the itinerary, but it is not ordinary local checkpoint traversal
- the first pattern checkpoint is an itinerary target reached by a non-local/jump-capable entry leg, not proof that the local mover should spend hundreds of swipe legs getting there
- full-map mapping must cover the full known domain from `(0, 0)` to `(511, 1023)` according to the canonical itinerary pattern

So the canonical search plan should represent the itinerary entry leg explicitly.

Add one itinerary-entry movement intent to the resolved plan, for example:

- `WorldMapExecutionEntryStrategyKind`
  - `ALREADY_POSITIONED`
  - `LOCAL_ENTRY`
  - `NON_LOCAL_RESET`

Suggested ownership:

- `WorldMapResolvedSearchPlan`
  - stores the actual current viewport start coordinate
  - stores the resolved entry-leg strategy
  - exposes one ordered itinerary whose first step is `(current_coordinate) -> (first_pattern_checkpoint)` when not already positioned
- `WorldMapSearchService.execute_search(...)`
  - iterates the ordered itinerary without knowing whether a step is entry or steady-state beyond the step's movement intent

Important architecture rule:

- `world_map_traversal.py` should continue to own sweep geometry and checkpoint ordering
- current-position entry composition should be represented as itinerary construction, not as ad hoc executor logic
- itinerary execution must remain agnostic over entry-vs-steady-state; it consumes typed movement intent

The route planner owns "where to sweep."
The itinerary composer owns "how the current viewport connects to the route start."
The executor owns "execute the next itinerary step according to its movement intent."

### 2.2 Route non-local itinerary legs through the reviewed coordinate-jump primitive

For broad full-map sweeps, the first itinerary leg's movement family is non-local.

The implementation should not invent a search-only helper. It should reuse the reviewed world-map primitive stack:

- coordinate jump when available and verified
- overview-seed positioning when available and reviewed
- direct swipe fallback only when the plan explicitly resolves to local entry

For the current live P&C map, the non-local entry leg to the first itinerary checkpoint should prefer coordinate jump through the existing coordinate-dialog/search-button primitive. A local swipe fallback may exist for unsupported runtimes, but it must be visible in the benchmark output as `LOCAL_ENTRY` rather than hidden inside normal checkpoint traversal.

That means the long-sweep performance fix should integrate with the existing navigation primitive model rather than bypass it, while keeping itinerary execution generic.

The movement primitive must be selected per executable itinerary step, not once for the entire resolved plan.

Target architecture:

- `WorldMapTraversalExecutionStep.action_family` remains the canonical movement-intent input.
- A small movement-strategy resolver owned by `WorldMapSearchService` maps `(step.action_family, request.movement_preferences, runtime support)` to one concrete primitive.
- `NON_LOCAL_DIRECT` entry/reset steps prefer coordinate jump when supported and allowed.
- `LOCAL_DIRECT` checkpoint-to-checkpoint steps prefer the local swipe mover unless a future reviewed policy explicitly opts into another primitive.
- The search profile records the primitive used for each step instead of relying on one plan-wide `movement_tool` for every checkpoint.

Current code review note:

- `WorldMapSearchService.resolve_plan(...)` currently resolves one plan-wide `movement_tool`.
- `move_to_checkpoint(...)` currently branches on that plan-wide value before considering the step's `action_family`.
- Implementation should retire or demote the plan-wide field to summary metadata once per-step primitive resolution is introduced.

### 2.3 Keep steady-state sweep work on `execution_plan.steps`

After route entry is fixed, steady-state performance must stay tied to the canonical execution seam:

- iterate `plan.execution_plan.steps`
- do not build alternate checkpoint loops in tooling
- do not add sweep-only movement shortcuts outside the search service

Any additional optimization should improve:

- the existing move-to-checkpoint path
- the existing checkpoint ingestion path
- the existing observation/matching path

### 2.4 Add a canonical performance breakdown

We already have enough evidence to know that "total runtime" is too coarse.

The search engine should emit one canonical performance summary that separates:

- non-local entry-leg time
- checkpoint movement time
- checkpoint observation/proof time
- checkpoint ingestion/matching time

This should be built from the existing runtime diagnostics and movement traces instead of adding a second measurement system.

### 2.5 Split movement proof into P1 synchronous proof and P2 asynchronous analysis

The older single-viewport benchmark showed that ordinary movement was slow even after screenshot persistence was removed from movement proof. The current implementation has since narrowed ordinary P1 movement proof to coordinate-only OCR and moved rich viewport treatment to P2 for production sweeps. The remaining P1 problem is measured more precisely by the July 8 benchmark: exact proof still costs about `0.97s` per sample because screenshot acquisition and coordinate OCR remain synchronous.

Introduce one canonical two-task pipeline for world-map search. The boundary between the two tasks is the screenshot captured after movement settles:

- `Task 1 / P1WorldMapViewportMovement`
  - synchronous
  - owns viewport-to-viewport movement
  - captures the post-movement screenshot that proves where the viewport landed
  - parses the exact viewport coordinate
  - returns the minimum typed proof required to choose the next movement leg
  - hands the captured screenshot and coordinate proof to Task 2
  - must not run full-frame OCR unless the narrow proof path fails and policy permits a bounded fallback
  - must not run broad selector probing
  - must not perform object sampling or internal-map ingestion
- `Task 2 / P2WorldMapViewportTreatment`
  - asynchronous where the search mode permits it
  - receives the screenshot captured by Task 1 as its input
  - performs the expensive screenshot treatment work:
    - OCR
    - selector detection
    - rich observation building
    - visible element extraction
    - object/resource/castle matching
    - internal-map sampling
    - production of inventory-ready world-map sightings for coordinator ingestion
  - persists analyzed checkpoint artifacts according to the existing artifact policy
  - reports failures through the same search diagnostics rather than silently dropping viewport work

The ownership model should stay DRY:

- `world_map_coordinates.py` remains the single owner for coordinate parsing
- `navigation/world_map_proof.py` owns proof strength and P1 exact/root proof semantics
- `ObservationBuilder` remains the canonical rich observation builder for P2
- `WorldMapSearchService` owns queueing and consuming P2 checkpoint-analysis work because it owns search stop policy and checkpoint iteration
- no live tool or task gets a private observation pipeline

P1 should produce a compact typed result, for example:

- captured screenshot identity and timestamp
- optional screenshot artifact path
- screen/proof strength
- exact coordinate when available
- image size
- failure diagnostics when exact proof cannot be produced

P2 should accept the P1 screenshot/proof result and return the canonical analyzed checkpoint result used by existing ingestion/matching. It should not re-capture the same viewport unless the screenshot is missing or stale by explicit policy.

The essential pipeline contract is:

1. Task 1 moves from viewport to viewport and identifies the resulting coordinate.
2. Task 1 emits one screenshot plus coordinate proof.
3. Task 2 asynchronously receives that screenshot.
4. Task 2 performs OCR, observation building, and production of inventory-ready world-map sightings.
5. The search executor reconciles Task 2 results with checkpoint order, stop-policy semantics, and single-writer inventory ingestion.

#### High-level P1 implementation sketch

The intended P1 implementation should be small and explicit:

- add `pnc_automation/app/pnc/navigation/world_map_proof.py`
  - owns proof strength models and movement-proof result models
  - exposes one narrow helper that consumes a `CapturedScreenshot`, `SelectorRegistry`, and shared `OcrService`
  - reads `PNC_WORLD_COORDINATE_BAR` through the canonical selector bounds
  - delegates all coordinate OCR/parsing to `world_map_coordinates.py`
  - returns an exact coordinate-bearing proof or raises a diagnostic `SelectorResolutionError`
- add one `ObservationService` method for movement proof capture
  - captures one screenshot through the existing `ScreenshotService`
  - applies the existing `WORLD_MAP_MOVEMENT_PROOF` artifact policy
  - calls the P1 proof helper instead of `ObservationBuilder.build(...)`
  - returns one typed movement-proof capture result containing the screenshot and a minimal typed `Observation` with:
    - `screen_type=PNC_WORLD_MAP`
    - image size and captured timestamp
    - `PNC_WORLD_COORDINATE_BAR` visible element
    - `SpatialSurfaceObservation(surface_type=WORLD_MAP, viewport=<parsed coordinate>, objects=())`
  - does not run full-frame OCR
  - does not run the broad screen-classifier probe selector set
  - does not persist debug OCR sidecars
- route only movement-proof follow-ups through that method
  - `WorldMapCoordinateMover._execute_actions(...)` should use P1 only when the action follow-up request is exactly `ObservationRequest.world_map_movement_proof_follow_up()`
  - `WorldMapCoordinateMover` should not switch to rich checkpoint analysis on the final swipe leg through an `arrival_observation_request`
  - final checkpoint treatment should be scheduled by `WorldMapSearchService` from the P1 screenshot/proof payload
  - coordinate jumps, overview navigation, recovery, and other non-movement-proof flows should keep using their reviewed observation requests unless explicitly moved onto the same P1/P2 contract
- keep generic runtime retry policy from defeating P1
  - P1 movement proof should not automatically promote `UNKNOWN` or missing-coordinate proof to `ObservationRequest.full_runtime_default()`
  - bounded P1 retry should stay narrow: recapture/prove the coordinate bar, apply the reviewed coordinate fallback, then fail with diagnostics if exact proof is unavailable
  - any full-runtime fallback from P1 must be explicit, counted, and visible in the movement profile
- keep fake services aligned with the same seam
  - the shared test fake should expose the movement-proof method so unit tests verify the P1 routing contract
  - tests should assert that ordinary movement proof no longer records a rich observation request
  - tests should assert that checkpoint analysis consumes the P1 screenshot/proof payload instead of recapturing the same viewport

This Task-1/P1-only shape is an explicitly intermediate milestone. It may be marked `offline-wired`, but it does **not** complete the P1/P2 split, Phase 2, or this plan. Worker/queue integration may begin only after P1 is measurable and sufficiently narrow, and Phase 2 remains incomplete until the production exhaustive path actually uses that queue and demonstrates overlap.

#### High-level P2 implementation sketch

The intended P2 implementation should receive the same screenshot/proof produced by P1 and run the rich viewport treatment work outside the movement-critical path.

- add one canonical P2 work-item/result model
  - work item fields should include route index, checkpoint coordinate, P1 screenshot, P1 proof result, label, artifact selection, and search/stop-policy context needed for diagnostics
  - result fields should include route index, checkpoint coordinate, rich `CapturedObservation` or `Observation`, indexed world-map elements/sightings, matching result summary, elapsed timings, and any failure details
  - work items must be immutable enough that background processing cannot mutate movement state
  - work items must carry a copied/frozen screenshot payload, screenshot bytes, or an immutable artifact reference so background OCR cannot race with mutable PIL image state
- add one rich-analysis entry point owned by the existing observation stack
  - the entry point should build a full `Observation` from an existing `CapturedScreenshot` instead of capturing again
  - it should call the existing `ObservationBuilder`/`PncObservationEnricher` stack through an explicit analysis context rather than a parallel parser
  - it should return the rich observation plus parsed world-map sightings to the search coordinator
  - it should not mutate `WorldMapSurveyRecorder.index` directly from a worker thread
  - the search coordinator should ingest results into the canonical world-map element inventory in deterministic route-index order
  - it should preserve the existing checkpoint-analysis artifact policy
  - it should not introduce a second object parser, matcher, or internal-map writer
- add one canonical observation treatment/profile for P2
  - the profile should represent required work such as world-map object inventory, chrome/selector enrichment, popup/loading guards, debug sidecars, and OCR scope
  - P2 work from a P1-proven world-map screenshot should default to inventory treatment without popup/loading guard OCR unless explicitly requested
  - diagnostic mode can request richer guards/sidecars through the same profile instead of adding a separate diagnostic observation path
- add one selector-detection planning seam
  - the detection plan should derive selector ids from the analysis context, known screen, candidate screens, and required guards
  - known-world-map P2 treatment should avoid `ScreenClassifier.probe_selector_ids()` and run only the selector work required for that treatment
  - template detection should be avoided unless the planned selector ids and treatment profile require it
  - geometry materialization for known screens should remain canonical through `SelectorRegistry.materialize_for_screen(...)`
- add one bounded P2 executor owned by `WorldMapSearchService`
  - exhaustive sweep mode can enqueue analyzed-checkpoint work after P1 proves the coordinate
  - the executor should run P2 work on a small bounded worker pool or a single worker first
  - queue depth must be bounded and visible in diagnostics
  - the search result boundary must drain all queued work before returning
  - the first P2 exception must be propagated, not logged-and-forgotten
- preserve deterministic result ordering
  - movement may continue while P2 analyzes previous screenshots
  - ingestion/matching results should be consumed by route index order unless the stop policy explicitly permits earlier cancellation
  - final survey/index state must be deterministic across repeated runs with the same screenshots
- keep target-search safer than exhaustive sweep
  - initial implementation may keep P2 synchronous for target-search modes
  - bounded lookahead can be added only after stop/cancel semantics are reviewed
  - if a background P2 result finds a stop-policy match, movement should stop at the next safe checkpoint boundary and then drain/cancel remaining work deterministically
- add P2 timing to the canonical execution profile
  - enqueue wait time
  - rich observation build time
  - full-frame OCR time when available
  - selector detection time when available
  - coordinator survey ingestion time
  - matching/stop-policy time
  - queue depth and drain time

This P2 design is deliberately not a second sweep engine. It is a background execution mode for the same checkpoint analysis that already exists today, fed by P1 screenshots so the runtime does not recapture the same viewport just to sample it.

#### P2 observation/OCR optimization directives

The June 7 single-viewport benchmark showed that P2-style work is expensive enough to deserve its own architectural optimization, even after it is moved off the movement-critical path. The target is not a new parser or a second observation implementation. The target is to make the existing rich observation path consume one canonical screenshot/proof input and avoid recomputing the same facts.

Implementation directives:

- Treat the P1 screenshot and coordinate proof as the canonical P2 input.
  - P2 must not recapture the same viewport.
  - P2 must not re-OCR `PNC_WORLD_COORDINATE_BAR` unless the P1 proof is absent, stale, or explicitly being validated by policy.
  - If P1 provides exact world-map proof, P2 should be seeded with that known world-map context instead of rediscovering the screen from `UNKNOWN`.
- Make rich observation construction request/proof-aware.
  - A P2 world-map checkpoint analysis should not run the broad generic screen-classifier probe set as its first step when P1 already proved `PNC_WORLD_MAP`.
  - The observation stack should expose one canonical "build from captured world-map screenshot" path that narrows selector work to the world-map treatment request.
  - This must still delegate to `ObservationBuilder`, `PncObservationEnricher`, selector registry, and existing survey ingestion owners rather than adding a parallel fast path.
- Introduce one explicit observation analysis context instead of growing ad hoc optional parameters.
  - The context should carry the captured screenshot, request/treatment profile, optional known screen type, optional P1 parsed viewport, artifact policy, selector-detection plan, and a screenshot-scoped OCR cache.
  - `ObservationBuilder.build(...)` can remain the compatibility entry point, but the optimized path should flow through the context so every stage consumes the same canonical facts.
  - `PncObservationEnricher` should accept or derive OCR lines from that context instead of always calling `ocr_service.read_result(image)` as an unconditional first step.
- Make selector work request-scoped and region-aware.
  - A known-world-map treatment should not start from the broad classifier probe set.
  - Selector detection should receive a planned selector id set and, where registry geometry is available, a bounded search region.
  - The existing `PillowSelectorEngine` and `PillowTemplateMatcher` should not be duplicated; they should be narrowed by a canonical detection plan before being called.
- Use one screenshot-scoped OCR result cache for the P2 treatment.
  - Full-frame or map-region OCR lines should be computed once per P2 screenshot and reused for anchors, visible element extraction, spatial-surface object parsing, and matching.
  - Coordinate-bar and bottom-nav region OCR should not be repeated if the same stage already produced the needed text.
  - The cache must be scoped to one captured screenshot or one P2 work item so stale OCR cannot leak across viewports.
  - Shared `CachedOcrService` instances should not be relied on for P2 worker concurrency because the current implementation caches only the last image/region and is mutable.
- Separate OCR preprocessing and backend timings.
  - P2 profiling should distinguish image crop/filter preparation, OCR image encoding, OCR backend runtime, and OCR result parsing when practical.
  - This gives enough evidence to decide later whether transport/backend changes are worthwhile without guessing.
- Narrow the expensive OCR region to the data P2 actually needs.
  - Internal-map inventory population needs world-map scene labels and objects.
  - It should not OCR static chrome, top HUD, bottom navigation, or debug-only regions unless the treatment request requires those regions.
  - The canonical spatial-surface builder already owns world-map object scan bounds through `spatial_surfaces.py`; implementation should expose/reuse that owner instead of re-hardcoding viewport geometry elsewhere.
- Keep artifact/debug sidecars out of routine P2 performance measurements.
  - Checkpoint artifact persistence should still use the existing artifact policy.
  - Debug sidecars that trigger additional OCR should be opt-in for diagnostics and clearly reported in the profile.
  - Routine exhaustive sweeps should not silently pay for a second full-frame OCR pass.
- Instrument P2 as first-class work.
  - The canonical profile should separate queue wait, rich observation build, full-frame or map-region OCR, extra region OCR, selector detection, spatial-surface parsing, inventory ingest, matching, stop-policy evaluation, and queue drain.
  - P2 throughput and queue depth must be visible because async execution only helps if P2 can keep up with P1 movement often enough to avoid unbounded backlog.

The expected first wins are avoid-work wins:

- skipping the broad generic selector probe for known world-map screenshots
- eliminating duplicate coordinate-bar OCR
- eliminating repeated chrome/HOME OCR unless required
- reusing one OCR result through the whole rich treatment
- avoiding debug sidecar OCR in benchmark and production sweep modes

Only after those are measured should lower-level OCR engine changes be considered. A C++ wrapper is not the first-order fix here because the current cost is dominated by repeated OCR/selector work and screenshot I/O around an existing native OCR engine, not Python loops alone.

### 2.6 Define safe pipeline semantics by search mode

The pipeline must preserve behavioral correctness. Not every search can move ahead blindly while P2 is still processing.

Use one canonical pipeline policy derived from the search request and stop policy:

- exhaustive sweep mode
  - P1 blocks movement only until the post-swipe coordinate is proven
  - P2 analysis can run behind the movement loop with bounded queue depth
  - the executor drains outstanding P2 work before returning the final result
- target-search mode
  - P1 still blocks movement for coordinate proof
  - P2 may run with a small bounded lookahead only if stop policy can cancel safely
  - P2 must be able to signal an asynchronous stop request once it completes a requested-match result
  - the itinerary executor must observe that signal between itinerary steps and stop consuming further steps after the current safe movement/checkpoint boundary, or when the itinerary reaches its final corner/end
  - async lookahead must be disabled when the matcher requires live castle/profile enrichment, because those follow-up actions depend on being at the candidate viewport
  - map-side-only target searches may use bounded lookahead only after deterministic cancellation and result-ordering tests exist
- diagnostic/stability mode
  - P2 can be forced synchronous to keep failure artifacts and logs easier to inspect

The queue must be fail-fast and bounded:

- reject invalid P1 proof results before enqueue
- bound queue depth to avoid unbounded memory growth
- propagate the first P2 exception to the search result boundary
- propagate P2 stop-policy matches to P1 as an interrupt signal
- drain or cancel workers deterministically at search completion
- keep output ordering stable by checkpoint route index
- keep `WorldMapSurveyRecorder` and `WorldMapSurveyIndex` single-writer by applying P2 results on the coordinator thread

This gives us overlap without making search nondeterministic.

### 2.7 P1 speed plan, benchmark-gated

The July 8 granular benchmark changes the P1 optimization target. The current P1 path already avoids routine full-frame OCR, broad selector probes, debug screenshot persistence, and implicit full-runtime retry. The next P1 work must therefore optimize the measured costs that remain.

Every proposed P1 speed change must be benchmarked before and after with `tools/benchmark_world_map_p1_capture.py` or a narrower benchmark added beside it. A change is not accepted if it improves a synthetic timing while regressing live exact-coordinate proof stability.

#### 2.7.1 Non-targets

Do not spend implementation effort on these unless a new benchmark contradicts the July 8 data:

- removing `CapturedObservation` or bypassing `ObservationService` only to avoid wrapper overhead
- screenshot artifact persistence for `WORLD_MAP_MOVEMENT_PROOF`, because routine P1 already uses no screenshot artifacts and measured debug-only persistence was about `2.64ms`
- generic selector-probe removal for P1, because movement proof already requests an empty selector-detection plan
- moving P1 coordinate proof to another thread, because movement still needs the coordinate or accepted uncertainty state before the next safe move
- adding a second "fast sweep" parser or movement mode instead of improving the canonical P1 proof and sparse-proof policy

#### 2.7.2 Benchmark instrumentation gate

Before changing runtime behavior, extend the benchmark evidence so decisions are attributable:

1. keep `tools/benchmark_world_map_p1_capture.py` as the live baseline tool
2. add a coordinate-proof microbenchmark over saved live screenshots
3. split coordinate proof into crop, filtering, image encode, OCR backend, parse, and fallback stages
4. report primary coordinate-bar OCR success rate versus fallback success rate
5. report proof failure class, not just elapsed time
6. persist JSON benchmark documents under artifacts when a benchmark is used as acceptance evidence

Acceptance gate:

- live `ObservationService` residual overhead remains below `1%`, or the plan must be revised
- exact P1 proof mean, median, min, max are reported separately from screenshot capture
- the benchmark includes at least one normal interior screenshot and one previously problematic coordinate-bar screenshot

#### 2.7.3 Coordinate OCR cost reduction

The largest single P1 proof cost is coordinate-bar OCR. The July 8 benchmark measured coordinate OCR/proof at roughly `0.57s` to `0.65s` per sample.

Candidate changes, in order:

1. benchmark the existing canonical coordinate-bar crop/filter pipeline without changing behavior
2. benchmark a tighter coordinate-text crop derived from the current coordinate-bar selector bounds
3. benchmark direct grayscale/threshold preprocessing versus the current cyan/blue filtered image
4. benchmark OCR input encoding format and crop dimensions, because RapidOCR receives encoded image bytes
5. cache immutable selector materialization and coordinate-bar region resolution where it is proven nonzero
6. keep all parsing and fallback ownership in `world_map_coordinates.py`

Acceptance gate:

- exact coordinate proof success rate is unchanged on saved regression screenshots
- live coordinate-only builder mean improves by at least `20%` before the change is accepted as meaningful
- no new coordinate grammar, crop owner, or parser fork is introduced

#### 2.7.4 Screenshot capture cost reduction

Screenshot transport is the second measured P1 cost. The July 8 benchmark measured raw ADB screenshot bytes at about `359ms` and canonical no-persist screenshot capture at about `339ms` to `403ms`.

Candidate changes, in order:

1. benchmark current `HD-Adb.exe exec-out screencap -p` or equivalent path if not already used by the session implementation
2. compare PNG screenshot transport with any available raw-frame or lower-overhead BlueStacks capture path behind the existing session/capture interface
3. measure whether persistent ADB process reuse is possible without destabilizing the current session abstraction
4. keep `ScreenshotService` as the canonical capture owner and hide transport choices behind `BlueStacksSession`
5. preserve one captured screenshot payload for P2; do not introduce P1-only screenshots that P2 cannot reuse

Acceptance gate:

- no change may bypass `ScreenshotService`/session ownership from navigation code
- live screenshot capture mean improves by at least `15%` before the change is accepted as meaningful
- P2 work items still receive the exact screenshot identity that P1 proved

#### 2.7.5 Reduce exact P1 proof frequency through sparse anchors

Even if each exact proof were reduced to `500ms`, proving every stride-`6` sample would still be too slow for a full parsed map. Production sweeping must use sparse exact coordinate anchors plus deterministic projected sampled frames, as Phase 3 already requires.

Policy shape:

1. exact P1 proof at segment start
2. exact P1 proof at segment end
3. exact P1 proof after any movement classified as uncertain, stalled, or gap-risking
4. optional periodic exact proof every reviewed distance or elapsed-time budget
5. projected intermediate screenshots queued to P2 with coordinate windows, not fake exact coordinates
6. correction only if adjacent exact/projection windows can leave an unobserved viewport gap

Acceptance gate:

- every queued P2 frame has either exact P1 proof or a bounded projected coordinate window
- coverage audit proves no viewport gaps using the reviewed scan footprint
- projection uncertainty is explicit in persisted inventory and cannot masquerade as exact coordinates
- a live row benchmark reports exact P1 proof count, projected frame count, correction count, coverage-gap count, and total P1 time

#### 2.7.6 P1 speed budget

The initial budget for the next live row milestone is:

- exact P1 proof mean: `<= 600ms`
- screenshot capture mean: `<= 300ms`
- coordinate-only proof mean on an existing screenshot: `<= 300ms`
- exact P1 proofs per long row segment: start plus end plus reviewed periodic anchors, not every sampled frame
- P1 proof/capture share of a parsed row: `<= 35%` of total row runtime

These are intermediate engineering budgets, not the final definition of done. The final acceptance target remains a full parsed map, including P2 drain and persistence, under `30 minutes`.

### 2.8 Tune steady-state movement only after route entry and P1 proof are correct

Once entry/reset is fixed, tune the local checkpoint mover on the canonical sweep path.

The likely targets are:

- minimizing leg count for one `10`-unit local checkpoint move
- minimizing unnecessary correction legs
- preserving exact proof with the smallest required post-action observation cost
- avoiding overshoot/stall correction loops like `(368, 510)` to `(374, 510)` then back to `(372, 510)`

Suggested scope:

1. review `WorldMapMovementPolicy`
2. review traverse-vs-correction thresholds
3. review axis-delta caps by movement mode
4. measure whether local `10`-unit horizontal/vertical traversal can settle in fewer legs without increasing stall risk
5. add focused benchmark cases for `10`-unit horizontal, `10`-unit vertical, and diagonal checkpoint moves

This work should stay inside the existing movement policy and mover owners.

### 2.9 Do not treat selector/artifact policy as a separate performance system

Performance tuning must preserve the current architecture:

- one analyzed checkpoint observation per intentional analyzed viewport
- no duplicate movement-proof vs checkpoint-analysis captures
- one shared artifact policy across movement families

If any extra cost is found in checkpoint analysis, the fix should be to narrow the existing canonical observation path, not to add a second "fast sweep" observation implementation.

### 2.10 Performance-phase implementation steps

1. Confirm and encode the reviewed full-map coverage contract: `(0, 0)` through `(511, 1023)`.
2. Extend `WorldMapResolvedSearchPlan` with actual execution-start context and resolved first-leg movement intent.
3. Compose one canonical itinerary whose first leg is current/original viewport to the first pattern checkpoint when not already positioned.
4. Route `NON_LOCAL_RESET` itinerary steps through reviewed navigation primitives rather than the local direct mover.
5. Prefer coordinate jump for the non-local first itinerary leg when available and verified.
6. Replace plan-wide movement-tool dispatch with per-step movement-strategy resolution driven by `WorldMapTraversalExecutionStep.action_family`.
7. Keep itinerary execution on one canonical agnostic step loop.
8. Add a search-summary timing document that splits:
   - non-local entry-leg movement
   - steady-state checkpoint movement
   - checkpoint proof/ingestion
9. Add itinerary composition that prepends the current-position-to-first-pattern-checkpoint leg with non-local intent when needed.
10. Keep the executor generic: it consumes itinerary steps and dispatches by movement intent.
11. Preserve the granular P1 benchmark tool and persist JSON evidence for every proposed P1 speed change.
12. Add saved-screenshot coordinate-proof microbenchmarks that split crop, preprocessing, image encode, OCR backend, parse, and fallback timing.
13. Optimize coordinate-bar OCR inside the canonical `world_map_coordinates.py` owner, accepting only changes with unchanged proof stability and at least `20%` live coordinate-proof improvement.
14. Benchmark screenshot transport alternatives behind the existing `BlueStacksSession`/`ScreenshotService` boundary, accepting only changes with at least `15%` live capture improvement and unchanged P1-to-P2 screenshot identity.
15. Add the canonical P1 movement-proof capture result only if it carries measured value beyond the current near-zero service residual; it must remain backed by the existing coordinate parser and proof vocabulary.
16. Remove final-arrival rich checkpoint analysis from `WorldMapCoordinateMover`; checkpoint treatment should be a coordinator-owned P2 work item built from the P1 screenshot/proof.
17. Add P2 viewport-analysis work items that reuse the P1 screenshot instead of recapturing.
18. Add one canonical observation-analysis context for building P2 observations from an existing captured world-map screenshot and P1 proof.
19. Make that entry point request/proof-aware so known world-map screenshots avoid the broad generic screen-classifier probe.
20. Add screenshot-scoped OCR reuse for P2 so coordinate text, OCR lines, object labels, selectors, inventory ingest, and matching do not recompute the same OCR output.
21. Reuse the world-map object scan bounds owned by the canonical spatial-surface/observation layer so P2 can OCR the meaningful map scene without re-hardcoding viewport geometry.
22. Add a canonical selector-detection plan so known-world-map treatment avoids broad classifier probes and unnecessary template scans.
23. Add an observation treatment/profile for P2 that separates inventory analysis from popup/loading/debug guard work.
24. Ensure P1 movement proof uses a bounded narrow retry policy and does not silently promote to `full_runtime_default()` on every proof miss.
25. Add a bounded P2 worker queue in the canonical search service for exhaustive sweep mode.
26. Apply P2 results to `WorldMapSurveyRecorder` on the coordinator thread in route-index order; workers must not mutate the survey index directly.
27. Preserve synchronous P2 mode for diagnostics, live enrichment, and correctness-sensitive target-search mode until bounded lookahead and async stop semantics are reviewed.
28. Re-measure the same June 7 `testing` serpentine/full-map scenario after itinerary-entry and P1 changes.
29. Only then tune local movement policy for steady-state step cost.

### 2.11 Performance-phase validation

Use the same live scenario shape validated on June 7, 2026:

- account: `testing`
- movement step budget: `500`
- pattern: `SERPENTINE_ROW_SWEEP`
- boundary: full map
- full-map coverage: `(0, 0)` through `(511, 1023)`
- itinerary start: current/castle viewport leg to the first pattern checkpoint, currently `(0, 0)` for the validated full-map row/serpentine route
- non-local entry-leg primitive: coordinate jump when available and verified

Track these metrics explicitly:

- resolved checkpoint count
- non-local entry-leg elapsed time
- whether the first itinerary leg used local or non-local strategy
- whether the first itinerary leg used coordinate jump, overview seed, or local swipe fallback
- sampled steady-state checkpoint time
  - for example checkpoints `3` through `10`
- failure rate near edge/corner states after entry/reset
- P1 movement-proof elapsed time per cycle
- P2 viewport-analysis elapsed time per checkpoint
- P2 queue depth and drain time
- P2 queue wait time
- P2 rich observation build time
- P2 full-frame or map-region OCR time
- P2 extra region OCR time
- P2 OCR crop/filter preprocessing time
- P2 OCR image encode time
- P2 OCR backend runtime when available
- P2 selector detection time
- P2 planned selector count by detection kind
- P2 spatial-surface parsing and inventory-ingest time
- P2 coordinator-ingest time
- primitive used per itinerary step
- number of movement cycles per `10`-unit local checkpoint move

### 2.12 Performance acceptance criteria

This phase is done only when all of the following are true **and** the corresponding automated/live evidence in the top-level `Required Acceptance Evidence` table exists. Model construction, direct analyzer calls, synchronous P2, and isolated queue tests cannot satisfy criteria 9, 10, 13, 15, or 17.

1. The first itinerary leg is no longer modeled as hundreds of ordinary local swipe legs from arbitrary start.
2. The canonical search engine records non-local entry-leg time separately from steady-state checkpoint time.
3. Full-map mapping covers the reviewed full domain from `(0, 0)` through `(511, 1023)`.
4. The first itinerary leg from current/castle viewport to itinerary start uses coordinate jump when available and verified.
5. The same broad serpentine scenario can be measured without proof collapse at the edge/corner states crossed during entry.
6. Any steady-state tuning remains inside the canonical movement/search owners.
7. There is still exactly one itinerary execution loop, and it is agnostic over entry-vs-steady-state.
8. Movement proof has one canonical P1 implementation and does not run full rich observation analysis on the ordinary critical path.
9. Checkpoint sampling/internal-map ingestion has one canonical P2 implementation that can reuse P1 screenshots.
10. Exhaustive sweep mode can overlap P2 analysis with movement using bounded, deterministic queue semantics.
11. Target-search mode either remains synchronous or uses reviewed bounded lookahead with safe cancellation semantics.
12. Single-viewport movement benchmarks report P1, P2, swipe, screenshot capture, OCR, selector detection, and movement-cycle counts separately.
13. P2 does not recapture or re-OCR coordinate proof already supplied by P1 except through explicit validation/fallback policy.
14. P2 observation building is request/proof-aware and avoids broad generic selector probing for already-proven world-map screenshots.
15. P2 OCR results are screenshot-scoped and reused by selector detection, spatial-surface parsing, inventory ingestion, and matching.
16. Movement primitive dispatch is per itinerary step; enabling coordinate jump for entry does not force every local checkpoint step to use coordinate jump.
17. P2 workers do not mutate `WorldMapSurveyRecorder` or `WorldMapSurveyIndex`; the coordinator applies results deterministically.
18. Castle/profile-enrichment target searches remain synchronous or movement-blocking until live follow-up semantics are explicitly reviewed.
19. Known-world-map P2 treatment uses a planned selector scope and does not run the broad classifier probe set.
20. P1 movement proof does not implicitly promote narrow proof misses to `full_runtime_default()` without an explicit measured fallback policy.
21. P2 treatment profiles distinguish inventory-only work from popup/loading/debug guard work.
22. Profiles report selector counts and OCR preprocessing/backend timings well enough to decide whether lower-level OCR or screenshot transport work is justified.
23. A production-wiring integration test invokes the canonical exhaustive-sweep entry point, blocks one P2 worker deterministically, and proves P1 advances to a later safe screenshot before that worker completes.
24. A live exhaustive profile reports non-zero P2 submissions, non-zero queue activity, positive movement/P2 overlap, bounded peak depth, deterministic drain, and zero routine P2 recaptures.
25. Phase status is recorded using the completion vocabulary at the top of this document; it cannot be reported as `done` while production-wiring or live evidence is missing.

## Phase 3. Under-30-Minute Parsed Full-Map Sweep

### 3.1 Purpose

The next performance target is not just a faster geometric sweep. It is a canonical full-map iteration that:

- keeps the existing proof/search architecture
- keeps one canonical sweep implementation
- completes a reviewed full-map iteration in under `30 minutes`
- produces a parsed, coordinate-attributed inventory of visible world-map elements across the full map

This target intentionally keeps correctness and parsing in scope. A fast movement-only pass that cannot say where map elements are is not accepted.

### 3.2 June 14, 2026 Live Benchmark

Live target:

- BlueStacks/account: `serious_stuff`
- language: English
- route: full-map `SERPENTINE_ROW_SWEEP`
- stride: `10`
- stop policy: `max_checkpoints=25`
- canonical engine: `WorldMapSearchService.execute_search(...)`
- start coordinate: `(20, 0)`
- visited checkpoints: `(0, 0)` through `(240, 0)`
- result: success

Measured totals:

- preflight: `7.630s`
- search total: `361.388s`
- non-local entry: `30.524s`
- steady-state movement total for `24` checkpoints: `330.841s`
- steady-state average: `13.785s/checkpoint`
- route plan time: `16.8ms`
- checkpoint ingest, match, and stop-policy time: effectively negligible

Comparison to the previous entry baseline:

- previous entry to `(0, 0)` by local swipes: about `530s` to `585s`
- current entry by coordinate jump: about `30.5s`
- entry speedup: roughly `17x` to `19x`
- steady-state remains around `11s` to `14s` per checkpoint

The coordinate-jump entry fix worked. The remaining blocker is steady-state movement/proof cost.

### 3.2.1 June 15, 2026 Default-Stride Live Duration Sample

After changing the canonical no-override viewport stride from `10` to `6`, a live English-account duration sample was run on `serious_stuff` using the canonical search engine with no stride override.

Live target:

- route: bounded same-row `ROW_MAJOR_SWEEP`
- canonical default stride: `6`
- start coordinate: `(384, 0)`
- visited checkpoints: `(384, 0)` through `(510, 0)`
- visited count: `22`
- movement step count: `27`
- result: success

Measured totals:

- sample elapsed: `64.706s`
- average checkpoint movement, including no-op checkpoints: `2.939s/checkpoint`
- average non-no-op checkpoint movement: `3.233s/checkpoint`
- median non-no-op checkpoint movement: `2.449s/checkpoint`
- average swipe/proof action elapsed: `2.395s/swipe`
- P2 total: `33.47ms`

The default stride change improves coverage safety, but it increases the exact-checkpoint route from `5,460` checkpoints at explicit stride `10` to `14,878` checkpoints at default stride `6`.

Exact-checkpoint full-map duration estimate from this sample:

- optimistic median steady-state: `14,878 * 2.449s = 10.1h`
- measured average all checkpoints: `14,878 * 2.939s = 12.1h`
- measured average non-no-op checkpoints: `14,878 * 3.233s = 13.4h`

This confirms again that the under-30 target cannot use exact proof at every default-stride checkpoint. The `6` stride is a conservative coverage default for route/sampling density, not an acceptance path for exact per-checkpoint live execution.

### 3.3 Hard Budget Math

The reviewed explicit-stride benchmark route had `5,460` checkpoints at stride `10`. The conservative default route now has `14,878` checkpoints at stride `6`.

To complete under `30 minutes`:

- total budget: `1,800s`
- maximum average per default-stride checkpoint: `1,800 / 14,878 = 0.121s/checkpoint`

Current exact-checkpoint steady-state average:

- `3.233s/checkpoint` on the June 15 default-stride sample

Required improvement if keeping all `14,878` physical default-stride checkpoint visits:

- `3.233 / 0.121 = 26.7x`

This is not reachable by small OCR, sleep, or selector optimizations alone. A screenshot plus OCR/proof loop per checkpoint cannot plausibly average `0.330s` on the current ADB/RapidOCR stack.

Under `30 minutes` therefore requires changing full-map sweep semantics from:

- physically stop and fully prove/analyze every `10`-coordinate checkpoint

to:

- move continuously through the map, prove position sparsely, and parse coordinate-attributed map elements from sampled frames with deterministic coverage windows

This must still be one canonical engine. The implementation should evolve the current search/sweep architecture with explicit policies, not add a parallel "fast sweep" executor.

### 3.4 Target Architecture

The project should have one canonical sweep engine with policy-driven execution.

Canonical engine responsibilities:

- route and segment planning
- non-local entry
- movement execution
- proof anchoring
- frame sampling
- P2 parsing
- coordinate projection
- survey and inventory merge
- benchmark profile persistence

Policies decide strictness and speed:

- `debug_exact_checkpoint_policy`: exact proof at every checkpoint, synchronous analysis, and diagnostic/calibration intent
- `production_full_map_policy`: sparse exact proof anchors, continuous row/segment traversal, sampled-frame parsing, coordinate-attributed parsed inventory, duplicate accounting, and uncertainty accounting

Both policies must use the same route ownership, movement abstractions, parser ownership, survey writer, and live tooling wrappers. No CLI or tool should expose "old sweep vs fast sweep" as two implementations.

### 3.5 Production Unit Of Work

Current exact-checkpoint unit:

- one checkpoint coordinate
- move to exact coordinate
- prove coordinate
- analyze/check stop policy

Production full-map unit:

- one row segment or lane segment
- start/end exact proof
- continuous swipe/drag sequence across the segment
- frame sampling during movement or at sparse intervals
- deterministic coverage projection from proven anchors
- coordinate-attributed element detections from every sampled frame

The canonical full-map route can still be generated from the same domain/pattern owner, but execution should group checkpoints into row/lane segments when the production policy is selected.

### 3.6 Sparse Proof Contract

Full exact proof remains mandatory at:

- route start
- non-local entry landing
- row or segment start
- row or segment end
- after any unexpected movement classification
- configurable periodic anchors

Between anchors:

- use deterministic movement model plus sampled screenshots
- keep a bounded drift budget
- force re-proof when drift budget is exceeded

Fail fast if:

- expected row/lane progress is not monotonic
- re-proof lands outside the expected segment envelope
- map ownership cannot be proven at an anchor
- sampling backlog exceeds bounded limits

### 3.7 Element Inventory Contract

The production policy must parse the map. It cannot simply mark a row as geometrically covered.

Each sampled frame must produce immutable analysis output:

- frame id
- segment id
- sampled screenshot artifact or in-memory payload reference
- estimated viewport center
- coordinate transform from screen pixels to kingdom coordinates
- detected map elements
- parser confidence and uncertainty flags
- source proof anchors

Each detected map element must include:

- canonical element kind, such as castle, monster, resource node, hell fortress, alliance building, altar, Dragonia, or unknown
- screen-space bounds
- projected kingdom coordinate or coordinate window
- text/OCR evidence when available
- visual evidence/source selector when available
- frame id and segment id
- confidence score
- de-duplication key or cluster id
- uncertainty reason when exact coordinate attribution is not possible

The inventory must not silently drop uncertain content. It must record unknown or uncertain detections separately from confident detections so downstream consumers can distinguish parsed elements, seen-but-unclassified elements, ambiguous duplicates, unparsed coverage windows, and gaps with no usable sample.

### 3.8 Coordinate Projection Model

Continuous movement means many frames will not have exact coordinate-bar proof. The system therefore needs one canonical projection model.

Inputs:

- exact proof anchors at segment start/end and periodic checkpoints
- calibrated screen-to-world viewport geometry
- frame capture time/order within the segment
- measured movement deltas from anchor proofs
- known map bounds and row direction

Outputs:

- estimated viewport coordinate for each sampled frame
- coordinate transform for screen-space detections
- uncertainty radius/window for each projected element

Fail fast if projection uncertainty exceeds policy. Do not store precise-looking coordinates when the proof only supports a broad window.

The projection model must live in the world-map navigation/geometry layer, not in a live benchmark script.

### 3.9 Sampling, P2 Analysis, And Merge

For exhaustive map discovery, the system should not require one rich observation per `10`-coordinate checkpoint.

Instead:

- capture frames at a target cadence during row/segment movement
- associate each frame with an estimated coordinate window
- enqueue P2 analysis work for those frames
- apply results in deterministic route/segment order
- keep `WorldMapSurveyRecorder` single-writer
- merge detections into one canonical coordinate-attributed element inventory

P2 workers must produce immutable analysis results only. The coordinator remains the only survey-index mutator.

Sampling cadence must be derived from coverage requirements, not just speed. Required sampling policy fields:

- maximum screen-space gap between sampled frames
- minimum horizontal/vertical overlap
- maximum projection uncertainty
- maximum allowed unparsed coverage window
- frame drop policy
- duplicate-cluster radius
- unknown-element retention policy

Canonical merge ownership belongs to `WorldMapSurveyRecorder` or a dedicated survey-ingest collaborator owned by it.

Merge inputs:

- element kind
- projected coordinate/window
- text/name evidence
- level/resource labels
- frame order
- confidence

Merge outputs:

- stable map element record
- supporting observations
- confidence summary
- uncertainty/gap annotations

### 3.10 Performance Budget Targets

Initial under-30 budget:

- non-local entry: `<= 35s`
- row transition/proof overhead: `<= 4 minutes` total
- row/lane traversal and frame capture: `<= 14 minutes` total
- P2 element parsing and merge: `<= 10 minutes` total
- final drain/profile/persistence: `<= 1 minute`
- safety margin: `<= 1 minute`

The current domain has about `1024 / 6 = 171` row bands under the conservative default stride. A row-based proof model must keep average row processing under about:

- `1,800s / 171 = 10.5s/row`

That is ambitious, but plausible with continuous movement. It is not plausible with per-checkpoint exact proof.

The budgets intentionally reserve time for P2. If parsing and merging elements cannot complete under budget, the sweep is not successful even if movement is fast.

### 3.11 Under-30 Implementation Phases

Phase 3A. Add benchmark math and route segmentation:

- add canonical models for sweep policy, sweep segment, segment kind, coverage window, sampled frame, projected frame, element detection, and element coordinate window
- extend route planning to group existing checkpoint routes into row/lane segments without changing route ownership
- test that the full-map route still has `5,460` checkpoints
- test that segment grouping covers the same route envelope
- test that row `0` groups `(0, 0)` through `(511, 0)`
- test that serpentine row turns are represented explicitly
- test that coverage windows cannot be marked complete without a sampling policy

Phase 3B. Add actual-coordinate proof and coverage policy:

- add one proof policy owner for actual-coordinate P1 samples, optional exact anchors, periodic proof interval, drift tolerance, row-end proof capture, and fail-fast conditions
- add one sweep-owned predicate for adjacent actual-sample coverage gaps based on the modeled visible scan footprint
- test that debug exact policy requires every checkpoint proof
- test that production policy requires enough actual-coordinate samples to prove contiguous coverage
- test that production policy rejects missing P1 sample proof, invalid scan footprints, non-monotonic progress, and projected frames whose uncertainty exceeds policy

Phase 3C. Add trajectory-based row movement primitive:

- stay inside the existing movement/navigation owners
- start from a proven coordinate
- issue calibrated directional swipes along the row/segment trajectory instead of snapping every sample to the planned checkpoint coordinate
- after each movement, capture narrow P1 coordinate proof and queue the exact screenshot plus actual coordinate to P2
- compare each actual sample to the previous actual sample; correct only if the modeled visible scan footprint says the sweep may have left an unobserved gap
- return the actual row segment endpoint and coverage-gap/correction evidence
- report movement cycles, P1 proof time, correction count, and elapsed time
- test fake success, accepted drift, coverage-gap correction, overshoot, stall, missing proof, and monotonic sampled-frame progress

Phase 3D. Add projection and sampling context:

- model actual sample coordinates, optional segment anchors, sampled frame order/timestamps, movement direction, viewport geometry, and uncertainty policy
- test sampled-frame center projection between actual anchors when projection is needed for uncertainty windows
- reject non-monotonic sample order
- widen coordinate windows when anchor distance or timing uncertainty increases
- fail when uncertainty exceeds policy

Phase 3E. Add P2 element parsing context:

- add canonical frame analysis work items with screenshot, estimated coordinate window, proof anchors, segment index, sample index, projection transform, and parser treatment profile
- workers build immutable results
- coordinator applies results in order
- test bounded queue semantics, first-failure propagation, coordinate projection, unknown retention, and deterministic duplicate merge

Phase 3F. Add parser completeness metrics:

- sampled frame count
- parsed frame count
- dropped frame count
- detected element count by kind
- unknown/uncertain element count
- duplicate merge count
- coverage window count
- coverage gap count
- maximum coordinate uncertainty
- P2 queue peak depth
- P2 parse elapsed
- merge elapsed

Phase 3G. Add live row benchmark tooling as thin wrappers around canonical services:

- segment count
- proof anchor count
- frame sample count
- row movement elapsed
- proof elapsed
- P2 elapsed/drain
- coverage windows
- uncertainty/gap count
- parsed element count by kind
- duplicate merge count
- max coordinate uncertainty

Phase 3H. Tune and validate:

1. current exact checkpoint benchmark, `25` checkpoints
2. production policy row `0`, one row with parser enabled
3. production policy three rows with parser enabled
4. production policy 10-minute parse soak
5. full parsed production-policy run

### 3.12 Milestones

Milestone 1: parse one full row under budget.

- start at `(0, 0)`
- traverse to `(511, 0)` or the final addressable x checkpoint on row `0`
- complete in under `90s`
- preserve actual-coordinate P1 sample proof through the row endpoint
- record sampled frames, actual sample coordinates, coverage windows, and any coverage-gap corrections
- produce coordinate-attributed element detections for every sampled frame
- report unknown/uncertain detections and coverage gaps

Milestone 2: parse three rows.

- traverse rows `0`, `10`, and `20`
- include row-transition movement/proof
- complete in under `5 minutes`
- record coverage windows
- produce merged element inventory across rows
- prove duplicate suppression across overlapping frames
- prove no silent drops of unknown/uncertain elements
- verify no proof collapse at row edge/turn states

Milestone 3: dry full-map route and inventory simulation.

- simulate segment grouping for the full route
- compute expected row/lane segments
- compute proof anchor count
- compute estimated frame sample count
- validate coverage covers `(0, 0)` through `(511, 1023)`
- validate no duplicate or missing coverage windows
- simulate sampled viewport footprints
- validate every map coordinate falls inside at least one sampled frame footprint
- validate required overlap for element detection at viewport edges
- validate projected element coordinates remain inside accepted uncertainty windows

Milestone 4: live 10-minute parse soak.

- max runtime: `10 minutes`
- expected progress: at least one third of the map
- no proof collapse
- bounded P2 queue with non-zero submissions, non-zero peak depth, and positive movement/P2 overlap
- zero routine P2 viewport recaptures and zero duplicate coordinate OCR from P1-proven screenshots
- deterministic ordered drain with no worker-side survey mutation
- deterministic persisted profile
- parsed element count
- unknown/uncertain element count
- coverage gap count
- duplicate merge count

Milestone 5: full parsed map under `30 minutes`.

- run the production full-map policy
- produce profile document
- prove route coverage
- produce full coordinate-attributed element inventory
- report skipped/uncertain windows, if any
- fail if coverage gaps exceed policy
- fail if parser backlog cannot drain under budget
- fail if element coordinate uncertainty exceeds policy
- fail if the production queue is bypassed, has no P2 work, or demonstrates no movement/P2 overlap
- fail if routine P2 treatment recaptures P1-proven viewports or repeats coordinate OCR without explicit fallback policy

### 3.13 Under-30 Acceptance Criteria

The under-30-minute target is accepted only when all of the following are true:

1. the canonical route coverage still spans `(0, 0)` through `(511, 1023)`
2. a full sweep completes under `30 minutes` on a live English account
3. exact proof is still used at non-local entry and segment anchors
4. the system reports coverage windows, uncertain windows, and gaps
5. survey index mutation remains single-writer
6. production policy becomes the default full-map policy only after it satisfies parsed-inventory acceptance criteria
7. debug exact checkpoint policy remains available only as a strict diagnostic policy inside the same engine
8. benchmarks are persisted as structured profile documents
9. the run produces a coordinate-attributed element inventory
10. unknown and uncertain elements are retained, not silently discarded
11. every stored element coordinate includes source frame/proof evidence
12. duplicate merging is deterministic and auditable
13. coverage windows cannot pass acceptance if parser sampling gaps exceed policy
14. P2 parse and merge complete within the under-30-minute budget
15. the canonical production exhaustive path, not a benchmark-only wrapper, submits all sampled-frame treatment through the bounded P2 queue
16. the retained live profile proves non-zero P2 submissions, bounded peak depth, positive movement/P2 overlap, deterministic drain, and propagated worker failures
17. routine P2 work reuses P1 screenshot identity/proof with zero viewport recapture and zero duplicate coordinate OCR outside explicit counted fallback policy
18. all top-level `Required Acceptance Evidence` gates are satisfied; dry simulation, estimates, and exact-checkpoint success cannot substitute for live parsed-sweep evidence

### 3.14 Replacement Criteria

The production full-map policy should replace the exact checkpoint policy for normal full-map iteration once all acceptance criteria pass.

After replacement:

- full-map sweep requests use the production policy by default
- debug exact checkpoint policy remains available only for diagnostics, calibration, and regression repros
- target searches that require live follow-up actions may still request stricter proof anchors through policy knobs, not through a second engine
- no CLI/tool should expose "old sweep vs fast sweep" as separate implementations
- docs should describe one sweep engine and explain policy strictness levels

The exact checkpoint policy should be treated like a microscope: useful when we need maximum proof density, wrong as the normal way to scan the whole kingdom.

### 3.15 Immediate Next Slice

The immediate next slice is benchmark-gated P1 speed reduction on the canonical production path. The bounded P2 queue, screenshot/proof work item shape, movement/P2 overlap, and trajectory-based segment traversal are already modeled and live-smoked, but P1 exact proof remains far too expensive for a full parsed map.

1. Preserve `tools/benchmark_world_map_p1_capture.py` as the standard live P1 baseline tool.
2. Add saved-screenshot coordinate-proof microbenchmarks that split crop, preprocessing, image encode, OCR backend, parse, and fallback timing.
3. Run the baseline on at least one normal live viewport and one known hard coordinate-bar fixture before any P1 speed change.
4. Optimize coordinate-bar OCR inside `world_map_coordinates.py`, keeping one parser owner and accepting only benchmark-proven wins.
5. Benchmark screenshot transport alternatives behind `BlueStacksSession`/`ScreenshotService`, keeping P1/P2 screenshot identity intact.
6. Add exact-proof frequency policy for production rows: exact start/end anchors, reviewed periodic anchors, uncertainty-triggered proof, and projected intermediate frames with coordinate windows.
7. Extend production profiles with exact P1 proof count, projected frame count, correction count, coverage-gap count, screenshot capture time, coordinate-proof time, and total P1 time.
8. Run a live one-row parsed benchmark and require lower total P1 time plus explicit coverage/inventory evidence before expanding to three rows.
9. Do not implement a P1 wrapper-removal refactor unless the benchmark first shows service residual overhead above `1%`.
10. Stop on the first live proof regression, coverage gap, fake-exact coordinate attribution, or benchmark regression.

This slice is complete only when it is `production-wired` and `live-validated`: measured P1 cost is lower, exact/projection evidence is explicit, P2 still reuses P1 screenshots, and the row output includes coordinate-attributed inventory plus coverage accounting.

## Remaining Gated Implementation Order

Previously completed or modeled work remains subject to the top-level evidence gates; the remaining implementation must proceed in this order:

1. Add P1 coordinate-proof microbenchmarks and require before/after evidence for all P1 speed changes.
2. Reduce coordinate OCR/proof cost without moving parsing ownership out of `world_map_coordinates.py`.
3. Reduce screenshot capture cost only behind the existing session/capture abstractions.
4. Complete sparse exact anchors, projection uncertainty, coverage windows, unknown retention, duplicate merge, and parser completeness accounting.
5. Add the canonical P2-from-P1-screenshot analysis context with screenshot-scoped OCR reuse and no viewport recapture.
6. Extend queue, overlap, recapture, duplicate-OCR, exact-proof, projected-frame, analysis, drain, and coordinator-merge metrics in the canonical profile.
7. Validate one parsed row, then three parsed rows, then a 10-minute parsed soak. Stop and fix the first bug or violated acceptance metric.
8. Run a bounded live exhaustive benchmark on an English account; do not proceed unless it proves non-zero queue activity, positive movement/P2 overlap, zero routine recapture, reduced P1 time, and explicit coverage evidence.
9. Run the full English-account parsed map and require complete drain, deterministic inventory/coverage output, and total elapsed time under `30 minutes`.

No step may be marked complete using a dry estimator, an isolated model test, or a tool-only execution path when its acceptance evidence requires production wiring or live behavior.

## Why This Is The Leanest Correct Solution

This plan is intentionally narrow in the right places:

- it does not create a second parser
- it does not create a second sweep engine
- it does not weaken the meaning of exact world-map proof
- it does not micro-optimize a path whose movement family is still wrong

Instead it makes two clean architectural corrections:

1. one canonical proof seam with explicit exact-vs-root behavior
2. one canonical long-sweep entry/reset seam separate from ordinary local traversal
3. one canonical P1/P2 split that keeps movement proof cheap while preserving rich checkpoint sampling

Those corrections directly address the real June 6 and June 7 failures and delays while preserving the current cleaned-up ownership model.

## Required Validation Workflow

For the stability gate:

- run focused capture/vision and world-map tests first
- then run full offline validation:
  - `py -3.13 -m unittest discover -s tests`

For the performance phase:

- run focused world-map search, traversal, calibration, and observation tests first
- then run full offline validation again
- then use the live `testing` serpentine/full-map scenario as the reviewed manual validation path

## DRY Checklist

Before this plan is considered complete, confirm:

1. exact/root world-map proof has exactly one canonical owner
2. coordinate-bar OCR parsing still has exactly one canonical owner
3. itinerary entry composition is implemented once in the canonical planning path
4. itinerary execution still runs through one canonical agnostic loop
5. P1 movement proof has exactly one canonical implementation
6. P2 viewport analysis/internal-map ingestion has exactly one canonical implementation
7. no live tooling owns a private proof, pipeline, or sweep implementation
8. movement primitive resolution has one canonical per-step owner
9. survey-index mutation has one canonical writer
10. screenshot-scoped OCR reuse has one canonical context owner
11. sweep policy selection has one canonical owner
12. row/segment coverage has one canonical geometry/projection owner
13. parsed element de-duplication and merge has one canonical survey-ingest owner
14. live benchmark tools are thin wrappers and do not own private sweep, parser, or proof logic
