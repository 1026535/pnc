# V41 — Castle and Territory Overview

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16–17 for upgrade/construction controls. Status: planned; support is not yet certified.

## Outcome and current evidence

Castle menu, Territory Overview and read-only territory/building status details.

PNC_CASTLE and PNC_TERRITORY_OVERVIEW exist, and exact building-level fields already have captured tests. Locked-territory regions and construction slots exist in the Home catalog; their appearance does not authorize an unlock. Use the [versioned endpoint note](../../../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Castle/Territory definitions, the canonical building catalog and exact level/identity models, current profile/region/control data and navigation. V17 retains build-slot menu ownership. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Preserve qualified Castle level/control publication and add only needed overview facts: visible building/territory identity, level, status and lock/prerequisite text.
2. Bind overview rows to measured current controls, distinguishing navigation to an existing building from opening a construction or unlock confirmation.
3. Qualify a read-only territory/building information detail and its actual return. Use V02 for a later Home relocation instead of interpreting overview coordinates as Home camera coordinates.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Extend building-level and captured-route tests with actual Territory Overview/detail frames through both publishers; preserve exact level facts and no action for ambiguous/locked rows. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Castle → Territory Overview → one proved status/information detail → overview/Castle → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not unlock territory, demolish, construct or upgrade. A Go control requires destination proof; do not assume it is harmless from its label. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
