# PNC World-Map Search Implementation Review

## Scope

Reviewed commit `04f00b16ec91cf868ecb7232a6f9b60ed9008d56` (`Implement world map search coordinate model`) against:

- `PNC_WORLD_MAP_SEARCH_SUBPLAN.md`
- `PNC_WORLD_MAP_SEARCH_PARTIAL_REVIEW.md`
- the new live/debug plans added in the commit.

Targeted validation run during this review:

- `py -m unittest tests.test_world_map_search tests.test_capture_and_vision tests.test_world_map_movement_calibration tests.test_script_runner`
- Result: `128` tests passed.

## Partial Review Disposition

The commit fixes or materially addresses several items from `PNC_WORLD_MAP_SEARCH_PARTIAL_REVIEW.md`:

- Search traversal now uses the cardinal coordinate mover instead of relying on diagonal checkpoint travel.
- Checkpoint ingestion can now record the already-proven post-move observation through `WorldMapSurveyRecorder.record_checkpoint(...)`.
- `SELF_TERRITORY` origin no longer silently falls back to the viewport center when no self castle can provide a coordinate.
- Edge-band traversal now orders checkpoints from the resolved origin instead of fully ignoring it.
- `EnsureGameRunningTask` now has a combined unknown-recovery + launch-wait replan budget.
- Castle candidate focus now fails fast when no movement is planned but the candidate is still hidden.
- Runtime wiring for connected tooling and automation runner now shares `_build_connected_runtime_services(...)`.

The findings below focus on issues still present after this commit.

## Findings

### 1. Out-of-domain coordinates silently clamp to map edges

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:253`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:261`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1105`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1834`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1837`
- Problem:
  - `WorldMapCoordinateDomain.nearest_addressable(...)` first clamps any coordinate into `WorldMapBounds`, then snaps to addressable parity.
  - That mixes two different concepts:
    - valid in-bounds but unaddressable coordinate pairs, such as `(511, 0)` or `(0, 1023)`,
    - truly out-of-domain coordinates, such as `(999, 999)`, `(512, 0)`, or OCR garbage.
  - Direct movement and origin resolution both call this method, so an invalid explicit target or bad viewport OCR can become a plausible edge coordinate instead of failing fast.
  - Reproduction from the current code:
    - `nearest_addressable((-5, 0)) -> (0, 0)`
    - `nearest_addressable((999, 999)) -> (511, 999)`
    - `nearest_addressable((0, 5000)) -> (0, 1022)`
- Why it matters:
  - A bad OCR read can turn into a real search route at the wrong edge of the kingdom.
  - A caller typo can silently move/search somewhere else.
  - This violates the fail-fast requirement and makes live search failures much harder to diagnose.
- Clean fix:
  - Split the API into explicit operations:
    - `require_inside_bounds(coordinate)` or equivalent validation,
    - `nearest_addressable_in_bounds(coordinate)` for parity-only normalization,
    - `clamp_bounds(...)` only for coverage rectangles/radius truncation, not point identity.
  - For observed viewport coordinates, fail if the coordinate is outside the domain; do not clamp OCR.
  - For explicit/magnifier targets, normalize only when the raw coordinate is inside the known domain but the pair is unaddressable.
  - Add tests for out-of-domain explicit origins, current-viewport origins, and direct coordinate-mover targets.

### 2. Coordinate-jump movement is not verified before checkpoint ingestion

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1219`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1748`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1749`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1751`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1752`
- Problem:
  - `_move_with_coordinate_jump(...)` asks the navigator for actions, executes them, checks for the invalid-coordinate banner, and returns the resulting observation.
  - It does not prove that the resulting world-map viewport is at the requested checkpoint.
  - If `plan_jump(...)` returns no actions, search treats the current observation as the moved checkpoint without verifying that it is already at the target.
- Why it matters:
  - Once coordinate-dialog navigation is enabled, a selector miss, stale dialog state, or partial action plan can make the search index the wrong viewport under the requested checkpoint label.
  - The subplan explicitly says coordinate navigation must verify that the viewport reached the intended coordinate.
