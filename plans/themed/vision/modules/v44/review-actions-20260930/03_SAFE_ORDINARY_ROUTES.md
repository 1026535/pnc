# 03 — Complete Hall of War, Recruiting Center and Infirmary routes

> Supporting V44 case study from the first planning pass. The [velocity roadmap](README.md) and [cause assessment](00_ROOT_CAUSES.md) supersede its priority and current-status assumptions. Reconcile historical candidate, ownership and policy notes before execution; this document is not a live assignment.

Priority: combine discovery with 02. Owners: V44 shared acquisition, V38 Hall of War, V42 Recruiting Center, V21 Infirmary; one integration owner. Review coverage: §2 safe ordinary rows, §3 occupancy/body/route distinctions, §5 coherent evidence packages.

## Current gaps

[E4–E5](README.md#evidence-index) support initial non-spending navigation for these three types in recovered build 5.0.203. They do not establish present occupancy, body geometry or all current UI transitions. Hall of War is distinct from accepted Alliance Hall. Recruiting Center is not a barracks merely because the recovered window is named `TRAININGCAMP_BUILD_WIN`.

| Target | Known evidence | Required new evidence |
|---|---|---|
| `HALL_OF_WAR`, slot14 | Native endpoint and Back fixtures under `tests/data/screen_recognition/building_routes/hall_of_war_{reference,validation}_20260914.png` | Full unclipped body source and independent translated native view; final public acquisition/entry/return |
| `RECRUITING_CENTER`, eligible17–51 | Canonical allowed slots; build-scoped statistics-panel behavior | Positive occupant, body/holdout, actual typed endpoint and measured return |
| `INFIRMARY`, eligible17–51 | Canonical allowed slots; initial info requests distinct from explicit healing actions | Positive occupant, body/holdout, endpoint identity and return |

## Implementation sequence

1. **Freeze ownership and observed availability.** Use `app/pnc/domain/{building_catalog,home_city_slots}.py`, canonical `scene_geometry.json` and [building coverage](../../BUILDING_MENU_COVERAGE.md). Assign exact target keys, caller symbols and fixture paths. Read the core porting contract before migrating callers. Do not expand V44 into rally formation, recruitment capacity operations or healing.
2. **Collect missing native prerequisites once.** Add these cases to the same compatible passive survey as Bank/Watchtower. Reuse naturally captured views. An eligible slot is a candidate; label the actual occupant only from positive native evidence. A failed match remains unknown. Positive empty/other-occupant evidence may resolve a particular slot, but does not prove a configurable type absent from every eligible slot.
3. **Qualify body data through the shared matcher.** Add target entries/templates and source/holdout fixtures to existing camera catalogs/manifests. Keep ordinary slot association and pose lifetime. Do not create per-building search loops or threshold exceptions. A body fully clipped in every saved frame remains an evidence dependency.
4. **Connect feature-owned endpoints and exits.** Reuse Hall of War's endpoint/Back contracts subject to current fixture and live confirmation. Qualify Recruiting/Infirmary endpoint and return through the existing selector/recognizer producers. If an unanticipated menu appears, use 02's capture-then-qualify boundary; do not improvise a tap.
5. **Migrate callers to the public path.** Use `NavigationCore.open_building` with `HomeCitySlotSelector` where requested. Preserve refusal/wrong-destination results through `WorkflowContext`. Remove an owned legacy fallback only after its final caller migrates and unrelated owners are accounted for.

Production scope: `pnc_automation/app/pnc/vision/home_city_camera/`, `app/pnc/domain/building_catalog.py`, `app/automation/engine/navigation_core.py`, the feature-owned selector/recognition entries and assigned callers. Shared files have one integration writer; route workers own named entries rather than entire catalogs.

## Validation

- Body qualification: owning `unit.app.pnc.vision.home_city_camera` cases and relevant `integration.vision.home_city_camera` publisher cases; independent native holdout and current ID/slot geometry.
- Route behavior: `tests/unit/app/pnc/navigation/test_navigation_core_buildings.py`, `test_home_city_slot_selection.py`, and `tests/integration/vision/test_building_route_captured_observers.py`; public-call handoff, wrong destination and no fallback.
- Public workflow/application changes retain `tests/integration/workflows/test_open_building_core.py` and `tests/contract/entrypoints/test_open_building_application.py` through affected selection.
- Run one final affected gate for the coherent group. Do not run full offline or live matrices per interchangeable plot.

## Minimum live proof and stop conditions

For each positively available type: fresh clear Home and verified target identity → real public open on final candidate → normalized acquisition and fresh requested body → typed intended endpoint → feature-owned measured return → verified Home. Preserve the requested slot in a materially distinct explicit-instance case; reuse equivalent repeated-instance proof. No rally, training, recruitment action, healing, speedup, help or cancellation is part of these navigation checks.

Record native body/menu if any/panel/return frames, action receipts and candidate binding. Stop dependent actions on unverified identity, missing control, unexpected panel or uncertain return; keep the case pending at the actual boundary. Do not construct a building or switch castles to manufacture availability.

Acceptance: each required route is either proved on the final candidate, positively unavailable under the approved coverage rules, or explicitly pending with evidence/owner/trigger. Unknown occupants cannot be silently removed from V44 scope. Feed the disposition into [11](11_COVERAGE_AND_CURRENT_STATE.md).
