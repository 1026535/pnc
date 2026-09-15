# V38 — Hall of War and rally information

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for upgrade/glory presentation. Status: planned; support is not yet certified.

## Outcome and current evidence

Hall of War overview, visible rally/status list and one read-only rally or Glory Level detail.

September14 reference and validation captures establish Hall of War and measured Home return. The enricher declares Glory Level, Upgrade and a rally Go control; Go's exact current destination still requires evidence. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Hall-of-War-specific content, row/detail models, existing visual/OCR/control catalogs and core navigation. Keep rally dispatch/join ownership outside this packet. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Preserve the qualified overview and return, then parse visible rally identity/status, participants, timer and observed eligibility/capacity fields from owned rows.
2. Qualify one information/Glory Level surface with its own identity and close. A displayed Join/Go control is not itself proof of a read-only route.
3. Keep pending/active/empty states explicit; an empty list or expired-looking timer cannot prove a rally completed.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Extend building-route tests using the Hall reference/validation frames and actual information/detail captures. Both publishers must preserve row associations and exclude unrelated Alliance controls. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Hall of War → one proved read-only information/Glory Level detail → Hall → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not launch/join/cancel rallies, dispatch troops or upgrade. If no safe detail exists, qualify overview facts and record the missing edge. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
