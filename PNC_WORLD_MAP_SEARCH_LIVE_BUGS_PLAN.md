# PNC World-Map Search Live Bugs Plan

## Purpose

Track bugs found while live-validating world-map search on the `serious_stuff` BlueStacks instance with the currently logged-in `please_b_gentle` P&C account.

This file is intentionally narrow: it records live validation defects and follow-up fixes discovered while trying to find the players `Toast.` / `Toast` and `Barcode`.

## Validation Context

- BlueStacks display name: `serious_stuff`
- P&C account context: `please_b_gentle`
- Config account id used by automation: `serious_stuff`
- Search targets:
  - `Toast.`
  - `Toast`
  - `Barcode`

## Bugs Found

### 1. Live world-map movement smoke helper cannot recenter between sweep phases

- Severity: Medium
- Status: Fixed in working tree
- Evidence:
  - `tests/test_live_world_map_movement_calibration_smoke.py`
  - Live run reached `serious_stuff`, entered the movement smoke, then failed with:
    - `TypeError: LiveWorldMapMovementCalibrationSmokeTests._move_to_coordinate() missing 1 required positional argument: 'coordinate'`
- Cause:
  - `_move_to_coordinate(...)` was decorated as `@staticmethod` while still declaring and using `self`.
- Fix:
  - Remove the `@staticmethod` decorator so the helper receives the test instance normally.
- Required validation:
  - Re-run the live movement smoke on `serious_stuff` after the Toast/Barcode search validation window.

## Live Search Findings

### 2026-04-11 bounded Toast/Barcode search attempt

Live command shape:

- account id: `serious_stuff`
- matcher: `Toast.`, `Toast`, or `Barcode`
- start screen: proven `PNC_WORLD_MAP`
- start coordinate: `(226, 958)`
- start artifact:
  - `artifacts/2026-04-11/serious_stuff/20260411T045932Z_live_toast_barcode_search_preflight_start.png`

Observed current-frame result:

- current viewport search completed without movement,
- stop reason: `route_exhausted`,
- visited checkpoints: `1`,
- matches: `0`,
- indexed sightings: `3`,
- visible castle sightings included:
  - self castle `My Territory`, estimated coordinate `(206, 1028)`,
  - unknown castle `K226bec6935554`, kingdom `K226`, estimated coordinate `(321, 1200)`.

Conclusion:

- visible-frame indexing and matcher evaluation worked,
- neither `Toast.`, `Toast`, nor `Barcode` was visible in the current viewport,
- broader validation was blocked by movement behavior below.

### 2026-04-11 bounded Toast/Barcode coordinate-domain retry

Live command shape:

- account id: `serious_stuff`
- matcher: `Toast.`, `Toast`, or `Barcode`
- start screen: proven `PNC_WORLD_MAP`
- start coordinate: `(504, 1020)`
- boundary: radius `2` from current viewport
- checkpoint spacing: `2`
- max checkpoints: `6`
- start artifact:
  - `artifacts/2026-04-11/serious_stuff/20260411T160821Z_live_toast_barcode_domain_probe_retry_start.png`

Planned route:

- `(502, 1018)`
- `(504, 1018)`
- `(506, 1018)`
- `(502, 1020)`
- `(504, 1020)`
- `(506, 1020)`
- `(502, 1022)`
- `(504, 1022)`
- `(506, 1022)`

Observed result:

- stop reason: `checkpoint_budget_exhausted`
- visited checkpoints: `6`
- matches: `0`
- indexed sightings: `10`
- visited route:
  - `(502, 1018)`
  - `(504, 1018)`
  - `(506, 1018)`
  - `(502, 1020)`
  - `(504, 1020)`
  - `(506, 1020)`

Conclusion:

- corrected coordinate-domain planning produced only valid checkerboard coordinate pairs,
- the canonical search loop traversed, captured, and indexed multiple checkpoints without requesting impossible magnifier coordinates,
- `Toast.`, `Toast`, and `Barcode` were not found in this small bounded area,
- broader player finding still needs a longer live run and continued movement confidence.

