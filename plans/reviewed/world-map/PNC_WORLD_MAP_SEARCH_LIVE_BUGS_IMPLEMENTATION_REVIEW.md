# PNC World-Map Search Live Bugs Implementation Review

## Scope

Reviewed commit `38e8862f105e2892eca52f9d26d06ee1c2ef4fff` (`Fix live world map calibration proof and retries`) against:

- `PNC_WORLD_MAP_SEARCH_LIVE_BUGS_PLAN.md`
- the touched navigation, vision, tool, and test modules in the commit

Validation run during this review:

- `py -3 -m unittest discover -s tests`
- Result: `697` tests passed, `13` skipped

Additional targeted sanity checks during this review:

- `py -3 -m unittest tests.test_world_map_search tests.test_world_map_movement_calibration tests.test_capture_and_vision`
- Result: `168` tests passed
- direct parser repros against `parse_world_coordinate_text(...)`

## Findings

### 1. The new OCR recovery path can silently turn invalid coordinates into different valid coordinates

- Severity: High
- Evidence:
  - `pnc_automation/app/pnc/vision/world_map_coordinates.py:147-154`
  - `pnc_automation/app/pnc/vision/world_map_coordinates.py:272-329`
  - new commit tests only cover accepted recoveries:
    - `tests/test_capture_and_vision.py:2544-2588`
    - `tests/test_capture_and_vision.py:2909-2913`
- Problem:
  - The new parser no longer just rejects oversized coordinate components. It now searches for any in-range digit slice inside the OCR run and accepts it as the coordinate.
  - That is broad enough to convert obviously invalid coordinates into plausible but wrong map positions.
  - Reproduced during this review:
    - `parse_world_coordinate_text("X:512 Y:200") -> (51, 200)`
    - `parse_world_coordinate_text("X:0 Y:1024") -> (0, 102)`
    - `parse_world_coordinate_text("X:999 Y:1023") -> (99, 1023)`
    - `parse_world_coordinate_text("X: 2736039 Y:958") -> (273, 958)`
- Why it matters:
  - The whole purpose of this commit is to improve movement proof and make live failures diagnosable.
  - This heuristic does the opposite for some inputs: it can hide parser failures by manufacturing a nearby-looking coordinate.
  - That can misclassify a bad OCR read as a real movement drift, stall, or landing error and send the search logic to the wrong place.
- Clean fix:
  - Replace `_best_bounded_digit_slice(...)` with explicit, narrow recovery strategies for only the live OCR defects we have actually observed.
  - Keep accepted recoveries deterministic and explainable, for example:
    - exact bounded value
    - whitespace-only merge when the merged value is still bounded
    - one trailing digit trim when the remaining prefix is bounded
    - one leading-noise trim only when it matches a specifically reviewed live pattern
  - Do not accept arbitrary interior substrings from an oversized run.
  - Add negative regressions proving the parser returns `None` for invalid-but-plausible inputs such as `X:512`, `Y:1024`, `X:999`, and similar one-off overflows.

### 2. The commit re-hardcodes the canonical PNC map bounds in the vision parser

- Severity: Medium
- Evidence:
  - `pnc_automation/app/pnc/vision/world_map_coordinates.py:18-19`
  - canonical domain owner: `pnc_automation/app/pnc/navigation/world_map_coordinate_domain.py:91-97`
- Problem:
  - The commit introduces `WorldMapCoordinateDomain.puzzles_and_conquest()` as the canonical owner of the live world-map bounds.
  - But the new OCR parsing recovery path independently hardcodes `_WORLD_COORDINATE_MAX_X = 511` and `_WORLD_COORDINATE_MAX_Y = 1023`.
  - That duplicates the same concept in two places immediately after the coordinate-domain refactor was supposed to centralize it.
- Why it matters:
  - If the canonical domain changes, or if another domain instance is ever used for a different environment, the vision parser and the navigation domain can drift.
  - This violates the repo's "single canonical implementation per concept" rule and makes future parser tuning easier to get wrong.
- Clean fix:
  - Remove the local max constants from `world_map_coordinates.py`.
  - Read the parser bounds from one canonical domain source instead:
    - either import `WorldMapCoordinateDomain.puzzles_and_conquest().bounds`
    - or expose a tiny shared constant/helper specifically for the live PNC world-map domain
  - Keep the parser bounded by that shared owner so vision and navigation cannot disagree.

### 3. The new local-bounds logic is duplicated between the live tool and the live smoke test

- Severity: Low
- Evidence:
  - `tools/run_world_map_movement_calibration.py:310-320`
  - `tests/test_live_world_map_movement_calibration_smoke.py:202-212`
- Problem:
  - The same "build a radius window, then clamp it to the canonical PNC domain" helper now exists in two places.
  - Both copies were added in this commit and both encode the same behavior.
- Why it matters:
  - This is small duplication, but it is still duplication around a live-diagnostics boundary that is actively being tuned.
  - If local calibration bounds change again, one copy can drift and the smoke test will no longer exercise the same geometry as the live tool.
- Clean fix:
  - Move this into one shared helper and reuse it from both call sites.
  - The cleanest home is either:
    - `world_map_movement_calibration.py` if it is part of the runtime calibration model, or
    - a narrow shared test/live utility if the production module should stay smaller.
  - Keep the smoke test and the live tool on the exact same local-bounds implementation.
