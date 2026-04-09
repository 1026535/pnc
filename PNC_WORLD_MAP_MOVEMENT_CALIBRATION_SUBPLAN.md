# PNC World-Map Movement Calibration Subplan

## 1. Goal

Make the world-map sweep-observation loop fully functional and trustworthy before treating the broader search feature as complete.

This subplan narrows the immediate problem:

- make world-map movement deterministic enough for sweep traversal
- make sweep coverage reliable enough for row-major, concentric, and edge patterns
- prove the observation loop remains stable while movement is happening

Search completion is explicitly downstream of this work. We should not try to "finish search" while the movement primitive and sweep loop are still only partially calibrated.

## 2. Scope

This plan is about world-map movement and sweep execution only.

Included:

- cardinal world-map movement calibration
- swipe-lane calibration and dead-zone verification
- coordinate/viewport movement validation
- sweep checkpoint movement reliability
- sweep capture/observation stability after movement

Excluded for now:

- castle matching semantics
- profile validation
- search stop-policy semantics
- diagonal-first optimization
- coordinate-jump or overview movement tooling

## 3. Current Conclusions

### 3.1 Canonical search movement should be 4-direction only

The search patterns we actually need to support immediately are:

- row-major full sweep
- concentric / expanding-ring sweep
- edge sweeps

These patterns only require:

- `left`
- `right`
- `up`
- `down`

Diagonal movement is not a blocker for those traversal patterns. It may remain available as a secondary optimization, but it is not part of the critical path for making sweep search reliable.

### 3.2 Interior dead zones are not acceptable

The only legitimate movement dead zones should be world-map bounds:

- left edge
- right edge
- top edge
- bottom edge

If a swipe returns zero movement while the viewport is still well inside the map, that is not expected game behavior. It indicates one of:

- the emitted gesture shape is wrong
- the chosen swipe lane is bad
- the emulator input source is wrong for that lane
- the viewport parser failed to detect real movement

So the guiding rule is:

- interior dead zone => bug
- boundary dead zone => expected limit

### 3.3 Small-vs-large quantum calibration exists, but is not formalized enough yet

We already did meaningful live movement refinement:

- tested multiple ratios in live runs
- observed quantized movement like `0`, `±2`, `±4`, `±6`, `±12`
- updated canonical cardinal lanes based on those observations
- introduced asymmetric input-source handling where live results justified it

That work was real and materially improved navigation, but it was not completed as a formal, systematic calibration study. We still need a canonical, repeatable calibration pass and documentation artifact.

So the status is:

- partially completed
- useful and already integrated
- not yet exhaustive or formally documented as a final calibration matrix

## 4. Design Principles

### 4.1 Movement calibration is primary, search is downstream

We should complete movement reliability first and only then rely on it for full-map search.

### 4.2 One canonical movement model for sweep traversal

Sweep traversal should use one canonical movement model:

- cardinal only
- profile-driven
- empirically calibrated
- bounded and fail-fast

We should not maintain separate hidden movement heuristics in search-specific code.

### 4.3 Observation must be part of movement validation

A swipe is only "good" when both are true:

- the world actually moved
- the observation pipeline measured that movement correctly

Gesture validation and observation validation must therefore be coupled.

### 4.4 No interior-stall normalization

We must not normalize away or excuse interior no-motion cases as "lag" or "acceptable variance." Those are exactly the cases the calibration plan must eliminate or explain.

## 5. Target End State

We want a sweep-ready movement subsystem with these properties:

1. For each cardinal direction, we have one canonical calibrated lane.
2. For each cardinal direction, we know the displacement quanta produced by a small set of tested ratios.
3. For each cardinal direction, we know which results correspond to:
   - usable movement
   - boundary stall
   - invalid interior stall
4. The sweep loop can move from checkpoint to checkpoint and re-observe without collapsing into parser churn or repeated no-motion failures.
5. Full-map traversal can be attempted with confidence because movement and observation are both already validated.

## 6. Work Plan

### Phase 1. Formal Cardinal Calibration

Goal:

- finish the calibration study for `left`, `right`, `up`, `down`

