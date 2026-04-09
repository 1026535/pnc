# Step 4.6: Puzzles & Conquest World-Map Search Sub-Plan

## 1. Purpose

This document defines the canonical architecture for searching within the already-open world map.

It is intentionally separate from:

- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which should own only screen-to-screen navigation such as Home City to World Map or World Map to Campaign,
- [PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_SURFACE_SUBPLAN.md), which owns the world-map spatial observation model,
- [PNC_SPATIAL_MAP_LOGGING_AND_ARTIFACT_POLICY_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_MAP_LOGGING_AND_ARTIFACT_POLICY_SUBPLAN.md), which owns routine artifact/debug persistence policy,
- [PNC_MARCH_MANAGEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_MARCH_MANAGEMENT_SUBPLAN.md), which should consume map search instead of redefining it,
- [PNC_RELICS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_RELICS_SUBPLAN.md), which may later consume the same precise world-map search capabilities.

This file owns the missing layer between:

- getting onto the world map,
- moving the world-map viewport,
- sampling and indexing visible map state,
- and resolving a requested castle or precise world-map object.

## 2. Context

The current architecture now has the core ingredients needed for world-map search, but not yet the correct ownership model or the full search design.

What now exists:

- the world map can be classified and its coordinate bar parsed,
- `SpatialSurfaceObservation` can represent world-map viewport state and visible spatial objects,
- `WorldMapSurveyIndex` and `WorldMapSurveyRecorder` can accumulate repeated checkpoint observations,
- `WorldMapCastleQuery` can express one high-level castle lookup against indexed sightings,
- the spatial navigator can already perform one coordinate-driven swipe increment.

Recent live testing also clarified two different user needs that must not be conflated:

- a local proximity scan around the player territory,
- and a broader search for a castle or other exact world-map target that may now be anywhere because of relocation or random porting.

The local 3x3 survey loop that now works is useful, but it answers only the first need. It is not a sufficient solution for finding a random-ported player.

The live debugging also exposed an architectural boundary that should now be made explicit:

- entering or leaving the world map is a screen-flow concern,
- moving the viewport by one swipe inside the world map is not a screen transition and should not be modeled as one.

That distinction is fundamental. A single swipe inside `PNC_WORLD_MAP` is spatial traversal, not reusable cross-screen flow.

## 2.1 Implementation Status As Of 2026-04-08

The architecture in this document is now partially implemented.

Implemented so far:

- a runner-owned task preflight contract now exists in the automation engine:
  - tasks can declare a required entry state through `TaskPreflight`,
  - the runner now owns the canonical `observe -> popup recovery -> navigate -> prove required screen` loop before the task body starts,
  - this moved root-entry ownership out of the task body for tasks that truly start from a stable root.
- the first task migrations to runner-owned preflight are complete:
  - `ResearchTask` now declares runner-owned `HOME_CITY` preflight,
  - `GatheringTask` now declares runner-owned `WORLD_MAP` preflight.
- coarse root-state classifications now exist instead of routing every incomplete root frame through `UNKNOWN`:
  - `PNC_HOME_CITY_ROOT`
  - `PNC_WORLD_MAP_ROOT`
- the screen-classification pipeline now reconciles coarse and exact root evidence correctly:
  - exact selector proof still wins,
  - compatible coarse+exact evidence collapses to the exact screen,
  - incompatible evidence still fails fast to `UNKNOWN`.
- the recurring live unknown artifact at:
  - [20260408T172223Z_mega_old_acc_post_prep_world_start.png](/c:/Users/lebel/pnc/artifacts/2026-04-08/mega_old_acc/20260408T172223Z_mega_old_acc_post_prep_world_start.png)
  is now recognized as world-map-root-like evidence rather than remaining generic `UNKNOWN`.
- screen flows now explicitly refine coarse roots into exact proofs:
  - coarse home-city root is re-observed into exact `PNC_HOME_CITY`,
  - coarse world-map root is re-observed into exact `PNC_WORLD_MAP`.
- home-city/world-map readiness handling is now more graceful when the root screen is correct but the parsed spatial surface is temporarily missing:
  - world-map readiness already refreshes transient parse misses,
  - home-city object-opening flows now also request one bounded surface refresh instead of failing immediately.

Implemented only partially:

- shared runner-owned preflight is in place, but not every task has been migrated to it yet.
- the migration was intentionally limited to tasks whose body truly starts from a root screen.
- tasks with meaningful in-progress subflows or resumable non-root screens still retain local ownership of those subflow boundaries.

Intentionally not migrated yet:

- `BuildingUpgradeTask`
- `OpenBuildingTask`

Reason:

- those tasks do not always begin from a stable root.
- they can legitimately resume from owned in-progress screens such as building-detail or building-owned screens.
- forcing unconditional home-city preflight on those tasks caused real end-to-end regressions and was therefore reverted.

Still remaining from the broader workflow simplification direction:

