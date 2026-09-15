# V21 — Infirmary healing menus

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for shared costs/queues. Status: planned; support is not yet certified.

## Outcome and current evidence

Infirmary entry, wounded-unit list, healing selection/detail presentation and an already-active healing queue.

`HomeCityObjectId.INFIRMARY` and construction ownership exist, but the inspected screen enum has no dedicated Infirmary identity. Current healing layout, controls and return behavior require capture qualification. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

The canonical building catalog and Home route, a small Infirmary producer in `app/pnc/vision`, typed observation, profile/selector/region catalogs and core navigation. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Establish the actual opened screen from a saved or bounded current capture. Add one screen identity only if the current generic building-detail identity cannot express the healing surface.
2. Publish observed wounded unit/tier counts, capacity, selected quantities, displayed cost/time and queue state. Distinguish a positively empty ward from missing or unreadable rows.
3. Measure inspectable details and owned return controls. Keep Heal, instant/premium heal, Help and speedup actions separate; do not change selection to obtain richer data.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Create captured Infirmary tests through both publishers; cover the available empty or populated state and an unrelated building negative. A missing populated capture must not become a synthetic visual qualification. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Infirmary → one proved non-spending information/detail surface if present → Infirmary → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not create wounded troops, heal, ask for help or use speedups. If the active castle has no Infirmary/access, report the exact route prerequisite. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
