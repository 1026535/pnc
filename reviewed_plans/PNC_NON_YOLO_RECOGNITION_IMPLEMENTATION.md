# Non-YOLO recognition implementation

Feature branch: `codex/non-yolo-recognition` in `artifacts/worktrees/non-yolo`.
Base: `b6c1a0176bd80423ba33015440ebac6b620fe001`.
Status: implemented recognition foundation validated; remaining F integrations
and broader promotion remain blocked as itemized below. No blanket rollout approval.

The isolated worktree preserves the relevant recognition/journal baseline recorded in
`artifacts/non_yolo_recognition/isolated_baseline.json`. The original checkout is
reserved for the user's other task. No configuration changes, castle switches,
resource actions, messages, YOLO, or trained detectors were introduced.

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