- extend runner-owned preflight coverage to additional tasks whose entry contract is truly root-owned,
- keep shrinking repeated task-local root-entry logic where the task body does not need to resume from owned subflow screens,
- continue adding coarse root or popup classifications for repeated live `UNKNOWN` artifacts instead of weakening exact classification.

## 2.2 World-Map Movement Calibration Status As Of 2026-04-08

The low-level world-map swipe path was also refined significantly during live validation.

Implemented so far:

- world-map movement is no longer using one shared generic swipe ratio for every axis.
- the navigator now supports axis-specific swipe calibration:
  - horizontal span is calibrated independently,
  - vertical span is calibrated independently,
  - diagonal movement uses the horizontal and vertical spans together instead of forcing decomposition through cardinals.
- the world-map movement planner now carries independent horizontal and vertical ratio state through replans instead of treating every swipe as one scalar distance.
- movement validation also hardened failure behavior:
  - tiny OCR jitter is no longer accepted as real map movement,
  - stagnant-swipe attempts are tracked across replans,
  - the movement loop fails cleanly instead of pretending the viewport advanced.
- world-map follow-up observation handling was hardened so narrow post-swipe observations can retry once with broader runtime observation when the frame looks transient or under-classified.

Live calibration findings gathered so far:

- vertical movement became live-stable and repeatable in the probes that were run.
- horizontal movement was narrowed from a broader `+4` to `+6` band toward a tighter smaller quantum.
- explicit left-swipe calibration on `mega_old_acc` showed:
  - ratio `0.08` -> exact `(+4, 0)`
  - ratio `0.10` -> exact `(+4, 0)`
  - ratio `0.12` -> exact `(+6, 0)`
- those live measurements were used to refactor the world-map planner to prefer a smaller horizontal default span.
- all eight directions were validated as directionally working during live probing:
  - left
  - right
  - up
  - down
  - up-left
  - up-right
  - down-left
  - down-right

Current implementation state:

- directional world-map movement is now materially more reliable,
- diagonal movement is first-class in the navigator,
- the planner is much closer to deterministic displacement than before,
- but exact "`same call` always yields the exact same `(a, b)` displacement" is still not fully proven for every direction and distance.

What is proven:

- the movement system now has a canonical calibration model rather than one hard-coded generic swipe profile,
- the runtime can distinguish real movement from OCR noise,
- coarse recovery after swipe follow-up misclassification is substantially better than before,
- vertical motion and several short calibrated horizontal probes behaved deterministically in live testing.

What is not yet fully proven:

- exact deterministic displacement for all horizontal distances,
- exact deterministic displacement for all diagonals over longer runs,
- long uninterrupted movement runs on unstable live accounts without popup or state churn interfering.

Practical consequence for the search architecture:

- the search layer now has a much better low-level movement primitive to build on,
- but full-map sweep correctness still depends on continued live validation of the movement primitive, especially for long row-major traversal and long diagonal repositioning.

## 2.3 Additional Implemented Changes Already Landed

This section records other important world-map-search-related changes that were implemented during debugging and refactoring, but were not yet documented above.

### 2.3.1 World-map detection correctness fixes

The world-map detector was corrected so home-city or unrelated OCR text no longer falsely satisfies world-map selectors.

Implemented fixes:

- OCR-region selector matching was tightened so world-map selectors require the intended text semantics rather than accepting arbitrary OCR text inside the crop.
- `PNC_WORLD_HOME_NAV` now requires actual `HOME` text semantics.
- `PNC_WORLD_COORDINATE_BAR` now requires real `X:` and `Y:` coordinate semantics.

Practical consequence:

- frames like Lord Info, player pages, or city-owned overlays that happened to contain unrelated OCR are no longer misclassified as `PNC_WORLD_MAP` just because text existed inside a selector crop.

### 2.3.2 Search ownership correction for world-map entry

The search layer itself no longer owns world-map entry.

Implemented change:

- `execute_search(...)` now requires a caller-provided or freshly captured proven `PNC_WORLD_MAP` observation with a parsed spatial surface.
- if the caller starts from Home City, popup, or any non-proven state, the search fails fast instead of silently taking over root navigation.

Architectural consequence:

- entering world map remains a higher-level screen-flow or runner-preflight concern,
- the search engine now assumes it is operating inside an already-proven world-map session.

### 2.3.3 Castle search and matching corrections

The castle-matching model was corrected to align with actual map-label semantics discovered during live debugging.

Implemented fixes:

- castle matching by `player_name` now stays map-label-based rather than treating profile inspection as an independent naming system,
- self-castle enrichment for remote player-name search was blocked because `My Territory` is a self-only label and must not become a general player-name candidate,
- non-self profile enrichment is now constrained so it cannot blindly override visible castle-label semantics,
- a separate profile-validation path was introduced for future profile/gear checks.

Current profile-validation status:

- opening the lord profile for validation is supported as a distinct search path,
- gear validation itself is still intentionally unimplemented and fails fast once the profile is open.

### 2.3.4 Stop-policy semantics correction

The search stop-policy behavior was corrected during debugging.

Implemented outcome:

