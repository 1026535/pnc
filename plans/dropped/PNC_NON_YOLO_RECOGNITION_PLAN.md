# Remaining screen recognition corrections before integration

> **Status: DROPPED — superseded 2026-09-15.** This is historical evidence, not an active execution plan. Use the [modular vision plan](../themed/vision/PNC_VISION_MODULAR_PLAN.md) and [replacement/retained-requirement map](../reviewed/vision/modules/PLAN_RETIREMENT.md). Historical ownership, accounts, budgets and resume instructions below are inactive. Retirement does not claim every historical defect is fixed.

Reviewed September 13, 2026 against commit 850bdb747be79bb78363b8dca49a0097c6ed6546.
This is the active remaining-work plan. Completed work and historical validation
belong in the [implementation report](../completed/vision/PNC_NON_YOLO_RECOGNITION_IMPLEMENTATION.md);
the [capture findings](../reviewed/vision/PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md) supply dated evidence.
Neither an old test result nor a captured frame proves the work below is complete.

## Outcome and scope

Finish the original screen-first approach for currently working coverage and known,
captured recognition gaps:

| Job | Required production behavior |
|---|---|
| Identify screens and blocking popups | Independent OpenCV anchors and reviewed layout/overlay evidence, independent of the caller's requested content. |
| Locate fixed controls | Measured normalized geometry or template bounds, guarded by current screen, layout, selected tab, state and overlay ownership. |
| Read names, quantities, timers, coordinates and UI rows | OCR only within reviewed semantic regions, followed by the existing canonical parsers. |

Full-screen OCR is prohibited in the completed PNC observation path, including
guards, unknown-screen fallback, selector discovery used for qualification, and
diagnostic export. This also excludes explicit whole-viewport bounds and arbitrary
tiling that reconstructs a full-screen OCR pass. OpenCV may inspect the whole image;
storing a screenshot is allowed. An OCR backend may process an entire approved crop
passed to it. The generic OCR engine API does not need an unrelated redesign.

If one requested value cannot be read, publish it as unknown/missing, preserve other
independently verified facts, and keep actions requiring that value unavailable.
An unresolved screen, layout or blocking overlay makes background actions ineligible.
Write a local recognition-gap report for later bug fixing; do not widen the OCR scan
or automatically attempt game actions to recover the missing fact.

**No YOLO transition ownership is assigned here.** Do not design or implement a YOLO
adapter, region-provider protocol, model, classes, dataset, training, evaluation,
rollout, world-object detection or associated object-label OCR. Do not modify existing
YOLO/shadow code as part of this work. Another agent owns that future plan and its
integration. Fixed world HUD coordinates and already selected-object UI panels remain
ordinary existing screen contracts; this plan adds no map-object discovery.

Retain the landed visual assets, screen decisions, frame-local OCR/cache foundation,
row provenance, Quest/Bag parsing, Research Development geometry and both-path normal
Start publication, timer-independent active-detail verification, Campaign/Gathering
producers, and corrected Player Mail Compose geometry. Rework these only where needed
to remove a demonstrated defect or full-screen OCR dependency. Do not repeat completed
Research, construction, upgrade, Campaign, gathering or shield actions for proof.

## Review findings resolved in this revision

1. **The old fallback policy contradicted the requested outcome.**
   [Region plans](../../pnc_automation/app/pnc/vision/ocr_region_plan.py) still allow full-frame
   fallback, and [capabilities](../../pnc_automation/app/pnc/vision/pnc_ocr_capabilities.py)
   register most families for guarded full-frame reuse. Even the seven region-plan
   families do not prove zero full-screen work: both guard entry points and enrichment
   in [the enricher](../../pnc_automation/app/pnc/vision/pnc_observation_enricher.py) still
   request it. Correction: migrate every proved working dependency, then enforce the
   bounded contract across both production paths; no fallback exemption for guards.
2. **Parsed content is not fully published by replacement perception.**
   [NavigationPerception.build](../../pnc_automation/app/pnc/vision/navigation_perception.py)
   retains list/scalar content but discards parsed visible elements. Building level
   is one known lost label. Correction: share explicit non-actionable label publication
   with the real builder; never merge all OCR-produced elements as clickable controls.
