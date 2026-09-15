# V15 — Trial Challenge cards and read-only details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01; V02 for automatic Home entry. Deliverable: current Trial card identities/states and one observed detail family with a verified return.

## Evidence and owners

Tour29 and tracked `trial_challenge.png` show Hero, Curio, Tech, Gear, Rune and Sauroi cards with progress, weekday/timer and lock indicators. The baseline already identifies `PNC_TRIAL_CHALLENGE`, returns Home and maps the Tower building to that destination. It does not parse cards or prove trial entry/battle behavior.

Extend the Trial feature producer in `app/pnc/vision`, current profiles/selectors, bounded OCR planning and `navigation_core.py`. Do not create a second Tower navigation controller.

## Implementation

1. Measure the category-card regions and selected/locked indicators under the proved Trial layout. Read only displayed category labels, progress/floor, schedule and counters.
2. Publish canonical category identity, observed availability, progress and measured inspectable control. A displayed weekday is observed text, not a computed server-time availability decision.
3. Qualify one available, non-spending category detail if its entry semantics are established by saved/current evidence. Parse the visible floor/reward/ranking information actually needed for inspection and its return control.
4. Reuse common card parsing across the six categories only where the layouts agree. If a category opens a different interface, record it as unqualified and prepare a separate packet rather than force it through the first parser.
5. Keep entry to battle/resource actions separate; retain the already-correct Trial → Home route.

## Acceptance and proof

Add a captured Trial content test family beside the existing profile tests. Both publishers must agree on the six evidenced card identities and current fields, and withhold actions for clipped/ambiguous/locked controls as appropriate. Do not infer unshown floors or reset schedules.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Home → Tower → Trial Challenge → one proved read-only detail if available → Trial → Home. If entry may immediately start a trial, stop at the card list. Save current cards, detail/return frames and trace. No trial, battle or reward claim is required. Report category-specific deeper layouts not covered.