- `FIRST_CONFIRMED_MATCH` is still valid,
- but search correctness now depends on preventing incorrect candidates from ever becoming confirmed matches,
- the earlier stop-policy precedence experiment was reverted once it became clear that the deeper issue was candidate eligibility and castle-label semantics, not the stop trigger itself.

### 2.3.5 World-map search service and canonical indexing work

The reusable world-map search subsystem itself was implemented as a shared canonical surface.

Implemented components:

- a canonical `world_map_search.py` service layer,
- request / matcher / stop-policy / traversal-plan modeling,
- one canonical checkpointed search loop over the shared world-map survey index,
- canonical world-map survey/index integration rather than feature-local object caches,
- world-map search integration into the runtime and gathering consumer.

Architectural consequence:

- world-map-local search behavior is now centered in the dedicated search subsystem rather than being split across feature-local loops.

### 2.3.6 Canonical world-map/local-operation boundary cleanup

The boundary between screen flows and map-local operations was tightened.

Implemented direction:

- world-map-local querying and interaction logic was pulled away from the screen-flow surface,
- screen flows remain responsible for root transitions such as opening world map or returning to home city,
- map-local traversal and object interaction remain below the search layer.

This remains an active architecture direction, but the key ownership split is now materially better than before.

### 2.3.7 Unknown-state and recovery hardening

The runtime’s error-handling and unknown-state behavior was improved substantially to avoid dangerous churn.

Implemented fixes:

- ambiguous `UNKNOWN` states no longer fall through to Android Home plus relaunch behavior,
- unknown recovery is now bounded and in-game-first,
- root chrome on `UNKNOWN` prefers safe re-observe rather than blind back-navigation,
- popup handling continues to run through the shared popup-recovery loop,
- world-map and home-city follow-up observations now get one broad-runtime retry when a narrow request returns transient `UNKNOWN` or an under-classified frame.

Practical consequence:

- the runtime is much less likely to spiral into shop / launcher / app-close churn,
- ambiguous in-game states now fail or re-observe conservatively instead of taking destructive recovery paths.

### 2.3.8 Home-city/world-map readiness refinement

Root-screen readiness now distinguishes:

- exact root classification,
- coarse root classification,
- and root classification with missing parsed spatial surface.

Implemented outcome:

- exact root proof remains the goal before root-owned task work begins,
- coarse root proof now routes into a bounded exact re-proof step,
- missing root spatial surfaces now request bounded refresh instead of crashing immediate consumers.

### 2.3.9 Search-origin and sweep-direction observations from live review

Live review clarified expectations for broad sweeps:

- full-map sweep should start from a corner,
- the intended broad traversal is row-major coverage,
- upper-left is treated as `(0, 0)`,
- likely world bounds are finite and should ultimately come from the higher-level map rather than blind edge-probing.

Current implementation state:

- the row-major/full-sweep intent is now clearly recognized as the target behavior,
- but automatic full-bound resolution from the high-level map is still not implemented and remains future work.

### 2.3.10 Known remaining gaps after the implemented work

The following important items are still not fully complete:

- exact overview/high-level-map bounds extraction for full-map sweep,
- fully proven deterministic displacement for every world-map movement direction and run length,
- implemented castle gear validation after opening a player profile,
- full migration of every root-owned task to runner preflight,
- complete live stabilization on popup-heavy or state-unstable accounts during long search runs.

## 3. Problem Statement

The project currently risks mixing three different responsibilities:

- `screen entry`: switching between Home City, World Map, Campaign, and other screens,
- `viewport traversal`: swiping the world-map camera while remaining on the same screen,
- `search intent`: deciding what to look for, where to search, how broadly to search, and when to stop.

If those responsibilities remain mixed, the design will drift toward duplicated feature-local logic:

- one task will implement a "scan nearby" loop,
- another will implement a "find castle anywhere" loop,
- another will implement its own "find relic/resource/fortress" loop,
- and all of them will re-describe traversal, checkpoint capture, and index lookup differently.

That would violate the core architecture requirements:

- one canonical implementation per concept,
- no duplicated logic,
- fail-fast validation,
- minimal boilerplate.

## 3.1 Current Architecture Flaws To Address Explicitly

The plan should explicitly track the concrete ownership flaws already visible in the current runtime, so they are not lost in the more general target design.

Current flaws:

- `focus_world_coordinate(...)` currently lives on the screen-flow surface even though it performs in-screen viewport traversal rather than screen-to-screen navigation,
- `find_visible_world_object(...)` currently lives on the screen-flow surface even though visible object querying is a spatial-surface/search concern rather than a screen-flow concern,
- `open_visible_world_object(...)` currently lives on the screen-flow surface even though tapping one visible world object is spatial interaction, not reusable screen transition behavior,
- the current flow-planner surface therefore exposes both screen transitions and in-surface world-map operations, which weakens ownership clarity,
- the current architecture also risks pushing future search behavior into the flow planner because that surface already exposes world-map movement/query affordances.

Required refactor direction:

