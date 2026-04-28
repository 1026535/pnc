# PNC World-Map Navigation Primitives Plan

## Purpose

Define the missing low-level navigation primitives needed by world-map search:

- coordinate-dialog movement through the in-game magnifier/search UI,
- full-map overview parsing and optional overview-assisted positioning.

This plan is separate from:

- `reviewed_plans/PNC_WORLD_MAP_SEARCH_SUBPLAN.md`, which owns search requests, matching, checkpoint loops, and result semantics,
- `PNC_WORLD_MAP_SEARCH_PATTERN_DEBUG_PLAN.md`, which owns traversal order such as serpentine sweep,
- movement calibration work, which owns swipe behavior after the viewport is already on the world map.

The search service should consume these primitives, not implement selector choreography inline.

## Target Architecture Fit

These primitives sit below `WorldMapSearchService` and beside the existing swipe-based `WorldMapCoordinateMover`. They are map-local world-map capabilities, not screen-flow routes.

Canonical ownership should stay as follows:

- `ScreenFlowPlanner` owns only entering world map, proving world-map readiness, and returning to home city.
- `WorldMapCoordinateMover` owns calibrated swipe movement inside an already-open world map.
- `WorldMapCoordinateNavigator` owns the coordinate-dialog action choreography and target normalization needed to build one jump request.
- `WorldMapOverviewNavigator` owns full-map overview action choreography and overview evidence parsing.
- `WorldMapSearchService` owns movement-tool selection, action execution, post-action observation, checkpoint verification, checkpoint ingestion, matching, and stop-policy evaluation.
- `WorldMapTraversalPlanner` owns checkpoint route generation and must remain the only owner of traversal order.

The primitive navigators should produce declarative action plans and typed parsed evidence. They should not introduce a second observe-execute loop, a second search loop, or task-local navigation shortcuts. If the classes later move to a `world_map_navigation_primitives.py` module, the implementation should be moved, not copied, so there remains one canonical implementation per concept.

Fixed overlay and dialog controls belong in the existing selector/catalog system. World-map scene objects remain spatial objects. The plan must not add selector ids for castles, resources, or other scrollable map content.

## Current State

The code already has placeholder owners:

- `WorldMapCoordinateNavigator`
  - `is_supported()` returns a configured flag,
  - `plan_jump(...)` currently raises `SelectorResolutionError`.
- `WorldMapOverviewNavigator`
  - `is_supported()` returns a configured flag,
  - `resolve_world_bounds(...)` currently raises `SelectorResolutionError`.

The request model can already express movement preferences such as `COORDINATE_JUMP` and `OVERVIEW_SEED`, but the default runtime cannot satisfy them yet.

`WorldMapCoordinateDomain.nearest_addressable_in_bounds(...)` now fails fast for out-of-domain coordinates and only normalizes in-domain unaddressable coordinate pairs. New primitive work must use that method and must not reintroduce a clamp-first "nearest addressable" path for point targets.

## Coordinate-Dialog Navigation

### Required UI Knowledge

To make `WorldMapCoordinateNavigator` supported, the implementation needs reliable selectors or OCR anchors for:

- opening the world-map coordinate/magnifier dialog from the world-map root by tapping the small magnifier beside the viewport coordinate bar,
- the kingdom input field,
- the X input field,
- the Y input field,
- numeric keyboard entry and commit behavior for each editable field,
- the `Go` button,
- the top-right close/cancel X,
- the transient invalid-coordinate status banner.

Evidence from the world-map root confirms the coordinate-dialog opener is the magnifier immediately next to the visible viewport coordinate. The tutorial icon can be present or absent without changing this requirement. The bottom-left magnifier opens a different world-map function and must not be used for coordinate-dialog navigation.

