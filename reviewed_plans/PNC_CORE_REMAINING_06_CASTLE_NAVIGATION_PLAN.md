# Remaining 06 — Castle switching and shared navigation

Date: September 14, 2026. Owner: A workflow/runtime navigation acceptance,
with B as the producer of recognition facts and root as the integration owner.
This handoff contains only the remaining alternate-castle switch-and-return
proof and the A-owned shared-navigation consumer gaps that can block it. It
does not reopen Research, Resource, Hero, Mail, Login or any other workflow
family.
The clean B producer checkpoint is commit
`10740ebb9b8d9d43fc24f970b904796ca41bd082`; it supplies saved recognition facts
for consumer qualification, not authorization for a live target or proof of an
alternate switch.

## Finish line

Accept this slice after one fresh, authorized production run proves an actual
alternate-castle round trip through the typed replacement core:

1. the configured `mega_old_acc` account is established through the canonical
   leased runtime and a fresh preflight observes the exact currently selected
   `CastleIdentity` before any selection tap; this observed source identity is
   retained as the required return target;
2. the route reaches Castle Selection through the reviewed
   Home → More → Settings → Manage Characters path, with each transition
   supported by a fresh observed control;
3. a bounded roster scan finds the supervisor-selected target using exact
   kingdom, canonical name and supplied level evidence, reacquires that row,
   and sends at most one observed `TapListEntryAction` for the switch;
4. fresh postflight evidence proves the target is selected and the core returns
   Home; the same caller then selects the observed original castle through the
   same guarded path, proves the original identity and returns Home again;
5. each actual hop yields a typed `SelectCastleResult` with the exact original
   and selected identities and `switched=True`, while a pre-existing target
   yields the explicit no-op result without a row tap; and
6. one process-scoped reservation covers the dependent phase and the production
   script uses one connected runtime for both hops; cleanup preserves the first execution error, and the result,
   trace, identity frames and final Home evidence are retained.

The alternate destination is still pending supervisor selection. The source is
the fresh active castle observed at the start of the run, and restoration to
that source is a fixed part of this package's acceptance. A no-op on the
already selected destination, a manually performed switch, a partial roster
observation, or a successful route to Settings does not satisfy the
alternate-switch acceptance gate.

## Source and evidence already verified

These A-worktree owners are present in the dirty integration candidate at
`HEAD 4f33202` and define the behavior to consume and validate:

| Owner | Contract to preserve |
| --- | --- |
| `pnc_automation/app/automation/select_castle.py:SelectCastleWorkflow` | Home-to-Home `NONSPENDING_STATE_CHANGE`; retains the original active identity, invokes reviewed `context.select_castle`, then requires exact `context.verify_active_castle_identity` postflight and reports a typed `SelectCastleResult`. |
| `pnc_automation/app/automation/engine/navigation_core.py:NavigationCore.select_castle` | Enters the reviewed Castle Selection route, observes Manage Characters, scans down/up within the bounded six-swipe limit, matches the exact target, reacquires a fresh row, sends one typed list-entry tap only when needed, and proves the selected row or safe Home return. |
| `pnc_automation/app/automation/engine/navigation_core.py:reviewed_navigation_edges` | Owns the reviewed transition graph, including More → Settings, Settings → Castle Selection, Castle Selection Back → Settings, Settings Back → Home/World, Research edges and the current world-coordinate edge. No workflow may add a local coordinate override. |
| `pnc_automation/app/automation/engine/core_runtime.py:CoreRuntime.preflight_active_castle_identity`, `_scan_active_castle_identity` | Performs the read-only fresh selected-row preflight with bounded roster scrolling and returns exact identity evidence before a typed workflow is allowed to continue. |
| `pnc_automation/app/automation/engine/core_script_dispatcher.py:CoreScriptDispatcher.execute`, `validate_core_script_step` | Requires an explicit `SELECT_CASTLE` target, obtains the already connected runtime, preflights the active identity, runs `SelectCastleWorkflow`, and borrows the caller's runtime without closing it or falling back to a legacy task. |
| `pnc_automation/app/automation/engine/runner.py:AutomationRunner._run_core_step`, `_align_step_castle_target` | Dispatches an authored typed selection directly; for an optional legacy castle target, constructs one synthetic required typed `SELECT_CASTLE` step and then observes the legacy task's post-alignment frame. The legacy task must not perform a second selection. |
| `pnc_automation/app/automation/engine/script_runner.py:_prepare_account_session_steps`, `_build_core_step_executor` | Materializes explicit castle targets and builds one connected core dispatcher/runtime graph for the script. The caller's role, cleanup and optional mutation boundary plumbing remain unchanged; castle selection itself is nonspending. |
| `pnc_automation/app/pnc/domain/castles.py`, `pnc_automation/app/pnc/domain/observation.py` | `castle_entry_identity_matches` requires kingdom plus canonical roster name; `castle_entry_matches` also requires level when supplied; current selected-castle resolution requires exact evidence. Preserve these consumers and their bounded OCR normalization. |

