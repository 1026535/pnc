# Remaining A15 gathering workflow — bounded implementation plan

## Status, owner, and checkpoint gate

Planning snapshot: September 14, 2026. This is an A-owned remaining-work plan for porting the legacy neutral-resource
Gathering caller to the replacement navigation and mutation core. It covers one
bounded dispatch workflow with exact target, march-slot, formation, and correlated
receipt semantics. It does not rewrite cavalry selection, search, YOLO, or broader
march policy, and it does not claim collection success from a screen transition.

Read the [six-package coordination contract](PNC_CORE_WORKFLOW_PORTING_PLAN.md#six-remaining-agent-packages) before implementation. It defines the shared snapshot, exclusive-file ownership, and permission ledger that govern this plan.

The implementation worker must begin by recording:

```text
git rev-parse HEAD
git status --short --ignored
```

The expected source checkpoint is `4f332027e924a9f73e3e3740d92980d8950ddae1`
(`HEAD4f33202`). The worktree contains dirty, completed A changes and root-owned
plans/ledger files. Preserve that snapshot, never reset or clean it, and never
overwrite a root-owned hunk. Shared files are serialized with the Buildings plan
and root's concurrent work:

- `pnc_automation/app/automation/engine/core_daily_mutation.py`
- `pnc_automation/app/automation/engine/core_workflow.py`
- `pnc_automation/app/automation/engine/navigation_core.py`
- `pnc_automation/app/entrypoints/task_registry.py`
- `pnc_automation/app/entrypoints/api.py`
- shared domain/policy or observation contracts

Publish an exact intended patch range before editing any shared file and wait for
its owner to release it. Do not use another worktree, merge, reset, or commit in
this plan. Report the preserved dirty paths, changed files, focused commands, and
results to root.

The current A candidate already contains the reviewed no-claim checkpoint guard and
loading-only `CoreRuntime.observe_ready` behavior. Those are preserved inputs to this
package, not remaining Gathering defects. Do not reopen them, add a second readiness
loop, or describe a successful lifecycle exit as a Gathering receipt. The current
candidate is intentionally dirty; implementation starts from its exact checked-out
state after the producer gate, not from a bare copy of `4f33202`.

### Current evidence boundary

The saved exploration under B's continuation worktree is useful evidence, but it is
not a qualified replacement producer and it does not authorize replay. The exact
Gathering facts are:

| Saved frame | What it proves | What it does not prove |
| --- | --- | --- |
| `0148_ordinary_gather_dispatch.png` | An ordinary `PNC_WORLD_MAP` frame after the visible gathering sequence. | A dispatch receipt, a slot count, or a target-bound army status. World Map identity alone is not receipt evidence. |
| `0150_march_troop_overview.png` | A `Troop Info` row in Gathering state for Farm level 6 at `X231 Y479`, troop size `1,000`, and a remaining timer. | A qualified producer profile, available march slots, an exact active-army id, or server acceptance. |
| `0215_gathering_report_list.png` | A `Gathering Report` row for Farm level 6, `K157 X231 Y479`, displaying `31.2K` food. | A qualified producer profile or an exact unrounded quantity; preserve the displayed rounded value. |

Frames `0150` and `0215` are unmatched by B's current production catalog. Frame
`0148` matches ordinary World Map only and remains explicitly receipt-ineligible.
The captured Farm/coordinate and Buffalo Catapults formation are historical
correlation evidence; they are never copied as a current target or default lineup.
The producer must independently publish the row/frame identity, destination/resource/
state/time association, and the smallest typed receipt facts through both production
paths before the consumer can report acceptance.

## Remaining deliverables and scope

Deliver the following finite slice:

1. Port the existing `GatheringTask` target selection, world-map preflight, march
   confirmation, and dispatch behavior into a typed replacement workflow.
2. Require an exact visible resource node, available march-slot fact, selected
   formation/army facts, and a fresh correlated dispatch receipt before reporting
   success. Preserve the existing resource priority and enforce
   `max_parallel_marches` as an explicit bounded policy; the legacy task does not
   currently enforce it. The producer must publish a fresh active-march count so the
   workflow computes allowed new dispatches (for example, active 1/max 2 permits
   one, active 2/max 2 permits none).
3. Use the existing reviewed navigation, loading-only ready-source acquisition,
   durable mutation journal, and `CoreMutationBoundary`. A dispatch creates one
   durable intent and one actuator input; an ambiguous result is reconciled without
   replay.
4. Keep collection correlation observable. If the original caller only dispatches a
   march, a later collection/return receipt is evidence associated with that march,
   not permission to invent a second mutation. A separate collect-back or turn
   action is outside this bounded port unless an existing caller explicitly owns it.
5. Wire the relevant direct/authored callers once the typed path has producer
   facts and offline acceptance, then use that path for one bounded live proof.
   Promote live acceptance only after its receipt and exit pass. Leave unrelated Daily,
   Research, Resource, Hero, building, and battle policy unchanged.

## Existing implementation and caller map

| Area | Existing path | Current behavior | Porting consequence |
| --- | --- | --- | --- |
| Legacy workflow | `pnc_automation/app/automation/tasks/gathering_task.py:GatheringTask` | `TaskPreflight.WORLD_MAP`; chooses visible resource nodes by `GatheringPolicy.preferred_resources`; zero slots skip; taps `PNC_GATHER_BUTTON`, then `PNC_MARCH_CONFIRM_BUTTON` | Preserve the policy and phase order but replace generic task dispatch with typed target/formation/receipt contracts |
| Node selection | `GatheringTask.plan` | Uses published `resource_type` and spatial node; no exact server/node identity or ownership proof | Require a typed node key, resource type, coordinate/owner facts, and source re-read before dispatch; an internal server id is optional when it is not observable |
| Follow-up | `GatheringTask.plan` plus `ObservationRequest.march_confirm_follow_up` and `post_march_dispatch_follow_up` | Strict phase transitions exist; node→confirm is a replan; confirmation accepts slot decrement or return to World Map | Keep phase-specific content confirmation, but a World Map return without a correlated receipt becomes pending/failure |
| Current verification | `GatheringTask.verify` | Accepts available-slot decrease or World Map return as dispatch success; fails when unchanged map has unknown slots | Replace inferred success with target/player-army correlation and explicit status |
| Policy | `pnc_automation/app/pnc/domain/policy_models.py:GatheringPolicy` | Preferred FOOD/WOOD/IRON and `max_parallel_marches=2` | Keep these bounded inputs; do not invent cavalry/search/formation defaults |
| Entrypoint registry | `pnc_automation/app/entrypoints/task_registry.py` | `GatheringTask` remains a legacy task | Add one typed step and migrate one caller after acceptance; remove duplicate mutation ownership for that caller |
| Direct API | `pnc_automation/app/entrypoints/api.py:gathering` | Forwards to `run_task` | Preserve parameter shape while forwarding to the typed workflow and same authority/journal |
| Core dispatcher | `pnc_automation/app/automation/engine/core_script_dispatcher.py` | No typed gathering branch; step validation rejects it | Add only the explicit gathering operation and strict parameters |
| Navigation | `pnc_automation/app/automation/engine/navigation_core.py:NavigationCore` | Reviewed routes/content action primitives exist; no typed gathering target/formation/dispatch helpers | Add focused world-map seams that revalidate exact source/control and use existing ready/content owners |
| Context | `pnc_automation/app/automation/engine/core_workflow.py:WorkflowContext` | Typed navigation/open-building/content helpers; no world-map gathering method | Add narrow typed methods, preserving raw ordinary post-action and Chat observation |

The existing `tests/unit/app/automation/tasks/test_gathering.py` is useful legacy
behavior evidence. It is not proof that the replacement producer publishes the
facts required by this plan.

## Canonical owners: existing symbols and proposed seams

Keep the existing symbols as the behavioral baseline and make every new seam
explicit before implementation. The names below are an ownership map, not permission
to add a parallel runner or observer:

| Concern | Existing verified owner | Remaining typed seam |
| --- | --- | --- |
| Policy/input | `GatheringPolicy.from_params` and `ResourceType` in `pnc_automation/app/pnc/domain/policy_models.py` | Reuse the policy; add only strict capability validation, including an explicit disposition for `STONE`. The Daily quest model has `GATHER_GOLD`; the Gathering policy has no `GOLD` resource value. |
| Legacy selection/phase behavior | `GatheringTask.plan`, `GatheringTask.verify`, `choose_priority_candidate`, `TaskPreflight.WORLD_MAP` | `GatheringWorkflow` and a typed result that preserve priority and phase order while replacing slot-decrement/map-return success shortcuts. |
| Screen/content model | `Observation`, `DetectedSpatialObject`, `ObservationAdditions.available_march_slots`, `NavigationPerception.build`, `ObservationBuilder.build` | B publishes independently qualified node, occupancy, controls, formation, active-march, slot and receipt facts with frame/layout provenance. Add no consumer parser or guessed metadata. |
| Navigation/context | `NavigationCore.navigate`, `NavigationCore.transition`, `NavigationCore._observe_source`, `WorkflowContext.navigate`, `WorkflowContext.observe_content` | Add focused world-map target/formation operations only after producer fields are released; they must revalidate the current source and action point immediately before input. |
| Mutation/reconciliation | `CoreMutationBoundary`, `DailyMutationAuthorizer`, `JournaledMutationDispatcher`, `DailyRunJournalStore` | Add one Gathering capability/receipt adapter to this boundary. One durable intent precedes one Dispatch input; duplicate or ambiguous operation ids reconcile by observation and never replay. |
| Callers | `GatheringTask` is registered in `task_registry.py`; `AutomationApi.gathering` and `AutomationSession.gathering` currently reach the legacy task path; typed core dispatch currently rejects `TaskId.GATHERING` | Add one `CoreWorkflowTaskDefinition`/factory and migrate direct/authored callers together after offline acceptance. No legacy fallback may remain behind the typed binding. |

`available_march_slots` already exists as an optional field on the observation model,
builder additions and navigation perception, but the saved producer replay does not
qualify its source or freshness and there is no `active_marches` field in the current
model. Treat both as missing producer contracts until B publishes them through both
paths. A test fixture that manually supplies the optional field proves only consumer
logic; it does not close production recognition coverage.

## Producer facts required before implementation can be accepted

These facts must be published by the canonical observation producer in both
production paths. B's separate authoritative follow-up
(`PNC_B_FOLLOWUP_RECOGNITION_HANDOFF.md`) owns Resource partial, Hero results and
broader Research recognition; it does not make these Gathering facts complete.
Do not fold this Gathering producer dependency into that three-item handoff. The active/report
surfaces below are additional producer dependencies. A must not add OCR, assets,
screen anchors, classifier exceptions, or workflow-local coordinate guesses to fill
the gap.

### Resource-node source facts

Publish one exact stable node identity (server/resource point id when it is actually observable, otherwise the repository's approved typed equivalent), resource type, map coordinate, visible node geometry, occupancy/owner, and shield/hostility state. The consumer may correlate by exact resource/coordinate plus own march/formation facts when internal ids are not published. The final pre-dispatch
observation must re-read the selected tile and either confirm the same node or stop.
A label such as `Farm` with a coordinate but no identity/owner correlation is not
sufficient for a mutation target.

The source client evidence shows this re-read boundary in
`SlgWarColHandler:FightStartClickHandler`: it calls `MapData:GetTileInfo2(x,y)`,
updates the map element, and checks `playerId`/`unionId` before sending. The
replacement observation must expose the facts needed for the consumer to make the
same decision. Unknown occupancy or an enemy/shield branch stops; the workflow does
not guess that the node is safe.

### Gather and formation facts

Publish the exact Gather control on the selected node panel, the march-confirm
screen, the selected formation/army identity, and the exact dispatch control. The
formation model must identify the selected heroes/army or the approved existing
formation id; it must not silently pick cavalry or a default lineup because a field
was missing. An absent or ambiguous formation is a no-input stop.

### Slot, active-march, and receipt facts

Publish available march slots as an independent typed value with its source and
freshness. Total troops, load capacity, army limit, or a historical slot decrement
must not be substituted for available march slots. If the field is unknown, the workflow skips/stops before the Gather input according to the existing policy. The typed workflow must enforce `max_parallel_marches`; publish the fresh active-march count as well, because spare slots alone do not establish that cap.

After dispatch, publish the strongest observable receipt correlated to the same node and selected formation: a server/player army id when it is actually exposed, or exact resource/coordinate plus own march/formation facts and a target-bound status such as `ON_THE_WAY_TO` or `UNDER_CONTROL`. A later collection/return observation must retain that correlation and expose the resource point and army status/report. A generic
World Map screen, the saved `0148` ordinary World Map frame, a changed node count,
or a slot decrement without target correlation is not a success receipt. The saved
`0150` Troop Info row is the expected active-gathering producer shape; the saved
`0215` Gathering Report row is the expected completed/report shape. Both need an
independent layout identity, bounded row association, and both-path publication.

The producer must also identify reviewed return edges for the march-confirm and
post-dispatch states. Existing visual fixtures prove portions of the node and march
screens, but they do not prove available slots or a production dispatch/collection
receipt:

- `tests/data/screen_recognition/gather_node.png`
- `tests/data/screen_recognition/march_confirm.png`
- `tests/data/screen_recognition/march_confirm_empty.png`
- `tests/integration/vision/test_gathering_march_visual_profiles.py`

The producer must publish `active_marches` separately from `available_march_slots`.
The source symbols `MapArmyData:GetSelfArmyNum` and `CampDataWin:UpdatePanel` expose
busy/total army statistics, while `MapArmyData:GetSelfArmyLimit` exposes an army
limit; none is an available-slot fact. Likewise, troop size, load/carry capacity,
formation hero slots, and a boolean collecting queue cannot be used for either
`active_marches` or `available_march_slots`. A numeric value without its source,
frame reference and freshness is unknown and stops before Gather.

These are B/producer evidence inputs; they are not a reason to bypass missing
fields.

## Target design and exact contracts

Create one explicit typed operation, using the existing workflow module conventions, for example GatheringWorkflow. Its WorkflowSpec should use the shared Home-to-Home workflow boundary: enter from PNC_HOME_CITY, navigate through the reviewed World Map/node/march states, and return to PNC_HOME_CITY after a correlated dispatch receipt. Record the legacy task's final World Map as an internal transition, not as a second public boundary. A caller that needs to remain on World Map may use a separate reviewed navigation step after the workflow; do not hide a second behavior in the gather action.

Declare `RESOURCE_CHANGING` with the exact applicable capability through the
canonical mutation boundary. Both public and authored callers use this same
Home-to-Home contract and retain the dispatch receipt independently of exit.

Add only focused context/navigation seams, such as:

- `WorkflowContext.observe_world_map_content` for fresh typed node/slot content;
- `NavigationCore.open_gathering_target` for selecting the observed node and
  revalidating its identity/ownership immediately before input;
- `NavigationCore.confirm_gathering_formation` for the exact selected formation and
  dispatch control;
- a typed dispatch/reconcile method that calls the existing mutation boundary and
  returns the existing journaled result.

Names may follow the repository's established naming once the interfaces are inspected, but the data contract must remain explicit: node identity, resource type, coordinate, occupancy/owner evidence, available slots, active-march count required by `max_parallel_marches`, formation/army identity, operation id, and correlated dispatch/collection receipt. Do not use an untyped `dict` of screen labels or add a generic navigation/mutation framework.

Use `CoreMutationBoundary`, `DailyMutationAuthorizer`,
`JournaledMutationDispatcher`, and `DailyRunJournalStore` as the one mutation owner.
Use existing `GATHER_FOOD`, `GATHER_WOOD`, or `GATHER_IRON` authority only where the operation is covered by the current policy. `ResourceType` is FOOD, WOOD, IRON, or STONE, while `DailyQuestId` also has GATHER_GOLD; GOLD is not a current GatheringPolicy value. Preserve STONE as an original input and resolve a narrow standalone capability/identity for STONE (and any other unsupported resource) with the shared mutation owner before dispatch. Do not relabel STONE as GOLD or silently add GOLD to the policy. Keep one mutation per invocation, zero diamond budget, and the existing account/castle/date acknowledgement. If the policy cannot authorize a requested resource, reject before navigation. A repeated or already committed operation id reconciles observation and never taps Gather or Dispatch again.

The typed operation must use a durable intent before the final actuator input and
freshly revalidate source, node, formation, and control immediately before that
input. `CoreRuntime.observe_ready` may settle a canonical `PNC_LOADING` source once
within the existing bounded budget. Ordinary post-action and Chat observations
remain raw; no generic UNKNOWN retry or sleep loop is allowed.

Keep `GatheringPolicy.max_parallel_marches` as an explicit bound. A typed available
slot of zero is a known no-action result. A slot value that is absent, stale, or
inconsistent with the fresh confirm screen is a stop. Do not infer capacity from
`MapArmyData:GetSelfArmyLimit` or `GetSelfArmyNum`.

The legacy task parses `max_parallel_marches` but never reads it during dispatch.
Close that gap in this port instead of accepting and ignoring the parameter.
For this bounded caller, the limit applies to the active castle's own currently
dispatched marches, separate from troop capacity and remaining game slots.
Require fresh `active_marches` and `available_march_slots` facts before dispatch:
one new march is eligible only if slots are positive and
`active_marches + 1 <= max_parallel_marches`. Dispatch at most one per invocation,
even if the difference is larger. Missing active-count evidence is an explicit
producer blocker for the promised cap, not permission to silently disable it.

Full package completion preserves FOOD/WOOD/IRON/STONE input and this limit.
A useful FOOD-only proof does not qualify Stone or close its standalone-capability
dependency. Add no Gold policy value as a substitute and no unrelated resource
families. Source/producer inspection and the shared owner resolve those technical
contracts without another user spending question.

## Required behavior

### Read-only target and preflight

1. Validate the resource policy, exact active account/castle, world-map entry, and
   one requested target/formation. Select a node only from a fresh published typed
   observation and the existing resource priority.
2. If available slots are zero, return the existing no-action result without opening
   the node. If slots are unknown or stale, stop before Gather. Require a fresh active-march count for the configured `max_parallel_marches` cap and allow at most one dispatch only when `active_marches + 1 <= max_parallel_marches`; for example active 1/max 2 permits one, while active 2/max 2 permits none. Do not treat spare slots as existing active-march count.
3. Revalidate the tile/node identity, owner/occupancy, shield state, and resource
   type from a fresh source frame. A changed, missing, enemy, shielded, or ambiguous
   node stops before input.
4. Open the exact node panel and revalidate the Gather control. A loading source may
   use bounded ready settlement; an unknown or blocked source stops.

### Formation and one dispatch

1. Revalidate the march-confirm screen, available slots, exact formation/army, and
   dispatch control from fresh content. A missing formation or ambiguous control
   stops without input.
2. Create the durable operation intent before dispatch. Press the exact Dispatch
   control once. The operation carries the target node identity, resource type,
   coordinate, formation/army identity, and zero-diamond authority.
3. Reobserve fresh content and accept only a receipt correlated to the same node and
   operation: a player army id/status, an explicit target-bound active march, or the
   exact approved equivalent. A World Map return alone is not success.
4. If the receipt is ambiguous, preserve the journaled intent as pending and stop.
   Reconciliation may inspect the current map/report once later; it must not replay
   the dispatch.
5. If the workflow later receives a collection/return report for the same army and
   resource point, record that correlation as post-dispatch evidence. Do not issue
   `GoingForCollectBack` or `GoingForCollectTurn` as a new mutation unless a separate
   existing caller and authority contract explicitly require it.

## Implementation sequence

1. Freeze the checkpoint and inspect current dirty paths. Obtain the producer's
   typed node, slot, formation, occupancy, control, and receipt facts for one
   unoccupied representative. If any fact is absent, record the exact producer
   dependency and do not weaken the consumer.
2. Resolve the exact observation model additions with the producer owner. Keep
   B-owned fields/assets/OCR in B's files; A may add only A-owned domain/workflow
   contracts after the producer agrees on field names and freshness semantics.
3. Add the typed node/formation/receipt domain models and policy validation, reusing
   `GatheringPolicy` and existing resource quest ids. Reject unsupported resources
   and missing authority before navigation.
4. Implement the reviewed World Map/node/march edges and focused context methods.
   Reuse loading-only readiness, fresh content observation, source revalidation,
   and existing action follow-up semantics.
5. Implement `GatheringWorkflow` and its one journaled dispatch/reconcile path. Do
   not accept a slot decrement or map return without correlated target receipt.
6. Add the typed dispatcher step and strict validator. Migrate one direct/authored
   caller (`task_registry`/API as applicable) in one coherent patch, preserving
   existing parameter semantics and removing the migrated legacy mutation owner.
7. Add focused unit/contract/integration regressions, run the smallest repository
   groups, and inspect journal/artifact output. Keep legacy task tests while their
   caller remains unmigrated; remove or update only tests that assert the migrated
   path's old mutation behavior.
8. Acquire the canonical live lease only after offline acceptance. Run one named,
   unoccupied target with one named formation, capture the correlated dispatch
   receipt, and optionally observe the later collection report without a second
   dispatch. Stop on the first unknown/ambiguous result.
9. Promote the caller only after exact receipt, journal, and no-replay evidence are
   recorded. Report the shared-file ranges and any producer fields still pending.

## Offline validation and acceptance

Use the repository runner and the installed Python 3.13 launcher:

```text
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group unit.app.automation.tasks
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group integration.workflows
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group contract.entrypoints
```

Select the narrowest groups accepted by the runner and report the exact selected
names. The existing combined affected gate at the starting checkpoint passed 2,033
tests, with 2,027 passed and six skipped, run id
`c467de4a5dcb42809cef0545c3aa43e6` at `2026-09-13T23:18:18.415109+00:00`; do not
rerun that unchanged gate because this document was added. For these documentation
edits, run `git diff --check`; no unit or live run is required before implementation.

Add only meaningful typed-contract regressions:

- positive: exact node/resource/owner facts, available slot, selected formation,
  Gather and Dispatch controls, one dispatch, correlated army/node receipt, and
  reviewed World Map-to-Home return;
- no action: zero available slots produces no input;
- negative before input: wrong resource priority, changed/missing node identity,
  unknown occupancy or shield, stale slot, no formation, missing/ambiguous Gather or
  Dispatch control, unsupported resource, absent authority, stale checkpoint, and
  wrong account/castle/capability/date;
- negative after dispatch: World Map return without target/army receipt, stale or
  unrelated receipt, unknown result, or blocked screen leaves a durable pending
  operation and causes no replay;
- duplicate/committed/PREPARED/DISPATCHED intents reconcile through the existing
  dispatcher and produce zero additional Gather/Dispatch inputs;
- collection/return evidence correlates to the same node and player army; it does
  not silently create a second mutation;
- direct API and authored dispatcher callers produce identical typed target,
  formation, authority, journal, receipt, and return behavior;
- existing `test_gathering.py`, visual profiles, and action-follow-up tests retain
  their legacy meanings until the corresponding caller is migrated. Do not add a
  matrix for every resource, formation, or catalog node.

The producer gate is a real both-path observer replay, not a consumer fixture: replay
the saved `0148`, `0150`, and `0215` pixels through both
`ObservationBuilder.build` and `NavigationPerception.build`, with actual RapidOCR
and their normal `ObservationRequest` scopes, and compare screen/layout, guard, row/control, frame and
semantic-field provenance. `0148` must remain ordinary World Map without a receipt;
`0150` and `0215` must either publish the qualified active/report facts or retain an
explicit unsupported result. Do not make a passing consumer test from mocked OCR or a
manually populated `Observation` close this producer gate.

Tests must prove the observable contract: positive input plus fresh receipt, or
negative no-input/pending behavior. Do not test implementation wording or replace
missing producer facts with mocked OCR.

Add the actual parallel-limit regression: active 1/max 2/free 3 permits exactly
one dispatch; active 2/max 2/free 3 permits none; unknown active count cannot claim
the cap was enforced. Verify all four original resource inputs have an honest
capability disposition, including Stone. Positive workflow/caller tests must
confirm Home after retaining the correlated march receipt.

After source changes, run the repository affected gate on the actual candidate:

```powershell
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py affected --base origin/main --explain --json .test-impact/gathering-selection.json --results .test-impact/gathering-results.json
git diff --check
```

Follow a required full fallback once; do not repeat the unchanged historical gate.

## Live proof and stop conditions

After the offline gate and a qualified both-path producer replay, use the canonical
process-scoped lease and configured live role for `mega_old_acc`; exact identity and
active castle must pass preflight. Select an eligible neutral node and existing
formation from fresh published observation under the granted authority, and record
the resource type, exact node/coordinate, occupancy, and formation/army choice in the
execution trace. A previously observed Farm at `K157 X231 Y479` with Buffalo Catapults
is evidence of one possible fixture, not a current target. Do not redo a previously
proven spend merely to qualify recognition; this live run is one consumer proof after
the producer gate.

Run one normal zero-diamond dispatch to an unoccupied node. The user's unlimited
mega_old_acc authorization covers all in-game actions/resources, so do not ask for
   spending permission again. The worker may choose an eligible current node and
   existing formation under that grant; account/castle identity still comes from
    configured preflight and must not be switched. Capture preflight identity, node
source, independent slot and active-march facts, formation facts, fresh controls, durable intent, dispatch input, target-correlated
receipt, journal transition, and reviewed return under a unique
`.local-data/artifacts/core_resume/` run directory.

If an occupied/enemy/shielded node, unavailable slot, stale target, loading state
outside the bounded ready path, UNKNOWN, blocked control, or ambiguous receipt is
seen, stop. Preserve the durable intent, reconcile by observation only, and never
repeat Dispatch. If the one proof obtains a correlated active march, a later
collection report may be observed without another dispatch; it is optional evidence
for the same operation, using the `0150`/`0215` destination and resource association,
not a second spend or a new `GoingForCollectBack`/`GoingForCollectTurn` mutation.

Acceptance is one exact target/formation dispatch receipt, correct journal state, no
duplicate input, and a confirmed reviewed return. A slot decrement or World Map
return alone does not satisfy acceptance.

## Evidence and version caveats

The original A15 requirements and current porting boundaries are in
`reviewed_plans/PNC_CORE_WORKFLOW_PORTING_PLAN.md` and
`instructions/CORE_WORKFLOW_PORTING.md`. The current legacy implementation is
`pnc_automation/app/automation/tasks/gathering_task.py`; its focused tests are
`tests/unit/app/automation/tasks/test_gathering.py`.

The source workflow note is `docs/game-reference/workflows/neutral-gathering.md`.
It records package build 5.0.203/version code 233 and a live footer 5.0.204.235.
Relevant extracted client symbols are:

- `handler/slgwar/handler/slgwarcolhandler.lua:SlgWarColHandler:FightStartClickHandler`
  and `SendRequest`: tile re-read, `playerId`/`unionId` ownership checks, resource
  point id, resource id, and the request boundary;
- `commands/resource/resourcecommand.lua:ResourceSend.RequireGoingForCollect`:
  lord/king/point/heroes/armys/lineup request parameters;
- `commands/resource/resourcecommand.lua:command.GoingForCollect`,
  `GoingForCollectBack`, and `GoingForCollectTurn`: success updates to self army,
  map army, and collection/return state;
- `scenes/worldmap/data/maparmydata.lua:GetSelfArmyLimit` and `GetSelfArmyNum`:
  total troop/army calculations, not available march slots;
- `uis/camp/campdatawin.lua:CampDataWin:UpdatePanel`: camp troop/load display,
  also not a slot source.

The live capture under B's evidence directory
`.local-data/artifacts/capture_gap_exploration/20260913T030954Z/` showed the historical
Farm `K157 X231 Y479`, `1,000` Buffalo Catapults, displayed food capacity `31,279`,
and travel time `47s`. `0148` is ordinary World Map and is not a receipt. `0150`
contains the active Gathering Troop Info row; `0215` contains the later Gathering
Report row. The captured sequence did not publish a usable available-slot field,
active-march count, or fully correlated replacement receipt. Do not copy that dirty
evidence into A source or treat it as current target authorization.

The source package is versioned client evidence, not proof of current server rules
or a successful live action. The latest live build differs. Live observation and
journal evidence are required before caller acceptance.

## Permission, configuration, and technical gates

| Item | State and required action |
| --- | --- |
| Account/resources | Granted: `mega_old_acc`, all in-game actions/resources, unlimited budget. Do not re-request spending approval. |
| Workers/network | Keep workers offline during implementation and offline gates; live execution uses the assigned canonical lease only after those gates. No direct service calls, APK changes, or other worktree edits. |
| Castle/identity | Exact configured active castle and account identity must pass preflight; do not switch them. |
| Resource target | Select an eligible neutral resource type and node identity/coordinate from fresh observation during the bounded proof; record occupancy/owner evidence. |
| Formation | Select an existing observed formation/hero/army selection during the bounded proof and record it; do not invent a cavalry or default lineup. |
| Slots | Producer must publish an independent available-march-slots value and a fresh active-march count for the configured cap. Troop count/load capacity is not a substitute. |
| Mutation authority | Use existing `GATHER_FOOD`, `GATHER_WOOD`, or `GATHER_IRON` authority when applicable; preserve STONE as an original policy input and resolve a narrow standalone capability for it before dispatch. Keep one mutation, zero diamonds, and account/castle/date acknowledgement. |
| Collection | Dispatch receipt is the caller acceptance boundary. A later collection/return report is optional read-only evidence correlated to the same node/army; it never creates a second mutation in this slice. |
| Producer facts | B/another explicit producer owner must publish node, occupancy, controls, formation, slots, and correlated receipt. A owns consumer/navigation/mutation after publication. |

There is no pending user choice for this package. The user's broad live authorization
already covers `mega_old_acc`, any needed in-game action, and unlimited in-game spend;
the remaining slot, Stone capability, and collection-correlation items are technical
contracts resolved by the producer/consumer owners. Do not request a new budget,
target, formation, or collection permission. The live worker still resolves the
current target and formation from fresh configured observation and must stop on an
identity, lease, guard, or receipt failure.

This package does not rebudget the task, run automatic Daily maintenance, merge or
push to main, use desktop mouse/keyboard control, call a game service directly, or
perform real-money actions.

## Independent qualification scope

B's evidence audit leaves independent positive holdouts missing for 19 changed
layouts overall. That inventory remains a B qualification queue; this consumer plan
does not require a blanket all-layout or all-resource replay. Gathering needs only
independent, separately reviewed positives for the exact node, active `Troop Info`,
report, slot/active-march and formation/control surfaces that its contract consumes,
plus wrong-node/occupied/unknown/blocked negatives. The already recorded idle Build
Queue and Economy idle-detail proofs are outside Gathering's acceptance; preserve
them without rerunning them or using them to qualify active/report facts. A correction capture cannot be promoted to an untouched holdout for
the same correction. Keep each feature's holdout and source revision in its own
artifact record.

Technical decisions and evidence gates before implementation or live dispatch:

1. Qualify the typed field and provenance for available march slots, distinct from troop/load capacity, plus the fresh active-march count required to enforce the configured cap.
2. Qualify the strongest observable dispatch/collection correlation on the current build: resource point id and/or player army id when visible, otherwise exact resource/coordinate plus own march/formation facts.
3. Select an existing observed formation and army selection for the representative proof; do not invent a default where the producer is ambiguous.
4. Keep collection/return as an observation-only postcondition for this dispatch port unless an existing authorized caller owns `GoingForCollectBack`/`Turn`.
5. Qualify the reviewed edge from the exact march/report state back through World Map to the shared Home boundary.

## Copyable worker kickoff

```text
Work in C:\Users\lebel\pnc\.local-data\worktrees\workflow-recognition-integration at verified HEAD4f33202, preserving all existing root-owned dirty files. Implement only reviewed_plans/PNC_CORE_REMAINING_03_GATHERING_PLAN.md: a typed bounded GatheringWorkflow for one exact neutral resource dispatch through NavigationCore/WorkflowContext and the existing CoreMutationBoundary/journal. Require published node identity/resource/owner facts, independent available march slots, exact formation/army and controls, fresh source revalidation, one durable intent, one Dispatch input, and the strongest target-correlated receipt (player-army id when exposed, otherwise exact resource/coordinate plus own march/formation facts). Do not accept a slot decrement or World Map return alone. Do not edit B-owned vision/OCR/assets/observation producer files, Resource/Hero/Research/building work, or other worktrees. First verify the producer facts; if node identity, slots, formation, occupancy, receipt, or reviewed return edges are missing, report the exact dependency and stop. Preserve GatheringPolicy and existing FOOD/WOOD/IRON authority; carry STONE as an original input until the shared owner adds its narrow capability. No generic mutation/navigation framework, YOLO/cavalry/search rewrite, or second collection mutation. Reuse loading-only observe_ready and raw post-action/Chat observation. Add focused no-input, stale/unknown/blocked, duplicate/no-replay, journal, receipt-correlation, and direct/authored parity tests. Use the installed Python 3.13 repository runner, never live tools until offline checks pass. For live proof, use only authorized mega_old_acc, exact preflight, canonical lease, one named unoccupied node and formation, zero diamonds, one dispatch at most, captured receipt/journal/return, optional read-only collection report, and stop on UNKNOWN or ambiguity without replay. Report exact changed files, shared-file ranges, test results, artifacts, and unresolved producer facts.
```
