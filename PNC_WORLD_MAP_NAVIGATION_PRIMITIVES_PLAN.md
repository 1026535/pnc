# PNC World-Map Navigation Primitives Plan

## Purpose

Define the missing low-level navigation primitives needed by world-map search:

- coordinate-dialog movement through the in-game magnifier/search UI,
- full-map overview parsing and optional overview-assisted positioning.

This plan is separate from:

- `PNC_WORLD_MAP_SEARCH_SUBPLAN.md`, which owns search requests, matching, checkpoint loops, and result semantics,
- `PNC_WORLD_MAP_SEARCH_PATTERN_DEBUG_PLAN.md`, which owns traversal order such as serpentine sweep,
- movement calibration work, which owns swipe behavior after the viewport is already on the world map.

The search service should consume these primitives, not implement selector choreography inline.

## Current State

The code already has placeholder owners:

- `WorldMapCoordinateNavigator`
  - `is_supported()` returns a configured flag,
  - `plan_jump(...)` currently raises `SelectorResolutionError`.
- `WorldMapOverviewNavigator`
  - `is_supported()` returns a configured flag,
  - `resolve_world_bounds(...)` currently raises `SelectorResolutionError`.

The request model can already express movement preferences such as `COORDINATE_JUMP` and `OVERVIEW_SEED`, but the default runtime cannot satisfy them yet.

## Coordinate-Dialog Navigation

### Required UI Knowledge

To make `WorldMapCoordinateNavigator` supported, the implementation needs reliable selectors or OCR anchors for:

- opening the world-map coordinate/magnifier dialog from the world-map root,
- the kingdom input field if the dialog requires kingdom,
- the X input field,
- the Y input field,
- field-clear behavior for each editable field,
- the `Go` / search / confirm button,
- the dialog close/back behavior after invalid input or cancellation,
- the transient invalid-coordinate status banner.

### Required Behavior

`WorldMapCoordinateNavigator` should:

1. require a proven `PNC_WORLD_MAP` observation,
2. open the coordinate dialog,
3. fill the target kingdom/X/Y fields through typed field selectors,
4. submit the dialog,
5. observe the post-submit frame,
6. fail fast if the invalid-coordinate banner appears,
7. prove the result is `PNC_WORLD_MAP`,
8. verify the viewport coordinate is near the normalized addressable target.

The navigator must not treat "actions executed" as proof of movement. The proof is the parsed post-submit world-map coordinate.

### Coordinate-Domain Interaction

Coordinate-dialog input should use `WorldMapCoordinateDomain` explicitly:

- reject truly out-of-domain coordinates before typing,
- normalize in-domain but unaddressable coordinate pairs to the addressable target the game accepts,
- compare the result against the normalized target, not the raw requested pair.

This depends on fixing the current `nearest_addressable(...)` clamping behavior so out-of-domain points do not silently snap to map edges.

## Full-Map Overview Navigation

### Required UI Knowledge

To make `WorldMapOverviewNavigator` supported, the implementation needs reliable selectors or OCR/vision anchors for:

- opening the full-map overview from the world-map root,
- closing the overview back to the same world-map context,
- identifying the current viewport marker,
- reading or inferring map bounds,
- optionally tapping/dragging the overview marker if live testing proves it reliable.

### Required Behavior

`WorldMapOverviewNavigator` should:

1. require a proven world-map observation,
2. open the overview,
3. parse map bounds and current viewport context,
4. optionally perform one overview-assisted repositioning if that interaction is proven live-stable,
5. close or return to a proven `PNC_WORLD_MAP` observation,
6. fail fast when overview evidence is ambiguous.

Overview support should initially focus on bounds/context extraction. Overview-assisted movement should be added only after live validation proves the UI interaction is stable.

## Search-Service Integration

After the primitives exist:

- `WorldMapSearchService._select_movement_tool(...)` can safely choose `COORDINATE_JUMP` or `OVERVIEW_SEED` when the runtime supports them,
- `_move_with_coordinate_jump(...)` must verify the resulting viewport coordinate before checkpoint ingestion,
- full-map searches can use coordinate jump or overview parsing to seed the start coordinate,
- traversal patterns remain owned by the traversal planner.

Search should not own the UI steps for opening dialogs or parsing overview state.

## Tests

Required unit coverage:

- coordinate jump rejects out-of-domain raw targets,
- coordinate jump normalizes in-domain unaddressable target pairs,
- coordinate jump fails when `plan_jump(...)` returns no actions and the viewport is not already at target,
- coordinate jump fails when post-submit observation is not world map,
- coordinate jump fails when the status banner reports invalid coordinates,
- coordinate jump succeeds only when the resulting viewport is near the normalized target,
- overview navigator fails fast while unsupported,
- overview bounds parsing succeeds from a synthetic proven overview fixture once selectors exist.

Required live validation:

- open and close the coordinate dialog without changing map state,
- jump to several known addressable coordinates,
- enter known unaddressable but in-domain pairs and verify the normalized result,
- attempt one out-of-domain coordinate and verify fail-fast handling,
- open overview and record the parsed current viewport marker/bounds,
- close overview and prove the world-map surface again.

## Recommendation

This should be addressed as its own plan before broad full-map search depends on these tools.

The current implementation-review finding should stay as a dependency warning only. The actual design and validation work belongs here because coordinate-dialog and overview behavior are reusable world-map navigation primitives, not search-loop behavior.