The current validation ledger records the implementation and no-op proof but
not an alternate switch. The root no-op result is
`.local-data/artifacts/replacement_core/select_castle_noop_result.json`; it
proved an active-castle selection request vetoed the row tap and returned Home.
The earlier focused selection/dispatcher/runner set passed 122 tests on the
original feature checkpoint, and the current A candidate's broader offline
ledger is **2,027 passed, six skipped (2,033 tests)**. Those are offline and
no-op evidence; they do not prove a real alternate transition or return.

The repository also contains concrete negative coverage for the remaining
consumer contract in
`tests/unit/app/automation/engine/test_select_castle_navigation.py`: wrong
kingdom, wrong level, absent/ambiguous rows, stale observations, invalid action
points, timeout and mismatched postflight all stop without a replayed tap.

The published B castle qualification records exact selected K157 / `0 sticker NPC`
/ level 15 evidence in saved frames `0042` and `0108`. Its initial OCR
spelling `0 stickerNPC` remains distinct; the correction is an exact producer
publication, not permission for a fuzzy consumer alias. The separately captured 3xx
roster correction extends the bounded request to include the 8th/bottom row
and publishes K303 / level 5 as the selected result. Its raw roster and holdout
pixels are duplicates and the evidence is off-manifest, so it is a correction
checkpoint rather than independent live target authorization.

Root's latest saved RapidOCR both-path Home frame (`0026`) is `Home/CLEAR` but
contains zero Home-building objects where the old A capture contained four.
Home identity therefore does not prove the Home object route; root's plans 01/02
own the Home/Institute producer regression. This package keeps that evidence
separate from castle selection and the More/Settings/Search edge checks.

## Decisions, target and authority

The user has authorized `mega_old_acc` and all needed in-game actions with
unlimited resource spending. Castle selection is classified by the workflow as
`NONSPENDING_STATE_CHANGE`; this package needs one round trip and qualified
navigation, without another game workflow. Account configuration remains
the authority for instance and live role. The saved config resolves
`mega_old_acc` to the configured `daily_canary` role, so the live caller must
use `DAILY_CANARY` where a role is required by the authored selection path.

The tracked catalog currently names exactly these aliases for the account:

| Alias | Exact configured identity |
| --- | --- |
| `main` | K314 / `K314a4452b3900` / level 1 |
| `npc_2` | K157 / `NPC 2` / level 22 |

The B captured K157 / `0 sticker NPC` / level 15 identity in saved frames `0042`
and `0108` is a qualified producer fixture, not the configured `npc_2` alias
and not a live target choice. Keep its exact spelling and level separate from
the catalog identity. Likewise, the corrected 3xx 8th/bottom-row evidence
publishes K303 / level 5, but the prior 3xx authorization and duplicate raw
roster/holdout pixels do not authorize this plan's current live target.

The earlier NPC 2 runs establish neither that it is still selected nor that it
is the intended switch destination. The worker must observe the current source
freshly, retain its exact identity, and match it to the configured catalog
before constructing the return step. The supervisor must choose the alternate
destination alias (or explicitly authorize the worker to choose one of the
other configured aliases). Restoration to the observed source is fixed by this
package. Do not turn the open destination choice into a permission denial: the
account/action envelope is already granted, but a worker must not guess which
alternate castle should be selected.

