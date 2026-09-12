# Non-YOLO recognition implementation

Feature branch: `codex/non-yolo-recognition` in `artifacts/worktrees/non-yolo`.
Base: `b6c1a0176bd80423ba33015440ebac6b620fe001`.
Status: implemented recognition foundation validated; remaining F integrations
and broader promotion remain blocked as itemized below. No blanket rollout approval.

The isolated worktree preserves the relevant recognition/journal baseline recorded in
`artifacts/non_yolo_recognition/isolated_baseline.json`. The original checkout is
reserved for the user's other task. No configuration changes, castle switches,
resource actions, messages, YOLO, or trained detectors were introduced.

## 2026-09-12 Institute controls and live ownership repair

Current implementation worktree: `artifacts/worktrees/non-yolo-integration-current`; published integration commit `5261b1d` includes freshly fetched main `15845b8`. Earlier baseline/status entries below are historical.

The Institute profile now has four measured category controls (Development, Economy, Military, Fortification), using cropped interior anchors and bounded search regions at threshold 0.97. Its revision is 2. Existing Back, source provenance and `guarded_reference_only` qualification are preserved. The four matches scored 1.0 on the native 540�960 reference and two archived 900�1600 captures. These correlated references do not establish independent build/locale accuracy. Tests cover scaled geometry, missing-control abstention, wrong-category rejection and blocking-popup suppression. Research Start and research rows remain unsupported by this slice.

Fresh live evidence superseded the earlier launch/connectivity and busy-lease blockers. A capture-only probe leased the now-free testing instance, found it already running, and confirmed PNC at Home. The canonical More selector canary passed, verified the active castle without switching, and returned Home. The first custom core harness omitted `allowed_selector_screens`; its zero-input rejection was a harness error, not a production recognition failure. Invoking the navigation validator without required selector/account arguments also failed at CLI parsing; the complete canary invocation passed.

A subsequent fixed-route core probe verified the active castle but stopped after six navigation inputs on an ordinary idle Research Queue. The exact frame `artifacts/2026-09-12/testing/20260912T160633Z_core_20260912T160535Z_935f4b91_0023_core_6_after_0.png` and existing tracked queue fixture reproduce the issue: visual recognition identifies Research Queue and its measured Go/Close controls, while the old OCR fallback labels the same surface a generic popup with no safe close. The navigator now declares ownership only for unique visual Research Queue identity with a matched dismiss control. That proof suppresses only the queue's generic-popup fallback; all other modal/text/visual-close guards still run. OCR-only bootstrap retains its conservative fallback. No Android Back, coordinates guessed from a screenshot, or mutation selectors were added.

The first live replay of the ownership fix exposed a separate registration gap: `PNC_RESEARCH_QUEUE_CLOSE` (and Go) existed in the visual catalog and enum but not the canonical selector registry. Added both existing controls as semantic, non-geometry registrations scoped to Research Queue, retaining planned maturity. A read-only graph audit also found unresolved registrations for More Rank, Settings Rank, Settings Preferences, Settings Notifications and World HUD Toggle. Those routes are outside this Institute slice and remain explicit blockers to broader navigation promotion; no claim of complete graph actionability is made.

Validation before the ownership repair: six new/updated Institute tests passed; affected selection against origin/main ran 1,692 portable tests with five skips, all passed. The first ownership-targeted run was started before fake guard signatures were migrated and failed with keyword-argument TypeErrors; its replacement result and live outcome are recorded below. Logs and bounded probe scripts are under `.local-data/reports/non_yolo_resume_20260912/`.

Final Institute live proof passed on testing after the two fixes: exact active-castle verification, Research Queue Close/Go transitions, observed Institute entry, all four category controls, and final Home. It used 10 inputs and 37 observations in 148.918 seconds, without switching castles, starting research, spending, or sending anything. Institute capture: `artifacts/2026-09-12/testing/20260912T161804Z_core_20260912T161607Z_901ef3aa_0033_core_9_building_after_1.png`; Home capture: `artifacts/2026-09-12/testing/20260912T161829Z_core_20260912T161607Z_901ef3aa_0037_core_10_after_1.png`. Summary: `.local-data/reports/non_yolo_resume_20260912/institute_core_summary.json`. The instance pre-existed and is preserved at Home after lease release. This proves recognition and entry/return on the current target; category taps and Research Tree behavior were not exercised. The 78 targeted tests passed after mock/registry migration. Full ownership-repair suite passed 1,695 tests with five skips before the final two registry-dispatch regressions were added.

