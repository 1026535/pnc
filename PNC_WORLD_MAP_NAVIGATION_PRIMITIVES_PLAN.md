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

## Screenshot / Evidence Capture Plan

This section lists the screenshots needed to implement and validate:

- `WorldMapCoordinateNavigator`
- `WorldMapOverviewNavigator`

The goal is to capture enough stable UI evidence to add selectors, OCR anchors, validation logic, and tests without guessing field names or screen geometry.

### Capture Rules

- Capture from a proven `PNC_WORLD_MAP` state with the coordinate bar visible.
- Prefer at least two supported emulator resolutions if practical:
  - current primary live resolution,
  - smaller supported live resolution.
- Include OCR/debug dumps where possible, not screenshots only.
- Keep account/world context noted:
  - account id,
  - kingdom,
  - starting coordinate,
  - target coordinate typed,
  - expected normalized coordinate if the target is unaddressable.
- Use filenames that include the state and coordinate, for example:
  - `world_map_coordinate_dialog_closed_x230_y958.png`
  - `world_map_coordinate_dialog_open_empty.png`
  - `world_map_overview_open_x230_y958.png`

### Coordinate-Dialog Screenshots

#### 1. World Map Before Opening Coordinate Dialog

- Required: Yes
- Purpose:
  - prove the source world-map root state,
  - locate the button/anchor that opens the coordinate or magnifier dialog,
  - record the starting viewport coordinate.
- Desired evidence:
  - coordinate bar,
  - bottom nav,
  - coordinate/magnifier/search entry control,
  - no popup/dialog overlays.

#### 2. Coordinate Dialog Immediately After Opening

- Required: Yes
- Purpose:
  - identify the dialog container,
  - identify all editable fields,
  - identify labels for kingdom/X/Y if present,
  - identify close/cancel controls.
- Desired evidence:
  - empty/default kingdom field,
  - X field,
  - Y field,
  - `Go` / search / confirm button,
  - close button,
  - OCR lines for all labels.

#### 3. Coordinate Dialog With X Field Focused

- Required: Yes
- Purpose:
  - locate focused-field visual state,
  - confirm keyboard behavior,
  - identify whether field selection clears or appends text.
- Desired evidence:
  - focused X field,
  - on-screen keyboard if it appears,
  - cursor/focus styling,
  - any clear button attached to the field.

#### 4. Coordinate Dialog With Y Field Focused

- Required: Yes
- Purpose:
  - same as X focus, but proves Y field geometry independently.
- Desired evidence:
  - focused Y field,
  - on-screen keyboard if it appears,
  - cursor/focus styling,
  - any clear button attached to the field.

#### 5. Coordinate Dialog With Kingdom Field Focused

- Required: Conditional
- Capture if the dialog has a kingdom field.
- Purpose:
  - determine whether kingdom must be filled,
  - determine whether K prefix is visible/required,
  - identify field-clear and keyboard behavior.
- Desired evidence:
  - focused kingdom field,
  - existing/default kingdom value,
  - keyboard state.

#### 6. Coordinate Dialog Fully Filled With Addressable Target

- Required: Yes
- Purpose:
  - verify OCR sees the typed values,
  - identify submit/go button enabled state,
  - create a fixture for pre-submit validation.
- Suggested target:
  - one known addressable pair near current viewport, such as `(506, 1020)` if the account is near that area.
- Desired evidence:
  - typed X,
  - typed Y,
  - typed/default kingdom,
  - enabled submit/go button.

#### 7. Post-Go Success Result

- Required: Yes
- Purpose:
  - prove the expected post-submit world-map state,
  - verify the coordinate bar updates to the target coordinate,
  - identify any transient loading/transition frames if they appear.
- Desired evidence:
  - proven `PNC_WORLD_MAP`,
  - coordinate bar at target,
  - no lingering dialog,
  - any temporary status/animation if captured.

#### 8. Coordinate Dialog Filled With In-Domain Unaddressable Pair

- Required: Yes
- Purpose:
  - prove magnifier normalization behavior in fixtures,
  - confirm the target that the game actually accepts.
- Suggested targets:
  - `(507, 1020)` expected to normalize to `(506, 1020)`,
  - `(511, 0)` expected to normalize to `(511, 1)`,
  - `(0, 1023)` expected to normalize to `(0, 1022)`.
- Desired evidence:
  - dialog before submit with raw typed values,
  - post-submit coordinate bar with normalized target.

#### 9. Invalid Out-Of-Domain Coordinate Attempt

- Required: Yes
- Purpose:
  - identify invalid-coordinate banner text,
  - prove fail-fast handling,
  - distinguish out-of-domain rejection from in-domain normalization.
