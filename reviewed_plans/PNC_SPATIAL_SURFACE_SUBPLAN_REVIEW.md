# Review: `Implement spatial surface world map architecture` (`d1a64fb7ba1e37e2510802edf86036999edd2245`)

## Scope

Reviewed the implementation against `PNC_SPATIAL_SURFACE_SUBPLAN.md`, with extra attention on:

- spatial observation modeling,
- world-map parsing and navigation,
- task/flow integration,
- index/query stability.

Validation run:

- `py -m unittest discover -s tests` -> `316` tests passed, `9` skipped.

## Findings

### 1. High: the current `world_coordinate` key path mixes map coordinates with raw screen pixels instead of using a normalized estimated-vs-confirmed model

Relevant code:

- `pnc_automation/vision/spatial_surfaces.py:259-266`
- `pnc_automation/pnc/world_map_index.py:236-241`

The parser currently computes each object's `world_coordinate` as:

- `viewport X/Y` + `pixel offset from viewport center`

The issue is not that estimated coordinates should never exist. The issue is that the current implementation stores a raw pixel-derived value as if it were already a stable world-space coordinate.

That mixes two different units:

- world-map coordinates from the viewport label,
- screen-pixel offsets from the screenshot.

The same object at the same relative map position therefore produces different `world_coordinate` values at different screenshot resolutions, and the computed coordinate can become negative.

I reproduced this with the current code by feeding the same normalized object placement into two image sizes:

- `900x1184` -> `world=(103, 408)`
- `1800x2368` -> `world=(-47, 369)`

`WorldMapSurveyIndex` then treats this value as a canonical `PROJECTED_WORLD` key, so sightings can drift or collide depending on instance geometry instead of actual map identity.

I agree with the underlying architectural direction discussed afterward:

- `viewport X/Y` from the world-map label is authoritative,
- `estimated coordinates` can still be useful for navigation and revisit flows,
- `confirmed coordinates` parsed from popup/detail UI are useful too,
- but estimated and confirmed coordinates should not be treated as the same evidence class.

This is especially important because many world objects are temporary. Resource tiles can spawn/respawn on short intervals, so even a confirmed coordinate is not a forever-identity. It is still valuable, but it should stay cheap to maintain and should be treated as time-sensitive object evidence rather than permanent truth.

Why this matters:

- the index will not be stable across supported BlueStacks resolutions,
- any future feature that trusts `object.world_coordinate` will be built on invalid data,
- the current "projected world" key can silently merge or split sightings incorrectly.

Clean fix:

1. Replace the current raw-pixel inference with a normalized-coordinate estimate:
   - keep `viewport_coordinate` from the top label,
   - keep `viewport_offset_ratio`,
   - infer `estimated_coordinate` from normalized offsets plus an explicit calibrated transform for the supported instance geometry.
2. Split estimated and confirmed coordinate evidence into different structures or indexes rather than one shared canonical key space.
3. Only populate `confirmed_coordinate` from authoritative UI such as popup/detail/magnifier `K/X/Y`.
4. Treat confirmed coordinates for temporary objects as expiring evidence with lightweight maintenance rather than as permanent identity records.
5. Do not let the current raw-pixel-derived `world_coordinate` drive `PROJECTED_WORLD` keys.
6. Add a regression test that asserts the same normalized object placement yields the same estimated key across multiple screenshot sizes.

### 2. High: `TapSpatialObjectAction` loses object identity and can tap the wrong duplicate object

Relevant code:

- `pnc_automation/pnc/action_requests.py:58-63`
- `pnc_automation/automation/action_executor.py:92-96`
- `pnc_automation/automation/action_executor.py:191-196`
- `pnc_automation/pnc/observation.py:361-376`
- `pnc_automation/automation/tasks/gathering_task.py:134-143`
- `pnc_automation/automation/tasks/building_upgrade_task.py:136-145`

The task/flow layer picks a specific `DetectedSpatialObject`, but the action only stores a broad `SpatialObjectQuery`. At execution time the query is re-resolved by scanning visible objects and returning the first match.

That is unsafe for the new spatial model because duplicates are normal:

- multiple visible `Food Farm` nodes,
- multiple `Barracks`,
- repeated alliance structures with the same name/category.

I reproduced this directly with the current code: when two visible `Food Farm` nodes share the same `resource_type`, the query built for the second node resolves back to the first node's action point.

Why this matters:

- gathering can click the wrong node even after correctly choosing a target,
- home-city navigation can click the wrong repeated building,
- the new spatial-action contract is weaker than the old list-entry contract because it drops identity before execution.

Clean fix:

1. Make `TapSpatialObjectAction` carry stable target identity, not just a semantic query.
2. The simplest version is to store a concrete tap point captured from the selected `DetectedSpatialObject`.
3. If you want semantic re-resolution, include a disambiguator such as `bounds`, `action_point`, or a canonical object key and fail fast on multiple matches.
4. Add tests with duplicate visible resource nodes and duplicate visible barracks to prove the exact selected object is the one being tapped.

### 3. High: building upgrade now treats any recognized building as upgradeable and can report success even when no upgrade happened

Relevant code:

- `pnc_automation/vision/spatial_surfaces.py:380-389`
- `pnc_automation/automation/tasks/building_upgrade_task.py:105-123`
- `pnc_automation/automation/tasks/building_upgrade_task.py:96-100`

The home-city parser now emits `HOME_BUILDING` objects with only:

- `category`
- `building_name`

There is no upgrade-eligibility signal. But `BuildingUpgradeTask` now treats every parsed `HOME_BUILDING` in a supported category as a candidate. After tapping one, `verify(...)` returns success as soon as it sees `PNC_BUILDING_DETAILS` without an upgrade button.

That creates a false-positive path:

1. detect any supported building,
2. tap it,
3. land on a details screen where upgrade is unavailable,
4. report `"Building upgrade started..."` anyway.

I reproduced that with the current code: a home-city observation containing a single parsed `Castle` building plus an empty `PNC_BUILDING_DETAILS` observation returns `TaskStatus.SUCCESS`.

Why this matters:

- the task can claim success on maxed, blocked, or otherwise ineligible buildings,
- runner state will move on even though no upgrade was started,
- this also overreaches the plan boundary, which explicitly said home-city building workflows should stay in a follow-on slice unless their constraints are modeled properly.

Clean fix:

1. Reintroduce an explicit upgrade-eligibility signal before treating a building as a candidate.
2. Good options are:
   - require a visible upgrade badge/evidence on the city scene, or
   - require the post-tap building-details screen to actually expose `PNC_BUILDING_UPGRADE_BUTTON`.
3. Change `verify(...)` so missing `PNC_BUILDING_UPGRADE_BUTTON` is a failure or replan, not success.
4. Keep home-city spatial navigation reusable, but do not let the task claim upgrade support until eligibility is represented canonically.

## Summary

The new observation/catalog split is moving in the right direction, and the commit passes the current automated suite. The main problems are correctness problems in the new spatial identity layer:

- raw-pixel world-coordinate inference instead of normalized estimated/confirmed coordinate handling,
- non-unique spatial tap targeting,
- over-eager building-upgrade success conditions.

Those are worth fixing before more features start depending on the spatial model, because they affect the core contracts that later world-map and home-city slices will inherit.