## Implemented architecture

- **A:** all 328 catalog selectors declare a strategy: 249 semantic, 19 guarded
  geometry, 58 unsupported, one template, one OCR region. Zero missing enabled
  template assets. The 52 enum IDs absent from the catalog have no runtime,
  authored-script, or tool consumers. Maturity is separate from resolver support.
- **B0:** immutable session/epoch/capture/input provenance, atomic one-use dispatch,
  stale-proof rejection, one compatible recapture for semantic targets, and no
  stale raw-point reuse. One read-only policy covers dispatch and recovery.
  Attempted inputs consume the budget; UNKNOWN permits passive recapture, not
  blind Back. Required-update confirmation is blocked in read-only probes.
  Roster synchronization is suppressed through the canonical observation service.
- **B:** ScreenClassifier owns the immutable ScreenDecision and derived
  Observation.screen_type. Global guards precede optional content regardless of
  request scope. Conflicts clear controls and facts; geometry cannot prove
  identity. Coordinate-only proof cannot authorize ordinary UI input.
- **C:** explicit catalog asset paths, masks, reference sizes and search regions
  replace implicit missing paths; loaders validate eagerly. Discovery and updater
  callers migrated. Fixed geometry requires guarded source state. OpenCV caches
  decoded templates and normalized frames; the 256-candidate bound is preserved.
- **D:** ObservationOcrContext owns an immutable captured-image copy and bounded
  region/preprocessing cache, with a pinned full-frame guard result and actual
  call/area/time diagnostics. All CachedOcrService callers migrated, including
  debug/discovery and coordinate preprocessing. Typed region plans share existing
  family/catalog bounds; reuse requires complete contained OCR boxes. Missing
  content stays unknown, with explicit named fallback.
- **E:** Bag and Daily Quest use complete detected cards and actual contained
  action buttons. Clipped/duplicate/ambiguous rows and missing controls abstain.
  Generic row actions and card-center substitutes are removed. Strict numeric
  parsing and connected inventory consumers preserve uncertainty.

Full-frame OCR remains the mandatory global guard. Families without reviewed
regions retain a named full-frame fallback. Reviewed geometry is restricted to
540×960 and 900×1600. Twelve visual profiles have 24 screen anchors, plus one
control PNG; provenance/layout revision is recorded. Profiles remain
`guarded_reference_only`: historical correlated frames and unknown build/locale
do not establish independent production accuracy.

## Live evidence

Shared flags:
`--config C:/Users/lebel/pnc/config/accounts.yaml --account testing`.
The canonical runtime verified the testing instance and foreground PNC. Startup
origin was not recorded. Manage Char proved active K287, level 10, with exactly
one selected matching row. Final Home identity can be name-only or insufficient;
it is not promoted to exact identity. No castle-selection action was dispatched.

Each run allowed eight attempted inputs/ten minutes and at most three passive
settle observations. Evidence lives in
`artifacts/non_yolo_recognition/live_final/`; screenshots/OCR use the configured
`C:/Users/lebel/pnc/artifacts/2026-09-11/testing/` artifact root.

Navigation command:
`py tools/validate_navigation_selectors.py --config C:/Users/lebel/pnc/config/accounts.yaml --account testing --selector PNC_BOTTOM_NAV_MORE --selector PNC_MORE_SETTINGS --output-dir artifacts/non_yolo_recognition/live_final/navigation`.
Passed three source cases: `20260911T035709Z_889bf4d6`,
`20260911T035827Z_edaac4bc`, `20260911T035939Z_335ef2a4`; 8/7/8 inputs,
Home restored.

Family command:
`py tools/validate_visual_navigation.py --config C:/Users/lebel/pnc/config/accounts.yaml --account testing --route ROUTE --output-dir artifacts/non_yolo_recognition/live_final/families`.

| ROUTE | Run | Result |
|---|---|---|
| fields | 20260911T040112Z_f371dcc2 | Passed, 7 inputs; Lord Info name matched reviewed current castle; Home |
| coordinates | 20260911T040202Z_d3a237d8 | Passed, 7; cheap P1 and fresh guarded P2 both X485/Y73; Home |
| quest | 20260911T040803Z_6e610d6d | Navigation passed, 8; Main/Daily; row recovery correction/proof pending below |
| bag | 20260911T041246Z_806bfcb5 | Passed, 8 including recovery; six complete rows; Home |
| vip | 20260911T041340Z_94ade44e | Passed, 7; VIP3; no reward/purchase; Home |
| chat | 20260911T041432Z_e4ce908b | Passed, 7; Kingdom tab/empty draft inspected; no transcript/send proof; Home |
| mail_hub | 20260911T041541Z_06ce741e | Passed, 7; hub only, no collection/send proof; Home |
| alliance | 20260911T041632Z_635dd09f | Applicability skip: Join Alliance proves no membership; 7; Home |
| gift_center | 20260911T041722Z_5a825125 | Passed, 7; banners observed, no offer/claim/purchase selected; Home |

