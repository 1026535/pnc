# V14 — Campaign stage detail, Hero Formation and return

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V13. Deliverable: a verified non-spending route to the actual Hero Formation surface with honest stage context.

## Current evidence and owner

The [Campaign note](../../../../docs/game-reference/workflows/campaign-navigation.md) and September13 captured findings distinguish stage detail, Hero Formation, battle and Victory. Older consumers expected `PNC_BATTLE_PREP` while the actual captured surface was `PNC_HERO_FORMATION`; button wording and routes need current qualification.

Own Campaign-specific functions in `pnc_observation_enricher.py`, `campaign_ocr_regions.py`, profiles/selectors, `navigation_core.py` and `tasks/campaign_task.py`. Preserve feature04's action boundary and existing generic formation consumers.

## Implementation

1. Verify the current feature04 branch/landed work and replay saved stage/formation frames first. Separate stage details from formation and battle identities; do not alias them to make a route pass.
2. Publish observed stage number/title, difficulty/mode only where displayed, availability, relevant costs and current controls. A label such as Challenge is not alone proof of a non-spending transition.
3. For an evidenced stage-to-formation control, verify the destination and publish visible formation slots, selected heroes and relevant readiness fields. Preserve prior stage identity as typed transition context; do not claim it was read on formation when absent.
4. Distinguish formation opening, formation editing/saving and battle-start controls. This packet reads the current formation without changing it.
5. Complete explicit back routes to stage/chapter/map/Home. Fix the Campaign consumer to request the correct observed screen and required facts; leave unrelated gathering or Hero Showdown formation behavior unchanged.

## Acceptance and proof

Extend captured Campaign/formation and `test_campaign.py` coverage. Both publishers must distinguish stage, formation and battle, retain source context without fabricated observed fields, and expose only measured controls. Test the consumer's correct endpoint and return path.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks including the Campaign consumer. One core-runtime live route ends at formation and returns Home **only if current evidence establishes a non-spending entry**. Otherwise stop at stage detail and report the unproved transition. Save stage/control/formation/return frames, typed context and action trace.

Do not start or replay a battle, spend AP, change heroes or press an ambiguous Challenge control for qualification. Historical battle receipts are evidence, not this packet's budget.
