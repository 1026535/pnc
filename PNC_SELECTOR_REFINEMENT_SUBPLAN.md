# Step 3: Puzzles & Conquest Selector Refinement Sub-Plan

## 1. Purpose

This document is the dependency-ordered third plan and covers iterative selector-registry refinement.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which covers account-specific bootstrap and castle-targeting behavior,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which covers concrete task behavior,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which covers reusable navigation flows,
- [PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SPATIAL_SURFACE_SUBPLAN.md), which covers scrollable world-map and home-city spatial-surface modeling,
- [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md), which covers orchestration.

This file owns the detailed work for former Phase 2 and Phase 2.5 from [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md).

Those two phases are now considered closed in the primary implementation plan, and any follow-on work stays here as selector maintenance and refinement.

This file therefore owns selector discovery, observation-baseline refinement, click-mapping, and registry refinement.

## 2. Why this exists

The screenshots currently provided are useful but incomplete. They are sufficient to seed the selector registry, but not to finish it.

Selector refinement must therefore be an explicit phase, not an implicit assumption.

That is especially important for:

- unique building interfaces reachable from the home city,
- empty building slots that open build menus,
- modal screens that only appear after a click,
- rotating UI states where the clickable source is stable but the destination varies slightly,
- any screen that cannot be modeled correctly from static screenshots alone.

## 3. Former implementation phases now owned here

### Former Phase 2: P&C observation baseline

- build selector registry,
- implement screen classification for Android home, P&C login, popup, and home city,
- add OCR for narrow required regions,
- produce typed observations.

Exit condition:

- the tool can reliably tell whether it is at Android home, P&C login, a popup, or P&C home city.

Status:

- closed in the primary implementation plan,
- future adjustments stay in this sub-plan as refinement work, not as a reopened platform phase.

### Former Phase 2.5: Selector refinement

- run a primary discovery phase to expand the registry with more visible and candidate-clickable elements,
- refine screenshot-seeded selectors through controlled click mapping,
- document source-screen to destination-screen transitions,
- add missing selectors for unique home-city buildings,
- add missing selectors for empty building slots and construction menus,
- advance high-value selectors from `planned` or `screenshot_seeded` to validated statuses.

Exit condition:

- the high-priority selectors required by the next implementation phases are click-mapped and interaction-validated.
- live smoke validation has confirmed that the current registry can successfully detect and safely navigate the real P&C UI for a small set of representative flows.

Status:

- closed in the primary implementation plan,
- runtime registry loading now reads from a static selector catalog rather than hardcoded seed tables,
- an offline registry-update script now exists and owns writes to the static catalog plus selector-id definitions,
- a reviewed selector-discovery script now exists and can analyze saved artifacts or stage live-assisted probe evidence into report/spec outputs without mutating the static catalog,
- automated tests now cover the offline updater and the catalog-backed registry loader,
- targeted live smoke validation completed on 2026-03-09 and 2026-03-10 on both configured BlueStacks instances after correcting the first-instance ADB port from `127.0.0.1:5555` to `127.0.0.1:5556`,
- future selector work stays here as ongoing registry refinement and validation maintenance.

## 4. Scope

This sub-plan should define:

- how candidate selectors are discovered,
- how a primary discovery pass expands the registry before deeper validation starts,
- how clickable UI elements are mapped to resulting screens or state changes,
- how selectors move from planned to validated status,
- how screenshot and click artifacts are staged for offline refinement,
- how missing screens are requested and documented,
- how unique building and empty-slot interactions are refined,
- how OCR output is normalized into reusable text anchors and screen evidence,
- how selector metadata is updated without duplicating definitions,
- how the offline registry-update script applies reviewed changes to the static catalog.

## 5. Refinement principles

- The canonical registry remains singular.
- Refinement updates the canonical registry; it does not create a second registry.
- Runtime registry population remains static from one canonical catalog.
- Live automation must never mutate registry files or auto-add selectors during execution.
- Registry writes must happen only through a separate offline update script.
- A selector is not fully trusted until its click outcome is mapped and verified.
- If a UI element is dynamic in content but stable in structure, refine the collection selector, not a temporary row id.
- Unknown click outcomes must be captured with artifacts and documented before automation relies on them.

### 5.1 Static catalog and offline updater target

The runtime should load selectors from one static catalog, and that catalog remains the only registry source of truth.

Target shape:

