# Puzzles & Conquest Tutorial Routine Sub-Plan

## 1. Purpose

This document owns tutorial-gated automation behavior that should not stay embedded inside general building-action planning.

It is intentionally separate from:

- [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md), which owns the canonical building and linked-screen inventory,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation guarantees,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns broader feature-task planning.

This file should answer one class of questions only:

- what tutorial-gated flows exist,
- which transitions are owned by the tutorial rather than by normal building actions,
- how automation should progress or recognize tutorial-only states.

## 2. Current confirmed context

From the current evidence already recorded in [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md):

- `sauroi_lair` is always at one fixed home-city position.
- Before tutorial completion, the owned screen can appear as `sauregg`.
- The `sauregg` screen currently shows `Obtain`.
- The `sauregg` screen also shows text such as `Hatch 3 times to awaken Sauroi` and `Next hatching requires Life Essence 0/1`.
- After the tutorial-owned unlock, the same building uses the normal `Sauroi Lair` detail screen with `Upgrade`.
- User confirmation says the change from egg form is unlocked via the tutorial.

## 3. Scope

This sub-plan should own:

- tutorial-gated building-state transitions,
- the Sauroi egg-form to awakened-form transition,
- tutorial-specific action ordering and state recognition,
- future tutorial-only routines if they share the same ownership pattern.

This sub-plan should not own:

- generic post-tutorial building actions,
- generic screen-navigation primitives,
- unrelated feature policy once tutorial gates are already cleared.

## 4. Core modeling direction

Tutorial-owned transitions should be modeled separately from ordinary building actions.

Recommended ownership boundary:

1. [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md) keeps the canonical fact that `sauroi_lair` may expose `sauregg` before tutorial completion and the normal `Sauroi Lair` detail screen after unlock.
2. This sub-plan owns the transition logic that moves the account from the tutorial-gated egg presentation to the normal awakened building flow.
3. Normal building-action consumers should treat unresolved tutorial state as a distinct prerequisite condition rather than guessing at ordinary upgrade behavior.

## 5. Seed open questions

- the exact step-by-step action flow from `Sauregg` `Obtain` to the awakened `Sauroi Lair` screen,
- which intermediate tutorial overlays, arrows, or forced taps appear during the Sauroi unlock flow,
- whether `Life Essence` acquisition is granted directly by the tutorial or requires some separate action during the same routine,
- when ordinary Sauroi upgrade behavior becomes available relative to the tutorial completion point.

## 6. Immediate next additions

- screenshots for each step between `Sauregg` `Obtain` and the awakened `Sauroi Lair` screen,
- any tutorial overlay arrows, highlights, or forced-tap prompts encountered during that flow,
- evidence for when the ordinary `Upgrade` path becomes available after tutorial completion.
