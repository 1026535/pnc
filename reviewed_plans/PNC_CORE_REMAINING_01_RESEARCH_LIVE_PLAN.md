# Remaining 01 — Development Research live acceptance

Reconciled September 14, 2026. Owner: A workflow/runtime acceptance. This handoff is
limited to the one already implemented Development Research caller and its one
supported live canary proof. It does not reopen broader Research categories,
change the mutation bridge, or absorb B's producer work.

## Finish line

Accept the existing `TaskId.RESEARCH` Development path only after one fresh,
authorized run on the selected `mega_old_acc` castle proves all of the following
through the production caller and the replacement core:

1. before connection, the caller validates the exact `mega_old_acc` account,
   configured journal root and authorized `npc_2` castle scope; after
   connection and immediately before route/mutation, a fresh active-castle
   preflight re-proves K157 / `NPC 2` / level 22;
2. the configured Development-only Research policy is accepted by the existing
   `CoreMutationBoundary` and `DailyMutationAuthorizer`;
3. the Research Queue → Institute → Development tree route uses current-frame
   published evidence, with one complete unambiguous Development row and one
   observed normal blue `Start` control;
4. the journal records the single `research-001` intent before input, the Start
   action is dispatched at most once, and two canonical stable fresh
   active-detail frames, both retaining the exact active Research identity and
   lacking a normal Start control, prove the result;
5. the typed result reports `ResearchDisposition.STARTED` and
   `DailyTargetOutcomeStatus.SUCCESS`, with exactly one Start, zero diamond
   spend, and the canonical checkpoint/receipt artifacts; and
6. `CoreWorkflowRunner` confirms final Home and the caller releases its one
   connected runtime while retaining any execution or cleanup error.

The current source already implements the caller. The outstanding acceptance
failure is Home spatial publication after Research Queue Go, including the
missing Institute object. The September 14 replay of published B `10740eb`
recognizes Home but publishes zero building objects on the saved source; this
also loses the four other objects in A's earlier replay. A future worker must qualify that producer handback before
attempting the Start proof. A successful lifecycle result with
`PENDING_CLARIFICATION`, a manual Institute tap, or a clean process exit is not
Research acceptance.

## Canonical owners and the current blocked boundary

Use these existing A owners in the dirty integration candidate at HEAD `4f33202`.
They locate the remaining producer-consumption and live acceptance work; the
caller implementation itself is not a task to repeat:

| Owner | Verified contract to preserve |
| --- | --- |
| `pnc_automation/app/automation/research.py:prepare_research_workflow`, `ResearchWorkflow.execute` | Accepts only `ResearchCategory.DEVELOPMENT`; opens `HomeCityObjectId.INSTITUTE`, navigates the Development tree, requires one complete observed row, opens it through `NavigationCore.open_research_node`, then delegates one Start to the mutation boundary. `ResearchResult` carries the durable checkpoint and typed disposition. |
| `pnc_automation/app/automation/engine/core_daily_mutation.py:CoreMutationBoundary.require_caller`, `authorize`, `verify_active_castle`, `start_research` | Binds account, configured journal root, exact target, `UPGRADE_RESEARCH` policy, one mutation, zero diamonds, durable checkpoint and `research-001` journal dispatch/reconciliation. An existing Research intent consumes the one budget; uncertain dispatch is retained and never replayed. |
| `pnc_automation/app/automation/engine/core_workflow.py:CoreWorkflowRunner.run`, `WorkflowContext.start_research` | Rejects a resource-changing workflow without the exact scope, preflights the active castle before navigation, gives the workflow only reviewed navigation/content operations, and confirms the Home exit. |
| `pnc_automation/app/automation/engine/navigation_core.py:NavigationCore.open_building`, `open_visible_building`, `open_research_node` | The Institute route first uses Research Queue Go to focus the city, then requires one current Home spatial object with `home_city_object_id == institute` and safe observed geometry. The Development node tap is a fresh, exact title/category row action; premium Research Now is not a normal Start. |
| `pnc_automation/app/automation/engine/script_runner.py:_validate_core_script_dependencies`, `_build_core_step_executor` and `pnc_automation/app/automation/engine/core_script_dispatcher.py:validate_core_script_step` | Authored Research receives the caller's boundary before connection, checks the configured journal root and account/castle, forces `DAILY_CANARY`, borrows the caller's connected graph, and has no legacy fallback. |
| `pnc_automation/app/entrypoints/app.py:ApplicationRunner.run_research`, `pnc_automation/app/entrypoints/api.py:AutomationApi.research`, `AutomationSession.research`, module-level `research` | Direct and authored callers return `CoreWorkflowResult[ResearchResult]`, use `priority=["development"]`, hold the account reservation for the direct call, and apply the existing cleanup policy. Generic `run_task(TaskId.RESEARCH)` without a scope remains rejected before device work. |

