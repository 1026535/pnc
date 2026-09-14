# Non-YOLO recognition implementation

## Current continuation — September 13, 2026

The implementation resumes the handoff in the existing dirty worktree at
`codex/non-yolo-recognition-continuation`, HEAD `93798a64de73538c8992c953b7394598468911f9`.
Initial branch/HEAD and the expected 29 modified tracked files plus untracked
implementation assets were verified. No reset, clean, checkout replacement or
merge was performed. The user subsequently authorized the review corrections
before pushing this existing branch. The historical first-slice results below
do not describe this continuation's acceptance.

The [reconciled checklist](PNC_NON_YOLO_RECOGNITION_REMAINING_CHECKLIST.md)
records the producer contracts, captured positives/negatives, and outstanding
consumer and independent-evidence gates. Implementation and offline verification
must be distinguished from promotion or combined-main workflow acceptance.

### Changed behavior

- Both observation-publication paths resolve independent visual screen/layout
  and foreground guards before ordinary semantic enrichment. Whole-capture OCR,
  unsupported-viewport fallback, unowned OCR screen discovery and diagnostic OCR
  are removed. Frame-bound OCR rejects full-capture requests; approved header,
  field and list-body crops preserve native offsets and cache identity.
- Measured visual controls retain current frame, source screen and layout.
  Content publishes canonical non-actionable labels, fields and rows; it cannot
  invent controls or replace independent identity. Missing or conflicting facts
  abstain while preserving unrelated independent facts. Unknown/gap reports reuse
  acquired OCR and also work when no OCR was performed.
- Update, reconnect, Shield warning and safe generic negative controls require
  current panel edges and measured button geometry. Their layout provenance is
  published only after qualification. Missing panel/button is unresolved, with no
  click rectangle recovered from OCR padding. Other known modal families require
  their visual profile. Loading uses publisher/actual game-start anchors or
  near-black pixels; the captured commercial offer is a loading negative despite
  its filename. Once loading is proved and the foreground guard has run, Builder
  now stops before unrelated selector OCR, matching Navigation's passive output.
- Alliance compact/tabbed home, member/reinforce rows, leader/ordinary Manage,
  Hall and remote Gear profile now have assets, annotations and captured tests.
  Row parsers measure complete cards and their own actions, reject clipped rows,
  and read names only in the owned fields. The remote exact name does not depend
  on the Mail control remaining visible.
- Farm detail/construction, centered Build Queue and Institute upgrade-detail
  facts are qualified from saved captures in both paths. The Institute's actual
  prerequisite Go is distinct from the lower Builder Set Go; satisfied or erased
  prerequisite controls cannot publish unmet facts. APK 5.0.203/233 source confirms
  that distinction in the updated building-upgrade reference note.
- Selected-castle name refinement uses a bounded single-line field from the
  existing roster locator. Both saved core replays publish exact `0 sticker NPC`
  for selected K157, level 15. `0 stickerNPC` remains unequal. No fuzzy matching,
  alias, target rewrite, account/castle switch or core-worktree edit was added.
- Compose reads only its requested recipient/subject/body interiors after
  independent layout proof. A bounded single-line body refinement preserves the
  captured `Recognition validation - no action needed` exactly, including spaces
  and punctuation. World Map reads its canonical coordinate crop and
  the existing coordinate-rejection status field, without bottom-HUD/navigation
  OCR. The measured magnifier now publishes the existing Search action
  selector; coordinate text remains a label.
- The final crop audit removes unused Campaign stage and Castle/Warehouse/Goddess
  body scans. Castle's numeric field uses one named RGB enlargement within its
  measured 97×40 reference crop; `17145` is never coerced into `17/45`.
- A fresh `3xx_spies` roster exposed a complete selected eighth card below the
  previous OCR viewport. The roster text-column crop now reaches that card's
  name and level. Both production replays recover exact selected K303/level 5;
  current-frame identity is still withheld when a required name is missing.
- The actual wide Alliance invitation has independent portrait/message identity
  and only a current measured Cancel control. The older invitation appearance
  shares that footer layout and no longer uses Cancel as an identity anchor.
  Erased identity, erased Cancel and foreign unresolved interruptions remain
  explicit negative tests; compact-modal geometry was not widened.
- The unjoined Alliance landing now has independent Odin/banner identity. It
  publishes `PNC_ALLIANCE_JOIN` without controls or content OCR, restoring the
  existing consumer's explicit not-joined stop.
- Review corrections move coordinate K/X/Y reads into the accepted-layout
  content stage shared by both paths. Passive navigation performs only the
  foreground guard read. Missing visual identity prevents field acquisition;
  a missing X field preserves the dialog, K/Y and measured controls.
- Each castle-name diagnostic now identifies its own roster row, so a later
  successful row cannot conceal an earlier missing name in the gap sidecar.
  Compose propagates the caller's field set through acquisition and publication;
  a subject-only request performs exactly the guard and subject backend reads.

### Verification record

The subsequent code review reproduced three defects: missing coordinate fields
in Navigation content, castle-name diagnostic collisions between rows, and
Compose reads exceeding the requested field set. All three corrections now pass
focused and full portable validation. The 2,048-test result below is retained as
the earlier pre-review gate; the final gate runs 2,052 tests.

The repository Python is
`C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe` (`py` is not
installed). Portable tests used `tools/run_tests.py`; named unittest modules
were used only for focused regressions.

- Post-review focused validation passed **25 tests, no skips**, in 57.342 seconds:
  `python -m unittest tests.integration.vision.test_coordinate_dialog_local_fixtures
  tests.integration.vision.test_coordinate_dialog_observation
  tests.integration.vision.test_castle_identity_captured_fields
  tests.integration.vision.test_mail_compose_captured_fields -v`.
  The log is `.local-data/reports/non_yolo_review_fix_focused.log`.
  Independent actual-RapidOCR replay also confirms both June 13/14 coordinate
  captures through both paths. Subject-only Compose uses exactly two backend
  crops. The row-gap replay passes with the production artifact collector
  configured, preserving the missing first row despite later successful rows.
  Its initial harness omitted that optional collector; the corrected probe and
  regression now check the actual emitted sidecar, not absence from an
  unconfigured exporter.
- The final post-review `tools/run_tests.py affected --base origin/main
  --explain --json .test-impact/non_yolo_review_fix_selection.json
  --results .local-data/reports/non_yolo_review_fix_results.json` **passed**.
  The required fallback selected **290/290 modules with 60 fallback reasons**:
  **2,052 tests run, 2,046 passed, six skipped, zero failures/errors**, in
  383.735 seconds (392.260 seconds including selection/reporting). The log is
  `.local-data/reports/non_yolo_review_fix_full.log`. The six skips remain five
  unavailable optional screenshots and one Windows symlink-privilege case.
  The 58-profile catalog, packaged assets and packaging configuration were
  unchanged by these review corrections; their installed-asset qualification
  below remains applicable. No live validation was needed for these parser and
  diagnostic corrections.
