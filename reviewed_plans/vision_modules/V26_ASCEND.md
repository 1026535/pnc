# V26 — Ascend menu and requirement details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V22. Status: planned; support is not yet certified.

## Outcome and current evidence

Blacksmith's Ascend branch, visible eligible-item/requirement presentation and read-only previews.

PNC_ASCEND and a hub entry are declared; the tour did not establish what items, requirements or confirmation sequence the current Ascend screen presents. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

An Ascend-specific content producer, the existing profile/region/selector catalogs, V22 equipment primitives where applicable, and core navigation. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Capture and classify the actual Ascend layout before choosing a domain result. Do not assume it shares Gear's item operation simply because it is a hub neighbor.
2. Publish the observed target item, current/next state if shown, material counts/costs, unmet requirements and measured preview/back controls. Distinguish displayed preview values from current owned state.
3. Qualify one safe requirement/info popup and its owned close. Mark the final Ascend/confirm action distinctly; no readiness fact executes it.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add source/validation Ascend and requirement-detail frames through both publishers, with missing-material text and unknown target handling where evidenced. Do not invent a progression-state matrix. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Blacksmith → Ascend → one proved non-spending information/requirement preview → Ascend → Blacksmith → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not ascend, select consumable materials, confirm or alter equipment. If even target selection consumes/changes state, stop at the menu and document that boundary. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
