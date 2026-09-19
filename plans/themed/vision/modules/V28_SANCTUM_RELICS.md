# V28 — Sanctum and Relics menus

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; reuse item/card primitives only where they fit. Status: planned; support is not yet certified.

## Outcome and current evidence

Sanctum entry, Relics Set List, Event Relic and Private Collection tabs, set/item rows and read-only stats/detail popups.

PNC_SANCTUM and PNC_RELICS exist with the three tab controls. The already-dropped Relics subplan records candidate row labels and destinations; treat those as dated leads requiring current capture proof. Use the [versioned endpoint note](../../../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Sanctum/Relics definitions in the enricher, feature-specific row/result model, current visual/control/OCR catalogs and core navigation. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Qualify the selected tab and real row viewport; discover set/item rows using geometry and artwork, then bounded OCR for identity, level and owned/required piece counts.
2. Publish observed active/inactive set effects, collection progress and current detail-control geometry. A displayed full set or reward preview does not prove ownership.
3. Qualify one shared row-stats/detail family and return. Keep tab-specific semantics distinct; event-only additional layouts become named follow-ons if they exceed this coherent family.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add captured Relics tab/row/detail tests through both publishers. Include an inactive set, clipped row or another-tab negative available in evidence; no fabricated completion state. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Sanctum → Relics → one available tab/complete row detail → Relics → Sanctum/Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not activate, upgrade, combine, purchase or claim relics. Unavailable event/private-collection variants remain explicitly unqualified. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
