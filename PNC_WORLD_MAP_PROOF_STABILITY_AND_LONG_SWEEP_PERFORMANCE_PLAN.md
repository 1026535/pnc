# PNC World-Map Proof Stability And Long-Sweep Performance Plan

## Purpose

Define one clean implementation plan for the next two world-map priorities:

1. a short stability gate for edge/corner world-map proof
2. performance work on the canonical long-sweep search path

This document intentionally treats those as one ordered program instead of two unrelated fixes. Broad sweep performance is not worth tuning until the world-map proof seam is stable at the exact edge/corner states the sweep must traverse.

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

## Vision

We want one world-map runtime that behaves like this:

1. Any operation that depends on exact world coordinates uses one canonical exact world-map proof seam.
2. That proof seam remains stable at normal interior states and at edge/corner states.
3. Long sweeps represent broad start positioning as an explicit non-local itinerary leg, not as hundreds of ordinary local swipe legs and not as an executor special case.
4. Once broad entry/reset is fixed, steady-state sweep traversal is measured and optimized on the same canonical search engine rather than through sidecar tooling or special-case search scripts.

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
- Full-map row-major and serpentine route construction currently produce `5460` addressable checkpoints using the default `10`-unit viewport stride.
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

- `pnc_automation/app/pnc/vision/world_map_proof.py`

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

- `WorldMapProofStrength.EXACT_SURFACE`
  - requires `observation.spatial_surface.surface_type == WORLD_MAP`
- `WorldMapProofStrength.ROOT_VISIBLE`
  - accepts `PNC_WORLD_MAP` or `PNC_WORLD_MAP_ROOT` style evidence without inventing a coordinate-bearing surface

Important constraint:

- `ROOT_VISIBLE` must not synthesize a fake `SpatialSurfaceObservation`
- exact coordinate-bearing operations must still require `EXACT_SURFACE`

This keeps the domain model honest while still giving the runtime a cleaner proof vocabulary.

Important ownership split:

- `world_map_proof.py` owns the proof vocabulary and pure exact/root validation.
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
   - `ROOT_VISIBLE` proof should succeed
   - `EXACT_SURFACE` proof should fail clearly
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

The single-viewport benchmark shows that ordinary movement is slow even after screenshot persistence is removed from movement proof. The main reason is that the post-swipe path still builds a rich observation when movement only needs a narrow proof.

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
- `world_map_proof.py` owns proof strength and P1 exact/root proof semantics
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

- add `pnc_automation/app/pnc/vision/world_map_proof.py`
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

This is intentionally a Task-1/P1-only implementation shape. It creates the clean seam that Task 2/P2 can later consume, but it does not introduce worker threads or queue semantics until the synchronous movement-and-coordinate-identification path is demonstrably cheap.

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

### 2.7 Eliminate superfluous movement-proof work before adding broader concurrency

The benchmark suggests the biggest immediate P1 wins are avoid-work wins, not thread scheduling wins:

1. Avoid full-frame OCR for ordinary movement proof.
   - A post-swipe movement proof only needs the coordinate bar and map-owned evidence.
   - Full-frame OCR should be reserved for P2 or bounded fallback.
2. Avoid duplicate coordinate-bar OCR.
   - The same screenshot currently pays for coordinate-region OCR through more than one path.
   - P1 should parse the coordinate once and pass the result forward.
3. Avoid broad probe-selector scans for movement proof.
   - The benchmark showed repeated scans across about `127` probe selectors.
   - P1 should use a narrow world-map proof selector set or no selector scan when coordinate-bar proof is enough.
4. Avoid debug sidecar work on movement proof.
   - The canonical `WORLD_MAP_MOVEMENT_PROOF` artifact policy already disables movement screenshots.
   - P1 should preserve that behavior and ensure debug-only OCR sidecars stay out of the movement critical path.
5. Keep configured movement sleeps small and explicit.
   - The measured configured sleeps are only about `100ms` per cycle, so they are not the main bottleneck.
   - Do not tune sleeps first unless a live settle failure proves the game needs less or more delay.

Concurrency should come after these reductions, because a background P2 queue does not help if P1 still performs the full rich observation synchronously.

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
11. Add the canonical P1 movement-proof capture result and keep it backed by the existing coordinate parser and proof vocabulary.
12. Route world-map movement follow-up through P1 instead of full rich observation building.
13. Remove final-arrival rich checkpoint analysis from `WorldMapCoordinateMover`; checkpoint treatment should be a coordinator-owned P2 work item built from the P1 screenshot/proof.
14. Add P2 viewport-analysis work items that reuse the P1 screenshot instead of recapturing.
15. Add one canonical observation-analysis context for building P2 observations from an existing captured world-map screenshot and P1 proof.
16. Make that entry point request/proof-aware so known world-map screenshots avoid the broad generic screen-classifier probe.
17. Add screenshot-scoped OCR reuse for P2 so coordinate text, OCR lines, object labels, selectors, inventory ingest, and matching do not recompute the same OCR output.
18. Reuse the world-map object scan bounds owned by the canonical spatial-surface/observation layer so P2 can OCR the meaningful map scene without re-hardcoding viewport geometry.
19. Add a canonical selector-detection plan so known-world-map treatment avoids broad classifier probes and unnecessary template scans.
20. Add an observation treatment/profile for P2 that separates inventory analysis from popup/loading/debug guard work.
21. Ensure P1 movement proof uses a bounded narrow retry policy and does not silently promote to `full_runtime_default()` on every proof miss.
22. Add a bounded P2 worker queue in the canonical search service for exhaustive sweep mode.
23. Apply P2 results to `WorldMapSurveyRecorder` on the coordinator thread in route-index order; workers must not mutate the survey index directly.
24. Preserve synchronous P2 mode for diagnostics, live enrichment, and correctness-sensitive target-search mode until bounded lookahead and async stop semantics are reviewed.
25. Re-measure the same June 7 `testing` serpentine/full-map scenario after itinerary-entry and P1 changes.
26. Only then tune local movement policy for steady-state step cost.

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

This phase is done when all of the following are true:

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

## Recommended Implementation Order

1. complete the short proof stability gate first
2. rerun the June 6 edge/corner repro until exact proof is stable
3. confirm the full-map itinerary covers `(0, 0)` through `(511, 1023)` under the canonical pattern
4. add explicit first-leg movement intent to the resolved itinerary
5. replace plan-wide movement-tool dispatch with per-step movement-strategy dispatch
6. route non-local first itinerary legs through the reviewed coordinate-jump primitive
7. add canonical timing breakdowns that distinguish non-local entry leg, per-step primitive, P1 proof, P2 analysis, and movement-cycle count
8. introduce P1 synchronous movement proof and route ordinary movement follow-up through it
9. introduce the P2 observation-analysis context and synchronous P2-from-P1-screenshot treatment first
10. introduce bounded async P2 only for exhaustive/map-side-safe modes after deterministic queueing tests exist
11. tune steady-state checkpoint movement only after the new entry path and P1 proof path are live and measurable

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