The coordinates route replaces the broader movement calibration smoke with the
smallest read-only P1/P2 OCR proof; movement algorithms were not recalibrated.

Independently reviewed Bag facts: normal food 1K ×2011, normal food 10K ×72,
safe food 10K ×29, normal food 150K ×1, normal wood 1K ×1963, normal wood 10K ×66.
All six action points were inside the corresponding visible single-Use buttons,
including the differently placed Use-only control. Bulk controls were untouched.

### Live failures and fixes

- Quest `20260911T040314Z_b46e518c` stopped after six inputs: the row rewrite
  removed tab controls. Restored only three reviewed tabs after header/selected-tab
  proof; two-resolution tests check their centers against independent tab bounds.
  Recovery `20260911T040721Z_f5e4103d` returned Home in six inputs; retry passed.
- Bag `20260911T040858Z_ddcf2386` stopped after six inputs: an exported tab predicate
  unpacked RGBA as RGB. Normalize inside its canonical owner; RGB/RGBA regression
  passes. Bag retry above passed.
- Quest full-frame OCR missed four Go labels. Eight bounded saved-frame OCR calls
  found valid geometry, 1/5 Go labels with RGBA, 4/5 with RGB, and successful
  missing-button crop OCR in both modes; alpha was opaque. The first typed crop
  retry (`20260911T043754Z_3725409d`, `live_final/quest_recovery`) recovered 3/5
  actions. A further eight-call saved-frame experiment found RGB plus 8px source
  padding at 900px width recovered both remaining labels; scaling was unreliable.
  The final implementation uses that single proportional, row-clamped crop
  preprocessing variant. Original action bounds and contradictory labels remain
  authoritative. Cache and coordinate projection are tested at both resolutions.
- Final Quest run `20260911T044551Z_b8eb57ad` under `live_final/quest_rgb` passed
  seven navigation inputs and returned Home. All five identities/progress values
  matched the independently inspected image: upgrade building 0/1, Hero Arena 0/3,
  upgrade research 0/1, infantry 0/250, cavalry 0/250. Four Go controls were COMPLETE
  with points inside their actual buttons. Upgrade Building's label remained
  unreadable and emitted no point. This is four recoveries and one explicit
  abstention, not perfect OCR or an authorized Go/Claim execution result.
- The benchmark stage wrapper incorrectly had slots without declared fields.
  Restored its ordinary class; a test now constructs/invokes actual instrumentation.

## F and promotion boundaries

**F is not complete.** Explicitly disabling unsupported dependencies does not
count as implementing those workflows.

| Cell | Disposition |
|---|---|
| Research | Required RESEARCH_START has no proved producer; explicit pre-dispatch diagnostic; implementation/evidence gap |
| Gathering | Required GATHER/MARCH_CONFIRM lack proved producers; node/formation evidence incomplete; explicit diagnostic |
| Campaign | Required CAMPAIGN_BATTLE lacks proved producer; explicit diagnostic |
| World-map Expand | Unsupported default; synthetic search tests supply a declared fixture strategy, not live proof |
| Alliance member-only screens | Observed membership applicability skip on this target only |
| Login/account selection/roster scan | Current Manage identity proved; account/castle switching and roster persistence untested |
| Chat/mail subflows, buildings, shops, other Daily cells | Existing semantic producers retain named full-frame fallback; entry evidence does not prove all variants |
| Use/Claim/Recruit/Research/Send/Purchase effects | No live mutation proof; exact target/action/budget needed for a later mutating canary |
| Other resolutions/builds/locales/targets | Unreviewed; no broad promotion |

The inventory distinguishes 16 registered tasks from 24 enabled Daily
declarations, many without executors. New game tasks are outside this plan.
See `artifacts/non_yolo_recognition/active_family_inventory.md`.
The final static audit found one legacy movement-request alias used only by four
tests. Those callers now use `world_map_movement_proof_follow_up`; the alias was
removed. Runtime search confirms no CachedOcrService/Pillow matcher aliases or
YOLO/Ultralytics references in production, tools, or package metadata. Bounds
containment is shared by OCR reuse, row parsing and dispatch.