- The handoff's 108 failures and 11 errors were triaged, not accepted as a
  baseline. `.local-data/reports/vision_failure_triage_continuation.md` separates
  captured production regressions, unfinished asset/interface wiring and obsolete
  OCR-only identity setups. Parser assertions were preserved at explicit semantic
  seams and actual captured tests prove production identity/control ownership.
- Focused gates include 92 shared contract/navigation tests, 61 captured-overlay
  tests, 56 core-vision tests, 18 building tests, 15 Alliance capture tests,
  12 coordinate/Institute tests, and exact castle/profile/Compose regressions.
  Individual command outputs are under `.local-data/reports/`.
- The initial affected full fallback ran 2,025 tests with 15 failures, three
  errors and six skips; it exposed remaining setup/contract migrations and was
  not accepted. A later vision group ran 585 tests with one legacy Compose
  parser-test error and five skips. The field assertions were preserved while
  correcting that test's canonical parser invocation; the subsequent focused
  World status/Compose/review-control gate passed 14 tests.
- The pre-review offline gate **passed**: `tools/run_tests.py
  affected --base origin/main --explain` selected its required full fallback
  (**290/290 modules, 60 fallback reasons**). It ran **2,048 tests: 2,042 passed,
  six skipped, zero failures/errors**, in 408.579 seconds (418.949 seconds
  including selection/reporting). Results and selection are recorded in
  `.local-data/reports/non_yolo_completion_verified_results.json` and
  `.test-impact/non_yolo_completion_verified_selection.json`; the complete log
  is `.local-data/reports/non_yolo_completion_verified.log`.
  Five skips are optional unavailable local screenshot fixtures; one is the
  host's missing Windows symlink privilege. No equivalent second full run was
  needed for that source state. Saved real-RapidOCR reports cover both paths,
  exact required fields and backend crop bounds; no broad-OCR comparison
  baseline was rerun.
- Before the final unjoined-Alliance identity addition, affected selection used
  its required full fallback (**289/289 modules, 59 fallback reasons**) and ran
  **2,045 tests: 2,039 passed, six skipped, zero failures/errors**, in 354.163
  seconds (361.850 seconds including selection/reporting).
  `.local-data/reports/non_yolo_integration_verified_results.json` preserves that
  result. The final gate above includes the subsequent asset addition.
- The pre-final-crop affected full fallback passed **2,033 tests, six skips,
  zero failures/errors** in 329.027 seconds (336.261 seconds including selection).
  `.local-data/reports/non_yolo_final_verified_results.json` records that result.
  The subsequent Campaign unused-body regression passed 19 tests. These are
  intermediate passing gates; the final gate above includes the later
  numeric-field/roster corrections.
- Final Loading/invitation/metadata focus: **15 tests passed** in 15.522 seconds.
  The new captured bottom-roster tests and existing exact K157 tests also passed;
  the combined interim run's only failures were the then-unreconciled invitation
  layout identity, which the final focused gate resolves.
- The final unjoined-Alliance landing profile restores the identity required by
  the existing `open_alliance_home` consumer. Independent Odin/banner anchors
  publish `PNC_ALLIANCE_JOIN` with no actions or content OCR. Both real-RapidOCR
  paths use exactly one global guard crop, and the consumer produces its intended
  not-joined error. Captured landing tests passed **3/3**, metadata tests **3/3**.
- Real RapidOCR confirms **12/12 base-building records** (Castle/Warehouse/Goddess,
  both viewports and both paths), and **12/12 postfix 3xx records** (six captures,
  both paths). That earlier snapshot included onboarding abstention; the final
  `independent_recognition_3xx_spies_alliance_landing_qualification.md` supersedes
  it with **2/2 passed** exact landing identities and the existing consumer stop.
  None of these correction references is independent accuracy promotion.
  Reports: `building_base_profiles_replay_20260913.md` and
  `independent_recognition_3xx_spies_postfix_qualification.md` under
  `.local-data/reports/`.
- Final installed-package qualification passed outside the checkout under Python 3.13:
  **58 profiles, 58 source images, 200 anchor/control assets and six selector
  assets**. Catalog/selector-registry bytes match checkout and wheel. The wheel
  SHA-256 is `12264efdbd408fe999b3f7e41c4f634480e654e90235670b53471a95c720b9db`.
  The fixture audit verifies **90 manifest samples and 43 manual annotations**,
  including source hashes and dimensions. Detailed commands are in
  `.local-data/reports/vision-wheel-qualification_final58.md`. The prior 57-profile
  report is retained as an earlier snapshot.
- The pre-review `git diff --check` passed. Branch and HEAD then remained the handoff values;
  no navigation, automation-workflow or core-infrastructure production diff was
  introduced. The post-review affected gate above covers the corrections.

### Delivery scope

The user authorized committing and pushing the corrected implementation on the
existing feature branch. The audited delivery contains 209 files: the existing
84 modified tracked files and 125 new implementation, asset and test files.
Generated artifacts and test-selection output remain ignored. No worktree or
branch was recreated and no merge was performed. The exact delivery commit and
remote verification are recorded in `.local-data/reports/non_yolo_delivery.json`
after push; the acceptance gates below remain open.

### Remaining acceptance

A owns the exact castle target/journal reconciliation, the World Map
dialog-opening edge's Search selector, Research idle-queue eligibility and the
documented Campaign/Gathering/receipt contracts. The existing navigation-core
test adaptation was preserved and extended only for the bounded guard plan,
layout-aware test doubles and actual captured update pixels; it requires
integration review. No navigation/core/workflow production behavior was edited.

The initial authorized independent-capture attempt failed at the launcher's
`mCurrentFocus` parsing. A later canonical read-only capture proved the launcher
state; opening the configured game through `session.launch_app()` allowed the
normal foreground checks to succeed. No core runtime parser was relaxed. The
final bounded session on `3xx_spies` completed 11 inputs (one launch and ten
inspected navigation/dismiss inputs), returned to Home and released its lease.
Including the earlier interactive scope, fourteen inputs were dispatched: two
configured launches and twelve inspected navigation/dismiss inputs. Expired
frame proof refused input; the harness required a fresh capture and review.
No spending, joining an alliance, account/castle switch, send, dispatch, research
start or upgrade occurred. Scope cleanup preserved pre-existing instances and
closed the instance started by this phase.

Fresh Settings pixels report build **5.2.77 / 5.0.201.227**; this is distinct
from the source APK and earlier capture builds. The active K303 castle is level
5 and has no Alliance membership. Independent member/Manage/Hall/profile
holdouts therefore remain unavailable on that active target. Captures are under
`.local-data/artifacts/independent_recognition/20260913T234148Z/`; actual replay
results and the earlier failures are reported separately. The failed bottom-row
case becomes regression/reference evidence after its correction; it is not
relabelled a passing independent accuracy result. Combined-main workflow and
the remaining independent-evidence acceptance gates remain open.

A delegated agent accidentally created one untracked helper in the main
checkout at `tests/support/pnc/capture_vision/modal_overlay.py`. Its intended
implementation is in this worktree. Automatic approval review rejected deleting
the misplaced main-checkout file because it is outside this task's worktree;
specific cleanup permission has been requested. No other main-checkout edits or
core-task worktree edits are part of this continuation.