- Clean fix:
  - After executing coordinate-jump actions, call `_require_proven_world_map_observation(...)`.
  - Check the resulting viewport coordinate against the checkpoint using the same tolerance policy used by swipe movement.
  - If no actions are returned, verify the current viewport is already at the checkpoint; otherwise raise `SelectorResolutionError`.
  - Add tests for:
    - no-action coordinate jump while not at target,
    - action result at the wrong coordinate,
    - action result with missing world-map surface,
    - valid coordinate jump landing at the normalized target.

### 3. Coarse world-map-root detection still has a duplicate coordinate parser

- Severity: Medium
- Evidence:
  - `pnc_automation/app/pnc/vision/pnc_observation_enricher.py:145`
  - `pnc_automation/app/pnc/vision/pnc_observation_enricher.py:4312`
  - `pnc_automation/app/pnc/vision/pnc_observation_enricher.py:4318`
  - canonical parser: `pnc_automation/app/pnc/vision/world_map_coordinates.py:130`
  - canonical parser: `pnc_automation/app/pnc/vision/world_map_coordinates.py:136`
- Problem:
  - Exact world-map proof and selector-region proof now use `world_map_coordinates.py`, but coarse root detection still uses `_WORLD_ROOT_COORDINATE_PAIR_PATTERN`.
  - That keeps a second coordinate grammar alive after the commit's stated consolidation.
  - The root regex also contains mojibake for the fullwidth colon alternative when inspected at runtime, while the canonical parser correctly uses `\uff1a`.
- Why it matters:
  - Coarse root proof can drift from exact proof.
  - A frame that exact parsing would understand can remain `UNKNOWN` or fail coarse-root recovery because the fallback regex is different.
- Clean fix:
  - Delete `_WORLD_ROOT_COORDINATE_PAIR_PATTERN`.
  - Make `_find_world_map_root_coordinate_line(...)` call `world_coordinate_text_matches(...)` or a small canonical helper from `world_map_coordinates.py`.
  - Add a regression where the coordinate line uses a fullwidth colon and another where X omits the colon, proving both exact and coarse root paths use the same parser.

### 4. Composite matchers drop castle-enrichment and profile-validation behavior