## Validation ledger

Final integrated runtime validation passed. Final Quest evidence is recorded above.

- `py -m unittest discover -s tests`: **1175 tests run, 18 skipped, zero failures**
  in 148.329 seconds; `artifacts/non_yolo_recognition/full_unittest_final.log`.
  The Windows journal tests are included in this clean result. The 18 opt-in/live
  and local-fixture skips are not asserted as passes.
- A subsequent benchmark-only correction evaluates the executor's implicit
  bounds-center target when no point override is supplied. It changes no runtime
  behavior or warm timing. `py -m unittest tests.test_benchmark_screen_recognition`
  passed **17 tests**; `benchmark_reporting_final.log`. The full suite was not
  repeated for this isolated serializer/test correction.
- `py artifacts/non_yolo_recognition/review_saved_targets.py`: passed. Saved
  selector bounds were reserialized through the corrected benchmark and checked
  against the original independent boxes; zero comparison failures and zero
  recovery regressions. Original row/guard comparisons and timing files remain
  unchanged. See `saved_target_review.json`.

- Before final live fixes, `py -m unittest discover -s tests`: **1167 run,
  18 skipped, zero failures**, 133.966s; `full_unittest_CDE2.log`.
  Earlier failures were stale test APIs/fixtures, migrated before this pass.
  The older B-only 1049-test pass is not the final integrated result.
- `py -m unittest tests.test_quest_tab_controls tests.test_daily_quest_vision tests.test_ocr_region_plan`:
  passed, 28 tests.
- `py -m unittest tests.test_resource_inventory_vision tests.test_quest_tab_controls`:
  passed, 26 tests.
- `py -m unittest tests.test_benchmark_screen_recognition`: passed, 16 tests.
- `py -m unittest tests.test_quest_action_ocr_recovery tests.test_daily_quest_vision tests.test_quest_tab_controls tests.test_ocr_region_plan tests.test_world_map_search`:
  passed, 114 tests before RGB refinement; `focused_final.log`.
- `py -m unittest tests.test_quest_action_ocr_recovery tests.test_ocr_region_plan tests.test_ocr_service`:
  passed, 33 tests after RGB refinement/shared containment; `quest_rgb_focused.log`.
- `git -c core.safecrlf=false diff --check`: passed; staged final check recorded
  with the feature commit.
- `py tools/benchmark_screen_recognition.py --coverage-audit --output artifacts/non_yolo_recognition/coverage_final.json`:
  passed; zero missing enabled template assets.
- Initial wheel build with `--no-build-isolation` failed because the local backend
  was unavailable. Isolated build passed. A separate venv installed with
  `--no-deps`; `-I` execution outside checkout verified 328 selectors, 12 profiles
  and 25 decoded PNGs from site-packages. No global package upgrade.
- Final wheel build: `py -m pip wheel . --no-deps --no-cache-dir -w artifacts/non_yolo_recognition/package_check/dist`
  passed; `package_check/final_build.log`. SHA-256:
  `581062587f94774f9fa376a2906803d450f365d65ec77b29991f0f3b6e1e6c22`.
- Final isolated install: `artifacts/non_yolo_recognition/package_check/venv/Scripts/python.exe -m pip install --no-deps --force-reinstall artifacts/non_yolo_recognition/package_check/dist/pnc_automation-0.1.0-py3-none-any.whl`
  passed; `package_check/final_install.log`.
- From `C:/Users/lebel`, execute the absolute venv Python with `-I` and
  `artifacts/non_yolo_recognition/package_check/verify_installed.py` (absolute
  worktree path): passed. All 25 PNGs decoded and **191 installed runtime file
  hashes matched the exact benchmarked source**; `package_check/installed_result.json`.

## Measurement contract

The manifest is frozen at 27 decoded-RGB-hashed frames, 14 source groups, with nine
independent manual control/row annotations. Correlated and synthetic samples are
not independent sessions. Incorrect values, missing facts, recovered/lost facts,
unsafe targets and abstentions are separate; rejecting all facts cannot qualify
a family. The same-revision no-visual comparator is not the frozen pre-D timing
baseline.

The earlier `pre_d_warm.json` is provisional due to observed concurrent Python
CPU work and is excluded. Quiet runs completed sequentially with no other Python,
OCR, live-test or build workload observed; process/environment snapshots are retained.

