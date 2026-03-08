# Step 5: Puzzles & Conquest Task Sub-Plan

## 1. Purpose

This document is the dependency-ordered fifth plan and covers concrete, screenshot-informed Puzzles & Conquest task design.

It is intentionally separate from [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which should remain focused on the primary platform architecture:

- account config,
- ADB wrapper,
- screenshot capture,
- selector registry,
- vision,
- P&C observation model,
- automation script runner,
- generic task framework.

## 2. When to use this plan

This plan should be filled in and refined only after selector-registry screenshots are available for the relevant screens.

It should not invent click paths or verification logic before the required screens are documented.

## 3. Scope

This task sub-plan should cover:

- exact screen entry conditions for each task,
- stable selectors and OCR regions per task,
- click paths and navigation sequences,
- verification rules,
- task-specific failure handling,
- retry and recovery rules,
- task-specific script parameters.

## 4. Task list

The concrete task-design follow-up should be organized by these tasks:

- `EnsureGameRunningTask`
- `PopupRecoveryTask`
- `LoginTask`
- `SelectCastleTask`
- `BuildingUpgradeTask`
- `ResearchTask`
- `GatheringTask`
- `CampaignTask`

## 5. Per-task template

Each task section should follow one canonical template:

### Task purpose

- what the task is responsible for,
- what it must not own.

### Entry conditions

- required `ScreenType`,
- required selectors,
- required script parameters,
- invalid preconditions that must fail fast.

### Observations required

- visual facts needed from `vision`,
- game meaning derived by `pnc`,
- OCR fields or list-entry extraction required.

### Planned actions

- navigation sequence,
- selector-based taps,
- optional waits,
- verification checkpoints.

### Verification

- expected destination screen,
- required selector state,
- OCR or badge evidence,
- negative conditions that indicate failure.

### Failure handling

- allowed retries,
- popup recovery interaction,
- when to stop the run.

### Validation gate

- required unit tests for any pure decision logic extracted from the task,
- required screenshot integration tests for selector, OCR, or observation assumptions,
- required live smoke validation for the end-to-end task flow,
- explicit evidence that must be captured before the task is considered complete.

### Script parameters

- supported YAML parameters,
- defaults,
- validation rules.

## 6. Current dependency status

The following task areas still require additional screenshots before their concrete sub-plans should be finalized:

- login,
- castle selection,
- building upgrade,
- academy and research,
- gathering node and march confirm,
- campaign screens,
- common popup and reward modal variants.

## 7. Relationship to selector registry

This sub-plan must consume the selector registry as input. It must not create a parallel selector definition system.

If a task needs a new selector, that selector must first be added to the canonical registry in [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), then referenced here.

## 8. Relationship to screen flows

This sub-plan should consume shared navigation flows from [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md). It must not duplicate reusable navigation logic inside each task section.

If a task needs a new reusable navigation path, that path should be defined in the screen-flow sub-plan first, then referenced here.

## 9. Relationship to automation orchestration

This sub-plan should consume generic task orchestration rules from [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md). It must not redefine the global task contract, script-runner behavior, or run-level retry policy.

## 10. Relationship to selector refinement

This sub-plan should consume selectors only after the required entries are sufficiently refined in [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md). It must not assume that screenshot-seeded selectors are already interaction-ready.

## 11. Validation requirement

Each concrete task must define its own validation gate using the template above. No task should be marked complete without:

- verification logic in the task itself,
- the smallest relevant automated tests,
- a targeted smoke run for the live clickable path.
