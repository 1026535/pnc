# Step 4.5: Puzzles & Conquest Spatial Surface Sub-Plan

## 1. Purpose

This document introduces the canonical design for scrollable, non-fixed game surfaces that cannot be modeled correctly as fixed UI selectors.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary architecture plan,
- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md), which owns selector maturity and registry refinement,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation flows,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which owns bootstrap and castle targeting,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns bounded feature/task slices.

This file owns the missing architectural layer for:

- the world map,
- the shared spatial-object contracts that home-city work can reuse later,
- any future scrollable or pannable in-world surface that mixes fixed overlay UI with dynamic spatial content.

## 2. Why this is needed

The current selector architecture is correct for fixed UI controls:

- bottom navigation,
- fixed buttons,
- login fields,
- close buttons,
- top-right icons,
- stable overlay shortcuts,
- verification labels.

It is not the correct abstraction for content whose location changes because the camera moves or because objects are placed within a scrollable scene.

That distinction is now explicit.

Examples from the current game behavior:

- `PNC_HOME_WORLD_SWITCH`, `PNC_WORLD_HOME_NAV`, `PNC_WORLD_SEARCH_BUTTON`, and the coordinate bar are fixed overlay UI and should remain selector-driven.
- castles, alliance buildings, monsters, hell fortresses, altars, Dragonia, and resource nodes on the world map are not fixed selectors.
- home-city buildings and empty build slots also behave like scene objects rather than fixed overlay buttons.
- bag rows, event rows, gift rows, and store rows are dynamic collections, not fixed selectors and not spatial scene objects.

Recent live evidence confirms the gap:

- the automation can visually reach the world map on `BlueStacks App Player`,
- but the current detection path still treats the resulting screenshot as `UNKNOWN` when fixed world-map selectors are not recognized at a given resolution,
- which shows that the world-map problem is not only one of click geometry but of missing spatial-surface modeling.

## 3. Scope

This sub-plan defines:

- the canonical coexistence model between fixed selectors, dynamic collections, and spatial surfaces,
- the world-map domain model,
- the world-coordinate navigation model,
- the observation/runtime changes required to support spatial objects cleanly,
- the selector-registry extensions needed to support fixed world-map overlay UI without misusing selectors for map objects,
- the integration points with selector refinement, screen flows, and tasks.

This sub-plan does not:

- replace the canonical selector registry,
- collapse scrollable map objects into fixed selector ids,
- redesign all current tasks,
- require a fully complete world parser before bounded feature work can start,
- define the full home-city building navigation strategy or per-building workflows.

## 4. Core architectural decision

The automation should support exactly three canonical observation modalities.

### 4.1 Fixed selectors

Use selectors for UI elements whose screen-relative location is stable for a given screen contract.

Examples:

- bottom nav buttons,
- `PNC_HOME_WORLD_SWITCH`,
- `PNC_WORLD_HOME_NAV`,
- `PNC_WORLD_SEARCH_BUTTON`,
- coordinate bar anchor,
- popup close buttons,
- fixed tabs and overlay buttons.

These remain owned by:

- [`selector_registry.yaml`](/c:/Users/lebel/pnc/pnc_automation/vision/data/selector_registry.yaml),
- `UiElementId`,
- the selector catalog loader,
- selector refinement and click-outcome validation.

### 4.2 Dynamic collections

Use dynamic collections for repeated rows or tiles whose members are selected from currently visible structured entries.

Examples:

- bag item rows,
- build-catalog rows after tapping an empty home-city slot,
- event rows,
- gift rows,
- store rows,
- castle-selection rows,
- research rows.

These remain owned by:

- `DetectedListEntry`,
- `ListEntryKind`,
- screen-specific collection parsers.

### 4.3 Spatial surfaces

Use spatial surfaces for scrollable scenes where objects exist inside a camera viewport and are identified by map position, scene semantics, ownership, text, and local bounds.

Examples:

- world-map castles,
- alliance buildings,
- monsters,
- hell fortresses,
- altars,
- Dragonia,
- resource nodes,
- home-city buildings,
- home-city empty construction slots.

These must not be modeled as selectors or list rows.

## 5. Design principles

