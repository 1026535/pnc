# PNC World-Map Search Pattern Debug Plan

## Purpose

Define and validate the canonical traversal behavior for world-map search patterns, especially broad full-map castle searches for targets such as `Toast.`, `Toast`, and `Barcode`.

This plan is separate from the coordinate-OCR and coordinate-domain fixes. Those fixes make coordinates trustworthy and addressable; this plan decides the order in which search should visit those coordinates.

## Context

Recent live testing on the `serious_stuff` BlueStacks instance with the `please_b_gentle` P&C account clarified that the current route planning is not yet the desired full-sweep behavior.

The desired broad search pattern is:

- start from the normalized upper-left world-map coordinate,
- sweep across the first row from left to right until the normalized top-right row endpoint,
- move down by roughly one viewport/search stride,
- sweep the next row right to left,
- repeat alternating row direction until the final row is covered.

This is a serpentine, or boustrophedon, sweep. It should minimize long horizontal reset moves and make live search coverage easier to audit.

## Recommended Apply Order

Between this plan and `PNC_WORLD_MAP_SEARCH_LIVE_BUGS_PLAN.md`, the clean order is:

1. Complete this plan's code-shaping phases first:
   - make the pattern explicit,
   - centralize the row/addressable helpers,
   - add route tests,
   - add dry-run/preview tooling.
2. Use the live-bugs plan second for bounded live validation of the resulting canonical route and for any movement defects discovered while exercising it.
3. Return to this plan's live-validation phase only after the live-bugs slice has either fixed or clearly bounded the blocking runtime issue.

Rationale:

- this plan owns traversal semantics and route auditability,
- the live-bugs plan should validate one already-explicit route instead of debugging broad search while route semantics are still implicit,
- movement/runtime defects discovered during validation should be tracked in the live-bugs plan, not folded back into traversal design.

Practical exception:

- if a currently open live movement defect prevents even a 2-row bounded validation sweep, fix that blocker under the live-bugs plan first, then resume this plan from dry-run or bounded-route validation.

## Architecture Fit Check

The target architecture in this plan still matches both the durable screen-flow architecture and the current code direction.

Current alignment already present in code:

- `ScreenFlowPlanner` owns world-map entry, readiness, and return-to-root behavior, not checkpoint traversal,
- `WorldMapNavigator` owns one low-level world-map movement/tap primitive,
- `WorldMapSearchService` owns request validation, route resolution, checkpoint movement orchestration, ingestion, matching, and stop policy,
- `WorldMapTraversalPlanner` is already split into its own module and owns route generation,
- `WorldMapCoordinateDomain` is already split into its own module and owns addressability/bounds behavior,
- survey/index ownership is already separated through `WorldMapSurveyRecorder` and `WorldMapSurveyIndex`.

Remaining architecture-shaped gaps are implementation-completion gaps, not signs that the target ownership model is wrong:

- `SERPENTINE_ROW_SWEEP` is still missing as a first-class traversal pattern,
- coordinate-dialog and overview primitives are currently owned by the search subsystem but still colocated in `world_map_search.py` rather than extracted into a smaller navigation-primitives module,
- feature/task consumers are not yet broadly migrated to consume `WorldMapSearchService` as their shared search entry point.

Practical conclusion:

- do not redesign the ownership model again before continuing,
- keep implementing toward the existing target architecture,
- prefer extraction/refinement only when it reduces size or duplication without reintroducing parallel APIs.

## Current Problem

The current `ROW_MAJOR_SWEEP` semantics are a logical sorted order over checkpoints. That is useful for deterministic tests, but it is not ideal for live full-map traversal.

Problems:

- a plain row-major route may require a long reset from the right edge back to the left edge at every row transition,
- long reset moves amplify movement calibration error,
- route logs are harder to visually compare with the intended map coverage,
- full-map player search should not depend on unnecessary far-distance repositioning when an alternating row sweep can cover the same area more naturally.

## Review Finding Moved Here

Implementation review of commit `04f00b16ec91cf868ecb7232a6f9b60ed9008d56` initially called out that serpentine row sweep is still not implemented:

- `WorldMapSearchPatternKind` currently exposes only:
  - `ROW_MAJOR_SWEEP`
  - `EXPANDING_RING`
  - `EDGE_BAND_SWEEP`
- there is no `SERPENTINE_ROW_SWEEP` enum value or factory yet,
- full-map broad search therefore still cannot express the intended alternating-row traversal directly in code.

This is intentionally tracked here, not in the implementation-review document, because this plan already owns traversal-pattern design and validation. Work on this item should happen when this plan resumes.

## Related Completed Work

The following work is already complete and should be treated as a dependency, not reimplemented here:

- one canonical coordinate-bar OCR/parser path is shared by world-map proof and spatial-surface viewport extraction,
- `WorldMapCoordinateDomain` owns the live PNC bounds and addressable coordinate-pair model,
- the domain normalizes magnifier-style raw inputs to real addressable tiles,
- search and direct movement now compare against normalized addressable coordinates,
- impossible coordinate-pair rectangles fail fast instead of silently snapping outside the caller's boundary.

## Target Model

### Search Boundary

The boundary continues to define the allowed coverage area.

Examples:

- full kingdom: `FULL_MAP` with the live PNC coordinate-domain bounds,
- local scan: `RADIUS_FROM_ORIGIN`,
- explicit debug lane: `RECTANGLE`,
- edge scan: `EDGE_BAND`.

### Search Pattern

The pattern defines visitation order, not coverage.

Recommended additions:

- keep `ROW_MAJOR_SWEEP` as the deterministic logical row-major order for small/local/debug use,
- add a first-class `SERPENTINE_ROW_SWEEP` pattern for movement-efficient broad row coverage,
- make full-map castle search prefer `SERPENTINE_ROW_SWEEP`.

Do not overload `ROW_MAJOR_SWEEP` silently. A caller reading the request should be able to see whether the route is logical row-major or alternating-row movement order.

### Coordinate Domain

Pattern planning must consume `WorldMapCoordinateDomain` for every emitted checkpoint.

Rules:

- do not emit impossible coordinate pairs,
- normalize map-corner origins through the domain,
- keep row endpoints inside the caller's boundary,
- fail fast if a requested row or rectangle contains no addressable tile,
- preserve the domain's magnifier snap behavior for explicit target movement.

### Recognition Scope

This plan should not assume that the runtime can recognize every world-map element.

Current explicitly modeled world-map object kinds are:

- `castle`
- `alliance_building`
- `monster`
- `hell_fortress`
- `resource_node`
- `altar`
- `dragonia`

Implications:

- broad player search depends primarily on reliable castle recognition plus trustworthy viewport coordinates and traversal,
- unsupported or weakly recognized object classes should not be treated as silently searchable,
- if live review uncovers a map object that the current spatial surface cannot classify, that is a recognition-coverage gap, not a traversal-pattern bug.

### Recognition Coverage Risk

We do not yet have proof that every relevant world-map element is recognized reliably in live conditions.

- Severity:
  - High for generic map search
  - Medium for castle-only player search
- Status: Open
- Current confidence:
  - castle recognition is the most important path for Toast/Barcode search and already has meaningful offline coverage,
  - the runtime does not currently claim exhaustive recognition for every visible world-map element,
  - unsupported elements, OCR noise, wrapped labels, and dense overlap can still produce false negatives or ambiguous classifications.
- Impact:
  - a broad search may traverse correctly yet still miss the target if castle labeling is not extracted from that viewport,
  - debugging becomes noisy if recognition misses are mistaken for traversal or movement failures,
  - generic future map search should not assume "all elements are searchable" without evidence.
- Required fix direction:
  - add one explicit recognition audit pass during bounded live search,
  - compare screenshot-visible objects against indexed sightings checkpoint by checkpoint,
  - classify misses as:
    - unsupported object kind,
    - OCR/label grouping miss,
    - relationship classification miss,
    - estimated-coordinate/indexing miss.
- Required validation:
  - run one dense bounded survey and manually compare the captured screenshot with the indexed object list,
  - specifically confirm castle handling for:
    - self label `My Territory`,
    - alliance-tagged player castles,
    - kingdom/id-only castle labels,
    - wrapped multi-line labels,
    - mixed-object frames containing castles plus neutral structures/resources.
- Exit criterion:
  - broad Toast/Barcode live search should proceed only once castle recognition is trusted enough that a "not found" result is meaningful within the searched area.

## Desired Full-Map Serpentine Route

For the live PNC domain:

- bounds are `X=0..511`, `Y=0..1023`,
- valid addressable pairs have even `x + y`,
- upper-left is `(0, 0)`,
- the top row's right endpoint is `(510, 0)`, because `(511, 0)` is not addressable,
- lower-left is `(0, 1022)`, because `(0, 1023)` is not addressable.

For a full sweep with row stride `S`:

1. Generate addressable row samples from top to bottom.
2. For row index `0`, emit addressable X samples left to right.
3. For row index `1`, emit addressable X samples right to left.
4. Alternate until the last sampled row.
5. Include the last addressable row inside the boundary even when the stride does not land exactly on it.

The exact row-sampling policy should be explicit and tested. It may use `checkpoint_spacing` initially, but the plan should leave room for a later viewport-aware stride once live viewport coverage is measured more precisely.

