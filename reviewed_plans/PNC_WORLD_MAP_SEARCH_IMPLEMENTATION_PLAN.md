# PNC World-Map Search Implementation Plan

## Purpose

Define one complete implementation plan for improving world-map search architecture, traversal semantics, and sweep throughput without sacrificing coverage correctness.

This document consolidates the prior search-pattern debug plan and the newer sweep-throughput plan into one canonical implementation document.

The target outcome is a clean, coherent, lean, DRY, fail-fast, and extensible world-map search design that:

- preserves frame-based search coverage for castle discovery,
- makes traversal shape explicit and auditable,
- improves throughput by separating cheap movement proof from full viewport analysis,
- introduces explicit broad-traverse vs fine-correction movement policy,
- keeps one canonical implementation per concept.

## Scope

This plan covers:

- world-map traversal pattern semantics,
- search checkpoint spacing and viewport-coverage progression,
- movement proof vs checkpoint-analysis separation,
- diagnostics and artifact-persistence behavior during movement and sweep execution,
- direct-movement policy and gesture primitive ownership,
- recognition scope implications for castle search,
- testing and live validation strategy.

This plan does not redesign the entire automation architecture. It refines the existing world-map search stack.

## Core Conclusion

For broad world-map search, especially castle search, the correct high-level loop remains:

1. move to the next analyzed viewport,
2. analyze that viewport,
3. move again,
4. repeat.

The current system is already functionally close, but it is too expensive and not explicit enough in two places:

- traversal pattern semantics for broad row coverage,
- movement-proof vs full-checkpoint-analysis responsibilities.

The clean solution is:

- make broad search traversal shape explicit,
- keep coverage frame-based,
- split cheap movement proof from full checkpoint analysis,
- make routine diagnostics persistence selective instead of eager-by-default for every intermediate observation,
- introduce explicit traverse vs fine-correction movement policy,
- make checkpoint spacing represent viewport coverage stride again,
- keep all of this under one canonical architecture.

## Current Architecture

### Canonical Ownership Already Present

The current codebase already has the correct major owners:

- `ObservationRequest`
  - owns observation scope and OCR cost policy
- `ObservationService`
  - owns screenshot capture plus OCR-backed observation building
- `ActionExecutor`
  - owns low-level action execution and pacing
- `ObservedActionExecutor`
  - owns observed action sequencing and reviewed selector fallback
- `WorldMapNavigator`
  - owns low-level world-map movement action planning
- `WorldMapCoordinateMover`
  - owns direct coordinate-focused movement orchestration
- `WorldMapSearchService`
  - owns search request validation, route resolution, checkpoint movement orchestration, ingestion, matching, and stop policy
- `WorldMapSurveyRecorder`
  - owns checkpoint ingestion and survey-state persistence
- `WorldMapTraversalPlanner`
  - owns route generation
- `WorldMapCoordinateDomain`
  - owns world bounds and addressable coordinate normalization

This ownership model should be preserved. The implementation work below should refine it, not bypass it.

### Current Search Loop

The current search loop is broadly:

1. resolve a `WorldMapSearchRequest`,
2. move to each traversal checkpoint,
3. land on a proven world-map observation,
4. ingest that observation through `WorldMapSurveyRecorder`,
5. analyze visible objects and index matches,
6. continue until stop policy is satisfied.

That structure is correct and should remain the basis of the system.

### Current Movement Proof Behavior

World-map direct movement currently relies on:

- `WorldMapNavigator.plan_focus_coordinate(...)`,
- `ObservationRequest.world_map_movement_follow_up()`,
- `WorldMapCoordinateMover.move_to_coordinate(...)`.

This is already narrower than the full runtime observation path, which is good. However, the landed observation still ends up serving both:

- movement proof,
- checkpoint-analysis-quality ingestion.

That coupling is now the main throughput problem.

### Current Checkpoint Ingestion Behavior

`WorldMapSurveyRecorder.record_checkpoint(...)` already avoids a redundant second screenshot when the landed observation is already a valid world-map observation.

That behavior is good and must be preserved.

However, avoiding a second screenshot is not enough. The current landed observation still carries enough responsibility for:

- movement proof,
- checkpoint ingestion,
- spatial-surface object recognition,
- match collection,
- survey debug persistence.

This is why movement proof and full checkpoint analysis still feel too expensive and too entangled.

### Current Diagnostics Persistence Behavior

Routine debug screenshots are currently written immediately when the active artifact policy includes screenshot persistence.

Routine logs are also emitted immediately.

This is simple and useful for live debugging, but for broad sweeps it creates too much routine persistence churn on intermediate movement observations that are not themselves important final checkpoints.

Logging is already a shared diagnostics concern in the architecture and should remain so. The improvement needed here is to extend that shared diagnostics system with buffering/mode support, then have world-map modules consume the appropriate defaults.

## Current Problems

### Problem 1: Broad Search Traversal Semantics Are Not Yet Explicit Enough

The current planner models `ROW_MAJOR_SWEEP` only as checkpoint order. It does not make row-transition movement policy explicit.

For the target design, the broad row-based patterns need two distinct semantics:

- `ROW_MAJOR_SWEEP`
  - every analyzed row proceeds left to right,
  - each row transition emits one explicit non-local reset intent toward the left/start of the next row.
- `SERPENTINE_ROW_SWEEP`
  - analyzed rows alternate direction,
  - row transitions stay local because the end of one row is already near the start of the next.

Without these semantics being explicit in the pattern model:

- route logs are harder to audit against intended coverage,
- movement-tool selection for row transitions remains implicit,
- broad full-map castle search cannot express the desired traversal order clearly in code.

### Problem 2: Movement Proof And Full Checkpoint Analysis Are Too Coupled

After moving, the system first needs to answer:

- are we still on the world map?
- what viewport coordinate did we land on?

It does not always need a fully checkpoint-analysis-ready observation for every intermediate leg.

Today, movement follow-up is narrower than the full runtime request, but it is still too close to full analysis responsibility in practice.

### Problem 3: Broad Traversal And Fine Correction Share One Intent

The same movement stack is effectively serving two different jobs:

- cover ground efficiently during broad traversal,
- land precisely near a target checkpoint.

This causes:

- too much correction behavior while still far away,
- overshoot and correction during long travel,
- unnecessary observed legs.

### Problem 4: Search Progression Still Risks Collapsing Into Tiny Coordinate Behavior

The system now has trustworthy coordinate-domain normalization and bounded coordinate movement. That means broad search should again be defined by viewport-coverage stride rather than by whichever small coordinate delta happened to be safe during earlier movement-debug phases.

### Problem 5: Recognition Coverage Must Be Treated Explicitly

