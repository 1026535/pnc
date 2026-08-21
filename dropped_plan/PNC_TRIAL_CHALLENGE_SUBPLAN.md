# Puzzles & Conquest Trial Challenge Sub-Plan

## 1. Purpose

This document owns the Trial Challenge subtree that was split out of the main building-actions plan.

It is intentionally separate from:

- [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md), which owns `tower_of_trial` as a building and the existence of the `trial_challenge` linked screen,
- [PNC_SCREEN_FLOW_ARCHITECTURE.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_ARCHITECTURE.md), which owns reusable screen-navigation patterns,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns broader feature-task planning.

This file should answer one class of questions only:

- how Trial Challenge rows are modeled,
- how day/state accessibility changes affect those rows,
- how row-local actions such as `Rank`, `Stats`, and `Trial` should resolve,
- what follow-up screens exist under the Trial Challenge subtree.

## 2. Current confirmed context

From the current evidence already recorded in [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md):

- `trial_challenge` is reached from `tower_of_trial`.
- Screen title is `Trial Challenge`.
- Top controls include `Exchange`, `Progress`, and `Total Rank`.
- Stable rows currently evidenced include `Hero Trial`, `Curio Trial`, `Tech Trial`, `Gear Trial`, `Rune Trial`, and `Sauroi Trial`.
- Repeated row-local actions include `Rank`, `Stats`, and `Trial`.
- Trial rows stay in fixed positions rather than behaving like a free-scrolling dynamic list.
- Accessibility changes by day/state, but row identity and row position remain stable.

## 3. Scope

This sub-plan should own:

- canonical row ids for each Trial Challenge entry,
- accessibility-state rules across the week,
- whether row-local controls are always present or only appear in accessible states,
- row-relative selector direction for `Rank`, `Stats`, and `Trial`,
- follow-up screen ownership for Trial Challenge tabs and row actions.

This sub-plan should not own:

- generic home-city Tower of Trial navigation,
- unrelated selector work for other buildings,
- broader policy scheduling for when routines should run Trial actions.

## 4. Core modeling direction

Trial Challenge should be treated as a fixed dashboard with stateful rows, not a dynamic feed.

Recommended ownership boundary:

1. [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md) keeps the high-level fact that `tower_of_trial -> trial_challenge` exists.
2. This sub-plan owns the row-level semantics inside `trial_challenge`.
3. Any later task behavior that consumes Trial Challenge should depend on the canonical row and accessibility model defined here.

## 5. Seed open questions

- whether every Trial Challenge row always exposes both `Rank` and `Stats`,
- the exact accessibility-state rules for each fixed Trial Challenge row across the week,
- whether `Trial` appears only on currently accessible rows or can still be resolved from a stable slot model,
- what exact follow-up screens open from `Exchange`, `Progress`, and `Total Rank`,
- whether any trial row ever changes label, order, or existence outside the currently observed weekly accessibility changes.

## 6. Immediate next additions

- Trial Challenge follow-up screens from `Exchange`, `Progress`, and `Total Rank`,
- row-level follow-up screens from `Rank`, `Stats`, and `Trial`,
- screenshots showing inaccessible, accessible, and countdown states for the same fixed rows across multiple days,
- a first-pass canonical row-id and availability-state table for all Trial Challenge entries.
