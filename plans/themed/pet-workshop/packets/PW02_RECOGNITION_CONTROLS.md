# PW02 — Workshop recognition, orders and measured controls

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW01](PW01_SHARED_CONTRACT_CATALOG.md)

## Read before implementation

- [Plan 01: evidence and canonical vision owners](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#3-evidence-and-existing-owners)
- [Plan 01: shared contract](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#4-shared-interface-contract)
- [Plan 01: recognition verification and gaps](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#6-verification-and-evidence-gaps)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** recognition worker. **Prerequisite detail:** accepted PW01. Can run alongside PW03/PW04 after PW01 is accepted.

1. Add evidence-backed profiles for Beast Manor/Workshop board and observed detail surfaces; expand to recycling confirmation, feeding/activation/depletion and level-result surfaces as their targeted evidence is acquired. Register the corresponding selector semantics/content request family through existing owners. Do not treat a requested screen as proof of its identity.
2. Detect the grid from the proved layout/anchors and measure cell geometry. Recognize item sprite/tier and overlays separately; use cached templates and bounded OCR for energy, header, selected-item names, rewards and details. Start with the existing OpenCV/OCR tools. Unknown icons request bounded information acquisition or stop; no external vision-service dependency is introduced.
3. Parse full/partial orders and duplicated ingredient icons correctly. Preserve portrait/inspection and immediate-submit controls separately. A clipped card cannot establish a total of two. Recipe/reward lookup may explain an observation but must not replace visible evidence with a guessed server order. Apply the [progression evidence limits](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#workshop-progression-and-order-selection): report visible level, requirements and producer state without inventing hidden order type/prerequisite completion or rejecting a card because inferred level eligibility disagrees.
4. Publish the same content through both observers, including native RGBA input and provenance. Do not normalize only the test fixture to hide the existing capture/OCR boundary issue. Reuse canonical image normalization where appropriate; do not implement a Workshop-only global OCR fix.
5. Keep order positions frame-owned. A bounded strip survey belongs to Plan 03; the parser identifies visible cards, partial edges and measured scroll surface. Distinguish currently reachable order coverage from unexposed server orders.
6. Extend recognition of the four ordinary mechanics and the restricted recycling controls. Unavailable action-state evidence is an explicit qualification gap, not permission to guess its result.
7. Hand back a route-evidence table for the four entry/return pairs in [Plan 01 evidence](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#evidence-that-can-be-used-without-live-access): source profile, measured control, destination profile, artifact pair and confidence. Lead acceptance of that table is required before Plan 03 PW07 registers the corresponding production edge. Missing control evidence remains a targeted gap; no edge is inferred from a remembered coordinate.

## Acceptance

Real saved board/details are labeled correctly where evidence is readable; unknown/transition states abstain; both observers agree; no parser performs navigation, planning or input.

## Focused validation

Replay the smallest representative native board/detail/transition captures through both production publishers. Check content, measured controls and frame provenance together, including repeated ingredients and clipped cards. Record exact readable coverage and missing action-state captures; keep those qualifications open for PW10.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Recognized fixture manifest, measured-control/profile ownership, both-publisher checks and the four-pair route-evidence table. PW05 consumes the labels; PW07 consumes the accepted route facts. Missing current action-state evidence stays explicit for PW10.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.


### Execution record — 2026-09-16

- Status: **Delegated**, not accepted. Foundation implementation `14b7d68` is reviewed/tested and pushed; worker base `91afce6f9a817129f2e205b9479043744c4ca300` adds its acceptance record only.
- Scope: Recognizers, measured controls, both publisher paths and four route-evidence pairs. No live access; missing captures stay explicit. Applicable live acceptance awaits the user releasing main.
- Checkout/branch: `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-pw01`, `codex/pet-workshop-pw01`.
- Native Devin session `cedar-stealer`, run `.local-data/devin-implement/pw01-platform-check`, turn `007`. Startup confirmed with `swe-2-max`, expected base and native steering/cancellation controls.
- Briefs: worker `.local-data/devin-briefs/pw02-recognition.md` and `pw-wave-common.md`. Use the explicit dependency-correct Python environment named there; global py/shared .venv lack current rapidocr. APK/extracted Lua remain offline references only.
- The existing lead monitor registered this run and the native completion callback targets this coordinating task. Lead owns independent review, fixes, applicable final-candidate live proof, integration and acceptance.
- Reviewed/tested result revision and acceptance evidence: pending handoff.

### Recovery and timed Main release

At the user's status refresh, the recorded worker/monitor processes were absent and all three worker heartbeats had stopped around 2026-09-17 01:34 UTC. The cause is unestablished. Lead verified no Workshop writer/test processes remained, checked `cedar-stealer` against native readiness and `devin list` in this checkout, preserved `turn-007/state-before-host-recovery.json`, and repaired the stale running record. No tracked PW02 source implementation had been saved; ignored measurements/crops and untracked generated `pnc_automation.egg-info/` were preserved.

The checkout was fast-forwarded to accepted main `4f1e119ae3f7a6d9e5e8891c81347a3656fbf4d3`, including the current shared observation-enricher change. Same session resumed as **turn 008**, supervisor 52372, native SWE-2 Max readiness confirmed. Delta brief: `.local-data/devin-briefs/host-recovery.md`. Scope remains offline implementation and candidate/evidence-gap handoff; no new test result or acceptance is claimed.

The user released Main at the absolute time in the [roadmap authority record](../PNC_PET_WORKSHOP_ROADMAP.md#current-execution-authority-and-acceptance-gate), excluding Hopeful NPC. A separate Devin live-test assignment will acquire its lease and verify the applicable stable candidate; this implementation worker must not independently access Main. The timed release supersedes the earlier account-availability hold.

### Windows Update recovery — 2026-09-17

At the user's status request, the turn-008 supervisor/bootstrap and monitor were absent; last worker activity was around 06:41 UTC. The user confirmed Windows Update, and Windows reported its latest boot at 13:54:06 UTC. Lead reconciled local processes, verified `cedar-stealer` and its exact checkout through `devin list`, preserved `turn-008/state-before-windows-update-recovery.json`, and repaired the stale execution record. Measurements and untracked fixture candidates were preserved; no source change or test result was accepted.

Same session resumed as **turn 009** on unchanged base `4f1e119`, supervisor 21696; native SWE-2 Max readiness was confirmed. The coordinator's `.local-data/devin-briefs/pw02-windows-update-recovery.md` directs the worker to reuse saved measurements, keep conflicting labels unknown, and return a bounded evidence question if interpretation blocks implementation. This worker remains offline. The prior Main capture pass is complete; further Main input awaits the configured-role decision. The existing continuation timer was explicitly acknowledged active and the monitor restarted with the same task and automation IDs.

### Correction review — 2026-09-21 UTC

Turn 010 returned R1–R5 corrections on `0219d42` plus uncommitted changes. Lead verified its portable test result: **2,799 passed, 7 environmental skips**, with source fingerprint `e995e23b142f773150b44df6a95481bb0b394ec140ba80b6a65a79b0f5687c40` matching the returned tree. That proof predates the additional lead fixes below and does not accept the final candidate.

Independent correction review reproduced two remaining coverage failures: dropping the EXP reward match silently removed that reward while leaving the card complete; a synthetic 52-pixel strip scroll hid one coconut behind the timer but published a complete two-piece order. The lead added independent reward-group coverage and a measured full-panel-width qualification. The lead also replaced color-only item status with separate full-cell appearance evidence, made conflicting selection votes abstain, and corrected the native RGBA test to use real OCR through both publishers. These changes reuse the shared matcher, normalization, observation contract and fixtures.

The corrected publication suite passed **15 checks**, followed by the additional shifted-strip regression (**1 passed**). Evidence: recognition checkout `.local-data/review/pw02/lead-correction-tests-2.log` and `lead-scroll-regression.log`. The original turn-010 full proof is preserved in `worker-turn010-{selection,results}.json` there. The final integrated candidate still requires its source-bound offline gate and a separate Devin live-test package on authorized Main, excluding Hopeful NPC; no Main lease or live action occurred during these corrections. Home-to-Manor remains an explicit control-qualification gap. The accepted simulator at `0724ad7` is available for development, but cannot substitute for pixel/live proof.

### Independent review and resumed corrections — 2026-09-21 UTC

**Status: Fixing findings, not accepted.** Turn 009 ended with a saved candidate (`cb386b4`, subsequently rebased to `f1593d2` and now `0219d42a5a25efa2d0d6875d4fc6bb89615f5271` on main `147d77a`). The launcher reported an incomplete final handoff; source work was preserved and reviewed directly. The worker's full offline result (2,585 passed, 7 environmental skips) had a fingerprint mismatch with the committed candidate, so it does not prove the final revision.

Lead review batch, owned by this packet:

- **R1 / P1:** A missed coconut match on the real ready three-coconut screenshot publishes `{20105: 2}`, COMPLETE and ready=True. Prove card/slot presence and read coverage independently from recognized item hits, including unknown rewards, clipped/moved cards and the two-card level-6 layout.
- **R2 / P1:** Actual candidate RapidOCR reports chest quantity **91** where the screenshot visibly says **1**, and its golden test repeats the mistake. Isolate count regions from icon graphics and ambiguous neighboring tokens.
- **R3 / P1:** Ordinary mode and Normal/none-selection states are overclaimed from identity/missing hits. Recognize action-state evidence separately; ambiguous/unsupported states must abstain.
- **R4 / P2:** The tests convert every input to RGB before publication. Direct lead replay preserves native RGBA and currently succeeds on the empty-OCR builder path, but both-publisher real-OCR regression coverage is still required.
- **R5 / P2:** The Home→Manor selector exists only as an enum/catalog entry; it has no measured publisher despite a high-confidence route claim. Qualify its actual owner/evidence or record the leg unqualified. Publish the measured order-scroll surface through the canonical view; the lead authorizes a minimal optional `order_strip_bounds` field if no existing equivalent can satisfy the consumer.

Detailed evidence and correction decisions: worker `.local-data/review/pw02/review-batch-1.md`; delta brief `.local-data/devin-briefs/pw02-review-batch-1.md`. The lead reproduced R1 using one dropped requirement match through the real producer and R2 using actual RapidOCR through the production observation builder. No live input was used for these reproductions.

Native `cedar-stealer` turn 010 owns the full PW02 correction batch. Preserve untracked `nul` and `pnc_automation.egg-info/`. The coding phase uses the explicit Python 3.13.5/RapidOCR 3.4.5 validation environment and remains offline; a separate Devin live assignment will qualify the final reviewed candidate on authorized Main. Pending corrections, final source-bound offline checks and applicable live proof all remain acceptance gates. No gameplay execution edge is accepted by this record.