The current caller tests and core tests establish the offline boundary:

- `tests/unit/app/entrypoints/test_research_callers.py` covers wrong journal
  root, typed result/cleanup/`DAILY_CANARY` forwarding, broad/default policy
  rejection, and explicit non-canary authored role rejection before runtime
  construction.
- `tests/integration/script_runner/test_core_research_dispatch.py` covers
  missing scope and unsupported category before the runtime factory, wrong
  requested castle and stale journal date before the factory, durable receipt
  retention through the borrowed dispatcher, wrong active identity before node
  navigation, and no action on the no-visible-node path.
- `tests/integration/workflows/test_research_core_workflow.py` covers the typed
  workflow result, Development row selection, ambiguity/incomplete-row guards,
  and unsupported policy rejection.
- `tests/contract/workflows/test_core_research_mutation.py` covers the existing
  exact authorizer, normal-versus-active detail guard, durable dispatcher and
  no-replay semantics. It is root-owned; do not edit it in this slice.

The current A validation ledger records the latest caller gate as **2,027 passed,
six skipped (2,033 tests)**, with focused caller groups also passing. Do not
rerun that unchanged full gate merely because this handoff is being written.
The prior live attempt is the material evidence for the remaining producer gap:

- `.local-data/artifacts/core_resume/research_caller_20260913T232029Z/summary.json`
  records `AutomationApi.research`, exact K157 / `NPC 2` / level 22 preflight,
  zero Research Starts, zero diamond spend, unchanged journal, final Home, and
  the Institute publication blocker.
- `.../stop.json` records `RuntimeError: Building is absent or ambiguous; no
  further gesture or building tap was sent`, with only the already committed
  `hero-hall-recruit-001` receipt in the checkpoint.
- `.../research_replay_20260913T232029Z_observation_diagnostic.json` replays
  the source frame through both `ObservationBuilder.build` and
  `NavigationPerception.build`. Both publish a clear Home surface with Castle,
  Warehouse, Goddess Statue and Trap Workshop, zero Institute candidates and no
  authoritative focus-arrow target. The A resolver correctly returns `None`.
- `.local-data/artifacts/core_resume/research_caller_20260913T232029Z/prepared.json`
  records the exact one-Start/zero-diamond policy, K157 / `NPC 2` / level 22,
  and the canonical journal root without connecting.

That failure is a B-owned producer dependency, not permission to add a guessed
coordinate, a workflow-local parser, or a legacy tap. The authoritative queued
handoff is
`reviewed_plans/PNC_B_FOLLOWUP_RECOGNITION_HANDOFF.md`: B owns the Institute
identity/action evidence and broader Research category producers; A owns the
category policy, route, mutation journal and callers. Read B's documentation
and published checkpoint only. Do not read/import or modify unfinished code in
`C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation`.