| Decision or permission | State | Worker action |
| --- | --- | --- |
| `mega_old_acc` account and its configured instance | Granted | Resolve through the canonical account/lease runtime; do not hard-code an ADB endpoint. |
| In-game switch and return actions | Granted by the user | Use only the reviewed typed route and exact observed controls; selection has no resource budget to spend. |
| Live role | Configured `DAILY_CANARY` | Pass the exact configured role required by the caller; missing authority is a runtime stop. Do not substitute `LIVE_TESTING`. |
| Current source castle | Fresh observed runtime fact | Preflight the selected row, retain its exact full identity, and match it to the configured catalog before constructing the return step. If it cannot be matched exactly, stop rather than inventing a return target. |
| Alternate target alias | Pending supervisor selection | Record a different configured alias and full identity, or record explicit permission for the worker to choose one; do not infer `main` or `npc_2` from prior evidence. |
| Return/round-trip policy | Fixed by this package | Return to the freshly observed source through the same reviewed route and prove exact source identity/Home before cleanup. |
| Other accounts, unconfigured castles, config edits, credentials/session secrets, direct game-service calls or external sign-in | Not authorized by this handoff | Do not access or change them. |
| Merge, push, destructive Git/filesystem operations | Not part of this handoff | Return reviewable docs/code evidence to root; root owns integration. |

## Source-freeze and producer checkpoint

Before a future implementation or live worker starts, record the shared A
worktree as `HEAD 4f33202` plus the existing dirty caller/core/documentation
changes. Run `git status --short --ignored` and inspect the relevant diff. Do
not reset, stash, clean, cherry-pick, import a B worktree, or begin from a bare
commit: the caller plumbing and current core changes are intentionally
uncommitted in this shared checkpoint.

