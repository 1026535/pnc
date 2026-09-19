# Remaining 06 — Castle switching and account-selection menus

Scope revised September 15, 2026; evidence snapshot September 14. **Owner: the Castle/navigation feature agent**, from
roster/control recognition through exact selection, route/caller behavior,
regressions and live switch/return acceptance. Missing castle or More/Settings
facts remain this package's implementation work because V01–V43 do not cover
account-selection menus. Shared visual integration is consumed from V01.

Execution base: the current assignment's verified checkpoint and this plan
revision. The old merged `6bc2758` remains historical source context. Reuse a suitable existing
isolated task worktree and create/use the feature branch there; do not create a
second worktree merely for a preferred path. Preserve resumed feature work; use
a new worktree only if the current checkout is shared or unsuitable. Follow the
[common starting-checkpoint rules](../core/PNC_CORE_WORKFLOW_PORTING_PLAN.md#common-starting-checkpoint-and-evidence-rules).
A's caller changes and B's recognition are already committed and merged. Record
that exact base and plan revision; never import dirty peer work or run multiple
feature writers in the integration checkout. Read the
[independent package contract](../core/PNC_CORE_WORKFLOW_PORTING_PLAN.md#six-remaining-agent-packages).

The existing World Search/coordinate-dialog edge remainder moves to package 03,
which retains the missing Search/dialog correction and gathering-action routes;
V19 supplies qualified World object acquisition/inspection. It is no longer a DoD item or
prerequisite here. Login/provider/session preparation ordering belongs to 05;
this package consumes an already authenticated session and owns selection and
identity semantics without waiting for 05's completion.

## V01–V43 boundary

Read the [remaining-feature scope amendment](../vision/PNC_CORE_REMAINING_VISION_BOUNDARY.md).
This package retains More/Settings/Manage Characters, selected-roster identity,
row geometry, bounded scanning and exact switch/return behavior, including their
feature-local recognition and qualification. V01 supplies the existing shared
matcher, OCR, guard and observation integration; do not rebuild those services.

V02–V03 own Home camera localization, fixed atlas, building acquisition/panning,
seasonal references and event occupancy. V41 owns the Castle building/Territory
menu. Neither is account or castle switching, and neither is new work here.
Use existing Home identity for More/Settings; Home-building detection is not a
prerequisite for that route. World Search/dialog remains package 03; Login/provider
and generated authentication ordering remain package 05.

Do not wait for all V packets or duplicate their qualification. Record any actual
shared-output dependency while continuing selection work. Preserve resumed
implementation; do not reset to the historical base. Bind the round trip to the
current assignment's authorized account, instance, configured role and fresh
source/alternate identities under the amendment. Saved identities are fixtures,
not an execution allocation.

### Saved evidence locations

Historical ignored `core_resume/` evidence resolves under
`C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration/.local-data/artifacts/`.
Historical B `.local-data/reports/` diagnostics resolve under
`C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation/.local-data/reports/`.
Other numbered capture paths use the exact roots in the linked capture-findings
record. Read these saved artifacts in place; they are not copied into a new
feature worktree. Tracked fixtures arrive with the merged base. Put this feature's
new captures, replays and reports under its own ignored `.local-data/` and test
selection under `.test-impact/`. Missing historical evidence is reported with its
exact source path, never replaced by a guessed current screen or invented result.

## Finish line

Accept this slice after one fresh, authorized production run proves an actual
alternate-castle round trip through the typed replacement core:

1. the current assignment's authorized account is established through the canonical
   leased runtime and a fresh preflight observes the exact currently selected
   `CastleIdentity` before any selection tap; this observed source identity is
   retained as the required return target;
2. the route reaches Castle Selection through the reviewed
   Home → More → Settings → Manage Characters path, with each transition
   supported by a fresh observed control;
3. a bounded roster scan finds the chosen configured alternate target using exact
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

Use the supplied alternate target, or choose a different configured castle only
when the current assignment authorizes that choice. Record its alias and exact
identity before the first hop. The source is
the fresh active castle observed at the start of the run, and restoration to
that source is a fixed part of this package's acceptance. A no-op on the
already selected destination, a manually performed switch, a partial roster
observation, or a successful route to Settings does not satisfy the
alternate-switch acceptance gate.

## Source and evidence already verified

These owners are present in merged `6bc2758` and define the behavior to
preserve, repair where demonstrated, and validate:

| Owner | Contract to preserve |
| --- | --- |
| `pnc_automation/app/automation/select_castle.py:SelectCastleWorkflow` | Home-to-Home `NONSPENDING_STATE_CHANGE`; retains the original active identity, invokes reviewed `context.select_castle`, then requires exact `context.verify_active_castle_identity` postflight and reports a typed `SelectCastleResult`. |
| `pnc_automation/app/automation/engine/navigation_core.py:NavigationCore.select_castle` | Enters the reviewed Castle Selection route, observes Manage Characters, scans down/up within the bounded six-swipe limit, matches the exact target, reacquires a fresh row, sends one typed list-entry tap only when needed, and proves the selected row or safe Home return. |
| `pnc_automation/app/automation/engine/navigation_core.py:reviewed_navigation_edges` | Owns the reviewed transition graph, including More → Settings, Settings → Castle Selection, Castle Selection Back → Settings and Settings Back → Home/World. Edit only these feature edges; Research belongs to 01 and World Search/dialog to 03. No workflow may add a local coordinate override. |
| `pnc_automation/app/automation/engine/core_runtime.py:CoreRuntime.preflight_active_castle_identity`, `_scan_active_castle_identity` | Performs the read-only fresh selected-row preflight with bounded roster scrolling and returns exact identity evidence before a typed workflow is allowed to continue. |
| `pnc_automation/app/automation/engine/core_script_dispatcher.py:CoreScriptDispatcher.execute`, `validate_core_script_step` | Requires an explicit `SELECT_CASTLE` target, obtains the already connected runtime, preflights the active identity, runs `SelectCastleWorkflow`, and borrows the caller's runtime without closing it or falling back to a legacy task. |
| `pnc_automation/app/automation/engine/runner.py:AutomationRunner._run_core_step`, `_align_step_castle_target` | Dispatches an authored typed selection directly; for an optional legacy castle target, constructs one synthetic required typed `SELECT_CASTLE` step and then observes the legacy task's post-alignment frame. The legacy task must not perform a second selection. |
| `pnc_automation/app/automation/engine/script_runner.py:_build_core_step_executor` and selection target materialization | Preserve one connected dispatcher graph and exact caller target forwarding. Package 05 owns authentication/preparation ordering in `_prepare_account_session_steps`; this feature consumes its existing contract without editing Login or waiting for a new implementation. |
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
Home identity therefore does not prove building acquisition; V02–V03 now own
Home localization/acquisition, with V04 consuming Institute entry. Keep that
evidence separate from account selection and More/Settings checks.

### September 16 regression: native screenshot drops the selected Hopium row

**Open; reproduced offline on `71272665667baf787538ca8377ed29746d440e22`.**
This is a concrete package-06 regression, not a new V01–V43 menu assignment.
During authorized Pet Workshop exploration on `main`, the agent left Workshop,
returned Home and ran the canonical active-castle preflight. Manage Characters
clearly showed selected **K157 / NPC on Hopium / C31**, with Hopeful NPC as a
separate unselected row. The bounded preflight failed with
`Active castle identity was not found within the bounded roster scan; no castle switch is allowed.`
Settings displayed build `5.2.80_5.0.204.235`. These identities describe saved
evidence; they do not allocate a future live target.

The initial description of a missed checkmark was too narrow. The saved OCR
diagnostic locates the full name in the roster pass, but its authoritative name
crop splits it into overlapping `NPC` and `on Hopium` lines (another captured
position yielded `NPC` and `C on Hopium`). `_read_castle_name_field` abstains on
multiple candidates, so `_build_castle_entry` drops the row before checking its
marker. Do not fix this by accepting partial names, concatenating overlapping
fragments or supplying the expected identity from config.

Paired real-RapidOCR replays through **both** `NavigationPerception.build` and
`ObservationBuilder.build` establish a material input-format difference:

| Same saved frame | Selected identity result |
| --- | --- |
| Native BlueStacks PNG, RGBA | `PNC_CASTLE_SELECTION`, `CLEAR`, `manage_char`, but `current_castle=None`; Hopium row omitted |
| Explicit RGB conversion | Exact `CastleIdentity("K157", "NPC on Hopium", 31)` |
| Existing marker detector on the selected row | `True` |

The native image has fully opaque alpha. The six canonical castle row/name/
selection functions are unchanged from the exploration's V01-era checkpoint
`f1ecc683` to this replay revision. Current captured identity tests convert loaded
fixtures to RGB; a passing RGB replay therefore does not close this native-input
failure. This establishes format-sensitive OCR behavior, not a diagnosis of the
backend's internal conversion. Fix the demonstrated difference at the appropriate
existing capture/OCR or field-preprocessing owner after tracing that boundary;
keep one canonical implementation and preserve exact-identity abstention.

Evidence root on the originating host:
`C:/Users/lebel/pnc/.local-data/artifacts/2026-09-16/pet_workshop_exploration_20260916/`.
The failed frame and its retained OCR diagnostic are respectively
`20260916T050902Z_core_20260916T050630Z_5fecd708_0021_core_6_castle_roster_scroll_after_0.png`
and the same stem with `_recognition_gap.json`. An additional position's fragment
evidence is `20260916T050809Z_core_20260916T050630Z_5fecd708_0015_core_4_castle_roster_scroll_after_0_recognition_gap.json`.
Replay entry point and results are under
`C:/Users/lebel/pnc/.local-data/reports/pet-workshop/`: `replay_castle_identity.py`,
`replay_castle_identity_failed_frame.json` (RGB) and
`replay_castle_identity_failed_frame_native.json` (native RGBA).
Pass the failed PNG path to the replay; add `--native` to preserve capture mode.
These paired replays use the same frame and are not independent holdout captures.

**Closure checks:** retain a mode-preserving captured regression, run real bounded
OCR through both production publishers and require the exact selected Hopium
identity from the native input. Preserve wrong-name/kingdom/level and genuinely
fragmented-name negatives. Investigate the producer boundary before choosing
the smallest normalization correction; do not mask the issue by converting only
the test fixture. Fold one fresh production preflight into this package's
already-required authorized round trip; no additional spending or broad live tour
is needed. Until those checks pass, this issue remains open even if RGB fixtures
and other V packets pass.

### September 17 follow-up: current native replay succeeds

The original failure is **not reproduced** at `752cb70c5d8d0eb3aadbaa11bfa6499037b70667`
with the current RapidOCR 3.4.5 environment. Both real production publishers
read the **same native RGBA frame** as exact K157 / NPC on Hopium / C31 and
detect its selected marker. The lead checked the replay code (native image
mode retained, real `RapidOcrService`, both production publisher compositions),
the structured results, and source/report hashes. The current OCR owner now
uses `rapidocr` with the qualified PP-OCR recognizer instead of the older
`rapidocr_onnxruntime` backend at the failing revision. This is a changed
implementation/environment; the specific causal commit was not isolated.

Current evidence is linked by the corrected manifest:
`C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-live-main/.local-data/devin-live-test/runs/main-evidence-20260917/turn-002/evidence.json`.
The replay report is at that run's `replay/replay_castle_identity_failed_frame_native.json`;
source PNG SHA-256 is `6abfad35b1c8d18d59c5dcde8050816e1ac1b82ff03896e472ed033419848939`.
The same pass exercised the production live preflight and verified current
selected **K157 / Sword NPC2 / C26** (no switch), corroborated by roster frame
`20260917T044719Z_core_20260917T044156Z_9e838404_0027_active_castle_identity.png`
under `C:/Users/lebel/pnc/artifacts/2026-09-17/pet_workshop_evidence_20260917/`.

**Still open for the package owner:** retain the mode-preserving portable
regression and exact-identity negatives before closing this entry; do not
implement an unnecessary second normalization path for a now-passing replay.
The live worker substituted an in-memory role for configured `read_only`, so
this pass does not qualify the configuration/authority boundary or the
package's complete switching/return contract. The Workshop coordinator has
requested a narrowly scoped temporary config-role change for future testing;
no new live action is authorized by this evidence note.

## Decisions, target and authority

Bind this proof to the current execution assignment's explicitly authorized
account/instance and switch/return scope. Preserve applicable session permission
without asking again. This plan does not select an account or grant new switching
or spending authority. Resolve the configured live role through the canonical
runtime; a missing role or caller incompatibility is an explicit gap, not a reason
to substitute a role or edit configuration. The proof is one
`NONSPENDING_STATE_CHANGE` round trip and requires no resource spend.

Preflight the current source freshly, retain its exact identity and match it to
the configured catalog before constructing the return step. Honor the user's
alternate target if supplied. Choose another configured alias only when the
current assignment authorizes that choice; freeze its full identity before input.
If no valid authorized source/alternate pair exists, request the exact missing
choice while continuing offline work. Restore the observed source through the
same reviewed route.

Historical fixtures remain separate from execution targets:

- The old catalog example named `main` as K314 / `K314a4452b3900` / level 1 and
  `npc_2` as K157 / `NPC 2` / level 22. Re-resolve current configuration; neither
  example selects or authorizes a target.
- Saved `0042` and `0108` publish K157 / `0 sticker NPC` / level 15. That is not
  the `npc_2` identity. Preserve spelling/level distinctions and exact matching.
- The corrected bottom-row fixture publishes K303 / level 5. Historical 3xx
  permission and duplicate raw/holdout pixels are not current target authority.

Record account/instance/role, applicable switch permission, fresh source, exact
alternate, return target and cleanup policy in the nonsecret run manifest. Keep
other accounts, unconfigured castles, protected-config changes and external
sign-in outside the assignment unless explicitly authorized. Merge/push authority
comes from the execution session, not this handoff.

## Independent source and producer checkpoint

Verify the merged code base and plan revision in this feature's own worktree.
Record `git status --short --ignored`, preserve unrelated work, and inspect the
actual current methods and captured fixtures. There is no dirty A snapshot or
new B release to wait for. Existing castle/More/Settings producer facts are
baseline evidence; the feature agent owns any necessary correction to those
facts and both-observer publication/qualification in this worktree.

Retain the bounded roster crop including the observed bottom/eighth row and the
exact published `0 sticker NPC` identity. The historical `0 stickerNPC` output
cannot be accepted via fuzzy matching, aliases or a workflow-local rewrite.
Preserve kingdom, canonical roster name and supplied level checks. Diagnose a
producer defect in its canonical field parser/semantic crop/control definition;
never supply a desired identity from config or the workflow target.

`CoreRuntime.observe_ready` and the no-claim checkpoint fix are implemented.
Preserve their timing, freshness and no-replay behavior. Home building
acquisition belongs to V02–V03; it is unnecessary for More/Settings entry and
is not this feature's blocker.
The World Search/dialog edge formerly listed here must be implemented and accepted
within 03, so castle completion neither waits for it nor repeats its proof.

The outstanding More → Settings failure is this feature's end-to-end diagnostic:
replay the published control through both observers, compare fresh bounds/point
with the actual transition, and fix the responsible feature producer or edge.
The old 3xx replay is useful reference evidence but does not by itself prove the
current production route. Missing/ambiguous controls stop input; they do not
transfer responsibility back to B.

## Remaining implementation sequence

1. **Own the selected-roster and control facts.** Check the saved K157 and bottom
   row regressions and the native-RGBA Hopium failure above through both real
   observers. Fix any demonstrated feature
   name/kingdom/level/selection/geometry issue in the canonical producer, with
   feature-specific semantic OCR requests, models/IDs, anchors and tests. Qualify
   a new changed layout on an independent capture group when required; no switch
   is needed merely to tune a saved name field.
2. **Close More/Settings/Manage navigation.** Reproduce the known Settings failure,
   distinguish control geometry from transition handling, and change only the
   corresponding feature producer/edge. Prove the fresh destination and safe
   return. Add absent/ambiguous/covered/stale control negatives. No hard-coded
   workflow coordinate, generic UNKNOWN retry or local popup bypass is allowed.
3. **Preserve and repair exact selection where evidence requires it.** Use the
   canonical bounded down/up scan, fresh row reacquisition and one observed entry
   tap; require exact postflight and Home. Retain no-op and ambiguous no-replay
   outcomes. Do not weaken the matcher to accept a differently published name.
4. **Complete this feature's caller acceptance.** Cover two explicit typed
   `SELECT_CASTLE` steps borrowing one connected graph. Cover the optional legacy
   task's synthetic typed alignment and one post-alignment observation with no
   second legacy selector. Own selection-specific dispatcher, target-materializing
   and caller/test branches. Package 05 may change Login ordering independently;
   do not make a joint preparation design or shared edit reservation a task here.
5. **Prepare and run the one round trip.** From an already authenticated session,
   observe source, choose/freeze a configured alternate, retain source as return,
   and run the complete production sequence below under one lease. Diagnose and
   resolve owned failures before another eligible attempt; uncertain hops require
   safe read-only state reconciliation, never a blind second tap.
6. **Accept locally.** Require the owned implementation/tests and actual switch,
   return, exact final identity/Home and cleanup evidence. Deliver the feature
   change and report independently of any other package or combined integration.

## Offline validation

Record the independent source checkpoint and relevant current facts, then select
only groups covering actual feature changes from the existing runner:

First replay the saved castle/More/Settings fixtures through both actual observer
paths (`ObservationBuilder` and `NavigationPerception`) with actual RapidOCR,
normal bounded semantic requests, screen/layout/guard, exact row identity and
action-point provenance retained. A passing group containing controlled OCR
tests is not itself this real replay. The replay is offline and does not
authorize a live roster tap. The K157 `0 sticker NPC` frames and the
corrected K303 level-5 bottom-row evidence remain producer checkpoints, while
More/Settings is a separate route predicate; World Search belongs to 03.

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
| `tests/unit/app/pnc/navigation/test_navigation_core.py` | Reviewed edge/transition behavior, limited to More/Settings/Manage and their reviewed returns. |
| `tests/integration/vision/test_castle_selection_observation.py`, `test_castle_identity_captured_fields.py`, `test_settings_profile_observation.py`, `test_menu_observation.py` | Feature-owned producer regressions/qualification for castle and More/Settings. Edit these scoped cases and their fixtures when fixing the corresponding facts. World/coordinate tests belong to 03. |
| `tests/integration/script_runner/test_typed_core_dispatch.py`, `tests/contract/workflows/**` | Own selection-specific cases; preserve all other workflow contracts. No coordinator edit is required. |

If this feature changes production code, run
`tools/run_tests.py affected --base origin/main --explain` and retain its
selection evidence. Run `full` only if the runner falls back, a shared model or
schema changes, or this feature changes a shared contract requiring broad coverage. The existing
2,027-pass/six-skip result is the baseline, not fresh evidence for a changed
implementation. Save command output in a unique ignored `.local-data` result file;
run `git diff --check` before recording feature acceptance.

The meaningful new tests, if required, are narrowly defined:

- A dispatcher composition test prepares two exact `SELECT_CASTLE` steps,
  asserts one runtime/graph factory and no runtime close by the borrowed
  dispatcher, and checks both typed results' original/selected/switched fields.
- A runner alignment test asserts an optional castle-targeted legacy step emits
  exactly one synthetic typed selection, then one post-alignment observation,
  with no legacy selection tap or second typed dispatch.
- Exact identity negatives cover same name/wrong kingdom, close or
  substring-like name, wrong level, stale selected evidence and missing action
  point. Keep producer spelling fixtures in this feature's captured producer contract; do not add a
  workflow rewrite test that blesses `0 sticker NPC` as `0 stickerNPC`.
- A More/Settings navigation-edge test requires a fresh valid control and the
  exact destination; text-only, covered or stale controls cannot authorize input.

## Bounded live proof

The feature worker resolves the authorized configured alternate under the target
policy above, honoring the current assignment's choice and scope. Record that target identity, the freshly observed source
identity and a sanitized reset/checkpoint identifier in a unique ignored
artifact directory.
The saved K303 level-5 3xx result and earlier 3xx authorization do not satisfy
this current target choice. Use the canonical process-scoped lease for the
assigned account/instance, hold it across both hops, and preserve a pre-existing
instance through the
existing cleanup policy. Do not edit account/castle configuration to
manufacture a target.

After the initial fresh preflight observes the source, match that exact
`CastleIdentity` to the account target catalog and construct one authored
`RunScript` with explicit typed selection steps, for example
`ENSURE_GAME_RUNNING`, `SELECT_CASTLE(target)`, then `SELECT_CASTLE(source)`.
Invoke the production ScriptRunner path once with the actual configured live
role required by that caller, the selected cleanup policy and no mutation boundary.
Verify the role contract; do not hard-code the historical `DAILY_CANARY` allocation.
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
   selected, record a no-op and choose a genuinely different configured target before a
   fresh request; do not tap merely
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

## Scope transfer: World Search/dialog

The pre-existing `PNC_WORLD_COORDINATE_BAR` versus measured
`PNC_WORLD_SEARCH_BUTTON` edge correction and its fresh-dialog/return proof are
now package 03's world-navigation work. This is a transfer of the existing
remainder, not deletion or acceptance of it. Package 03 contains the implementation,
negative tests and bounded live evidence requirements. This package does not
edit those keys/edges or depend on their completion.

## Stop, no-replay and evidence rules

| First unproved observation | Required disposition |
| --- | --- |
| Current source identity is absent, ambiguous, stale, wrong kingdom/name/level, or cannot be matched to a configured return target | Stop before any switch tap; retain exact frame and identity diagnostic. Do not select another configured castle. |
| More, Settings or Manage Characters action is absent/ambiguous or the transition returns to an unexpected screen | Stop before the next action; classify the producer versus shared-edge defect. Do not use a raw coordinate or manual bypass as proof. |
| Target row is absent, ambiguous, malformed, outside the bounded scan, stale, has no safe point, or has mismatched identity | Stop before the row tap. Do not widen the scan, fuzzy-match, alias, or replay. |
| Post-tap target identity or Home return is unproved | Do not tap again. Preserve the trace and inspect read-only through the existing supported API. Resume the fixed return only when current exact target/source state and controls prove it safe; never repeat the uncertain hop. |
| First hop succeeds but return source is absent/mismatched or its route fails | Stop after the first failed predicate; never repeatedly tap the target or source. Report the target receipt and current exact evidence. |
| Runtime factory/lease/cleanup fails | Preserve the exception and cleanup error according to the existing runner policy; do not create a second runtime or rerun the sequence. |

No blind replay is allowed after an uncertain tap, identity mismatch or changed
screen. The feature owner diagnoses the state from fresh evidence and retains the
first operation result; missing evidence is a stop, not a request for routine
coordinator permission. Ask the user only for genuinely missing external input. This workflow
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

| Area | Exclusive feature edit scope |
| --- | --- |
| Castle/roster models and producers | Castle row/selection/name/kingdom/level fields, `_build_castle_roster_additions`, `_extract_castle_entries`, `_read_castle_name_field`, exact row geometry and bounded semantic requests; feature keys/fixtures in both observers' publication paths. Generic OCR/guard engines remain unchanged. |
| More/Settings/Manage controls | `_build_more_settings_menu_additions` and feature profile/control/selector keys, semantic regions, `navigation_core.py:reviewed_navigation_edges` entries and fresh transition/return tests. |
| Core and callers | `SelectCastleWorkflow`, `NavigationCore.select_castle`, `CoreRuntime.preflight_active_castle_identity`/bounded selected scan, selection-specific `WorkflowContext`/dispatcher/API branches, synthetic alignment in `AutomationRunner._align_step_castle_target`, exact target materialization. Login/provider handling and `_prepare_account_session_steps` ordering belong to 05. |
| Tests | Feature-specific producer/caller/route/exact-identity cases in the existing modules listed above and new feature-local fixtures. Shared files are partitioned by symbols/keys, not held for root edits. |
| Plan/evidence | This plan and its own ignored source/action/receipt/cleanup report. No shared index or peer progress editing is required. |

**Independent DoD:** all required owned producer/control/route corrections and
caller semantics are complete; meaningful changed-contract tests and repository
gates pass; the actual two-hop production proof establishes exact identities,
one entry tap per hop, both fresh Home exits, one shared runtime and proper
cleanup; the reviewable feature change records its exact base and evidence.
No-op is tested behavior but cannot replace the actual alternate proof. No B
handback, other feature acceptance or final combined merge is a DoD predicate.
Missing required facts or an unperformed hop keeps this package incomplete.

Consult Continue core only for a demonstrated generic runtime/identity contract
question outside this feature's semantic scope, and Continue non-YOLO only for a
generic vision service question. Normal castle/control producer fixes, selection
methods and their tests belong to this worker and do not require consultation.

## Copyable worker kickoff

> Implement the revised package 06 with PNC_CORE_REMAINING_VISION_BOUNDARY.md.
> Preserve resumed work and record actual code/plan revisions. Reuse V01 shared
> visual/observation machinery. Own only uncovered More/Settings/Manage Characters
> and roster recognition, exact identity, bounded scan/selection, typed callers
> and alignment, and an authorized actual switch/return proof. Do not implement
> V02/V03 Home camera/building panning, V41 Castle building menus, World inspection
> or the Search/dialog edge. Keep Login/provider ordering in package 05. Qualify
> changed roster/control facts in both observers; retain exact kingdom/name/level
> matching and no replay after uncertainty. Use the current assignment's authorized
> target/configured role, freeze fresh source and alternate identities, and run
> both production hops on one runtime/lease. Historical aliases, roles and budgets
> are not the execution allocation. Report tests, actual switch/return identity
> and Home evidence, cleanup and exact remaining gaps.
