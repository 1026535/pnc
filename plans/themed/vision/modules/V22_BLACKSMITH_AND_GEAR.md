# V22 — Blacksmith hub and Gear inventory

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for building upgrade presentation. Status: planned; support is not yet certified.

## Outcome and current evidence

Blacksmith category hub, Gear inventory/list, gear-item inspection and return. Gem/Saurgem, Warsigil, Hero Curio and Ascend are V23–26.

The September14 Blacksmith reference proves the gear hub and category controls. Its historical return acceptance was blocked by a VIP modal later corrected elsewhere; recheck current code before treating that blocker as still present. Use the [versioned endpoint note](../../../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Blacksmith/Gear definitions in the enricher, current profile/control catalogs and `navigation_core.py`. Reuse existing item identity models where suitable; do not use Bag ownership for equipment inventory. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Preserve qualified hub anchors and measure current category controls independently. Complete the real hub return edge if it remains unproved.
2. Parse Gear list/card identity, slot/type, level/quality, equipped/locked indicators and visible item quantities/stats. Use artwork plus bounded name/variant fields, not icon similarity alone.
3. Qualify one read-only item detail and its close. Define only the small shared equipment card/detail primitives needed by V23–26; those packets own their semantic fields and specific layouts.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Extend `test_building_route_captured_observers.py` using `building_routes/blacksmith_reference_20260914.png`, plus actual Gear/detail and independent return evidence. Ensure category selection cannot be confused with Blacksmith Upgrade. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Blacksmith → Gear → one independently proved item-detail control → Gear → Blacksmith → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not equip, unequip, forge, enhance, dismantle or upgrade. A card tap that changes equipment is not an inspection control. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