Evidence from the opened coordinate dialog confirms there are three editable fields labeled `K:`, `X:`, and `Y:`. On open, `K` defaults to the active castle's current kingdom, while `X` and `Y` default to the current viewport center coordinate. The kingdom field would allow viewing the same `X,Y` coordinate in another kingdom, but cross-kingdom coordinate jumps are out of scope for this plan; the implementation should document and OCR the field while preserving the current/default kingdom value.

Evidence from focused fields confirms all three fields use numeric keyboard entry. Tapping a field clears the committed value from the dialog box while the prior value remains visible in the keyboard input area as gray text until replaced. After typing the desired numeric value, the keyboard `OK` / enter action must be pressed to commit the input, close the keyboard, and render the new value in the dialog box. Filling X/Y should therefore be modeled as a precise focus -> type -> keyboard commit sequence for each field, not as a single blind text action followed by `Go`.

The numeric keyboard appears at the bottom of the screen, with the commit `OK` action presented in the keyboard input-entry strip. That bottom keyboard presentation should be treated as the normal editing layout.

Evidence from filled dialogs confirms the committed state is the same coordinate dialog with new numeric values rendered in the `K`, `X`, and `Y` boxes. No secondary confirmation screen appears, and the `Go` button remains the submit action. This means a pre-submit proof can validate that the intended values are visible in the same dialog before pressing `Go`.

The top-right `X` is the close/cancel control. Closing the dialog returns to the world map with the viewport centered on the original coordinate. Pressing `Go` closes the dialog and returns to the normal `PNC_WORLD_MAP` surface with the coordinate bar showing the designated `K,X,Y` coordinate as the viewport center.

Live boundary evidence also clarifies the two post-`Go` outcomes. Truly out-of-domain input leaves the dialog open and renders the inline red error text `Please enter valid coordinates`. In-domain but unaddressable input closes the dialog like a normal success and moves the viewport to the nearest valid coordinate accepted by the game.

When the inline invalid-coordinate error is present, the dialog is not locked. The `K`, `X`, and `Y` fields remain editable, so recovery can happen in-place by entering a valid coordinate and pressing `Go`, or by abandoning the attempt with the top-right `X`.

Live editing evidence also shows that a persistent partially-filled dialog is effectively impossible in the normal flow. If the keyboard-entry state is closed without committing a new value, the field reverts to its previously committed coordinate. The dialog therefore should be modeled in terms of committed values only, not as a stable screen with missing coordinate parts.

### Required Behavior

`WorldMapCoordinateNavigator` should:

1. require a proven `PNC_WORLD_MAP` observation,
2. validate the raw target with `WorldMapCoordinateDomain.require_inside_bounds(...)`,
3. normalize the target with `nearest_addressable_in_bounds(...)`,
4. produce the declarative actions that open the coordinate dialog,
5. preserve the current/default kingdom field and reject cross-kingdom jump requests until cross-kingdom behavior is intentionally supported,
6. fill the target X/Y fields through typed field selectors,
7. commit each numeric field with the keyboard `OK` / enter action before moving to the next field,
8. submit the dialog with the `Go` button and an action-scoped follow-up request,
9. expose the normalized target that the search service must verify after execution.

`WorldMapSearchService._move_with_coordinate_jump(...)` should remain responsible for executing those actions, observing the post-submit frame, detecting an invalid-coordinate status banner, proving the result is `PNC_WORLD_MAP`, and verifying that the parsed viewport coordinate is near the normalized addressable target.

The post-`Go` success proof is just the normal world-map coordinate bar parsed from the returned viewport. There is no distinct success dialog or extra confirmation state to model.

If execution observes the inline invalid-coordinate dialog state, the primitive should treat it as a recoverable editing state, not as a closed terminal screen. The runtime may either fail fast immediately with the visible error text or allow a bounded same-dialog correction path, but it must not misclassify that state as a successful close/cancel path.

Because uncommitted edits revert when the keyboard-entry state closes, the primitive does not need a dedicated runtime path for a stable partially-filled coordinate dialog.

