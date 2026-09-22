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

### Prepared harness cleared for bounded evidence collection

Turn 018 corrections and a final lead correction passed **37 harness checks**, with all scripts byte-compiling and source candidate `20b39e3` unchanged. Lead reviewed the actual per-frame classification, failed-input/close stop paths and restrictive no-launch resolver. Card-wide readiness cannot prove an individual Fruit 5 icon's color, and writing a detail report cannot prove its item/reward recognition; these cases now await native visual review, not an automatic pass. Unknown/factless surveys fail. Final harness SHA-256: `9f76a4d2e3c7d9318fdf4546a8245eafa64e90e2c4ee8255beb8c02ba2843acf`; manifest: PW05 checkout `.local-data/review/pw05/live-preparation/preparation.json`; review: `.local-data/review/pw05/review-turn018.md`.

Status is **awaiting validation**. No live phase has run or been accepted; separate Devin live-test dispatch remains limited to 01:00–05:00 Toronto. The window-continuation/error record was updated, with the single-heartbeat scheduling limitation still explicit. Turn 018 was resolved only after review, correction/checks and recording this concrete wait. PW07 continues independently.

### Live phase launched after explicit user release — 2026-09-22 UTC

The user confirmed immediate Main release through 05:00 Toronto and included Hopeful NPC. Lead updated only the ignored harness's exact-date time gate and removed its Hopeful exclusion; **38 offline harness/window checks pass**, with source `20b39e3` unchanged. Final harness SHA-256 is `9b90af77e419fe87a4c4f51c33b0ac291259be69147789137109dd1d10d880bd`; phase helper hash is `4c7702df40f3293a19d0bdd441d5449324b2298c3118da2b2d6251b70f6cdb50`.

Separate live session `laced-ferryboat`, turn 001, is running in the exact PW05 checkout via `.local-data/devin-live-test/runs/pw05-main-live-released-20260922`, brief `.local-data/devin-live-test/briefs/pw05-main-released-20260922.md`. One active C24+ Main castle, Hopeful permitted, no switching and **zero spending**. Main is temporarily `live_testing`; lead restores the original role from `.local-data/review/pw05/main-role-restore-released-20260922.json` after terminal cleanup. Curated evidence and independent live review remain pending. The user's broader current-energy depletion request is a subsequent reviewed gameplay phase, not part of this recognition lease.

### Closed-instance setup corrected — live turn 002

Turn 001 stopped before ADB because the configured Main instance was closed and the lead brief prohibited launch. All C0–C5 remain not-run; zero inputs/spending. Lead reviewed the actual exception and cleanup evidence, independently acquired/released the canonical lease, and restored Main read_only. This is a lead-resolvable preparation constraint, not missing user authority.

Lead permits ordinary canonical configured startup within the existing Main release, with one app foreground launch and no restart/reconnect/takeover/switch. Canonical `close_at_phase_end` preserves existing instances and closes only one started by this phase. **40 harness checks and bytecompile pass**; source `20b39e3` is unchanged. Corrected brief `pw05-main-startup-20260922.md` resumes `laced-ferryboat` turn 002, writes a new `pw05-main-recognition-20b39e3-startup` output directory, and retains all recognition/spending/time gates. Main is temporarily live_testing; current restoration record is `.local-data/review/pw05/main-role-restore-startup-20260922.json`. Final live evidence and acceptance remain pending.

### Live turn 002 failure and resolved correction — 2026-09-22 UTC

Command: validation Python `.local-data/review/pw05/live-preparation/pw05_live_check.py` on frozen20b39e3. Canonical startup succeeded; one app launch and zero taps/swipes/energy/purchases. Before Workshop, a delayed Lucifer offer remained UNKNOWN: C0–C4 not-run, C5 failed Home return. The phase-started instance closed, lease release was independently verified, original Main read_only restored, and canonical host inventory confirms Main stopped. Curated evidence: live run `pw05-main-live-released-20260922/turn-002/evidence.json`; harness report: `pw05-main-recognition-20b39e3-startup/evidence.json`; native frames: root artifacts/2026-09-22/pet_workshop_pw05_recognition_20b39e3_startup.

**L02-R1, blocking:** lead replay disproves the worker's missing-profile diagnosis. Existing Lucifer artwork and measured back templates match the final nativeRGBA900x1600 frame at1.0. The actual capture sequence briefly matches Home base anchors at02:01:52, setting post_login_proven; blanket exclusion of subsequent blocking profiles suppresses the delayed offer. Lead evidence/review: `.local-data/review/pw05/startup-gap/lead-reproduction.json`, `lead-sequence.json`, `lead-cleanup.json` and `.local-data/review/pw05/review-live-released-turn002.md` in the PW05 checkout.

Resolved implementation is delegated to `cedar-stealer` turn019: keep demand-driven base-first matching and expired-family suppression, allow the observed Lucifer family after Home when base identity is unknown, and consolidate eligibility in its existing owner. No generic matcher/threshold/CoreRuntime changes. Add captured same-session sequence regressions through both publishers, preserve independent identity/control guards, and record reusable provenance. Final source-bound offline checks and a separate reviewed-candidate Devin live retest remain gates. PW05 is **fixing findings**, not accepted; independent PW07 work continues and current-energy depletion remains pending.

### Turn 019 review and final narrowed candidate