- One canonical implementation per concept.
- `UiElementId` remains fixed-UI only.
- `DetectedListEntry` remains repeated-list only.
- Spatial objects get one dedicated typed model instead of being forced into either of the other two models.
- The selector registry remains canonical, but it must grow to represent fixed overlay UI on spatial surfaces.
- Spatial-object definitions must reuse the same canonical catalog ownership boundary rather than inventing ad hoc task-local heuristics.
- If evidence is weak, screen classification or object classification must stay `UNKNOWN`.
- All cross-resolution handling must be normalized and fail fast on unsupported assumptions.

## 6. Vision

The target runtime should be able to:

1. open the world map through fixed selector-driven overlay UI,
2. read the current map coordinates from the fixed coordinate bar,
3. understand which world objects are currently visible and what they mean,
4. move the viewport toward a target coordinate without relying on absolute pixel tables for the map content,
5. select a visible world object by semantic query,
6. open object-specific interfaces such as Lord Info or gather confirmations,
7. return safely to home city via the fixed Home button.

The same typed spatial-object contracts may later support the home-city building scene, but Home City should not assume global `X/Y` coordinates unless the game actually exposes them, and it should not be forced into the world-map viewport model.

## 7. Canonical model

### 7.1 New observation types

The observation layer should gain a dedicated spatial-surface model.

Target types:

- `SpatialSurfaceType`
- `SpatialViewport`
- `SpatialViewportAddressingKind`
- `DetectedSpatialObject`
- `SpatialObjectKind`
- `SpatialObjectRelationship`
- `SpatialSurfaceObservation`

Recommended responsibilities:

- `SpatialSurfaceType`: distinguishes `WORLD_MAP` and later `HOME_CITY_SURFACE`.
- `SpatialViewport`: stores either absolute coordinate context or local camera context for the active surface.
- `SpatialViewportAddressingKind`: distinguishes coordinate-addressable surfaces from camera-relative surfaces.
- `DetectedSpatialObject`: stores one visible map/building object and its typed metadata.
- `SpatialObjectKind`: canonical object category such as `CASTLE`, `ALLIANCE_BUILDING`, `MONSTER`, `HELL_FORTRESS`, `RESOURCE_NODE`, `ALTAR`, `DRAGONIA`, `HOME_BUILDING`, `HOME_EMPTY_SLOT`.
- `SpatialObjectRelationship`: `SELF`, `ALLY`, `OTHER`, `NEUTRAL`, `UNKNOWN`.
- `SpatialSurfaceObservation`: stores the current surface type, viewport data, and visible spatial objects.

`Observation` should then contain:

- fixed `visible_elements`,
- dynamic `list_entries`,
- optional `spatial_surface`.

This keeps one canonical model per content shape.

### 7.2 Why a dedicated spatial-object model is required

Forcing world objects into selectors would create the wrong architecture:

- selectors imply canonical ids and stable screen-relative meaning,
- world objects are instance-level content that changes with camera position,
- many visible world objects share the same structure and differ only by type, name, alliance, level, and location,
- object queries are semantic, not enum-based.

Forcing world objects into `DetectedListEntry` would also be wrong:

- the world map is not a list,
- object order is not canonical,
- object identity is geometric and semantic, not row-based.

## 8. Registry design

### 8.1 Registry ownership rule

The canonical registry file should remain singular, but it must support both fixed selectors and spatial-surface definitions without creating a second disconnected source of truth.

Target direction:

- keep the existing `selectors:` section for fixed UI selectors,
- add a new `surfaces:` section to the same canonical catalog document for spatial-surface definitions.

This avoids:

- a second parallel registry file,
- duplicated geometry ownership,
- task-local hardcoded world parsing rules.

### 8.2 What stays in `selectors:`

The following world-map elements remain selectors because they are fixed overlay UI:

- `PNC_HOME_WORLD_SWITCH`
- `PNC_WORLD_HOME_NAV`
- `PNC_WORLD_SEARCH_BUTTON`
- `PNC_WORLD_COORDINATE_BAR`
- `PNC_WORLD_EXPAND_BUTTON`
- any future fixed overlay icon or fixed tool button

These selectors should prefer:

- normalized relative bounds,
- OCR-region anchoring where text is authoritative,
- screen-evidence-backed materialization rather than brittle full-resolution template dependence.

### 8.3 What moves into `surfaces:`

The following should be modeled as spatial objects, not selectors:

- player castle (`My Territory`),
- allied castles,
- other-alliance castles,
- alliance buildings,
- Dragonia,
- altar,
- monsters,
- hell fortresses,
- resource nodes,
- later, home-city buildings and empty slots.

The build-selection screen that appears after tapping an empty home-city slot should not live here. That screen is a structured UI screen and should be modeled through the existing collection/screen system.

### 8.4 Suggested `surfaces:` schema

Recommended shape:

```yaml
surfaces:
  - id: PNC_WORLD_MAP_SURFACE
    screen: PNC_WORLD_MAP
    viewport:
      addressing_kind: coordinate_bar
      coordinate_selector: PNC_WORLD_COORDINATE_BAR
      home_selector: PNC_WORLD_HOME_NAV
      optional_zoom_indicator_selector: PNC_WORLD_EXPAND_BUTTON
    object_kinds:
      - CASTLE
      - ALLIANCE_BUILDING
      - MONSTER
      - HELL_FORTRESS
      - RESOURCE_NODE
      - ALTAR
      - DRAGONIA
    relationship_rules:
      self_castle_label: "My Territory"
      ally_name_color_family: light_blue
      other_alliance_color_family: yellow
      self_color_family: deep_blue
```

The exact YAML shape may change, but the ownership boundary should not:

- fixed UI in `selectors`,
- scrollable scene semantics in `surfaces`,
- one canonical catalog file.

The same section should later support a home-city surface with a different viewport mode, for example:

```yaml
  - id: PNC_HOME_CITY_SURFACE
    screen: PNC_HOME_CITY
    viewport:
      addressing_kind: camera_relative
    object_kinds:
      - HOME_BUILDING
      - HOME_EMPTY_SLOT
```

## 9. World-map domain model

### 9.1 Viewport model

The world map should be modeled as one viewport over absolute kingdom coordinates.

Required viewport facts:

- current `x`,
- current `y`,
- artifact path,
- optional zoom bucket if it can be observed reliably,
- current surface screen evidence.

The coordinate display highlighted in the provided screenshots is the canonical source for current viewport location.

### 9.2 Home-city viewport model

Home City may reuse the shared spatial-object contracts, but it should be modeled as a camera-relative scene rather than an absolute coordinate plane.

Required home-city viewport facts should therefore be different:

- current camera state when inferable,
- stable anchor buildings or overlays currently visible,
- visible building and empty-slot objects,
- optional swipe history or recovery hints,
- no assumed global `X/Y` unless the client exposes one later.

This means the shared spatial architecture should support both:

- coordinate-addressable surfaces such as `WORLD_MAP`,
- camera-relative surfaces such as `HOME_CITY_SURFACE`.

However, only the first one requires viewport-to-world coordinate correspondence.

### 9.3 World-object metadata

Each visible world object should expose typed metadata where available.

Recommended fields:

- `kind`
- `relationship`
- `name_text`
- `alliance_tag`
- `level`
- `kingdom`
- `bounds`
- `action_point`
- `metadata`

Examples:

- player castle: `kind=CASTLE`, `relationship=SELF`, `name_text="My Territory"`
- ally castle: `kind=CASTLE`, `relationship=ALLY`, `alliance_tag="RST"`
- other-alliance castle: `kind=CASTLE`, `relationship=OTHER`
- Dragonia: `kind=DRAGONIA`
- Northern Altar: `kind=ALTAR`
- Enchanted Reptilian: `kind=MONSTER`, `level=29`
- resource node: `kind=RESOURCE_NODE`, resource subtype in metadata

### 9.4 Object relationship rules

The parser should use semantic ownership rules once, centrally:

- deep blue named castle with `My Territory` => self castle,
- light blue named castle/building => same alliance,
- yellow named castle/building => other alliance,
- neutral named monsters/resource nodes => neutral,
- anything ambiguous => `UNKNOWN`.

These rules must live in one canonical world-surface parser, not inside tasks.

## 10. Detection and parsing strategy

### 10.1 Fixed overlay detection

