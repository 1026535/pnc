# PNC World-Map Navigation Primitives Implementation Review

## Scope

Reviewed commit `63f16eca93e63913c39a14c2a9cfb34d5e2ddba0` (`Complete world map navigation primitives`) against:

- `reviewed_plans/PNC_WORLD_MAP_NAVIGATION_PRIMITIVES_PLAN.md`
- the touched navigation, vision, selector, and test modules in the commit

Validation run during this review:

- `py -3.13 -m unittest discover -s tests`
- Result: `680` tests passed, `13` skipped

## Findings

### 1. Overview projection math is off by one at the right and bottom edges

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_overview_projection.py:18-30`
  - `pnc_automation/app/pnc/navigation/world_map_overview_projection.py:42-52`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:2190-2196`
  - `tests/test_world_map_search.py:495-506`
- Problem:
  - The projection helpers treat `Bounds.width` and `Bounds.height` like inclusive max coordinates instead of pixel spans.
  - For a `Bounds(x=0, y=0, width=200, height=200)` region, the current code projects the maximum world coordinate to `(200, 200)`, which is one pixel outside the actual crop/tap region `0..199`.
  - The reverse projection has the same problem: `(199, 199)` maps back to `(508, 1018)` instead of the maximum world coordinate, while the out-of-bounds point `(200, 200)` is accepted and maps to `(511, 1023)`.
  - `_bounds_contains_point(...)` masks the bug by also treating `x + width` and `y + height` as inside.
  - The new unit test currently codifies the invalid edge point by asserting `(200, 0)` as a valid recenter tap target.
- Why it matters:
  - Overview recenter taps can land outside the intended click region at the far right/bottom edges.
  - Marker parsing systematically under-reports near the maximum edges unless an out-of-bounds point is injected.
  - This is exactly the kind of bug that passes synthetic tests and then causes flaky live edge behavior.
- Clean fix:
  - Treat `Bounds.width` and `Bounds.height` as spans, not inclusive maxima.
  - Use `(width - 1)` / `(height - 1)` when mapping inclusive world-coordinate ranges onto pixel coordinates, with a safe single-pixel fallback when the span is `1`.
  - Change point containment checks to `< bounds.x + bounds.width` and `< bounds.y + bounds.height`.
  - Update the affected tests so maximum taps stay inside the region, and add round-trip regressions for the bottom-right edge.

### 2. Overview-assisted movement is still not implemented end to end

- Severity: Medium
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1165-1172`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1810-1821`
- Problem:
  - The commit adds overview parsing and `plan_recenter(...)`, but the actual search runtime path is still a stub.
  - `WorldMapOverviewNavigator.is_supported()` remains `False` by default because `movement_supported` is still `False`.
  - `WorldMapSearchService._move_with_overview_seed(...)` still raises `SelectorResolutionError` unconditionally.
- Why it matters:
  - The plan explicitly scoped overview-assisted positioning as part of these primitives.
  - The code now has a partially implemented overview primitive surface, but the search service still cannot execute or verify any overview-seed movement.
  - As written, the commit is not actually "complete" for the overview movement portion of the plan.
- Clean fix:
  - Either finish the overview movement path end to end:
  - `open overview`
  - `parse context`
  - `recenter through the dedicated click region`
  - `re-observe world map`
  - `verify landing against the normalized target`
  - Or explicitly narrow the scope to "parse-only overview support" and remove the complete/fully-implemented claim until the runtime path exists.
  - Add runtime-facing tests for `_move_with_overview_seed(...)` once the path exists.

### 3. Parse-only overview bounds support is still coupled to marker extraction

- Severity: Medium
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1241-1244`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1257-1283`
- Problem:
  - `resolve_world_bounds(...)` delegates directly to `parse_context(...)`.
  - `parse_context(...)` hard-fails unless `PNC_WORLD_OVERVIEW_VIEWPORT_MARKER` is visible and inside the calibrated map region.
  - That means the new `supports_bounds_parsing()` capability is not actually independent of marker detection.
