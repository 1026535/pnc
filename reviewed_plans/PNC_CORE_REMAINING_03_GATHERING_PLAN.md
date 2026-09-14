# Remaining gathering workflow, world resource facts, and dispatch

## Objective and ownership

This is the independently executable A03 vertical slice for the remaining gathering
feature. It owns the end-to-end feature contract: world resource and occupancy
observations, current slot and active-march facts, formation and march controls,
target selection, route and return edges, the bounded World Search edge transferred
from A06, typed gathering models, canonical gathering action identity, executor,
authority and receipt/journal integration, direct and Daily-Go adapters, both
production observation paths, focused fixtures and tests, and the live evidence
needed by those contracts.

The execution base is the assignment's pinned checkpoint containing merged
6bc27585fbac1244672cf4a653ea6248955a4aca and this planning revision. Reuse a
suitable existing isolated task worktree and create/use the feature branch there;
do not create a second worktree merely for a preferred path. Preserve resumed
feature work; use a new worktree only if the current checkout is shared or
unsuitable. Follow the [common starting-checkpoint rules](PNC_CORE_WORKFLOW_PORTING_PLAN.md#common-starting-checkpoint-and-evidence-rules).
Do not use the dirty historical 4f33202 snapshot, wait for another
feature worker, or take a whole-file coordinator lock. Shared files may contain
semantic slices for other features; ownership is by the exact methods, task ids,
screen profiles, and data keys in this plan. Physical same-file edits can merge
later.

A03 is independently complete when its own branch implements and validates the
full feature slice. A routine B handback, a prerequisite proof from A05/A06, or a
coordinator-owned mutation design is not part of its definition of done. Consult
the Continue core owner only for a concrete generic conflict; the gathering
implementation and its missing producer facts remain A03 work.

## Saved evidence roots

Historical ignored core_resume artifacts remain read-in-place under
C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration/.local-data/artifacts/.
B diagnostic report references remain read-in-place under
C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation/.local-data/reports/.
Those artifacts are not copied into each isolated feature worktree. New A03
artifacts belong under its own ignored .local-data/artifacts/core_resume/ run
directory. The exact remaining B capture roots are recorded in
reviewed_plans/PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md.

## Definition of done

A03 is complete only when all of the following are reviewable from its branch:

1. A typed gathering workflow selects one exact neutral resource target, validates
   current resource/occupancy/owner facts, formation and march controls, enforces
   available slots and max_parallel_marches, dispatches once, records a
   target-correlated receipt, and returns through a reviewed Home boundary.
2. Resource node, occupancy, coordinate, current slot, active-march, formation,
   control, post-dispatch and optional report facts are independently published
   by both ObservationBuilder.build and NavigationPerception.build with screen or
   layout identity, source frame, provenance and freshness. The feature owns
   producer work for its named screens and fields; manually populated observations
   cannot satisfy this item.
3. Gathering has one feature-owned canonical action identity for direct entry and
   Daily-Go entry. It distinguishes action kind, exact resource target and
   parameters, and durable operation_id. DailyQuestId is optional entry/progress
   metadata only. Retries of the same operation reuse the receipt or pending
   journal state; a separate authorized operation remains possible when policy
   permits it.
4. The existing journal, dispatcher, authorizer and runtime mechanics remain the
   one canonical store/state machine. The gathering slice adds only its typed
   identity, target metadata, capability and receipt semantics to the shared
   envelope/serialization, preserving old Daily receipts and limits. No duplicate
   journal or mutation framework exists.
5. Both direct and authored callers exercise the same executor, operation identity,
   journal, authority, receipt and return behavior. Meaningful offline tests cover
   positive dispatch, no-input guards, pending ambiguity, no replay and a genuinely
   separate operation where policy allows it.
6. The transferred World Search edge has a correct measured control and a separate
   nonspending Home-to-World-to-coordinate-dialog-to-Home proof. If a Gathering
   run traverses this exact edge, its evidence may satisfy the edge proof without a
   duplicate live run. A03 does not add coordinate submission, search policy,
   YOLO/OCR engine changes, or a new target-finding system.
7. After offline acceptance, one bounded live proof on the configured authenticated
   active castle captures the exact target, formation, preflight facts, single
   dispatch input, receipt, journal transition, no-replay behavior and reviewed
   return. An unknown or ambiguous result remains pending and is never replayed.

## Scope and non-goals

The feature covers the existing gathering caller's full bounded dispatch behavior:

- FOOD, WOOD, IRON and STONE remain distinct resource inputs. STONE is never
  relabeled as GOLD. A resource without current authority receives an explicit
  standalone capability disposition and is rejected before input until that
  capability is covered.
- Resource priority from GatheringPolicy remains the selection policy. A target
  must be a fresh exact resource node with coordinate, identity or the approved
  typed equivalent, visible geometry, and occupancy/owner state.
- Current available march slots and active own marches are separate facts.
  GatheringPolicy.max_parallel_marches remains an enforced bound, and one
  invocation dispatches at most one march.
- Existing formation/army selection is observed and correlated. The workflow does
  not invent a cavalry lineup, default heroes, or a hidden army id.
- The existing Gather, march-confirm and Dispatch controls are revalidated from
  fresh content immediately before each input. One durable intent precedes one
  dispatch input.
- The post-dispatch receipt is correlated to the same target and selected army.
  A later Troop Info or Gathering Report observation is read-only evidence for
  that operation; collection-back/turn actions are outside this slice unless an
  existing separately authorized caller already owns them.
- Existing Home-to-World, World-to-Home, node, march-confirm and report routes are
  used or extended with exact source, control and destination predicates.

The transferred A06 edge is also in scope:

- A03 owns the World Map to coordinate dialog transition using the measured
  PNC_WORLD_SEARCH_BUTTON control. PNC_WORLD_COORDINATE_BAR is content/label
  evidence and is not an actionable substitute.
- A03 owns the coordinate-dialog fields and controls needed to identify a fresh
  dialog and the safe close/back return. The standalone proof is
  Home -> World Map -> Search -> fresh coordinate dialog -> safe return -> fresh
  Home, with no coordinate submission and no resource mutation.
- This edge is an existing navigation correction, not new search scope. A03 reuses
  the current navigation and observation machinery and does not create a YOLO,
  coordinate parser, or generic search framework.

Out of scope are generic OCR/guard/readiness/lease mechanics, cavalry or formation
policy beyond observed selection, generic world search or coordinate submission,
Resource/Hero/Daily-claim workflows, broader Research, building workflows, battle
automation, collection mutations, and real-money actions. Generic changes that are
truly necessary may receive one concrete core consultation, but they do not become
a scheduled peer handoff.

## Hard technical contracts and organizational non-dependencies

The current code has concrete gaps that A03 must close inside its feature slice:

| Existing technical fact | A03 contract |
| --- | --- |
| MutationOperation and MutationIntent are shaped around DailyQuestId; DailyRunJournalStore serializes quest_id and the core boundary rejects gathering capability | Add typed gathering action kind, target/parameter metadata, capability and receipt branches under A03 semantic ownership. Reuse the same JournaledMutationDispatcher, DailyRunJournalStore, CoreMutationBoundary and state transitions; preserve legacy Daily deserialization and receipts. |
| DailyQuestId has GATHER_FOOD/WOOD/IRON/GOLD, while ResourceType is FOOD/WOOD/IRON/STONE and Stone is not Daily Gold | DailyQuestId remains optional entry context. Preserve Stone as Stone and give unsupported standalone gathering input an explicit feature capability/policy outcome. Never map Stone to Gold or add a fake Daily row. |
| Observation has optional available_march_slots but no qualified freshness/source contract and no active_marches field | A03 owns typed fields and producer publication for both observers. Troop count, load, army limit, or a stale slot decrement cannot stand in for either fact. |
| Spatial world parsing publishes resource_type and coordinates but not a complete target/occupancy/receipt contract | A03 owns resource-node identity, coordinate, owner/occupancy/shield/hostility, formation, control and target-correlated receipt fields for the named surfaces. |
| Legacy GatheringTask accepts slot decrease or World Map return as success and does not enforce max_parallel_marches | Typed workflow must re-read target and current facts, apply active_marches + 1 <= max_parallel_marches and require a correlated receipt. |
| Core task registry/API/dispatcher have legacy gathering entry points but no typed gathering branch | A03 adds strict TaskId.GATHERING binding and migrates direct/authored callers through one executor without a legacy mutation fallback. |
| reviewed_navigation_edges() has Home/World edges but no complete gathering route and currently maps PNC_WORLD_COORDINATE_BAR as the World Search action | A03 adds exact gathering edges and transfers the Search correction to PNC_WORLD_SEARCH_BUTTON with fresh-dialog and safe-return predicates. |
| Saved capture rows 0150 and 0215 are not covered by the current production catalog | A03 qualifies the active Troop Info and Gathering Report facts through both production paths or records the exact unsupported result. Historical pixels do not authorize a current target. |

These are implementation contracts, not requests to another feature agent. A01's
Institute and Research ownership, A02's building ownership, A05's setup, A06's
castle/roster/More/Settings ownership, and root's integration work do not gate A03.
Use an already authenticated exact active castle for feature proof; setup work is
not acceptance evidence.

## Existing implementation and evidence anchors

| Area | Existing owner | Current behavior and porting consequence |
| --- | --- | --- |
| Legacy workflow | pnc_automation/app/automation/tasks/gathering_task.py:GatheringTask | WORLD_MAP preflight, preferred resource selection, node tap, PNC_GATHER_BUTTON, PNC_MARCH_CONFIRM_BUTTON, and slot-decrement/map-return shortcut. Preserve policy/phase order while replacing the success shortcut. |
| Policy | pnc_automation/app/pnc/domain/policy_models.py:GatheringPolicy and ResourceType | Preferred FOOD/WOOD/IRON and max_parallel_marches=2. Keep all original resource inputs, including Stone, with explicit authority disposition. |
| Observation | pnc_automation/app/pnc/domain/observation.py; pnc_automation/app/pnc/vision/spatial_surfaces.py | DetectedSpatialObject metadata already carries resource_type and coordinates. available_march_slots is optional; active_marches, ownership and receipt contracts are absent or unqualified. |
| Production paths | pnc_automation/app/pnc/vision/observation_builder.py:ObservationBuilder.build; pnc_automation/app/pnc/vision/navigation_perception.py:NavigationPerception.build | Both must publish the same typed gathering facts with frame/layout/provenance/freshness. A consumer fixture alone is insufficient. |
| Observation scopes | pnc_automation/app/pnc/vision/observation_request.py | Reuse world-map, gather-node, march-confirm, post-march-dispatch, report and home follow-up scopes; add only bounded gathering fields within A03 ownership. |
| Navigation/context | pnc_automation/app/automation/engine/navigation_core.py:NavigationCore; pnc_automation/app/automation/engine/core_workflow.py:WorkflowContext | Home/World transition primitives and source revalidation exist; add focused gathering target/formation/receipt operations and exact Search/dialog transition. |
| Mutation | pnc_automation/app/automation/engine/core_daily_mutation.py:CoreMutationBoundary; pnc_automation/app/automation/daily_maintenance/mutation_dispatcher.py:JournaledMutationDispatcher; pnc_automation/app/pnc/persistence/daily_run_journal_store.py:DailyRunJournalStore | Existing PREPARED/DISPATCHED/RECONCILED/COMMITTED lifecycle is the single durable owner. Add gathering semantic fields and capability adapters in A03-owned methods. |
| Binding | pnc_automation/app/automation/engine/core_script_dispatcher.py; pnc_automation/app/entrypoints/task_registry.py; pnc_automation/app/entrypoints/api.py | Core typed dispatch currently rejects TaskId.GATHERING while direct API reaches the legacy task. Add one strict typed branch and converge callers. |
| Tests/evidence | tests/unit/app/automation/tasks/test_gathering.py; tests/integration/vision/test_gathering_march_visual_profiles.py; tests/data/screen_recognition/gather_node.png, march_confirm.png, march_confirm_empty.png | Preserve legacy meanings while callers migrate; add typed producer, receipt, journal, parity and no-replay coverage. |

The saved exploration under
.local-data/artifacts/capture_gap_exploration/20260913T030954Z/ is bounded
evidence only:

| Frame | Reusable fact | Limit |
| --- | --- | --- |
| 0148_ordinary_gather_dispatch.png | Ordinary PNC_WORLD_MAP after the visible sequence | No dispatch receipt, target army, slot count or server acceptance |
| 0150_march_troop_overview.png | Farm level 6 at K157 X231 Y479, troop size 1,000 and remaining timer in Troop Info | No qualified active-march or army id producer |
| 0215_gathering_report_list.png | Gathering Report row for Farm level 6, K157 X231 Y479, displayed 31.2K food | Rounded report display and no proof of the current target or dispatch |

The historical Farm and Buffalo Catapults formation are correlation evidence only. They
must never become a current target or default lineup.

## Exact semantic ownership

A03 owns the following slices even when a file also contains another feature:

| Concern | A03-owned symbols, methods, screens or keys |
| --- | --- |
| Resource identity | ResourceType handling for FOOD/WOOD/IRON/STONE, typed gathering target/action models, target identity and exact resource/coordinate/occupancy fields |
| World producer | World Map/resource node spatial metadata, owner/occupancy/shield/hostility, current slot and active-march facts, formation/army facts, march/report rows, and target-correlated receipt fields in both observer paths |
| Gathering controls | PNC_GATHER_BUTTON, PNC_MARCH_CONFIRM_BUTTON, exact Dispatch control and their screen/layout profiles, bounded OCR regions and fixtures |
| Search edge | reviewed_navigation_edges() slice for PNC_WORLD_MAP -> PNC_WORLD_COORDINATE_DIALOG using PNC_WORLD_SEARCH_BUTTON; fresh dialog fields/controls and safe dialog-to-World/Home return predicates; no coordinate submission |
| Gathering routes | Exact Home/World/node/march-confirm/report source and return predicates; A03's NavigationCore and WorkflowContext methods for target and formation revalidation |
| Workflow | GatheringWorkflow, one-dispatch state/receipt/reconcile behavior, max_parallel_marches enforcement and direct/Daily-Go convergence |
| Mutation | Gathering action kind, exact target/parameters, operation_id, capability/authority and receipt semantics in existing shared envelope/serialization; no new store or state machine |
| Binding | TaskId.GATHERING typed definition, strict core dispatcher validation, registry and direct API/authored adapters |
| Validation | Gathering unit, observer replay, route, contract, journal, caller parity, artifact and bounded live evidence |

A03 may edit shared files at these exact semantic slices. It does not claim the whole
file, and it does not replace generic runtime/lease/readiness mechanics.

## Producer contract

A03 must make the named production facts available through both
ObservationBuilder.build and NavigationPerception.build. Each fact carries the
screen/layout identity, frame reference, capture freshness and source/provenance
needed by a consumer to reject stale or ambiguous state.

### Resource node and occupancy

Publish one stable node identity: a server/resource point id when observable,
otherwise the approved typed equivalent based on exact resource and coordinate.
Publish resource type, coordinate, visible node geometry, owner/player or union
relation, occupancy, shield and hostility state. The final pre-dispatch observation
must re-read the tile and confirm the same identity and safe state. Unknown,
changed, occupied, enemy or shielded state stops before Gather.

The source client evidence gives the boundary in
SlgWarColHandler:FightStartClickHandler: it re-reads MapData:GetTileInfo2(x,y),
updates the map element and checks playerId/unionId before SendRequest. This is
versioned client evidence, so the replacement producer exposes the facts needed to
make the same safe decision without treating the extracted source as server proof.

### Slots and active marches

Publish available_march_slots as an independent typed value with source and
freshness, and publish active_marches as a separate fresh count for the active
castle. The workflow allows one dispatch only if slots are positive and
active_marches + 1 <= max_parallel_marches. Unknown or stale facts stop before
input. GetSelfArmyLimit, GetSelfArmyNum, troop size, load/carry capacity, formation
hero slots and a historical slot decrement are not valid substitutes. Keep the
configured cap explicit even when free slots exceed it.

### Formation, controls and receipt

Publish the selected formation/army identity, exact Gather control on the node panel,
march-confirm state, and exact Dispatch control. A missing or ambiguous formation
is a no-input stop. Do not silently choose cavalry, heroes or a default lineup.

After dispatch, publish the strongest target-correlated receipt available: a player
army id when exposed, or exact resource/coordinate plus own march/formation facts and
target-bound status such as ON_THE_WAY_TO or UNDER_CONTROL. A generic World Map,
changed node count, free-slot change or World Map return alone is not a receipt.
Troop Info and Gathering Report rows retain the resource point and army correlation
when available. A later report is read-only post-dispatch evidence.

The existing fixtures prove parts of node and march presentation but not this full
contract. Replay saved 0148, 0150 and 0215 through both production paths with actual
RapidOCR and normal ObservationRequest scopes. 0148 must remain ordinary World Map
without a receipt. 0150 and 0215 must either publish qualified active/report facts or
return an explicit unsupported result. Do not pass this gate by constructing an
Observation manually or mocking OCR.

## Canonical action and mutation contract

Create one typed GatheringActionIdentity and one GatheringWorkflow using existing
workflow conventions. The identity distinguishes:

1. action kind: gather;
2. exact action target and parameters: resource type (including Stone), stable
   node/resource identity or exact approved resource/coordinate identity,
   occupancy/owner expectation, selected formation/army, and policy-relevant
   parameters such as max_parallel_marches; and
3. durable operation_id: one caller request, reused when the same request retries
   through a direct caller or Daily-Go.

DailyQuestId may be attached as optional entry/progress context after a real Daily
row's Go control launches the action. It does not define the operation, turn Stone
into Daily Gold, authorize a different target, renew a consumed budget, or prevent
every future gather action for the same castle. The direct adapter skips the Daily
row; the Daily-Go adapter revalidates and consumes PNC_QUEST_GO_BUTTON on the real
row, then invokes the same feature executor with the same action identity. A
genuinely separate operation id may proceed when current policy and authority
permit it.

Persist the intent before the final Gather/Dispatch actuator input. Use
CoreMutationBoundary, DailyMutationAuthorizer, JournaledMutationDispatcher and
DailyRunJournalStore as the one runtime/journal owner. Add a typed gathering
capability/receipt adapter and feature metadata to the existing envelope and
serializer under A03's semantic branches while preserving old Daily quest receipts.
The adapter preserves Daily limits when DailyQuestId is present and uses the
feature's standalone capability when the action is direct or is a resource not
represented by an honest Daily quest. No fake Daily row, duplicate store, or second
state machine is allowed.

One invocation performs at most one dispatch. A repeated operation id loads the
existing PREPARED, DISPATCHED, RECONCILED or COMMITTED intent and reconciles by
observation without another Gather or Dispatch input. An unrelated operation id is a
new request and is governed by the current cap, target state and authority. A
World Map return or ambiguous post-action state leaves the durable operation
pending; it does not authorize replay.

## Required behavior

### Read-only preflight and target

1. Validate the resource policy, exact account/castle, one current target request
   and one observed formation. Use fresh Home/World guards and the existing
   resource priority.
2. If available slots are zero, return the existing no-action result before opening
   the node. If slots or active_marches are missing, stale or inconsistent, stop
   before Gather. Active 1/max 2/free 3 permits exactly one dispatch; active 2/max
   2/free 3 permits none.
3. Re-read the selected tile/node and confirm identity, resource, coordinate,
   owner/occupancy, shield and hostility. Changed, missing, enemy, occupied,
   shielded or ambiguous state stops before input.
4. Open the exact node panel, confirm the node identity and Gather control, and use
   the bounded loading-only ready settlement if the source is PNC_LOADING. No
   generic UNKNOWN retry or caller sleep loop is permitted.

### Formation and dispatch

1. Revalidate march-confirm content, independent slots and active-march facts,
   selected formation/army, and exact Dispatch control from fresh content.
2. Create one durable intent containing the target, resource, coordinate, formation,
   authority and operation_id before pressing Dispatch. Press Gather and Dispatch
   only on their exact reviewed controls, once per operation.
3. Reobserve fresh content and accept only a receipt correlated to the same target
   and operation: player army id/status or the approved exact resource/coordinate
   plus own march/formation status. A World Map return alone is pending.
4. If the receipt is ambiguous, preserve the journal intent and stop. Later
   reconciliation may observe the map, Troop Info or report once but must not replay.
5. Correlate any later collection/return report to the same node and army as
   read-only evidence. Do not issue GoingForCollectBack or GoingForCollectTurn in
   this slice.

### World Search edge proof

A03's separate nonspending navigation proof starts from a fresh Home, uses the
reviewed Home-to-World edge, confirms fresh World Map, taps
PNC_WORLD_SEARCH_BUTTON, confirms a fresh PNC_WORLD_COORDINATE_DIALOG, then safely
closes/backs out and confirms fresh World Map and fresh Home. It submits no
coordinate and performs no gathering mutation. PNC_WORLD_COORDINATE_BAR may be
published as dialog content but cannot satisfy the action control. If an accepted
Gathering live run traverses this exact edge, retain its evidence and do not run a
second live proof solely for duplication.

## Implementation sequence

1. Verify the clean base and inspect the current gathering task, policy, observation
   models, producer paths, route graph, journal, callers and focused tests. Record
   missing facts as A03-owned implementation items.
2. Define GatheringActionIdentity, exact target/formation/receipt values, resource
   and capability dispositions, binding them to the existing operation_id and
   canonical no-replay handling. Keep DailyQuestId
   optional metadata and preserve legacy Daily envelope loading.
3. Implement world resource/node, occupancy, slot, active-march, formation, control,
   Troop Info/report and receipt publication in both production observers, with
   bounded OCR profiles/assets/fixtures for the named surfaces. Use actual
   RapidOCR replay before consumer acceptance.
4. Add exact Home/World/node/march-confirm/report route and return predicates.
   Correct the transferred Search edge to PNC_WORLD_SEARCH_BUTTON and add its
   fresh-dialog/safe-return predicates and standalone nonspending proof.
5. Add focused WorkflowContext/NavigationCore methods and GatheringWorkflow.
   Reuse observe_ready, source revalidation, raw post-action/Chat observation and
   existing action-follow-up mechanisms.
6. Integrate gathering action kind, target metadata, operation_id, authority,
   receipt and no-replay semantics into the existing mutation envelope,
   serializer, journal and dispatcher. Do not add another journal/store/runtime.
7. Add strict typed TaskId.GATHERING dispatcher/registry/API/authored adapters.
   Migrate the direct and Daily-Go callers to the same executor and remove the
   migrated legacy mutation owner from those paths.
8. Add focused unit, contract, route, observer replay, journal and caller parity
   regressions. Run the narrowest repository groups accepted by the test runner.
9. After offline acceptance, acquire the canonical process-scoped lease and run one
   bounded live proof using the already authenticated configured active castle, one
   current neutral target, one observed formation, zero diamonds and at most one
   Dispatch input. Capture the target receipt, journal state, no-replay result,
   return and optional read-only report.
10. Promote the direct/Daily-Go binding only after exact receipt, journal and
    parity evidence are reviewable. Report any field that remains explicitly
    unsupported; unsupported is not silently successful.

## Offline validation and acceptance

Documentation changes require git diff --check. No unit or live run is required
for this plan-only change.

The implementation worker should use the narrowest repository runner groups for
the changed symbols, then the affected gate on the actual candidate:

C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group unit.app.automation.tasks
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group integration.workflows
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group contract.entrypoints
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py affected --base origin/main --explain --json .test-impact/gathering-selection.json --results .test-impact/gathering-results.json

Do not run unit or live tests for this plan-only change.

Meaningful regressions must cover:

- positive exact target/resource/owner facts, fresh slots and active-march count,
  observed formation, Gather and Dispatch controls, one input and correlated
  army/node receipt;
- no input for zero slots, active cap reached, unknown/stale slots or active
  count,
  wrong resource, changed/missing/occupied/enemy/shielded node, absent formation,
  missing/ambiguous control, unsupported capability, stale checkpoint or wrong
  account/castle/date;
- World Map return without target/army receipt, unrelated/stale receipt, UNKNOWN
  or blocked post-action leaves a durable pending intent and performs no replay;
- PREPARED retains the canonical retry-permitted disposition with fresh
  validation; DISPATCHED, RECONCILED and COMMITTED duplicate retries use the
  existing no-replay handling and produce no additional Gather/Dispatch input;
- direct and Daily-Go callers converge on the same action kind, exact target,
  operation_id, authority, journal, receipt and return; a separate authorized
  operation id remains possible when policy permits;
- the explicit Daily adapter revalidates the actual resource quest row and
  PNC_QUEST_GO_BUTTON, proves the expected world/gathering arrival, and invokes
  the same executor; wrong/stale Go or arrival stops before mutation, and a fresh
  Daily survey separately establishes quest progress;
- Stone remains Stone with an honest standalone capability disposition, and no
  GATHER_GOLD relabeling is accepted;
- collection/report observation correlates to the same node/army and does not
  create a second mutation;
- both production observers publish every consumed field with source/layout/frame
  provenance and freshness;
- Search uses PNC_WORLD_SEARCH_BUTTON, opens a fresh coordinate dialog, safely
  returns to Home, submits no coordinate, and does not depend on a coordinate-bar
  label being actionable.

The producer gate replays 0148, 0150 and 0215 through both
ObservationBuilder.build and NavigationPerception.build with actual RapidOCR and
normal scopes. 0148 remains ordinary World Map without a receipt; 0150/0215 either
publish qualified active/report facts or retain explicit unsupported results.
Mocked OCR and manually populated observations cannot close the gate.

## Live proof and stop conditions

Use the canonical process-scoped lease and the configured live role for
mega_old_acc only after offline acceptance. The existing user authorization covers
all needed in-game actions and unlimited in-game spend; do not ask for a new budget
question. Resolve the exact active castle, current neutral target, resource type,
occupancy and existing formation from fresh configured observation. The historical
Farm K157 X231 Y479 and Buffalo Catapults are not a current target or default.

Run one normal zero-diamond dispatch at most. Record preflight identity, node
source and target, independent slot and active-march facts, selected formation,
fresh controls, durable operation identity, intent, actuator inputs,
target-correlated receipt, journal transition, no-replay retry result and reviewed
Home return under a unique .local-data/artifacts/core_resume/ run directory. A
later Troop Info or Gathering Report observation is optional read-only evidence for
the same operation.

If a node is occupied, enemy or shielded, a slot/cap fact is unavailable, a source
is loading beyond bounded readiness, a control is blocked, a receipt is stale or
ambiguous, or identity/lease checks fail, stop. Preserve the intent and reconcile
by observation only. Never repeat Gather or Dispatch to obtain evidence. A slot
decrement or World Map return alone does not satisfy acceptance.

The separate Search edge proof is nonspending and uses the same lease and active
castle. Capture Home, World Map, PNC_WORLD_SEARCH_BUTTON, fresh coordinate dialog,
safe return and fresh Home. If the gathering proof already traverses this exact
edge, reference that artifact instead of duplicating it.

## Evidence and version caveats

The source workflow note is docs/game-reference/workflows/neutral-gathering.md.
It records package build 5.0.203/version code 233 and live footer 5.0.204.235.
Relevant extracted client symbols are versioned evidence:

- handler/slgwar/handler/slgwarcolhandler.lua:SlgWarColHandler:FightStartClickHandler
  and SendRequest re-read the tile, check playerId/unionId, and send the resource
  point/resource request;
- commands/resource/resourcecommand.lua:ResourceSend.RequireGoingForCollect
  describes lord/king/point/heroes/armys/lineup request inputs;
- commands/resource/resourcecommand.lua:GoingForCollect,
  GoingForCollectBack and GoingForCollectTurn update self-army/map-army and
  collection/return state;
- scenes/worldmap/data/maparmydata.lua:GetSelfArmyLimit and GetSelfArmyNum are
  total army/troop calculations, not available slots;
- uis/camp/campdatawin.lua:CampDataWin:UpdatePanel is troop/load display, not a
  slot source.

The captured evidence directory
.local-data/artifacts/capture_gap_exploration/20260913T030954Z/ and fixtures are
versioned observations, not current server proof. The latest live build differs.
Current production observation, exact active identity and durable journal evidence
govern acceptance.

This plan does not change automatic Daily maintenance, scheduling, Resource/Hero/
Research/building ownership, generic OCR/guard/runtime/lease mechanics, direct game
services, APKs, real-money actions, or other worktrees. Its branch is complete when
the feature definition of done and all required evidence are reviewable
independently of peer completion or final merge.

## Copyable worker kickoff

Reuse a suitable existing isolated task worktree and feature branch; create
another worktree only if the current checkout is shared or unsuitable. Preserve
ongoing task work. For a fresh start use the assignment's pinned checkpoint
containing merged 6bc27585fbac1244672cf4a653ea6248955a4aca and this plan revision.
Implement only the A03 gathering slice:
world resource/node and occupancy facts, independent available slots and active
march count, observed formation and exact Gather/march-confirm/Dispatch controls,
typed GatheringWorkflow, canonical gathering action identity and operation_id,
existing journal/dispatcher/authority/receipt integration, direct and Daily-Go
adapters, both production observers, exact reviewed routes and tests. Keep FOOD,
WOOD, IRON and STONE distinct; do not map Stone to Daily Gold. Persist one intent
before one Dispatch input, require a target-correlated receipt and never replay an
ambiguous operation.

Own the transferred World Search edge: use PNC_WORLD_SEARCH_BUTTON to open a fresh
coordinate dialog and prove safe Home return without coordinate submission. A
Gathering run may reuse that exact proof. Do not add YOLO, coordinate submission,
generic OCR/runtime/navigation/mutation framework, Resource/Hero/Research/building
work or collection mutations. Do not wait for B or feature 05/06 setup; resolve
missing facts in this named slice or record the exact unsupported contract.

Use the repository runner after implementation and no live action before offline
acceptance. For the one bounded live proof use only the already authenticated
mega_old_acc active castle, canonical lease, one current neutral target, one
observed formation, zero diamonds and at most one dispatch. Capture receipt,
journal, no-replay and return evidence; stop on ambiguity. Report exact files,
semantic shared-file ranges, tests, artifacts and residual unsupported facts.