- Suggested targets:
  - `X=512, Y=0`,
  - `X=0, Y=1024`,
  - negative values if the UI allows typing them.
- Desired evidence:
  - typed invalid values,
  - post-submit invalid-coordinate banner,
  - whether dialog stays open or closes,
  - resulting screen type/state.

#### 10. Coordinate Dialog Close/Cancel

- Required: Yes
- Purpose:
  - implement cleanup after failed or aborted navigation,
  - prove return-to-world behavior.
- Desired evidence:
  - dialog open,
  - close/cancel control location,
  - world map after close with unchanged coordinate.

### Overview Screenshots

#### 11. World Map Before Opening Overview

- Required: Yes
- Purpose:
  - locate the overview/map button or control,
  - record current coordinate before overview.
- Desired evidence:
  - coordinate bar,
  - overview entry control,
  - bottom nav,
  - no overlays.

#### 12. Overview Immediately After Opening

- Required: Yes
- Purpose:
  - classify the overview state,
  - identify map bounds visuals,
  - identify the current viewport marker,
  - identify close/back controls.
- Desired evidence:
  - full kingdom map,
  - viewport marker,
  - edge/corner landmarks if any,
  - close button,
  - any coordinate labels or scale text.

#### 13. Overview At Several Known Viewport Coordinates

- Required: Yes
- Purpose:
  - calibrate marker position against world coordinates,
  - verify map-bound inference across the overview image.
- Suggested captures:
  - near upper-left normalized coordinate `(0, 0)`,
  - near upper-right normalized coordinate `(511, 1)`,
  - near lower-left normalized coordinate `(0, 1022)`,
  - near lower-right normalized coordinate `(511, 1023)` if addressable, otherwise nearest valid lower-right,
  - one central coordinate.
- Desired evidence:
  - overview marker position for each known coordinate,
  - same emulator resolution for all captures where possible,
  - corresponding pre-overview world-map coordinate.

#### 14. Overview Close/Back Result

- Required: Yes
- Purpose:
  - implement reliable return from overview,
  - prove overview cleanup returns to exact/proven world map.
- Desired evidence:
  - overview open with close/back visible,
  - post-close world map,
  - coordinate bar still parsed.

#### 15. Optional Overview Tap/Drag Reposition Attempt

- Required: Optional
- Capture only if live testing suggests overview interaction can move the viewport.
- Purpose:
  - decide whether `OVERVIEW_SEED` should support movement or only context/bounds parsing.
- Desired evidence:
  - overview before interaction,
  - tap/drag target point,
  - overview after interaction if it remains open,
  - returned world-map coordinate after close/go.

### Negative / Recovery Screenshots

#### 16. Coordinate Dialog With Keyboard Blocking Submit

- Required: Conditional
- Capture if keyboard appears and covers the submit/go button.
- Purpose:
  - plan keyboard dismissal or alternate submit behavior.
- Desired evidence:
  - focused field,
  - keyboard covering/not covering controls,
  - available confirm/done key.

#### 17. Coordinate Dialog With Partial Values

- Required: Conditional
- Purpose:
  - identify validation messages for missing X/Y/kingdom,
  - avoid misclassifying partial input as an invalid coordinate jump result.
- Desired evidence:
  - one missing field,
  - any disabled submit button,
  - any status/prompt after submit.

#### 18. Overview/Coordinate Dialog Under Popup Or Loading Churn

- Required: Conditional
- Capture only if seen during live use.
- Purpose:
  - preserve fail-fast/recovery boundaries,
  - avoid search primitives swallowing unexpected overlays.
- Desired evidence:
  - popup/loading overlay,
  - underlying dialog or overview if visible,
  - available close/retry controls.

### Minimum Screenshot Set

If time is limited, capture these first:

1. world map before coordinate dialog,
2. coordinate dialog open empty/default,
3. coordinate dialog filled with addressable target,
4. post-go success at that target,
5. coordinate dialog filled with `(507, 1020)`,
6. post-go normalized result for `(507, 1020)`,
7. invalid out-of-domain submit with status banner,
8. coordinate dialog close/cancel result,
9. world map before overview,
10. overview open at current coordinate,
11. overview close result.

### Output Expected From Capture Pass

For each screenshot, record:

- artifact path,
- account id,
- emulator resolution,
- starting coordinate,
- typed target coordinate if applicable,
- expected normalized target if applicable,
- observed post-action coordinate,
- OCR text dump path if available,
- notes about controls that were visually present but not OCR-detected.

This capture pass should unblock selector work without adding heuristic field probing.