## Implementation Plan

### Phase 1: Make The Pattern Explicit

- Add `SERPENTINE_ROW_SWEEP` to `WorldMapSearchPatternKind`.
- Add `WorldMapSearchPattern.serpentine_row_sweep()`.
- Route it through `WorldMapTraversalPlanner`.
- Keep all coordinate generation inside the coordinate-domain/traversal ownership, not in feature tasks.

### Phase 2: Domain-Owned Row Helpers

- Add a domain-owned helper that returns addressable row samples.
- Add a domain-owned helper that returns addressable coordinates on one row in either left-to-right or right-to-left order.
- Reuse these helpers from both row-major and serpentine planning.
- Delete or avoid any duplicate row/axis sampling helpers once the domain helper exists.

### Phase 3: Full-Map Search Defaults

- Decide how broad castle-search callers should express "whole kingdom":
  - pattern: `SERPENTINE_ROW_SWEEP`,
  - origin: `MAP_CORNER(UPPER_LEFT)`,
  - boundary: `FULL_MAP(WorldMapCoordinateDomain.puzzles_and_conquest().bounds)`.
- Keep the request explicit rather than hiding a full-map search behind a task-local shortcut.

### Phase 4: Tests

Add unit tests for:

- a small rectangular serpentine route:
  - first row left to right,
  - second row right to left,
  - third row left to right.
- top-row live-domain endpoint:
  - route includes `(0, 0)` and `(510, 0)`,
  - route does not include `(511, 0)`.
- lower-left live-domain endpoint:
  - route includes `(0, 1022)`,
  - route does not include `(0, 1023)`.
- checkerboard parity:
  - no emitted checkpoint violates the coordinate domain.
- non-addressable single-coordinate boundary:
  - fail fast.
- full-map dry-run route preview:
  - a request can produce a route without executing movement, so live debug can inspect route shape first.

### Phase 5: Recognition Coverage Audit

Before broad live player search, add one explicit audit slice for map-element recognition.

Audit goals:

- prove the world-map surface still classifies visible castles correctly after traversal changes,
- verify wrapped labels, alliance-tagged labels, self-castle labeling, and kingdom/id-only castle labels,
- confirm that unsupported or ambiguous elements fail visibly instead of being misclassified as castles,
- record the exact currently supported object kinds so later work can expand them intentionally.

Suggested offline coverage:

- castle-only viewport with self, ally, and other castles,
- wrapped castle-name viewport,
- mixed viewport containing castle, alliance building, monster, and resource node,
- neutral-object viewport for `altar`, `dragonia`, and `hell_fortress`,
- one noise-heavy viewport where unrelated OCR text must not create false world objects.

Suggested live coverage:

- a bounded survey on a dense map area,
- manual review of the indexed sightings versus the screenshot,
- a short list of false positives, false negatives, and unsupported-but-visible object types.

### Phase 6: Live Debug Tooling

Add or reuse a live-safe command/tool that:

- connects to the account,
- proves world map,
- builds the planned route,
- prints the first N checkpoints, row transitions, and last N checkpoints,
- optionally runs only the first N checkpoints.

This is important before running broad live player searches. The operator should be able to verify route shape without committing to a full sweep.

### Phase 7: Live Validation

Use `serious_stuff` / `please_b_gentle` gently.

Suggested validation sequence:

1. Dry-run route preview for a small rectangle near the current viewport.
2. Execute a 2-row or 3-row bounded serpentine sweep.
   - validate both from a fresh-start world-map observation and after any probe/recenter sequence used during movement debugging, because the current live blocker appears state-sensitive.
3. Run the recognition coverage audit on the same bounded area and classify any misses as:
   - traversal issue,
   - movement issue,
   - coordinate-proof issue,
   - recognition issue.
4. Dry-run full-map route preview from upper-left.
5. Execute only the first few full-map checkpoints.
6. Only after route, movement, and castle recognition look stable, run a broader Toast/Barcode search.

## Acceptance Criteria

- There is exactly one canonical implementation of serpentine row traversal.
- `ROW_MAJOR_SWEEP` and `SERPENTINE_ROW_SWEEP` have distinct, documented semantics.
- Full-map broad search can start at the normalized upper-left coordinate and naturally alternate row direction.
- The route never emits impossible coordinate pairs.
- Tests prove corner behavior for `(511, 0)` and `(0, 1023)`.
- Recognition coverage is explicit:
  - supported object kinds are documented,
  - castle-search assumptions are tested,
  - unsupported/ambiguous elements are surfaced as gaps rather than silently treated as searchable.
- Live dry-run output makes the planned route auditable before movement begins.
- No feature/task implements its own custom sweep loop.
