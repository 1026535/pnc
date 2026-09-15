# V37 — Alliance Hall and reinforcement menus

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for building upgrade facts. Status: planned; support is not yet certified.

## Outcome and current evidence

Alliance Hall, current reinforcement/member rows, non-spending recipient/army information and return.

Alliance Hall identity/level and captured Reinforce rows already have both-path tests. Existing member Manage and Reinforce geometries are distinct. Preserve this support and identify only remaining current content/detail gaps. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

`alliance_member_rows.py`, Alliance Hall definitions, existing Alliance/player identity models and measured navigation. Donation/research belongs to V08 and resource transport to V27. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Inventory current qualified Hall/recipient rows before changing them. Publish needed capacity/count/status fields only if current consumers require and captures show them.
2. Keep recipient identity, reinforcement action geometry and any current troop-detail facts associated with their actual row. Do not reuse member-Manage controls.
3. Qualify only a missing read-only detail/return family; reuse the existing sender/dispatch operation owner without extending resource-changing behavior.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Extend `test_alliance_member_captured_rows.py` and `test_alliance_remaining_visual_contracts.py` only for reproduced gaps; test both publishers with actual Hall/detail frames. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Alliance Hall → proved member/reinforcement information → Hall → Home, only if inspection is distinct from sending.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not reinforce, recall troops, change membership or join an Alliance. If a row button immediately dispatches, do not press it for vision proof. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
