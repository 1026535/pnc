# Step 4: Puzzles & Conquest Screen Flow Sub-Plan

## 1. Purpose

This document is the dependency-ordered fourth plan and owns only canonical reusable navigation and screen-flow logic.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which covers bootstrap, login, and castle-targeting behavior,
- [PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_SURFACE_SUBPLAN.md), which covers the world-map and home-city spatial model consumed by scrollable-scene flows,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which now defines the feature-based tracer-bullet planning model for post-navigation work.

This file is not the active feature backlog. Feature slices and account-navigation work may drive additions here, but only flows that are reusable or foundational should be promoted into this document.

## 2. Scope

This sub-plan should define shared flows that many tasks or features consume, such as:

- `ensure_android_home()`
- `ensure_pnc_foreground()`
- `ensure_correct_castle_selected()`
- `ensure_home_city()`
- `open_world_map()`
- `open_institute()`
- `close_blocking_popup()`
- `return_to_safe_root_screen()`

The list can grow, but the principle must remain the same: one canonical implementation per reusable flow.

A flow belongs here only when at least one of the following is true:

- it is required by both account navigation and later feature work,
- it is reused by two or more post-navigation features,
- it represents core safety or recovery behavior many tasks depend on.

Feature-local click paths should stay in the active feature plan until the reuse boundary is clear.

## 3. Why this remains separate

Reusable screen flows are not the same thing as features:

- feature plans own bounded outcomes and end-to-end validation,
- screen flows own reusable navigation guarantees between screens,
- spatial-surface parsing owns scrollable-scene semantics and viewport state,
- keeping flows central prevents login, chat, building, research, gathering, and campaign work from each re-describing the same navigation logic.

## 4. Feature-driven expansion model

Flow work should now be driven by bounded feature slices instead of by a separate horizontal backlog.

Rules:

- do not wait for a hypothetical fully completed flow catalog before implementing one bounded feature,
- add or refine only the next reusable navigation increment required by the active feature or account-navigation slice,
- when a feature discovers a path that is clearly reusable, promote it here and remove duplicate descriptions elsewhere,
- if a path is still one-off, provisional, or poorly understood, keep it in the active feature plan until reuse is proven,
- flow promotion must simplify the rest of the planning set, not create parallel descriptions.

## 5. Promotion gate

No feature-local navigation path should be promoted into this document until it passes the promotion gate.

Required promotion conditions:

- the path has a clearly reusable responsibility instead of serving only one temporary feature detail,
- the source and destination guarantees are explicit,
- the required selectors already exist canonically or have a defined selector-refinement increment,
- the path has one owning canonical name,
- the feature plan that discovered the path is updated to reference the canonical flow instead of restating it,
- the promotion removes duplication from at least one other planning document,
- the validation gate for the promoted flow is explicit.

If a navigation path does not yet satisfy those conditions, it must stay feature-local until the boundary is clear.

## 6. Per-flow template

Each canonical flow should follow one template:

### Flow purpose

- what navigation state the flow guarantees,
- what it explicitly does not guarantee.

### Entry assumptions

- allowed starting `ScreenType` values,
- required selectors,
- known blocking conditions.

### Navigation steps

- selector-based taps,
- screen transitions,
- optional waits,
- fallback transitions if a known modal appears.

### Success criteria

- destination `ScreenType`,
- required selectors visible,
- state assertions that must hold.

### Failure handling

- allowed retries,
- popup recovery interaction,
- conditions that must fail fast.

### Validation gate

- screenshot evidence for the required source and destination screens,
- targeted smoke validation for the live navigation path,
- explicit proof that the flow succeeds from every allowed entry assumption.

### Dependencies

- selectors required from the canonical registry,
- OCR fields if any,
- account-navigation or feature plans that consume the flow.

## 7. Initial canonical flow backlog

The first reusable flows to keep canonical here are:

- `ensure_android_home()`
- `ensure_pnc_foreground()`
- `ensure_correct_castle_selected()`
- `ensure_home_city()`
- `open_world_map()`
- `open_institute()`
- `close_blocking_popup()`
- `return_to_safe_root_screen()`

Additional flows should be added only when active feature work proves that they are genuinely reusable.

## 8. Relationship to feature planning

Feature work defined through [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md) should consume these flows instead of re-describing navigation in every feature plan.

If a feature needs a new reusable navigation path:

- first define the path as a candidate inside the active feature plan,
- promote it here once the reuse boundary is clear,
- then remove the duplicated navigation detail from the feature plan and replace it with a reference to the canonical flow.

This keeps feature plans focused on feature-specific decisions, not on re-explaining shared navigation.

## 9. Relationship to account navigation

[PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) should continue consuming the canonical flows in this file for bootstrap, popup recovery, and castle targeting.

[PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_SURFACE_SUBPLAN.md) should own world-map and home-city scene semantics; this file should only own the reusable navigation guarantees built on top of that model.

If account navigation needs a reusable path that later features will also depend on, that path belongs here rather than as duplicated bootstrap-only logic.

## 10. Relationship to automation orchestration

This sub-plan should be consumed by [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md), [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), and the feature plans governed by [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md).

It must not redefine script-runner policy, task ownership, or feature-specific business rules.

## 11. Relationship to selector refinement

Reusable flows in this file should rely on selectors refined through [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SELECTOR_REFINEMENT_SUBPLAN.md).

Scrollable world-map and home-city flows should also rely on the spatial model defined in [PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_SURFACE_SUBPLAN.md) rather than inventing task-local swipe heuristics.

Rules:

- a flow only depends on the selector slice required for that flow's current scope,
- selector growth should happen flow by flow as new clickable UI elements become necessary,
- each flow should request only its next required selector increment,
- do not block one bounded reusable flow on a hypothetical fully completed registry.

## 12. Validation requirement

Each reusable flow must define and pass its own validation gate before broad reuse.

No flow should be treated as canonical only because one feature happened to use it once. Canonical status requires:

- a clearly reusable responsibility,
- explicit source and destination guarantees,
- selectors mature enough for safe reuse,
- validation evidence that the flow works from its supported entry states.

