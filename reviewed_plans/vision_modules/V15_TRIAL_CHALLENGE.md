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

## Reviewed implementation coverage, September 16

Implemented on `codex/vision-v15-trial` atop accepted V04 `0dcc68d`; lead-owned qualification evidence (Stats screen profile, measured Stats/Back anchors, graph edge and metadata tests) was handed to this package intact. Baseline evidence: tour29/testing 2026-09-15 list source (tracked reference is a scaled copy, same capture group), independent 2026-09-16 mega_old_acc completion variant (run `bd76a1da`), and the lead's non-spending live Stats qualification run `8e5a65ab` (one measured Gear Stats tap; destination frames `0029`/`0030`, tracked 540x960 fixture `trial_gear_stats_20260916.png`).

- `domain/trial_challenge.py` owns `TrialCategory` (HERO/CURIO/TECH/GEAR/RUNE/SAUROI), `TrialCardFacts`, `TrialChallengeSummary` (observed toolbar counter, not a named currency), `TrialApplicableStat` and `TrialApplicableStatsDetail`. `ListEntryKind.TRIAL_CATEGORY` plus `DetectedListEntry.trial_card_facts`, `Observation.trial_summary`/`trial_stats_detail` and the shared provenance binders follow the accepted research_facts pattern.
- `vision/trial_challenge.py` (`TrialContentProducer`) reads six fixed measured card slots only under `trial_challenge_live`. Identity comes from each card's own bounded title read — never slot order. Progress, castle requirement, countdown, weekday, lock glyph, reward chest, Trial-chip presence and Stats-chip presence are independent facts: a countdown can coexist with a castle lock (Rune), a chest never implies completion, and an occluded weekday stays unknown. The toolbar counter publishes once at screen level; a lone `0` glyph is honestly unreadable and stays unknown.
- Only the Gear card's measured Stats chip is actionable (row COMPLETE with chip bounds/point); every other row is NO_ACTION regardless of visible chips, and duplicate resolved categories mark rows AMBIGUOUS with no action. Trial/Rank/Exchange/Mall/Progress/Total Rank controls stay observation-only — content OCR never grants action authority.
- The Applicable Stats detail publishes under `trial_applicable_stats`: nine bounded label/percent rows preserving literal text (including the misread `%96`) plus numeric values, and the footer `In Gear Trial, only gear stats are applicable.` as the sole category source. Title or values alone never establish screen identity.
- `NavigationCore.open_trial_stats(category)` accepts only `TrialCategory.GEAR`, requires the proved list anchor plus one unique COMPLETE typed Gear row, sends one `TapListEntryAction` at the measured Stats chip, and confirms two stable CLEAR Applicable Stats frames whose bounded footer category agrees with the source. Wrong/unreadable detail or stale frames fail without a retap. Return reuses the lead-reviewed Back edge to `PNC_TRIAL_CHALLENGE`. `WorkflowContext.open_trial_stats` wraps the route with fresh-content bookkeeping.

Lead corrections applied from the evidence turn: matcher search bounds are reference coordinates while returned bounds are original-frame (no cross-resolution collapse — lock .933-.997 / clock .922-.963 at both sizes; chest floor .60, lock/clock .90); the Sauroi card is fully visible with a complete border envelope (no clipping claim); and content OCR does not enable OCR-derived toolbar actions.

Tests: `tests/unit/app/pnc/vision/test_trial_challenge.py` (parsing/dispatch/model invariants), `tests/integration/vision/test_trial_challenge_publication.py` (both publishers, real bounded RapidOCR, reference/completed/stats fixtures, provenance and demand-driven reads), and `TrialNavigationCoreTests` in `test_navigation_core.py` (route, unsupported categories, source/detail rejection).

## Remaining limits and live gate

Gear Stats is the only proved detail family. Other categories publish complete card facts but remain unsupported for inspection — they are not force-fit to the Gear detail, and any deeper route for them needs its own evidence. Trial entry, battle, stamina/resource use, Exchange purchases and claims are outside this packet. V15 is a review candidate pending lead review of the combined content/navigation path and the final non-spending live Gear Stats route proof (source → Stats → Applicable Stats → Back → Trial → Home).