## First remaining-plan slice — September 13, 2026

The reviewed remaining-work plan was committed as `f3b88f774722a950ae3069a5a516adce9f78d051`
and pushed to `origin/codex/non-yolo-recognition-continuation`. Its parent and the
validation base are main commit `850bdb747be79bb78363b8dca49a0097c6ed6546`.
The implementation described here was prepared on that plan commit and subsequently
reviewed with the corrections below. It starts the plan; it does not complete or
promote the full correction.
The [remaining checklist](PNC_NON_YOLO_RECOGNITION_REMAINING_CHECKLIST.md) records
working contracts, reproduced gaps and captured variants awaiting qualification.

### Producer contract and changed owners

- `observation_provenance.py` owns registry-declared, OCR-only label selection.
  `selector_registry.yaml` explicitly classifies the building level as a label.
  `observation_builder.py`, `navigation_perception.py` and
  `pnc_observation_enricher.py` reuse this rule. On the independently identified
  Institute capture, both real production paths publish the existing `8/45` label
  with native bounds, current frame and source screen/layout. It has no action point
  or identity authority. Existing visual proof wins a collision; foreign frame/layout
  and mismatched selector keys are rejected. Blocked/unknown observations and
  navigation with `include_content=False` do not gain content labels. Generic Farm
  still lacks independent visual identity and retains its existing navigation abstention.
- `core/vision/ocr/ocr_service.py` retains immutable results alongside read diagnostics,
  including cache/reuse outcomes. Existing cache semantics and native-coordinate
  projection remain unchanged. The shared artifact collector moved from the builder
  to `vision/observation_diagnostics.py`; the old builder import remains available.
  It exports acquired lines without requesting OCR. Both production paths reach the
  same gap reporter for unknown decisions, unresolved guards and recorded terminal
  missing/error reads, including zero-read unknown frames. Reports retain capture,
  profile, decision, attempted-region and result evidence. Ephemeral captures retain
  in-memory diagnostics without claiming a saved report. Successful retries are not
  reported as remaining missing reads.
- New regressions are `tests/integration/vision/test_content_label_publication.py`,
  `tests/integration/vision/test_observation_diagnostics.py` and
  `tests/unit/core/vision/test_ocr_diagnostic_snapshot.py`. They exercise production
  registry/recognizer/selector-engine paths and controlled OCR, provenance/overlay
  negatives, existing visual-proof precedence and zero additional exporter reads.
  Labels are parsed from OCR evidence rather than injected into the tested observation.
  Luna xhigh agents implemented bounded publication/tests/checklist slices; root
  reviewed them and implemented the shared diagnostics and compatibility correction.

### Review corrections

- The new consumer regression first reproduced four failing cases: label taps and
  label text-focus requests through each production observation path. Clearing the
  action point had allowed the executor to tap the label's center. The user's request
  to apply this finding authorized a narrow correction to A's `action_executor.py`:
  its selector input validation now rejects canonical `LABEL` metadata before
  geometry fallback, frame authorization or input accounting. Both input forms fail
  without taps/text or consumed input proof; a measured Development control remains
  usable from that same frame. No mutation authorization/journal or workflow behavior
  was redesigned; A retains ongoing ownership of this boundary.
- Luna xhigh corrected `ocr_region_plan.py` to use the existing planned-read identity
  for both missing and successful diagnostics. The collector therefore clears a
  recovered planned miss without parsing a second string convention. Regressions
  invoke `execute_ocr_region_plans` for a caught backend error followed by success,
  an unrecovered empty result, and a different unresolved fact at the same bounds.
  Root reviewed the patch and required the isolation test to preserve actual cache
  behavior. No recovery action, OCR retry policy or diagnostic schema was added.

### Offline validation

Commands ran in `.local-data/worktrees/non-yolo-recognition-continuation` with
`C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe`:

- `tools/run_tests.py group unit.core.vision`: **46 passed**.
- `tools/run_tests.py group vision --results
  .test-impact/recognition-first-slice-vision.json`: **498 run, 493 passed, five skipped**,
  zero failures/errors, 101.072 seconds.
- The first affected/full fallback found four existing guard-contract errors because
  label publication had been made mandatory for content-only guards. The correction
  makes registry-backed label publication an optional typed capability. A's runtime,
  workflow and contract tests were preserved. The four affected tests plus all four
  new publication tests then passed: **8 passed**.
- Pre-review `tools/run_tests.py affected --base origin/main --explain --json
  .test-impact/recognition-first-slice-final-selection.json --results
  .test-impact/recognition-first-slice-final-results.json`: full fallback selected
  **274/274 modules; 1,943 run, 1,937 passed, six skipped, zero failures/errors**,
  189.831 seconds (204.207 seconds including selection/reporting). Log:
  `.local-data/reports/recognition-first-slice-final.log`.
- Review fixes: `-m unittest tests.integration.vision.test_content_label_publication
  tests.unit.app.automation.engine.test_action_tap_targets
  tests.unit.app.automation.engine.test_action_text_and_channel
  tests.unit.app.automation.engine.test_mail_text_input`: **17 passed**. The new label
  denial test failed in all four builder/navigation and tap/text-focus combinations
  before the executor correction, then passed with its valid-control check.
- Luna's focused diagnostic module: **12 passed**; OCR-region-plan module:
  **nine passed**. Root inspected the final producer and regression changes.
- Final review-fix acceptance: `tools/run_tests.py affected --base origin/main
  --explain --json .test-impact/recognition-review-fixes-selection.json --results
  .test-impact/recognition-review-fixes-results.json` selected the full portable
  fallback, **274/274 modules; 1,947 run, 1,941 passed, six skipped, zero failures/errors**.
  Test time: 154.804 seconds; total including selection/reporting: 163.772 seconds.
  Log: `.local-data/reports/recognition-review-fixes-tests.log`. Refreshed main base
  remained `850bdb747be79bb78363b8dca49a0097c6ed6546`. This validates the complete
  first-slice implementation and both review fixes together.
- Changed Python files compiled; `git diff --check` passed. No assets changed, so a
  new installed-package asset check was not required. No live test or game action ran.

### Remaining acceptance

Zero **additional** OCR during export is now verified; zero full-screen OCR across
the production pipeline is still outstanding. Shared guard/content region migration,
explicit required-field gap coverage, independent visual qualification and remaining
captured-contract dispositions must be completed without dropping working facts.
Research and other retained controls passed the offline suite; they were not rebuilt.
No YOLO/shadow, workflow, route, runtime composition, mutation authorization or journal
code changed. The explicit executor label denial is documented above. This result
includes the recorded main baseline, not later main commits.
A retains future combined-main/workflow integration acceptance and both sides of
overlapping contract tests. The plan remains **promotion_ready: no**.

## Capture update — September 13, 2026

The user's separately authorized exploration captured the previously missing
Research categories, construction, Campaign Hero Formation/battle/result, ordinary
gathering receipt, Player Mail Compose, Alliance member/Hall variants, and native
account UI. The [capture findings](PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md) record
exact evidence, spending, remaining dependencies and source-backed layout rules.
K157 was shielded before leaving Lost City; the original castle was returned Home
and the live reservation released. The K290 comparison confirms the Faction tab's
absence and resulting Alliance layout shift on a nonparticipating castle.