- Severity: Medium
- Evidence:
  - visible generic-object matching: `pnc_automation/app/pnc/navigation/world_map_search.py:717`
  - visible castle matching: `pnc_automation/app/pnc/navigation/world_map_search.py:734`
  - indexed generic-object matching: `pnc_automation/app/pnc/navigation/world_map_index.py:122`
  - indexed castle matching: `pnc_automation/app/pnc/navigation/world_map_index.py:103`
  - checkpoint visible/indexed collection: `pnc_automation/app/pnc/navigation/world_map_search.py:1905`
  - indexed collection loop: `pnc_automation/app/pnc/navigation/world_map_search.py:1928`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:847`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:870`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:893`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1637`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1639`
- Problem:
  - Base map-element matching does exist and is centralized:
    - `SpatialObjectSearchMatcher.matches_visible_object(...)` delegates to `DetectedSpatialObject.matches(...)`.
    - `SpatialObjectSearchMatcher.matches_sighting(...)` delegates to `WorldMapObjectSighting.matches_object_query(...)`.
    - `CastleQuerySearchMatcher.matches_visible_object(...)` applies castle-specific visible-label/kingdom/alliance/level/coordinate predicates.
    - `CastleQuerySearchMatcher.matches_sighting(...)` delegates to `WorldMapObjectSighting.matches_castle_query(...)`.
  - The search loop consumes those through `_collect_checkpoint_matches(...)` and `_collect_index_matches(...)`.
  - `AllOfWorldMapSearchMatcher`, `AnyOfWorldMapSearchMatcher`, and `NotWorldMapSearchMatcher` only compose visible/indexed match checks.
  - They do not propagate `supports_castle_enrichment(...)`, `supports_castle_profile_validation(...)`, `rank_castle_candidate(...)`, or `validate_castle_profile(...)`.
  - A composed matcher containing `WorldMapCastleProfileQuery` will not trigger candidate inspection because the top-level composite reports no enrichment support.
- Why it matters:
  - The subplan calls matcher composition a canonical seam.
  - Composition currently works for simple object filtering but breaks the special castle-inspection path.
- Clean fix:
  - Add a single canonical candidate-enrichment composition model.
  - For `AnyOf`, enrichment support should be true when any child supports it, and ranking can take the best eligible child score.
  - For `AllOf`, avoid ad hoc behavior: introduce a candidate-eligibility/ranking helper so map-side constraints and profile-validation children can compose predictably.
  - Keep `Not` conservative unless there is a concrete supported use case for negative profile inspection.
  - Add tests proving composed profile-validation matchers inspect candidates.

### 5. Coordinate-dialog and overview navigation are still placeholders

- Severity: Medium
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1208`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1219`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1222`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1229`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1240`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1243`
- Problem:
  - The request model can express `COORDINATE_JUMP` and `OVERVIEW_SEED`, but the default navigators are unsupported stubs.
  - This is acceptable as a staged implementation detail, but it means the subplan's low-level movement primitives and map-bounds extraction are not actually complete.
- Why it matters:
  - Full-map search still lacks the efficient "seed start from corner / overview bounds / jump to known candidate" primitives described by the plan.
  - Consumers can wire movement preferences that look supported at the type level but are not available in the default runtime.
- Clean fix:
  - Track this in a dedicated navigation-primitives plan instead of expanding the search review into an implementation plan.
  - Implement coordinate-dialog navigation behind `WorldMapCoordinateNavigator` with target verification from finding 2.
  - Implement overview bounds parsing or remove `OVERVIEW_SEED` from any "implemented" claim until it can return real bounds.

### 6. Coordinate-domain/traversal ownership can be simplified

- Severity: Low
- Evidence:
  - `pnc_automation/app/pnc/navigation/world_map_search.py:204`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:279`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:1264`
  - `pnc_automation/app/pnc/navigation/world_map_search.py:2421`
- Problem:
  - `world_map_search.py` now owns request modeling, matching, coordinate-domain rules, movement, traversal planning, castle inspection, and execution.
  - The coordinate-domain helpers are canonical, but they are embedded in a very large service module.
  - Some route support logic is domain-owned while some remains as free traversal helpers.
- Why it matters:
  - The planned pattern work will add serpentine row helpers and likely make the file harder to reason about.
  - Keeping coordinate-domain and traversal generation separate would make the single canonical implementation easier to maintain without duplicating logic.
- Clean fix:
  - Extract `WorldMapCoordinateDomain` and addressable-row helpers to a small domain module.
  - Extract traversal pattern generation to `world_map_traversal.py`.
  - Keep `WorldMapSearchService` focused on orchestration: resolve plan, move, observe, ingest, match, stop.

## Recommended Fix Order

1. Fix out-of-domain coordinate clamping first, because it can silently turn bad OCR or caller input into wrong live movement.
2. Add coordinate-jump verification before enabling or relying on `COORDINATE_JUMP`.
3. Delete the duplicate coarse-root coordinate parser and route it through `world_map_coordinates.py`.
4. Implement matcher composition for enrichment before encouraging composed castle/profile queries.
5. Use `PNC_WORLD_MAP_SEARCH_PATTERN_DEBUG_PLAN.md` for `SERPENTINE_ROW_SWEEP`; do not duplicate that work in this review.
6. Use `PNC_WORLD_MAP_NAVIGATION_PRIMITIVES_PLAN.md` for coordinate-dialog and overview-map support.
7. Extract domain/traversal modules when touching the pattern code, so the next change reduces complexity instead of adding another layer to `world_map_search.py`.

## DRY Checklist

- One canonical coordinate-bar parser is almost achieved, but `_WORLD_ROOT_COORDINATE_PAIR_PATTERN` is still a duplicate and should be removed.
- Coordinate addressability is centralized in `WorldMapCoordinateDomain`, but the API currently conflates clamping and parity snapping.
- Search execution has one canonical checkpoint loop.
- Obsolete duplicate recapture behavior was removed through `record_checkpoint(...)`.
- Feature/task consumers have not yet migrated to `WorldMapSearchService`; no task currently calls `require_world_map_search_service(...)`.
