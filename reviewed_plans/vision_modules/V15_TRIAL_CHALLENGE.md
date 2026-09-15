# V15 — Trial Challenge cards and read-only details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01; V02 for automatic Home entry. Deliverable: current Trial card identities/states and one observed detail family with a verified return.

## Evidence and owners

Tour29 and `trial_challenge.png` from
[source commit `4d317db`](CONTEXT_AND_EVIDENCE.md#navigation-findings-retained-in-these-plans)
show Hero, Curio, Tech, Gear, Rune and Sauroi cards with progress, weekday/timer
and lock indicators. That revision qualifies `PNC_TRIAL_CHALLENGE`, the measured
top-left Home return and Tower's destination. The exact runtime changes and
fixture are ported after `ff38127`: Tower now maps to `PNC_TRIAL_CHALLENGE`.
Preserve this baseline. It does not parse cards or prove trial entry/battle
behavior.

Extend the Trial feature producer in `app/pnc/vision`, current profiles/selectors, bounded OCR planning and `navigation_core.py`. Do not create a second Tower navigation controller.

## Implementation

1. Preserve Tower → `PNC_TRIAL_CHALLENGE` and its measured top-left
   Home return through the canonical catalog/navigation owner; reuse the source
   profile and fixture rather than adding a second Tower controller. Measure the
   category-card regions and selected/locked indicators under the proved layout. Read only displayed category labels, progress/floor, schedule and counters.
2. Publish canonical category identity, observed availability, progress and measured inspectable control. A displayed weekday is observed text, not a computed server-time availability decision.
3. Qualify one available, non-spending category detail if its entry semantics are established by saved/current evidence. Parse the visible floor/reward/ranking information actually needed for inspection and its return control.
4. Reuse common card parsing across the six categories only where the layouts agree. If a category opens a different interface, record it as unqualified and prepare a separate packet rather than force it through the first parser.
5. Keep entry to battle/resource actions separate and qualify Trial → Home on
   the actual candidate; preserve an already-integrated equivalent return.

## Acceptance and proof

Add a captured Trial content test family beside the existing profile tests. Both publishers must agree on the six evidenced card identities and current fields, and withhold actions for clipped/ambiguous/locked controls as appropriate. Do not infer unshown floors or reset schedules.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Home → Tower → Trial Challenge → one proved read-only detail if available → Trial → Home. If entry may immediately start a trial, stop at the card list. Save current cards, detail/return frames and trace. No trial, battle or reward claim is required. Report category-specific deeper layouts not covered.
