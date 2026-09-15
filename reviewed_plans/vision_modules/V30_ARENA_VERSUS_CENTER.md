# V30 — Arena and Versus Center menus

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry. Status: planned; support is not yet certified.

## Outcome and current evidence

Versus Center with Arena selected, visible opponent/ranking/attempt facts, Exchange Shop inspection and one observed read-only opponent/detail family.

September14 reference and validation captures establish Versus Center/Arena and its Home return. The Hero/Arena audit is useful dated evidence; it does not establish combat proficiency or every tab's semantics. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Versus/Arena feature definitions, typed list/detail observations, current profiles/regions/selectors and navigation. Keep Campaign and Hero Showdown formation ownership distinct. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Preserve the qualified hub/return and establish the active tab before publishing opponent or shop rows.
2. Read observed opponent identity, rank/power, attempts/cooldown, offer quantities/costs and lock state within measured rows. Do not infer winning odds or select an opponent from strength alone.
3. Qualify one safe ranking/opponent or offer-preview detail and its return. Challenge, refresh and exchange controls remain separate from inspection.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Extend `test_hero_arena_audit.py` and captured building-route tests using `arena_reference_20260914.png` and `arena_validation_20260914.png`, then add actual content/detail evidence through both publishers. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Arena/Versus Center → one proved non-spending ranking/detail → Versus Center → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not Challenge, refresh opponents, buy/exchange rewards or enter a battle. Selecting an opponent is allowed only when evidence proves it opens a read-only detail. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
