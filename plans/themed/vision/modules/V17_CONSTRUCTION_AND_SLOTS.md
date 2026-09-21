# V17 — Construction slot menus and construction details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V02 and V16. Deliverable: supported fixed/large/small construction menu families and honest construction readiness facts.

## Existing owners and evidence

Reuse `building_catalog.py` reserved slot IDs, `spatial_navigation.py`, `_build_building_construction_additions` and shared building helpers, current profiles/selectors, `navigation_core.py` and `tasks/building_construction_task.py`.

The existing building plan/tests include construction and slot menu work. Reconcile feature02 before edits. A catalog slot does not establish that the current castle has an empty, unlocked construction site.

## Implementation

1. Inventory actual fixed/large/small slot captures and current supported construction menus. Reuse V02's current target proof and V03-style occupancy semantics where already available; do not create another slot-state model.
2. Parse menu category and visible build options from measured cards. Publish building identity, displayed availability/lock reason and current inspection controls.
3. Qualify construction detail using V16's common costs, level, prerequisite and queue facts where the UI matches. Keep Build/Construct separate from menu opening and detail inspection.
4. Bind selected detail to the chosen option and verify return destinations. Clear old option geometry when the menu changes.
5. Retain the existing construction consumer and mutation journal. Remove touched duplicate facts rather than introducing a parallel building catalog.

## Acceptance and proof

Extend `test_building_captured_flows.py`, `test_building_route_captured_observers.py`, `test_building_construction.py` and relevant Home slot tests. Both publishers must distinguish an unavailable slot, an empty available site, build menu and selected detail. Use existing variant captures; no requirement to recreate all slot types live.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: testing Home → one current, proved empty/unlocked slot → build menu → non-spending detail if available → menu/Home. Save slot proof, menu/detail facts and return trace. If no such slot exists, report applicability and use saved evidence; do not demolish, unlock territory, switch castles or construct a building to create it. A material unproved live edge remains pending, not silently passed.