- keep `open_world_map()` and `ensure_world_map_ready()` as screen-flow responsibilities,
- move viewport traversal, visible-object query, and visible-object interaction behind dedicated spatial-navigation or world-map-search ownership,
- make the world-map search service the canonical entry point for higher-level search behavior so feature work does not keep reaching into the flow planner for map-local operations.

## 4. Scope

This sub-plan defines:

- the canonical distinction between world-map screen entry and world-map traversal,
- the canonical search request model for world-map targets,
- support for both proximity scans and broader exact-target searches,
- the canonical origin model for "scan around my territory",
- the traversal model for bounded-area and full-map sweeps,
- the search loop that combines movement, checkpoint capture, indexing, and target resolution,
- castle-specific candidate enrichment when visible labels alone are not enough.

This sub-plan does not define:

- the selector-registry evolution for unrelated screens,
- generic screenshot/artifact policy,
- feature-specific marching, relic interaction, or gathering business logic after the target has been found,
- native-code parsing or threading optimizations as the primary first step.

## 5. Core Architectural Decision

The canonical ownership split should be:

### 5.1 Screen flow

Screen flow owns only transitions between distinct screens.

Examples:

- `ensure_home_city()`
- `open_world_map()`
- `return_home_city_from_world_map()`
- `open_campaign()`

Screen flow should not own:

- sweeping the world map,
- planning repeated coordinate checkpoints,
- deciding scan radius,
- deciding whether to search locally or globally,
- or deciding when to inspect candidate castles.

### 5.2 Spatial navigation

Spatial navigation owns one movement increment inside an already-active spatial surface.

Examples:

- one coordinate-driven swipe toward a world-map checkpoint,
- one tap on one visible spatial object,
- later, one atlas-guided movement increment inside Home City.

This is where a single world-map swipe belongs.

### 5.3 World-map search

World-map search owns:

- translating a search request into a traversal plan,
- resolving the search origin when needed,
- capturing and indexing checkpoints,
- checking whether the target is already visible or already indexed,
- escalating to castle candidate inspection when required,
- deciding when the search succeeded, exhausted, or failed.

This should be one canonical higher-level service, not duplicated per feature.

## 6. Vision

The target design should expose one generic world-map search functionality.

Consumers should provide parameters, not choose between different top-level workflows.

That one search engine should accept:

- what to match,
- when to stop,
- where the search originates,
- what area or boundary is allowed,
- what traversal pattern to use,
- and which low-level movement tools the engine may use.

This should support requests such as:

- "Find one Hell Fortress of level 30 within radius `R` from my territory."
- "Find up to 20 resource nodes of level 6 and stop when 20 are found."
- "Find up to 30 unaffiliated castles within a bounded area."
- "Find the castle of player `X`, even if they random ported."
- "Sweep outward from `(0, 0)`."
- "Search only within an edge band near the map boundary."

The consuming feature should not need to know:

- how checkpoint coordinates are generated,
- how the viewport is moved between checkpoints,
- whether the engine uses swipes, coordinate jump, or overview-map assistance,
- how repeated observations are indexed,
- how search termination is decided,
- or how castle candidate enrichment is applied.

## 7. Functional Requirements

The solution must be one generic search engine, with the following parameterized capabilities.

### 7.1 Generic matcher support

The engine must accept general and specific search criteria through one canonical matcher seam.

Examples:

- Hell Fortress of level 30,
- resource node of level 6,
- castles with no alliance,
- castle of player `X`,
- composed criteria such as "castle AND unaffiliated AND level >= N" once that evidence exists canonically.

### 7.2 Stop-condition support

The engine must support explicit stop conditions rather than assuming every search is "find one thing".

Required stop controls:

- stop after the first confirmed match,
- stop after `N` matches,
- stop when the allowed search boundary is exhausted,
- stop when the allowed radius is exhausted,
- optionally stop after a maximum checkpoint budget when the caller wants a bounded search effort.

This is what turns a local radius-bounded search into the same engine as a broad survey.

### 7.3 Pattern support

Traversal pattern must be a parameter, not a separate API.

Required pattern families:

- row-major sweep:
  - left to right, then next row, then continue top to bottom,
- expanding sweep:
  - expand outward from the origin until the stop policy is satisfied or the boundary is exhausted,
- center sweep:
  - a configured sweep around an explicit center such as `(0, 0)` or another provided coordinate,
- edge sweep:
  - traverse only a band near one or more map edges.

Different search behaviors should be expressed as combinations of the same engine plus different patterns.

### 7.4 Origin support

Search origin must also be a parameter.

Required origin behavior:

- if no origin is provided, default to `My Territory`,
- allow explicit coordinates,
- allow current viewport when the caller truly wants viewport-relative behavior,
- allow map-derived locators such as upper-left corner or specific edge reference when the traversal pattern needs them.

### 7.5 Result support

The engine must support plural results, not only a single match.

Required result behavior:

- return zero, one, or many matches,
- preserve the order in which matches were found unless a later ranking step is explicitly applied,
- expose why the search stopped,
- expose enough indexed/search context for the caller to understand coverage and next steps.

## 8. Non-Functional Requirements