Required method:

- keep lane fixed while testing ratio
- keep ratio fixed while testing lane
- repeat probes from a stable viewport
- record actual coordinate deltas

Required probe separation:

- separate "small quantum" from "large quantum" probes
- explicitly test ratios such as:
  - `0.10`
  - `0.20`
  - `0.30`
  - `0.40`

For each direction, measure which displacement bands appear, for example:

- `0`
- `±2`
- `±4`
- `±6`
- `±12`

Then define the canonical lane from observed quantized behavior rather than from guesses.

Deliverables:

- one canonical calibrated profile per cardinal direction
- one documented displacement table per direction
- one explicit rule for which input source belongs to that direction

### Phase 2. Dead-Zone Verification

Goal:

- prove that no-motion cases only occur at true map bounds

Method:

- probe the canonical lane from multiple interior viewport locations
- compare with behavior near each edge
- classify each no-motion result

Required classification:

- `expected_boundary_stop`
- `interior_stall`
- `parser_uncertain`

Success condition:

- interior stalls are either eliminated or diagnosed into a concrete lower-level cause

### Phase 3. Observation-Coupled Movement Validation

Goal:

- prove that movement detection is trustworthy during live traversal

Method:

- pair each movement probe with before/after world-map observations
- capture parsed coordinate and raw coordinate OCR evidence
- compare world movement against parser output

We must detect and distinguish:

- swipe emitted but map did not move
- map moved but parser did not update correctly
- parser updated but OCR fused or corrupted coordinates

Success condition:

- coordinate parsing is stable enough that movement calibration is not being driven by bogus viewport data

### Phase 4. Sweep-Observation Loop Validation

Goal:

- prove that the calibrated cardinal movement actually supports sweep traversal

Method:

- run bounded row-major sweep segments
- run bounded edge sweep segments
- run bounded concentric / expanding-ring segments
- verify that each movement step is followed by a usable observation

Focus:

- not "did we find the target"
- but "did movement and observation remain reliable over repeated checkpoints"

Success condition:

- sweep traversal can cover multiple checkpoints without no-motion churn, parser collapse, or dangerous recovery loops

### Phase 5. Search Re-entry

Goal:

- resume the broader search feature only after the sweep loop is proven

Entry condition:

- Phases 1 through 4 are complete

Only then should we continue:

- full-map player search
- castle targeting through sweep traversal
- broad search feature closeout

## 7. Diagnostics To Build

### 7.1 Dedicated Swipe Probe Runner

Add a dedicated probe path that performs exactly one swipe at a time and records:

- before coordinate
- exact swipe points
- input source used
- after coordinate
- delta
- screenshot artifact path
- raw coordinate OCR text before/after

This should be usable without invoking the whole search loop.

### 7.2 Cardinal Calibration Matrix

For each of `left`, `right`, `up`, `down`, record:

- lane location
- input source
- ratio tested
- repeated trial count
- observed displacement distribution

This matrix becomes the source of truth for the canonical profiles.

### 7.3 Dead-Zone Report

Record each zero-motion result with:

- viewport coordinate
- direction
- lane
- ratio
- whether the viewport was near a boundary

This is required to prove that dead zones are boundary-only.

## 8. Acceptance Criteria

This subplan is complete only when all of the following are true:

1. Cardinal movement is formally calibrated and documented.
2. Interior dead zones are not observed, or each remaining case is concretely explained and fixed.
3. The movement detector and coordinate parser are stable enough to support calibration decisions.
4. The sweep-observation loop works across multiple checkpoints using only the calibrated 4-direction model.
5. We can resume full-map search work without movement being the dominant blocker.

## 9. Relationship To Existing World-Map Search Plan

This subplan does not replace [PNC_WORLD_MAP_SEARCH_SUBPLAN.md](/C:/Users/lebel/pnc/PNC_WORLD_MAP_SEARCH_SUBPLAN.md).

It isolates the remaining critical prerequisite:

- make sweep movement and observation fully reliable first

Then, and only then, use that proven loop to finish the broader world-map search feature.
