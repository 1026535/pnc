# V13 — Campaign map and chapter navigation

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01; V02 for automatic Home entry. Align with [feature04](../PNC_CORE_REMAINING_04_CAMPAIGN_PLAN.md). Deliverable: current visible chapter/stage-map facts and verified map/chapter/return routes.

## Current state and owners

The [source fix](CONTEXT_AND_EVIDENCE.md#navigation-findings-retained-in-these-plans)
recognizes Chapter6 and its bottom-right Home portal on `4d317db`; its exact
runtime changes and fixtures are ported after `ff38127`. Preserve that baseline
and reconcile newer Campaign work before extending content. In `pnc_observation_enricher.py`, `_build_campaign_additions` still publishes only the reviewed Chapter10/Grandia Ruins and stage3 cases. `campaign_ocr_regions.py` contains those bounded regions. `navigation_core.py` and `tasks/campaign_task.py` own navigation and consumption.

V13 owns Campaign semantics, profiles, and routes. Its local backend/model candidate is evidence for the shared [OCR text recognition and localization modernization plan](../PNC_OCR_TEXT_LOCALIZATION_MODERNIZATION_PLAN.md), which owns backend selection, model packaging, measured text positions, and cross-surface qualification. Reuse qualified pieces with source-commit attribution; do not make Campaign the permanent owner of the shared OCR stack.

Use tour15, the Chapter6 pulse validation fixture, and the saved Chapter10/path/stage evidence in the [Campaign note](../../docs/game-reference/workflows/campaign-navigation.md). Old source-build conclusions do not prove today's visible control semantics.

## Implementation

1. Preserve the integrated title-only Chapter6 anchor and bottom-right
   Home portal on this candidate. Reuse `campaign_map_chapter_6.png` and
   `campaign_map_chapter_6_pulse.png` with source-manifest provenance. Exclude the
   animated ring; the source's first loading frame does not justify UNKNOWN retry. Expand content within observed map/chapter layouts, without hardcoding the only readable chapter to10.
2. Discover visible chapter/path markers using stable artwork and measured geometry; obtain number/name from bounded OCR. Publish observed lock/selection/completion only when pixels prove them.
3. Bind each target to its visible chapter/stage identity and current viewport. A fixed known chapter order can guide search but cannot create unseen actionable nodes.
4. Extend the existing Campaign content producer and region planner for the evidenced layouts. Use one shared representation consumed by the current campaign task; remove touched one-off duplicate parsing.
5. Add measured map → chapter path and explicit return edges. Verify destination chapter identity and refresh nodes after camera/viewport movement. Preserve transition context separately from newly observed facts.

## Acceptance and proof

Extend `test_campaign_visual_profiles.py` and Campaign task/navigation tests with Chapter6 and10 source/validation frames. Both publishers must emit the correct current identities and geometry. Preserve the pulsing-ring regression and absence of unsupported mode/eligibility facts.

Start `py tools/run_tests.py group unit.app.pnc.vision` and `group unit.app.pnc.navigation`, then affected checks. One core-runtime route: Home → Campaign map → one proved unlocked chapter path → map → Home via the bottom-right portal. Save source/destination frames, typed targets and trace. Stop if no independently measured chapter entry is available. Stage Challenge, formation and battles are outside this packet; V14 owns the next boundary.

## Lead review and live checkpoint — 2026-09-16

The complete candidate integrates the accepted V16 building owners and preserves
one shared OCR service, one Campaign producer, canonical frame binding on both
publishers, and the existing navigation/observed-action boundary. R1–R6 and the
reference-sized Castle level correction passed the post-integration full run:
2,449 passed, 7 skipped, 0 failures/errors (a09501c32f72402cb29549753d913ce9,
2026-09-16T17:03Z, base10decf7). The vendored PP-OCRv3 recognizer, license and
notice are packaged by the single RapidOCR3.4.5 adapter. No parallel decoder,
model guessing or lowered stage confidence threshold is used.

The lead's canonical leased live run20260916T173004Z_70c229e3 on mega_old_acc,
active K157/NPC2/22, passed Home -> Campaign map -> Chapter5 -> map -> Home.
Chapter frame0036 was captured at17:32:19.820Z; the final Home frame0047 at
17:32:52.035Z. The lead visually inspected chapter, returned map and Home.
Nine measured stage markers yielded credible numbers1,2,3,5,6,8,9. Markers4/7
remained UNREADABLE with no action geometry. Mode/completion stayed unknown;
chapter number5 was independently proved, while its raw OCR name retained
noise ('C Costa Dorad'). No stage tap, battle or resource action was sent.
The lease released and the pre-existing instance was preserved.

Evidence is `.local-data/devin-v13/live_accepted_candidate/` with source/return
frames, typed rows and trace. This validates the reviewed candidate's live
boundary. Main has since accepted V12, and the V05–V07/camera integration is
being finalized separately; integrate those changes and validate their combined
OCR contracts before final V13 acceptance and push. V14 remains the owner of
stage details, Hero Formation and any later battle boundary.


## Final integration corrections — 2026-09-16

The shared OCR migration initially regressed native Research tile labels and
one Ranged ATK counter. A bounded engine diagnostic proved the orientation
classifier rotated Output I. Research now requests explicit upright text through
the canonical OCR context; orientation participates in raw/preprocessed cache
keys. Default OCR behavior elsewhere is unchanged. Horizontal fragments read
left to right within overlapping text rows, preserving vertically wrapped labels.
The original counter read remains first; only unresolved counters use one tighter
text-band retry. Conflicting complete readings still abstain without a retry.

The integrated Bag name retry now dispatches through the same tab-specific
identity owner as the initial read. Both Military/Misc positive cases and foreign
Speedup text have regression coverage. The native Misc capture visibly contains
Owned 2,915; the new backend reads it at 540px as well, so its stale unknown-count
assertion was corrected. All Bag publication methods passed in the 69-method
Research/Bag run. After the final counter correction, all 48 OCR/category units
and whole Research captured-acceptance methods passed in 252.341 seconds.

V18's independent result producer is integrated on the same candidate so one
combined affected/full check can verify the shared observation and OCR contracts.
The corrected live Research route passed in runtime
`20260916T185736Z_14d3e76b`: Wood Output I 1/5 and March Speed I 5/5 MAX,
with both category returns and Home verified. The lead inspected the saved
detail screens. The first March detail frame was transitional UNKNOWN; the
existing bounded wait accepted the settled layout without a repeated selection.
No research or spending occurred. Previous Campaign map/Chapter 5 return evidence
is unchanged.

## Acceptance — 2026-09-16

Accepted for the stated coverage after review and live validation. Combined
source commit `684c78923641a2c039d16df87979f3637c158152` passed
`tools/run_tests.py affected --base origin/main --explain`; shared contracts
selected the full portable suite: 2,496 passed, 7 skipped, no failures/errors,
1,507.468 seconds including selection and reporting. Run ID is
`1598ae0a7e6b49f0aec8c8bebcac9e48`; machine evidence is
`.test-impact/v13-v18-final-results.json` in the vision-v01-foundation worktree.
This supersedes the earlier pending integration gate. The reviewed Campaign
and corrected Research live evidence above applies unchanged to this commit.