The design must satisfy the following architecture rules.

### 8.1 One canonical search engine

There must be exactly one world-map search loop for:

- checkpoint generation,
- viewport movement,
- checkpoint capture,
- survey-index ingestion,
- matcher evaluation,
- and stop-condition evaluation.

Proximity scan, broad survey, exact castle search, center sweep, and edge sweep must be configurations of this same engine.

### 8.2 One canonical index

`WorldMapSurveyIndex` must remain the one canonical accumulated map-state store.

No task should keep a second ad hoc castle map, object cache, or local candidate list that duplicates indexed state.

### 8.3 One canonical matcher interface

The engine should support typed filters, functor-style matching, and compositions of matchers, but through one canonical matcher interface.

That means:

- do not create one search path for `SpatialObjectQuery`,
- another search path for `WorldMapCastleQuery`,
- and a third ad hoc path for custom lambdas.

Instead, adapt them into one canonical matcher contract and let composition happen there.

### 8.4 Fail-fast inputs

Search requests must reject:

- missing matcher content,
- invalid or negative radii,
- zero or negative checkpoint spacing,
- invalid edge-band widths,
- contradictory origin and pattern combinations,
- full-map or edge-based requests when map bounds cannot be resolved,
- stop policies that request zero matches or otherwise invalid limits.

### 8.5 Correctness before throughput

This slice should prioritize:

- correct ownership,
- correct matcher semantics,
- correct origin resolution,
- correct traversal semantics,
- and correct search termination.

Performance tuning remains important, but it should optimize the canonical search engine after the architecture is correct.

### 8.6 Future partitioned-search extensibility

The current plan should not implement quadrant splitting, dichotomic search, or multi-agent map partitioning yet.

However, the architecture should remain open to that later extension without reshaping the core public model.

Required design guardrails:

- search boundary and traversal pattern must remain explicit data, so later partitioning can assign sub-boundaries without inventing a second search contract,
- the canonical search request must be serializable/sliceable into smaller equivalent requests,
- search results must remain mergeable because later partitioned search may combine results from multiple independently searched subregions,
- the canonical index must remain the single accumulated world-map state owner even if later execution uses partitioned or parallel traversal,
- low-level movement primitives must stay below the search layer so future partitioned execution can reuse them without changing search semantics.

## 9. Canonical Search Model

The design should add one high-level request model rather than exposing raw loops directly to features.

Recommended types:

- `WorldMapSearchRequest`
- `WorldMapSearchMatcher`
- `WorldMapSearchStopPolicy`
- `WorldMapSearchPattern`
- `WorldMapSearchOrigin`
- `WorldMapSearchBoundary`
- `WorldMapSearchResult`
- `WorldMapTraversalCheckpoint`

### 9.1 `WorldMapSearchRequest`

This request should own:

- the matcher,
- the stop policy,
- the traversal pattern,
- the origin,
- the allowed search boundary,
- checkpoint spacing or stride,
- optional castle-enrichment policy,
- optional movement-tool preferences.

Recommended request shape:

- one required `matcher`,
- one required `stop_policy`,
- one required `pattern`,
- one optional `origin` that defaults to `My Territory` when the pattern needs an origin and the caller did not provide one,
- one optional `boundary`,
- one required positive checkpoint spacing value,
- optional low-level movement preferences.

The request must not force callers into separate "proximity" or "full survey" APIs.

### 9.2 `WorldMapSearchMatcher`

This should be the canonical filter/functor seam used by the engine.

Recommended responsibilities:

- evaluate visible spatial objects,
- evaluate indexed sightings,
- support castle-specific identity matching when required,
- support composition.

Recommended matcher forms:

- adapter from `SpatialObjectQuery`,
- adapter from `WorldMapCastleQuery`,
- composite matchers such as `all_of(...)`, `any_of(...)`, and `not_(...)`,
- optional callable adapter for bounded experimentation when a typed matcher does not yet exist.

The important rule is that composition should happen through the canonical matcher seam, not through parallel search APIs.

### 9.3 `WorldMapSearchStopPolicy`

This type should make search termination explicit.

Recommended fields:

- `max_matches`,
- optional `max_radius_units`,
- optional `max_checkpoints`,
- optional `stop_on_first_confirmed_match`,
- optional `stop_when_boundary_exhausted` behavior when not implied by the boundary itself.

Most current search needs are just different stop-policy configurations:

- proximity scan:
  - radius-bounded stop policy,
- resource collection search:
  - stop after `N` matches,
- exact castle search:
  - stop on first confirmed match or full-coverage exhaustion.

### 9.4 `WorldMapSearchPattern`

Traversal shape should be explicit and reusable.

Recommended patterns:

- `ROW_MAJOR_SWEEP`
- `EXPANDING_RING`
- `EDGE_BAND_SWEEP`

Examples:

- local left-to-right, top-to-bottom radius scan:
  - `ROW_MAJOR_SWEEP` around a self-territory origin plus a radius boundary,
- outward search from my territory:
  - `EXPANDING_RING` around a self-territory origin,
