# Step 3: Puzzles & Conquest Selector Refinement Sub-Plan

## 1. Purpose

This document is the dependency-ordered third plan and covers iterative selector-registry refinement.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which covers account-specific bootstrap and castle-targeting behavior,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which covers concrete task behavior,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which covers reusable navigation flows,
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

- refine screenshot-seeded selectors through controlled click mapping,
- document source-screen to destination-screen transitions,
- add missing selectors for unique home-city buildings,
- add missing selectors for empty building slots and construction menus,
- advance high-value selectors from `planned` or `screenshot_seeded` to validated statuses.

Exit condition:

- the high-priority selectors required by the next implementation phases are click-mapped and interaction-validated.

Status:

- closed in the primary implementation plan,
- future selector work stays here as ongoing registry refinement and validation maintenance.

## 4. Scope

This sub-plan should define:

- how candidate selectors are discovered,
- how clickable UI elements are mapped to resulting screens or state changes,
- how selectors move from planned to validated status,
- how missing screens are requested and documented,
- how unique building and empty-slot interactions are refined,
- how selector metadata is updated without duplicating definitions.

## 5. Refinement principles

- The canonical registry remains singular.
- Refinement updates the canonical registry; it does not create a second registry.
- A selector is not fully trusted until its click outcome is mapped and verified.
- If a UI element is dynamic in content but stable in structure, refine the collection selector, not a temporary row id.
- Unknown click outcomes must be captured with artifacts and documented before automation relies on them.

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

1. capture a full screenshot of the source screen,
2. identify a candidate selector,
3. click it in a controlled run,
4. capture the resulting screenshot,
5. classify the destination screen or changed state,
6. update the selector entry with click mapping and verification evidence,
7. mark the selector status forward only when evidence is sufficient.

## 9. Validation requirement

No selector should move forward in status without recorded validation evidence.

Minimum evidence per stage:

- `screenshot_seeded`: source screenshot with selector identified,
- `click_mapped`: source screenshot plus destination screenshot after click,
- `interaction_validated`: repeated successful detection and click verification,
- `task_validated`: successful use inside at least one live feature flow.

## 10. Initial refinement backlog

The first high-value refinement targets are:

- bottom navigation selectors,
- home right-rail shortcuts,
- home-city clickable buildings,
- empty building slots and construction menus,
- build and upgrade entry buttons,
- academy and research entry points,
- world-map gather entry points,
- popup close and confirmation buttons,
- castle-selection entries and selection indicators.

## 11. Buildings and empty slots

Home-city building refinement needs special treatment.

Rules:

- treat each unique building entry point as a selector candidate,
- treat empty building slots as distinct selector candidates,
- map each click result to the resulting screen or build menu,
- document whether the opened interface is shared or building-specific,
- only then define the reusable flows and task logic that depend on those selectors.

This is required because home-city building interactions are not uniform and should not be guessed from partial screenshots.

## 12. Relationship to the selector registry

This sub-plan refines the registry defined in [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md). It must not create a parallel selector-definition system.

If a selector is refined here, the canonical selector entry in the main plan or future implementation must be updated accordingly.

## 13. Relationship to other plans

- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) must consume account-navigation-related selectors only after they are sufficiently refined here.
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md) must consume selectors only after the required selectors are sufficiently refined.
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md) must reference the refined selectors for reusable navigation flows.
- [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md) must not redefine refinement rules; it only consumes the resulting registry quality level.