If `plan_jump(...) -> list[ActionRequest]` becomes too weak to carry normalized-target, cleanup, or follow-up-proof metadata, replace it with one typed jump-plan dataclass and migrate callers. Do not add a parallel legacy-compatible API.

No layer may treat "actions executed" as proof of movement. The proof is the parsed post-submit world-map coordinate.

### Coordinate-Domain Interaction

Coordinate-dialog input should use `WorldMapCoordinateDomain` explicitly:

- reject truly out-of-domain coordinates before typing,
- normalize in-domain but unaddressable coordinate pairs to the addressable target the game accepts,
- compare the result against the normalized target, not the raw requested pair.

This uses the already-corrected `nearest_addressable_in_bounds(...)` behavior. Out-of-domain points must fail before typing. In-domain unaddressable pairs may be typed when live evidence proves the game normalizes them consistently, but verification must compare against the normalized target.

Current live evidence replaces the earlier speculative corner examples:

- `511,0` is in bounds but not directly addressable and normalized live to `510,0`,
- `511,2` normalized live to `510,2`,
- `0,1023` normalized live to `0,1022`,
- `512,1` and `0,1024` were rejected as invalid,
- `507,1090` was rejected as invalid because the Y coordinate is out of bounds.

This suggests the game first preserves legal in-bounds coordinates and then snaps to a nearby parity-valid tile, often by adjusting X when that is sufficient. That X-first preference is an evidence-backed hypothesis, not yet a fully proven global rule. The implementation should therefore treat the runtime normalization examples as fixtures to match, while keeping the normalization helper isolated and easy to revise if more edge cases disprove the current hypothesis.

No explicit loading screen was observed for coordinate-jump or overview-close transitions. If any transition exists, it is effectively instantaneous at human timescales. The runtime should therefore model these actions as immediate post-action re-observation rather than introducing a dedicated loading-screen state.

## Full-Map Overview Navigation

### Required UI Knowledge

To make `WorldMapOverviewNavigator` supported, the implementation needs reliable selectors or OCR/vision anchors for:

- opening the full-map overview from the world-map root,
- closing the overview back to the same world-map context,
- identifying the current viewport marker,
- reading or inferring map bounds,
- optionally tapping/dragging the overview marker if live testing proves it reliable.

Live world-map evidence confirms the overview opener is an always-visible world-map icon in the lower-left area. Its exact pixel position can shift with tutorial-completion state, but it remains visible on the world map and should be modeled through selectors resilient to that small layout variation rather than through hard-coded absolute pixels.

Live overview-open evidence confirms the overview header contains:

- the kingdom number and name, for example `K:157 Shadow Realm`,
- ruler information,
- kingdom status text.

The main body is a large map representation. Blue dots mark alliance-member castle locations. Separate artifact-holder castle icons are also shown. The bottom controls include:

- a world/kingdom-list control on the left,
- a legend control in the center,
- a visibility-toggle control on the right.

On open, alliance-member and artifact visibility are enabled by default, while resource visibility is disabled by default.

Live overview calibration evidence from the map corners and one interior point shows that the yellow viewport marker simply moves within the overview map as the world-map viewport changes. That marker motion is the primary evidence for overview-to-world correspondence.

The earlier assumption about the left bottom control was wrong: it does not return to the world map. It opens the `Kingdom List` screen.

Live close-path evidence now shows three distinct overview interactions:

- tapping the top-right `X` closes the overview and returns to the original world-map viewport,
- tapping somewhere on the overview map closes the overview and recenters the world-map viewport on the clicked overview location,
- tapping the left world icon opens the kingdom-list screen rather than closing back to world map.

Live follow-up evidence indicates the overview does not expose a separate movable tap/drag viewport mode beyond simple map-click recentering. The yellow viewport marker reflects the current viewport, but the overview itself cannot be panned into an independent reposition state for this feature slice.

### Required Behavior

