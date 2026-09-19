# V34 — Wall and Defense Info menus

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for common upgrade presentation. Status: planned; support is not yet certified.

## Outcome and current evidence

Wall menu, Defense Info, visible garrison/defense facts and read-only stat details.

PNC_WALL and PNC_DEFENSE_INFO exist; the enricher declares Defense Info, Repair Wall and Upgrade. The endpoint note records an asynchronous Wall-info request before the menu, so the object click alone is not success. Use the [versioned endpoint note](../../../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Wall/Defense Info producer and profile/region/control keys, the existing building catalog and core navigation. Preserve shared building-upgrade handling. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Qualify settled Wall identity and distinguish loading from the final menu. Publish observed durability/status, visible defense composition and current detail controls.
2. Parse Defense Info rows/stats only within owned regions, keeping defending hero/troop information distinct from editable selection controls.
3. Qualify its detail/return route and keep Repair Wall, garrison edits and Upgrade separate from information navigation.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add captured Wall/Defense Info both-path cases beside building-route tests, with the observed loading/final boundary and a missing required identity negative. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Wall → Defense Info → Wall → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not repair, change defenders, extinguish/boost or upgrade. If current state exposes only a mutation control, stop after reading the menu. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
