# Step 4: Puzzles & Conquest Screen Flow Sub-Plan

## 1. Purpose

This document is the dependency-ordered fourth plan and covers reusable Puzzles & Conquest navigation and screen-flow design.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which covers concrete task behavior.

This file owns only shared navigation and reusable screen-flow logic.

## 2. Scope

This sub-plan should define shared flows that many tasks consume, such as:

- `ensure_android_home()`
- `ensure_pnc_foreground()`
- `ensure_correct_castle_selected()`
- `ensure_home_city()`
- `open_world_map()`
- `open_academy()`
- `close_blocking_popup()`
- `return_to_safe_root_screen()`

The list can grow, but the principle must remain the same: one canonical implementation per reusable flow.

## 3. Why this is separate

Reusable screen flows are not the same thing as tasks:

- tasks own goals and verification of business outcomes,
- screen flows own reusable navigation between screens.

If flows stay mixed into task plans, navigation logic will get duplicated quickly across login, castle selection, research, gathering, and campaign work.

## 4. Per-flow template

Each screen flow should follow one canonical template:

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
- task types that consume this flow.

## 5. Initial flow backlog

The first reusable flows to document and refine are:

- `ensure_android_home()`
- `ensure_pnc_foreground()`
- `ensure_correct_castle_selected()`
- `ensure_home_city()`
- `open_world_map()`
- `open_academy()`
- `close_blocking_popup()`
- `return_to_safe_root_screen()`

## 6. Relationship to task planning

Tasks in [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md) should consume these flows instead of re-describing their navigation every time.

If a task needs a new reusable navigation path, it should be added here first as a canonical flow, then referenced from the task sub-plan.

## 7. Relationship to automation orchestration

This sub-plan should be consumed by [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md) and [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md). It must not redefine script-runner policy or task ownership.

## 8. Relationship to selector refinement

Reusable flows in this file should rely on selectors that have been refined through [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md), especially for unique building entry points and empty-slot construction flows.

## 9. Validation requirement

Each reusable flow must define and pass its own validation gate before tasks depend on it broadly.