`WorldMapOverviewNavigator` should:

1. require a proven world-map observation,
2. produce the declarative actions that open the overview,
3. parse map bounds and current viewport context from overview evidence,
4. distinguish between the three overview exits:
   - top-right `X` close,
   - map-click reposition-and-close,
   - left world-icon kingdom-list navigation,
5. produce the declarative actions needed for close-in-place and, when intended, map-click repositioning,
6. avoid modeling a separate drag-to-move overview viewport mechanic unless new evidence disproves the current live behavior,
7. fail fast when overview evidence is ambiguous.

Overview support should focus on bounds/context extraction plus click-to-recenter semantics. A separate drag-based overview movement path should not be implemented unless later live evidence shows a distinct supported interaction.

Do not set `WorldMapOverviewNavigator.is_supported()` in a way that lets `WorldMapSearchService._select_movement_tool(...)` choose `OVERVIEW_SEED` until `_move_with_overview_seed(...)` can actually execute and verify a movement or seed operation. Parse-only overview bounds support can land first, but it must not masquerade as an implemented movement tool.

If overview parsing lands before overview movement, split the capability model into explicit parse-bounds support and movement-seed support instead of overloading one `supported` flag.

## Search-Service Integration

After the primitives exist:

- `WorldMapSearchService._select_movement_tool(...)` can safely choose `COORDINATE_JUMP` only when coordinate-dialog planning, execution, and landing verification are all implemented,
- `WorldMapSearchService._select_movement_tool(...)` can safely choose `OVERVIEW_SEED` only when overview-assisted seeding has a verified runtime path,
- `_move_with_coordinate_jump(...)` must verify the resulting viewport coordinate before checkpoint ingestion,
- full-map searches can use coordinate jump to seed the start coordinate and parse-only overview support to resolve full-map boundaries/context,
- traversal patterns remain owned by the traversal planner.

Search should not own the UI steps for opening dialogs or parsing overview state. It should own the runtime loop that executes a primitive action plan, obtains the follow-up observation, validates the landing/context, records the checkpoint, and evaluates the matcher.

## Tests

Required unit coverage:

- coordinate jump rejects out-of-domain raw targets,
- coordinate jump normalizes in-domain unaddressable target pairs,
- coordinate jump action planning uses one canonical selector sequence instead of probing multiple field names or control variants,
- coordinate jump action planning commits each edited numeric field through keyboard `OK` / enter before pressing `Go`,
- coordinate jump can prove the filled dialog state by reading committed `K/X/Y` values before pressing `Go`,
- coordinate jump normalizes `511,0 -> 510,0`, `511,2 -> 510,2`, and `0,1023 -> 0,1022` from live fixtures,
- coordinate jump fails when `plan_jump(...)` returns no actions and the viewport is not already at target,
- coordinate jump fails when post-submit observation is not world map,
- coordinate jump surfaces `Please enter valid coordinates` and keeps the dialog open for out-of-domain requests such as `512,1`, `0,1024`, or `507,1090`,
- coordinate jump relies only on committed field values because uncommitted partial edits revert when the keyboard-entry state closes,
- coordinate jump fails when the status banner reports invalid coordinates,
- coordinate jump succeeds only when the resulting viewport is near the normalized target,
- overview navigator fails fast while unsupported,
- parse-only overview bounds support does not enable `OVERVIEW_SEED`,
- overview bounds parsing succeeds from a synthetic proven overview fixture once selectors exist,
- overview marker calibration uses known-corner and interior fixtures,
- overview `X` close returns to the original viewport,
- overview map-click closes and recenters to the clicked coordinate,
- overview left world icon opens kingdom list and must not be treated as return-to-map,
- overview does not expose a distinct movable drag/seed viewport interaction beyond click-to-recenter based on current live evidence,
- screen-flow tests continue to prove that world-map entry/readiness/exit stay in `ScreenFlowPlanner`, not in these primitives.

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