Commands:

- From `artifacts/non_yolo_recognition/pre_d_snapshot`, run
  `py tools/benchmark_screen_recognition.py --warm-replays 5 --measurement-profile pre_d --output C:/Users/lebel/pnc/artifacts/worktrees/non-yolo/artifacts/non_yolo_recognition/quiet_pre_d.json`.
  Measurement completed; correctness exit 1 is the retained pre-fix exact warning
  mismatch (generic popup instead of Upgrade Warning), not an ignored final failure.
- From the feature worktree,
  `py tools/benchmark_screen_recognition.py --warm-replays 5 --measurement-profile post_d --output artifacts/non_yolo_recognition/quiet_final.json`:
  passed. Zero wrong actionable classifications, zero annotated comparison
  failures, zero lost same-revision no-visual baseline facts.
- `py artifacts/non_yolo_recognition/compare_quiet_runs.py`: passed;
  `quiet_comparison.json`. Both revisions contain 135 warm replays on identical
  27 frames/groups. Total latency excludes ADB screenshot capture.

| Measurement | Frozen pre-D | Final |
|---|---:|---:|
| OCR engine p50 / p95 | 3476.9 / 6949.8 ms | 2117.2 / 4983.7 ms |
| Observation p50 / p95 | 3746.2 / 7434.8 ms | 2313.1 / 5278.0 ms |
| Visual stage p50 / p95 | 57.7 / 304.1 ms | 40.6 / 73.1 ms |
| Guard stage p50 / p95 | 2040.3 / 3335.9 ms | 1775.9 / 2970.6 ms |
| Content stage p50 / p95 (when invoked) | 1.1 / 2592.4 ms | 1.0 / 1811.7 ms |
| OCR engine calls | 575 | 250 |
| Processed pixel area | 115435575 | 109695330 |
| Cache hits | 115 | 130 |
| Full-frame contained reuse | Not instrumented by old cache | 135 |

Overall OCR median improved **39.1%**, observation p95 **29.0%**. Every represented
family met the timing target. For the cropped row families, OCR median improved
34.6% for Bag, 56.9% for Daily Quest and 44.3% for Main Quest; observation p95 also
improved. Fixed-field/coordinate families absent from this corpus are not assigned
those percentages. Fallback reasons remain recorded per replay; the mandatory
full-frame guard remains in place. Timing gates do not promote unreviewed layouts,
targets, controls or mutations.

## Final review disposition

The root reviewed the integrated canonical owners, worker corrections, offline
tests, installed artifacts and bounded live traces. No additional defect requiring
a change remains in the implemented boundaries. The explicit F implementation
gaps, limited independent profile coverage, and live Quest label abstention above
prevent claiming the whole plan or all game workflows complete. No broad rollout,
crop-only guard replacement, account switch or mutation result is approved here.

## 2026-09-12 resumed integration through `15845b8`

The next merge incorporates mainline `15845b8` into published feature `b2af988`, preserving history. It adds typed authored mail/Chat dispatch, bounded roster refresh, and outer cleanup-policy propagation while retaining the non-YOLO perception and legacy task-support gates. There were no text conflicts; review confirmed typed dispatch borrows the same connected graph and obtains frame/guard/OCR contracts from the canonical core composition.

Validation passed: 136 targeted typed-dispatch, roster, lifecycle and recognition-contract tests, then the full portable suite (**1,688 tests, 5 skips**). Logs: `.local-data/reports/non_yolo_resume_20260912/`. The sandbox's `py` launcher could not discover Python; equivalent commands used `C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe` directly. The full command was that interpreter followed by `-u tools/run_tests.py full`; no test failures remain in the combined candidate.

The refreshed live readiness command used the same interpreter with `.local-data/reports/non_yolo_resume_20260912/readiness_probe.py`. It stopped at **`InstanceBusyError` during the canonical reservation's bounded acquisition**, before connection or capture. Evidence: `readiness_summary.json` beside the probe. No launch, game-navigation input, castle switch or resource action occurred. This is a new live blocker; the older launch/connect failures below are historical, not a claim about the current emulator state. The lease was not bypassed and another account was not substituted.

The plan now reflects current typed workflow ownership. F continuation begins with saved Research/Institute evidence and the smallest supported recognition improvement; Research Start and research-row actionability remain unproved and unsupported. Current live promotion still requires the configured testing target after its reservation becomes available.

