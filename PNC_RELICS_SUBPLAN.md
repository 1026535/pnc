# Puzzles & Conquest Relics Sub-Plan

## 1. Purpose

This document owns the Relics-specific navigation and row-destination mapping that was intentionally split out of the main building-actions plan.

It is intentionally separate from:

- [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md), which owns Sanctum as a building and the existence of the `relics` linked screen,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns broader feature-task planning,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns shared navigation patterns.

This file should answer one class of questions only:

- what each Relics tab contains,
- how repeated relic-set rows should be modeled,
- what the small row button on each relic row opens,
- which follow-up screens and actions should exist under the Relics subtree.

## 2. Current confirmed context

From the current evidence already recorded in [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md):

- `relics` is reached from `sanctum`.
- Screen title is `Relics`.
- Top tabs include `Set List`, `Event Relic`, and `Private Collection`.
- Repeated row content includes entries such as `Lv.1 Gale Instrument (2/8)`.
- Repeated rows show state text such as `Lv.1 Set Stats (Inactive)`.
- Each row has a small action button at the right side.

## 3. Scope

This sub-plan should own:

- canonical Relics screen and tab modeling,
- row identity for relic-set entries,
- destination ownership for the row-local action button,
- any follow-up screens opened from Relics rows,
- selector direction specific to Relics row-level behavior.

This sub-plan should not own:

- Sanctum artifact-side behavior,
- generic home-city Sanctum navigation,
- unrelated inventory systems unless a Relics screen clearly links into them.

## 4. Core modeling direction

Relics should be treated as a Sanctum-owned subtree with stable top tabs and repeated row entries.

Recommended ownership boundary:

1. [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md) keeps the high-level fact that `sanctum -> relics` exists.
2. This sub-plan owns the row-level semantics inside `relics`.
3. Any later task behavior that consumes Relics should depend on the canonical row/destination model defined here.

## 5. Seed open questions

- what exact screen or overlay the small right-side row button opens,
- whether `Set List`, `Event Relic`, and `Private Collection` all use the same row structure,
- whether relic rows are static by set id or partially event-driven,
- whether the row button always means inspect/detail or can change by tab/state,
- whether any Relics follow-up surfaces contain actionable flows or are info-only.

## 6. Immediate next additions

- screenshots for the destination opened by the small Relics row button,
- screenshots for `Event Relic` and `Private Collection` content states,
- confirmation of whether row ordering is stable across tabs,
- proposed linked-screen ids and selector ids for any confirmed Relics follow-up surfaces.
