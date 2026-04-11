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

## Current Problem

The current `ROW_MAJOR_SWEEP` semantics are a logical sorted order over checkpoints. That is useful for deterministic tests, but it is not ideal for live full-map traversal.

Problems:

- a plain row-major route may require a long reset from the right edge back to the left edge at every row transition,
- long reset moves amplify movement calibration error,
- route logs are harder to visually compare with the intended map coverage,
- full-map player search should not depend on unnecessary far-distance repositioning when an alternating row sweep can cover the same area more naturally.

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

### Phase 5: Live Debug Tooling

Add or reuse a live-safe command/tool that:

- connects to the account,
- proves world map,
- builds the planned route,
- prints the first N checkpoints, row transitions, and last N checkpoints,
- optionally runs only the first N checkpoints.

This is important before running broad live player searches. The operator should be able to verify route shape without committing to a full sweep.

### Phase 6: Live Validation

Use `serious_stuff` / `please_b_gentle` gently.

Suggested validation sequence:

1. Dry-run route preview for a small rectangle near the current viewport.
2. Execute a 2-row or 3-row bounded serpentine sweep.
3. Dry-run full-map route preview from upper-left.
4. Execute only the first few full-map checkpoints.
5. Only after route and movement look stable, run a broader Toast/Barcode search.

## Acceptance Criteria

- There is exactly one canonical implementation of serpentine row traversal.
- `ROW_MAJOR_SWEEP` and `SERPENTINE_ROW_SWEEP` have distinct, documented semantics.
- Full-map broad search can start at the normalized upper-left coordinate and naturally alternate row direction.
- The route never emits impossible coordinate pairs.
- Tests prove corner behavior for `(511, 0)` and `(0, 1023)`.
- Live dry-run output makes the planned route auditable before movement begins.
- No feature/task implements its own custom sweep loop.