## 2026-09-12 integration outcome

Final publication and review: feature code pushed at `6f3f732`. `py -u tools/run_tests.py full` passed **1,642 tests with 5 skips**; the eight newly relocated shutdown tests passed separately. The exact scope, command results, and remaining acceptance limits are in [PNC_NON_YOLO_INTEGRATION_REVIEW.md](PNC_NON_YOLO_INTEGRATION_REVIEW.md). Main advanced to `b0ba590` while validation ran; following the user's push-then-review instruction, this publication includes main through `c7dfdd5` and records the newer integration as pending.

The combined feature preserves published history through `5c4ce6b` and mainline through `c7dfdd5`. Local merge commits are `e6df3bb` and `8697789`; the latter retains quiescent BlueStacks cleanup and the `.local-data` defaults. All conflict files were resolved. The split-test migration carried 175 feature test definitions into canonical owners, removed seven obsolete monoliths, and relocated 11 new feature tests. Mainline's eight shutdown tests were also moved into the portable inventory and passed.

The fresh coverage audit passes on the actual tracked catalog and manifest: 329 selectors, 273 enabled, 56 unsupported, 59 orphan IDs; 90 families include seven reviewed region plans and 83 guarded full-frame fallbacks. All 35 manifest hashes and 29 profile-source hashes match the canonical dimension-prefixed decoded-RGB contract. The catalog now declares layout identity independently of appearance identity, preserving Home recognition when multiple compatible variants match.

Packaging: the exact Python 3.13 wheel command could not load `setuptools.build_meta`; no dependencies were installed. A bundled build runtime produced the wheel without downloads, and isolated loading under Python 3.13 with the source worktree excluded succeeded. The wheel includes catalog v3, 29 profiles, 95 declared anchor images, 329 selectors, and the required Gift Center template. Wheel build/load evidence is under `artifacts/non_yolo_recognition/integration_20260912/`.

Targeted validation passed: 16 visual/catalog-layout tests, two Home/loading navigation regressions, 62 emulator/provenance/probe-lifecycle tests, and 41 tests fixing the last migrated fixture imports/paths. The current live gate remains blocked before capture, as detailed below. Remaining Research/Gathering/Campaign recognition and broad promotion are incomplete; the latest user request is to push this integration and review the published changes before further feature work.

### Historical recovery checkpoint

This checkpoint supersedes the source-control status in the historical continuation below. The corrected feature was committed and published as `5c4ce6b2c0b9ded17ddc7ddf8622bd6663b42e50`. Integration is underway in `artifacts/worktrees/non-yolo-integration-current` on temporary branch `codex/non-yolo-integration-current`, merging that published feature with mainline `68e7349`. The original feature worktree and its unrelated scratch files are preserved. Newly observed mainline commits `76c486f` and `0a12e8c` remain to integrate before landing.

The recovered code contains the replacement-navigation decision/provenance and shared OCR fixes described below. Mainline meanwhile moved canonical castle and observation-policy owners, modularized tests, and added direct mail/Chat/building workflow ports. The merge preserves these owners and ports, mainline's measured Chat shortcut and channel controls, and the feature's mandatory guards and capture-bound content. The merged catalog contains 29 profiles and 35 reference/validation samples; new mainline reference samples retain their existing screen labels and receive required provenance metadata without independent-corpus promotion.

Review also found a live-tool lifecycle gap: `run_probe` now validates `SMOKE_TEST`, holds the canonical API account reservation across its connected runtime, and releases both on failure or success. An unused enricher OCR-backend compatibility field and positional guessing were removed; the frame-scoped context is the backend owner.

Mainline's new Home appearance profiles exposed a real contract interaction: one Home screenshot can match both the general profile and a Chat-preview variant. Treating profile IDs as layout IDs made the strict classifier reject that valid Home frame, including when it was background evidence for loading. Catalog v3 now declares explicit layout IDs; these compatible Home appearances share `home_city`, while other layouts remain distinct. The 16 visual/variant tests and two focused Home/loading navigation tests passed. Different-layout evidence still abstains.

Current testing-instance readiness remains blocked: the scoped launch check raised `GameLaunchError`; the follow-up capture-only check raised `DeviceConnectionError` before screenshot capture. Commands: `py artifacts/non_yolo_recognition/integration_20260912/check_readiness.py` and the same command with `--capture-only`. Evidence: `readiness_summary.json` and `readiness_capture_summary.json` in that directory. Zero game navigation inputs, no castle switches or resource actions occurred. This does not count as live confirmation of the integrated recognition behavior.

