# A workflow implementation restart — September 13, 2026

## Current purpose and execution boundary

Current user authorization (September 13): `157_farm` and `testing` may be used
for any in-game action needed to implement and validate these workflow ports,
including necessary resource spending. This supersedes this restart document's
earlier live-action restriction for those two instances. It does not authorize
mainline landing, unrelated vision/YOLO work, real-money purchases, or scheduler
activation. Resolve fresh target identity through the canonical runtime, hold its
exclusive lease across dependent steps, and record each bounded action and result
through the existing mutation boundary where applicable. Ambiguous outcomes are
not authority to replay an action. Workers remain offline.

Resume the unfinished original core workflow ports against B's published vision work.
This supersedes this file's September 12 wait-for-B instructions and initial sequencing.
B has finished a reviewed implementation slice, not its complete vision plan. A may resume
supported offline implementation after the integration checkpoint below; unsupported
producer dependencies remain parked. This document's publication does not itself send
or resume a task. A uses it when the user delivers the restart instruction.

Keep [whole-file ownership](PNC_AB_COORDINATED_CONTINUATION.md#exclusive-whole-file-ownership):
A owns workflows/navigation, runtime composition, canonical action/mutation boundaries and
consumer tests; B owns vision, perception models/IDs, assets/catalogs, parsers, both observation
paths and vision tests. YOLO and map-object integration belong to their separate active tasks.
No new parser, local popup bypass, duplicate mutation mechanism or speculative adapter.
Use one reusable Luna xhigh worker for concrete repetitive code/tests. A owns analysis,
uncertainty, orchestration and review. No peer polling or per-slice ownership negotiation.

## Verified Git baseline and completed work to preserve

Verified locally and by remote ref query on September 13:

| Ref | Exact commit / condition |
|---|---|
| `origin/main` | `850bdb747be79bb78363b8dca49a0097c6ed6546` |
| `origin/codex/non-yolo-recognition-continuation` | `93798a64de73538c8992c953b7394598468911f9`; feature worktree clean |
| `origin/codex/workflow-recognition-integration` | `199402099b8a1d840aaf2916e39ed63d7d112a9b`; candidate worktree clean |
| Relevant common baseline of A candidate and B/main | `521019b15d358b2aab6ce50475ebc22841958b4e` |

B's tip includes current main, but does **not** contain A's Daily claim/core bridge
`291f049` or Development Research `9e34d14`; those remain in A's candidate `1994020`.
A tip-to-tip diff showing those files absent on B is divergence, not evidence B deleted
A's work. Do not replace A's candidate with B's checkout or cherry-pick duplicate milestones.

The main checkout at `C:/Users/lebel/pnc` was dirty and behind remote at inspection, with
unrelated castle-target/game-reference/YOLO and runtime-plan work. It is not a staging or
integration location for A. Preserve all historical worktrees and other tasks' changes.

Retain these accepted components and their tests:

- A's existing readiness/popup/castle/roster/Chat/mail-collection ports, Campaign map/chapter/
  stage entry/return routes, claims-only core adapter and bounded Development Research.
  A's last candidate reports 1,911 passes/six skips. Broader Research/callers are incomplete.
- B's Gathering/March and Campaign recognition, measured Stage/Challenge controls, corrected
  Player Mail Compose, selected Bag Resource tab, separate Hero Hall Free Recruit 1x control,
  and guarded normal Research Start through both production paths.
- B's newest explicit non-actionable label publication, zero-additional-OCR diagnostics,
  terminal retry reporting, and `ActionExecutor._validate_selector_input` label rejection.
  The narrow executor and earlier consumer-test exceptions followed direct user approval;
  they do not transfer ongoing action/workflow ownership to B. Preserve them during integration.
- All **40 current profiles**, recorded reference provenance and earlier useful fixtures.
  Recount on changed bases and preserve legitimate newer additions rather than forcing 40.

B's latest full fallback reports 1,941 passed/six skipped at `93798a6`; this validates B's
slice, not the combination with A's additional code. The original vision release has an
installed-wheel check; the latest label/diagnostic slice changed no assets.

## What B actually finished and what remains outside A

The [implementation report](PNC_NON_YOLO_RECOGNITION_IMPLEMENTATION.md) explicitly calls
`93798a6` the first remaining-plan slice. Its [checklist](PNC_NON_YOLO_RECOGNITION_REMAINING_CHECKLIST.md)
still leaves shared guard/content region migration, removal of full-screen OCR, complete
required-field gap diagnostics, independent qualification and captured-family dispositions
unfinished. Zero additional OCR during diagnostic export is not zero full-screen OCR.

B's [current vision plan](PNC_NON_YOLO_RECOGNITION_PLAN.md) supersedes the older coordination
plan's full-frame fallback allowance. A neither expands that fallback nor implements B's
migration. Existing partial production behavior can support scoped offline workflow work;
do not claim complete vision/zero-OCR or final Daily readiness from those checks. Before
an affected workflow's final acceptance, require its actual production facts and guards.

B's live exploration also produced Research/building/Campaign/Gathering/Alliance/account
captures under later explicit user requests. Captures and action receipts are evidence,
not automatically new producer implementations, new Daily features or current authority.
Use the [capture findings](PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md) and scoped game-reference
notes to avoid replaying actions. Their source APK and live build differ and are recorded.
Raw evidence is locally available in B's worktree under
`.local-data/artifacts/capture_gap_exploration/20260913T030954Z/` (`events.jsonl`,
`evidence_sidecar.json`, frames); account/mail images require sanitization before tracking.

## First checkpoint: combine preserved code, then implement

1. Read root/scoped guidance, the porting guide and only the relevant producer/consumer
   evidence. Inspect current candidate/feature status and fetch named refs. If a ref moved,
   assess only intervening commits; do not repeat the broad audit or alter another worktree.
2. A alone performs history-preserving integration on the existing candidate branch/worktree.
   Merge this published planning branch's reviewed commit into the candidate: this plan
   commit descends from B `93798a6`, which already includes main `850bdb7`. One merge brings
   main, B and the updated plan while retaining A's unique implementation. If integrating
   different later tips, verify ancestry instead of repeating these merges mechanically.
3. The inspected change sets overlap only in this A plan; use this current execution plan
   while retaining relevant A completion evidence. Runtime trees still need behavioral
   validation even if Git merges cleanly. No reset, force push, cleanup or broad side choice.
4. Validate the combined production boundary: real-builder Research Start/provenance and
   premium/overlay negatives; Daily/Research durable mutation and no replay; label tap/text
   rejection; retry diagnostics; Campaign producer/return routes; mainline Chat/archive and
   atomic journal/locking. Run the repository final portable full suite once on this frozen
   combination. Record real failures and skip reasons. Publish the accepted candidate.
5. Continue into the next supported implementation milestone without requiring a routine
   user approval after an offline checkpoint. Mainline landing and live actions remain
   governed by their applicable explicit authorization; this restart is not new live approval.

## Next bounded implementation: existing Daily adapters (A17/X01)

First port the existing Hero Hall adapter through the core lifecycle and canonical mutation
boundary. Reuse `HeroHallRecruitmentExecutor`, existing cooldown/checkpoint reconciliation,
and exact free-single policy; do not rewrite its parser or persist another journal.
`ConnectedHeroHallSession.recruit_free_single` still targets generic
`PNC_HERO_HALL_RECRUIT_1X_BUTTON`. Consume B's distinct
`PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON` for a proven free dispatch without changing the generic
selector's meaning. Visible Free alone is not a receipt or a substitute for current attempts,
cooldown, identity and authorized policy. Keep the existing daily completion check.

Expose only the required typed operation on `WorkflowContext`/`CoreMutationBoundary`,
using existing authorizer, observed executor and journal dispatcher. Preserve pre-device
capability denial, exact active-castle preflight, durable intent before input, observed
postconditions and no replay of ambiguous outcomes. Do not simply enable arbitrary effects.

Acceptance: production-observation evidence supports the free control and required state;
consumer tests cover free versus paid/generic/blocked control, cooldown/attempt reconciliation,
interruption/ambiguous receipt without replay, and preserved claims/Research behavior. Use
focused/affected validation per repository guidance. If required facts or a route are still
unqualified, stop this adapter once with the exact symbol/fixture blocker and continue the
Resource Item adapter where evidence permits. Do not invent a producer to keep the task busy.

Then port the existing `ResourceItemExecutor`/`ConnectedResourceItemSession` behavior:
complete inventory scan, exact stable row/item reacquisition, one normal Use, quantity/daily
receipt and existing durable reconciliation. Reuse `ResourceInventory` and its parser;
retain partial/unknown inventory semantics and bulk/premium exclusions. B's selected-state
Resource tab anchor does not establish navigation from an unselected tab. Keep full-sweep
semantics and automatic Daily execution disabled. These are migrations of existing features,
not D01's new Daily capabilities or release/scheduler work.

## Remaining original ports and prerequisites

| Work | Next A-owned implementation / exact dependency |
|---|---|
| Research (A14) | Retain Development and strict active-detail receipt. Finish broader categories and direct/authored migration only after their actual producers are qualified. Captures now exist for Economy/Military/Fortification but are not a completed producer release. Blue Start can remain visible with no idle queue; preserve eligibility and premium exclusions. |
| Campaign (A16) | Consume published Chapter/Stage/Challenge and retain routes/tests. Finish the original stage-to-battle-preparation endpoint when separate formation identity/control/content is qualified. Do not relabel stage proof as current formation data or assume a global 20 AP cost. Full battle automation remains outside the original port unless explicitly assigned. |
| Construction/upgrade (A12/A13) and remaining building endpoints (A11) | Reuse current requirement/queue/level policy and exact mutation boundary. Institute level labels now publish through both paths. Other captured building variants still need independent identity qualification; empty queue alone is not proof of a new level. Satisfied Requirement is not the unmet blocking selector. |
| Gathering (A15) | Consume selected-node/formation controls; retain exact resource/target/occupancy and receipt semantics. Captured live collection is not a production correlated-receipt parser. Available march slots remain unobserved; troop/load capacity is not slots. No new cavalry/search policy or YOLO object work. |
| Send Mail (A08) | Preserve corrected lower-left Compose and current fields. Port canonical compose/send behavior when field/current-screen/receipt contracts support it. No send receipt or recipient authorization is inferred from an empty Compose capture. |
| Login (A03) | Keep current legacy binding until the intended route is established. Captured native provider/email UI has no legacy password/Continue flow; do not manufacture controls, log out or change credentials. |
| Completed navigation/collection/Chat/castle rows | Retain; change only a reproduced regression or remaining explicitly scoped proof. Alternate-castle live proof is not renewed by this plan. |

## Stop/report and completion

B's incomplete vision work remains B-owned; A does not resume B or renegotiate each missing
field. Record one dependency list and continue supported rows. If all remaining rows depend
on unimplemented producers, stop with exact blocking facts and acceptance tests; do not call
A's original plan complete or silently absorb B's outstanding workload.

A's earlier port collision is historical. Current main contains startup/focus improvements,
but this task did not validate live discovery or resolve any Codex task/fork blocker. Preserve
other agents' runtime/configuration work. Before a separately authorized live phase use the
canonical resolver/lease and exact account/action/target/budget; do not assume either blocker
is fixed from unrelated commits. No live action or cross-task approval is granted here.

Finish A when original supported ports/callers are implemented and integrated with required
checks, with unavailable evidence/authority clearly marked. Final portable validation belongs
to the combined candidate, and live proof remains separate. Hand broader D01 completion to
the future Daily owner with exact remaining capabilities; no cleanup or scheduling required.

## Retained A completion evidence

The history-preserving September 13 integration retains A's claim adapter at
291f049f2fc11ef65a11056a609bb9b71560ee8b and Development Research at
9e34d1446a9aadd2d58c43fe70b7baf943d0bfca. Claims reuse the full-sweep coordinator,
exact authority, durable journal and unknown-title failure semantics. Their final
portable gate passed 1,901 tests with six skips. Research retains exact row
reacquisition, one normal Start, two fresh guarded active-detail receipt frames,
pre-dispatch authority and no replay. Its gate passed 1,911 tests with six skips
(1,917 total), plus 22 focused checks and diff check. These historical results do
not replace validation of the new combined tree. No live claim/Research action was
performed in those slices; the prior discovery conflict and released lease remain
historical, not a current emulator-state assertion.

## September 13 integration checkpoint result

Merged published plan 4a58e86b (including B 93798a6 and main 850bdb7) into A's
1994020 candidate with history preserved. Only this plan conflicted; the current
execution plan and the A completion evidence above are both retained. All 40
profiles survive, with no missing IDs from A, B or main. The frozen production tree
passed the final portable gate: 1,967 passed, six skipped (1,973 total), no failures,
194.006 seconds including collection/reporting. This includes real-builder Research,
mutation/no-replay, label-input rejection, retry diagnostics, Campaign, Chat/archive,
atomic journal and shared-lock checks. Five skips are optional local screenshots;
one is Windows symlink privilege. Diff check passed. The subsequent authorization
and result notes change documentation only; this offline checkpoint performs no live
operation and does not establish full workflow or vision completion.

## September 13 Hero Hall adapter slice

The typed CoreHeroHallWorkflow and CoreMutationBoundary now consume the distinct
PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON through the existing HeroHallRecruitmentExecutor,
DailyMutationAuthorizer, JournaledMutationDispatcher and DailyRunJournalStore.
The five-single/zero-diamond policy remains exact; each invocation executes at most
one eligible increment. Durable cooldown, reconciliation without replay, and the
final full Daily survey remain canonical. Unknown/zero attempts cannot dispatch,
and disappearance alone is no longer accepted as consumption. The existing legacy
canary dispatch also uses the distinct free selector, without redefining generic 1x.
Its navigation/caller migration remains pending live acceptance.

Real RapidOCR replay of both saved Hero Hall fixtures through both production paths
proved a CLEAR Hero Hall screen, distinct template Free control and Daily attempts:5.
This exposed and fixed the consumer's old generic-selector check. No vision files
were changed. Focused Hero/core checks passed (22 tests); the affected mandatory
full fallback passed 1,984 tests with six existing skips (1,990 total), no failures,
225.015 seconds including collection/reporting. Diff check passed.

Live proof remains blocked before any recruit or spending. Under separate canonical
leases, testing resolved and accepted the required game update, then encountered a
Savannah hero offer popup without a published safe-close selector. Evidence is
.local-data/artifacts/core_ports_20260913/2026-09-13/testing_hero_hall/
20260913T170227Z_core_20260913T170044Z_e9666465_0006_preflight_settle_2.png in the root
workspace. Testing was released at that popup, without a current-castle assertion.
157_farm resolved, but canonical foreground preflight failed because Android window
output did not contain exactly one mCurrentFocus field; no game action occurred there.
Those perception/runtime blockers are outside this port's ownership. No bypass was
added. Hero Hall live acceptance, final five-single canary proof and caller migration
are not claimed complete; automatic Daily execution remains disabled.