The world-map overlay should be recognized independently of object parsing.

Minimum overlay evidence should come from a combination of:

- `PNC_WORLD_HOME_NAV`,
- `PNC_WORLD_COORDINATE_BAR`,
- optional `PNC_WORLD_SEARCH_BUTTON`,
- OCR evidence that the coordinate bar contains `X:` and `Y:`.

The system should not require brittle template matches at one exact resolution before it can classify the world map.

### 10.2 Coordinate-bar parser

The coordinate bar should be parsed by a dedicated world-map OCR parser.

Responsibilities:

- locate or materialize the coordinate bar region,
- OCR the text,
- parse strict `X:<int> Y:<int>` values,
- emit `ScreenEvidence(ScreenType.PNC_WORLD_MAP, ...)` only when parsing is strong,
- populate `SpatialViewport`.

This parser should fail fast on malformed or partial coordinate strings.

### 10.3 Spatial-object parser

The world-map parser should then analyze the visible scene and extract typed spatial objects.

Detection inputs may include:

- OCR text anchors,
- color-family rules,
- local icon or silhouette matching,
- nameplates,
- level badges,
- alliance tags,
- stable layout cues around objects.

This parser must produce object instances, not selector ids.

### 10.4 Home-city spatial parser

The same object model can later be reused for the home-city scene for:

- tappable buildings,
- empty slots,
- city decorations that should be ignored,
- city-specific camera movement and focus logic without assuming absolute coordinates.

World map is the first required slice. Home-city building navigation should be treated as a separate follow-on planning problem, not as a forced extension of the world-coordinate slice.

### 10.5 Home-city building workflow boundary

The home-city building workflow should be split into two different models with a clear ownership boundary.

#### Empty-slot entry

- the empty slot visible on the city scene is a `DetectedSpatialObject` with `kind=HOME_EMPTY_SLOT`,
- its tap target belongs to the home-city spatial surface,
- selecting that slot opens the build-selection screen for that specific slot.

#### Build-selection screen

- the build-selection screen is not a spatial surface,
- it is a structured screen with repeated building options,
- those building options should reuse the existing dynamic-collection model, ideally `ListEntryKind.BUILDING`,
- each building entry should carry typed metadata such as building name, owned count, owned limit, and whether the entry is currently buildable,
- text such as `Requirements not met. Tap to view.` should be parsed as an unavailable or gated state, not ignored,
- page selectors or tab selectors on that screen remain fixed selectors if they are stable.

#### Existing-building entry

- an existing city building is a `DetectedSpatialObject` with `kind=HOME_BUILDING`,
- tapping it may open the already-known building-detail workflow,
- once the building-detail screen is open, existing fixed selectors such as the back button and upgrade button remain the correct abstraction.

This keeps one canonical ownership rule:

- city scene objects are spatial,
- build-menu entries are dynamic collection entries,
- building-detail buttons are fixed selectors.

## 11. Motion and navigation model

### 11.1 Fixed geometry rule

Fixed normalized geometry remains valid only for fixed overlay UI.

It is explicitly not the strategy for:

- world-map objects,
- home-city buildings,
- bag contents,
- event rows.

### 11.2 Coordinate-driven world navigation

World movement should be driven by the viewport coordinates, not by pre-recorded map object coordinates in screen pixels.

Target model:

1. read current coordinates,
2. compare them to desired target coordinates,
3. compute movement direction,
4. swipe the map,
5. reobserve coordinates,
6. repeat until target viewport is reached or until fail-fast limits are exceeded,
7. once the target area is visible, resolve the desired spatial object from the parsed visible objects.

### 11.3 Camera-relative home-city navigation

Home-city movement should not assume global coordinates.

Target model:

1. read the current fixed overlay state and visible spatial objects,
2. determine whether the desired building or empty slot is already visible,
3. if not, perform one canonical city-camera movement step,
4. reobserve the scene,
5. repeat until the target object is visible or the fail-fast limit is reached.

This is still a spatial-surface problem, but it is not a coordinate-bar problem and it does not require any viewport-to-world coordinate conversion.

### 11.4 Motion controller

The runtime should gain one canonical `SpatialSurfaceNavigator` contract with per-surface strategies such as `WorldMapNavigator` and, if still justified after dedicated design work, a home-city navigator.

