# V24 — Warsigil menu and details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V22. Status: planned; support is not yet certified.

## Outcome and current evidence

Blacksmith's Warsigil branch, visible sigil slots/list, current loadout presentation and item/stat inspection.

PNC_WARSIGIL and the Blacksmith entry selector are declared. No current Warsigil content proof was collected in the September15 tour. Use the [versioned endpoint note](../../../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Warsigil-specific producer and profile/region/control keys, V22 shared equipment primitives, typed observation and the Blacksmith navigation branch. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Qualify the actual Warsigil screen and selected tab/loadout indicators before publishing slots or rows.
2. Read observed sigil identity, slot, level/quality, owned quantity and displayed effects/requirements. Represent empty, locked and unresolved slots distinctly from an equipped item.
3. Qualify one non-spending detail and owned return; keep activation, replacement and enhancement controls distinct from inspection.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add captured Warsigil content/detail cases through both publishers, including an observed empty/locked slot or a wrong-equipment-family negative. Do not claim loadout support from a header-only reference. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Blacksmith → Warsigil → one proved information/item detail → Warsigil → Blacksmith → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not equip, activate, replace, enhance or alter a loadout. Missing access or detail evidence is an explicit packet limit. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
