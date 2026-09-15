# V20 — Barracks training and unit information

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for shared upgrade/speedup presentation. Status: planned; support is not yet certified.

## Outcome and current evidence

Infantry, Cavalry, Ranged and Siege training menus, visible unit/tier choices, Unit Advantage and unlock information, and existing queue presentation.

The catalog has four exact building/screen identities and the enricher declares Train, Train Now, Speedup and Collect controls. The endpoint note identifies a shared CAMP_PANEL family. Those declarations do not qualify current training rows or all four layouts. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Barracks definitions in `pnc_observation_enricher.py`, the building catalog, shared control/OCR catalogs, and core navigation. Keep one unit-row producer with exact troop-family identity. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Measure unit cards/tier selectors and parse displayed unit identity, tier, selected amount, cost/time, availability and current training timer when visible. Keep current selection separate from any recommended training quantity.
2. Qualify Unit Advantage/unlock details and their owned close controls. Share geometry only where captured layouts agree; do not publish Cavalry facts on an Infantry screen.
3. Keep Train, Train Now, Collect and Speedup semantically distinct. Hand typed readiness facts to the existing operation boundary without creating training or collection automation.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add a captured Barracks menu test family beside `test_building_route_captured_observers.py`; cover one shared-layout validation frame and an evidenced cross-family identity negative, plus active/idle or locked variants only when available. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → one available Barracks → a proved Unit Advantage or unlock-information detail → Barracks → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not train, collect troops, accelerate a queue or change the selected training amount. Missing other-family captures remain named coverage gaps; do not repeat the same live proof on all four barracks. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