3. **Existing diagnostics cannot satisfy the unknown-report requirement.**
   [ObservationDebugArtifactCollector](../../pnc_automation/app/pnc/vision/observation_builder.py)
   starts a full-screen OCR read and writes nothing without unmatched lines.
   NavigationPerception does not call it. Correction: reuse the collector for recorded
   evidence and missing-fact reports from both paths, including zero-OCR unknown frames.
4. **Catalog counts and capture inventories overstated the remaining contract.**
   An enabled selector or static reference is not proved runtime coverage; a screenshot
   omission is not automatically a defect. Correction: freeze an evidence-backed list
   of working contracts and reproduced gaps. Do not invent controls to fill a matrix,
   or drop working contracts merely to reach zero full-frame calls.
5. **The draft needed a firmer integration boundary and migration order.**
   YOLO transition work is entirely excluded. Guard/content migration must precede
   final enforcement and promotion, so a global restriction does not silently turn
   currently working observations into unknowns. Workflow and execution ownership
   stays with A.

## Work packages and acceptance

### 1. Freeze the regression baseline and remaining cases

Reuse the existing coverage inventory, production callers, portable fixtures, manual
annotations and September 13 captures. Save one compact checklist alongside this plan
when implementation starts. For each required case record the screen/layout, consumer
and required facts, visual control proof, OCR regions, source frames, expected output
through each applicable observation path, negative cases and completion evidence.
Classify cases as proved working, reproduced gap, or pre-existing unsupported behavior.
An enum, planned catalog entry or static reference alone cannot promote a case.

The following captured cases must receive a contract disposition and any necessary
producer correction. Already correct behavior needs regression coverage, not rebuilding:

| Area | Bounded remaining correction or qualification |
|---|---|
| Shared navigation and blockers | Preserve currently working Home/More/Settings and other evidenced screen identities, including return-home candidate-scope negatives. Migrate known modal/loading/update/reconnect guards without allowing background actions through an unresolved overlay. |
| Research | Qualify the captured Economy/Military/Fortification variants against existing Research contracts. Keep normal blue Research distinct from premium Research Now, and visible control distinct from queue eligibility. Preserve Development and strict active-detail negative regressions. |
| Building | Publish the existing level label through both paths with non-actionable provenance. Qualify captured construction level 0/1, upgrade level 7/8, unmet requirements and active queue. A satisfied Requirement heading must not become the existing unmet-requirement blocking selector. An empty queue alone cannot prove the new level. |
| Alliance | Bind tabbed/compact layouts to current visual evidence, not map location. Correct evidenced leader/member Manage geometry and Hall Reinforce row ownership where current contracts need them; retain disabled Transport state at zero selected resources. |
| Mail and other working text fields | Preserve the corrected Player Compose entry. Read evidenced recipient/subject/body, empty/focused field state and supported mailbox rows from owned regions. Do not introduce send/delivery behavior. |
| Campaign | Preserve existing stage/chapter controls and qualify captured Hero Formation, battle/result UI only to the extent of existing producer contracts. Do not copy stage/AP/mode into a formation frame that lacks those facts. Read displayed AP cost where present; do not hard-code a global cost. |
| Gathering/March UI | Preserve selected-target, formation, active march/collection and captured report facts with their actual source/row association. Troop or load capacity is not available march slots. Recognition of a report does not by itself correlate a workflow's dispatch. |
| Remaining proved working OCR families | Migrate their required labels, numeric fields and dynamic rows, including existing Quest/Bag, Chat, profile and fixed coordinate contracts. Request only the semantic regions those consumers need. |

Use the [seasonal layout](../../docs/game-reference/workflows/seasonal-alliance-layout.md),
[gathering](../../docs/game-reference/workflows/neutral-gathering.md),
[building](../../docs/game-reference/workflows/building-upgrade.md) and
[Campaign](../../docs/game-reference/workflows/campaign-navigation.md) notes with the newer
capture findings. APK 5.0.203/233 is versioned client evidence, not proof of live
5.2.76 / 5.0.204.235 server behavior. Keep raw private account/mail captures ignored;
use sanitized minimal fixtures when tracking new evidence.

