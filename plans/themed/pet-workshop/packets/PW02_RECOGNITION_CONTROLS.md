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

Storage is outside the board-only workflow. Its recognition is passive: if a drawer is already visible, publish an excluded surface rather than actionable board contents. Do not open, manage or dismiss storage as a feature or as an acceptance exercise. The existing captured overlay regression proves this classification boundary; a dedicated live storage visit is not required. This clarification supersedes the intentional storage checks in the historical execution records below and does not waive applicable board-workflow validation.

## Focused validation

Replay the smallest representative native board/detail/transition captures through both production publishers. Check content, measured controls and frame provenance together, including repeated ingredients and clipped cards. Record exact readable coverage and missing action-state captures; keep those qualifications open for PW10.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Recognized fixture manifest, measured-control/profile ownership, both-publisher checks and the four-pair route-evidence table. PW05 consumes the labels; PW07 consumes the accepted route facts. Missing current action-state evidence stays explicit for PW10.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.

### Acceptance — 2026-09-21 UTC

**Accepted for stated recognition/control coverage; landing in progress.** Final live candidate `b405304d92a1577472c88511d1679d8c717b1337` passed the lead's independent review after the complete correction cycle. Integrated `95e31da` is based on current main `f6fa298`; runtime, tests and packaged resources are byte-identical to the final offline/live candidate. Only documentation/plans changed during integration. Final full proof remains **2,833 passed / 7 unchanged environmental skips**, with source fingerprint `6fc1657581eafd52e08793b648c44cb2eca452ae059029cfaf5ae47a549e5e46` bound to `b405304`. No repeated full/live suite is justified by documentation-only integration.

The separate Devin turn 009 ran one **234.6-second** Main/Poney NPC C31 lease (17:49:29.039–17:53:23.600 UTC), ten non-spending inputs and no launch/reconnect, castle switch, storage or raw Back. Actual candidate paths published equal complete typed payloads from native capture 33: **LV7, EXP67/90, energy15/200**, with frame/layout provenance. Lead visually verified the header and all eleven identified pieces using the canonical bottom-up row numbering. The earlier apparent row mismatch was a lead interpretation error. Measured Manor→Workshop and Workshop→Manor→Home controls passed; Main ended stable Home. Lead independently confirmed lease release and restored original read_only plus complete config hash.

Acceptance does not promote unknowns to facts: only 11/26 occupied cells had known identities on this board; most item states and both visible orders remained unknown/unreadable. The parser safely abstained. Existing ready-three-coconut, clipped-card and missing-reward regressions remain part of the accepted saved-image proof. Home→Manor succeeded as exploratory fresh-label setup but still lacks a canonical measured source-control owner, so PW07 must not register that edge yet. Four-mechanic, recycle and consumption/level-result qualification remains with PW10. Prior unchanged item/order/help evidence remains reusable; storage stays excluded with a passive saved-frame guard.

Evidence in the recognition checkout: `.local-data/review/pw02/{review-live-turn009.md,acceptance-proof.json,main-role-restore-scoped-board.json}`; `.local-data/devin-live-test/runs/pw02-main-20260921/turn-009/{handoff.md,evidence.json}`; complete artifact references in `live-scoped-board-b405304/evidence.json` and its canonical trace. Native board PNG: `.local-data/artifacts/2026-09-21/pet_workshop_pw02_board_scoped_b405304/20260921T175231Z_c3_board.png` under the shared root. Source-bound offline result: `.test-impact/pw02-storage-final-results.json` in the recognition checkout.

PW05/PW07 may consume the immutable landed dependency once push is verified. The following dated records are historical and retain failure/authorization provenance.

### Current live continuation — 2026-09-21 UTC

**Awaiting validation, not accepted or merged.** Candidate remains `b405304d92a1577472c88511d1679d8c717b1337`; the source-bound offline evidence is unchanged. Turn 007's ignored harness bypassed initial canonical popup recovery by supplying a raw observation. The lead corrected that call after reproducing the failure offline; normal recovery already worked. No production popup change was justified. Evidence: recognition checkout `.local-data/review/pw02/review-live-turn007.md`.