These captures close evidence gaps only where explicitly identified. Newly
evidenced producers still require implementation and both-path offline validation;
the published release and its checks below remain unchanged. In particular,
available march-slot count, a sent-mail receipt, and the legacy Login/Continue
contract are not proved by unrelated troop-capacity, Compose, or native SDK frames.

### Working-tree corrections after the capture audit

- Player Mail Compose now has an independent visual control at reference point
  `(98, 896)` on 540×960, or `(163, 1493)` on 900×1600. Both production observation
  paths preserve template, current-frame, screen and layout provenance; missing
  controls, other mailboxes and blocking overlays abstain. The sanitized reference
  and derived negative share one capture group and are not independent holdouts.
- The generic building-detail builder now invokes the existing shared level parser.
  This restores observed `1/45` and `7/45` labels without another parser or changes
  to satisfied/unmet requirement semantics. A real production-registry builder test
  covers the publication. NavigationPerception still requires independent visual
  identity and does not publish parsed label elements in its control-only result;
  the regression preserves that abstention. This is not complete both-path building
  qualification and does not change that navigation contract.
- Root review corrected the overlay regression's viewport so the background level
  actually lies in its eligible region. Final focused command:
  `python -m unittest tests.integration.vision.test_visual_selector_scope
  tests.integration.vision.test_building_confirmation_observation
  tests.integration.vision.test_building_requirements_observation` — **22 passed**.
- The initial affected run had one error in the old blank-image Compose consumer
  fixture. The user authorized its narrow test-only correction after review. Luna
  applied the captured fixture and canonical visual recognizer; root reviewed the
  diff. All 11 consumer-module tests pass, including the actual measured dispatch
  at `(163, 1493)` through the fake actuator. No production behavior was weakened.
- Final `python tools/run_tests.py affected --base origin/main --explain --json
  .test-impact/compose-review-fix-selection.json --results
  .test-impact/compose-review-fix-results.json` passed the full fallback:
  **1,925 run, 1,919 passed, six skipped, zero failures/errors**, 121.761 seconds
  (128.835 seconds including selection/reporting). Log:
  `.local-data/reports/compose-review-fix-tests.log`. `git diff --check` passed.
- Test base resolved to `0ecb242fbae46ab48b71d26dc5fb91b5a49fe1ef`; tested source is
  dirty on HEAD `274da71`. Main has two additional commits since the integrated
  `5135dde` baseline (startup waiting and castle targets). This run is not combined
  main acceptance. No Git mutation was made during this phase. New installed-wheel
  and warm/independent-family qualification remain outstanding.

## Resumed vision component release — September 12, 2026

Worktree: `.local-data/worktrees/non-yolo-recognition-continuation`, branch
`codex/non-yolo-recognition-continuation`. Checkpoint `e3b388f` preserves the
previous dirty Gathering/March/Campaign slice; `6915b2f` includes current main
`5135dde` and revised whole-component plan `1c67745`. Historical worktrees remain.

### Concrete corrections and producer contract

- The retained Gathering selected-node and populated/empty March profiles publish
  only their independently matched Gather/Dispatch controls. Slots and a correlated
  dispatch receipt remain unknown.
- Real RapidOCR splits the map's chapter badge `10` from `Grandia Ruins`; enrichment
  now associates the exact tokens only inside the measured chapter row. The stylized
  stage `3` is absent from actual full-frame and crop OCR. Its independently matched
  unlocked badge now supplies `PNC_CAMPAIGN_MAP_REGION_NODE`; the existing Chapter
  parser uses that evidence with the exact header to publish the measured stage row.
- ObservationBuilder now supplies preliminary canonical visual controls to content
  enrichment, matching NavigationPerception. Final decision, guard, and frame binding
  still own publication. Owned Close geometry is passed to the existing global visual
  popup exclusion logic; another unowned close or a semantic blocker still abstains.
  `recognize_guards` accepts additive optional `owned_dismiss_bounds=()`; existing
  no-visual calls and public builder/perception constructor/build signatures are retained.
- Initial selector probes are intersected with registry screen ownership only after a
  clear actionable visual decision. This removes the observed unrelated World-coordinate
  OCR pass on Mail. Unknown, ambiguous, unreviewed and nonvisual cases retain broad
  fallback. Global popup/loading OCR runs before this optimization.
- Chapter and Stage rows retain current-frame, source-screen/layout, measured row/action
  bounds and provenance in both production paths. No Campaign mode, battle preparation,
  resource eligibility or mutation success is inferred. Challenge remains an action,
  not an automatically safe navigation edge. Its geometry has one visual-profile owner.
- Hero Hall now has a separate `PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON`, matched
  from the visible gold `Free Recruit 1x` artwork. The existing generic Recruit 1x
  selector keeps its meaning. Bag's existing `PNC_BAG_SUBTAB_RESOURCE` is also
  published through the visual path when its gold selected-state anchor matches.
  Both reuse canonical guarded publication; neither adds a parser or workflow caller.
  These facts establish visible control state, not cooldown policy, successful
  recruitment, or a way to navigate from an unselected Resource tab.

### Evidence and validation

- Actual saved-frame RapidOCR replay exposed and then verified the Campaign corrections.
- Focused Research/tree/queue/upgrade-warning regressions: 37 tests passed.
- Installed wheel: built with isolated build dependencies, installed under ignored
  `.local-data/qualification/installed-final`, and imported outside the checkout. All 39
  profiles and 343 selectors load; packaged Chapter/Challenge/Gather/Dispatch and
  Hero Free/Bag Resource anchors recognize their fixtures. Wheel SHA256:
  `ca456f7b78ac7095b826a4c12a2b500d40ffd662c62190db4614f632ff242696`.
  Initial builds without setuptools/network failed; the isolated network-enabled build passed.
- Five paired warm Mail replays against synchronized pre-correction builder `6915b2f`
  preserved screen, guard, row count and control IDs. Median total time: 1.495s -> 0.827s;
  nearest-rank p95: 1.538s -> 1.396s. Median OCR time: 1.402s -> 0.693s; backend calls:
  2 -> 1; processed pixels: 595,674 -> 518,400. This is a local single-frame measurement,
  not broad independent family/target qualification. Full records and environment are in
  `.local-data/reports/vision-mail-scope-performance.json`.
- Focused Campaign/metadata/selector-scope tests: 20 passed. Pre-Hero/Bag repository vision
  group: 468 tests run, 463 passed and five optional-fixture skips, 54.868s.
  `git diff --check` passed. Results: `.test-impact/vision-component-results.json`.
