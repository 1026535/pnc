# V23 — Gem and Saurgem inventories

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V22. Status: planned; support is not yet certified.

## Outcome and current evidence

The Gem and Saurgem branches of Blacksmith, visible inventory/socket presentation and read-only item details.

PNC_GEM and PNC_SAURGEM plus category controls are declared. This survey did not qualify their item rows or socket/detail behavior; inspect saved feature evidence first. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

V22's shared equipment primitives, Gem/Saurgem-specific producers, bounded OCR/control catalogs and the existing Blacksmith navigation branch. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Independently identify the selected family and current layout before parsing cards or sockets. Keep Gem and Saurgem identities distinct even when artwork is similar.
2. Publish observed name/type, level/quality, quantity, socketed/selected state and displayed stats/requirements. Infer neither compatibility nor ownership from an empty-looking socket.
3. Qualify a non-mutating inspection detail per shared layout and the exact return. If these branches use materially different interaction families, split the remaining branch into a named packet before expanding implementation.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add real Gem/Saurgem family fixtures with a selected-family negative, same-artwork variant when evidenced, and detail close. Replay through both production publishers and their actual OCR plans. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Blacksmith → one available Gem/Saurgem branch → a proved read-only item detail → branch → Blacksmith → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not socket, remove, combine, synthesize, upgrade or consume items. A missing family remains unqualified rather than inheriting the other family's controls. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