## Additional Bugs Found

### 2. Horizontal right-swipe movement can stall with zero coordinate delta away from known modeled bounds

- Severity: High
- Status: Open
- Evidence:
  - bounded Toast/Barcode search from `(226, 958)`,
  - first movement toward `(220, 958)` failed with:
    - `before_coordinate=(226, 958)`
    - `after_coordinate=(226, 958)`
    - `delta=(0, 0)`
    - `direction=right`
    - `classification=interior_stall`
- Impact:
  - row-major searches that need to move toward smaller X can fail before covering the requested area,
  - the search engine correctly fails fast, but the movement primitive is not yet live-stable enough for broad player search.
- Required fix direction:
  - add a focused live calibration/recovery slice for the right-swipe lane near the current kingdom/viewport geometry,
  - preserve fail-fast behavior for unexpected stalls,
  - record the exact swipe points and artifact path in the movement error so live diagnosis does not require re-running with ad hoc scripts.

### 3. Coordinate-bar OCR mixed unrelated top-HUD resource text with the real Y coordinate

- Severity: High
- Status: Fixed in working tree
- Evidence:
  - rightward Toast/Barcode validation from `(226, 958)`,
  - the route advanced to a checkpoint near the right edge, then a left swipe produced:
    - `target_coordinate=(232, 958)`
    - `before_coordinate=(230, 958)`
    - `after_coordinate=(2, 958)`
    - `delta=(-228, 0)`
    - `direction=left`
    - `classification=unexpected_delta`
  - User review of the screenshot clarified that the destination coordinate was actually `(230, 958)`, not `(2, 958)`.
  - Full OCR on the artifact exposed the root parser issue:
    - unrelated top-HUD/resource text: `X: 2,736,039`
    - real coordinate bar lines: `X:230` and `Y:958`
  - The old parser independently selected the first X-like value and first Y-like value in the top band, producing the bogus pair `(2, 958)`.
  - direct reproduction attempt on 2026-04-11:
    - requested repro anchor: move from `K226 X:230 Y:958` to `X:232 Y:958`,
    - actual current preflight coordinate before anchoring was `(228, 958)`,
    - attempting to move from `(228, 958)` toward `(230, 958)` was parsed as:
      - `target_coordinate=(230, 958)`
      - `before_coordinate=(228, 958)`
      - `after_coordinate=(2, 958)`
      - `delta=(-226, 0)`
      - `direction=left`
      - `classification=unexpected_delta`
    - anchor artifact before movement:
      - `artifacts/2026-04-11/serious_stuff/20260411T144651Z_live_wrap_repro_preflight_start.png`
    - post-error confirmation artifact:
      - `artifacts/2026-04-11/serious_stuff/20260411T144722Z_live_wrap_repro_post_error_check_start.png`
  - Re-parsing the post-error artifact after the fix returns:
    - coordinate `(230, 958)`
    - coordinate text `X:230 Y:958`
- Impact:
  - valid movement could be misclassified as a huge wrong-sign delta,
  - search traversal could fail even though the viewport reached the intended checkpoint,
  - apparent map wrap/bounds bugs could be inferred from bad coordinate evidence.
- Fix:
  - coordinate parsing now requires one coherent same-line or nearby split-line X/Y pair,
  - unrelated top-HUD/resource rows are no longer allowed to provide the X value for a different Y row,
  - `world_map_coordinates.py` is now the canonical owner for blue/cyan coordinate-bar OCR filtering and X/Y parsing,
  - world-map selector proof and spatial-surface viewport coordinates now consume the same coordinate-bar OCR implementation,
  - added a regression for the live failure pattern.
- Required validation:
  - re-run the bounded Toast/Barcode search after the parser fix,
  - if movement still fails, classify the remaining issue separately from OCR coordinate identification.