- Why it matters:
  - One flaky marker-detection frame now prevents even plain bounds resolution, despite the capability split that was introduced to keep parse-only support separate from movement support.
  - This couples two different concepts:
  - "Can we read or know the overview bounds?"
  - "Can we locate the current viewport marker right now?"
- Clean fix:
  - Split the API into two canonical operations:
  - `resolve_world_bounds(...)` or `parse_bounds(...)`
  - `parse_viewport_context(...)` or equivalent marker-aware parsing
  - Keep `WorldMapOverviewContext` marker fields optional if one shared return type is preferred.
  - Add tests proving bounds can still resolve when the marker is absent, and separate tests for marker-required context parsing.

### 4. Overview-open and coordinate-jump planning are stricter than the new request model requires

- Severity: Low
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1068-1071`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1182-1190`
  - `pnc_automation/app/pnc/vision/observation_request.py:123-134`
- Problem:
  - `WorldMapCoordinateNavigator.plan_jump(...)` always requires a parsed current viewport coordinate just to detect the no-op case.
  - `WorldMapOverviewNavigator.plan_open(...)` always requires a parsed current viewport coordinate even though `ObservationRequest.world_map_overview_follow_up(...)` explicitly makes the coordinate hint optional.
  - Both actions fundamentally only need a proven world-map surface; the current-coordinate read is an optimization or hint, not a hard prerequisite.
- Why it matters:
  - The primitives now fail earlier than necessary when the world-map surface is proven but the coordinate bar is temporarily unreadable.
  - That weakens the reusability of the primitives and makes the new optional hint path effectively mandatory from one important call site.
- Clean fix:
  - Make the current-coordinate dependency opportunistic:
  - `plan_jump(...)` should skip the no-op optimization when the viewport coordinate is absent and still build the dialog plan.
  - `plan_open(...)` should pass `expected_coordinate=None` when the current coordinate is not available.
  - Add focused tests for "proven world map, missing coordinate parse" on both primitives.

### 5. Coordinate-dialog numeric-field parsing is duplicated

- Severity: Low
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:2169-2187`
  - `pnc_automation/app/pnc/vision/pnc_observation_enricher.py:2708-2722`
- Problem:
  - The same "extract the first integer from coordinate-dialog field text, with special handling for kingdom" rule now exists in two places.
  - One copy is used while enriching OCR field state, and another copy is used later while proving the committed dialog state.
- Why it matters:
  - The feature just introduced one more duplicated parser for the same domain concept, which increases drift risk the next time OCR edge cases are tuned.
  - This is exactly the kind of small duplication that quietly creates inconsistent runtime behavior over time.
- Clean fix:
  - Move this parsing rule into one canonical helper or typed dialog-state parser and reuse it from both the enricher and the navigation proof path.
  - Add one shared regression set for blank text, labeled values, and invalid kingdom values.

## Recommended Fix Order

1. Fix the overview projection math and the corresponding edge tests first, because this can produce wrong live taps and wrong marker coordinates even when the rest of the flow is correct.
2. Decide whether overview-assisted movement is truly part of the completed scope. Either finish `_move_with_overview_seed(...)` or explicitly narrow the implementation claim.
3. Decouple parse-only overview bounds support from marker extraction so the new capability split is real.
4. Relax the unnecessary current-coordinate prerequisite for overview open and coordinate jump planning.
5. Deduplicate the coordinate-dialog field parser while touching the primitive code again.

## DRY Checklist

- Overview projection currently has one canonical implementation, but it is mathematically wrong at the inclusive edges.
- Overview parse capability and marker parsing are still coupled and should be separated into clear owners.
- Coordinate-dialog numeric parsing is duplicated and should be centralized.
- The screen-flow unwind path for coordinate dialog, overview, and kingdom list is nicely centralized in `ScreenFlowPlanner`.