Turn 008 verified active **Poney NPC C31**, with no switch, launch or reconnect. Its five measured taps were canonical identity navigation. One lease lasted **299.4 seconds** (17:34:00.896–17:39:00.266 UTC), with zero spending and stable Home at exit. The work cutoff refused the first exploratory Manor swipe; Workshop was never reached. The lead independently confirmed lease availability and restored Main's original `read_only` role and complete config hash. Do not call this board or route acceptance.

Lead review found unnecessary full Home-content requests in the ignored harness. Exact saved-frame replay preserved identity/layout/guard/controls with narrow requests: builder 15.96s versus 1.63s; navigation perception 14.14s versus 1.05s. These are single measurements, not latency guarantees. The prior live offer remains blocked through both narrowed paths. The corrected harness leaves full Workshop publication, canonical fresh castle identity and every phase/input limit unchanged; two deadline/full-equality regressions pass. Evidence: `.local-data/review/pw02/{review-live-turn008.md,saved-home-scope-profile.json,scoped-popup-proof.json}` and live-run `turn-008/lead-scope-correction/execution-proof.json`.

The same `global-milk` session is resumed as **turn 009**, startup verified, with one five-minute phase on Main's active eligible non-Hopeful castle. No switch, launch/reconnect, spending or storage. The lead owns temporary role restoration in `.local-data/review/pw02/main-role-restore-scoped-board.json`. Final board/header and equal same-capture production publication remain the acceptance gate, followed by supported return. The user was notified of the observed failure, release, offline correction and new bounded check.

**Completion transport limitation:** turn 007's native callback failed with an empty tool catalog; an attempted bridge fix failed actual verification and was reverted. Turn 008's callback arrived successfully, so delivery is intermittent and no repair is claimed. The lead also waits directly on the current supervisor. Turns 007/008 are resolved with reviewed evidence and concrete subsequent assignments; later queue dispatch must retain a functioning completion owner.

### Current correction disposition — 2026-09-21

**Offline ready, awaiting final board validation; not accepted or merged.** Candidate `b405304d92a1577472c88511d1679d8c717b1337` includes fetched main `68cb935`. Lead reviewed cedar-stealer turn 013's actual changes and found no blocking code defects. The canonical storage profile now recognizes both saved drawer placements, and the header parser leaves both energy fields unknown for an invalid OCR denominator while preserving `0/200` and `240/200`. Storage operations remain excluded; the user's clarification above governs acceptance.

The lead independently verified the full-suite evidence against HEAD and source fingerprint `6fc1657581eafd52e08793b648c44cb2eca452ae059029cfaf5ae47a549e5e46`: **2,833 passed, 7 unchanged environmental skips**, all 334 modules, no failures/errors. Five additional lead checks passed, covering the two drawer fixtures, invalid/zero/over-capacity energy, real header OCR and native RGBA board publication. The new tracked fixture is byte-identical to the original crashing capture. Evidence is in the implementation checkout's `.test-impact/pw02-storage-final-{selection,results}.json` and `.local-data/review/pw02/{review-turn013.md,lead-turn013-regressions.log}`.

The remaining final-candidate live boundary is board classification/header and same-capture publication, followed by supported return. Prior unchanged dialog/route evidence remains reusable; do not repeat storage, detail/help or strip exercises for this correction. Global-milk's next package is **offline preparation only** of one five-minute phase with one lease and a single deadline. The lead must review that harness before arranging another short Main window. Main is released/read_only, and no reconnect is currently authorized. PW05/PW07 remain dependent on accepted PW02.

**Preparation reviewed:** global-milk turn 005 completed offline. Lead corrected three execution/evidence defects: publisher disagreement omitted from the pass verdict, reuse of the preparation manifest path, and nested runtime calls bypassing deadline gates. The reviewed copy preserves prior evidence, refuses a second invocation, compares complete typed Workshop content, and gates nested captures/inputs under the original phase deadline. Four phase/import checks and two lead regressions passed; production source is unchanged. The implementation checkout's `.local-data/review/pw02/{review-live-turn005.md,final-board-preparation.json}` records exact executable paths/hashes, findings, checks and the in-flight timeout limitation. The lead has asked for Main availability; execution and PW02 acceptance remain pending that reply.

