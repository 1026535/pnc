# V40 — Bank and current Treasure Cave endpoint

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry. Status: planned; support is not yet certified.

## Outcome and current evidence

The Bank building's current hub, displayed deposit/return/status information and read-only rules/detail presentation.

BANK exists in the Home catalog, but the endpoint note leaves its current screen identity unpromoted. The versioned client maps it to TREASURE_CAVE_WIN; do not infer present-day deposit mechanics from that name. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

The existing Bank catalog entry, a feature-specific endpoint producer/profile/control set, typed observations and core navigation. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Verify actual title/layout and measured return from current saved/live pixels before assigning a screen enum or promoting the Home route.
2. Publish only displayed balances, active terms/timers, rates/rewards and requirements. Keep preview/estimated returns distinct from owned resources and committed deposits.
3. Qualify one rules/term-information detail; separate Deposit/Withdraw/Collect or any equivalent mutation controls from inspection.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add captured current hub/detail and unrelated-building negatives through both publishers. State missing active-term evidence rather than inventing it or using a source-code mapping as visual proof. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Bank → one proved rules/information detail → Bank → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not deposit, withdraw, collect, buy a term or alter resource holdings. If access is unavailable, report the exact menu/entry gap. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
