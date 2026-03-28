# Puzzles & Conquest Hero Hall Policy Sub-Plan

## 1. Purpose

This document owns the deferred policy layer for Hero Hall recruitment and exchange behavior.

It is intentionally separate from:

- [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md), which owns Hero Hall as a building surface and its visible tabs/buttons,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns higher-level task planning,
- [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md), which owns broader automation architecture.

This file should answer one class of questions only:

- which Hero Hall recruit pool to use,
- when to spend 1x vs 10x pulls,
- how to prioritize normal vs timed recruit tokens,
- what exchange behavior should be policy-driven vs explicitly requested.

## 2. Current confirmed context

From the current evidence already recorded in [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md):

- Hero Hall is a non-upgradeable building.
- Hero Hall has fixed top tabs `Recruit` and `Exchange`.
- Recruit banners are stable selectable entries such as `Basic Recruit`, `Adv. Recruit`, and `Rare Recruit`.
- Recruit buttons include `Recruit 1x` and `Recruit 10x`.
- Token counts are visible near the recruit controls.
- Token inventory is also visible externally under `Bag -> Misc`.
- Shown token examples include `Oath Rune I`, `Oath Rune II`, `Oath Rune III`, and `Timed Oath Rune`.
- User confirmed that token-based `Recruit 10x` for 9 tokens should be favored when available.

## 3. Scope

This sub-plan should own:

- canonical recruit-banner ids and token types,
- recruit banner priority rules,
- 1x vs 10x spending rules,
- timed-token preference rules,
- exchange policy direction for fragment spending,
- failure and fallback handling when preferred pulls are unavailable.

This sub-plan should not own:

- generic building navigation to Hero Hall,
- selector naming for the Hero Hall surface itself,
- unrelated `Bag` automation outside token inspection that directly informs Hero Hall policy.

## 4. Recommended policy direction

The implementation should separate Hero Hall navigation from Hero Hall spending policy.

Recommended model:

1. The building/navigation layer opens Hero Hall and resolves the current Recruit or Exchange surface.
2. A dedicated Hero Hall policy object decides which banner and spend mode are allowed/preferred.
3. Execution resolves one concrete action such as `Recruit 10x` on one concrete banner.

This keeps one canonical ownership boundary:

- building plan owns what the screen is,
- Hero Hall policy owns what we choose to spend.

## 5. Seed policy assumptions

Until a fuller policy is authored, the current confirmed assumptions are:

- if a token-based `Recruit 10x` is available for 9 tokens, it should be preferred over spending those same tokens as repeated `Recruit 1x`,
- recruit banners should be treated as stable named pools rather than inferred dynamically,
- timed-token handling should be explicit policy, not hardcoded as an accidental side effect,
- exchange behavior should remain opt-in and rule-driven rather than automatically spending all points.

## 6. Open policy questions

- what is the explicit priority order across `Basic Recruit`, `Adv. Recruit`, `Rare Recruit`, and timed-token variants,
- when a preferred banner lacks enough tokens for `Recruit 10x`, should automation fall back to `Recruit 1x` or save tokens,
- how should timed tokens be prioritized relative to persistent tokens,
- should exchange spending be driven by explicit allowlists, score thresholds, or a later curated policy table,
- should Hero Hall policy be exposed through routine parameters or only through static config in the first slice.

## 7. Immediate next additions

- Hero Hall recruit confirmation follow-up screens,
- Hero Hall recruit-result screenshots,
- Hero Hall insufficient-token follow-up screens,
- Hero Hall timed-token examples on live recruit surfaces,
- Hero Hall exchange-result follow-up screens,
- one first-pass policy schema proposal once the preferred banner/token order is finalized.