- full-map search:
  - `ROW_MAJOR_SWEEP` with a full-map boundary and an upper-left start coordinate,
- center sweep around `(0, 0)`:
  - `EXPANDING_RING` or `ROW_MAJOR_SWEEP` with explicit origin `(0, 0)`,
- edge search:
  - `EDGE_BAND_SWEEP` with an edge-band boundary.

### 9.5 `WorldMapSearchOrigin`

Origin should be explicit when the pattern needs one.

Recommended origin kinds:

- `SELF_TERRITORY`
- `CURRENT_VIEWPORT`
- `EXPLICIT_COORDINATE`
- `MAP_CORNER`
- `MAP_EDGE_REFERENCE`

Default rule:

- if the caller omits origin, use `SELF_TERRITORY` unless the pattern explicitly requires another origin kind.

### 9.6 `WorldMapSearchBoundary`

Boundary should define where the engine is allowed to search.

Recommended boundary kinds:

- `FULL_MAP`
- `RADIUS_FROM_ORIGIN`
- `RECTANGLE`
- `EDGE_BAND`

This keeps the distinction clear:

- the pattern defines visitation order,
- the boundary defines allowed coverage,
- the stop policy defines when the search ends.

This also keeps the design open for future partitioning:

- a full-map boundary can later be split into quadrant or sub-rectangle boundaries,
- each partition can still be searched through the same request/matcher/pattern model,
- and merged results can still flow back through the same canonical result/index ownership.

### 9.7 `WorldMapSearchResult`

The result should expose:

- `matches`,
- `stop_reason`,
- `visited_checkpoints`,
- `coverage_boundary`,
- whether castle-profile enrichment was used,
- and enough access to the canonical index state for follow-up work.

Consumers should not need to reinterpret raw survey checkpoints to understand what was found and why the search stopped.

## 10. Low-Level World-Map Navigation Capabilities

The generic search engine should be allowed to use lower-level world-map movement helpers when appropriate.

These helpers are not separate search workflows. They are movement primitives used by the same search owner.

### 10.1 Coordinate navigation

Coordinate navigation through the `K/X/Y` input dialog should be treated as a low-level world-map movement primitive.

Recommended owner:

- `WorldMapCoordinateNavigator`

Recommended responsibilities:

- open the coordinate input dialog,
- fill kingdom and coordinate fields,
- press `Go`,
- verify that the resulting viewport moved to the intended coordinate within accepted tolerance.

The higher-level search engine may use this:

- to seed the start of a sweep,
- to reposition efficiently between far-apart checkpoints,
- or to jump directly to known candidate coordinates.

### 10.2 Full-map overview

The full-map overview showing the whole kingdom and the orange viewport marker should also be treated as a low-level helper.

Recommended owner:

- `WorldMapOverviewNavigator`

Recommended responsibilities:

- open and close the overview,
- parse enough state to understand map bounds, current viewport position, and edge-relative context,
- optionally use overview interaction to seed or confirm traversal start positions if the live UI supports it reliably.

This is especially relevant for:

- full-map sweeps,
- upper-left or edge-based origins,
- edge-band searches,
- and future optimizations that want better global positioning context.

## 11. Traversal and Pattern Planning

All search patterns should reuse one traversal planner.

Recommended owner:

- `WorldMapTraversalPlanner`

Recommended responsibilities:

- convert a `WorldMapSearchRequest` into an ordered sequence of checkpoint coordinates,
- resolve origin plus boundary plus pattern into one deterministic route,
- keep route-generation rules independent from screenshot capture and matching logic,
- support pattern-specific traversal without splitting into separate search services.

Examples:

- proximity sweep:
  - `ROW_MAJOR_SWEEP` plus `RADIUS_FROM_ORIGIN` boundary around `SELF_TERRITORY`,
- expanding local search:
  - `EXPANDING_RING` plus `RADIUS_FROM_ORIGIN`,
- full survey:
  - `ROW_MAJOR_SWEEP` plus `FULL_MAP`, starting from `MAP_CORNER(upper_left)`,
- center sweep:
  - `EXPANDING_RING` around `EXPLICIT_COORDINATE(0, 0)`,
- edge sweep:
  - `EDGE_BAND_SWEEP` plus `EDGE_BAND` boundary.

## 12. Search Loop

The world-map search engine should own one canonical end-to-end loop.

Recommended owner:

- `WorldMapSearchService`

Recommended loop:

1. ensure the runtime is on a world-map screen through the reusable screen flow,
2. resolve the origin, boundary, and start coordinate required by the request,
3. optionally use coordinate navigation or overview-map helpers to reach the intended start position,
4. build the checkpoint route from the request,
5. at each checkpoint:
   - move toward the checkpoint through the allowed low-level movement primitive,
   - capture one observation/checkpoint through the shared observation service,
   - ingest the observation into `WorldMapSurveyRecorder` / `WorldMapSurveyIndex`,
   - evaluate the matcher against the current visible surface,
   - evaluate the matcher against the accumulated index,
   - accumulate confirmed matches,
   - if needed, escalate to castle candidate inspection,
   - evaluate the stop policy,
