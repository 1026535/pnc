# PNC Spatial Map Logging And Shared Artifact Policy Sub-Plan

## Summary

This document defines a bounded refactor that adds a durable logging path for world-map `x,y` survey results and introduces one shared higher-level switch that controls whether runtime observation persistence produces screenshot artifacts, spatial-map logs, both, or neither.

The goal is to solve two related problems with one clean ownership model:

- repeated spatial survey loops should be able to persist the semantic `x,y` map they discovered instead of only raw screenshot artifacts,
- persistence policy should be decided above screenshot capture so the runtime can choose the right diagnostic output without overloading screenshot-specific APIs.

The design must keep one canonical implementation per concept:

- screenshot capture remains responsible only for screenshot bytes and optional screenshot file persistence,
- world-map survey/index components remain responsible for map-coordinate semantics,
- observation/runtime policy remains responsible for deciding which artifact families are enabled for one observation or scan.

## Core Decision

Introduce one shared artifact policy at the observation/request layer instead of extending `ScreenshotService.persist` into a multi-meaning enum.

That shared policy must support four modes:

- `NONE`: do not persist routine runtime artifacts,
- `SCREENSHOT`: persist screenshot artifacts only,
- `SPATIAL_MAP`: persist spatial-map logs only,
- `ALL`: persist both screenshot artifacts and spatial-map logs.

This shared policy becomes the canonical switch used by runtime observation and spatial survey flows.

The screenshot service must continue to answer only one question: "should this screenshot payload be written to disk?" It must not learn about spatial-map logging.

The world-map `x,y` logging must be owned by the world-map spatial/index layer because that layer already owns:

- coordinate-addressable viewport semantics,
- deduplicated map-object keys,
- accumulated survey results across repeated observations,
- object evidence such as viewport coordinates and optional artifact linkage.

## Implementation Changes

### 1. Shared observation-level artifact policy

Add one new shared artifact-policy type under the runtime/observation layer and use it as the single canonical persistence switch.

Target behavior:

- `ObservationRequest` gains an optional artifact-policy override instead of the current screenshot-only `persist_artifact` boolean.
- `ObservationService` resolves an effective artifact policy from:
  - an explicit call-site override when provided,
  - else the request override,
  - else the runtime observation mode default.
- the resolved policy is then split into:
  - screenshot persistence enablement,
  - spatial-map logging enablement.

The current screenshot-only boolean path should be removed after the refactor so there is only one persistence policy surface.

### 2. Screenshot persistence remains screenshot-specific

Keep `ScreenshotService.capture(...)` as a screenshot-only service.

Required behavior:

- keep its `persist` input as a simple boolean,
- derive that boolean from the higher-level artifact policy before calling into the screenshot service,
- do not add spatial-map logging branches, enums, or map-specific behavior into screenshot capture or generic artifact storage.

This preserves the clean current separation between:

- `BlueStacksSession.capture_screenshot_bytes()`,
- screenshot decoding,
- screenshot artifact persistence.

### 3. Add a dedicated spatial-map log store

Add one new durable persistence component for world-map survey logs. It should live alongside other P&C persistence helpers, not inside generic screenshot storage.

Recommended responsibility:

- persist one structured snapshot of the accumulated world-map survey/index state after an iteration or checkpoint,
- record the active viewport coordinate,
- record the indexed sightings and their canonical keys,
- record the observation timestamp,
- optionally record linked screenshot artifact paths when screenshot persistence is also enabled.

Recommended output shape:

- JSON, because it is easy to diff, inspect, and feed back into debugging tools,
- one file per completed survey iteration/checkpoint rather than one file per visible object,
- per-account/per-castle directory naming consistent with the existing artifact/archive naming conventions.

The new store should consume the canonical survey/index model rather than rebuilding the `x,y` map from raw observations.

### 4. World-map survey/index owns the semantic log payload

The map logging data should be emitted from the world-map survey/index path, centered on `WorldMapSurveyIndex` and related spatial-surface structures.

Required behavior:

- the log payload must be derived from the canonical indexed sightings already accumulated by the survey/index,
- the persisted file should capture enough information to reconstruct the discovered map state without rereading screenshots,
- object keys and addressing-kind distinctions must stay explicit so the log does not collapse confirmed, estimated, and viewport-relative evidence into one ambiguous coordinate model.

Recommended minimum payload:

- capture metadata: account/castle artifact directory key, timestamp, surface type,
- viewport metadata: current world coordinate and addressing kind,
- indexed objects:
  - object kind,
  - object key,
  - latest viewport coordinate,
  - confirmed or estimated world coordinate when present,
  - viewport offset ratio when relevant,
  - name/alliance/kingdom/level metadata when present,
  - linked screenshot/profile artifact paths when available.

### 5. Shared policy integration points

The higher-level policy must be usable from both routine observation flows and spatial survey loops.

Target integration points:

- generic observation capture through `ObservationService`,
- world-map scan/survey helpers that iterate across multiple observations,
- any future home-city spatial atlas/index flow if it later needs its own semantic logging.

Required defaults:

- current debug behavior should continue to default to screenshot persistence unless a caller explicitly asks for another policy,
- lightweight or scheduler-style flows should be able to choose `NONE` or `SPATIAL_MAP` without paying screenshot-artifact cost,
- failure capture should remain explicit and centralized: task-failure paths may still force a screenshot artifact even when routine policy would not.

### 6. Failure-mode rules

The new policy must fail fast on invalid or unsupported combinations.

Required rules:

- if spatial-map logging is requested for an observation/flow that does not produce a coordinate-addressable world-map survey state, do not silently no-op; either skip only at an explicitly guarded survey boundary or raise an implementation-time error for invalid direct usage,
- do not let spatial-map logging pretend it succeeded when no survey/index snapshot exists,
- do not infer or backfill fake map coordinates from unrelated screens,
- keep screenshot-failure diagnostics explicit so task failures still surface actionable visual evidence.

## Public Interface Changes

The implementation should introduce or update the following public-facing contracts:

- replace `ObservationRequest.persist_artifact: bool | None` with a shared artifact-policy field,
- add one shared artifact-policy enum/type in the runtime observation layer,
- add one world-map log store API that accepts a canonical survey/index snapshot and persists it,
- update observation/survey call sites to request artifact behavior through the shared policy instead of a screenshot-only boolean.

No changes should be made to the public contract of `ScreenshotService` beyond receiving the already-resolved screenshot boolean from above.

## Test Plan

Add focused tests that lock down both the policy resolution and the world-map log payload.

Required scenarios:

- artifact-policy resolution defaults:
  - debug mode resolves to screenshot persistence by default,
  - lightweight mode can resolve to no routine persistence,
  - request-level policy overrides mode defaults,
  - call-site explicit override wins over request policy.
- screenshot-only path:
  - screenshot artifacts persist,
  - no spatial-map log is written.
- spatial-map-only path:
  - no screenshot artifact is written,
  - one structured world-map log is written from the indexed survey state.
- all-artifacts path:
  - both screenshot artifact and spatial-map log are written,
  - spatial log links to screenshot artifact paths when available.
- none path:
  - routine observation writes neither screenshot nor spatial-map artifacts.
- failure path:
  - forced task-failure screenshot persistence still works even when routine policy is `NONE` or `SPATIAL_MAP`.
- spatial payload correctness:
  - confirmed-world and estimated-world keys stay distinguishable in the persisted JSON,
  - viewport-relative objects preserve viewport-offset evidence,
  - repeated sightings update the canonical indexed object entry instead of duplicating inconsistent records.

## Assumptions

- the first target is the world map, not home-city atlas logging.
- the durable `x,y` log is intended to represent semantic survey state after iteration/checkpoint, not a raw per-frame dump of every observation.
- JSON is the preferred initial file format for the spatial-map log.
- screenshot persistence and spatial-map logging are parallel artifact families controlled by one shared higher-level policy, but they remain implemented by separate components with separate ownership.
