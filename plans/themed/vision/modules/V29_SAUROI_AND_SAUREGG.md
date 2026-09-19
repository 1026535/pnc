# V29 — Sauroi Lair and Sauregg menus

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for ordinary Home entry; V03 for variant-specific acquisition. Status: planned; support is not yet certified.

## Outcome and current evidence

Sauroi Lair's current progression-dependent menu, Sauregg information and owned read-only details.

The user confirmed one fixed Lair location with tutorial-dependent appearances. PNC_SAUROI_LAIR and PNC_SAUREGG are declared; an Obtain control exists in the text definitions. The current tutorial variants were not captured by the tour. Use the [versioned endpoint note](../../../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

The Lair/Sauregg feature producer and profile/region/control keys, Home appearance facts from V03 and the existing building/navigation catalog. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Qualify the actually available menu/progression layout without assuming artwork determines unlock state. Keep Home appearance separate from menu facts.
2. Publish observed creature/egg identity, displayed progression/level, requirements, counts/timers and current information controls. Unknown tutorial state must not be filled from a guessed stage order.
3. Define Sauregg and other evidenced information popups as owned surfaces with measured close/return; do not reuse Obtain as a navigation control unless proven non-mutating.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Use actual available Lair/menu/detail captures through both publishers. Add a different observed appearance/menu state only when evidence exists; retain unknown behavior on unsupported tutorial variants. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Sauroi Lair → a proved Sauregg/info detail → Lair → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not hatch, Obtain, feed, awaken, upgrade or advance the tutorial for evidence. Missing progression variants are qualification gaps, not a reason to change the castle. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