Acceptance: every required case has an observable expectation and a relevant negative.
Unobserved march-slot UI, an actual mail-send receipt, and the different native account
versus legacy Login/Continue route remain named external dependencies. They cannot be
fabricated, counted as fixed, or made reasons to implement another workflow. Future
coverage is separate; a blocked required case remains visibly blocked.

### 2. Migrate shared guards and region reads through existing owners

First add offline regressions demonstrating the unbounded reads and recording expected
facts from saved evidence. Migrate guards and their dependent content in coherent slices;
do not promote a partially migrated pipeline as coverage-preserving.

- Keep one decision sequence in both builders: validate capture provenance; establish
  ordinary base identity with blocking popup profiles excluded; if that base is
  recognized, skip popup profiles and generic modal recovery, then acquire exact
  bounded guard OCR only when compact foreground panel geometry is present; otherwise
  resolve the bounded exact guard and eligible popup work;
  read approved content regions for the permitted screen; publish guarded facts.
  Known popup profiles and generic fallback are considered only for an UNKNOWN base.
  Within that UNKNOWN branch, caller candidate scopes never suppress exact guards.
- Reuse the shared modal recognizers and canonical classifier; remove the duplicated
  full-frame acquisition/policy between recognize_guards and detect_interruption.
  Retain legitimate foreground dismiss controls and the established Research detail
  ownership rules. A missing known-popup match alone is not a clear-frame proof.
  Require reviewed positive layout/control evidence and applicable occlusion checks;
  unresolved observed occlusion stays unknown. Do not claim detection of every novel popup.
- Extend OcrRegionPlan and its compiler for the checklist's guard, header, field and
  row regions. Reuse existing parsers and typed facts. Missing text does not authorize
  wider scans, OCR-driven screen invention or approximate click boxes.
- Remove PNC full-frame fallback plans, guarded-full-frame strategies and observation
  reuse paths once their supported callers are migrated. Enforce bounded reads at the
  frame-scoped observation boundary, including unbounded preprocessed or debug calls.
  Unsupported viewport/layout produces unknown plus diagnostics without OCR fallback.
- Preserve native-frame offsets exactly once, immutable capture validation, successful
  empty-result caching, and cache separation by crop, preprocessing and backend revision.
  Retain the coordinate-only read contract: a bounded coordinate result does not grant
  screen/action eligibility. Navigation include_content=False remains content-free.

Acceptance: both production paths pass the migrated positive/negative cases without a
whole-viewport OCR request. Expected region assertions prove semantic cropping on the
fixtures; a backend spy proves the actual crop received. Review region ownership as well
as total area so many arbitrary tiles cannot satisfy the rule accidentally. Do not rerun
the legacy full-screen backend to obtain a benchmark baseline; use recorded evidence.

### 3. Correct publication and unknown reporting

- Share the existing publication/provenance owner across ObservationBuilder and
  NavigationPerception. Independently proved controls remain authoritative. Publish
  parsed labels only through explicit label semantics in the canonical selector metadata
  and a shared non-actionable publication rule; current building label metadata needs
  that classification. Do not infer label safety from a selector's name or missing
  click configuration. Do not publish action/navigation elements from this content merge.
- Preserve current frame, source screen/layout, crop/row association and existing
  evidence. Reject foreign or contradictory proof instead of rebinding it. A content
  parser cannot replace visual identity, override blocking guards, or authorize mutation.
- Use the existing artifact collector and frame context diagnostics to serialize
  missing screen/guard/required-field facts and already performed region reads. Include
  screenshot/frame reference, matched profiles, guard decision, expected fact, attempted
  regions, read result/status and reason for withholding a value/control. The exporter
  must make zero additional OCR calls and must write unknown reports even with no lines.
- Reach this same report path from both observation implementations, keeping existing
  constructor/call semantics and artifact ownership. Persist beside the existing capture
  when available; normal runtime already persists captures. For ephemeral captures,
  retain in-memory diagnostics and explicitly distinguish them from a persisted report.
  Do not add a capture service, automated repair loop, external issue sender or separate
  deduplication subsystem. Avoid duplicate exports for the same observation.

