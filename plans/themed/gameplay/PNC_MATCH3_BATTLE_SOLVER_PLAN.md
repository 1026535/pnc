# Match-3 solver design reference — M1 and M4

**Status:** design/evidence reference, 2026-09-21; no independent solver delivery track or implementation claim. **Repository base:** `68cb9351c141b9467e3f2a6a54018b38df201d4c`. The [match-3 epic](PNC_MATCH3_COMPONENT_PLAN.md) owns all delivery milestones and acceptance. Former S1 board rules and S2 combat-aware selection are now in [M1](PNC_MATCH3_COMPONENT_PLAN.md#m1--shared-foundations-and-pure-solver); former S3 runtime integration is now in [M4](PNC_MATCH3_COMPONENT_PLAN.md#m4--solver-integration-and-operational-qualification). This file retains pure-code boundaries and versioned rule evidence so the delivery plan does not duplicate that reference material.

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

## Delivery and validation ownership

Use M1's board-rule and combat-selection acceptance checks and M4's deterministic integration/live qualification checks in the epic. Do not maintain duplicate checklists here. Pure solver work may advance alongside lifecycle and V work once the relevant domain types have one owner; Pet Workshop neither owns nor gates it. Land shared types once and record their supplying revision.

Generated calibration traces stay under ignored `.local-data/`; reviewed non-secret fixtures belong in `tests/data/`. The epic owns test selection, operational availability and the retained single Campaign solver attempt / 20 AP limit. Consolidating the milestones creates no additional spending or retry authority.
