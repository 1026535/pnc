# V35 — Watchtower reports and information

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; V16 for common upgrade presentation. Status: planned; support is not yet certified.

## Outcome and current evidence

Watchtower's current overview, visible warning/report rows and one read-only report/information detail.

The catalog and screen enum declare Watchtower; the versioned endpoint maps it to TOWER_WIN. Current threat/empty-state content and report-return behavior were not captured in the tour. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Watchtower-specific content and profiles, bounded row OCR, current selector catalog, typed observation and core navigation. Reuse report identity models only if an existing owner fits the observed fields. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Qualify the actual overview and positively distinguish empty/no-alert status from an unreadable list.
2. Publish visible report/actor/arrival-time or status fields with their row association and measured information controls. Read a countdown as displayed rather than inventing a threat schedule.
3. Qualify one existing read-only report detail and owned close. Preserve uncertainty about unavailable threat states; no synthetic pixels count as live qualification.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Add captured overview/available-detail cases through both publishers, including a clipped row or empty-state source if available. Keep semantic conversion tests distinct from perception evidence. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Watchtower → one already-existing proved information/report detail if present → Watchtower → Home.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not scout, attack, create an incoming threat, activate protection or send messages to manufacture reports. No report present means detail coverage remains pending. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