Worker correction `e665220` passed 2,848 tests/7 skips, with independently recomputed fingerprint `08cfeac4` matching the final source and native fixture provenance verified. Lead finding **R19-1**: removing blanket exclusion also re-enabled King Return/unconsumed Valiant after Home, outside the observed Lucifer scope. Lead corrected at `525807bb7452e7cffa40c7baca51139eb69f7567` in the existing eligibility owner, extended retained-expiry tests and clarified the workflow note. Native same-session Home→Lucifer replay passes both publishers; all other blocking families stay expired.

Same worker turn 020 runs a fresh final source-bound affected/full gate in `.test-impact/pw05-final-narrow-{selection,results}.json`. Ignored final-candidate live harness is prepared with a new output directory and 40 passing checks/bytecompile; collection is **not cleared** until this gate passes. Source/live acceptance is pending; no feature merge/push. Review/evidence: `.local-data/review/pw05/review-turn019.md` and `startup-gap/lead-narrow-correction-proof.json`.

### Final source gate passed; live turn 003 dispatched

Final `525807bb7452e7cffa40c7baca51139eb69f7567` affected/full proof: **2,848 passed/7 environmental skips/0 failures**, run `e00d00cb`, 1,681.15 seconds. Lead recomputed source fingerprint `0a2d17a3c013dd02adff1d89e19fed2d60d0b2047c02c6aee45adc19a202420c`, matching actual working source, selection, results and committed HEAD. No source edits occurred in turn 020; tracked tree remains clean aside from preserved unrelated untracked paths.

Separate `laced-ferryboat` live turn 003 is dispatched on that exact candidate using the reviewed 40-check harness, output `pw05-main-recognition-525807b`. Active C24+ Main including Hopeful is permitted; zero game spending, same 900-second lease/120-second return reserve/30-second release margin and exact-date user release. Ordinary canonical startup allowed once; preserve existing instance and close only one started by this phase. Lead owns `.local-data/review/pw05/main-role-restore-525807b-20260922.json` and independent native C0–C5/delayed-popup evidence review. Feature remains awaiting live acceptance.

### Live turn 003 startup failure; bounded readiness correction

On final 525807b, the single app launch failed in **0.604 seconds** while the native capture remained on Android startup. C0–C4 and delayed-Lucifer live case were not-run; C5 Home return failed. One launch attempt, zero taps/swipes/keys/game spending. Lead disproved the worker's internal-retry attribution: later fatal publication includes cleanup, while launch failed immediately. Exact subprocess details were absent from old harness logs, so boot readiness is a supported hypothesis rather than a proven error cause. Main role/lease/stopped state were independently restored and verified; prior source offline proof remains valid. Review: `.local-data/review/pw05/review-live-released-turn 003.md`.

Lead corrected ignored setup only: at most 90 seconds of leased read-only Android boot/configured-package readiness checks before one app launch, within the existing 900-second phase; preserved launch error details. **45 harness checks and bytecompile pass.** Same live session resumes turn 004 with fresh output `pw05-main-recognition-525807b-ready`; original-role restoration record is `.local-data/review/pw05/main-role-restore-525807b-ready-20260922.json`. No source change, acceptance, merge or energy depletion. PW07 continues independently.

### Live turn 004 reviewed; missing variants remain open

Final525807b reached Workshop on freshly verified Poney NPC K157C31: level7, EXP67/90, energy106/200 at04:21Z. Same-frame publishers agreed; bounded survey and one detail visit executed; measured return reached stable Home. Sixteen inputs (one app launch, twelve taps, three swipes), zero gameplay mutations/spending. Lease04:18:50–04:24:28Z released; phase-started Main stopped; lead independently verified cleanup and restored read_only at04:28:48Z.

Lead corrected worker evidence interpretation: the native fruit is Fruit4, not Fruit5; order1 is fully visible but unreadable, not clipped; order2 is complete/two-piece/feed1634/not-ready, not lasso. Detail1 does not establish Wood10/Fruit5/lasso. Actual safe abstention is supported, while blue/green Fruit5, ready order, three-piece rejection and eligible two-piece lasso/detail remain unavailable. C2/C3 pass their executed navigation boundaries only. PW05 stays **awaiting validation**. Review/evidence: `.local-data/review/pw05/review-live-released-turn004.md` and live run `pw05-main-live-released-20260922/turn-004/evidence.json` in the PW05 checkout.

Devin `cedar-stealer` turn021 prepares a focused zero-spending follow-up on configured Main castle `npc_on_hopium`, using the canonical selection workflow and fresh exact identity under one bounded lease. Lead observed Hopium selected in the original September16 exploration's identity frame, making it the evidence-based target for naturally occurring variants. Preparation remains offline, frozen source525807b; no new live phase until lead review. Exact-date Main authority ends05:00 Toronto. Current-energy depletion remains a separate pending gameplay assignment.

The shared delayed-Lucifer fix passed actual Home→offer→measured close→Home in this run. Its isolated main-based candidate9b87cdb passed the final full portable gate: **2,836 passed/7 environmental skips/0 failures**, run `ac14a982e39f4af59551a8f8b0ded55d`, 1,750.96seconds. Lead independently recomputed the matching source fingerprint `7573cba93cef296788ae052afa45d961e8b04d36947f1e61526a1626825db3ac`. Clean rebase over status-only main produced accepted landing candidate `21381a2bbefcc480becf2b73907e686775e4de3b`; runtime/tests/resources remain identical. Accepting this slice does not accept the remaining PW05 feature. No new simulator game rule was established: this run's findings concern captured recognition and evidence classification.