Validation so far: application import and compile checks passed. The visual catalog's 14 integration tests passed, including mainline mail/Chat frames. The first wider vision run reported 25 failures and 63 errors while fixture/test migrations were still in progress; this is not an accepted integration result. Logs are in `artifacts/non_yolo_recognition/integration_20260912/`. Full portable validation, current live proof, final synchronization and push are still pending at this checkpoint. Historical test counts below must not be presented as validation of the combined tree.

## 2026-09-12 continuation after rebase

This section supersedes the historical "Final review disposition" for the current dirty feature worktree. The feature remains based on `02f07ac`; the source-control baseline and two newer remote test-organization commits are recorded in the updated plan. No main-worktree edits, commit or push were performed by this continuation. Pre-existing untracked review/build artifacts and the `send_mail_task.py` worktree status were preserved.

### Implemented integration

- Replacement `NavigationPerception` obtains the canonical capture OCR context factory through `core_runtime.py`. It no longer silently skips guards because the enricher lacks its own backend, nor creates a second unbound content context. Guards/content reuse native screenshot pixels and real capture identity.
- Shared `observation_provenance.py` owns control/row publication and rejects foreign frame/screen/layout proof. Missing provenance is retained as missing, so dispatch cannot treat a synthetic fixture identity as real capture proof.
- The canonical classifier now handles navigation layouts, viewport rejection, loading, conflicting foreground guards and explicit background evidence. Update-over-coordinate-dialog regression retains the background identity without treating both dialogs as competing foreground guards.
- Exact modal and loading recognition uses one shared implementation across the two guard entry points. A measured popup is no longer suppressed merely because Home anchors survive. Generic close search distinguishes the outer close band from shifted controls belonging to separately established modals; owned dismiss regions are removed before selecting another close candidate.
- Strict screen/decision consistency and requested OCR-selector registration are restored. Rebase-only duplicated recovery declarations, error-policy substitution and default registry injection were removed. Offline fixtures now supply explicit contracts. The shadow-detector test file changed only to migrate shared Observation fixtures; no YOLO production behavior was added.

### Validation of this working-tree state

All paths below are relative to `C:/Users/lebel/pnc/artifacts/worktrees/non-yolo` unless the full path is shown.

| Command/check | Result |
|---|---|
| `py -m unittest tests.test_capture_and_vision tests.test_yolo_shadow tests.test_ocr_region_plan tests.test_observation_artifact_policy` (worker targeted modules) | Passed: 184 tests across the modules; 3 fixture skips |
| `py -m unittest tests.test_navigation_core tests.test_core_runtime tests.test_screen_decision_contract tests.test_frame_provenance tests.test_ocr_service tests.test_flows_and_tasks` | Passed: 284 tests before the final additional-close regression |
| `py -m unittest tests.test_navigation_core tests.test_core_runtime tests.test_capture_and_vision` | Passed: 203 tests; 3 fixture skips, including final close-exclusion behavior |
| `py -m unittest discover -s tests` | Passed: **1,392 tests, 22 skips**, after the review corrections. Log: `artifacts/non_yolo_recognition/resume_20260912/full_unittest_review_fixed.log`. The final click-point containment refinement additionally passed the 62 targeted tests below |
| `py tools/benchmark_screen_recognition.py --coverage-audit --root C:/Users/lebel/pnc/artifacts/worktrees/non-yolo --output artifacts/non_yolo_recognition/resume_20260912/coverage_audit.json` | Passed; 329 selectors, 273 enabled, 56 unsupported, 59 orphan IDs, zero missing required assets |
| Refreshed audit consistency checks | Passed; `artifacts/non_yolo_recognition/resume_20260912/report_validation.json` |
| `py -m unittest tests.test_navigation_core tests.test_core_runtime tests.test_screen_decision_contract` | Passed: 62 tests including empty popup profile, displaced same-ID control, supplied classifier and final click-point containment |
| `git diff --check` | Passed |
| `py artifacts/non_yolo_recognition/resume_20260912/run_core_probe.py` | Failed before navigation: configured testing instance connected, PNC not foregrounded, canonical launcher raised `GameLaunchError`; `core_summary.json` |
| Follow-up canonical runtime diagnostic through `py -` | Blocked by Android readiness `DeviceConnectionError`, before capture; `launch_diagnostic.json` |
| `py tools/validate_navigation_selectors.py` | Initial invocation rejected missing `--account` and `--selector`; this tool is now a live canary CLI. Fully specified rerun below remains blocked by the confirmed readiness failure |
| Current installed-wheel, warm latency, per-target and mutation promotion | Not rerun/promoted; old evidence remains explicitly historical and mutation execution is outside this authorization |