6. stop when:
   - the stop policy is satisfied,
   - the allowed boundary is exhausted,
   - the route is exhausted,
   - or the search encounters a fail-fast invalid state.

This is the single canonical implementation for all local, broad, center, and edge searches.

## 13. Query and Matching Ownership

Matching should stay close to the indexed/observed models rather than moving into task-local helpers.

Recommended ownership:

- visible generic object matching stays with `SpatialObjectQuery` and `DetectedSpatialObject.matches(...)`,
- indexed generic object lookup should be added to `WorldMapSurveyIndex`,
- castle-specific lookup continues to use `WorldMapCastleQuery`,
- the generic search engine consumes them through the canonical `WorldMapSearchMatcher` seam.

Recommended index expansion:

- add `find_object(...)` / `require_object(...)` style lookup for indexed spatial objects,
- keep `find_castle(...)` / `require_castle(...)` as the castle-specialized seam,
- do not build a separate "search-only" cache that bypasses the index.

## 14. Castle-Specific Candidate Inspection

Castle finding is a special case because visible castle labels may be unreliable or intentionally changed.

The search layer should therefore support optional castle enrichment after map-side surveying.

Recommended castle inspection flow:

1. survey and index visible castle candidates,
2. rank likely candidates using map-side evidence already present in the index,
3. open Lord Info only for those candidates,
4. annotate the indexed castle sighting with resolved player/profile evidence,
5. re-run the canonical castle query against the same index.

Map-side evidence may include:

- visible castle label,
- kingdom,
- alliance tag,
- castle level,
- indexed coordinate,
- route proximity or bounded-area membership.

Lord Info enrichment may later include:

- displayed lord name,
- hero lineup,
- gear and gem evidence,
- other high-confidence profile signals.

The critical rule is:

- there is still one canonical indexed castle sighting,
- and profile enrichment updates that sighting rather than creating a parallel candidate record type.

## 15. Ownership in Code

The implementation should converge on the following code ownership model.

### 15.1 Keep in screen flow

- `open_world_map()`
- `ensure_world_map_ready()`
- `return_home_city_from_world_map()`

These remain valid screen-flow responsibilities because they move between screens or guarantee screen readiness.

### 15.2 Keep in spatial navigation

- one coordinate-directed world-map swipe,
- one visible-object tap,
- any calibration needed to turn one target checkpoint into one movement increment.

### 15.3 Add low-level world-map navigation primitives

- coordinate-dialog open/fill/go behavior,
- full-map overview open/close/parse behavior,
- low-level verification that those helpers produced the intended repositioning context.

These are movement primitives used by higher-level search, not separate search workflows.

### 15.4 Keep in survey/index ownership

- checkpoint capture and ingestion,
- indexed map-state persistence,
- canonical query seams over accumulated sightings.

### 15.5 Add dedicated search ownership

Recommended new module(s):

- `pnc_automation/app/pnc/navigation/world_map_search.py`
- optionally `pnc_automation/app/pnc/navigation/world_map_traversal.py` if route planning becomes large enough to justify separation
- optionally `pnc_automation/app/pnc/navigation/world_map_navigation_primitives.py` if coordinate and overview helpers need one shared owner

Recommended responsibilities:

- search request validation,
- matcher adaptation/composition,
- stop-policy evaluation,
- origin and boundary resolution,
- traversal-pattern planning,
- search loop orchestration,
- low-level movement-tool selection,
- castle candidate inspection orchestration.

### 15.6 Refactor boundary note

`focus_world_coordinate(...)` currently appears on the flow planner surface, but its true responsibility is spatial traversal, not screen flow.

The implementation should therefore migrate toward one of these end states:

- remove `focus_world_coordinate(...)` from the canonical screen-flow contract and expose the movement/search behavior through dedicated search/spatial-navigation ownership, or
- keep a temporary delegating compatibility shim only during migration while making the dedicated search owner the canonical implementation.

The first option is cleaner and should be the target.

## 16. Relationship to Existing Plans

### 16.1 Relationship to screen flow

[PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md) should be updated conceptually by this document, not expanded to own viewport traversal.

World-map search should consume:

- `open_world_map()`
- `ensure_world_map_ready()`

It should not ask screen flow to own:

- repeated swipes,
- search radius,
- checkpoint routing,
- or search completion policy.

### 16.2 Relationship to spatial surface

[PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_SURFACE_SUBPLAN.md) remains the owner of:

- parsed viewport coordinates,
- visible spatial objects,
- self/ally/other relationship semantics,
- world-map scene interpretation.

This document consumes that model to search over it.

### 16.3 Relationship to artifact policy

[PNC_SPATIAL_MAP_LOGGING_AND_ARTIFACT_POLICY_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_MAP_LOGGING_AND_ARTIFACT_POLICY_SUBPLAN.md) remains the owner of routine artifact selection.

World-map search should accept artifact/debug policy through the existing runtime seams rather than inventing a second persistence toggle model.

### 16.4 Relationship to feature plans