Castle search depends on reliable frame analysis.

If traversal is correct but viewport analysis cannot recognize relevant castle evidence, a broad search can still miss targets. That is a recognition issue, not a traversal issue, and the architecture should make that distinction visible.

### Problem 6: Diagnostics Persistence Is Too Eager For Broad Sweeps

For long movement and broad sweeps, routine persistence currently happens too early and too often.

The two most important cases are:

- routine logs that may be desirable either live or buffered by sequence,
- routine screenshots that are useful for selected analyzed checkpoints and failures, but not necessarily for every intermediate movement-proof observation.

The system needs explicit policy here instead of one always-on behavior.

## Important Findings From Recent Investigation

### Granularity Findings

Recent live work established:

- `max_axis_delta_per_leg` is useful,
- `granularity=1` was invalid with `focus_tolerance=1` and is now correctly rejected fail-fast,
- `granularity=4`, `5`, and `10` are workable,
- changing granularity alone does not remove the dominant movement cost.

Conclusion:

- granularity remains useful,
- but it is not the main long-term throughput lever for broad search.

### Viewport Width vs Effective Movement

Recent live reasoning and screenshots support:

- visible horizontal coverage is plausibly around `8-10`,
- one reliable swipe often advances only around `6`,
- long moves still overshoot or undershoot depending on lane and state.

Conclusion:

- one gesture's effective displacement is not the same as one viewport width,
- checkpoint spacing should be based on viewport-coverage policy, not raw swipe delta.

### `press_move_release` Primitive

The codebase now supports two gesture primitives:

- `SwipeGesturePrimitive.SWIPE`
- `SwipeGesturePrimitive.PRESS_MOVE_RELEASE`

The second primitive is implemented through Android `motionevent DOWN/MOVE/UP` and is runtime-configurable through `configure_world_map_movement_gesture_primitive(...)`.

Recent live findings showed:

- it works through the production movement stack,
- it does not automatically solve overshoot,
- it is slower than normal `swipe` on the tested lane,
- it needed fewer legs in one long-travel comparison, but each leg took longer.

Conclusion:

- the primitive is valid and should remain first-class,
- but it is not the primary throughput fix.

### Long-Travel Behavior

Recent live comparisons of `x:+30` showed that both gesture primitives can complete long travel, but both still behave as if correction is active too early.

Conclusion:

- the movement policy needs an explicit broad-traverse vs fine-correction distinction.

### Missing Live Validation Coverage

Recent live testing has been materially stronger for horizontal X-axis movement than for vertical Y-axis movement.

We do not yet have equivalent live evidence for:

- `y:+N` broad travel,
- `y:-N` broad travel,
- top/bottom boundary-stop behavior under the current movement stack,
- whether `press_move_release` changes vertical movement characteristics differently from horizontal movement,
- whether vertical movement should use the same traverse-vs-correction thresholds as horizontal movement.

Conclusion:

- the implementation plan should explicitly require vertical live validation before considering world-map movement policy sufficiently tuned.

## Requirements

### Coverage Requirement

Broad castle search must progress by intentionally analyzed viewports, not by skipping unseen map areas.

### Traversal Requirement

Broad row-style full-map traversal must be able to express both:

- left-to-right row-major traversal with explicit non-local row-reset intent,
- serpentine traversal with alternating row direction.

### Throughput Requirement

Movement proof must be cheaper than full checkpoint analysis.

### Stride Default Requirement

Across search patterns, the default traversal stride should be:

- one horizontal viewport for horizontal progression,
- one vertical viewport for vertical progression.

Custom stride overrides should remain supported, but only as explicit authored/runtime parameters.

### Diagnostics Requirement

The system must support two logging behaviors:

- immediate write-through logging,
- buffered logging that flushes at defined sequence boundaries or on failure.

Routine screenshot persistence for broad sweep flows must be selective:

- keep failure screenshots immediate,
- keep `LIGHT` mode unchanged as the no-routine-persistence mode,
- in persisted sweep/debug flows, persist selected analyzed checkpoints and end-of-sequence artifacts instead of every intermediate movement observation.

This should be achieved by improving the shared diagnostics and observation-artifact policy systems, not by making world-map search own a separate logging subsystem.

### Policy Requirement

The system must explicitly distinguish:

- broad traversal movement,
- near-target correction movement.

### Segment Intent Requirement

Traversal planning must emit segment intent explicitly when checkpoint-to-checkpoint movement semantics differ.

At minimum, the route model must be able to distinguish:

- local traversal between nearby checkpoints,
- non-local reset transitions where the runtime may select a different reviewed movement primitive family.

### Observation Contract Requirement

The system must not capture the same settled viewport twice just because both lightweight movement proof and full checkpoint analysis exist.

For one settled viewport, the workflow must choose exactly one observation mode at that moment:

- lightweight coordinate/movement proof,
- full checkpoint analysis.

If the viewport is only an intermediate traversal stop, capture only the lightweight movement-proof observation.

If the viewport is an analyzed checkpoint, capture only the full checkpoint-analysis observation.

Do not first capture lightweight proof and then recapture the exact same settled viewport for full analysis.

### DRY Requirement

Each of the following must have one canonical owner:

- observation scope policy,
- diagnostics persistence policy,
- movement policy,
- traversal-pattern semantics,
- checkpoint-analysis ingestion,
- search stride semantics.

### Validation Requirement

Invalid authored or runtime policy combinations must fail fast with precise error messages.

## Non-Goals

This plan does not aim to:

- replace broad castle search with coordinate jumps,
- redesign the full recognition stack from scratch,
- recalibrate every map detector immediately,
- introduce parallel movement/search subsystems,
- finalize every gesture calibration detail in this document.

Coordinate jumps remain useful for other workflows, but this plan keeps broad castle sweep frame-based.

## Current Configurability

### Traversal Stride Policy

The target design should replace split stride ownership with one canonical `TraversalStridePolicy` owned by the request/pattern layer.

That policy should be the only search-stride seam.

It should support:

- symmetric stride for the common case,
- explicit horizontal and vertical stride components when a pattern truly needs axis-specific progression.

This keeps the default broad-search behavior viewport-sized while avoiding pattern-local duplicate stride parameters.

### Default Viewport Stride Profile

The target design should add one canonical default viewport-stride profile rather than scattering raw viewport constants through search patterns.

That profile should own:

- `default_horizontal_viewport_stride_units`
- `default_vertical_viewport_stride_units`

It should provide the reviewed default stride values used when the caller does not override search progression explicitly.

This keeps the existing request semantics intact:

- explicit request/authored `TraversalStridePolicy` values still win,
- the profile only supplies defaults,
- pattern implementations should consume the same shared default source.

### Direct-Movement Granularity

Direct-movement granularity is already runtime-configurable through `max_axis_delta_per_leg`.

This is useful for bounded direct movement and live tuning, but it should not become a parallel owner of broad search stride semantics.

### Gesture Primitive

The world-map gesture primitive is currently configurable at runtime through:

- `configure_world_map_movement_gesture_primitive(...)`

It is not yet an authored config/YAML field.

That is acceptable for live experimentation today. If it becomes a stable runtime policy surface, it should move into one canonical config seam.

### Observation Persistence Mode

`LIGHT` mode already behaves as the no-routine-persistence mode and should remain unchanged.

The improvement described in this plan is not a replacement for `LIGHT`. It is a selective persisted mode for world-map sweep flows where:

- failure screenshots remain immediate,
- routine intermediate movement-proof observations are not all written,
- selected analyzed checkpoints and end-of-sequence artifacts are written intentionally.

### Logging Mode

Logging should grow an explicit mode distinction:

- immediate logging mode,
- buffered-per-sequence logging mode.

This should stay in the shared diagnostics subsystem rather than becoming world-map-specific logic.

## Recognition Scope

This plan does not require a complete map-element taxonomy before the first improvement slice can be built.

However, full checkpoint analysis will eventually benefit from an explicit classification of map elements by search importance.

The currently modeled world-map object kinds already include:

- `castle`
- `alliance_building`
- `monster`
- `hell_fortress`
- `resource_node`
- `altar`
- `dragonia`

Implications:

- castle recognition remains the primary correctness requirement for this plan,
- OCR on the coordinate bar is acceptable and should remain part of movement proof,
- a faster full-map classifier, if later needed, should apply to checkpoint-analysis work rather than movement-proof work,
- unsupported or weakly recognized map elements must be treated as recognition gaps, not silently as traversal bugs.

## Canonical Typed Models

The target design should name the main policy and route concepts explicitly rather than letting them remain implicit across request fields and planner behavior.

Recommended typed models:

- `TraversalStridePolicy`
  - owns symmetric vs axis-specific analyzed-checkpoint stride
  - is the canonical stride-policy seam across all traversal patterns
- `WorldMapViewportStrideProfile`
  - owns reviewed default horizontal and vertical viewport stride values
  - supplies defaults to `TraversalStridePolicy`
- `WorldMapTraversalRoutePlan`
  - owns the ordered route geometry resolved from one high-level search pattern plus its parameters
  - represents the route as one ordered array of route segments / polylines rather than only disconnected checkpoints
- `WorldMapTraversalRouteSegment`
  - owns one segment of the ordered route geometry
  - carries segment geometry plus traversal intent
- `TraversalSegmentIntent`
  - owns semantic intent for checkpoint-to-checkpoint transitions
  - distinguishes local traversal from non-local reset transitions
- `WorldMapTraversalExecutionPlanner`
  - owns translation from route geometry plus movement policy into executable traversal steps
  - pairs each route segment with the reviewed action family that should satisfy it
- `WorldMapTraversalExecutionStep`
  - owns one executable traversal-step envelope
  - carries pre-op policy, action family, post-op policy, and failure-handling policy needed for one route segment
- `WorldMapMovementPolicy`
  - owns gesture primitive, traverse-vs-correction behavior, and intent-to-primitive resolution
- `ObservationMode`
  - owns the settled-viewport observation contract
  - distinguishes lightweight movement proof from full checkpoint analysis

These names are illustrative, but the architecture should end up with one explicit typed owner for each concept rather than spreading the same semantics across loosely related fields.

### Naming Improvement Note

The current runtime names `WorldMapNavigator` and `WorldMapCoordinateMover` are serviceable, but they under-describe the route-planner vs execution-planner vs primitive-layer split.

The target design should prefer names that make the layering obvious:

- high-level route planner
- execution planner
- low-level action planner
- traversal executor

Recommended target naming:

- `WorldMapTraversalRoutePlanner`
  - high-level route planner
  - turns one search pattern plus resolved parameters into one ordered route plan
- `WorldMapTraversalExecutionPlanner`
  - execution planner
  - turns one route plan into executable traversal steps
- `WorldMapTraversalActionPlanner`
  - low-level action planner
  - turns one planned action family into concrete low-level map actions such as swipe, click-drag-release, or jump
- `WorldMapTraversalExecutor`
  - execution owner
  - runs traversal execution steps end to end

If the codebase keeps the existing class names for compatibility during migration, the plan should still treat these as the intended responsibilities:

- current `WorldMapNavigator` -> conceptual traversal action planner
- new layer still needed -> conceptual traversal execution planner
- current `WorldMapCoordinateMover` -> conceptual traversal executor

## Route Segment Intent

Traversal patterns should not directly hardcode low-level movement primitives. They should emit route semantics through explicit route geometry plus segment intent.

Recommended minimum intent model:

- `LOCAL_TRAVERSE`
  - for nearby checkpoint progression that should remain in the direct local movement stack
- `NON_LOCAL_RESET`
  - for reviewed non-local reposition transitions such as row resets

Pattern planning owns:

- resolving one high-level pattern plus its parameters into one ordered route plan,
- emitting route segments / polylines,
- emitting the intent between checkpoints,
- preserving deterministic route semantics.

The execution-planning layer owns:

- interpreting route geometry against movement policy,
- pairing each route segment with the reviewed action family that should satisfy it,
- assigning per-segment pre-op policy,
- assigning per-segment post-op policy,
- assigning per-segment failure-handling policy,
- preserving separation between route geometry planning and primitive selection.

The runtime movement layer owns:

- executing the reviewed primitive family selected for the compiled segment,
- deciding how one compiled jump, swipe, or drag family becomes concrete low-level map actions,
- preserving fail-fast behavior when no supported primitive can satisfy the planned intent.

This is the clean separation that keeps:

- traversal semantics,
- route compilation,
- low-level primitive execution

distinct from one another.

That means the low-level primitive layer should stay agnostic of:

- segment pre-ops,
- segment post-ops,
- sequence logging policy,
- observation workflow decisions.

Those belong in the traversal execution step and the higher-level traversal executor.
Those belong in the traversal execution step and the higher-level traversal executor.

## Target Model

### 1. Explicit Search Patterns And Route Geometry

Traversal pattern must explicitly define one ordered route geometry plan, not be inferred from movement side effects.

That route geometry should be represented as one ordered array of route segments / polylines. Each segment should carry:

- ordered coordinate geometry,
- segment intent,
- the requested relationship between one segment and the next.

Recommended pattern model:

- keep `ROW_MAJOR_SWEEP`
  - left-to-right analyzed rows
  - explicit non-local row-reset intent to the next row origin
  - default horizontal row stride of one viewport
  - default vertical row-to-row stride of one viewport
- add `SERPENTINE_ROW_SWEEP`
  - alternating row direction with local row-to-row continuity
  - default horizontal row stride of one viewport
  - default vertical row-to-row stride of one viewport
- keep `EXPANDING_RING`
  - default ring expansion stride of one viewport per axis step
  - implemented through the same canonical stride policy as other patterns
- add `PERIMETER_RING_SWEEP`
  - one explicit perimeter loop around the current rectangle
  - intended for top edge, right edge, bottom edge, and left edge traversal in one ordered cycle
- add `SHRINKING_PERIMETER_SWEEP`
  - repeated inward perimeter loops
  - intended for outer perimeter first, then the next inset perimeter, and so on until exhausted

`EDGE_BAND_SWEEP` should be treated as obsolete in the target design and removed rather than carried forward. Its current semantics are too weak and too unlike the intended perimeter-search behavior to justify keeping it as a canonical pattern.

Do not silently overload `ROW_MAJOR_SWEEP` to behave like serpentine traversal. Callers should be able to see the intended semantics directly in the request.

Likewise, do not redefine `EDGE_BAND_SWEEP` to secretly mean one of the new perimeter patterns. The clean path is:

- remove `EDGE_BAND_SWEEP`,
- add `PERIMETER_RING_SWEEP`,
- add `SHRINKING_PERIMETER_SWEEP`.

### Pattern Summary

| Pattern | Default stride source | Allowed overrides | Transition intent | Expected movement primitive family |
| --- | --- | --- | --- | --- |
| `ROW_MAJOR_SWEEP` | `TraversalStridePolicy` resolved from `WorldMapViewportStrideProfile` | Symmetric or axis-specific through the same shared stride policy | `LOCAL_TRAVERSE` within rows, `NON_LOCAL_RESET` between rows | Local direct movement within rows; reviewed non-local primitive for row reset |
| `SERPENTINE_ROW_SWEEP` | `TraversalStridePolicy` resolved from `WorldMapViewportStrideProfile` | Symmetric or axis-specific through the same shared stride policy | `LOCAL_TRAVERSE` throughout, including row transitions | Local direct movement |
| `EXPANDING_RING` | `TraversalStridePolicy` resolved from `WorldMapViewportStrideProfile` | Symmetric by default; axis-specific only through the same shared stride policy | `LOCAL_TRAVERSE` between successive ring checkpoints unless a future reviewed route says otherwise | Local direct movement |
| `PERIMETER_RING_SWEEP` | `TraversalStridePolicy` resolved from `WorldMapViewportStrideProfile` | Axis-specific through the same shared stride policy; explicit `start_corner` and `rotation` | `LOCAL_TRAVERSE` around the perimeter by default | Local direct movement |
| `SHRINKING_PERIMETER_SWEEP` | `TraversalStridePolicy` resolved from `WorldMapViewportStrideProfile` | Axis-specific through the same shared stride policy; explicit `inset_x` and `inset_y` | `LOCAL_TRAVERSE` around each perimeter, then reviewed transition to next inset perimeter | Local direct movement by default; future reviewed inset-transition policy if needed |

### Geometry Completeness Requirement

The plan is close to sufficient for route geometry generation, but the implementation target should make the segment schema explicit so each pattern can be implemented without hidden decisions.

Each `WorldMapTraversalRouteSegment` should carry at least:

- `segment_index`
- `polyline_vertices`
- `start_coordinate`
- `end_coordinate`
- `traversal_segment_intent`
- `analyzed_checkpoint_coordinates` represented by that segment

For pattern implementation, this means:

- `ROW_MAJOR_SWEEP`
  - one local-traverse polyline per row
  - one non-local-reset segment between consecutive rows
- `SERPENTINE_ROW_SWEEP`
  - one local-traverse polyline per row
  - row-to-row continuity stays local unless a reviewed exception is introduced
- `EXPANDING_RING`
  - one deterministic ordered ring decomposition, preferably by top edge, right edge, bottom edge, then left edge per ring
  - corner handling must avoid duplicate vertices/checkpoints
- `PERIMETER_RING_SWEEP`
  - one deterministic perimeter-edge decomposition
  - top, right, bottom, left edge order must be explicit and rotation-aware
- `SHRINKING_PERIMETER_SWEEP`
  - one deterministic sequence of perimeter decompositions over inset rectangles
  - inset exhaustion rules must be explicit and fail fast when no valid addressable perimeter remains

So the answer is:

- yes, the plan now has enough architecture to support geometry generation cleanly,
- but the implementation should still add this explicit segment schema and deterministic edge/ring decomposition rules so pattern geometry is mechanically derivable rather than inferred.

#### `PERIMETER_RING_SWEEP` Semantics

`PERIMETER_RING_SWEEP` should traverse one resolved rectangle perimeter explicitly.

Default intended semantics:

1. start at the requested start corner,
2. traverse the top edge by horizontal viewport stride,
3. traverse the right edge by vertical viewport stride,
4. traverse the bottom edge by horizontal viewport stride,
5. traverse the left edge by vertical viewport stride,
6. stop after the full perimeter loop closes.

Recommended parameters:

- `start_corner`
  - default `UPPER_LEFT`
- `rotation`
  - default `CLOCKWISE`
- `traversal_stride_policy`

#### `SHRINKING_PERIMETER_SWEEP` Semantics

`SHRINKING_PERIMETER_SWEEP` should repeat the perimeter loop on progressively inset rectangles.

Default intended semantics:

1. run one `PERIMETER_RING_SWEEP` on the outer rectangle,
2. inset the rectangle,
3. run the same ordered perimeter loop on the next inner rectangle,
4. repeat until no valid addressable perimeter remains.

Recommended parameters:

- `start_corner`
  - default `UPPER_LEFT`
- `rotation`
  - default `CLOCKWISE`
- `traversal_stride_policy`
- `inset_x`
- `inset_y`

`inset_x` and `inset_y` should remain explicit even when they often equal one viewport-sized stride, because overlap-safe inward shrink may eventually need to differ from edge traversal stride.

### 2. Coverage-Driven Search Stride

`checkpoint_spacing` should represent analysis stride between intentionally analyzed viewports.

It should be chosen from viewport-coverage policy, not from correction-sized movement behavior.

Conceptually:

- default horizontal analysis stride = one horizontal viewport,
- default vertical analysis stride = one vertical viewport,
- custom authored/runtime overrides may reduce or increase that stride when needed.