**Renewed authorization and startup correction:** the user authorized Main testing. Global-milk turn 006 used one 42.7-second lease and only launched the game; the default eight-observation readiness budget expired on the 100% login-progress splash before identity or Workshop was reached. Lead reviewed the actual image/input log, verified release and restored the complete original config hash/read_only role. This is a failed startup check, not a Workshop recognition result. The correction uses the canonical passive settler with 24 observations/90 seconds under the unchanged outer deadline; only the exact observed boot-progress text permits waiting on an unknown frame. Real OCR replay of the failure image and two boundary/verdict regressions passed. Turn 007 was delegated for one new bounded phase under the user's testing authorization, with **no launch or reconnect**, no spending, no castle switch and no Hopeful NPC/storage use. If the phone has retaken the account, it stops. Evidence and recovery record: `.local-data/review/pw02/review-live-turn006.md`. PW02 remains unaccepted until actual board evidence passes review.


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

### Final offline gate and live finding — 2026-09-21 UTC

Candidate **`276153699af57610efbd689ef058f5ff1fd66e3a`**, based on main `06d7d0d`, passed **2,831 tests with 7 environmental skips**, all 334 portable modules and 16 Workshop publication integration tests. Lead verified the unchanged candidate and source fingerprint `a2a268fe8f0b9bd6407bda20b88df68daceb036b1808f73f622b4fec14061a53` in `.test-impact/pw02-integrated-final-{selection,results}.json`. Implementation session `cedar-stealer` turn 011 is handled.

The separate Main live assignment (`global-milk`, `.local-data/devin-live-test/runs/pw02-main-20260921`, turns 001–002) verified active **Poney NPC, C31**, the outbound Manor→Workshop leg and equal dual-publisher header observations at LV7 / 200 energy. It failed on opening Fruit 1 details. The final attempt encountered **“Your account has been logged in on another device.”** No Confirm was sent. The worker reconstructed 19 non-spending inputs; overwritten interim manifests leave missing per-input and post-scroll content records. Its consolidated report is `turn-001/evidence.json`; lead disposition is `.local-data/review/pw02/review-live-turn002.md`. Both turns are handled and all worker processes/leases released. Main's original `read_only` role is restored, with the original config file hash verified. The already-asked account-availability question remains pending before further live access.

**L1 / P1 — Workshop dialogs entered generic interruption recovery.** Lead replayed the exact live native-RGBA Fruit 1 frame through both production publishers with real RapidOCR. Both correctly recognized `PNC_PET_WORKSHOP_ITEM_DETAIL` with a measured close, but public `recover_interruption_if_required` raised `SelectorResolutionError: Transient popup has no explicit safe close selector; Android Back is forbidden.` This supports a popup-ownership defect, not the worker's unproven misclassification claim. The canonical `TASK_OWNED_POPUP_SCREEN_TYPES` registry omitted Workshop dialogs.

Lead correction **`4b3926a923bd2773aa3b4c173fcc06f18e54d446`** adds item detail, order detail, help and storage to that registry. Real-fixture publication regressions now exercise public recovery on both publishers and require no automatic input or extra observation. The item-detail regression failed before the fix on both publishers; all **10** modal-publication and executor-popup checks pass afterward. Logs: `.local-data/review/pw02/popup-ownership-{before,after}.log`. Final source-bound offline validation is delegated to the existing implementation session; no source changes or live access are authorized in that validation package.

**Still unaccepted.** Required final-candidate live proof includes item/detail inspect and measured close, post-scroll order requirements/rewards/readiness, order detail/help/storage, Workshop→Manor→Home and cleanup. The outbound-only route and successful strip swipes do not pass those missing checks. Home→Manor remains exploratory setup, not a qualified production route. Resume one bounded zero-spending assignment after Main availability is resolved, retaining unique attempt evidence and all typed observations. PW05/PW07 cannot consume PW02 as an accepted dependency yet.

### Short-window retest and storage finding — 2026-09-21 UTC