Responsibilities:

- consume the current `SpatialViewport`,
- delegate to the addressing mode supported by the current surface,
- use coordinate deltas on coordinate-addressable surfaces,
- use camera-relative reobservation on non-coordinate surfaces,
- stop when the target condition is reached,
- fail fast when movement evidence is unreadable or inconsistent.

Tasks must not implement their own swipe loops.

### 11.5 Search integration

If the world search UI becomes reliable later, it should be integrated as an optimization, not as the only navigation path.

The canonical model should still support coordinate-driven movement even without search.

## 12. Screen-flow integration

This plan does not replace [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md). It defines the missing architecture that those flows should consume.

### 12.1 Flows that remain canonical in the screen-flow plan

- `open_world_map()`
- `ensure_home_city()`
- `return_to_safe_root_screen()`
- `close_blocking_popup()`

### 12.2 New canonical flow candidates enabled by this plan

- `ensure_world_map_ready()`
- `focus_world_coordinate(target_coordinate)`
- `find_visible_world_object(query)`
- `open_world_object_lord_info(query)`
- `return_home_city_from_world_map()`
- `open_home_city_empty_slot(query)`

Promotion rule:

- flow ownership stays in the screen-flow plan,
- this document owns the spatial model those flows consume.

The full home-city build-catalog and building-detail workflow should move to a dedicated follow-on plan once building-specific constraints are documented.

## 13. Task integration

This plan does not replace [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md). It defines the missing observation/runtime layer those tasks should consume.

### 13.1 Gathering task impact

Current gathering logic assumes `ListEntryKind.GATHER_NODE`, which is not the right long-term model for world-map nodes.

Target change:

- gathering should consume `DetectedSpatialObject` with `kind=RESOURCE_NODE`,
- the flow should navigate to the correct map area before evaluating visible candidate nodes,
- the task should choose from visible spatial objects instead of pretending the world map is a list screen.

### 13.2 Lord Info from world map

A future feature slice should support:

- finding a visible castle object,
- tapping it,
- opening the castle interaction UI,
- entering Lord Info when that path is supported,
- verifying the result with the existing Lord Info screen model.

### 13.3 Home-city building tasks

Building upgrade and construction work should eventually consume:

- fixed overlay selectors for city UI chrome,
- spatial objects for buildings and empty slots,
- dynamic collection entries for the build-selection screen opened from an empty slot,
- building-detail selectors only after the building scene has been navigated correctly through camera-relative scene navigation.

The intended home-city building flow should be documented in a separate home-city building plan because some buildings are unique and some workflows are slot-specific. This document only defines the boundary that future work should respect:

1. city navigation should be camera-relative and visibility-driven,
2. empty slots and existing buildings may share the same base spatial-object model,
3. build-catalog entries should remain dynamic collection entries rather than spatial objects,
4. building-specific uniqueness and per-building workflows should be designed explicitly instead of generalized prematurely.

## 14. Selector-refinement integration

This plan depends on [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md) and refines its ownership boundary.

Required refinement increments:

- promote the fixed world-map overlay controls to geometry-backed, cross-resolution-safe selectors,
- add world-map coordinate-bar OCR coverage,
- collect positive and negative fixtures for world-map classification,
- add parser fixtures for player castle, ally castle, other-alliance castle, alliance buildings, Dragonia, altar, monsters, hell fortresses, and resource nodes,
- validate that home-city buildings are treated as scene content rather than as fixed selectors when that slice is implemented.

Refinement rule:

- selector refinement owns fixed overlay maturity,
- spatial-surface refinement owns surface fixtures and parser maturity,
- both remain under one canonical catalog and one observation system.

## 15. Fail-fast validation rules

- Never classify the world map from one weak cue alone.
- Never trust coordinate OCR that does not parse into strict integers.
- Never treat an ambiguous colored label as a typed world object without supporting evidence.
- Never let tasks or flows guess whether a world object is self, ally, other, or neutral.
- Never encode dynamic scene objects as new `UiElementId` members.
- Never let feature code implement its own coordinate-swiping logic outside the canonical navigator.

## 16. Implementation plan

### Phase A: Formalize the spatial observation model