Acceptance: a real production registry, recognizer and selector engine recover the
building label and existing Research control at the consumer boundary. Controlled OCR
must honor crop bounds; do not inject the label/control into the observation under test.
Use an offline fake actuator where a consumer assertion requires one. Cover foreign
frames, premium controls, blocked overlays, wrong layouts/rows, missing required fields,
and zero-OCR unknown diagnostics. Verify known unrelated facts survive a field miss.

### 4. Qualify the complete correction and prepare integration

- Run the narrowest relevant repository test group after each coherent slice, then
  affected selection. Start with the existing OCR-region/context, Research, screen
  decision/overlay and production observation tests; use the vision group when shared
  publication or guards change. Follow [tests/README.md](../../tests/README.md).
- Replay the frozen checklist through the production implementations using saved
  screenshots. Include real OCR replay for changed crop boundaries in addition to
  controlled OCR regressions. Assert expected fields and safe action availability;
  unknown cannot substitute for a previously correct required output.
- Keep independent annotations and holdout groups for changed visual profiles. Neighboring
  historical frames and resized duplicates are not independent accuracy evidence.
  Verify packaged assets using the installed-package check when assets change.
- Exercise diagnostics and the affected qualification/discovery tools under the same
  zero-full-screen contract. Record OCR calls, processed area and cache use. If timing
  qualification is needed, use the existing screen benchmark with at least five warm
  replays on unchanged source, reporting p50/p95 and host conditions; correctness gates
  take priority over latency and no new benchmark framework is needed.
- Run final cross-cutting offline acceptance on the integrated source. Honor mandatory
  affected fallback; do not rerun an equivalent full result unless edits, failures or
  another material concern make that necessary. Finish with git diff --check.

Typical commands from the applicable checkout, using the configured Python 3.13+:

```powershell
py tools/run_tests.py group vision
py tools/run_tests.py affected --base origin/main --explain
# Required for final shared-contract integration if not already covered by full fallback:
py tools/run_tests.py full
git diff --check
```

Saved captures suffice to start. Live validation is needed only for a changed boundary
that offline evidence cannot establish: one bounded relevant smoke through the existing
lease/live workflow, preserving the user's target and spending constraints. Do not replay
a battle, research start, dispatch or send solely to validate a visual producer. If new
state-changing evidence is necessary, record its exact missing fact and action scope.

## Ownership, execution and completion

B owns the existing vision/publication/guard/region and perception-model owners,
relevant selector assets, vision tests and offline qualification tools under the
[coordinated boundary](../themed/operations/PNC_AB_COORDINATED_CONTINUATION.md#exclusive-whole-file-ownership). A retains routes, workflows,
runtime composition, authorization, executors, journal mechanisms, live-driving tools
and consumer tests. Reuse published interfaces; do not port Research or other workflows
to conceal a producer gap. Preserve the previously authorized narrow consumer-fixture
correction; it is not blanket permission to edit A's tests. If an integration boundary
actually requires A's change, specify the smallest dependency and its acceptance check.
Only the component boundary is carried forward from that historical coordination plan;
its old pause state, revision numbers and full-frame fallback policy do not govern this
revision. The YOLO exclusions above narrow B's directory-level ownership for this task.

The lead agent owns diagnosis, uncertain geometry, architecture, orchestration and
review. During implementation, delegate bounded fixture/region migrations and repetitive
tests to a Luna xhigh agent with exact file ownership and acceptance criteria. Review
each slice before integrating it. Do not delegate uncertain scope or safety decisions.

Completion requires all required checklist cases fixed or preserved, zero full-screen
OCR in the scoped production and diagnostic paths, both-path publication/reporting proof,
and passing applicable offline/asset checks. A missing required case is a dependency,
not completion. Report exact source revision, changed files, commands/results, producer
contract and any remaining combined-main acceptance. A owns that integration and workflow
acceptance; preserve both sides of overlapping contract tests. No YOLO completion claim
or future transition deliverable is part of this release.

Review verdict: **implementation_ready: yes** for these corrections and the concrete
baseline freeze. **promotion_ready: no** until the required cases and integration gates
above pass. The review used current source and saved evidence; no live action or new
production implementation was performed while revising this plan.
