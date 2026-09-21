# V42 — Warehouse, resource buildings and Recruiting Center details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for shared upgrades. Status: planned; support is not yet certified.

## Outcome and current evidence

Warehouse, Farm, Lumber Camp, Moon Well, Iron Mine, Gold Mine and Recruiting Center information panels that share the ordinary building-detail family.

The catalog contains these exact building IDs. Farm/detail/level cases and Warehouse fields already have qualification; the presence of an ID does not prove a dedicated current menu for every utility building. Use the [versioned endpoint note](../../../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Existing generic building/detail producer and domain models, feature-specific field descriptors only where needed, current profile/region/control catalogs and navigation. Do not create one near-identical parser per building. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Inventory the actual endpoint family for each listed building. Preserve qualified generic details; route a materially different newly discovered family to its own packet instead of forcing it through Farm geometry.
2. Publish exact building identity, observed capacity/output/protection/support statistics, level and timers only where the information panel displays them.
3. Qualify shared information/detail return and keep production collection/help controls separate. Reuse V16 for Upgrade and V17 for Build; avoid duplicating those readiness models.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Extend `test_building_captured_flows.py` and `test_building_level_publication.py` with only uncovered shared-field differences, using both production publishers and exact building-identity negatives. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → one representative available utility building → proved information detail → building → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not collect production, recruit, boost or upgrade. Other IDs sharing a proved layout use saved evidence; a different endpoint remains a named qualification gap, not implied coverage. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
