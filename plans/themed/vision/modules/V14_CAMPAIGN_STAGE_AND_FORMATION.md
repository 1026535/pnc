# V14 — Campaign stage detail, Hero Formation and return

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V13's qualified target/navigation contract, not completion of V13's new composed-caller test; the added caller slice needs only M0 from the [shared match-3 component plan](../../gameplay/PNC_MATCH3_COMPONENT_PLAN.md). Deliverable: a verified non-spending route to the actual Hero Formation surface with honest stage context, and a tested mode-selectable match-3 API handoff. Amendment dated 2026-09-21; no battle implementation is claimed.

## Current evidence and owner

The [Campaign note](../../../../docs/game-reference/workflows/campaign-navigation.md) and September13 captured findings distinguish stage detail, Hero Formation, battle and Victory. Older consumers expected `PNC_BATTLE_PREP` while the actual captured surface was `PNC_HERO_FORMATION`; button wording and routes need current qualification.

Own Campaign-specific functions in `pnc_observation_enricher.py`, `campaign_ocr_regions.py`, profiles/selectors, `navigation_core.py` and the current Campaign consumer endpoint correction. Add one thin Campaign handoff adapter beside that consumer boundary; package 04 reuses it during migration, rather than duplicating it in `CampaignTask` or a new workflow. Preserve feature04's preparation-only action boundary and existing generic formation consumers.

## Implementation

1. Verify the current feature04 branch/landed work and replay saved stage/formation frames first. Separate stage details from formation and battle identities; do not alias them to make a route pass.
2. Publish observed stage number/title, difficulty/mode only where displayed, availability, relevant costs and current controls. A label such as Challenge is not alone proof of a non-spending transition.
3. For an evidenced stage-to-formation control, verify the destination and publish visible formation slots, selected heroes and relevant readiness fields. Preserve prior stage identity as typed transition context; do not claim it was read on formation when absent.
4. Distinguish formation opening, formation editing/saving and battle-start controls. This packet reads the current formation without changing it.
5. Complete explicit back routes to stage/chapter/map/Home. Fix the Campaign consumer to request the correct observed screen and required facts; leave unrelated gathering or Hero Showdown formation behavior unchanged.
6. Accept the shared `solver`, `daily_exit` or `game_auto` choice forwarded by V13/the Campaign caller. For an explicit battle request, check the shared API's availability before opening a runtime or navigating; all modes are unavailable in M0. Preserve omission as preparation-only. Invalid values must fail validation rather than be silently ignored or treated as another Campaign policy.
7. Implement the single preparation-to-match-3 API handoff using context `campaign`, selected mode and the canonical typed target/preparation receipt. When execution becomes available, it borrows the existing session after qualified preparation. Preserve source-stage provenance; do not manufacture current AP/stage fields on formation. Return typed results/errors without replay or mode fallback. This adapter calls the shared component, which will dispatch to the selected policy; it never calls the pure solver directly.

## API handoff definition of done

Use real shared request/result types and production parsing/composition. With an offline recording implementation of the shared API reporting availability, verify exactly one execution call for each selected mode, with correct Campaign target, source-stage receipt and borrowed session. Verify typed result/error propagation and no retry/fallback. V13 proves forwarding into this adapter; both packets share this handoff test rather than adding two invocations. Test preparation-only omission sends zero execution calls.

Also exercise the actual M0 production implementation: explicit battle requests report `not_implemented` before runtime creation/navigation/input and never report battle success. The recording implementation is a test substitution at the shared interface, not a production dummy solver or a flag that enables unfinished modes. M0's availability/error semantics are genuine delivered behavior even though its execution policies remain unimplemented.

**V14 is done when its existing perception/navigation proof and these API tests pass.** It does not need solver code, Daily-exit controls, Auto waiting, battle-start authority, live combat, quest credit or all of package 04's migration. The [match-3 epic](../../gameplay/PNC_MATCH3_COMPONENT_PLAN.md) owns those battle deliverables, including the pure algorithm in M1 and solver integration in M4. No new live run is required solely to verify mode wiring.

## Acceptance and proof

Extend captured Campaign/formation and `test_campaign.py` coverage. Both publishers must distinguish stage and formation and reject saved battle frames as preparation, retain source context without fabricated observed fields, and expose only measured controls. Active-board/result recognition belongs to the shared component. Test the consumer's correct endpoint and return path, plus the API handoff above.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks including the Campaign consumer. One core-runtime live route ends at formation and returns Home **only if current evidence establishes a non-spending entry**. Otherwise stop at stage detail and report the unproved transition. Save stage/control/formation/return frames, typed context and action trace.

Do not start or replay a battle, spend AP, change heroes or press an ambiguous Challenge control for qualification. Historical battle receipts are evidence, not this packet's budget.
