# V36 — Trap Workshop and effect tables

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for costs/queues and upgrades. Status: planned; support is not yet certified.

## Outcome and current evidence

Trap Workshop, trap type/tier selection presentation, Effect Table and existing production queue facts.

PNC_TRAP_WORKSHOP and PNC_TRAP_WORKSHOP_EFFECT_TABLE are declared; the client endpoint is a distinct trap workshop family. Current row/queue variants need captured qualification. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Trap-specific definitions/producer, existing building and typed operation models, shared OCR/profile/control catalogs and navigation. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Measure trap rows/tier controls and read observed identity, level/tier, available/selected count, capacity and costs/time.
2. Qualify Effect Table as an owned read-only surface; bind displayed effects to the currently identified trap/tier rather than a remembered selection.
3. Distinguish production, premium production, collect and speedup controls from information. Reuse V16 queue facts where semantics agree, preserving unknown/busy state.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add captured workshop/effect-table tests through both publishers. Use a current tier/row negative and any already-available active queue; do not generate production for fixtures. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Trap Workshop → Effect Table or a proved information detail → Workshop → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not build/collect traps, change quantities, accelerate or upgrade. Missing queue variants remain explicit. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