- Required full `affected --base origin/main --explain --verbose` initially stopped
  in a workflow contract whose mocks looped after measured Gathering support replaced
  its stale unsupported-catalog assumption. The user approved the narrow test-only
  ownership exception. Unsupported-selector denial tests now explicitly construct an
  unsupported test registry; the supported Gather transition-stop test verifies one
  Gather tap and no dispatch when the destination does not change. No production
  executor/authorization behavior changed. The first completed full run had 1,913 tests,
  two further stale-fixture failures and six skips. The corrected final full fallback
  passed: **1,921 run, 1,915 passed, six skipped**, 130.625s (137.281s including selection
  and reporting). Command: `python tools/run_tests.py affected --base origin/main
  --explain --verbose --json .test-impact/vision-final-selection.json --results
  .test-impact/vision-final-results.json`. Log: `.local-data/reports/vision-final-tests.log`.
  After that run, the Hero update regression's image was tightened to retain the actual
  Hero anchors under controlled update OCR; its complete 11-test module passed again
  in 6.741s. No production files changed after full validation. Both production paths
  cover Free/paid/disabled state, selected/unselected Bag, overlays, and frame/layout
  provenance. The two corrected workflow integration modules separately passed six tests.
- Corpus qualification processed all 50 frames (31 reference, 12 validation, seven
  holdout), five warm replays per frame. All expected screen labels matched; there were
  zero wrong actionable classifications, manual-comparison failures or known-field
  recovery regressions. Only nine frames carry manual action/field annotations, so this
  is not an all-controls or all-targets accuracy claim. Independent frame contexts share
  one sequential OCR backend to avoid competing idle engine pools. The initial CLI run
  was stopped before completion; its timing wrapper lacked the new optional owned-dismiss
  argument. The wrapper now forwards it and has a production-stack regression.
  Detailed corpus diagnostics, fallback reasons, OCR calls/area/cache and per-split p50/p95
  are in `.local-data/reports/vision-component-qualification.json`. The subsequent
  Hero Free/Bag selected-tab additions passed a separate five-frame qualification,
  with five warm replays per frame and zero wrong actionable classifications,
  manual-comparison failures or known-field recovery regressions. This includes the
  independent Hero/Bag captures and update-over-Bag blocker. Results are in
  `.local-data/reports/vision-controls-qualification.json`; control-state negatives
  are covered separately by the focused production-path tests.

### Live evidence and remaining dependencies

The existing Mail Compose tool leased configured `testing`; no access to `main` or a
second instance occurred. The sandbox attempt could not enumerate processes. The first
host attempt launched PNC but checked foreground immediately and stopped with zero
navigation inputs. One follow-up after startup reached Mail, observed an empty Player
mailbox, returned Home in eight inputs, and released the reservation. Compose is an
explicit applicability skip. There was no resource spending or message send. Exact run:
`.local-data/artifacts/vision_resume_mail/20260913T015421Z_8f928e87/summary.json`.
Configured screenshots remain under the existing root `artifacts/2026-09-13/testing`;
the config was not changed to relocate them.

Remaining unproved cells are Login/account-switch controls, populated Player Mail/
Compose and send-receipt facts, non-Development Research categories, Gathering slot
count and correlated dispatch receipt, Campaign mode/preparation, and additional
building/member-only layouts. These need actual independently annotated frames;
current reference transforms do not count as held-out target/build/locale evidence.
Full-frame guard fallback is retained until independent blocker coverage supports
narrowing it. The previously authored Campaign source note and index are retained
for the plan's one-time A handover; future game-reference/workflow maintenance remains A-owned.
A owns workflow callers/routes/mutation behavior and final combined-main acceptance.

### Release disposition

The first evidence-supported B release is implemented, reviewed and offline validated.
Fresh `origin/main` remains `5135dde`; it is already an ancestor of this feature.
The new Hero Free ID is available for A's existing Daily consumer to adopt through its
normal policy/execution boundary. It does not silently replace the generic Recruit ID.
Source-hash and exact-crop checks passed for both new Hero/Bag assets, and generated
wheel/build/report output remains ignored. Historical scratch worktrees are retained.
The complete original plan is **not** marked finished: the missing capture cells above
and A's final producer/consumer integration remain required. Spending authorization
does not supply those observations or permit invented success/receipt facts.


