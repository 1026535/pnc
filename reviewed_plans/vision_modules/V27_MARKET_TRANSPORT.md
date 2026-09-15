# V27 — Market and resource-transport menus

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md) · [Building coverage](BUILDING_MENU_COVERAGE.md).
Depends on V01; V02 for Home entry; reuse V09 resource identities. Status: planned; support is not yet certified.

## Outcome and current evidence

Market hub, recipient list, zero/populated resource-selection form and read-only transport details.

PNC_MARKET and PNC_ALLIANCE_MEMBER_TRANSPORT exist. The old recognition checklist explicitly distinguishes the zero-selection Transport Resources form from the Alliance recipient list; it must not inherit that list's identity/actions. Use the [versioned endpoint note](../../docs/game-reference/workflows/building-endpoints.md) as a route lead and current captured pixels as acceptance evidence.

## Canonical ownership and implementation

Market/transport content in the enricher, existing Alliance member-row parser, resource domain models, typed observation and core navigation. Keep the existing transport mutation owner. Both `ObservationBuilder` and `NavigationPerception` use the same feature producer. Reuse V01's frame-bound identity/content/control contract; V02 handles Home acquisition, not menu semantics.

1. Independently qualify hub, recipient list and selection form; bind any form to the observed recipient or carried transition context with explicit provenance.
2. Publish visible resource kinds, available and selected amounts, capacity/tax/cost and enabled state only where displayed. Preserve zero as a real value distinct from missing.
3. Measure read-only recipient/detail/return controls. Do not publish Send/Transport from a matching title or previously selected recipient; it requires the current form's own evidence.
4. Add or correct a scoped workflow note with source date/build, supported layouts, actual return and remaining gaps. Keep references separate from validation captures; preserve newer landed work before modifying it.

## Acceptance and bounded proof

Extend `test_alliance_remaining_visual_contracts.py` and new Market form tests with actual zero-selection and available populated captures. Verify both publishers keep recipient-list rows separate from form controls. Require independent visual identity, typed observed facts, measured unoccluded controls and correct post-close state. Unknown values never inherit a prior screen's facts.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then use the index's affected/integration rule for actual source changes.

One configured-testing, active-castle core-runtime route: **Home → Market → a proved recipient/transport-form inspection → Market → Home, without editing amounts.** Follow the common lease, fresh-frame and stop protocol; record screenshots, observations and action/return trace under ignored `.local-data/`. Saved evidence comes first; no broad live tour is required.

Do not send resources, change recipients through account/Alliance switching or submit a transport. If current membership/access prevents inspection, report the prerequisite. If a material route remains unproved, report the exact pending edge rather than calling the feature complete.