- `build_default_selector_registry` loads one static catalog file and produces the in-memory typed registry.
- Selector ids remain canonical static definitions, not runtime-discovered strings.
- A separate offline update script owns edits to the static catalog and selector-id definitions.
- The offline script consumes reviewed refinement inputs, such as source screenshots, post-click screenshots, and an explicit update spec.
- The offline script may add missing selectors, merge additional source screens, and promote selector status forward, but it must reject duplicate ids, invalid screens, and backward status changes.
- Runtime observation, classification, and tasks continue consuming only the static registry produced at startup.

Current implemented baseline:

- `build_default_selector_registry` now loads the runtime registry from `pnc_automation/vision/data/selector_registry.yaml`.
- Static catalog loading and validation now live in `pnc_automation/vision/selector_catalog.py`.
- Offline catalog and enum updates now live in `pnc_automation/vision/selector_registry_updater.py`.
- The current command-line entry point for reviewed registry writes is `tools/update_selector_registry.py`.
- Reviewed selector discovery now lives in `pnc_automation/vision/selector_discovery.py`.
- The current command-line entry point for staged discovery is `tools/discover_selector_registry.py`.
- Discovery can analyze saved screenshot artifacts, optionally add safe live-connected click probes, and emit a reviewable report plus update spec without mutating the canonical catalog.

### 5.2 OCR and text-evidence architecture target

The current line-based OCR fallbacks are an acceptable bootstrap only. Refinement should move the vision stack toward a stricter evidence model.

Target shape:

- `OcrService` remains the single OCR abstraction, but it should expose richer OCR results, ideally including word-level boxes in addition to line-level groupings.
- OCR backend choice stays behind that contract. RapidOCR may remain the first backend, but a stronger existing OCR library can replace it without changing downstream consumers.
- A canonical `TextAnchorDetector` should normalize OCR output and map words or phrases such as `Upgrade`, `Alliance`, `More`, `Manage Char`, kingdom labels, and similar stable UI text into typed anchors.
- Text normalization, synonym handling, and tolerant matching must live in that detector once, not be reimplemented inside each screen parser.
- Screen-specific parsers should consume typed text anchors together with visual selectors or layout cues and emit typed screen evidence.
- `ScreenClassifier` should classify from aggregated screen evidence, not from ad hoc OCR fallbacks that directly override the screen from a couple of loose text hits.
- If evidence is partial or ambiguous, the result must remain `UNKNOWN`.
- Synthetic clickable selectors must only be emitted when the parser has strong enough evidence for the target screen and the click target geometry is justified by that screen contract.

### 5.3 Parser ownership rules

- OCR extraction owns raw text and localization only.
- `TextAnchorDetector` owns normalization and typed text-anchor creation.
- Screen parsers own screen-specific interpretation of those anchors.
- `ScreenClassifier` owns the final screen decision from accumulated evidence.
- Automation tasks must continue consuming only typed observations, never raw OCR output.

## 6. Selector lifecycle

Each selector should move through explicit statuses:

- `planned`
- `screenshot_seeded`
- `click_mapped`
- `interaction_validated`
- `task_validated`

Meaning:

- `planned`: known to be needed, but not yet grounded in screenshots.
- `screenshot_seeded`: visible in screenshots and named in the registry.
- `click_mapped`: the result of clicking it is known and documented.
- `interaction_validated`: detection and click target are reliable enough for general use.
- `task_validated`: the selector has been proven inside at least one end-to-end task flow.

## 6.1 Primary discovery phase

Selector refinement should start with a broad discovery phase whose first goal is to expand registry coverage, not to fully validate every selector immediately.

Purpose:

- find more visible registry candidates from screenshots before flow-specific work narrows the focus,
- identify clickable text labels, icons, buildings, empty slots, tabs, buttons, and repeated rows that are not yet represented canonically,
- stage reviewed candidates for later click mapping and interaction validation.

Rules:

- discovery should prioritize breadth first across important screens before deep validation of one branch,
- discovery may use screenshots, OCR anchors, controlled click probes, and resulting screenshots to surface missing selectors,
- every newly discovered candidate must be recorded with artifacts and proposed through the offline registry-update path,
- discovery should distinguish between stable canonical selectors and dynamic collection entries,
- discovery should not treat temporary event names or one-off content labels as permanent selector ids unless repeat evidence proves they are structurally stable.

Exit condition:

- the registry has broad enough coverage that the main clickable surfaces on the prioritized screens are represented canonically or intentionally modeled as dynamic collections,
- the remaining gaps are narrow, documented, and ready for targeted click-mapping work.

## 7. Per-selector refinement template

Each selector refinement entry should capture:

### Selector id

- canonical selector name.

### Source screen