If effective horizontal coverage is roughly `8-10`, then the reviewed default should be one viewport of progression, with custom overlap-conscious overrides available where the caller wants denser or sparser coverage.

The canonical default values should come from one reviewed viewport-stride profile rather than being re-derived separately by each pattern.

Recommended design:

- use one shared stride-policy model across all traversal patterns,
- allow that model to express symmetric and axis-specific stride values,
- keep the default broad-search case symmetric where appropriate,
- use axis-specific values only when one pattern truly needs different horizontal and vertical progression.

`EXPANDING_RING` should use this same shared stride policy.

Recommended stance for `EXPANDING_RING`:

- default to symmetric expansion for the normal case,
- allow axis-specific horizontal/vertical expansion through the same shared stride policy when explicitly configured,
- do not invent a pattern-local expansion parameter model that duplicates stride ownership.

### 3. Separate Movement Proof From Full Checkpoint Analysis

Movement proof should answer only:

- still on world map?
- landed at which coordinate?

Checkpoint analysis should own:

- spatial-surface object extraction,
- checkpoint ingestion,
- index updates,
- match collection,
- survey-state persistence.

These should remain part of one canonical observation system, but they should use different scopes intentionally.

Concrete handoff contract:

- for an intermediate traversal stop, capture only the lightweight movement-proof observation,
- for an analyzed checkpoint stop, capture only the full checkpoint-analysis observation,
- do not capture the same settled viewport twice to satisfy both responsibilities,
- workflow intent decides which observation mode applies at that settled viewport.

Observation rule:

- there is no “promotion then recapture the same settled viewport” path
- there is one chosen observation mode per settled viewport event
- if full checkpoint analysis is needed at that viewport, capture it directly instead of first taking a lightweight proof capture

### Execution Step Mapping To Existing Runtime Concepts

The planned `WorldMapTraversalExecutionStep` should map to the current runtime concepts as follows.

`pre_op`

- owned by the traversal execution planner as workflow policy, not by the low-level action planner
- maps to existing readiness/proof concepts such as:
  - `_require_proven_world_map_observation(...)`
  - world-map entry / recovery through `ScreenFlowPlanner`
  - start-of-step validation that the current viewport is still world-map and coordinate-addressable

`action_family`

- owned by the traversal execution planner and movement policy
- maps to the existing low-level movement families:
  - direct local movement through `WorldMapNavigator`
  - coordinate jump through the existing coordinate-jump flow
  - future reviewed non-local primitives such as overview-assisted repositioning when applicable

`post_op`

- owned by the traversal execution planner as workflow policy, not by the low-level action planner
- maps to existing observation and validation seams:
  - lightweight movement proof through `ObservationRequest.world_map_movement_follow_up()`
  - proven world-map validation through `_require_proven_world_map_observation(...)`
  - final checkpoint ingestion through `WorldMapSurveyRecorder.record_checkpoint(...)`
  - optional diagnostics/logging/artifact persistence through the shared diagnostics and artifact-policy subsystems

`failure_handling`

- owned by the traversal execution planner and the higher-level executor
- maps to the existing fail-fast / bounded-recovery behavior:
  - `SelectorResolutionError`
  - bounded proof-refresh or retry behavior already used by the movement/search stack
  - immediate failure logging and artifact persistence

This keeps the ownership clean:

- low-level action planning stays agnostic of workflow concerns,
- pre-op/post-op remain execution-step policy,
- existing observation, proof, ingestion, and diagnostics concepts are reused rather than duplicated.

### 4. Explicit Traverse vs Fine-Correction Movement Policy

The movement system should explicitly model two modes:

- `traverse`
- `fine_correction`

The low-level gesture/profile layer already supports both cardinal and diagonal movement primitives. However, the current canonical direct checkpoint mover used by world-map search intentionally decomposes travel into cardinal legs. That distinction should remain explicit in the implementation and validation work:

- primitive/profile capability may be diagonal,
- current sweep/direct movement policy is cardinal-leg-based,
- any future use of diagonal traverse movement should be an explicit policy decision rather than an accidental side effect.

The movement layer should also consume explicit traversal segment intent from the planned route rather than inferring all transitions from checkpoint geometry alone.

#### Traverse

Used when remaining travel is still large.

Properties:

- optimized for moving to the next analyzed viewport,
- allows controlled overlap and bounded imprecision,
- avoids overly conservative correction behavior while far away.

#### Fine Correction

Used only when remaining distance is sufficiently small that precise landing matters more than throughput.

Properties:

- smaller intended movement,
- smaller tolerance for overshoot,
- activated only near target.

### 5. Gesture Primitive As Policy Input

Gesture primitive should remain one parameter of the canonical movement policy.

Do not create parallel movement systems for:

- `swipe`
- `press_move_release`

Both should remain implementations of one shared world-map movement stack.

### 6. Explicit Diagnostics Persistence Policy

The search stack should explicitly distinguish between:

- routine intermediate observations needed only to continue execution,
- analyzed checkpoint observations worth persisting,
- failure observations that must persist immediately.

Likewise, logging should explicitly distinguish between:

- immediate write-through mode for live interactive debugging,
- buffered mode for sequence-scoped flush.

This should not be handled by ad hoc tool logic. It should be one canonical shared diagnostics policy concept that world-map modules consume through defaults and call-site policy.

## Desired Broad Full-Map Row Routes

For the live PNC domain:

- bounds are `X=0..511`, `Y=0..1023`,
- valid addressable pairs require even `x + y`,
- upper-left is `(0, 0)`,
- top-row right endpoint is `(510, 0)` because `(511, 0)` is not addressable,
- lower-left is `(0, 1022)` because `(0, 1023)` is not addressable.

For a full-map `ROW_MAJOR_SWEEP` with default row stride of one viewport:

1. generate addressable row samples from top to bottom,
2. for every sampled row, emit one left-to-right local-traverse polyline using the default horizontal viewport stride unless overridden,
3. after each completed row except the last, emit one non-local row-reset segment toward the left/start of the next row,
4. advance to the next sampled row using the default vertical viewport stride unless overridden,
5. include the last addressable row inside the boundary even when stride does not land on it exactly.

The intended row-transition policy for this pattern is:

- local traversal within a row,
- explicit non-local reset intent between rows.

The runtime movement layer should then resolve that non-local reset intent to the reviewed primitive available in the runtime, such as coordinate jump by default or another approved non-local reposition primitive later.

For a full-map `SERPENTINE_ROW_SWEEP` with default row stride of one viewport:

1. generate addressable row samples from top to bottom,
2. row `0`: emit one left-to-right local-traverse polyline using the default horizontal viewport stride unless overridden,
3. row `1`: emit one right-to-left local-traverse polyline using the same default horizontal viewport stride unless overridden,
4. alternate until the final sampled row,
5. advance rows using the default vertical viewport stride unless overridden,
6. include the last addressable row inside the boundary even when stride does not land on it exactly.

Pattern planning must always consume `WorldMapCoordinateDomain`:

- do not emit impossible coordinate pairs,
- normalize corner origins through the domain,
- keep row endpoints inside the boundary,
- fail fast when a requested row or rectangle contains no addressable coordinate.

## Proposed Canonical Ownership After Improvement

### Observation Scope

Owner:

- `ObservationRequest`

Responsibilities:

- movement-proof scope,
- checkpoint-analysis scope,
- explicit runtime observation contracts.
- no-double-capture settled-viewport rule.

### Traversal Pattern Semantics

Owner:

- `WorldMapTraversalPlanner`
- with `WorldMapCoordinateDomain` as the canonical source of addressable coordinate rules

Responsibilities:

- row-major vs serpentine route generation,
- producing the ordered route geometry / polyline plan,
- pattern-owned row-transition semantics,
- segment intent emission,
- stride-driven checkpoint emission,
- boundary-respecting addressable coordinate planning.

Recommended target conceptual name:

- `WorldMapTraversalRoutePlanner`

That better reflects the target responsibility: converting one high-level pattern plus resolved parameters into one ordered route plan.

### Traversal Plan Compilation

Owner:

- `WorldMapTraversalExecutionPlanner`

Responsibilities:

- consume the ordered route geometry / polyline plan,
- consume movement policy and runtime capability,
- translate each route segment into one `WorldMapTraversalExecutionStep`,
- pair each route segment with the reviewed action family that should satisfy it,
- attach segment pre-op policy,
- attach segment post-op policy,
- attach segment failure-handling policy,
- keep primitive selection out of the high-level traversal route planner.

Recommended target conceptual name:

- `WorldMapTraversalExecutionPlanner`

That better reflects the intended responsibility than a generic compiler name: it plans how each route segment should be executed, not just how it should be transformed.

### Movement Policy

Owner:

- the world-map movement policy used by `WorldMapNavigator` and `WorldMapCoordinateMover`

Responsibilities:

- mapping planned segment intent to reviewed primitive families,
- gesture primitive selection,
- traverse vs fine-correction selection,
- correction-threshold validation,
- reviewed movement defaults.

### Primitive Action Planner

Current runtime owner:

- `WorldMapNavigator`

Recommended target conceptual name:

- `WorldMapTraversalActionPlanner`

Responsibilities:

- translate one compiled action family into concrete reviewed low-level map actions,
- implement low-level jump, swipe, and click-drag-release action planning,
- stay agnostic of segment pre-op/post-op workflow concerns,
- avoid owning multi-segment end-to-end traversal.

Interacts with:

- `WorldMapMovementPolicy`
- `WorldMapTraversalExecutionStep`
- `WorldMapTraversalExecutionPlanner`
- `ActionExecutor`
- the higher-level traversal executor

### Traversal Execution Runner

Current runtime owner:

- `WorldMapCoordinateMover`

Recommended target conceptual name:

- `WorldMapTraversalExecutor`

Responsibilities:

- own end-to-end execution of one compiled traversal plan,
- run segment pre-ops when required,
- delegate the segment action family to the traversal action planner,
- run segment post-ops such as observation, validation, logging, and error handling according to policy,
- choose traverse vs fine-correction mode only where the execution planner/policy requires it,
- avoid owning high-level route-shape generation.

Interacts with:

- `WorldMapTraversalExecutionPlanner`
- `WorldMapTraversalActionPlanner`
- `WorldMapMovementPolicy`
- `WorldMapTraversalExecutionStep`
- `ObservationRequest`
- `ObservationService`
- `ActionExecutor`
- `WorldMapSearchService`

### Search Stride

Owner:

- the request/pattern-owned `TraversalStridePolicy`

Responsibilities:

- define analyzed viewport stride for traversal patterns,
- provide viewport-sized defaults for horizontal and vertical progression unless explicitly overridden,
- consume one canonical reviewed viewport-stride profile for default values,
- reflect viewport coverage policy rather than arbitrary micro-movement.

`WorldMapSearchRequest.checkpoint_spacing` should remain supported only as the current symmetric authored seam during migration, with the target ownership moving to the canonical `TraversalStridePolicy`.

### Default Viewport Stride Profile

Owner:

- the canonical world-map search policy surface consumed by `WorldMapSearchRequest` and `WorldMapTraversalPlanner`

Responsibilities:

- hold reviewed default horizontal viewport stride units,
- hold reviewed default vertical viewport stride units,
- provide one shared default source for all traversal patterns,
- preserve explicit request overrides.

### Checkpoint Analysis

Owner:

- `WorldMapSurveyRecorder`
- `WorldMapSearchService`

Responsibilities:

- checkpoint ingestion,
- indexing,
- match collection,
- survey-state persistence.

### Diagnostics Persistence

Owner:

- the shared diagnostics subsystem for logging behavior
- the shared observation-artifact policy subsystem for screenshot persistence behavior

Responsibilities:

- immediate vs buffered logging mode,
- selective vs routine screenshot persistence behavior,
- guaranteed immediate failure persistence,
- sequence-boundary flush semantics,
- exposing clean defaults that world-map observation and runner flows can adopt without inventing local buffering logic.

## Detailed Implementation Plan

## Migration Strategy

The current runtime still uses:

- `checkpoint_spacing` as the authored stride seam
- `EDGE_BAND_SWEEP` as one implemented pattern
- direct planner-to-checkpoint routing without the explicit route-plan / execution-step split

The migration must be explicit and single-track so we do not leave parallel APIs behind.

Required migration rules:

- introduce the new canonical seams first
- adapt existing callers through one compatibility bridge only while migration is in progress
- port authored/runtime call sites to the new seams
- delete obsolete compatibility paths once call sites are migrated

Specific migration targets:

- replace `EDGE_BAND_SWEEP` with the reviewed perimeter patterns and remove the edge-band-specific route generation path
- migrate `checkpoint_spacing` ownership to `TraversalStridePolicy`, keeping only one temporary symmetric compatibility adapter during rollout
- replace any planner-to-checkpoint assumptions with explicit route-plan and traversal-execution-step ownership

This migration phase is necessary to preserve DRY ownership and avoid “same concept, different seam” drift.

## Phase 1: Define Canonical Viewport/Stride Ownership

### Changes

