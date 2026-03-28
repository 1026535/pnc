# Puzzles & Conquest Campaign, Arena, and Match Solver Sub-Plan

## 1. Purpose

This document owns the shared Campaign and Arena subtree that was split out of the main building-actions plan.

It also owns the future match-puzzle solver planning that should sit under the same canonical owner instead of being split across separate Campaign, Arena, and puzzle documents.

It is intentionally separate from:

- [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md), which owns `campaign` and `arena` as buildings and the existence of the `campaign_map` and `versus_center` linked screens,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation patterns,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns broader feature-task planning.

This file should answer one class of questions only:

- how the current Campaign map is modeled,
- what the visible Campaign nodes mean semantically,
- how Arena / Versus Center entries are modeled,
- whether Versus Center entries are fixed or event-rotating,
- which follow-up screens/actions live under Campaign and Arena,
- how the shared match-puzzle solver should be introduced beneath those navigation surfaces.

## 2. Current confirmed context

From the current evidence already recorded in [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md):

- `campaign_map` is reached from `campaign`.
- `versus_center` is reached from `arena`.
- `Campaign` is always present at one fixed home-city position.
- `Arena` is always present at one fixed home-city position.
- `Campaign` is non-upgradeable.
- `Arena` is non-upgradeable.
- The current screenshot shows region nodes such as `Dawn Forest` and `Misty Bay`.
- The current screenshot shows a special destination such as `Neptune's Labyrinth`.
- The current modeling direction is that the Campaign surface behaves like a map with tappable nodes.
- `Versus Center` currently shows top tabs `Arena` and `Exchange Shop`.
- `Versus Center` currently shows entries `Hero Showdown` and `Hero Championship`.
- Both Campaign and Arena are good candidates to eventually hand off into a shared match-puzzle battle layer instead of inventing separate battle consumers later.

## 3. Scope

This sub-plan should own:

- canonical node types for the Campaign map,
- canonical entry types for Arena / Versus Center,
- region-node vs special-stage-node semantics,
- follow-up screen ownership for selected Campaign nodes and Arena entries,
- selector direction specific to Campaign map navigation and Versus Center entry navigation,
- the ownership boundary between navigation surfaces and the future match-puzzle solver,
- the canonical modeling direction for the future match-puzzle solver.

This sub-plan should not own:

- generic home-city Campaign/Arena building recognition,
- unrelated world-map behavior outside the Campaign subtree,
- broader policy about when routines should spend time in Campaign or Arena.

## 4. Core modeling direction

Campaign and Arena should be treated as sibling owned navigation surfaces that can eventually feed the same battle/puzzle execution layer.

Recommended ownership boundary:

1. [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md) keeps the high-level facts that `campaign -> campaign_map` and `arena -> versus_center` exist.
2. This sub-plan owns the entry semantics inside `campaign_map` and `versus_center`.
3. The future match-puzzle solver should be introduced under this same owner so node/entry navigation and puzzle execution share one canonical contract.
4. Any later task behavior that consumes Campaign or Arena should depend on the canonical node/entry model defined here.

## 5. Seed open questions

- the exact node semantics and action flow on the current Campaign map,
- whether region nodes and special-stage nodes open different follow-up screen families,
- whether Campaign node order/labels are stable or can vary by progression,
- whether Versus Center entries remain fixed or rotate by event state,
- what exact follow-up screens exist under `Arena`, `Exchange Shop`, `Hero Showdown`, and `Hero Championship`,
- what minimum selector set is needed for robust Campaign/Arena targeting before match execution,
- what the first canonical match-puzzle board model should look like,
- how puzzle-board state, legal moves, and solver output should be represented for downstream automation.

## 6. Immediate next additions

- Campaign follow-up screens and node destinations,
- Arena / Versus Center follow-up screens and tab destinations,
- screenshots for at least one normal region-node destination,
- screenshots for at least one special-stage destination,
- screenshots for each currently visible Versus Center entry destination,
- a first-pass canonical node taxonomy for the current Campaign surface,
- a first-pass match-puzzle solver shell that defines board state, move generation, and solver-result ownership.