Apply the shared source-freeze, ownership and evidence rules in the [six-package
checkpoint](PNC_CORE_WORKFLOW_PORTING_PLAN.md#common-starting-checkpoint-and-evidence-rules)
before handing this slice to a future live worker.

### Producer acceptance on the saved Institute source

The latest offline replay is
`C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation/.local-data/reports/institute_remaining_audit_20260914/results.json`,
with its adjacent `replay.py`. It used the original 900×1600 PNG ending
`0026_core_7_building_source.png`, SHA-256
`0fd0bcbc89d540847cae7fc51ff45572f917ec178f8f17e5b605f0b3f250462d`.
Actual RapidOCR and both unchanged production observers returned
`PNC_HOME_CITY` / `CLEAR` / `home_city`, zero spatial objects, and four bounded
backend reads per path. This was a diagnostic execution, not a passing acceptance
test or a live run. A's earlier four-object replay remains historical evidence;
do not describe it as the result on `10740eb`.

B's `vision/ocr_region_plan.py` currently owns only Home queue-status and bottom
navigation content regions. `pnc_observation_enricher._build_home_city_additions`
passes the content lines to `spatial_surfaces.build_home_city_spatial_surface`;
none of those semantic crops contains the pictured building labels. The broad
popup guard crop is not an alternative content source. Thus a new Institute
string rule alone cannot repair this production path. Keep the correction inside
the existing Research handoff's Home producer work and preserve supported Home
objects for package 02; do not create a competing navigation or OCR owner.

The B handback must make the following concrete before A opens Institute:

1. Independently establish Home/layout and foreground ownership, then establish
   the visible building or its semantically bounded nameplate/level region using
   the existing visual/spatial owners. Publish one exact `INSTITUTE` identity,
   source `FrameRef`, current bounds and an observed safe action point. The
   pointer overlays the building in this source; it is corroboration only.
   Do not turn the pointer tip or saved camera coordinates into a tap authority.
2. Keep neighboring Castle, Warehouse, Goddess Statue and Trap Workshop facts
   where the current frame actually supports them. Admit no whole-screen OCR,
   arbitrary tiles, guard-result harvesting or additional diagnostic OCR. If
   a nameplate is occluded/unreadable, keep that missing fact explicit; a known
   Home screen does not make every building present or actionable.
3. Add a durable captured regression through `ObservationBuilder.build` and
   `NavigationPerception.build`, using real RapidOCR for this motivating case.
   Retain focused parser tests but do not substitute injected building words for
   production crop coverage. Assert exact Institute count, frame identity,
   current measured bounds/point, and the consumer's exact object query. Verify
   missing/ambiguous Institute, occluded label or missing independent identity,
   and foreground-blocked controls all stop without a building tap.
4. Reuse the raw source for reproduction; after fixing against it, it is reference
   evidence. Qualify a separate capture group for the changed Home acquisition
   behavior before calling it independently validated. The smallest new live
   evidence is read-only Home/Queue focus/Institute open/return on the configured
   target, only where an existing source/transition cannot prove that boundary.
   Do not start Research merely to collect a Home nameplate holdout.
5. A replays the actual saved source and published objects through the canonical
   `NavigationCore` resolver, then tests fresh reacquisition immediately before
   the Institute action. Expected screen, target supplied by the workflow, or a
   cached earlier object must not supply missing current evidence. Proceed to
   the one Start proof only after the route and destination gates pass.

## Remaining work and dependency order

Preserve the implemented Development caller. A production changes are conditional
on a concrete mismatch with the completed producer handback, not a new caller
rewrite. The dependency order for the eventual validation worker is:

1. **B producer handback.** B's preceding recognition batch is published at
   `10740ebb9b8d9d43fc24f970b904796ca41bd082`; it does not close this gate.
   The separate follow-up Research slice must publish one exact Institute object with
   valid current-frame identity, bounds and safe action point through both
   production observation paths, or report the precise remaining producer
   limitation. The handback must include the producer commit/checkpoint, focused
   tests, the preceding both-observer replay, source/build provenance and negative behavior for missing/ambiguous
   Institute content. A focus arrow, expected camera position, OCR word alone,
   or one builder-only result is insufficient.
2. **A source freeze.** Before any caller or live worker starts, record the
   current A worktree as `HEAD 4f33202` plus its dirty caller/core/docs state.
   Inspect `git status --short --ignored` and the diff of the existing Research
   caller files. Do not reset, stash, clean, cherry-pick, or start from bare
   `4f33202`; doing so can lose the uncommitted caller plumbing. Root owns the
   shared plan/index and integration sequencing.
3. **A review of B's publication.** Confirm that the existing A consumer can
   consume the published Institute object without changes to the observation
   model. If a published contract genuinely requires an A adaptation, edit only
   A-owned automation/entrypoint files and add a focused consumer regression.
   Never compensate for absent identity with a coordinate, OCR string, fuzzy
   building match, or a second observer. Re-run the focused groups below after
   that adaptation. Broader Economy/Military/Fortification tree rows and their
   busy/active/completion variants remain in the three-item B follow-up handoff;
   they are not prerequisites for this Development-only caller, and this caller's
   success must not close them. Captured tree files 0028/0034/0039 are still
   unsupported at `10740eb`, while a separately captured Economy idle detail
   already has a bounded proof worth reusing.
4. **One bounded live proof.** Use the existing prepared helper or an ignored
   timestamped equivalent, with the exact target and scope recorded before
   connection. Perform one production `AutomationApi.research` call. Do not
   repeat it after a journal intent exists.
5. **Promotion decision.** Promote only when the exact Research result and
   journal receipt pass. Otherwise preserve the stop artifacts and report the
   first unproved predicate. Do not promote from a no-visible-node pending
   result, a manually completed action, or a partial route.

## Target, authority and decisions

The user has authorized live testing on `mega_old_acc` and all needed in-game
actions with unlimited resource spending. That grants the account/action
envelope; the current acceptance proof intentionally uses one normal Start and
zero diamonds through the existing `UPGRADE_RESEARCH` policy, and
`accounts[].live_roles` remains the runtime authority. The authorized Research
target is K157 / `NPC 2` / level 22 (`npc_2`). This proof does not select or
restore a castle; alternate selection and round-trip handling belong to package
06.

The tracked target catalog contains the following exact `mega_old_acc` aliases:

| Alias | Exact configured identity |
| --- | --- |
| `main` | K314 / `K314a4452b3900` / level 1 |
| `npc_2` | K157 / `NPC 2` / level 22 |

The earlier blocked Research proof used `npc_2`, and the user authorization
already covers that exact target for the resumed proof. Require it to be active
after connection and before Research navigation. If another castle is active,
stop without switching and wait for package 06's explicit alternate-castle
handling or a separately recorded target decision; do not silently select a
castle inside Research.

| Decision or permission | State | Worker action |
| --- | --- | --- |
| `mega_old_acc` live account and in-game actions | Granted by the user | Resolve the configured instance/role/target through the canonical runtime; never hard-code an ADB port or device. |
| Research action/spend envelope | Broad in-game action and spending authorization granted by the user; current supported proof policy is one normal Start and zero diamonds | Use one normal owned Start, zero diamonds; do not use premium Research Now or add a second intent. |
| `DAILY_CANARY` authority | Required by the authored/direct Research callers and must be present in configured account roles | Use `DAILY_CANARY`; an absent configured role is a configuration/runtime stop, not a caller fallback. |
| Exact Research castle alias | Authorized as `npc_2` | Record K157 / `NPC 2` / level 22 before connection and require it still active after connection; do not switch inside Research. |
| Return/round-trip policy | Not part of Research acceptance; package 06 owns alternate selection and restoration | Do not add a second castle switch to this proof. |
| Other accounts, unconfigured castles, local config edits, credentials/session secrets, direct game-service calls or external sign-in | Not authorized by this request | Do not access or change them. |
| Merge, push, destructive Git/filesystem operations | Not part of this worker handoff | Return a reviewable diff/report to root; root owns integration. |

## Offline checkpoint before live work

Run the narrowest affected checks after B's handback and any A consumer change,
using the installed Python 3.13 executable:

```powershell
$py = 'C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe'
& $py tools/run_tests.py group integration.workflows
# If caller/dispatcher code changes, add the corresponding focused group:
& $py tools/run_tests.py group unit.app.entrypoints
& $py tools/run_tests.py group integration.script_runner
```

The existing Research-specific modules should be visible in those groups; the
mutation module belongs to `contract.workflows`, which is required if its shared
boundary changes. Do not run every listed group for an unchanged caller:
`tests/unit/app/entrypoints/test_research_callers.py`,
`tests/integration/script_runner/test_core_research_dispatch.py`,
`tests/integration/workflows/test_research_core_workflow.py`, and the root-owned
Research mutation contract. If an A-owned navigation/consumer adaptation is
made, also run:

```powershell
& $py tools/run_tests.py group unit.app.automation.engine
& $py tools/run_tests.py group unit.app.pnc.navigation
```

Record command output in a unique ignored `.local-data` result file. Use
`tools/run_tests.py affected --base origin/main --explain` only after an actual
source change or B integration; use the full fallback if the runner selects it.
The prior 2,027-pass/6-skip result remains the baseline and is not new evidence
for a changed candidate.

## Bounded live proof

Use the canonical process-scoped account reservation and one connected runtime.
The outer phase owns cleanup and should use the existing `keep_warm` policy so a
pre-existing instance is preserved. The prepared helper
`.local-data/artifacts/core_resume/research_caller_live.py` demonstrates the
correct construction; if the selected alias differs, create a new ignored
timestamped helper or parameterize the ignored copy. Do not edit local
`accounts.yaml`, `daily_maintenance.yaml`, `castle_targets.yaml`, credentials or
tracked production code to make the proof pass.

Before connection, save a sanitized `prepared.json` containing only account ID,
selected exact castle, one-Start/zero-diamond policy, journal root, game reset
ID and existing intent IDs. `CoreMutationBoundary.require_caller` and
`load_checkpoint` must succeed. If the checkpoint already contains a Research
intent for this reset/account/castle, stop: inspect its durable state and do not
replay it. The committed `hero-hall-recruit-001` receipt may remain; it is an
unrelated retained receipt and must not be replaced.

After acquiring the lease:

1. Call `ensure_game_ready()` and capture a fresh stable, unblocked Home frame.
   If the app remains loading/unknown, shows a blocking popup without the
   canonical safe recovery, or cannot produce responsive captures within its
   configured bound, save the trace and stop.
2. Run the exact nonselecting active-castle preflight. The observed Manage
   Characters row must prove the authorized K157 / `NPC 2` / level-22
   `CastleIdentity` with exact kingdom, name and supplied level. Do not select a
   castle in this Research proof. If another configured castle is active, stop
   and wait for package 06's explicit switch/return handling; do not silently
   switch it inside Research.
3. The direct caller may use a separate read-only inspection runtime before the
   production call, but retain the single outer account reservation across both
   dependent phases. Close only that inspection runtime through its existing
   ownership boundary, then invoke exactly one production
   `AutomationApi.research(account_id=..., priority=["development"],
   mutation_boundary=scope)` call. The direct caller must build its own scoped
   runtime while the outer reservation remains held for the complete sequence.
   An authored variant, if separately checked, must use one YAML
   `TaskId.RESEARCH` step with the same boundary and must borrow the caller's
   connected graph; it must not reconnect, close the shared runtime or fall back
   to `ResearchTask`.
4. Observe the route through the production trace. The route must prove Home →
   Research Queue, the reviewed Go focus transition, one exact Institute object
   and action point, Institute → Development tree, one complete unambiguous
   Development row, the exact node detail and a template-backed normal Start.
   A visible blue button alone is insufficient if the detail is active/busy or
   an overlay owns the frame. Do not tap the premium Research Now control.
5. At the mutation boundary, verify the journal's `research-001` intent was
   durable before the observed Start input. Allow no second Start, no speedup,
   no diamond action and no manual click. The postcondition must be two
   canonical stable fresh active-detail frames, each with exact active-detail
   evidence and no normal Start control. The typed outcome must be
   `STARTED`/`SUCCESS`,
   with one intent committed (or an explicitly retained dispatched intent if
   the postcondition is uncertain), zero diamonds and the authorized K157 /
   `NPC 2` / level-22 castle in the checkpoint.
6. Require the core runner's fresh Home exit. Save the typed result, trace path,
   source/detail/receipt artifact paths, pre/post checkpoint summaries, Start
   count, diamond delta and `closed.json`. Release the reservation using the
   existing cleanup path even when the workflow raises; preserve both execution
   and cleanup errors.

The Institute step is the first meaningful gate. If either production observation
path publishes zero or ambiguous Institute objects, the core must raise before
an Institute tap and before any journal intent. Save the source frame, both
builder observations, OCR/diagnostic report, trace, `summary.json`, `stop.json`
and cleanup record, then return a B producer blocker. Do not retry unchanged
captures or spend the Research budget to test the same absence.

## Success, stop and no-replay rules

| Observation | Disposition |
| --- | --- |
| Exact preflight, Institute, Development row/detail, normal Start, two stable active-detail frames, typed success and Home all pass | Accept this Development caller cell and hand the evidence to root for combined integration. |
| Institute absent/ambiguous, missing safe point, unsupported return edge, unknown/popup/stale frame | Stop before that action; classify the producer/route predicate precisely and retain artifacts. No retry without a new diagnosis or published fix. |
| No visible supported Development row or row is incomplete/ambiguous | A typed pending/verification outcome is expected; this is not live acceptance and must not be promoted. |
| Start control missing, premium-only, active detail, or queue eligibility unproved | Stop before mutation. Do not treat a visible blue word as authorization. |
| Dispatch returns uncertain or cleanup fails | Retain the durable intent and trace, do not replay. Report the exact journal state and cleanup error. |
| Exact identity mismatch or active castle is not authorized `npc_2` (K157 / `NPC 2` / level 22) | Stop before Research navigation/mutation. Do not fuzzy-match, rewrite the target or select another castle. |

The worker may perform a safe existing return-to-Home operation when the core
runner owns it and the destination is freshly confirmed. It must not send a new
Start, invoke a second API call after a Research intent, use a manual result as
proof, or repeat a failed proof whose evidence is unchanged.

## Source/build and evidence limits

`docs/game-reference/README.md` and `docs/game-reference/SOURCE_MAP.md` identify
Research client sources as `commands/collegetech/collegetechcommand.lua` and
`datas/collegedata.lua`. The recovered package is 5.0.203 / version code 233,
while the live footer in the saved run is a later 5.2.77 / 5.0.204.235. Client
handlers are useful source evidence only; they do not prove current server
eligibility, visual publication, or a successful live Start. The saved A replay
and B handback are the authoritative producer/consumer evidence for this plan.

## Exclusive ownership and return package

| Area | Owner for this slice |
| --- | --- |
| Research producer, Institute visual profile/identity/action publication, observation model and vision fixtures/tests | B. Read published handback; never edit/import B's dirty files. |
| Research policy, route, `CoreMutationBoundary`, journal, workflow, `CoreScriptDispatcher`, `ScriptRunner`, `ApplicationRunner`, `AutomationApi` and A-owned consumer tests | A/root. Any adaptation must remain in these files and preserve the current API/result contract. |
| Shared plan/index and validation ledger | Root. Do not edit them from this worker plan. |
| Live helper/artifacts | A-owned live phase; write only ignored timestamped artifacts and sanitized reports. |

Before handing back, verify the source freeze (HEAD and dirty state), list every
file actually changed after the B publication, record focused commands/results,
and include the exact live target, role, policy, journal state, trace/artifacts,
cleanup decision and first stop predicate. Do not claim the full port complete:
broader Economy/Military/Fortification support remains the queued B producer/A
consumer work in `PNC_B_FOLLOWUP_RECOGNITION_HANDOFF.md`.

## Copyable worker kickoff

> Work only in `C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration`.
> This is the remaining Development Research live-acceptance slice. Start from
> the source checkpoint `HEAD 4f33202` **plus the existing dirty caller/core/docs
> changes**; inspect status and preserve them, and never reset, stash, clean,
> merge, push or start from a bare commit. Read `AGENTS.md`,
> `instructions/CORE_WORKFLOW_PORTING.md`, this plan, the current A validation
> ledger, and `PNC_B_FOLLOWUP_RECOGNITION_HANDOFF.md`. Do not read/import/edit
> unfinished code in the B worktree. Wait for B's published Institute producer
> handback. The callers already pass the current offline gate (2,027 passed,
> six skipped); do not redesign them. Use only the exact existing Research
> scope: `UPGRADE_RESEARCH`, one normal Start, zero diamonds, `DAILY_CANARY`,
> exact configured account/castle/journal and one durable `research-001` receipt.
> The user authorizes `mega_old_acc` live actions with unlimited resources, and
> the Research target is already authorized as `npc_2` (K157 / `NPC 2` / level
> 22). Require that castle to remain active after connection; if another castle
> is active, wait for package 06's explicit switch/return handling rather than
> switching inside Research. After B handback and focused
> offline checks, run one canonical leased production `AutomationApi.research`
> proof. Stop before Institute tap/Start on missing, ambiguous, stale, popup or
> identity evidence; never replay a Research intent. Return a sanitized result
> package and the exact success/stop predicate to root.