Current continuation and ownership are in [B's revised plan](PNC_NON_YOLO_RECOGNITION_PLAN.md)
and the [shared A/B backlog](PNC_AB_COORDINATED_CONTINUATION.md). The foundation and
Research production-builder correction are now integrated in main `2eacb12`; later
combined candidate `8a7d1a9` was published and validated. Preserve the dated evidence
below; its historical pause/baseline statements do not override the resumed plan.

Feature branch: `codex/non-yolo-recognition` in `artifacts/worktrees/non-yolo-integration-current`.
Current landed baseline: `2bb3c9074d99a532018e071ed121d12e6d75cd8f` on `origin/main` (2026-09-12).
Status: implemented recognition foundation validated; remaining F integrations
and broader promotion remain blocked as itemized below. No blanket rollout approval.

## Paused checkpoint: Development research action and reconciliation (2026-09-12)

The current continuation closes the bounded Development Research action gap on the
configured `testing` target. The canonical OCR row producer identifies complete
Development nodes and derives each action point from the measured node icon rather
than its label. A reviewed detail profile exposes only the blue normal Research
button; the adjacent gold Research Now option is excluded. A separate active-detail
profile uses stable Speedup-button chrome while excluding the changing progress fill
and timer, and exposes no Speedup or cancel action.

Root first observed that a label-center tap produced no transition, then required
icon-derived action geometry. The corrected node action opened Construction I
(2/5). The normal Research action was dispatched once through the observed executor
with an exact budget of 16,400 food, 7,010 wood, and zero premium currency. The
postcondition showed both exact resource deltas, a running timer, and no Start
control. `ResearchTask.verify` now requires clear
`visual_anchor:research_tree_node_detail_active` evidence; an ordinary tree or
unrecognized same-screen frame cannot confirm the mutation.

Live source and postcondition evidence:

- Detail before dispatch: `artifacts/2026-09-12/testing/20260912T192049Z_core_20260912T183757Z_5d65bcbf_0046_research_node_detail.png`.
- Immediate active detail: `artifacts/2026-09-12/testing/20260912T201102Z_core_20260912T183757Z_5d65bcbf_0051_research_start_postcondition.png`.
- Elapsed-time regression source: `artifacts/2026-09-12/testing/20260912T202536Z_core_20260912T183757Z_5d65bcbf_0052_research_detail_reloaded.png`.
- Final active-detail proof: `artifacts/2026-09-12/testing/20260912T204123Z_core_20260912T183757Z_5d65bcbf_0056_research_detail_reloaded.png`.
- Final Home: `artifacts/2026-09-12/testing/20260912T204305Z_core_20260912T183757Z_5d65bcbf_0066_core_route_source.png`.

The active-detail profile matched both active frames despite the elapsed timer. A
single reviewed Android Back closed that proved detail, and canonical navigation
returned to clear Home. The continuous reservation completed with 15 input attempts
and 66 observations; the pre-existing instance was preserved and the lease released.
The focused root suite passed 60 tests. Gathering/March, Campaign, broader category
coverage, member-only applicability, and target/build/locale promotion remain open.
Implementation is paused at this durable checkpoint at the user's request.

The isolated worktree preserves the relevant recognition/journal baseline recorded in
`artifacts/non_yolo_recognition/isolated_baseline.json`. The original checkout is
reserved for the user's other task. No configuration changes, castle switches,
resource actions, messages, YOLO, or trained detectors were introduced.

## Development Research Tree continuation (2026-09-12)

The resumed F slice adds the first real Research Tree reference and visual producer. The Development title and independent fixed Master Researcher icon must both match; scrollable research nodes are not identity anchors. The profile exposes only the independently matched top-left Back control, reusing the measured Institute arrow. Catalog v3 provenance and manifest v2 retain `guarded_reference_only` qualification. The three live source frames are correlated evidence, not independent accuracy measurements or qualification of other categories, builds, locales, or accounts.

Live exploration first reproduced `UNKNOWN` on three Development frames. Root reviewed the source screenshot and crops; replay then matched all three native 900x1600 frames and abstained when either identity anchor was removed. A fresh production observation identified Research Tree and exposed only Back. One canonical Back tap returned to unblocked Institute in two captures, establishing the two added graph edges: Institute Development to Research Tree, then Research Tree Back to Institute. The graph replay confirmed Development entry and return through Institute to Home. No category other than Development was entered, and no node, Research Start, resource action, message, or castle switch was attempted.

The complete scoped testing phase passed with exact current-castle preflight, 13 inputs and 49 observations in 965.224 seconds, within the 24-input/1,200-second budget. Elapsed time includes waiting under the same lease for implementation and review. The configured smoke-test target pre-existed, its lease was released, and it was preserved at visually inspected Home. Command: direct Python 3.13 `-u .local-data/reports/non_yolo_research_tree_20260912/probe.py`, with reviewed `qualify_return` and `verify_graph` commands inside the existing reservation. Summary and trace remain beside the probe.

- Source tree: `artifacts/2026-09-12/testing/20260912T180007Z_core_20260912T175539Z_09c5f27b_0034_development_evidence_1.png`.
- Qualified tree: `artifacts/2026-09-12/testing/20260912T180840Z_core_20260912T175539Z_09c5f27b_0036_qualified_development_tree.png`.
- Confirmed parent: `artifacts/2026-09-12/testing/20260912T180851Z_core_20260912T175539Z_09c5f27b_0038_tree_return_1.png`.
- Graph entry: `artifacts/2026-09-12/testing/20260912T181113Z_core_20260912T175539Z_09c5f27b_0042_core_9_after_1.png`.
- Final Home: `artifacts/2026-09-12/testing/20260912T181142Z_core_20260912T175539Z_09c5f27b_0049_core_11_after_1.png`.

Research rows, eligibility, Start, and mutation reconciliation remain unsupported and unproved. Gathering/March, Campaign, member-only applicability, independent corpus coverage, and target/build/locale promotion remain open plan gates. This increment closes Development identity and safe navigation only.

Bounded checks passed: 65 navigation/registry tests, then 10 Development visual-control/metadata tests. The latter cover reviewed scales, missing identity/control anchors, the Institute negative, blocking-update ownership, current/foreign frame dispatch, and unsupported Start. `tools/validate_navigation_selectors.py --config C:/Users/lebel/pnc/config/accounts.yaml --account testing --selector PNC_INSTITUTE_DEVELOPMENT_BUTTON --source-screen PNC_INSTITUTE --output-dir .local-data/reports/non_yolo_research_tree_20260912/selector_canary` failed before connection because the older canary allowlist does not include this core route. Its gate was preserved; the successful canonical core graph probe above is the relevant live validation.

The increment was committed as `a557ae9`, then synchronized with freshly fetched main `69ae648` by merge `e376fed`, preserving shared history. Main's authored Open Building port uses the existing strict core endpoint contract; its host-safety update centralizes host binding validation, hardens lease cleanup, rejects identity replacement during startup, and prevents capture-file collisions. There were no overlapping recognition edits or merge conflicts. The combined catalog retains 32 profiles/27 screen types and the graph has 48 edges. The final 32 recognizer/benchmark tests passed; Luna also passed the added graph contract and focused Research/metadata tests.

Combined live boundary proof passed: `-u .local-data/reports/non_yolo_research_tree_20260912/combined_readiness.py` acquired the configured testing reservation and produced two clear Home captures with zero inputs in 20.375 seconds. The pre-existing instance was preserved. Final capture: `artifacts/2026-09-12/testing/20260912T181849Z_core_20260912T181839Z_f816a640_0002_combined_home_1.png`; `combined_readiness_summary.json` and trace are beside the probe. This checks the merged lease/artifact/perception boundary; it does not claim an additional Research route replay.

Final combined validation passed: direct Python 3.13 `-u tools/run_tests.py full --json .local-data/reports/non_yolo_research_tree_20260912/full_selection.json --results .local-data/reports/non_yolo_research_tree_20260912/full_results.json`, **1,763 tests with five optional local-screenshot skips**, 141.051 test seconds/147.261 total. Tested commit `e376fed`; source fingerprint `58304461dca1860f8090dd7c5aeadd8f27df3387810712e5a81a9444b1e39c91`. Only this plan/report ledger changed after that run. `git diff --check` passed. Root reviewed Luna's profile, crops, graph, provenance and regressions; no actionable finding remains in this bounded increment. The older canary limitation and broader plan gates above remain explicit.

## Authorized main landing gate (2026-09-12)

Landing completed: the combined candidate was fast-forwarded from freshly fetched main `e4eb8b5` in a clean detached landing worktree, pushed without rewriting history, and verified on `origin/main` at `2bb3c90`. The current feature worktree is now checked out on `codex/non-yolo-recognition`, with the same commit published to its remote. The historical dirty worktree remains untouched on `codex/non-yolo-recognition-preserved-20260912`; the root checkout's unrelated local commit was preserved. Subsequent mainline work is independent of this completed landing.

The user authorized landing the feature to main and continuing on `codex/non-yolo-recognition`. Fresh main `e4eb8b5` adds workflow reservation isolation, strict claim reconciliation, complete Daily viewport processing, bounded coordinate samples, and portable shutdown-test discovery. The Daily coordinator merge removes the now-unused `_has_pending_rows` helper while retaining `RowRecognitionStatus.COMPLETE` in both active claim and action selection. No resource-changing behavior was exercised live.

Validation passed: 31 targeted API/Daily/coordinate tests and full portable suite, 1,744 tests with five optional local screenshot skips (167.934 test seconds; 174.586 total). The initial targeted command used the wrong API module path and failed import; the corrected `tests.integration.entrypoints.test_automation_api_runner` command passed. Full command: `tools/run_tests.py full --json .local-data/reports/non_yolo_gap_20260912/landing_selection.json --results .local-data/reports/non_yolo_gap_20260912/landing_results.json`. Tested source fingerprint `f10907cbdd677a20b2b59e675bbefdcd9fe93f5dcb9c52441d18c30527520e39` matched the combined code before this documentation update.

The combined runtime passed a scoped testing-instance proof: exact current-castle preflight, six complete Bag entries, and final Home with seven inputs/31 observations in 214.297 seconds. No Use taps, spending, messages or castle switches. The instance pre-existed and remains at Home. Bag artifact: `artifacts/2026-09-12/testing/20260912T174339Z_core_20260912T174056Z_11c1f869_0026_bag_content_proof.png`; Home: `artifacts/2026-09-12/testing/20260912T174419Z_core_20260912T174056Z_11c1f869_0031_core_route_source.png`. The prior publication's exclusion of workflow-safety commits is superseded by this integration. Remaining F producer/evidence gaps are unchanged and will be resumed after landing.

## 2026-09-12 publication: navigation gaps, startup, and Bag confirmation

Authoritative worktree: `artifacts/worktrees/non-yolo-integration-current`, published to `origin/codex/non-yolo-recognition`. This increment integrates main through `87e6151` (building focus, popup vectorization, offline-test improvements, and Castle endpoint). Main subsequently advanced independently to `4b63bd9` with workflow safety; that later change is not included or claimed validated here. This is feature publication, not landing to main.

Five missing graph selectors are registered without guessed geometry and live-confirmed: More Rank, Settings Rank, Settings Preferences, Settings Notifications, and World HUD Toggle in both directions. The final graph includes 46 edges after the upstream Castle return edge; registry support remains 336 selectors with 56 explicitly unsupported controls. Planned maturity and independent visual/frame proof remain required.

The audit handoff's resource numeric fixes were already present in the canonical `numeric_parsing`/resource parser. Added only missing regression cases combining decimal/grouped amounts with OCR glyph repairs (`1.5K Fo0d` and `1,500 Wo0d` remain 1,500), plus malformed count/amount cases. The publisher splash profile was missing: two measured logo anchors at 0.95 now identify passive loading, expose no controls, and abstain when either logo is absent. Tests cover 540x960 and 900x1600; this is reference qualification, not independent broad accuracy.

The upstream Castle profile retains its anchors and measured Back unchanged. Its metadata is migrated to catalog v3, and its manifest entry uses the canonical decoded-image digest. The existing clear `castle_aug25.png` validation frame now correctly expects Castle recognition. No duplicate legacy samples were imported. Final catalog: 31 profiles, 26 distinct screen types.

The exact previously failing Bag screenshot now produces six complete resource entries through both `NavigationPerception(include_content=True)` and `ObservationRequest.source_screen_retry(PNC_BAG)`, using the production OCR pipeline. No new parser owner or threshold adjustment was needed. Fresh live confirmation after integration through `39ce6fc` reproduced all six entries, verified current-castle identity, and returned Home with 7 inputs/30 observations in 108.537 seconds. No Use taps, spending, setting changes, messages, or castle switches occurred. Bag: `artifacts/2026-09-12/testing/20260912T170823Z_core_20260912T170700Z_5c128bf4_0025_bag_content_proof.png`; final Home: `artifacts/2026-09-12/testing/20260912T170845Z_core_20260912T170700Z_5c128bf4_0030_core_route_source.png`. Saved replay and live summaries: `.local-data/reports/non_yolo_gap_20260912/bag_replay.json` and `bag_summary.json`. The pre-existing instance remains at Home.

The eight incomplete main-checkout helper copies had no unique changes beyond correct feature versions already committed at `cb9a879`. After root review and Luna equivalence checks, the main-owning task preserved the exact patch at `C:/Users/lebel/pnc/.local-data/reports/main_checkout_incomplete_non_yolo_helpers_20260912.patch`, removed only those superseded copies, and fast-forwarded local main. No duplicate fixture migration commit was created. The separate offline provenance test defect was corrected using per-test temporary lease registries; both helper and direct real-session construction retain production provenance checks without contending with live instances.

Validation (direct Python 3.13 interpreter; report directory `.local-data/reports/non_yolo_gap_20260912`):

- `tools/run_tests.py group vision`: passed, 397 tests/5 optional skips.
- Navigation registry regressions: 4 passed; frame-provenance module: 15 passed.
- Main integration targeted navigation/popup/provenance group: 80 passed.
- Numeric/startup/metadata/schema/recognizer/benchmark group: 72 passed; final Castle metadata/recognizer/benchmark/navigation group: 95 passed.
- Initial full run: failed, 1,721 tests/5 skips/one real-lease fixture collision; corrected as above. Pre-Castle full checkpoint: passed, 1,735 tests/5 skips.
- Final `tools/run_tests.py full --json .local-data/reports/non_yolo_gap_20260912/castle_final_selection.json --results .local-data/reports/non_yolo_gap_20260912/castle_final_results.json`: passed, 1,737 tests/5 skips, 70.645 test seconds (72.731 total). All skips are unavailable optional local screenshots. Tested source fingerprint `115d6c64eb53bd5e13773054db7242e4d8b3b362608a67b93fbb7d5a99fdcc91` matched the final code/assets before this documentation-only ledger update.
- Legacy navigation-selector CLI: rejected before connection because its metadata/allowlist does not support these planned core semantic controls. The successful canonical core live routes provide the relevant proof; no legacy bypass was added.
- Live first combined probe: More/Settings passed; world entry exhausted an overly tight three-observation harness budget. The six-observation rerun passed both HUD directions and final Home. Production defaults and classification thresholds were unchanged.
- `git diff --check`: passed. Root review found no remaining actionable issue in this increment after Luna corrections/self-review.

The complete vision plan remains broader than this increment. Research/Gathering/Campaign producer gaps, mutation-backed postconditions, member-only applicability, and independent target/build/locale promotion remain explicit gates. This publication does not authorize resource-changing actions or claim those gates complete.

## 2026-09-12 Institute controls and live ownership repair

Current implementation worktree: `artifacts/worktrees/non-yolo-integration-current`; published integration commit `5261b1d` includes freshly fetched main `15845b8`. Earlier baseline/status entries below are historical.

The Institute profile now has four measured category controls (Development, Economy, Military, Fortification), using cropped interior anchors and bounded search regions at threshold 0.97. Its revision is 2. Existing Back, source provenance and `guarded_reference_only` qualification are preserved. The four matches scored 1.0 on the native 540�960 reference and two archived 900�1600 captures. These correlated references do not establish independent build/locale accuracy. Tests cover scaled geometry, missing-control abstention, wrong-category rejection and blocking-popup suppression. Research Start and research rows remain unsupported by this slice.

Fresh live evidence superseded the earlier launch/connectivity and busy-lease blockers. A capture-only probe leased the now-free testing instance, found it already running, and confirmed PNC at Home. The canonical More selector canary passed, verified the active castle without switching, and returned Home. The first custom core harness omitted `allowed_selector_screens`; its zero-input rejection was a harness error, not a production recognition failure. Invoking the navigation validator without required selector/account arguments also failed at CLI parsing; the complete canary invocation passed.

A subsequent fixed-route core probe verified the active castle but stopped after six navigation inputs on an ordinary idle Research Queue. The exact frame `artifacts/2026-09-12/testing/20260912T160633Z_core_20260912T160535Z_935f4b91_0023_core_6_after_0.png` and existing tracked queue fixture reproduce the issue: visual recognition identifies Research Queue and its measured Go/Close controls, while the old OCR fallback labels the same surface a generic popup with no safe close. The navigator now declares ownership only for unique visual Research Queue identity with a matched dismiss control. That proof suppresses only the queue's generic-popup fallback; all other modal/text/visual-close guards still run. OCR-only bootstrap retains its conservative fallback. No Android Back, coordinates guessed from a screenshot, or mutation selectors were added.

The first live replay of the ownership fix exposed a separate registration gap: `PNC_RESEARCH_QUEUE_CLOSE` (and Go) existed in the visual catalog and enum but not the canonical selector registry. Added both existing controls as semantic, non-geometry registrations scoped to Research Queue, retaining planned maturity. A read-only graph audit also found unresolved registrations for More Rank, Settings Rank, Settings Preferences, Settings Notifications and World HUD Toggle. Those routes are outside this Institute slice and remain explicit blockers to broader navigation promotion; no claim of complete graph actionability is made.

Validation before the ownership repair: six new/updated Institute tests passed; affected selection against origin/main ran 1,692 portable tests with five skips, all passed. The first ownership-targeted run was started before fake guard signatures were migrated and failed with keyword-argument TypeErrors; its replacement result and live outcome are recorded below. Logs and bounded probe scripts are under `.local-data/reports/non_yolo_resume_20260912/`.

Final Institute live proof passed on testing after the two fixes: exact active-castle verification, Research Queue Close/Go transitions, observed Institute entry, all four category controls, and final Home. It used 10 inputs and 37 observations in 148.918 seconds, without switching castles, starting research, spending, or sending anything. Institute capture: `artifacts/2026-09-12/testing/20260912T161804Z_core_20260912T161607Z_901ef3aa_0033_core_9_building_after_1.png`; Home capture: `artifacts/2026-09-12/testing/20260912T161829Z_core_20260912T161607Z_901ef3aa_0037_core_10_after_1.png`. Summary: `.local-data/reports/non_yolo_resume_20260912/institute_core_summary.json`. The instance pre-existed and is preserved at Home after lease release. This proves recognition and entry/return on the current target; category taps and Research Tree behavior were not exercised. The 78 targeted tests passed after mock/registry migration. Full ownership-repair suite passed 1,695 tests with five skips before the final two registry-dispatch regressions were added.

## Resumed graph registration slice at cb9a879

The five documented missing IDs are now registered as planned semantic controls without relative geometry: More Rank, Settings Rank, Settings Preferences, Settings Notifications and the World HUD toggle. Their canonical visual producers already exist in the `more_overlay`, `settings`, `world_map` and `world_expanded` profiles. The registry audit now finds 336 selectors, including the unchanged 56 explicitly unsupported controls, and no missing supported selector across the 45 reviewed navigation edges. This is registration completeness, not proof that every route works in every game state.

The review also checked eight core Back sources absent from the legacy Back detector's screen list. That list enables guarded geometry materialization, whereas the core obtains measured Back controls from the visual profiles. Expanding the list would change legacy detection behavior, so it is intentionally preserved. The new invariant checks graph selector support; the five newly registered selectors additionally require exact source declarations.

The legacy `tools/validate_navigation_selectors.py` invocation for `PNC_MORE_RANK`/`PNC_MORE_MENU` failed before connecting: planned semantic registration does not supply that older canary's navigation-click metadata, and its static allowlist does not cover the new core routes. The acceptance probe therefore uses `NavigationCore` with an allowlist derived from reviewed edges and their source screens, under one reservation, exact active-castle preflight, bounded non-spending inputs and Home after each route. Generated commands, summaries and traces are under `.local-data/reports/non_yolo_gap_20260912/`.

The first combined live probe confirmed More Rank and all three Settings destinations, with Home after each completed phase. It then exhausted its artificially tight three-observation limit entering the world map: two loading/unknown frames were followed by one correct world frame, short of the two stable observations required. No HUD toggle was attempted in that run. The follow-up uses six observations per transition under the same 45-second bound (production defaults allow eight), without loosening recognition or repeating an unconfirmed tap. Evidence: `all_summary.json` and `all_trace.jsonl` in the report directory.

The initial full suite ran 1,721 tests with five skips and one error: `test_actual_session_age_rejects_expired_frame` used the real default instance lease despite its fake ADB backend, contending with the concurrent live probe. This is an offline fixture-isolation defect, not a Windows journal permission failure; the correction must preserve the real session's age check while using the existing fake lease owner.
Final world-HUD proof passed with exact active-castle preflight, both toggle directions and final Home: 10 inputs, 43 observations, 172.497 seconds. Expanded frame: `artifacts/2026-09-12/testing/20260912T170024Z_core_20260912T165813Z_d088d7fc_0033_core_8_after_1.png`; final Home: `artifacts/2026-09-12/testing/20260912T170102Z_core_20260912T165813Z_d088d7fc_0043_core_route_source.png`. Together with the four earlier route proofs, all five newly registered controls are live-confirmed on the current testing target. No resources, settings toggles, account/castle switches or messages were used. The pre-existing instance remains at Home after lease release. This does not promote other builds, locales, targets or unrelated legacy Expand selectors.
## Main-checkout migration review

Root review and Luna xhigh's eight-file comparison found no unique uncommitted behavior to rescue from the main checkout. The intended fixture migrations already exist in committed feature `cb9a879`. `recording_selector_engine.py` and `mail/build_observation.py` are semantically equivalent; five capture/world helpers omit required frame/OCR/decision imports, and `world_map_runtime_fixtures.py` incorrectly dedents `_build_runtime_service_bundle` outside its class. The feature copies pass AST/import validation. These helpers depend on the feature's production interfaces and must not be committed independently on main. The main-owning task was given the verified disposition: preserve the patch, remove only the superseded copies during its scoped cleanup, and retain the correct migrations through the feature branch. Detailed local audit: `C:/Users/lebel/pnc/.local-data/reports/non_yolo_gap_20260912/main_checkout_review.md`.
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

The subsequent main commit `e3a7b83` was also integrated: authored popup recovery now uses the same typed lifecycle dispatch and core observation boundary. The merge applied without conflicts, retained the Research Queue ownership repair and configured OCR/classifier injection, and removed the retired legacy popup task rather than maintaining duplicate paths.

Final validation through `e3a7b83`: direct Python `tools/run_tests.py full` passed 1,717 tests with five skips (`.local-data/reports/non_yolo_resume_20260912/full_popup_merge.log`). The merged readiness and popup lifecycle methods passed on already-clear Home with zero inputs and five observations in 22.466 seconds; this is a no-popup lifecycle proof, not an additional dismissal proof. Final Home: `artifacts/2026-09-12/testing/20260912T163015Z_core_20260912T162958Z_8a53bf9a_0005_final_home.png`; summary: `.local-data/reports/non_yolo_resume_20260912/latest_popup_lifecycle_summary.json`. Fresh remote fetch still matched main `e3a7b83`; whitespace validation passed. No new actionable findings remain in the implemented Institute/queue increment and resolved merge; broader plan gaps listed above remain open.