Final candidate **`4b3926a`** passed **2,831 tests / 7 environmental skips**, all 334 modules. Lead independently recomputed source fingerprint `274476bfd1595fb34b8bb9121322f3c44367cc0fa57a1fb3b4016f9ba20ccbff` and checked the matching commit in `.test-impact/pw02-post-live-final-{selection,results}.json`. Saved native-RGBA/real-OCR Fruit 1 replay also passed through both publishers and public recovery. Implementation turn 012 is handled.

The user permitted a brief Main window while playing on the phone. `global-milk` turn 003 ran candidate `4b3926a` on **Poney NPC C31**, with zero reported spending. **L1 is closed for observed item detail, order detail and help:** the surfaces stayed available to the caller and measured closes returned to Workshop. The apparent same-frame failure was a harness mistake: lead verified the same FrameRef and equal typed Workshop payload; the differing hashes were respectively encoded PNG bytes and decoded pixels. No PW02 source change is required for that test criterion.

**L2 / P1 remains open:** opening storage routes a frame into `WorkshopContentProducer.board_additions`, where header OCR constructs `WorkshopEnergy(capacity=0)` and raises. A missing/incorrect overlay classification is material independently of that exception: do not accept underlying actionable board controls behind storage. The canonical domain rejects zero capacity correctly; the vision boundary must abstain on invalid OCR instead of crashing or publishing a false zero-energy stop. Existing tracked storage fixtures pass both real-OCR publishers, so the actual saved failure frame is being curated for lead diagnosis. Code corrections and regression proof remain offline.

The live package is **not accepted**. Its top-level detail check says passed despite its failed storage subcase, and post-back screenshots labeled storage actually show Manor. Return actions at 12:53:16/12:53:32 appear in the cited log, but the handoff attributes them to the wrong attempt; their source/control provenance is pending curation. The lead disposition is `.local-data/review/pw02/review-live-turn003.md`; worker manifest is `.local-data/devin-live-test/runs/pw02-main-20260921/turn-003/evidence.json`.

Execution also exceeded the brief: the worker acquired **seven leases from 12:38:47 through 13:13:28 UTC**, ending at Home and releasing at **13:19:06 UTC**. Resetting the 600-second budget per attempt did not honor one short phase. It introduced raw BACK recovery and overwrote earlier attempt manifests. These deviations are recorded, not accepted as future authority. Lead restored Main's original role and verified the original complete config hash, confirmed the lease free without ADB, and notified the user. **No further Main access until another window is arranged after offline corrections.** Future validation must use one lease and one absolute deadline, with the evidence/cleanup path prepared before reconnecting.

Offline-only `global-milk` turn 004 is assigned the actual saved storage-failure capture and minimal return-leg provenance, with no emulator/config/source/Git access. Native completion remains active. The coordinator and shared main include fetched `origin/main` at `76a6957`; candidate synchronization follows curation and precedes its next correction gate.

Turn 004 is now reviewed and handled. The actual failing native-RGBA frame is `20260921T131757Z_post_actions.png` in the canonical `2026-09-21/pet_workshop_pw02_retest_t3_20260921` artifact directory. Lead visual review found that the old reference has five storage slots (four occupied), while the live frame has six occupied slots. Get Slots moves from the first to second column; both profile anchors searched only the old column. The existing templates match the new frame above their unchanged thresholds when searched across the qualified drawer bands. The lead also confirmed the two return legs belong to the 12:49–12:53 session, using turn-004's corrected trace attribution.

Resolved L2 implementation is delegated to **`cedar-stealer` turn 013**, starting at **`c4a55e3`** after a clean rebase onto current main **`68cb935`**. Scope: extend the existing storage profile's bounded search, abstain on energy OCR with nonpositive denominator, promote the exact native regression fixture, and verify both production publishers plus valid-zero/over-capacity behavior. No shared fingerprint redesign or emulator use. Lead brief: `.local-data/devin-briefs/pw02-storage-correction.md`. Final source-bound offline proof and later applicable live proof remain required; Main stays released/read_only.

The user clarified that only the board is needed. The lead's intentional storage-opening live check was unnecessary and has been removed from subsequent assignments. The already-scoped L2 fix remains only a passive excluded-overlay safeguard plus general invalid-energy-OCR handling, verified with saved frames. Turn 013 received this clarification without expanding implementation or tests; no new Main access is authorized.