- Completed validation:
  - live preflight after the fix read `(230, 958)` from the same map area,
  - moving from `(230, 958)` to `(232, 958)` succeeded and ended at `(232, 958)`,
  - validation artifacts:
    - `artifacts/2026-04-11/serious_stuff/20260411T145921Z_live_coord_parser_fix_repro_preflight_start.png`
    - `artifacts/2026-04-11/serious_stuff/20260411T145939Z_live_coord_parser_fix_230_to_232_1_post_action_1.png`

### 4. Search bounds modeled every integer pair as addressable, but the map uses a checkerboard coordinate-pair domain

- Severity: High
- Status: Fixed in working tree
- Evidence:
  - live overview/magnifier checks on 2026-04-11 established the kingdom coordinate extents:
    - min X: `0`
    - max X: `511`
    - min Y: `0`
    - max Y: `1023`
  - `(0, 1023)` does not exist; the lower-left corner is `(0, 1022)`.
  - `(511, 0)` does not exist; the upper-right corner is `(511, 1)`.
  - same-row checks clarified that integer axis values are not invalid by themselves:
    - `(506, 1020)` exists,
    - `(508, 1020)` exists,
    - the closest right neighbor of `(507, 1019)` is `(509, 1019)`.
  - magnifier correction also clarified the interior tie-break behavior:
    - entering `(507, 1020)` corrects to `(506, 1020)`.
  - This implies an addressable coordinate-pair rule rather than an invalid-axis rule: usable world-map pairs satisfy even `x + y` parity in the observed kingdom domain.
- Impact:
  - full-map and edge routes could include impossible coordinate pairs,
  - map-corner origins such as upper-right/lower-left could target coordinates the magnifier snaps away from,
  - broad searches could waste movement/checkpoint budget on coordinates that cannot contain objects.
- Fix:
  - added one canonical `WorldMapCoordinateDomain` beside `WorldMapBounds`,
  - `WorldMapBounds` now owns only inclusive kingdom extents,
  - `WorldMapCoordinateDomain` owns addressable coordinate-pair parity, observed nearest-addressable snapping, and row-major checkpoint generation,
  - `WorldMapSearchRequest` defaults to the live PNC domain `X=0..511`, `Y=0..1023`, even `x + y`,
  - origin resolution, radius clamping, row-major route planning, expanding-ring route normalization, and edge-band route normalization now reuse the same domain model.
  - direct `WorldMapCoordinateMover` calls also normalize raw requested coordinates before planning movement legs, so calibration/live helpers compare against the real tile the magnifier will use.
  - rectangle routes that contain no addressable coordinate pair now fail fast instead of snapping outside the caller's requested boundary.
- Required validation:
  - keep live magnifier probes focused on pair validity, not individual X/Y integer validity,
  - verify broad Toast/Barcode sweeps no longer request impossible corner or row checkpoints.
- Completed validation:
  - unit coverage now asserts:
    - `(506, 1020)`, `(508, 1020)`, `(507, 1019)`, and `(509, 1019)` are addressable,
    - `(508, 1019)` is not addressable,
    - `(507, 1020)` snaps to `(506, 1020)`,
    - `(0, 1023)` snaps to `(0, 1022)`,
    - `(511, 0)` snaps to `(511, 1)`,
    - row-major traversal across `Y=1019` visits `(507, 1019)`, `(509, 1019)`, `(511, 1019)`,
    - full-map corner origins normalize to addressable coordinates.
    - a single-coordinate rectangle containing only impossible pair `(508, 1019)` fails fast.

## Follow-Up Checklist

- Re-run the targeted unit suite after any bug fixes.
- Re-run the bounded live Toast/Barcode search.
- If movement or parser failures occur, capture the exact stop reason, checkpoint count, latest coordinate, and artifact paths.
- Keep fixes in canonical world-map search/movement owners; do not add task-local duplicate search loops.
- Add more unit tests for radius/rectangle planning near known map bounds as live edge behavior is refined.
- Add live-safe diagnostics that can probe one horizontal lane without starting a broad search.
