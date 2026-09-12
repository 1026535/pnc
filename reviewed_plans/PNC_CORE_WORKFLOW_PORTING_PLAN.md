# Core workflow porting: A's continuation plan

## Scope and source of truth

The original request was to port remaining existing workflows to the new core, using
workflow-named feature branches and Luna for concrete implementation. Its execution
record lived in [the porting guide](../instructions/CORE_WORKFLOW_PORTING.md),
[validation ledger](PNC_CORE_PORTING_VALIDATION.md) and the local September 12 pause
checkpoint. This document consolidates its remaining execution plan without replacing
the canonical guide or discarding historical evidence.

Use [the coordinated backlog](PNC_AB_COORDINATED_CONTINUATION.md) as the sole shared
ownership/dependency table. Its authority and exclusions supersede prior narrow
publication-only milestones. This is implementation through completion of A's original
remaining scope, not another integration-only stop.

## Retain and retire

Retain completed A01/A02/A04/A05/A06/A07/A09/A10/A11 implementations and tests.
Do not rebuild readiness, popup recovery, active-castle scanning, shared Chat sending,
archives, direct/authored collection, modeled building focus, castle selection or
Campaign navigation assets. Castle alternate-target and automated Campaign navigation
proof remain explicitly pending; code landing alone does not satisfy them.

Retire from A's plan any independent OCR/row parser, shared predicate/catalog/guard
implementation or observation-publication workaround: these belong to B. Resource
workflows must not add a second mutation boundary. Do not create empty ports for catalog
TaskIds without an existing implementation. Broader Daily new-capability work is D01,
while migration of existing Daily execution remains A17.

## Implementation sequence

1. Establish a clean workflow-named branch from the coordinated base, preserving other
   worktrees. Verify current direct/authored bindings against the seven remaining legacy
   tasks: Login, SendMail, BuildingConstruction, BuildingUpgrade, Research, Gathering and
   Campaign. Use that narrow caller check to catch new completed work, not a broad audit.
2. Supervisor: define X01's smallest concrete typed operation/authority/journal contract
   and tests, reusing existing exact target/budget semantics. Consume B's published facts;
   record missing observations once and batch only material blocker requests under the
   shared plan's communication rule. One Luna xhigh worker implements an unblocked port;
   if Login lacks controls, continue the existing Daily adapter or another supported slice.
3. Implement X01 offline and prove rejection before dispatch, current-frame guards,
   journal continuity, exception/cleanup ownership and ambiguous-result no replay. Do not
   simply enable the resource-changing enum. Resolve concrete authority-model gaps before
   dependent implementations, and retain denial for unsupported actions.
4. Port A08/A12/A13/A14/A15/A16 in coherent workflow slices as B's producers and X01 permit.
   Preserve canonical parameters, meaningful completion, supported direct/authored
   behavior and migration of obsolete callers. Remove obsolete legacy paths only after
   replacement consumers/tests exist. Campaign's existing endpoint is battle preparation;
   do not silently promise a full battle loop or Daily farm policy.
5. Port A17's existing Daily coordinator and session/adapters through the same boundary.
   Preserve full-sweep semantics, recognized/unknown outcomes, exact claims, resource-item
   selection, Hero Hall durable singles/cooldowns and journals. Keep automatic execution
   disabled and leave new features, release configuration and scheduling to D01.
6. Integrate B/A slices into the single candidate at useful dependency boundaries. Reuse
   valid component evidence, validate changed production combinations, and publish exact
   reviewed commits. Do not repeat completed component merges. Main landing authority
   follows the shared plan's explicit rule; lack of it does not stop independent coding.
7. Close the porting ledger with each row's code, bindings, tests, integration commit and
   remaining live limits. Prepare exact live-proof requests for blocked rows, without
   treating an unanswered request as approval or blocking unrelated offline work.

## Validation and stop conditions

Use the repository runner, focused/affected tests per slice, and the required combined
portable full gate. Preserve B's real-builder Research regression and actual active-detail
postcondition, A's real-context castle mismatch/no-replay regression, Campaign return-chain
tests, mainline Chat contracts and atomic journal/locking tests. Test consumer behavior
through the real builder when it depends on B's publication, not only synthetic controls.

Supervisor A reviews Luna's exact diff and handles uncertain architecture. One Luna worker
at a time; no live actions by the worker. A can fix routine issues and continue without
another permission request. Stop the affected row for an unresolved behavior/authority
decision, missing producer/evidence or failing checks with no diagnosed fix; record the
symbol/fixture needed and continue unblocked rows. No worktree cleanup or new task creation.

## Working status

- Start: shared plan baseline; prior A/B component work integrated and offline validated.
- Continue current X01/consumer work; do not restart or resend settled producer requests.
- Dependencies: record missing facts once and reference B's published interface evidence.
  B owns producer contracts; A owns consumer acceptance and integration. No routine peer
  acknowledgement or shared-file ownership negotiation is required.
- Live: alternate-castle switch, Campaign automated route and remaining mutating/sending
  workflows need separate exact authorization and evidence.

### September 12 continuation: first implementation slice

- `codex/daily-mutation-core-bridge` starts at published `bad1898f`.
  X01 initially admits only `CLAIM_COMPLETED` through `CoreDailyClaimBoundary`:
  exact `DailyMutationAuthorizer` acknowledgement, canonical active-castle preflight,
  matching durable checkpoint, existing `JournaledDailyClaimExecutor`,
  `JournaledMutationDispatcher` and `DailyRunJournalStore`. The context exposes a typed
  claim operation, never a raw action callback. Unsupported resource effects remain denied.
- A17's existing claim-only connected runner now uses `CoreDailyMaintenanceWorkflow`
  and the canonical coordinator through core navigation/observations. Normal/adjusted
  Daily scrolling preserves the existing measured gestures and requires fresh completion.
  Claims, ambiguous outcomes, full traversal and reorder policy retain their existing owners.
  Resource-item and Hero Hall adapters remain separate pending migration; this slice
  does not promote action capabilities or enable automatic execution.
- A03 Login: Luna's bounded inventory found credential/submit/account-switch/reconnect
  controls still planned, with no independent visual profiles or reliable saved frames.
  B received the exact producer requirements. The existing Login binding is retained;
  no partial implementation is labelled a completed port.
- A15/B04: B owns the proved Gather-node and formation profiles/controls in both
  observation paths. Existing resource-node metadata stays canonical. Exact march-slot
  counts and a correlated post-dispatch receipt are not proved by saved evidence.
  A must preserve ambiguity without replay; World-map return alone is insufficient.
- A16/B05: the remaining consumer ends at battle preparation. B was asked for supported
  stage identity/geometry, the stage-to-preparation control and preparation screen proof.
  Existing A map/chapter/stage assets and measured return routes stay intact.
- Device: A acquired the canonical `serious_stuff` account reservation for implementation.
  Lease acquisition performed no game action. Workers remain offline; no prior live
  budget has been replayed or treated as renewed authority.

Reviewed X01 claim boundary and A17 claim-only adapter: 16 focused new tests passed;
`tools/run_tests.py affected --base origin/main --explain` selected the mandatory
full fallback (shared contracts/new modules): 1,901 passed, six skipped, no failures
on September 12. Five skips are unavailable optional screenshots; one is Windows
symlink privilege. `git diff --check` passed. No live claim was attempted.
Other mutation capabilities and Resource Item/Hero Hall core adapters remain pending.

The connected summary also rejects an otherwise finished sweep with unknown quest
titles; the real composition regression preserves these as incomplete work.