Feature plans such as march management and relic work should consume this search layer instead of describing their own local scan loops.

Examples:

- march management may request a generic search with a self-territory origin, radius boundary, and row-major or expanding pattern,
- castle-finding workflows may request a full-map row-major sweep for a castle matcher,
- future relic/resource workflows may request an area or edge-band search for one spatial-object matcher.

## 17. Implementation Plan

The implementation should proceed in bounded increments.

### 17.1 Phase 1: Establish the ownership boundary

- add this canonical search sub-plan,
- treat world-map traversal as distinct from screen flow,
- introduce one dedicated search owner in code,
- keep screen flow limited to world-map entry/exit guarantees.

### 17.2 Phase 2: Add canonical search request and traversal planning

- introduce `WorldMapSearchRequest`, `WorldMapSearchMatcher`, `WorldMapSearchStopPolicy`, `WorldMapSearchPattern`, `WorldMapSearchOrigin`, and `WorldMapSearchBoundary`,
- implement strict validation,
- implement matcher adapters for `SpatialObjectQuery` and `WorldMapCastleQuery`,
- implement stop-policy evaluation,
- implement deterministic row-major, expanding-ring, and edge-band route planning.

### 17.3 Phase 3: Add low-level movement primitives

- add coordinate-dialog navigation as a low-level primitive,
- add overview-map navigation/parsing as a low-level primitive when the live UI proves it reliable,
- keep both owned below the generic search layer.

### 17.4 Phase 4: Unify checkpointed search loop

- integrate traversal planning with `WorldMapSurveyRecorder`,
- reuse the existing world-map navigator for per-checkpoint movement,
- allow the search engine to use coordinate navigation or overview seeding when the request or route benefits from it,
- add immediate visible-match and indexed-match checks after each checkpoint,
- define explicit termination conditions.

### 17.5 Phase 5: Expand indexed lookup for precise object search

- add generic indexed object lookup on top of `SpatialObjectQuery`,
- ensure castle lookup still reuses the same index,
- keep one canonical search result model.

### 17.6 Phase 6: Add castle candidate inspection

- define candidate ranking based on indexed map-side evidence,
- inspect only likely candidates,
- annotate the same indexed sighting with resolved profile evidence,
- re-query the same canonical index.

### 17.7 Phase 7: Feature integration

- update castle-finding consumers to use the new world-map search service,
- update proximity-scan consumers to request the generic search engine with self-territory default origin plus the requested boundary and pattern,
- delete any duplicated local survey loops once the shared engine exists.

## 18. Validation Gate

This sub-plan should not be considered implemented until the following evidence exists.

### 18.1 Unit tests

Required unit-test coverage:

- search-request validation,
- matcher and stop-policy invalid input rejection,
- origin-relative and explicit-origin route generation,
- row-major, expanding-ring, and edge-band route generation,
- fail-fast behavior when origin resolution is required but unavailable,
- coordinate-navigation request planning and validation,
- overview-helper request planning when supported,
- index lookup for generic spatial objects,
- castle lookup after profile enrichment.

### 18.2 Screenshot/integration tests

Required screenshot or observation-level coverage:

- world-map observations that expose `My Territory` / self relationship,
- generic search checkpoint ingestion around a resolved origin,
- row-major, expanding-ring, and edge-band boundary interpretation where the observation layer is involved,
- indexed lookup succeeding from accumulated survey state rather than only the currently visible frame.

### 18.3 Live smoke validation

Required live validation:

- one local self-territory search using a non-zero radius boundary,
- one search proving that repeated checkpoint movement actually covers the requested row-major route,
- one expanding search proving the engine can grow outward from its origin correctly,
- one broad search proving the engine can continue past the local neighborhood,
- one castle-search flow that can index candidates and stop cleanly when no match is found within the requested boundary and stop policy.

## 19. Out of Scope for the First Implementation

The following should remain explicitly out of scope for the first clean implementation slice:

- threaded screenshot parsing pipelines,
- Rust/C++ parser rewrites,
- quadrant splitting, dichotomic search, or multi-agent partitioned map search,
- aggressive performance tuning before the ownership model is correct,
- full visual gear/gem profile matching as the first castle-enrichment strategy,
- feature-specific march dispatch after a target is found.

Those may become later optimization or feature slices, but they should not distort the first clean canonical architecture.

## 20. Success Criteria

This sub-plan is successful when the codebase has one clean answer to each of the following questions:

- how do we search near the player territory?
- how do we search broadly for a relocated castle?
- how do we express what to match without inventing a new API for each use case?
- how do we express when to stop after `N` matches or after a radius is exhausted?
- how do we choose row-major, expanding, center, or edge traversal without changing the engine?
- where is the origin for a local scan defined and validated?
- who owns one world-map swipe?
- who owns checkpoint routing?
- who owns indexed accumulated world-map state?
- who owns castle candidate inspection?

And the answers should be:

- not the screen-flow layer for viewport traversal,
- not duplicated across feature plans,
- and not split across multiple ad hoc caches or search loops.
