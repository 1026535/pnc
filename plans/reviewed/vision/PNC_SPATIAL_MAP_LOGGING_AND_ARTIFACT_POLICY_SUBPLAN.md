# PNC Spatial Map Logging And Shared Artifact Policy Sub-Plan

## Summary

This document defines a bounded debugging-focused refactor that adds a durable world-map survey dump and replaces the current screenshot-only persistence toggle with one shared, extensible artifact-selection model.

The goal is to solve two related problems without collapsing responsibilities:

- repeated world-map survey loops should be able to persist the semantic state they accumulated, not only raw screenshot files,
- routine observation persistence should be controlled by one shared higher-level artifact-selection model instead of one screenshot-specific boolean.

This slice is explicitly for debugging and diagnostics, not long-term archive retention. The new world-map survey dumps should therefore live under the runtime `artifacts` tree, not under durable `archives`.

The design must keep one canonical implementation per concept:

- screenshot capture remains responsible only for screenshot bytes and optional screenshot persistence,
- world-map survey/index components remain responsible for world-map semantic state,
- a shared runtime artifact-selection model remains responsible for deciding which debug artifact kinds are enabled for one observation flow.

## Core Decisions

### 1. Use extensible artifact kinds, not a fixed four-mode enum

Do not introduce a fixed `NONE/SCREENSHOT/SPATIAL_MAP/ALL` enum.

Instead, add one shared artifact-kind model in the runtime/observation layer:

- `ObservationArtifactKind.SCREENSHOT`
- `ObservationArtifactKind.WORLD_MAP_SURVEY_STATE`

The effective routine artifact selection should be represented as a set-like value, for example:

- `frozenset[ObservationArtifactKind]`, or
- an equivalent flags-based model.

This keeps the design open for future debug artifact kinds without reshaping the public contract again when another observation artifact type is added later.

Initial default behavior:

- `ObservationMode.DEBUG` defaults to `{SCREENSHOT}`,
- `ObservationMode.LIGHT` defaults to `{}`,
- world-map survey-state dumps are opt-in, not part of the default runtime mode.

### 2. Keep screenshot capture screenshot-specific

`ScreenshotService.capture(...)` must remain screenshot-only.

Required behavior:

- keep its `persist` input as a simple boolean,
- derive that boolean from the resolved higher-level artifact selection before calling into screenshot capture,
- do not add world-map branches, survey enums, or semantic logging responsibilities into screenshot capture or generic artifact byte storage.

This preserves the clean current separation between:

- `BlueStacksSession.capture_screenshot_bytes()`,
- screenshot decoding,
- screenshot file persistence.

### 3. World-map dumps are checkpointed survey outputs, not generic observation side effects

World-map survey-state dumps must not be treated as a generic per-observation side effect.

They should only be written at explicit world-map survey/checkpoint boundaries, after the accumulated state has been ingested into the canonical survey index.

Recommended ownership:

- add one small world-map survey recorder/checkpoint component around `WorldMapSurveyIndex`,
- that component owns:
  - ingesting repeated observations into the index,
  - deciding when one checkpoint should be written,
  - delegating persistence of the debug dump to a dedicated store.

`ObservationService` should remain observation-scoped. It may contribute the screenshot artifact path and capture timestamp, but it must not become the owner of accumulated world-map survey-state logging.

### 4. Persist the internal survey/index state exactly, through an index-owned export seam

Because this is a debugging tool, the persisted world-map dump should intentionally mirror the live `WorldMapSurveyIndex` state rather than reduce it to a simplified business schema.

However, the store should not serialize private mutable structures directly.

Required design:

- `WorldMapSurveyIndex` must own one canonical export seam, for example `snapshot()` or `to_debug_document()`,
- that export must be isomorphic to the internal debug state we care about,
- the persistence store must only write the exported snapshot/document to disk.

The export must preserve the meaningful internal state already stored by the index, including:

- index order,
- full `WorldMapObjectKey` content,
- full `WorldMapObjectSighting` content,
- linked screenshot artifact paths,
- linked profile artifact paths,
- timestamps,
- current checkpoint viewport metadata.

The store must not rebuild the survey state from raw observations, and it must not reinterpret or compress the indexed evidence into a different semantic model.

## Implementation Changes

### 1. Shared runtime artifact selection

Add one shared artifact-selection type and one shared resolver in the runtime/observation layer.

Recommended public shape:

- `ObservationRequest` replaces `persist_artifact: bool | None` with an optional artifact-selection override,
- `None` means "use the mode default",
- an empty selection means "explicitly persist no routine artifacts",
- non-empty selections explicitly request the included artifact kinds.

Recommended resolution precedence:

1. explicit call-site override when provided,
2. else request override,
3. else runtime mode default.

The resolved selection is then consumed by the relevant owners:

- screenshot persistence enablement goes to `ObservationService` / `ScreenshotService`,
- world-map survey-state enablement goes to the world-map survey recorder/checkpoint path.

The current screenshot-only boolean policy surface should be removed after the refactor so there is only one canonical routine artifact-selection model.

### 2. Observation mode remains a default source, not an artifact family

`ObservationMode` should remain a coarse runtime default source, not a replacement for artifact-kind selection.

Required behavior:

- keep `DEBUG` and `LIGHT` as the user-facing runtime modes,
- map each mode to a default artifact selection,
- do not overload `ObservationMode` with world-map-specific or future artifact-kind-specific semantics.

### 3. Add a dedicated world-map survey debug store under P&C persistence

Add one new persistence component for world-map survey debug dumps alongside the other P&C persistence helpers.

Recommended responsibility:

- persist one structured debug dump per completed survey iteration/checkpoint,
- write JSON under the runtime `artifacts` tree,
- use directory naming consistent with existing artifact naming helpers.

Recommended path shape:

- `artifacts/<date>/<artifact_directory>/world_map_surveys/<timestamp>_<label>.json`

Recommended output shape:

- JSON,
- one file per survey iteration/checkpoint,
- include `schema_version`,
- include enough metadata to understand the capture context without reopening screenshots.

This store is for debug output only. It should not be placed under `archive_root`.

### 4. Add an exact debug snapshot export from `WorldMapSurveyIndex`

Add one export owned by `WorldMapSurveyIndex`, for example:

- `snapshot(...) -> WorldMapSurveySnapshot`, or
- `to_debug_document(...) -> dict[str, object]`.

The exported data should be intentionally close to the live internal state and should not hide important evidence distinctions.

Recommended minimum payload:

- `schema_version`,
- checkpoint metadata:
  - artifact directory key,
  - label/reason,
  - timestamp,
  - surface type,
- checkpoint viewport metadata:
  - current world coordinate,
  - viewport addressing kind,
- ordered indexed sightings:
  - full serialized `WorldMapObjectKey`,
  - full serialized `WorldMapObjectSighting`,
  - latest visible object metadata already stored by the index,
  - linked screenshot/profile artifact paths when present.

Required evidence rules:

- confirmed-world, estimated-world, and viewport-relative addressing kinds must stay explicit,
- viewport-offset evidence must remain explicit when present,
- repeated sightings must appear as the current canonical indexed entry, not duplicated historical reconstructions.

### 5. Add a small world-map survey recorder/checkpoint owner

Add one small component that owns the survey-local mutable flow around `WorldMapSurveyIndex`.

Recommended responsibilities:

- ingest one observation into the canonical index,
- keep the latest checkpoint metadata needed for debug dumps,
- persist one checkpoint dump when the resolved artifact selection includes `WORLD_MAP_SURVEY_STATE`,
- optionally link to the current screenshot artifact path when `SCREENSHOT` is also enabled.

This keeps the logging boundary where the semantic survey state actually exists instead of forcing `ObservationService` to know about accumulated world-map survey ownership.

### 6. Keep existing screenshot-derived debug sidecars out of scope for this slice

This slice should only introduce the shared selection model for:

- `SCREENSHOT`,
- `WORLD_MAP_SURVEY_STATE`.

Existing screenshot-derived debug sidecars should remain unchanged for now. They can be folded into the shared artifact-kind model later if that becomes useful, but this refactor should stay bounded.

## Public Interface Changes

The implementation should introduce or update the following public-facing contracts:

- replace `ObservationRequest.persist_artifact: bool | None` with an optional shared artifact-selection override,
- add one shared `ObservationArtifactKind` type in the runtime observation layer,
- add one shared artifact-selection resolver or equivalent canonical helper,
- add one `WorldMapSurveyIndex` export seam for exact debug snapshot/document generation,
- add one world-map survey debug store API that writes the exported index-owned snapshot/document,
- add one world-map survey recorder/checkpoint helper that owns survey-local ingestion plus checkpoint persistence.

No public change should be made to `ScreenshotService` beyond continuing to receive one already-resolved screenshot boolean.

## Failure-Mode Rules

The new design must fail fast on invalid usage.

Required rules:

- if world-map survey-state dumping is requested outside a world-map survey/checkpoint boundary, do not silently pretend it was satisfied,
- do not let the store rebuild or invent survey state from raw observations,
- do not infer or backfill fake map coordinates from unrelated screens,
- do not collapse confirmed, estimated, and viewport-relative evidence into one ambiguous coordinate model,
- keep failure screenshot capture explicit and centralized so task failures still surface actionable visual evidence even when routine artifact selection does not include screenshots.

## Test Plan

Add focused tests that lock down both the shared artifact-selection resolution and the exact world-map debug dump payload.

Required scenarios:

- artifact-selection resolution defaults:
  - debug mode resolves to `{SCREENSHOT}`,
  - light mode resolves to `{}`,
  - request-level override wins over mode default,
  - explicit call-site override wins over request override.
- screenshot-only path:
  - screenshot artifacts persist,
  - no world-map survey dump is written.
- world-map-survey-state-only path:
  - no screenshot artifact is written,
  - one world-map survey dump is written at a valid checkpoint boundary.
- combined path:
  - both screenshot artifact and world-map survey dump are written,
  - the survey dump links to screenshot artifact paths when available.
- none path:
  - routine observation writes no screenshot artifact,
  - no world-map survey dump is written.
- failure path:
  - forced task-failure screenshot persistence still works even when the routine artifact selection is empty or contains only `WORLD_MAP_SURVEY_STATE`.
- index dump correctness:
  - dump order matches index order,
  - confirmed-world and estimated-world keys stay distinguishable,
  - viewport-relative objects preserve viewport-offset evidence,
  - latest screenshot/profile artifact linkage is preserved,
  - repeated sightings update the canonical indexed entry instead of duplicating contradictory records.
- invalid usage:
  - requesting `WORLD_MAP_SURVEY_STATE` without a valid survey/checkpoint owner fails fast.

## Assumptions

- the first target is world-map survey-state debugging, not home-city atlas logging,
- the world-map dump is a debug artifact under `artifacts`, not a durable archive under `archives`,
- the dump should mirror the live internal survey/index state closely because this tool is for debugging,
- the shared artifact-selection model must remain open for future artifact kinds without another shape change,
- screenshot persistence and world-map survey-state dumping remain separate responsibilities even though they are selected through one shared higher-level model.
