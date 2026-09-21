# V30 — Arena menus and match-3 API handoff

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; M0 of the shared match-3 component for the caller slice. Status: planned; support is not yet certified. Caller amendment: 2026-09-21.

## Outcome and current evidence

Versus Center with Arena selected, visible opponent/ranking/attempt facts, Exchange Shop inspection and one observed read-only opponent/detail family, plus a mode-selectable call to the shared match-3 API.

The [match-3 epic](../../gameplay/PNC_MATCH3_COMPONENT_PLAN.md) owns shared lifecycle and the pure algorithm in M1, Daily-exit/game-Auto policies in M2, and solver integration plus operational qualification in M4. V30 supplies qualified menu identity, targets, safe returns and a thin caller adapter. Match-3 Arena must be distinguished from Hero Showdown before any Daily quest binding; this packet's read-only and API proofs do not qualify battle execution or early-exit credit.

September14 reference and validation captures establish Versus Center/Arena and its Home return. The Hero/Arena audit is useful dated evidence; it does not establish combat proficiency or every tab's semantics. Use the [versioned endpoint note](../../../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Versus/Arena feature definitions, typed list/detail observations, current profiles/regions/selectors and navigation. Keep Campaign and Hero Showdown formation ownership distinct. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Preserve the qualified hub/return and establish the active tab before publishing opponent or shop rows.
2. Read observed opponent identity, rank/power, attempts/cooldown, offer quantities/costs and lock state within measured rows. Do not infer winning odds or select an opponent from strength alone.
3. Qualify one safe ranking/opponent or offer-preview detail and its return. Challenge, refresh and exchange controls remain separate from inspection.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.
5. Expose an explicit `battle_mode` choice of `solver`, `daily_exit` or `game_auto` for a battle request using M0's canonical parser/types and public option documentation. Existing inspection stays read-only. Reject invalid choices; check shared availability before runtime creation/navigation for a battle request. Do not register a fake successful Arena workflow just because its task ID already exists.
6. Add one feature caller adapter that hands context `arena`, the selected mode and qualified typed menu/target receipt to the shared API, borrowing the caller's session. The receipt proves only its observed menu/target; battle-start readiness remains the component's job. Propagate typed unavailable/results/errors with no retry or alternate mode. Do not call the pure solver directly or put battle logic in vision/navigation.

## API handoff definition of done

Offline tests invoke production parsing/composition with real shared request/result types. A recording implementation of the shared API reports availability and proves exactly one execution call for each of the three modes, the correct observed Arena target/context, borrowed session and result/error propagation. No mocked battle execution is mistaken for actual Arena qualification, and no production option enables unfinished modes.

The real M0 unavailable path must reject an explicit battle request before connection/navigation/input and preserve an honest `not_implemented` result, without retry, false success or fallback. Inspection requests make zero battle execution calls. Do not alias `HERO_ARENA` to this context based solely on the enum name.

**V30 is done when its menu/perception/navigation acceptance and these API handoff tests pass.** M0 is the only new match-3 dependency. Implementing the solver, Daily exit, game Auto, battle authority/entry/result recognition or a live battle is outside this packet. No additional live test is required solely for mode wiring.

## Acceptance and bounded proof

Extend `test_hero_arena_audit.py` and captured building-route tests using `arena_reference_20260914.png` and `arena_validation_20260914.png`, then add actual content/detail evidence through both publishers. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Arena/Versus Center → one proved non-spending ranking/detail → Versus Center → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not Challenge, refresh opponents, buy/exchange rewards or enter a battle. Selecting an opponent is allowed only when evidence proves it opens a read-only detail. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