- add one canonical `TraversalStridePolicy` model at the request/pattern layer,
- add one canonical `WorldMapViewportStrideProfile` that supplies reviewed default horizontal and vertical stride values,
- route all traversal patterns through the same shared stride-policy seam,
- preserve explicit request/authored stride overrides.

### Rules

- do not leave stride ownership split across request fields and pattern-local parameters,
- do not scatter viewport-sized defaults through traversal implementations,
- do not weaken explicit request/authored overrides.

### Expected Outcome

All traversal patterns consume one canonical stride-policy surface before any pattern reshaping begins.

## Phase 2: Define Route Segment Intent And Domain-Owned Row Helpers

### Changes

- add one explicit `TraversalSegmentIntent` model or equivalent typed seam,
- add one explicit `WorldMapTraversalRoutePlan` model or equivalent typed seam,
- add one explicit `WorldMapTraversalExecutionPlanner` layer between route planning and low-level action planning,
- make row-based routes emit local-traverse vs non-local-reset intent explicitly,
- add one domain/traversal-owned helper for addressable row sampling,
- add one domain/traversal-owned helper for addressable coordinates on a row in either direction,
- reuse those helpers from both row-major and serpentine route generation.

### Rules

- do not let movement primitives leak into traversal planning,
- do not collapse route geometry planning and route compilation into one class,
- do not let row-reset semantics remain implicit,
- no duplicated row/addressability helpers,
- no feature-local row sampling logic,
- fail fast on impossible row requests.

### Expected Outcome

Traversal semantics, route compilation, and primitive execution are separated cleanly before the pattern set expands.

## Phase 3: Make Broad Traversal Patterns Explicit

### Changes

- add `SERPENTINE_ROW_SWEEP` to `WorldMapSearchPatternKind`,
- add `WorldMapSearchPattern.serpentine_row_sweep()`,
- route the reviewed row, ring, and perimeter patterns through `WorldMapTraversalPlanner`,
- migrate existing edge-band callers to the reviewed perimeter patterns and remove `EDGE_BAND_SWEEP`,
- keep all emitted checkpoint generation under traversal/domain ownership.

### Rules

- do not hide serpentine behavior inside `ROW_MAJOR_SWEEP`,
- do not reintroduce pattern-local stride fields,
- do not let tasks/features implement ad hoc sweep loops,
- do not duplicate route-shape logic outside the traversal planner/domain seam.

### Expected Outcome

Broad full-map castle search can express the reviewed pattern families explicitly and readably.

## Phase 4: Introduce Explicit Movement-Proof Observation Scope

### Changes

- extend `ObservationRequest` with one explicit world-map movement-proof request or equivalent canonical scope,
- ensure that this scope is narrower than full checkpoint-analysis needs,
- update direct world-map movement to use it intentionally,
- enforce the settled-viewport no-double-capture contract,
- preserve fail-fast retry behavior when movement proof cannot resolve a usable world-map coordinate.

### Rules

- no duplicate observation builders,
- no duplicate coordinate OCR/parser path,
- no duplicate settled-viewport capture for proof plus analysis,
- no ad hoc movement-only parser outside the canonical coordinate extraction path.

### Expected Outcome

Movement proof becomes intentionally cheap without forking the observation architecture.

## Phase 5: Introduce Traverse vs Fine-Correction Policy

### Changes

- add one explicit world-map movement policy model that includes:
  - gesture primitive,
  - correction threshold,
  - traverse-vs-correction selection,
  - optionally separate reviewed defaults for traverse and correction.

- keep `WorldMapNavigator` as the canonical low-level action emitter,
- let `WorldMapCoordinateMover` choose the active movement mode from remaining delta.

### Rules

- do not scatter near-target predicates across tools or tests,
- do not duplicate correction-threshold logic in multiple layers,
- fail fast on invalid policy combinations.

### Expected Outcome

Broad travel stops behaving like permanent micro-correction, while final landing remains precise.

## Phase 6: Make Search Stride Coverage-Driven

### Changes

- review broad-search callers and live tools that still treat checkpoint spacing as arbitrary movement size,
- migrate request/pattern callers toward the canonical `TraversalStridePolicy`,
- define broad sweep stride in terms of viewport-sized progression by default, with explicit custom overrides,
- keep one canonical stride-policy seam across symmetric and axis-specific patterns,
- retire the temporary symmetric `checkpoint_spacing` compatibility bridge once callers are migrated,
- document reviewed defaults for broad sweep use cases.

### Rules

- no duplicate stride owner for the same concept,
- no hidden task-local stride translation,
- keep stride meaning tied to analyzed viewport progression.

### Expected Outcome

Broad search becomes auditable in terms of viewport coverage instead of arbitrary coordinate churn.

## Phase 7: Keep Full Checkpoint Analysis Only At Intended Analyzed Viewports

### Changes

- preserve `WorldMapSurveyRecorder.record_checkpoint(...)` and full ingestion architecture,
- ensure the richer checkpoint-analysis path runs only when the system intentionally stops at the next analyzed viewport,
- keep survey indexing and match collection unchanged in ownership.

### Rules

- no duplicate search-checkpoint analysis helper outside the recorder/search boundary,
- no second hidden analysis pipeline.

### Expected Outcome

The system remains DRY and coverage-correct while paying full analysis cost only where it matters.

## Phase 8: Introduce Explicit Diagnostics Persistence Policy

### Changes

- extend the shared diagnostics subsystem to support:
  - immediate logging mode,
  - buffered-per-sequence logging mode.

- extend the shared observation-artifact policy surface so persisted sweep/search flows can use selective screenshot persistence cleanly.

- keep `LIGHT` mode unchanged as the no-routine-persistence mode,
- keep failure screenshot persistence immediate,
- persist routine screenshots only for:
  - selected analyzed checkpoints,
  - explicit end-of-sequence summaries,
  - failures.

- have world-map movement/search/observation flows consume these shared defaults by default instead of inventing tool-local behavior.

### Rules

- do not make each tool invent its own buffering behavior,
- do not move logging ownership into world-map modules,
- do not weaken failure diagnostics,
- do not break current consumers that rely on persisted artifacts for failure paths,
- do not treat selective persisted sweep mode as a replacement for `LIGHT`.

### Expected Outcome

Broad sweeps stop writing every intermediate movement-proof screenshot while preserving the checkpoints and failures that actually matter.

## Phase 9: Recognition Coverage Audit

Before trusting broad live not-found results, add one explicit recognition-audit slice.

### Audit Goals

- confirm visible castles are indexed correctly after traversal changes,
- verify self-castle labeling, alliance-tagged castles, kingdom/id-only labels, and wrapped/multi-line labels,
- distinguish:
  - traversal issue,
  - movement issue,
  - coordinate-proof issue,
  - recognition issue.

