# V25 — Hero Curio inventory and details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V22. Status: planned; support is not yet certified.

## Outcome and current evidence

Blacksmith's Hero Curio branch, current curio inventory/equipped state and read-only effect/requirement details.

PNC_HERO_CURIO is a declared Blacksmith destination. Trial's Curio card is a different feature and does not qualify this inventory. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Hero-Curio-specific parser/profile/region keys, V22 equipment primitives, typed item observations and existing navigation. Reuse exact hero identities if an existing canonical model already owns them. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Identify the Curio family and selected hero/category only from current pixels; do not borrow selection from Trial or the previous screen.
2. Publish observed curio identity, level/quality, quantity, equipped association and displayed effects/requirements. Unknown hero association remains unknown.
3. Measure read-only details and explicit close/return controls; preserve any selection context separately from facts observed on the detail.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add actual Curio inventory/detail fixtures through both production publishers. Include a visually related Gear/Trial negative and same-icon variants when captured. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Blacksmith → Hero Curio → one proved item-information detail → Curio → Blacksmith → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not equip, switch a hero's equipment, enhance or consume curios/fragments. If selecting a card mutates the loadout, inspect only via an independently proved information control. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