Apply the shared source-freeze, ownership and evidence rules in the [six-package
checkpoint](PNC_CORE_WORKFLOW_PORTING_PLAN.md#common-starting-checkpoint-and-evidence-rules)
before handing this slice to a future worker.

The original B recognition plan and the current published producer evidence
remain authoritative for B-owned castle/More/Search facts. The narrower
`reviewed_plans/PNC_B_FOLLOWUP_RECOGNITION_HANDOFF.md` is authoritative only for
the follow-up slices it lists; it is not a blanket handback for every castle,
More or Search dependency. B exclusively owns
`pnc_automation/app/pnc/vision/**`, `pnc_automation/core/vision/**`, the
observation/domain producer models and their fixtures/tests. Read published
findings and checkpoints only; never copy unfinished B code into A. In
particular, preserve the recorded producer distinction between `0 sticker NPC`
and `0 stickerNPC`. The A consumer must not normalize, alias, or rewrite a
published castle name to make a selection pass. If a producer handback changes
the published identity contract, stop and ask root to reconcile the shared
contract before editing the matcher.
Use the saved B evidence first; do not repeat a proven recognition mutation just
to qualify this consumer.

The current A `CoreRuntime.observe_ready` loading-only settle and the no-claim
checkpoint behavior are already fixed in the guide/source and are not remaining
blockers. Keep them as readiness guards. A Home identity observation is also not
proof of a Home object route; any Home/Institute producer regression remains in
root's package 01/02 plans.

There is one known A-owned shared-navigation integration gap. The current
`reviewed_navigation_edges()` entry at
`pnc_automation/app/automation/engine/navigation_core.py` maps
`PNC_WORLD_MAP` through `PNC_WORLD_COORDINATE_BAR`, while B's measured selector
evidence identifies `PNC_WORLD_SEARCH_BUTTON` as the actionable control and the
coordinate bar as a non-actionable label. After verifying the current released
producer facts, A should change only this reviewed edge to the existing
Search-button selector and add the fresh-dialog regression described below. The
existing released enricher already
publishes a Search action point, and
`tests/integration/vision/test_world_root_observation.py` covers the world-map
observation; verify those facts first rather than waiting for a new B release.
Do not add a world-map coordinate tap or a workflow-specific fallback. This
edge is a shared navigation prerequisite for future consumers; it is not
evidence that castle switching itself can be completed by raw coordinates.

The More → Settings action geometry is another explicit dependency. A's
consumer already asks the reviewed `PNC_MORE_SETTINGS` control for a fresh
action point. The prior live observations showed a route-level failure where a
manual More menu could be used but the production point did not reliably reach
Settings. Verify the current published bounds/point through both observation
builders before assigning ownership. If the producer evidence is wrong, return
that finding to B; if it is correct and the route still fails, A may repair the
shared edge/transition in `navigation_core.py` and its consumer test. A must
not compensate with a hard-coded workflow coordinate.
The B 3xx More/Settings replay is useful reference evidence in both builders,
but it does not close this current A route check. More/Settings and the world
Search edge remain separate predicates.

## Remaining A work

There is no reason to redesign the typed castle workflow or add another
selector. The future worker should do only the following if the producer
handback or focused tests show a real gap:

1. **Consume exact identity.** Keep kingdom and canonical name matching paired,
   require level whenever the configured target supplies it, and require fresh
   selected evidence after a tap. Each accepted identity must come from a fresh
   `PNC_CASTLE_SELECTION` / `manage_char` frame with a `CLEAR` guard, frame-local
   provenance and exact selected row. A selection action additionally requires
   its own current measured safe action point; read-only selected-identity proof
   must not manufacture a tap control. Stale, fragmented or ambiguous identity
   rows remain unknown. Do not use name-only matching, substring or
   fuzzy matching, kingdom wildcards, aliases in place of observed values, or
   level omission. The existing `castle_names_match` normalization is the
   current OCR normalization; it strips formatting noise but is not permission
   to collapse the concrete `0 sticker NPC`/`0 stickerNPC` producer mismatch.
   If raw-spacing identity is a new requirement, raise it as a shared design
   decision instead of silently changing one consumer.
2. **Repair only shared More/Settings consumption when justified.** Reproduce
   the exact fresh frame and compare both builder outputs from B's handback.
   Treat this as a separate route predicate from Search-button publication;
   passing B's 3xx replay does not prove the current A transition.
   Preserve the reviewed edge and action semantics; change the A navigation
   owner only if the published point/selector is valid and the transition
   remains incorrect. Add a deterministic fixture/test for the observed
   failure and a negative test that no action is sent for absent/ambiguous
   controls.
3. **Correct the world coordinate edge.** Verify the released observation facts
   and tests first, then use the existing measured `PNC_WORLD_SEARCH_BUTTON` as
   the action selector and retain `PNC_WORLD_COORDINATE_BAR` as content/label
   evidence. Require a fresh `PNC_WORLD_COORDINATE_DIALOG` after the button
   action. Do not wait for a new B package or alter B-owned world
   observation/enricher files in this slice.
4. **Cover composed typed dispatch.** Verify that one authored script containing
   two explicit required `SELECT_CASTLE` steps can borrow one connected runtime
   and dispatch each typed workflow in order. Verify that an optional legacy
   castle target uses exactly one synthetic typed selection before the legacy
   task and does not call a second legacy selector/tap. Keep this as a caller
   integration check; do not add a compatibility kwargs layer or a new runtime
   graph.
5. **Keep live acceptance bounded.** Do not extend this slice to Research,
   Resource, Hero, Daily maintenance, broad castle matrices, or a new fallback
   route. Any failure outside the listed consumer/route owners returns to root
   or B with its first unproved predicate.

## Offline validation

Run only after the source-freeze check and verification of the relevant current
producer facts are recorded. The following existing groups are the smallest
useful A gate:

First replay the saved B castle and world fixtures through both actual observer
paths (`ObservationBuilder` and `NavigationPerception`) with actual RapidOCR,
normal bounded semantic requests, screen/layout/guard, exact row identity and
action-point provenance retained. A passing group containing controlled OCR
tests is not itself this real replay. The replay is offline and does not
authorize a live roster tap. The K157 `0 sticker NPC` frames and the
corrected K303 level-5 bottom-row evidence remain producer checkpoints, while
More/Settings and Search are separate A consumer predicates.

```powershell
$py = 'C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe'
# Add when producer implementation/fixtures change; report real OCR replay separately.
& $py tools/run_tests.py group integration.vision
& $py tools/run_tests.py group unit.app.automation.engine
& $py tools/run_tests.py group unit.app.pnc.navigation
& $py tools/run_tests.py group script_runner
& $py tools/run_tests.py group workflows
```

Relevant modules are:

| Module | Purpose and edit boundary |
| --- | --- |
| `tests/unit/app/automation/engine/test_select_castle_navigation.py` | A-owned selection workflow, exact identity, bounded scan, no-op and no-replay guards. Add only a missing consumer regression. |
| `tests/integration/script_runner/test_castle_target_preparation.py` | Prepared explicit target/alias materialization and required selection policy. |
| `tests/integration/workflows/test_runner_castle_targeting.py` | A-owned synthetic typed alignment before an optional castle-targeted legacy task. |
| `tests/integration/workflows/test_runner_end_to_end.py` | One connected graph with explicit typed steps and final result ordering; run the existing case before changing it. |
| `tests/integration/workflows/test_core_runtime.py` | Exact active-castle preflight and bounded roster scan. |
| `tests/unit/app/pnc/navigation/test_castle_profile_entry.py` | More → Settings → Manage Characters route contract. |
| `tests/unit/app/pnc/navigation/test_navigation_core.py` | Reviewed edge/transition behavior, including the world-coordinate dialog edge. |
| `tests/integration/vision/test_castle_selection_observation.py`, `test_world_root_observation.py`, `test_coordinate_bar_local_fixtures.py` | B-owned producer evidence; run for diagnosis or handback verification, never edit in this slice. |
| `tests/integration/script_runner/test_typed_core_dispatch.py`, `tests/contract/workflows/**` | Protected/root-owned tests; do not edit. |

If A changes a production consumer, run
`tools/run_tests.py affected --base origin/main --explain` and retain its
selection evidence. Run `full` only if the runner falls back, a shared model or
schema changes, or root requests the final integration gate. The existing
2,027-pass/six-skip result is the baseline, not fresh evidence for a changed
candidate. Save command output in a unique ignored `.local-data` result file;
run `git diff --check` before handback.

The meaningful new tests, if required, are narrowly defined:

- A dispatcher composition test prepares two exact `SELECT_CASTLE` steps,
  asserts one runtime/graph factory and no runtime close by the borrowed
  dispatcher, and checks both typed results' original/selected/switched fields.
- A runner alignment test asserts an optional castle-targeted legacy step emits
  exactly one synthetic typed selection, then one post-alignment observation,
  with no legacy selection tap or second typed dispatch.
- Exact identity negatives cover same name/wrong kingdom, close or
  substring-like name, wrong level, stale selected evidence and missing action
  point. Keep producer spelling fixtures in B's producer contract; do not add a
  workflow rewrite test that blesses `0 sticker NPC` as `0 stickerNPC`.
- A navigation-edge test asserts a fresh world-map observation dispatches the
  actionable Search-button selector and accepts only a fresh coordinate dialog;
  a coordinate-bar-only observation must not qualify the action.

## Bounded live proof

The future live worker must first obtain the supervisor's alternate target alias
(or the explicit permission for the worker to choose one of the other
configured aliases). Record that target identity, the freshly observed source
identity and a sanitized reset/checkpoint identifier in a unique ignored
artifact directory.
The saved K303 level-5 3xx result and earlier 3xx authorization do not satisfy
this current target choice. Use the canonical process-scoped lease for
`mega_old_acc`,
hold it across both hops, and preserve a pre-existing instance through the
existing cleanup policy. Do not edit account/castle configuration to
manufacture a target.

After the initial fresh preflight observes the source, match that exact
`CastleIdentity` to the account target catalog and construct one authored
`RunScript` with explicit typed selection steps, for example
`ENSURE_GAME_RUNNING`, `SELECT_CASTLE(target)`, then `SELECT_CASTLE(source)`.
Invoke the production ScriptRunner path once with the configured
`DAILY_CANARY` role, the selected cleanup policy and no mutation boundary.
Resolve the target and return identities through the account target catalog; do
not substitute a hand-written identity or raw ADB endpoint. If the observed
source cannot be matched exactly to a configured return target, stop before a
switch and report that integration gap. If an explicit test must exercise an
optional legacy task's alignment, use a separate bounded offline/live
diagnostic after the core proof; do not mix that task's possible mutation with
the castle acceptance.
Use the canonical API and typed actions only: no desktop mouse/keyboard control,
direct game service or repeated budget/authorization request. The first fresh
source identity, each one-row action, exact target/source result and final Home
screen are the correlated proof records.

If learning the initial source requires a separate inspection runtime, retain
the same outer process reservation while closing that inner runtime with the
canonical preserving cleanup policy, then invoke the production script. The
two switch steps must still share one production graph. Do not release and
reacquire the lease between inspection and switching, and do not make the
script borrow a runtime through an interface that does not support borrowing.
Record the inspection and production runtime lifetimes separately in evidence.

Before the first switch action:

1. Ensure the game is ready and obtain a fresh stable Home frame. A loading,
   blocking popup, unknown screen or unresponsive capture stops the run before
   navigation.
2. Run the typed dispatcher/runtime's exact active-castle preflight. The
   selected row must prove the freshly observed source identity with exact
   kingdom, canonical name and level. If the current source cannot be matched
   to a configured return target, or the active evidence changes, do not
   silently repair it or reinterpret the target; stop and retain the evidence.
3. Enter Castle Selection through fresh Home → More → Settings → Manage
   Characters observations. If the reviewed More/Settings point does not
   produce the expected screen, stop before a roster tap and classify the
   producer/edge predicate.
4. Observe the roster, scan only within the existing bounded down/up limit, and
   accept one exact target row with a safe observed point. Reacquire the row
   from a fresh frame immediately before the one typed tap. If it is already
   selected, record a no-op and follow the supervisor's policy; do not tap merely
   to create a switch receipt.
5. After the tap, require fresh selected-target identity and the reviewed Home
   return. Save the first `SelectCastleResult`, action trace, pre/post frames,
   row evidence and final screen. Repeat the same bounded route for the
   observed original source only after target postflight succeeds. Never use a
   stale first roster frame or a manually opened Settings page as postflight
   proof.
6. After the return, require exact source identity and Home again, then release
   the single lease/runtime through normal cleanup. Preserve execution and
   cleanup errors and save `summary.json`, `stop.json`, `cleanup.json`, typed
   result JSON and the trace under the unique ignored artifact directory.

Success requires both actual hop results to report exact identities and
`switched=True`, one observed row tap per actual hop, no duplicate or legacy
tap, exact final source identity, final Home and clean lease cleanup. It also
requires the route to have used the production reviewed selectors. A no-op
result is valid behavior for that request but is not the alternate-switch
acceptance proof.

## Separate world-coordinate edge proof

The castle round trip does not exercise the world-map coordinate-dialog edge.
If A changes `reviewed_navigation_edges()` to use
`PNC_WORLD_SEARCH_BUTTON`, run one separate bounded nonspending production
proof after the offline edge tests and before claiming that shared navigation
gap closed. Hold the canonical `mega_old_acc` process lease for the complete
Home → World Map → dialog → Home sequence and use the configured role/runtime;
do not run a world calibration or coordinate search matrix.

The proof must start from a fresh stable Home frame, reach World Map through
the existing reviewed route, observe a visible actionable
`PNC_WORLD_SEARCH_BUTTON` point, send exactly one typed button action, and
capture a fresh `PNC_WORLD_COORDINATE_DIALOG`. The coordinate bar may be
published as label/content evidence but must not qualify the action by itself.
Close/back through the reviewed dialog edge, require fresh Home, release the
lease through normal cleanup, and save the source/action/dialog/return frames,
trace, typed outcome and cleanup record under a unique ignored artifact
directory. This proof enters the dialog only; it does not type coordinates or
submit a destination.

Stop before the button if the Search control is absent, ambiguous, stale,
covered by a popup or has no safe observed point. Stop after the action if the
dialog is not a fresh exact screen, the return edge is unproved, or Home is not
freshly observed. Do not tap the coordinate bar, use raw coordinates or replay
an uncertain button action. If the current released producer evidence and
offline fixtures cannot support the edge, return the first failed predicate to
B/root rather than editing a B-owned observer.

## Stop, no-replay and evidence rules

| First unproved observation | Required disposition |
| --- | --- |
| Current source identity is absent, ambiguous, stale, wrong kingdom/name/level, or cannot be matched to a configured return target | Stop before any switch tap; retain exact frame and identity diagnostic. Do not select another configured castle. |
| More, Settings or Manage Characters action is absent/ambiguous or the transition returns to an unexpected screen | Stop before the next action; classify the producer versus shared-edge defect. Do not use a raw coordinate or manual bypass as proof. |
| Target row is absent, ambiguous, malformed, outside the bounded scan, stale, has no safe point, or has mismatched identity | Stop before the row tap. Do not widen the scan, fuzzy-match, alias, or replay. |
| Post-tap target identity or Home return is unproved | Do not tap again. Preserve the trace and ask root whether the state can be safely inspected before the fixed return step. |
| First hop succeeds but return source is absent/mismatched or its route fails | Stop after the first failed predicate; never repeatedly tap the target or source. Report the target receipt and current exact evidence. |
| Runtime factory/lease/cleanup fails | Preserve the exception and cleanup error according to the existing runner policy; do not create a second runtime or rerun the sequence. |
| World-coordinate dialog edge is exercised and Search-button evidence is absent | Stop that navigation check and return it to A/B ownership; castle acceptance cannot use the coordinate bar as an action. |

No live replay is allowed after an uncertain tap, identity mismatch or changed
screen without a new diagnosis and explicit supervisor decision. This workflow
spends no diamonds and writes no mutation journal; that does not reduce the
need to retain the exact selection trace and prevent duplicate switches.

## Client-source limits and ownership

`docs/game-reference/README.md` records the recovered client build as
5.0.203/version 233 and requires source provenance to be distinguished from
live behavior. `docs/game-reference/SOURCE_MAP.md` is the source map, not a
castle-selection success claim. The B handoff and its producer captures are
useful evidence for labels, bounds and screen classification, but only a fresh
live observation on the authorized account proves the current roster and
transition behavior. The original B recognition plan and current published
producer captures are inputs for consumer diagnosis, but do not use extracted
client handlers, a source inventory or a stale screenshot to authorize a castle
tap.

| Area | Exclusive owner for this slice |
| --- | --- |
| Vision/observation/domain producer publication, source captures and related fixtures/tests | B. Read the published handback; do not edit/import dirty B code. |
| Castle workflow, exact identity consumer, reviewed navigation edges, core dispatcher/runtime composition and caller tests | A/root. Keep changes in A-owned automation/navigation/entrypoint files and allowed tests. |
| Shared plan/index and validation ledger | Root. This worker supplies this plan; do not modify the shared index. |
| Live lease choreography and ignored artifacts | A live-validation worker after target/policy selection. |

Before handback, the worker must list every file changed after the producer
checkpoint, retain focused test outputs and `git diff --check`, and state the
freshly observed source identity and selected target alias, the fixed return
step, configured role, exact result fields, final identity/Home evidence, lease
cleanup and first stop predicate.
Do not claim the complete core port: broader producer-dependent workflows remain
in the authoritative B follow-up.

## Copyable worker kickoff

> Work only in `C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration`.
> This is the remaining castle switch/return and shared-navigation consumer
> slice. Start from `HEAD 4f33202` **plus the existing dirty caller/core/docs
> changes**; inspect status and preserve them. Never reset, stash, clean, merge,
> push, or start from the bare commit. Read `AGENTS.md`,
> `instructions/CORE_WORKFLOW_PORTING.md`, this plan, the current A validation
> ledger, `PNC_AB_COORDINATED_CONTINUATION.md` and the authoritative
> `PNC_B_FOLLOWUP_RECOGNITION_HANDOFF.md`. Do not read/import/edit unfinished
> code in `C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation`.
> Use the original B recognition plan and current released producer evidence for
> castle/More/Search facts; the narrower B follow-up is authoritative only for
> its listed slices. B owns vision/model/producer files. Verify the exact castle
> identity and More/Settings evidence before the route. Preserve exact kingdom + canonical name +
> supplied level matching and the recorded `0 sticker NPC` versus `0 stickerNPC`
> distinction; add no fuzzy, alias, substring or coordinate
> fallback. A owns only the shared navigation consumer, including changing the
> reviewed world coordinate edge from the non-actionable coordinate bar to the
> measured Search-button selector after verifying current released producer
> facts and tests. The offline
> baseline is 2,027 passed and six skipped; run only focused groups after a real
> change. The user authorizes `mega_old_acc` in-game actions with unlimited
> resources, and the configured live role is `DAILY_CANARY`. The alternate target
> alias is pending supervisor selection (or explicit permission for the worker to
> choose another configured alias); the source is the fresh observed active
> castle and return to it is fixed. Do not guess the destination or frame the
> open choice as a permission denial. After source freeze, current producer-fact
> verification and focused checks, run one canonical leased production script
> with typed `SELECT_CASTLE(target)` then `SELECT_CASTLE(source)`. Prove fresh exact
> source identity, reviewed route, one bounded target-row tap, fresh target
> postflight/Home, one bounded return tap, fresh source postflight/Home and
> cleanup. Stop before any tap on missing, ambiguous, stale, malformed or
> mismatched evidence; never replay an uncertain switch. Return sanitized result,
> trace, identity frames and the first success/stop predicate to root.