### Suggested Offline Coverage

- castle-only viewport with self, ally, and other castles,
- wrapped castle-name viewport,
- mixed viewport with castle, alliance building, monster, and resource node,
- neutral-object viewport for altar, dragonia, and hell fortress,
- noise-heavy viewport where unrelated OCR should not create false objects.

### Suggested Live Coverage

- bounded dense survey,
- screenshot vs indexed-sighting comparison,
- explicit list of false positives, false negatives, and unsupported-but-visible object types.

### Expected Outcome

Recognition gaps become explicit rather than being mistaken for traversal failures.

## Phase 10: Dry-Run And Live Debug Tooling

Add or reuse one live-safe route-preview tool that:

- proves world map,
- resolves the planned route,
- prints the first `N` checkpoints,
- prints row transitions,
- prints the last `N` checkpoints,
- optionally executes only the first bounded portion.

This must exist before broad live player searches so route shape can be audited before a full sweep.

## Fail-Fast Validation Requirements

The improved design must reject:

- non-positive checkpoint spacing,
- non-positive movement granularity,
- movement granularity less than or equal to focus tolerance,
- invalid traverse/correction thresholds,
- invalid gesture primitive values,
- impossible row/rectangle requests with no addressable coordinate,
- invalid authored combinations that imply no usable movement behavior.

Error messages must remain specific and actionable.

## Testing Plan

### Offline Tests

Add or extend focused tests for:

- dedicated route-planner unit coverage at the geometry layer, separate from broad search-service tests,
- dedicated traversal-execution-planner unit coverage for step envelope generation,
- dedicated traversal-action-planner unit coverage for action-family-to-low-level-action translation,
- small serpentine rectangular route behavior,
- top-row endpoint behavior:
  - include `(0, 0)` and `(510, 0)`
  - exclude `(511, 0)`
- lower-left endpoint behavior:
  - include `(0, 1022)`
  - exclude `(0, 1023)`
- checkerboard parity for emitted checkpoints,
- non-addressable single-coordinate boundary fail-fast behavior,
- movement-proof observation scope behavior,
- default viewport-stride profile resolution and override behavior,
- `TraversalStridePolicy` symmetric vs axis-specific resolution behavior,
- route segment intent emission for row-major vs serpentine transitions,
- route geometry / polyline planning behavior,
- traversal execution-step planning from route geometry,
- traverse-vs-correction handoff,
- preservation of full checkpoint ingestion at analyzed checkpoints,
- immediate vs buffered logging policy behavior,
- selective screenshot persistence behavior for analyzed checkpoints vs intermediate movement proof,
- fail-fast invalid movement-policy validation,
- gesture primitive propagation through the movement policy.

### Live Validation

Use existing live calibration and comparison tooling to validate:

- movement proof remains reliable,
- broad traversal uses fewer correction-style legs,
- checkpoint progression reflects viewport stride policy,
- perimeter and expanding-ring patterns consume the same canonical stride-policy model as row-based patterns,
- reviewed default horizontal and vertical viewport stride values are validated live before becoming canonical defaults,
- full checkpoint analysis still finds castles at intended analyzed viewports,
- selective persistence writes only the intended analyzed checkpoints plus sequence summaries while still preserving failures,
- horizontal and vertical movement are both validated live, not just horizontal movement,
- both positive and negative Y travel are validated live,
- vertical boundary-stop behavior is validated live,
- route preview is auditable before broad execution.

### Timing Validation

Record and compare:

- drag execution time,
- movement-proof time,
- checkpoint-analysis time,
- total time per analyzed viewport.

The primary metric should be analyzed-viewport throughput, not just single-leg timing.

## Current Apply Order

Recommended implementation order:

1. define canonical viewport/stride ownership,
2. define route segment intent and centralize row/addressable helpers,
3. add and reshape the traversal patterns,
4. introduce explicit movement-proof observation scope,
5. introduce traverse-vs-correction movement policy,
6. make broad sweep stride coverage-driven,
7. preserve full checkpoint analysis only at intended analyzed viewports,
8. introduce explicit diagnostics persistence policy,
9. add recognition audit coverage,
10. add dry-run/preview tooling,
11. perform bounded live validation before broader live search.

Practical exception:

- if one current live movement bug prevents even bounded row validation, fix that blocker first under the same canonical movement stack, then resume this plan.

## Acceptance Criteria

- there is exactly one canonical implementation of serpentine traversal,
- there is exactly one canonical traversal-stride policy surface across all patterns,
- `EDGE_BAND_SWEEP` and the temporary `checkpoint_spacing`-only ownership path are removed after migration,
- `ROW_MAJOR_SWEEP` and `SERPENTINE_ROW_SWEEP` have distinct documented semantics,
- `ROW_MAJOR_SWEEP` expresses left-to-right rows with explicit non-local row-reset intent,
- `SERPENTINE_ROW_SWEEP` expresses alternating row direction with local row transitions,
- route generation never emits impossible coordinate pairs,
- route planning emits explicit segment intent where row-transition semantics differ,
- one canonical route planner produces ordered route geometry / polylines from the high-level pattern,
- one canonical execution planner translates route geometry into executable traversal steps,
- movement proof and checkpoint analysis are intentionally separated in scope,
- the same settled viewport is not captured twice just to satisfy both proof and analysis,
- diagnostics persistence is explicit:
  - `LIGHT` remains unchanged,
  - routine persisted sweep mode is selective,
  - failures remain immediate,
  - logs support immediate and buffered sequence modes,
- broad traversal and fine correction are explicit policy concepts,
- checkpoint spacing clearly means analyzed viewport stride,
- default search progression is one horizontal or vertical viewport unless the caller overrides it,
- reviewed default viewport stride values come from one canonical shared profile,
- checkpoint analysis still runs exactly once per intended analyzed viewport,
- recognition coverage assumptions for castle search are explicit,
- route preview is auditable before broad live execution,
- the test pyramid includes focused route-planner and execution-planner unit coverage below service-level search tests,
- no task or feature owns a custom parallel sweep loop.

## Final Recommendation

Proceed with one narrow, architecture-preserving refinement path:

- keep frame-based search coverage,
- keep one canonical observation system,
- keep one canonical movement stack,
- make traversal shape explicit,
- make movement proof cheap,
- make broad traversal broad,
- make correction near-target only,
- make checkpoint spacing mean viewport coverage stride again,
- keep recognition gaps visible rather than hidden.

This is the cleanest way to improve world-map search correctness, auditability, and throughput while staying DRY, fail-fast, and well integrated with the current codebase.
