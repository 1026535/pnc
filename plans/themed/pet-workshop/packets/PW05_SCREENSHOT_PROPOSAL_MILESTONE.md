# PW05 — Saved screenshots and proposed-action milestone

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW02](PW02_RECOGNITION_CONTROLS.md), [PW04](PW04_ONE_STEP_SOLVER.md)

## Read before implementation

- [Plan 01: saved evidence and native input modes](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#3-evidence-and-existing-owners)
- [Plan 01: recognition verification and gaps](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#6-verification-and-evidence-gaps)
- [Plan 02: saved screenshot scenarios](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#5-required-scenarios-and-acceptance-limits)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** recognition worker, with Plan 02's accepted public planner. **Prerequisite detail:** PW02 for labels; PW04 for proposed actions.

Provide a small offline analysis entry point using the production parser and planner. It accepts saved images/fixture sets and emits machine-readable facts, an annotated review image and the proposed action/reason under `.local-data/`. Reuse existing rendering/serialization utilities where suitable. Do not create a second recognizer in the tool. Phone reference frames may be labeled by their evidenced layout, but must never qualify BlueStacks gesture geometry.

Select and track the smallest sanitized crops/full Workshop fixtures required for portable regression tests, with an authored manifest. Retain native input modes. Originals, generated annotations and bulk extraction stay ignored. Do not change `tests/data/local_fixture_artifacts.json` or require another worker to have the originating user's Pictures directory.

## Acceptance

The ready three-coconut order is labeled as three and rejected; the Wood 10 + coconut lasso order is eligible but incomplete; the selected Tree 4/production/merge sequence is distinguishable; unknown and black frames never produce a gameplay gesture.

## Focused validation

Compare both the recognized facts and the proposed action with reviewed labels for the cited native sequence and order frames. Explicitly reject the ready three-coconut order and block gameplay proposals from unreadable/black frames. Show observed Workshop level and relevant producer state with their evidence; do not infer hidden server order IDs or label an observed order invalid from an unproven level rule. The [reviewed progression findings](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#workshop-progression-and-order-selection) set that boundary. Keep generated annotated images and machine-readable reports ignored; portable authored fixtures remain tracked.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Portable labeled fixtures, offline analysis command, generated report locations and exact reviewed proposed actions. Lead acceptance is the first screenshot/proposal milestone and is mandatory before the lead invokes a production gameplay caller in PW10. PW06 and PW07 may finish their scoped offline work independently of this analysis-tool/report handoff.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.

### Delegation — 2026-09-21 UTC

**Delegated, offline only.** Recognition session `cedar-stealer`, turn 014, starts from accepted `1f14e06` in `pet-workshop-pw01`. Brief: `.local-data/devin-briefs/pw05-implementation.md`; run: `.local-data/devin-implement/pw01-platform-check`. Scope is this packet's real-parser/planner analysis tool, portable labels/fixtures, review images and behavioral checks. The lead reviews exact reports and three-coconut rejection. Shared policy/authority/workflow owners remain unchanged; any material shared-contract issue returns to the lead. No Main/ADB/lease access. Lead owns status records and acceptance.

### Freeze recovery — 2026-09-21

Turn 014 was interrupted with no tracked source edits or completed acceptance evidence. The lead verified absent supervisor/children and native `cedar-stealer` identity in the exact checkout, preserving `turn-014/recovery-original-state.json` and `recovery-evidence.json`. Same session resumed as **turn 015**, base `1f14e06`, with `.local-data/devin-briefs/pw05-recover-20260921.md`; startup and the replacement completion route were verified. Unrelated `nul` and `pnc_automation.egg-info/` remain untouched.

User-approved simulator use is available for logical development, while PW07 owns any necessary simulator changes. PW05 keeps actual native recognition/geometry evidence separate from simulated or downscaled images and routes concrete simulator gaps to the lead. Status remains **Delegated**; final candidate/report review, offline evidence and any applicable live proof remain required before acceptance. The new lead and Main's 01:00–05:00 Toronto limit are recorded in the roadmap; this assignment has no live authority.


## Independent review and correction batch — 2026-09-21

**Fixing findings, not accepted.** Lead reviewed candidate `78dc70ab9ce09a1f99003faff7390967b1d6b878`, the complete analyzer/parser delta, labels and four rendered reports. The source-bound full result is 2,842 passed / 7 environmental skips; its resource fingerprint was independently recomputed and matched. Native production/merge deltas and the three-coconut rejection are supported; occluded selection remains unknown.

Two P2 acceptance findings were independently reproduced: **PW05-R1**, inputs with the same stem silently overwrite reports/annotations while returning two successful index rows; **PW05-R2**, the saved full Wood10+coconut lasso card is incorrectly clipped/ineligible, while the existing detail test only proves readiness unknown. The canonical recognizer must prove eligible and not ready on that full card, preserving genuinely clipped-card abstention. Review/reproductions: recognition checkout `.local-data/review/pw05/review-turn015.md`, `collision-reproduction/result.json` and `lasso-board/`.

The private branch rebased cleanly onto accepted main `499ace6` as `215bb01`. Same session `cedar-stealer` resumed as turn 016 with both findings, final report regeneration and designated Python 3.13/RapidOCR checks. No source from PW05 is merged or accepted. Because the candidate changes production recognition, separate Devin final-candidate live validation is required before merge, during Main's 01:00–05:00 America/Toronto window under the canonical lease/temporary role. No spending is needed for that recognition check. Independent PW07 offline work continues.


### Correction review and final validation preparation — 2026-09-21

**Awaiting validation.** Lead reviewed correction `2d1fbdc05b97733e829edd0fae73b7bcd1970fa3`, inspected the native annotated lasso image and independently matched the full run's source fingerprint `2095660768ba32d6c6fa33e97350e2b033beaa2182a5ecf404dc31c5a673c2a2`. Result: 2,847 passed / 7 expected environmental skips, no failures. R2 now proves the full Wood10+Fruit5 card eligible and not ready, while the clipped leading card keeps the survey partial. All five report labels match.

R1 still allowed Windows case collisions (`Screen.png` / `screen.png`); the lead reproduced this at the real CLI boundary, directly normalized collision keys and extended the same regression. Ten analysis tests passed in 87.635 seconds. After a clean rebase over status-only `bfa8a1b`, final candidate is **`20b39e389e325f406e5c5031be042286bcc65a44`**. Recognition code/resources are unchanged from the fully tested worker correction. Unrelated `nul` and `pnc_automation.egg-info/` are preserved; candidate remains local and unaccepted.

Same session `cedar-stealer` turn 017 (verified startup, supervisor 33828) owns final source-bound affected checks and one ignored, bounded live-harness preparation package. No live access or source edits in that package. Lead evidence: recognition checkout `.local-data/review/pw05/review-turn016.md` and `final-lead-correction/focused.log`; final preparation will be `.local-data/review/pw05/live-preparation/preparation.json` and `.test-impact/pw05-final-results.json`.

The requested 01:00 Toronto wake was **not created**: the app permits only one heartbeat per task, currently occupied by `devin-cache-keepalive-6`. Existing monitor/completion callbacks remain active; no workaround cron was created. Once workers are idle and final checks/preparation pass review, the coordinator must stop the monitor with acknowledgement, repurpose that existing heartbeat for the live window through the native tool, and restore cache monitoring before the new worker dispatch. Obligation/error record: root `.local-data/devin-monitor/pw-queue/pw05-window-continuation.json`. User was notified. Main remains unavailable outside 01:00–05:00 America/Toronto, and no role or account state changed during this review.

## Final offline gate and prepared-harness review — 2026-09-22 UTC

Turn 017 kept frozen candidate `20b39e389e325f406e5c5031be042286bcc65a44` unchanged. Its final affected full fallback passed **2,847 tests / 7 environmental skips**, with no failures. Lead independently recomputed source fingerprint `0750379add94cb238339e92901d01f5a6a6ebfdd022f1cd040c3925f2830aff2`, matching final metadata; all five saved-frame reports match their labels. Evidence: PW05 checkout `.test-impact/pw05-final-{selection,results}.json`, final console and `.local-data/review/pw05/review-turn017.md`.

The prepared live harness is not cleared for execution. Lead ran its 20 offline guard checks and independently reproduced incorrect pass verdicts for unknown surveys, failed detail visits and absent required classification cases. Review also found initial-viewport-only classification, stale-board continuation after failed detail/close and instance launch still permitted by the role-derived resolver path. Reproduction evidence: `.local-data/review/pw05/live-preparation/lead-verdict-reproductions.json`.

Same `cedar-stealer` resumed turn 018 to correct only ignored harness/evidence files, preserving frozen source and avoiding a redundant broad suite. Brief: `.local-data/devin-briefs/pw05-live-harness-corrections.md`. These are harness/runtime findings, not new game rules for the simulator. Required next gate: lead review corrected code/checks, then separate final-candidate Devin live assignment in Main's 01:00–05:00 Toronto window. No role/lease/device access occurred in this offline phase. Missing natural appearances remain unavailable, never a silent pass. Status remains fixing harness findings / awaiting live validation; no acceptance, merge or push of PW05 production code.
