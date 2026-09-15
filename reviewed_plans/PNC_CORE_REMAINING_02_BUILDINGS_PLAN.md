# Remaining building routes, construction, and upgrade workflows

## Objective and ownership

This is the independently executable A02 vertical slice for the finite A11/A12/A13
building remainder. It owns the nineteen unqualified original building routes, the
existing normal construction caller, and the existing building-upgrade policy. The
worker owns the feature domain models, building-screen recognition facts, both
production observation paths, reviewed building edges, typed workflows, canonical
building action identities, authorization/receipt/journal integration, direct and
Daily-Go callers, feature fixtures, tests, and any live proof needed by those
contracts.

The execution base is the assignment's pinned checkpoint containing merged
6bc27585fbac1244672cf4a653ea6248955a4aca and this planning revision. Reuse a
suitable existing isolated task worktree and create/use the feature branch there;
do not create a second worktree merely for a preferred path. Preserve resumed
feature work; use a new worktree only if the current checkout is shared or
unsuitable. Follow the [common starting-checkpoint rules](PNC_CORE_WORKFLOW_PORTING_PLAN.md#common-starting-checkpoint-and-evidence-rules).
Do not reset, clean, branch from an
older checkpoint, or wait for a dirty historical 4f33202 snapshot. Shared files may
contain A02-owned methods and keys beside other feature slices. Ownership is by the
exact symbols below; a coordinator lock or routine B handback is not part of this
plan.

A02 has no dependency on another remaining feature being implemented. A01 owns
Institute-specific label/focus qualification and the Development Research path;
A02 owns Institute upgrade detail panels and all building action facts. Both use
the existing typed Home-object output contract. A02 may correct the canonical
general Home-building collector when an owned route needs it, including baseline
Institute acquisition, while preserving that output contract. It does not wait
for A01, add a second Institute parser, or change Research-specific focus behavior.

## Saved evidence roots

Historical ignored core_resume artifacts remain read-in-place under
C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration/.local-data/artifacts/.
B diagnostic report references remain read-in-place under
C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation/.local-data/reports/.
Those artifacts are not copied into each isolated feature worktree. New A02
artifacts belong under its own ignored .local-data/artifacts/core_resume/ run
directory. The exact remaining B capture roots are recorded in
reviewed_plans/PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md.

## Definition of done

A02 is complete only when all of the following are reviewable from its branch:

1. The six existing core endpoints remain green, and the nineteen finite original
   A11 rows each have an exact current identity, independently qualified source and
   destination evidence, a reviewed return edge, and a consumer open/return test.
   A row with a missing current producer identity is reported as an exact blocked
   row; a generic building-details fallback does not count.
2. Normal construction ports the current BuildingConstructionPolicy through the
   typed core, exact empty-slot/source-family validation, one durable intent, one
   ordinary Build input, a target-specific start receipt, and a reviewed Home
   return. It remains an explicit caller and is excluded from automatic Daily
   maintenance.
3. Upgrade ports the current priority, level, prerequisite (FAIL and QUEUE),
   queue/full, warning, normal payment, optional speedup, premium-material, and
   post-start Help semantics. Each enabled branch has typed controls, target
   correlation, a journal entry, a receipt, and a no-replay regression. A normal
   happy path alone does not close the policy remainder.
4. Construction and upgrade each have one feature-owned canonical action identity
   used by direct entry and any applicable real Daily-Go entry (currently upgrade;
   no construction quest is invented). The identity carries
   action kind, exact target/parameters, and one durable operation_id. DailyQuestId
   is optional entry/progress context only; it does not become the underlying action
   type. A direct retry and a Daily-Go retry of the same operation reuse the receipt
   and budget, while a genuinely separate authorized operation remains possible
   when policy permits. No duplicate journal, store, authorizer, dispatcher, or
   state machine exists.
5. Every consumed building field is produced by both ObservationBuilder.build and
   NavigationPerception.build with independent screen/layout, frame, provenance,
   and freshness evidence. Feature tests use the real bounded OCR requests and
   saved images where a producer fact matters.
6. Focused offline checks pass, and the smallest necessary leased live proof records
   the exact target, controls, receipt, journal transition, no-replay behavior, and
   Home return. An unknown or ambiguous result remains pending and is never retried
   by tapping the same mutation.

## Scope and non-goals

The finite route inventory is the original twenty-five-target A11 smoke inventory.
Six are preserve-only modeled endpoints: Castle, Institute, Warehouse, Goddess
Statue, Hero Hall, and Campaign. The nineteen route deliverables are Wall, Trap
Workshop, Watchtower, Sauroi Lair, Arena, Alliance Hall, Blacksmith, Market, Tower
of Trial, Bank, Sanctum, Ranged Barracks, Infantry Barracks, Cavalry Barracks,
Siege Factory, Hall of War, Sacred Tree, Pit, and Dragondom Conquest.

The six preserved endpoint identities and return edges are:

| Home object | Primary screen | Reviewed return |
| --- | --- | --- |
| CASTLE | PNC_CASTLE | PNC_BACK_BUTTON_TOP_LEFT -> PNC_HOME_CITY |
| INSTITUTE | PNC_INSTITUTE | PNC_BACK_BUTTON_TOP_LEFT -> PNC_HOME_CITY |
| WAREHOUSE | PNC_WAREHOUSE | PNC_BACK_BUTTON_TOP_LEFT -> PNC_HOME_CITY |
| GODDESS_STATUE | PNC_GODDESS_STATUE | PNC_BACK_BUTTON_TOP_LEFT -> PNC_HOME_CITY |
| HERO_HALL | PNC_HERO_HALL | PNC_BACK_BUTTON_TOP_LEFT -> PNC_HOME_CITY |
| CAMPAIGN | PNC_CAMPAIGN_MAP | PNC_CAMPAIGN_HOME_PORTAL -> PNC_HOME_CITY |

Arena must establish the canonical PNC_VERSUS_CENTER mapping and Versus-to-Home
return. Bank and Dragondom Conquest need an actual current endpoint identity before
a catalog mapping is added. The old generic PNC_BUILDING_DETAILS fallback, a menu
option, a classifier header, a generic Back selector, or a historical task fixture
cannot close an A11 row. Farm is an action representative; it is not a replacement
for any of the nineteen original endpoint rows.

This plan includes normal construction and the full legacy upgrade policy. It does
not add Build Now as a new construction mode, enable automatic Daily scheduling,
or invent a construction Daily row. Explicit feature Daily-Go adapters are included.
It does not
expand cavalry/search/YOLO behavior, automate battles, or take ownership of generic
OCR, generic guard/readiness, Resource, Hero, or broader Research behavior. A03 owns
the transferred world-coordinate Search edge; A02 uses existing Home-city
navigation and does not wait for that unrelated proof.

## Exact file and symbol ownership

A02 owns the following semantic slices, including producer acceptance inside those
slices. The shared file name does not transfer the entire file to A02.

| Concern | A02 owns | Existing canonical symbols to preserve |
| --- | --- | --- |
| Building identity and source | Building definitions, endpoint mapping gaps, construction-source facts, instance/slot correlation, and building metadata keys needed here | HomeCityObjectId, HomeCityObjectDefinition, BuildingConstructionSource, _PRIMARY_SCREEN_BY_HOME_CITY_OBJECT_ID, _OWNING_HOME_CITY_OBJECT_ID_BY_SCREEN, _CONSTRUCTION_SOURCE_BY_HOME_CITY_OBJECT_ID, home_city_object_id_from_metadata, require_building_construction_source |
| Building producer | Building Home objects except A01's Institute label/acquisition slice; detail, construction menu, requirement, queue, level, warning, speedup, premium, Help and start-receipt facts | DetectedSpatialObject.metadata, ObservationAdditions, Observation, ObservationBuilder.build, NavigationPerception.build, build_home_city_spatial_surface |
| Building controls | Building-specific UiElementId profiles, screen/layout evidence, bounded OCR regions, and feature fixtures | PNC_BUILDING_CONSTRUCTION_*, PNC_BUILDING_UPGRADE_*, PNC_BUILDING_REQUIREMENT_*, PNC_BUILD_SPEEDUP_*, and building primary-screen controls |
| Building routes | A02's NavigationEdge entries and exact route/return predicates in the canonical graph | NavigationCore.open_building, open_visible_building, _require_reviewed_building_route, reviewed_navigation_edges, WorkflowContext.open_building |
| Construction | Typed target/source/receipt, canonical construct action identity, executor/authority integration, and direct/Daily-Go adapters | BuildingConstructionTask, BuildingConstructionPolicy, building_workflow_support |
| Upgrade | Typed target/level/precondition/queue/receipt, canonical upgrade action identity, all existing policy branches, and direct/Daily-Go adapters | BuildingUpgradeTask, BuildingUpgradePolicy, _QueuedBuildingPrerequisite, _complete_started_upgrade_at_home_city, building_workflow_support |
| Core binding | Exact BUILDING_CONSTRUCT and BUILDING_UPGRADE parser/dispatcher/registry/API branches | TaskId, CoreWorkflowTaskDefinition, CoreScriptDispatcher, validate_core_script_step, AutomationApi.building_construct, AutomationApi.building_upgrade |
| Journal envelope | Building action kind and exact target metadata in the existing shared envelope/serialization; bind them to the existing operation_id and no-replay handling, preserving old DailyQuestId receipts | MutationOperation, MutationIntent, DailyTaskCheckpoint, DailyRunJournalStore, JournaledMutationDispatcher, CoreMutationBoundary |
| Feature validation | Building unit, workflow, entrypoint, visual replay, contract, artifact and live evidence files | Existing building task and navigation tests; add meaningful target/receipt/no-replay regressions |

The existing journal and dispatcher remain the one canonical runtime mechanism. A02
owns only the building semantic fields and action identities in their shared
envelope. DailyQuestId names an optional Daily entry/progress row, and existing
Daily receipts remain readable. A02 must not create a second store or use a Daily
quest id as a fake construction identity.

## Current implementation anchors

| Area | Source | Behavior to retain |
| --- | --- | --- |
| Construction | pnc_automation/app/automation/tasks/building_construction_task.py:BuildingConstructionTask | Exact policy target, fixed/large/small source family, empty-slot search, menu option, ordinary Build, timer/queue/target verification |
| Upgrade | pnc_automation/app/automation/tasks/building_upgrade_task.py:BuildingUpgradeTask | Priority selection, target focus, requirement handling, queue/full decisions, warning, normal Upgrade, optional speedup, level/timer verification and Help follow-up |
| Shared building facts | pnc_automation/app/automation/tasks/building_workflow_support.py | Timer, active build, queue row, requirement, Help and speedup meanings |
| Catalog and policy | pnc_automation/app/pnc/domain/building_catalog.py; pnc_automation/app/pnc/domain/policy_models.py | Exact Home object ids, screen ownership, construction source families, BuildingConstructionPolicy, BuildingUpgradePolicy defaults and priority loader |
| Typed read-only entry | pnc_automation/app/automation/open_building.py; NavigationCore.open_building | Fresh observed Home object, exact destination and reviewed return; no coordinate fallback |
| Shared binding | core_workflow.py, core_script_dispatcher.py, task_registry.py, entrypoints/api.py | Typed workflow context/runner and direct/authored lifecycle; A02 owns only its exact building branches |
| Mutation | CoreMutationBoundary, JournaledMutationDispatcher, DailyRunJournalStore | Durable PREPARED/DISPATCHED/RECONCILED/COMMITTED lifecycle, exact account/castle/date authority and no replay |

The current catalog has primary mappings for most remaining screens but the reviewed
navigation graph must contain an exact return edge for every accepted screen. The
graph currently proves only the preserved building returns; a catalog mapping alone
is not route support. A02 adds its own endpoint and return evidence in the canonical
graph. A missing or ambiguous producer field stops before input and is an A02-owned
evidence gap when it belongs to a building screen or control.

## Producer contract and evidence

A02 qualifies the building producer itself. It does not request a B handback or fill
the gap with consumer OCR, coordinates, guessed ids, or a manually populated
Observation. Every positive source, action, receipt, and return image is replayed
through both production paths with actual RapidOCR and the normal ObservationRequest
scope. Compare screen, layout, guard, control, row, frame, semantic field, and
source provenance.

The Home source contract publishes one exact home_city_object_id for each visible
building or legal empty slot, valid bounds and action point, source frame, fresh
capture time, relationship, and corresponding canonical primary screen. A
repeatable building also needs an instance/slot/geometry correlation strong enough to
distinguish two visible instances. A visible label, level number, generic detail
screen, or stale object does not authorize input. Source and post-action frames must
agree on target identity.

For route rows, evidence contains source identity, post-open identity, exact
consumed control or read-only endpoint, measured return action, and fresh Home. For
each of the nineteen additions, keep its capture group, source revision,
action/destination pair, and return artifact in the A02 evidence record. The saved
alliance_remaining_hall reference can seed Hall row recognition, but A02 still
proves Home acquisition, exact Hall object route, current return, and an independent
capture group.

For construction, publish:

- exact empty position/slot identity and ConstructionSlotFamily (FIXED, LARGE, or SMALL);
- menu screen, target option, normal Build control, and distinct premium/instant Build Now control;
- unavailable versus selected option, requirement state, and payable cost facts when shown; and
- a target/position-correlated start receipt: active timer, queue row, or equivalent exact state. A changed screen or global queue count is insufficient.

For upgrade, publish current level, intended next level, strongest target
correlation, precondition and requirement text, normal Upgrade, castle warning and
Confirm controls, queue state, speedup and premium-material controls, and the fresh
post-action target receipt. Queue distinguishes idle/available from full, gift,
third-queue, and unknown states. A started timer/queue is a start receipt;
completion requires a fresh exact target-level increase after refresh. An empty queue
or generic success panel is not proof.

The existing evidence subsets remain useful but bounded:

| Evidence | Reusable fact | A02 still proves |
| --- | --- | --- |
| building_detail_farm, building_construction_farm, level 0/1, upgrade 7/8 | Farm detail, construction, and level shapes | Exact slot/instance, current controls, source family, and new target-correlated Start receipt |
| Castle/Institute/Warehouse/Goddess level captures | Per-field level reads | Target identity and action/receipt correlation; preserve Castle native RGB3x behavior |
| institute_upgrade_detail unmet prerequisite Go | Distinct unmet row and Go control | Actual prerequisite identity, FAIL/QUEUE result, reviewed Go route, and receipt; a satisfied Requirement heading is not an unmet row |
| build_queue_centered active/idle rows | Title/timer/state association and Close | New target-associated queue baseline and receipt; a replayed reference row is not a new upgrade proof |
| 20260913T234651Z_build_queue_holdout.png | Independent idle centered Queue and measured Close | Nothing about active queue/start/level; reuse without rerunning |
| alliance_remaining_hall | Hall destination rows | A02 Home-to-Hall object route, return edge, and independent layout qualification |

The earlier saved Institute source replay had clear Home but zero building objects
through the production observers. Reproduce any missing building source predicate
through the canonical Home collector and repair the general building acquisition
needed by A02's routes, preserving the existing typed Institute output. A01's
Research-specific focus and qualification remain separate. A02 owns all Institute
upgrade-detail, construction, queue, requirement and receipt facts; no second Home
parser or A01 completion gate is permitted.

## Typed design

Create two explicit typed operations using existing workflow conventions:

- BuildingConstructionWorkflow: one exact Home object, one validated empty slot,
  one source family/menu/option, one ordinary Build, and one target-specific start
  receipt;
- BuildingUpgradeWorkflow: one exact Home object instance and one level transition,
  including explicit prerequisite, queue, warning, speedup, premium, and Help
  decisions where policy enables them.

Each operation declares entry PNC_HOME_CITY, reviewed action states, and exit
PNC_HOME_CITY after the receipt. Each declares RESOURCE_CHANGING. It uses the one
existing CoreMutationBoundary, JournaledMutationDispatcher, and DailyRunJournalStore
through the building-owned adapter. It accepts typed target and policy data; it
never accepts an arbitrary screen, coordinate, or button name.

The building action identity must distinguish three separate concepts:

1. action kind: construct or upgrade;
2. exact action target and parameters: HomeCityObjectId plus empty slot/source
   family for construction, or object/instance/current-level/next-level and branch
   parameters for upgrade; and
3. durable operation_id: one caller request, reused by direct or Daily-Go retries.

DailyQuestId may be attached as entry/progress context after the existing Daily
row's Go control is pressed. It must not determine operation identity, authorize an
unrelated target, renew a consumed budget, or turn construction into a Daily quest.
The direct adapter skips the Daily row; the Daily-Go adapter revalidates and
consumes PNC_QUEST_GO_BUTTON on the real row, then calls the same building executor
with the same typed action identity and target metadata. The current real Daily row
covers upgrade; construction remains direct unless a real Daily row exists, and no
fake row is added. Existing Daily upgrade receipts remain loadable and their limits
remain enforced by the adapter.

Persist the intent before any actuator call and reconcile fresh observations. A
repeated operation id reuses its persisted receipt or pending disposition. A
different operation id for a genuinely separate authorized action is allowed only
after the shared policy/budget contract permits it. A02 must not hide speedup,
premium-material purchase, prerequisite Start, or Help as an unjournaled sub-action.

WorkflowContext and NavigationCore receive only focused building methods. Reuse
open_building, fresh content observation, bounded loading-only observe_ready, and
existing post-action/Chat raw observation. Every target and control is revalidated
from a fresh frame immediately before input. There is no generic UNKNOWN retry or
caller-local sleep loop.

## Required behavior

### Endpoint open and return

For each inventory row:

1. Resolve OpenBuildingPolicy to exact HomeCityObjectId, primary screen, and owning-screen map. Arena, Bank, and Dragondom remain blocked until current identities are canonical and independently recognized.
2. From fresh guarded Home, require exactly one matching object with valid bounds, source frame, safe point, and current identity. Missing Home publication, stale capture, wrong target, or ambiguity stops before input.
3. Tap the observed target through NavigationCore.open_building or open_visible_building; do not use atlas coordinates or generic detail fallback.
4. Confirm independently observed destination and consumed content, then use the measured reviewed return action and confirm fresh Home. Reusing a Back selector is valid only when this screen's destination is recorded.
5. Test a wrong destination and lost/changed object before input. A modeled catalog row or menu option without these observations remains blocked.

### Normal construction

1. Validate one constructable catalog object, one exact empty slot, its fixed/large/small source family, menu, target option, and normal Build control.
2. Ensure Home and capture a fresh source. If loading, settle once within the shared bounded ready budget and retain the first capture.
3. Open the exact construction menu and revalidate target option, normal Build, requirement, and cost state. Build Now is a distinct premium control and never a fallback.
4. Persist the building construct operation intent, then press ordinary Build exactly once.
5. Reobserve fresh content and accept only target/position-specific active timer, queue row, or equivalent receipt. A stale, blocked, unknown, or unrelated result remains pending and is reconciled later without replay.
6. Return through the reviewed edge only after the receipt is known. Do not wait for completion or infer completion from an empty queue.

### Upgrade

1. Validate exact catalog object, strongest observed instance correlation, current level, and requested next level. A level label without target ownership is insufficient; an invisible client numeric id must not be fabricated.
2. Revalidate requirements. FAIL stops on an unmet requirement. QUEUE may follow only the one observed Go/prerequisite route with reviewed destination and return. Keep the requested target separate from the actual prerequisite.
3. Revalidate queue. Idle/available is dispatchable; full, gift, third-queue, unknown, or other blocked states stop without purchase or an alternate queue path.
4. Revalidate normal Upgrade and any castle warning/Confirm. Normal payment proceeds only from published facts and explicit policy.
5. If speedups or premium materials are explicitly enabled, require typed control, item/quantity/cost, availability, acknowledgement, and exact target revalidation. Otherwise reject before navigation; no diamond cap is increased.
6. Persist the building upgrade operation intent and press normal Upgrade once. Reconcile a fresh receipt tied to the same instance or strongest approved object/slot/geometry/level correlation. A started timer/queue is a start receipt.
7. Completion is proven only by a fresh exact target-level increase after refresh. Empty queue, unrelated level, disappeared timer, or generic success is pending clarification.
8. Return through a reviewed edge after a known receipt. An ambiguous result is reconciled from the journal and never replayed.

The full policy branches remain explicit:

| Branch | Required behavior and proof |
| --- | --- |
| FAIL / QUEUE | Distinguish satisfied Requirement from unmet prerequisite. In QUEUE, identify the actual prerequisite and record its one Start, route and receipt for the root target. Unsupported Go or changed prerequisite stops. |
| Optional speedup | Consume only qualified item, quantity, Use control, availability and cost; correlate resulting state to the same target and prove level if completion is claimed. |
| Premium materials | Give each purchase a separate durable intent and receipt. Revalidate target and cost after purchase; unknown purchase outcome stops before another purchase or Upgrade. |
| Post-start Help | After a valid upgrade receipt, use the observed Help control through one constrained follow-up. Missing Help does not erase the upgrade receipt or rerun Upgrade. |

## Implementation and validation sequence

1. Verify clean base 6bc27585fbac1244672cf4a653ea6248955a4aca and inspect the
   existing building source, tests, catalog, route graph, and shared journal.
2. Freeze A02's exact ownership for screen profiles, building metadata keys,
   target/receipt fields, BUILDING_CONSTRUCT and BUILDING_UPGRADE branches, and
   action identity metadata. Missing building facts are A02 work inside this plan.
3. Add or correct the building-specific producer fields, bounded OCR regions,
   profiles, and both observer publication paths. Replay saved Farm, queue,
   Institute-detail, Hall, and each new route capture through real production
   observation before making a consumer test pass.
4. Extend exact catalog/owning-screen mappings and reviewed building edges for each
   independently qualified row. Keep Arena, Bank, and Dragondom explicitly blocked
   until current endpoint identity exists.
5. Add typed construction and upgrade domain values, canonical action identities,
   focused context/navigation methods, and the two workflows. Reuse existing
   support predicates and remove any migrated legacy mutation owner from caller paths.
6. Integrate building action kind, exact target metadata, operation dedup, and
   feature capability/receipt semantics into the existing mutation envelope and
   serialization without replacing old Daily receipts. Add strict direct and
   Daily-Go adapters using the same executor and journal.
7. Add exact dispatcher steps, parameter validation, registry definitions, direct
   API/session wrappers, and authored caller adapters. Preserve current priority,
   source-family, prerequisite, speedup, premium, and acknowledgement parameters.
8. Add focused unit, integration, contract, and both-observer visual replay tests.
   Verify journal/artifact output and run the narrowest accepted repository groups.
   Do not add a matrix for every building, flag, or equivalent Back edge.
9. After offline acceptance, acquire the canonical process-scoped lease for the
   configured mega_old_acc live role. Reobserve exact active castle, target,
   controls, and policy from current state. Run at most one normal construction and
   one normal upgrade representative, plus one smallest live proof for any optional
   mutation boundary whose current behavior is not already qualified.
10. Capture preflight identity, source/profile, control, durable action identity and
    operation_id, intent, input, target-specific receipt, journal transitions,
    direct/Daily-Go no-replay behavior, and reviewed Home return. Stop on UNKNOWN,
    stale, blocked, wrong-target, or ambiguous state; preserve the intent for
    observation-only reconciliation.

## Offline acceptance

Use the installed Python 3.13 launcher and repository runner:

C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group unit.app.automation.tasks
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group integration.workflows
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group contract.entrypoints

Select the narrowest groups accepted by the runner and report exact names. After
source changes, run:

& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py affected --base origin/main --explain --json .test-impact/buildings-selection.json --results .test-impact/buildings-results.json
git diff --check

Follow a required full fallback once. A documentation-only edit needs git diff
--check only. Keep existing legacy tests while callers remain unmigrated; update
only assertions whose behavior intentionally moves to the typed path.

Meaningful regressions must cover:

- each accepted endpoint's exact Home object, destination, current control/content, measured return, and fresh Home;
- construction exact family/menu/option, normal Build, target-specific Start receipt, and no input for wrong slot/family/target, missing option, blocked menu, premium-only control, stale source, or unknown receipt;
- upgrade exact level/instance, available queue, normal Upgrade, warning, target receipt, and no input for unmet FAIL, unsupported/changed QUEUE, full/gift/third-queue, wrong level, ambiguous target, or missing control;
- explicit speedup, premium-material, and Help policy/acknowledgement/receipt paths;
- loading-only settlement with first capture retained and raw ordinary post-action and Chat observation;
- wrong account/castle/capability/date and stale checkpoint rejection; PREPARED retains the existing retry-permitted disposition with fresh validation, while DISPATCHED/RECONCILED/COMMITTED operations cannot issue another Build/Upgrade input;
- direct and Daily-Go parity for the same action identity, target, operation_id, authority, journal, receipt, and return, plus a genuinely separate authorized operation when policy permits;
- the explicit Daily adapter revalidates the actual quest row and PNC_QUEST_GO_BUTTON, proves arrival at the expected building state, and invokes the same executor; wrong/stale Go or arrival stops before mutation, and a fresh Daily survey separately establishes quest progress; and
- both production observers publishing every consumed building fact with source frame/layout/provenance. Mocked OCR or manually populated observations cannot close this producer gate.

## Live proof and stop conditions

The existing user authorization covers mega_old_acc, all needed in-game actions, and
unlimited in-game resource spending. Do not request another spending question. The
live worker still uses the configured exact account/castle, canonical lease, current
observed target/slot/level, explicit normal zero-diamond policy, and shared mutation
authority. Castle switching is not part of this proof.

Store redacted artifacts under a unique .local-data/artifacts/core_resume/ run
directory. For each attempted operation record source frame, target identity,
control, pre-action state, typed action identity, durable operation_id, intent,
input, post-action state, receipt, journal transition, no-replay result, and
reviewed Home return. A started queue/timer is enough for normal Start acceptance;
completion and optional branches retain their separate acceptance cells above.

If the source is loading, use only the existing bounded ready callback. If the result
is UNKNOWN, stale, blocked, wrong-target, or ambiguous, stop, preserve the durable
intent, reconcile by observation only, and never repeat the mutation. A successful
live proof is one exact target-specific receipt, correct journal state, no duplicate
input, and confirmed Home return. Report each remaining blocked route or policy
branch with its exact missing producer predicate; blocked is not complete.

## Evidence and version caveats

The route inventory is recorded in .local-data/artifacts/core_resume/a11_endpoint_inventory.json
and originated from the historical twenty-five-target smoke in
tests/test_live_home_city_map_smoke.py. The source workflow note is
docs/game-reference/workflows/building-upgrade.md; its extracted client evidence is
build 5.0.203/version code 233 with later live footer 5.0.204.235. Relevant symbols
include buildingupgradewin.lua:OnUpgradeHandler, CheckResIsEnough,
buildingcommand.lua:CreateBuilding, DoneFastCreate, UpgradeBuilding,
buildingdata.lua:GetIdelCoolStatusType, CheckBuildPreconditionIsPass,
GetEmptyPosForBuild, and GetBuildDataForId.

Those sources are versioned client evidence, not proof of current server acceptance,
payment, completed level, or a live receipt. Base resource tables do not establish
the current payable cost after modifiers. Current production observation and durable
journal evidence govern acceptance.

This package does not change automatic Daily maintenance, scheduling, real-money
actions, other accounts, generic OCR/guard/runtime mechanics, or unrelated feature
ownership. Its branch is reviewable and independently complete once the feature
definition of done above is satisfied.

## Implementation report — 2026-09-14

Status: **implemented and offline-validated; partially live-accepted; incomplete on
explicit evidence/producer blockers.** The historical `mega_old_acc` live wording
above was superseded for this run by the prompt's exact allocation
`serious_stuff / bs-main / live_testing`. The freshly observed active castle was
`K226 / free cookies / level 17`; no account or castle switch was performed.

### Repository and source-control record

- Feature repository root:
  `C:/Users/lebel/pnc/.local-data/worktrees/buildings_package_02`
- Feature branch: `codex/a02-buildings`
- Code and plan base: `a4ac5d280ce04f63251c616e0b9f7bcb380b2be8`
- Merged code ancestor: `6bc27585fbac1244672cf4a653ea6248955a4aca`
- Both requested ancestry checks passed locally. No remote refs were updated and no
  peer worktree changes were imported.

### Implemented slice

- Added typed construction/upgrade targets, action kind, exact observable
  slot/instance/level identity, durable `operation_id`, optional Upgrade-Building
  Daily context, and target-bound receipts.
- Extended the canonical mutation envelope, journal serialization, authorizer,
  dispatcher, workflow runner, API/session/CLI/authored dispatch, and direct versus
  Daily-Go boundary without creating a construction quest or a second journal.
- Direct and Daily-Go callers share operation identity and replay budget. Automatic
  Daily scheduling remains disabled; Upgrade Building remains claim-only in the
  generic Daily catalog.
- Construction uses the exact observed empty-slot spatial query, canonical source
  family/menu/option, ordinary Build control, and target/slot-correlated receipt.
- Upgrade re-acquires the target on the dispatch frame, requires a typed owning
  screen and exact current→next level, checks requirement/queue state, journals
  warning/confirmation and post-start Help follow-ups, and accepts only a
  target-correlated timer/queue/level receipt. Priority selection skips only
  safely proven ineligible candidates before creating an intent; explicit QUEUE,
  speedup, and premium branches remain attached to the selected target and fail
  closed when their required facts are unavailable. Premium-only construction and
  mutation states stop before input.
- Optional speedup and premium-material branches now fail closed before input when
  their required item/quantity/availability/cost producer is absent. QUEUE parses
  the visible requirement and rejects unsupported or untyped prerequisite routes.
  These three enabled branches are safe but not complete; see blockers below.
- Added bounded Home OCR publication used by both observers and guarded visual
  profiles/fixtures for Hall of War, Sacred Tree, Arena/Versus Center, and the newly
  observed Blacksmith endpoint. Added the Arena primary mapping. Pit is retained as
  a read-only mine-war endpoint and is not considered upgradeable.
- Added the scoped client-source note
  `docs/game-reference/workflows/building-endpoints.md` from build
  `5.0.203 / 233`, including `BuildTableData:_OpenBuildWinImpl` mappings.

### Route acceptance and blockers

The six preserve-only endpoints remained green. Of the nineteen A02 rows:

- Live accepted with independently replayed typed destination and measured Home
  return: **Arena, Hall of War, Sacred Tree**.
- APK and one exact live source→destination observation: **Blacksmith**
  (`CONSTRUCTIONID -> EQUIP_ENTER_WIN`). Its second group and Back return were
  blocked by the generic VIP daily-reset foreground described below, so it is not
  counted as fully accepted.
- Current Home source observed but no safe endpoint tap: **Pit**. The live producer
  published `upgradeable=false`; its point was outside the reviewed safe band.
  Client source maps `MINE_HOLE` to `MineWarData:sendOpenMineMainWin()`.
- Current bounded Home acquisition did not find a safe exact object:
  **Wall, Trap Workshop, Watchtower, Alliance Hall, Bank**. Market was not retargeted
  after the preceding untyped Blacksmith frame because the fresh-source guard
  detected a different screen.
- Not live attempted after the foreground blocker: **Sauroi Lair, Market, Tower of
  Trial, Sanctum, Ranged Barracks, Infantry Barracks, Cavalry Barracks, Siege
  Factory, Dragondom Conquest**.
- Bank and Dragondom remain intentionally unpromoted despite client candidates
  `TREASURE_CAVE_WIN` and `DRAGON_CAVE_MAIN_WIN`; the plan requires current typed
  destination and return evidence.

Relevant ignored evidence groups:

- `.local-data/artifacts/core_resume/20260914T231500Z` — Hall of War
- `.local-data/artifacts/core_resume/20260914T255500Z` — Sacred Tree
- `.local-data/artifacts/core_resume/20260914T263000Z` — Pit safe-band stop
- `.local-data/artifacts/core_resume/20260914T271500Z` — Wall source miss
- `.local-data/artifacts/core_resume/20260914T274500Z` and
  `20260914T283000Z` — Arena destination and independent return evidence
- `.local-data/artifacts/core_resume/20260914T292000Z` — Bank source miss
- `.local-data/artifacts/core_resume/20260914T301500Z` — five-route group and
  Blacksmith destination
- `.local-data/artifacts/core_resume/20260914T311500Z` — independent run stopped
  at the unqualified VIP daily-reset foreground before route acquisition

### Exact remaining blockers

1. The VIP daily-reset modal in the `20260914T311500Z` group was classified
   `UNKNOWN`. Existing OCR can describe it, but `ObservationBuilder` deliberately
   requires an independent visual modal identity before publishing Close. No input
   was sent. A focused consultation with `Continue non-YOLO recognition` confirmed
   this is a generic producer gap and that A02 must not add a coordinate/Back
   bypass or import unreviewed dirty peer work.
2. Optional speedup lacks a production fact containing the exact inventory item,
   quantity, availability and cost. The available tests describe screen controls
   only; no independently qualified consumable receipt exists.
3. Premium-material purchase lacks an exact purchase selector/cost/availability
   producer and independently qualified purchase receipt. Diamond authority alone
   does not establish those facts.
4. QUEUE lacks a qualified actual-prerequisite identity/Go destination/return and a
   separate prerequisite Start receipt tied to the requested root target.
5. `tests/data/local_fixture_artifacts.json` is absent in this checkout; no path was
   invented. Saved historical evidence was read in place from the roots named by
   this plan.

No live construction or upgrade mutation was attempted because the required branch
producers and final live route preconditions were not all offline-qualified. No
durable intent was created and no in-game resources were spent.

### Runtime review revision — 2026-09-14

- The typed retry path now resolves the stored target and reconciles its receipt
  before any Daily-Go, Home, queue, or detail precondition is reacquired. A
  prepared intent is returned as an actionable retry state; it is not replayed.
- Direct building authority uses the direct acknowledgement mutation/diamond
  limits. Only an invocation carrying the existing Upgrade Building Daily
  capability uses the Daily limits. The durable building identity ignores that
  optional progress context while retaining the stored receipt and budget.
- Upgrade now requires a fresh production Home build-control proof before the
  target is opened. The detail observer's unproduced queue-state metadata is no
  longer used as queue availability proof; existing requirement, warning,
  payment, speedup, premium-material, and Help branches remain fail-closed.
- CLI `build`/`construct --operation-id` is rejected before runtime because the
  CLI has no invocation acknowledgement/boundary composition. Legacy commands
  without `--operation-id` retain their existing path; authored/API callers with
  an explicit boundary remain supported.
- The duplicate Sacred Tree validation fixture was removed at this revision.
  The later follow-up below found and promoted a genuinely distinct saved capture;
  that later evidence supersedes this revision's temporary downgrade.

Focused offline revision validation: `py tools/run_tests.py group
contract.workflows` — **78 passed**; `py tools/run_tests.py group
contract.entrypoints` — **60 passed**. Live validation remains intentionally
blocked/skipped under the parent task's offline-only delegation.

### Verification record

- `py -m unittest tests.contract.workflows.test_building_mutation_identity
  tests.integration.persistence.test_daily_maintenance_config
  tests.integration.persistence.test_daily_run_journal
  tests.unit.app.pnc.navigation.test_navigation_core
  tests.integration.vision.test_building_route_captured_observers
  tests.integration.vision.test_home_city_captured_observers` — **105 passed**.
- `py tools/run_tests.py group contract.entrypoints` — **59 passed**.
- `py tools/run_tests.py group contract.workflows` — **74 passed** on the
  final implementation.
- `py tools/run_tests.py group integration.workflows` — **200 passed**.
- `py tools/run_tests.py group integration.persistence` — **133 passed,
  1 skipped**.
- `py tools/run_tests.py group unit` — **1,072 passed** after restoring the
  no-automatic-Daily contract.
- `py -m unittest tests.integration.vision.test_building_route_captured_observers
  tests.unit.app.pnc.vision.test_visual_screen_metadata
  tests.unit.app.automation.daily_maintenance.test_daily_canaries
  tests.unit.app.automation.daily_maintenance.test_daily_quest_catalog
  tests.integration.persistence.test_daily_maintenance_config` — **36 passed**.
- `py -m compileall -q pnc_automation ...` — **passed**.
- `git diff --check` — **passed** (line-ending conversion warnings only).
- `py tools/run_tests.py affected --base origin/main --explain --json
  .test-impact/buildings-selection.json --results
  .test-impact/buildings-results.json` — selected the mandated full fallback and
  **passed 2,154 tests, 7 skipped**.
- After the full gate, the final acknowledgement invariant and priority-fallback
  regression coverage passed **62 tests**, followed by the final building-focused
  suite at **96 tests**.

The final source-control review and local feature commit are recorded in the task
handoff.

### Follow-up runtime review — 2026-09-14

- Follow-up base: `e40d96df72a7317da2f0cc1557f9889eff6c6ecc` on `codex/a02-buildings`; offline-only, no BlueStacks, ADB, live config, or live artifacts were accessed.
- Queue availability now requires a production-observed first-slot `queue_state=idle` fact through the shared enrichment path used by both `ObservationBuilder` and `NavigationPerception`; active and unknown rows fail closed.
- Building PREPARED intents now rehydrate the stored typed target, reacquire and revalidate its exact construction slot or Home building detail, durably transition to DISPATCHED once, dispatch once, and reconcile. Generic mutation callers retain their existing non-replay PREPARED disposition.
- The alternate Sacred Tree source/return capture at `.local-data/artifacts/core_resume/20260914T250000Z` was inspected. The selected return frame is visually Sacred Tree, has decoded SHA-256 `af8f39db49447ebd19f8f3dea2e9a1288debbbd0d5d3a5cab70ab26c5c70f158`, and is promoted as `sacred_tree_validation_20260914.png` under capture group `2026-09-14/a02_buildings/20260914T250000Z/sacred_tree_return`. Its provenance reports `unknown_screen`, and all source/return frames in that saved run are byte-identical; it is therefore one independent saved capture group, not multiple independent frames. The observer gate now validates both reference and return-group fixtures through both production observers.
- Focused offline results: `contract.workflows` 80 passed; `unit.app.automation.daily_maintenance` 119 passed; `integration.vision` 435 passed, 6 skipped. `git diff --check` passed. Live acceptance remains blocked by the explicitly offline-only delegation.

### Final review and bounded live recheck — 2026-09-15

- Reviewed implementation commits: `446112019e0931ddb9bc2a539ce221a08a300c69`,
  `e40d96df72a7317da2f0cc1557f9889eff6c6ecc`, and
  `fd0f3f630acd0e54afada5ec6e330f318c04711b`.
- Exact runtime resolution from `C:/Users/lebel/pnc/config/accounts.yaml` passed for
  `serious_stuff / bs-main / serious_stuff / live_testing`. One canonical
  process-scoped reservation was used and the pre-existing instance was preserved.
- The non-spending core preflight stopped on its first screenshot with
  `UNKNOWN / guard_unresolved`. OCR independently described the VIP daily-reset
  text and Close label, but no visual profile proved the modal identity, so no
  recovery input was sent and the active castle could not be freshly reverified.
  Evidence is retained under the feature-owned ignored group
  `.local-data/artifacts/core_resume/20260915T040847Z`.
- No building route input, construction, upgrade, speedup, prerequisite, Help,
  premium-material purchase, diamond purchase, durable intent, or receipt was
  attempted. Actual resource and diamond spend: **0**. The live lease and connected
  runtime were released after the failed preflight.
- Independent focused recheck:
  `py -m unittest tests.contract.workflows.test_building_mutation_identity
  tests.unit.app.automation.daily_maintenance.test_daily_mutation_dispatcher
  tests.integration.vision.test_build_queue_observation
  tests.integration.vision.test_building_route_captured_observers
  tests.integration.vision.test_building_captured_flows` — **38 passed**.
- Required affected gate:
  `py tools/run_tests.py affected --base origin/main --explain --json
  .test-impact/buildings-final-selection.json --results
  .test-impact/buildings-final-results.json` selected the full portable fallback:
  **2,158 passed, 7 skipped, 1 failed** out of 2,166. The sole failure was the
  unrelated concurrent mail-archive test
  `test_same_fingerprint_lookup_and_create_are_serialized`; its isolated rerun
  immediately passed **1/1**. No building, journal, dispatcher, entrypoint, visual,
  navigation, or architecture test failed.

Live acceptance remains incomplete until the generic VIP modal obtains an
independently qualified visual identity in the integration line. The package does
not import the uncommitted generic recognition worktree and does not bypass that
guard. Once integrated, rerun the same preflight first, then resume the unaccepted
route inventory and at most one exact normal construction and one exact normal
upgrade under target-bound operation ids and displayed finite per-operation caps.

### Route-resumption revision — 2026-09-15

- The feature worktree was safely fast-forwarded to the already-integrated A02
  merge `cfdeb1e5161c7fe495ccd260656d0a837a0a1b23`; ongoing feature work remains
  on `codex/a02-buildings` in the same repository root recorded above.
- Commit `91960a9d629d583f5d5b1e3c1feb21e912a76df9` adds one bounded pan derived
  from an exactly observed out-of-band Home target. The pan consumes the existing
  gesture budget, requires fresh unblocked Home reacquisition, and permits only
  one tap on the reacquired exact target. It adds no atlas coordinate or predicted
  target and preserves stale, unknown, popup, missing, and ambiguous fail-closed
  behavior.
- Focused validation passed 5/5 new regressions and 250/250 tests in
  `unit.app.pnc.navigation`; an independent direct run of
  `tests.unit.app.pnc.navigation.test_navigation_core` passed 70/70. The required
  affected command selected its mandated 305-module fallback because the public
  navigation declaration changed and passed **2,169 tests, 7 skipped** at commit
  `91960a9d629d583f5d5b1e3c1feb21e912a76df9`.
- Two new independent `serious_stuff` preflight groups,
  `.local-data/artifacts/core_resume/20260915T045517Z` and
  `.local-data/artifacts/core_resume/20260915T045551Z`, stopped before input on
  the same daily-reset VIP modal. Their decoded frame SHA-256 values are
  `f7f5a38fe46f52d3cbdc61be9d35737cdecd4085ab69e2c0362a746e700883c9`
  and `e14bf9fdeffbf51bd43852a3cf35de27aa92234a43b8da85bfcb03ebc6a0e291`.
  The production guard OCR read VIP, the daily-login text, points, and Close, but
  correctly retained `UNKNOWN / guard_unresolved` because the generic modal lacks
  independent visual identity. No input or spend occurred.
- That reset popup is not a building route, is not evidence from `mega_old_acc`,
  and is not owned by A02. Its canonical reset-close task has the evidence and is
  handling the generic recognition/close boundary. A02 will neither add a popup
  profile nor bypass the screen-first guard; live route capture resumes on
  `serious_stuff / bs-main` after that task leaves a recognized stable screen.
- APK or extracted-client evidence is not being used for this resumed route
  acceptance. Pit remains a read-only `MINE_HOLE` mapping row and is deliberately
  not treated as upgradeable.
