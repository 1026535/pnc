# Match-3 solver plan — pure rules and move selection

**Status:** revised plan, 2026-09-21; implementation not claimed. **Repository base:** `68cb9351c141b9467e3f2a6a54018b38df201d4c`. This document replaces the former combined solver/lifecycle scope at this path. The [shared match-3 component plan](PNC_MATCH3_COMPONENT_PLAN.md) now owns the API, battle lifecycle, context adapters, `daily_exit`, `game_auto` and runtime integration of the solver. This plan owns only pure board rules, combat evaluation and move selection.

## Outcome and boundary

Build one solver usable by **Campaign, Arena and Lost Land**, through their qualified rules and observed state. It tries to win by repeatedly recommending an explained legal action; a win is not guaranteed. The shared component owns observations, input and the repeated battle loop. **Time Rift is deferred.** The dropped `plans/dropped/PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md` is historical context, not another specification.

The user-requested battle choices remain `solver`, `daily_exit` and `game_auto` for each of those three contexts. They are execution policies of the shared component, not three solvers. V13/V14 and V30 finish their new caller scope with **mode selection and tested shared-API handoff**. They do not depend on completion of this plan, any implemented battle policy or a live battle. The shared component's M0 contract is their only new match-3 prerequisite.

## Current state and design

At the revision base, `CampaignTask` only reaches preparation, and there is no active match-3 solver or board/result observation contract. `CampaignPolicy.enabled_modes` selects Standard/Elite difficulty; `CampaignExecutionMode` selects `fixed_stage` / `progress_then_farm`. Neither is the battle-mode choice. Keep these concepts independent.

Use pure immutable board, rule, combat-state, action and evaluation types under the PNC domain. Keep board geometry, OCR confidence, frame provenance, runtime handles, authorization, gestures and Daily progress outside this package. The shared observation adapter converts qualified facts into solver input; it maps a selected logical action back to fresh measured controls. The solver never imports `WorkflowContext`, opens a runtime or sends a game request.

The solver returns a legal swap or observed-special click with an explanation and uncertainty, or an explicit no-action/unsupported-state result. Share pattern detection and legal-action enumeration across contexts. Context names must not silently select board dimensions, rules or a combat model. Add only evidenced differences to a small rules contract; no game/plugin framework or separate Campaign/Arena algorithms.

## Evidence and limits

The [battle behavior note](../../../docs/game-reference/workflows/match3-battles.md) records source paths, build and unresolved behavior. Findings below are artifact-observed in packaged PNC **5.0.203 / versionCode 233**, rather than proof of the current server or measured UI.

| Rule or fact | Solver consequence |
|---|---|
| Ordinary battle initialization uses 5 rows × 7 columns; a separate PVP path uses 7 × 7. | Use observed dimensions and qualified rules. The requested Arena surface's actual family remains unknown. |
| Ordinary adjacent swaps create a horizontal/vertical run of at least three; the inspected new-puzzle rules also accept a same-color 2 × 2 square. | One generator examines each adjacent pair once and emits only supported legal moves. |
| Straight five or qualifying five-cell T/L creates color-clear; straight four creates a 3 × 3 clear; a 2 × 2 square creates a five-cell cross clear: the activated cell plus its four immediate orthogonal neighbours, clipped at board edges. Creation precedence is color > nine-grid > cross. | Keep creation patterns separate from effects. The three effects were also user-confirmed. Color-clear uses its observed color; spatial effects do not require matching colors. The cross does not clear the full row and column. Clip effects at board edges. |
| Specials are clicked; ordinary moves are dragged. Server reports supply damage, spawned cells and outcomes. | Distinguish swap from special click. Never assert a predicted refill, cascade, spawn position or damage as authoritative next state. |
| Current saved Campaign evidence qualifies navigation/formation, not board dynamics or a combat model. | Pure authored-board work can start now. Captured board/report traces gate calibration and operational promotion, not V caller acceptance. |

Exact special placement, chained-special behavior, per-context applicability, board-to-army targeting, retaliation cadence and damage remain qualification work. Unsupported observed mechanics yield an explicit limitation rather than guessed semantics. Individual hero-effect forecasting is outside this release; the component handles visibly ready skills and reobserves their consequences.

## S1 — Canonical board rules and explained one-step decisions

Implement immutable board/action types and one rule engine for legal swaps, ordinary matches, supported special creation and activation. Keep detection, effect calculation and scoring separate without duplicating pattern knowledge. Include a deterministic baseline ranking and stable coordinate tie-break so the result is inspectable and reproducible. Do not model exact random refills or unverified special chaining.

**Done:** authored-board tests establish legal/illegal swaps, three/four/five, T/L, square, overlapping creation precedence, the three distinct effects, edge clipping, special clicks and deterministic no-action/ranking behavior. Cross-effect fixtures assert exactly the activated cell and its immediate orthogonal neighbours: five cells in the interior, four at a non-corner edge and three at a corner, leaving diagonals and more distant row/column cells unchanged. Pure input/output works without a screenshot, emulator, runtime, authority object or completed component lifecycle. An uncalibrated baseline is not advertised as a qualified winning strategy.

## S2 — Combat-aware selection

Trace the packaged client's board-driven attacks, targeting, color interactions, health and turn pressure, then calibrate server-controlled behavior against available UI/report traces. Keep observed health/turn state separate from estimated damage and refill distributions. Evaluate bounded multi-turn win/survival prospects under documented uncertainty. Rank by supported win estimate, survival, expected damage/resource gain and stable coordinates; expose the terms actually supported by evidence rather than fabricated precise probabilities.

Use authored scenarios for meaningful combat ordering and observed traces for calibration. Hero skills are exogenous changes to the observed state: provide the shared component's ordinary visible-target ranking where needed, but do not add a second hero-effect simulator. The component reobserves and requests a new decision after a skill resolves.

**Done:** deterministic scenarios cover meaningful survival/target tradeoffs and blocked/unknown states; calibrated model terms and remaining estimates are documented. Missing traces can leave operational qualification pending without blocking S1 or the V API handoffs. Do not claim S2 calibration complete from authored scenarios alone.

## S3 — Solver policy integration

Provide the pure solver to the shared component's M2 solver policy through the agreed domain contract. The component requires a fresh settled board, player control and Auto proved off; maps one returned action to existing measured input; waits for resolution; then reobserves. It alone owns ready-skill execution, stop budgets, result recognition and authority. No second solver loop in Campaign, Arena, Lost Land, Daily or `CampaignTask`.

**Done:** a component-level deterministic trace proves observe → decide → one action → settle → reobserve, rejects stale/unknown required facts and retains the actual terminal result. Rules and selector acceptance remain independent of GUI qualification. Any live solver acceptance belongs to M4 in the component plan, including the retained single Campaign attempt / 20 AP allocation; this plan creates no additional spending or retry authority.

## Validation and delivery

Run focused pure-component tests through `py tools/run_tests.py group <registered-group>`, then `py tools/run_tests.py affected --base origin/main --explain` for source changes. Use the full suite only for an actual shared-contract or final integration change. Generated calibration traces stay under ignored `.local-data/`; reviewed non-secret fixtures belong in `tests/data/`. Documentation changes require `git diff --check`.

S1/S2 can proceed alongside component lifecycle and V work once the relevant domain types have one owner. Land shared types once and record the supplying revision. Pet Workshop has its own model and solver; PW packets neither own this algorithm nor gate it. The component plan owns operational support status for the nine requested context/mode combinations. Pure solver completion, API handoff completion and live battle qualification are separate claims.
