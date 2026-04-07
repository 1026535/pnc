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
- Recent live evidence also showed one important failure mode: when the account has not completed the required early Campaign progression (for example Chapter/level 2 gating), navigation can keep retrying for minutes without ever reaching a usable world/campaign surface.

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

This sub-plan should explicitly own progression-gate detection for Campaign/Arena entry when that gating blocks this subtree from becoming usable.

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

## 6.1 Progression gate and retry-budget requirements

Campaign/Arena navigation must not treat early-account progression blockers as ordinary transient navigation misses.

The runtime should explicitly detect and classify cases such as:

- the account has not completed the required Chapter/level 2 Campaign progress,
- the intended Campaign/Arena subtree is still tutorial-locked,
- the expected downstream screen family cannot exist yet for this account state.

Required behavior:

- recognize the gating screen/state when possible,
- stop retrying after one short bounded retry budget when the same blocker persists,
- return one explicit structured failure instead of looping indefinitely,
- record the blocker reason in logs/results so operators can tell that progression, not selector drift, caused the stop.

Recommended policy:

- allow only a small retry count for repeated identical progression-gate observations,
- distinguish `temporary loading / popups` from `persistent progression gate`,
- fail fast once the runtime has enough evidence that the subtree is not yet unlocked,
- never spend minutes retrying the same impossible transition.

The core ownership rule is:

- transient navigation recovery belongs to shared screen-flow retry logic,
- Campaign/Arena subtree gating belongs here because only this owner understands whether the subtree is actually unlocked and reachable.

## 7. Match-3 solver creation

The shared battle layer should explicitly include creation of one canonical match-3 solver rather than leaving puzzle execution as an unspecified later concern.

The solver should be treated as one owned subsystem under this document because:

- Campaign stages can eventually feed directly into the puzzle board,
- Arena entries can eventually feed directly into the puzzle board,
- the same board detection, move legality, scoring, and execution loop should be reused regardless of whether the puzzle was entered through Campaign or Arena,
- keeping one solver owner prevents separate Campaign-specific and Arena-specific battle logic from drifting apart.

## 8. Canonical ownership boundary

The owned battle/puzzle subtree should be split into exactly four layers.

### 8.1 Surface navigation

This layer owns:

- opening `campaign_map`,
- opening `versus_center`,
- selecting one Campaign node or Arena entry,
- reaching the actual battle / match screen.

This layer must not:

- reason about gem swaps,
- score puzzle moves,
- choose battle moves from board state.

### 8.2 Board observation

This layer owns:

- detecting whether the current screen is a match board,
- locating the board bounds,
- slicing the board into canonical cells,
- classifying each visible tile,
- exposing typed board state to the solver.

This layer must not:

- choose the best move,
- execute swipes directly,
- own Campaign/Arena routing.

### 8.3 Solver

This layer owns:

- legal move generation,
- board simulation,
- move scoring,
- selecting the preferred move for the current strategy.

This layer must not:

- inspect raw screenshots directly,
- depend on Campaign/Arena entry names,
- perform input execution itself.

### 8.4 Execution / battle loop

This layer owns:

- consuming one observed board state,
- asking the solver for one move,
- converting that move into one swipe/tap action,
- waiting for board resolution,
- repeating until the board is no longer active or the battle ends.

This layer must not:

- reimplement move legality,
- reclassify raw tiles itself,
- duplicate Campaign/Arena routing.

## 9. First canonical board model

The first solver slice should introduce one explicit board model rather than passing around ad hoc arrays or screenshot snippets.

Recommended target types:

- `MatchBoardObservation`
- `MatchBoardCell`
- `MatchTileKind`
- `MatchMove`
- `MatchMoveDirection`
- `MatchMoveEvaluation`
- `MatchSolverResult`
- `MatchBattleState`

Recommended responsibilities:

- `MatchBoardObservation`: immutable snapshot of one detected board and its current tile grid.
- `MatchBoardCell`: row/column position plus tile kind and optional bounds metadata.
- `MatchTileKind`: canonical tile identity enum used by both detection and simulation.
- `MatchMove`: one legal swap candidate between adjacent cells.
- `MatchMoveDirection`: `UP`, `DOWN`, `LEFT`, `RIGHT`.
- `MatchMoveEvaluation`: stores score breakdown and non-obvious effects such as cascade depth or special-tile creation.
- `MatchSolverResult`: the chosen move plus ranked alternatives and solver metadata.
- `MatchBattleState`: typed higher-level state such as `BOARD_ACTIVE`, `RESOLVING`, `VICTORY`, `DEFEAT`, `UNKNOWN`.

Design rules:

- exactly one canonical tile enum,
- exactly one canonical move type,
- exactly one canonical solver entrypoint for the current board snapshot,
- fail fast if board dimensions, tile identities, or screen assumptions are inconsistent.

## 10. First solver scope

The first implementation should stay intentionally narrow.

Phase-1 solver scope:

- ordinary rectangular board only,
- adjacent two-cell swaps only,
- direct 3+ match legality detection,
- simple cascade-aware simulation if feasible,
- no special-skill button timing,
- no hero-ability optimization,
- no event-specific puzzle rules,
- no separate Arena-vs-Campaign solver forks.

The first goal is not a perfect endgame optimizer.

The first goal is:

- detect the current board reliably,
- enumerate legal moves,
- avoid illegal/no-op swaps,
- pick one reasonable move deterministically,
- execute that move through one shared battle loop.

## 11. Move scoring direction

The first solver should use one explicit scoring policy instead of hidden heuristics spread across multiple helper functions.

Recommended first-pass scoring inputs:

- whether the move is legal,
- immediate match count,
- number of matched tiles,
- whether the move creates multiple simultaneous matches,
- whether the move likely creates a special tile,
- estimated cascade continuation,
- optional color preference weights if later strategies need them.

Recommended rule:

- keep one canonical score function,
- return one structured evaluation object,
- let policy weights vary later without duplicating the move-generation engine.

## 12. Detection strategy for the match board

The first board-observation slice should not assume we can solve the whole battle problem from selectors alone.

Recommended approach:

1. classify the battle screen family,
2. identify the puzzle board bounds,
3. infer row/column geometry,
4. crop cell images from one canonical board region,
5. classify each tile into `MatchTileKind`,
6. build one `MatchBoardObservation`,
7. fail fast if any required cell cannot be classified confidently enough.

Detection notes:

- board detection should prefer one canonical board geometry per screen family,
- tile classification should remain separate from solver logic,
- if multiple battle skins/layouts exist later, those should extend the detection layer without forking solver semantics.

## 13. Execution loop direction

The battle loop should consume the solver output through one shared runtime path.

Recommended loop:

1. observe battle screen,
2. confirm board-active state,
3. detect board,
4. solve one move,
5. execute one swipe,
6. wait for board resolution,
7. reobserve,
8. repeat until terminal battle state.

Guardrails:

- detect repeated identical board states and fail fast if execution appears stuck,
- detect illegal or ineffective move retries,
- keep one runtime move-history structure for debugging and later tuning,
- do not silently continue if board observation degrades to `UNKNOWN`.

## 14. Creation order

Recommended implementation order:

1. Add the first board-state domain types and tests.
2. Add one match-move generator with deterministic legality rules.
3. Add one score/evaluation layer with a single canonical ranking policy.
4. Add one solver facade that returns the best move for one board snapshot.
5. Add one board-observation shell that can eventually plug in live screenshot parsing.
6. Add one battle-loop shell that converts `MatchSolverResult` into GUI actions.
7. Connect Campaign and Arena follow-up screens to the shared battle-loop entrypoint.

## 15. Immediate next additions

This sub-plan should now explicitly include creation of the match-3 solver as a concrete near-term deliverable.

Recommended next concrete additions:

- define the first `MatchTileKind` set from live board screenshots,
- confirm board dimensions and board bounds from at least one Campaign battle screenshot,
- confirm whether Arena uses the exact same board presentation,
- add one pure headless test module for board modeling and move legality,
- add one pure headless test module for move scoring and solver ranking,
- add one first live-observation fixture set for board tile classification,
- add one shared battle-loop shell that can be fed by either Campaign or Arena navigation.