- add typed spatial-surface classes to the observation layer,
- add observation helpers for visible spatial objects,
- keep existing selector and list-entry contracts unchanged,
- add fail-fast validation for invalid surface/object metadata.

Exit condition:

- the runtime can represent spatial surfaces without abusing selectors or list entries.

### Phase B: Harden fixed world-map overlay detection

- convert `PNC_WORLD_HOME_NAV`, `PNC_WORLD_SEARCH_BUTTON`, and `PNC_WORLD_COORDINATE_BAR` to cross-resolution-safe detection,
- reduce reliance on exact template scale,
- add strong world-map screen evidence from the coordinate parser.

Exit condition:

- both configured BlueStacks instances can classify the world map reliably.

### Phase C: Implement the world-map surface parser

- parse coordinates,
- detect and classify visible world objects,
- populate `SpatialSurfaceObservation` for `PNC_WORLD_MAP`,
- add screenshot fixtures covering the provided object classes.

Exit condition:

- the observation layer can describe the current world viewport and visible world objects.

### Phase D: Implement the world-map navigator

- add coordinate-driven viewport movement,
- calibrate swipe effects from observed coordinate deltas,
- add fail-fast movement bounds,
- expose one canonical world-navigation interface to flows/tasks.

Exit condition:

- the runtime can move from one world coordinate region to another without hardcoded object pixel tables.

### Phase E: Integrate one tracer-bullet feature

Recommended first slice:

- open world map,
- verify current coordinates,
- detect the self castle,
- tap Home to return,
- then expand to one visible-castle Lord Info open or one visible resource-node selection.

Exit condition:

- one bounded spatial feature works end to end with recorded live evidence.

### Phase F: Split home-city building work into a separate follow-on plan

- keep the shared spatial-object contracts reusable by home-city work,
- explicitly do not require viewport-to-world coordinate conversion for home city,
- define home-city navigation around camera scrolling and object visibility only,
- design unique-building and slot-specific workflows in a dedicated plan rather than forcing them into the world-map slice.

Exit condition:

- the world-map slice is complete without overclaiming home-city building completeness, and the follow-on home-city planning boundary is explicit.

## 17. Validation gate

No spatial-surface slice should be considered complete without all of the following:

- unit coverage for coordinate parsing and typed classification helpers where the surface is coordinate-addressable,
- screenshot coverage for world-map overlay detection on both supported resolutions,
- screenshot coverage for positive and negative object classification,
- live smoke validation for `home city -> world map -> home city`,
- live smoke validation for at least one coordinate-driven navigation increment,
- live smoke validation for at least one camera-relative home-city scene increment once the separate home-city slice starts,
- artifacts captured on every mismatch.

## 18. Definition of done

This sub-plan is done only when:

- fixed overlay world-map UI is registry-backed and cross-resolution-safe,
- the world map is classified through strong evidence instead of brittle template coincidence,
- scrollable world objects are represented as spatial objects rather than selectors,
- world movement is coordinate-driven through the canonical spatial navigator where coordinates exist,
- at least one bounded feature uses the spatial model end to end,
- the shared spatial-object contracts are reusable by a future home-city plan without forcing a world-coordinate model onto city navigation,
- no parallel selector-like special-case system was introduced.

## 19. Relationship to other plans

- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md) should request and validate the fixed overlay selectors and parser fixtures required here.
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md) should own the reusable flows that consume this spatial model.
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md) should consume this spatial model for gathering and Lord Info from world map, while home-city building work should be specified by a dedicated follow-on plan.
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) should continue using only the reusable flows and selectors it actually needs.

## 20. Recommended immediate next increment

The next clean implementation increment should be:

1. add `PNC_SPATIAL_SURFACE_SUBPLAN.md` as the canonical design reference,
2. harden fixed world-map overlay selectors for both configured BlueStacks resolutions,
3. implement a strict coordinate-bar parser that can classify `PNC_WORLD_MAP`,
4. add one `SpatialSurfaceObservation` model for `WORLD_MAP`,
5. validate the existing `home city -> world map -> home city` round-trip against that stronger evidence.

That is the smallest coherent slice that improves the architecture without overcommitting to a full world-object parser immediately.