Initial navigation tests exposed the update-over-coordinate-dialog foreground/background bug and were rerun after the fix. One targeted invocation used nonexistent `tests.test_screen_decision`; corrected to `tests.test_screen_decision_contract`. These invocation failures are not counted as successful validation. The first full run passed 1,389 tests; subsequent full runs passed 1,390 and 1,392 as the additional-close and review regressions were added. The final containment refinement was checked by the affected 62-test suite while the last full run was in progress. Expected offline CLI negative-test messages in the full log do not represent host restarts: the full suite remained offline, with opt-in live modules skipped.

### Live blocker and exact next commands

Target was the configured `testing` instance with required `SMOKE_TEST` role and its currently active castle. Both attempts used canonical runtime leases and configured ADB resolution. Startup origin is unknown. No navigation tap, resource mutation, message, or castle switch occurred. Active castle verification, Bag content, final Home and live timing remain unverified because the launch/readiness failures happened first.

After the configured instance is responsive, rerun the bounded core proof (eight attempted inputs, ten minutes, three observations per settle) and the selector canary:

```powershell
py artifacts/non_yolo_recognition/resume_20260912/run_core_probe.py
py tools/validate_navigation_selectors.py --config C:/Users/lebel/pnc/config/accounts.yaml --account testing --selector PNC_BOTTOM_NAV_BAG --source-screen PNC_HOME_CITY --output-dir artifacts/non_yolo_recognition/resume_20260912/selector_live
```

Then repeat the relevant Quest/field/coordinate evidence before extending F. The refreshed `f_disposition_matrix.md` still records 90 families, seven reviewed region plans, and 83 guarded full-frame fallbacks. Research/Gathering/Campaign producer evidence, independent corpus labels, per-target qualification and mutation-backed postconditions remain incomplete. A visual-only generic close with measured surface support retains its pre-existing navigation recovery policy; the general builder still treats that evidence as unresolved. This continuation shares exact modal detection and conservative decision/provenance contracts, but does not promote a uniform visual-only policy or claim the complete vision plan is finished.

Final bounded review found and resolved two further integration issues: same-screen visual popup profiles no longer drop interruption-owned controls, and runtime composition injects the existing classifier instead of constructing a separate one. Template refinement is limited to foreground-guard-owned selectors whose proposed click point falls inside the measured guard bounds; an underlying same-ID control cannot redirect dismissal. Regression tests cover both issues. The live readiness blocker remains unchanged.

2026-09-12 final Institute increment validation: direct Python `tools/run_tests.py full` passed 1,697 tests with five skips (`.local-data/reports/non_yolo_resume_20260912/full_institute_registered.log`); targeted suite passed 78 tests; canonical More canary and Institute core live proof passed; `git diff --check` passed.

## Final synchronization with main 328e000

The live-tested increment was committed and pushed as `0cd24ad` before integrating five newer mainline commits. Main now dispatches game readiness and roster refresh through the typed core and uses the actual focused Android window when deciding whether PNC needs launching. The session merge retains both the focused-window parser and this branch's capture/input provenance and one-use frame guard. Removed legacy task tests are migrated to canonical readiness coverage; the independent passive-UNKNOWN navigation regression and unsupported Research Start rejection remain required. Core perception still receives the configured classifier and frame-local OCR context.

Merged readiness validation passed on testing using `CoreRuntime.ensure_game_ready`: zero inputs, three captures, final Home, 13.407 seconds. Summary: `.local-data/reports/non_yolo_resume_20260912/latest_readiness_summary.json`; final capture: `artifacts/2026-09-12/testing/20260912T162132Z_core_20260912T162122Z_b8b372be_0003_final_home.png`. Focus/session/core/Queue targeted checks passed 51 tests. The loading regression no longer imports the retired legacy readiness task; its canonical guard, recovery, input-denial and runner-settle coverage passed four tests.

Integration through main `328e000`: full portable suite passed 1,709 tests with five skips (`.local-data/reports/non_yolo_resume_20260912/full_latest_main_merge.log`); 51 core/session/queue, eight bootstrap/unknown-root, four loading and two end-to-end tests passed. Whitespace check passed.