- required `ScreenType`,
- required preconditions.

### Detection basis

- template, OCR region, anchored region, or collection element.

### Click mapping

- where the click lands,
- expected resulting screen or state,
- alternate known outcomes if the UI varies.

### Verification

- which selectors or OCR fields prove the click succeeded,
- what artifact should be saved on mismatch.

### Notes

- scaling issues,
- ambiguity risks,
- blockers,
- follow-up screenshot needs.

## 8. Refinement workflow

The selector-refinement workflow should be:

1. run a primary discovery pass on prioritized screenshots and screens,
2. capture a full screenshot of the source screen,
3. identify a candidate selector, including text labels, icons, unique buildings, and empty slots,
4. save discovery artifacts and prepare an explicit selector-update spec for newly identified registry entries,
5. run the offline registry-update script so the static catalog and selector ids are updated canonically,
6. click the selector in a controlled run when validation is appropriate,
7. capture the resulting screenshot,
8. classify the destination screen or changed state,
9. save the source and destination screenshots as refinement artifacts in a dedicated input folder,
10. update the selector entry with click mapping and verification evidence,
11. mark the selector status forward only when evidence is sufficient.

### 8.1 Offline update script requirements

- The update script must be separate from the live automation entry point.
- The update script must treat the static selector catalog as canonical and update that file directly.
- The update script must also update canonical selector-id definitions when new selector ids are introduced.
- The update script must fail fast on duplicate selector ids, invalid screen names, invalid statuses, or backward status transitions.
- The update script may batch multiple reviewed selector additions from one refinement pass so long as every change is backed by saved artifacts.
- The current implementation already satisfies the static-catalog write path and fail-fast validation requirements.
- Screenshot-folder ingestion, draft-spec generation, and live-assisted click-probe staging are now implemented through the reviewed discovery path.

## 9. Validation requirement

No selector should move forward in status without recorded validation evidence.

Minimum evidence per stage:

- `screenshot_seeded`: source screenshot with selector identified,
- `click_mapped`: source screenshot plus destination screenshot after click,
- `interaction_validated`: repeated successful detection and click verification,
- `task_validated`: successful use inside at least one live feature flow.

### 9.1 Registry-wide clickability validation

Selector refinement must include a controlled clickability pass across the registry, not just spot checks for a few high-priority selectors.

This pass exists for validation and discovery only. It is not the normal runtime automation policy.

Rules:

- Every selector intended to be clickable should be exercised from its valid source screen.
- The refinement pass should keep clicking through reachable selector chains until it reaches a screen or state where no further safe click is defined or the next visible controls are intentionally excluded.
- Each hop must capture source and destination screenshots and record the resulting screen or terminal state.
- If a selector is visible but not currently actionable, the run should capture artifacts and record the blocker instead of guessing.
- Real-money purchase controls are excluded from live click validation. Buy or price buttons may be observed and classified, but they must not be pressed.
- Any selector discovered to be non-clickable, unsafe, or monetized must be marked clearly in refinement notes so downstream automation does not treat it as a normal action target.
- This validation flow may also be used to discover previously unknown clickable entries, provided those discoveries are recorded as artifacts and reviewed before they are added to the canonical registry.

### 9.2 OCR and parser validation rules

- Every new OCR-driven parser must have both positive and negative coverage.
- Negative coverage is mandatory when a parser can override screen classification or synthesize clickable selectors.
- Word or line normalization rules must be tested centrally through the shared text-anchor detector, not duplicated in screen-specific tests.
- Adjacent screens with similar labels must be part of the negative fixture set so the classifier proves it rejects near-matches.

### 9.3 Definition of done

Selector refinement is not done only because the static catalog loads and the Python tests pass.

Definition of done requires all of the following:

- the primary discovery phase has expanded the registry coverage for the prioritized reachable screens,
- required selectors have recorded screenshot evidence and click-mapping evidence,
- registry-wide clickability validation has been performed for the safe clickable selectors in scope,
- live smoke validation on the real P&C UI has confirmed that screen detection works on the current account state,
- live smoke validation on the real P&C UI has confirmed that a small set of safe selectors can actually be clicked successfully,
- live smoke validation on the real P&C UI has confirmed at least one simple round-trip navigation flow such as `home -> bag -> back` or `home -> alliance -> back`,
- excluded monetized controls such as buy buttons were not pressed during validation,
- remaining gaps, blockers, and intentionally dynamic areas such as Event Center entries are documented explicitly.

### 9.4 Current live smoke evidence

Current recorded live smoke evidence for this sub-plan:

- On 2026-03-09, `127.0.0.1:5565` successfully classified the current live account state as `PNC_HOME_CITY`, `PNC_POPUP`, `PNC_BAG`, and `PNC_ALLIANCE_JOIN`.
- Blocking popup detection and dismissal were validated from the real UI using the artifacts under `artifacts/2026-03-09/k313_cold_duke_of_the_north/`, beginning with `20260309T214555Z_live_smoke_recovery_start.png`.
- A typed selector-driven round-trip `home -> bag -> back` was validated with `20260309T215402Z_live_smoke_final_start.png`, `20260309T215407Z_final_bag_post_action_1.png`, and `20260309T215412Z_final_bag_return_post_action_1.png`.
- A typed selector-driven round-trip `home -> alliance join -> back` was validated with `20260309T215417Z_final_alliance_post_action_1.png` and `20260309T215421Z_final_alliance_return_post_action_1.png`.
- On 2026-03-10, after correcting the first-instance config from `127.0.0.1:5555` to `127.0.0.1:5556`, `BlueStacks App Player` successfully classified the live account state as `PNC_ACADEMY`, returned to `PNC_HOME_CITY`, and completed a typed `home -> bag -> back` round-trip.
- The first-instance validation artifacts were recorded under `artifacts/2026-03-10/k230_lv_6_hellhound/`, including `20260310T000711Z_first_instance_live_retry_start.png`, `20260310T000716Z_first_instance_live_retry_home_1_post_action_1.png`, `20260310T000721Z_first_instance_live_retry_bag_post_action_1.png`, and `20260310T000727Z_first_instance_live_retry_bag_return_post_action_1.png`.
- No monetized controls were pressed during the smoke validation.

## 10. Initial refinement backlog

The first high-value refinement targets are:

- a primary discovery sweep for additional selectors across the currently reachable screens,
- bottom navigation selectors,
- home right-rail shortcuts,
- home-city clickable buildings,
- empty building slots and construction menus,
- build and upgrade entry buttons,
- academy and research entry points,
- world-map gather entry points,
- world-map fixed overlay selectors and spatial-surface parser fixtures requested by [PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SPATIAL_SURFACE_SUBPLAN.md),
- popup close and confirmation buttons,
- castle-selection entries and selection indicators,
- replacing ad hoc OCR fallbacks with a shared text-anchor detector and evidence-based screen parsers,
- upgrading OCR support from line-only assumptions to richer localized text results where the backend allows it.

## 11. Buildings and empty slots

Home-city building refinement needs special treatment.

Rules:

- treat each unique building entry point as a selector candidate,
- treat empty building slots as distinct selector candidates,
- map each click result to the resulting screen or build menu,
- document whether the opened interface is shared or building-specific,
- only then define the reusable flows and task logic that depend on those selectors.

This is required because home-city building interactions are not uniform and should not be guessed from partial screenshots.

## 12. Event Center strategy

`PNC_EVENT_CENTER` needs separate handling because its entries rotate over time and cannot be assumed to be a fixed static list.

Rules:

- Event Center tabs may remain canonical static selectors when their structure is stable.
- Event rows inside `PNC_EVENT_CENTER` should default to a dynamic collection model rather than one fixed selector id per temporary event.
- Do not create permanent selector ids for short-lived event names unless repeated evidence proves that the row identity is structurally stable across rotations.
- Prefer a more capable dynamic event-entry system that can interpret recurring event rows from shared visual structure, OCR titles, badges, timers, and resulting click destinations.
- Screenshot collection across multiple days is required so the dynamic model is built from real variation rather than one snapshot.
- Newly observed events discovered during the week should be saved as refinement artifacts and used to extend fixtures, parsers, and click-mapping evidence.
- If some events prove stable across time, the registry may later add explicit recurring event definitions, but that should be a deliberate refinement outcome rather than the default strategy.

## 13. Relationship to the selector registry

This sub-plan refines the registry defined in [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md). It must not create a parallel selector-definition system.

If a selector is refined here, the canonical static selector catalog and selector-id definitions must be updated through the offline registry-update script.

## 14. Relationship to other plans

- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) must consume account-navigation-related selectors only after they are sufficiently refined here.
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md) must consume selectors only after the required selectors are sufficiently refined.
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md) must reference the refined selectors for reusable navigation flows.
- [PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SPATIAL_SURFACE_SUBPLAN.md) must request fixed overlay selector maturity and parser-fixture increments here rather than redefining registry ownership.
- [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md) must not redefine refinement rules; it only consumes the resulting registry quality level.
