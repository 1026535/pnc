# Repository velocity and modularity: findings outside V44

September 30, 2026. Reviewed source: `868157f5897e89e2b6090c0009ecc9a835eaf3e2`, containing the newly published V44 plan pack and the coordinator's earlier quality review. Objective: identify independent defects and architectural friction that justify changes to code, tests, skills or workflows. This is a scoped review and proposed work sequence, not implementation or a new live assignment.

The V coordinator's [quality sequence](../vision/modules/v44/V44_QUALITY_REVIEW_AND_SEQUENCE.md) remains its authority. This review excludes its shared observation-field fix, Home camera contract migration, Home fixture ownership and live case/result redesign. No new item below is a prerequisite for completing V44. Existing core/application dependency guards, lazy public exports, shared YAML validators and pure traversal modules were inspected and should be retained; a large file alone was not treated as a defect.

## Findings, ordered by practical priority

### F1 — P2: Worker infrastructure changes run the wrong test inventory

**Locations:** [inventory](../../../tools/test_selection/models.py), lines 28–36; [affected planner](../../../tools/test_selection/planner.py), lines 98–99; [CI workflow](../../../.github/workflows/tests.yml), line 77; [.agents worker tests](../../../.agents/skills/devin-implement/scripts/test_devin_worker.py), [monitor tests](../../../.agents/skills/devin-implement/scripts/test_devin_monitor.py), [ACP tests](../../../.agents/skills/devin-implement/scripts/test_devin_acp.py) and [consultation tests](../../../.agents/skills/devin-game-knowledge/scripts/test_consult_game_knowledge.py).

The canonical inventory admits only `tests/{unit,contract,integration,architecture}/test_*.py`. Four existing test modules under skills contain **92 statically counted test methods**, but none is in that inventory. Meanwhile, a change to `devin_worker.py`, `devin_monitor.py` or `consult_game_knowledge.py` is an unknown Python owner and selects **all 411 portable modules**. CI invokes that same runner and has no separate skill-runtime test step.

The deterministic same-snapshot probes reproduced both facts. A broad green application gate therefore does not execute the worker's relevant tests. There is a documented manual worker-test command in [keepalive.md](../../../.agents/skills/devin-implement/references/keepalive.md), line 40, but it is outside the normal validation route. This is both a coverage gap and unnecessary test work; it is not evidence that those tests currently fail.

**Cause:** executable automation infrastructure is maintained in skill packaging without first-class test ownership. A conservative fallback runs unrelated tests but cannot discover missing tests.

**Smallest clean fix:** put the existing offline test coverage into canonical inventory, with one explicit tooling owner for each known skill script. Prefer moving the tests into `tests/unit/tools/` with a small shared loader for the actual bundled scripts; retain production scripts at their skill locations. Move reusable test support out of peer test modules. Preserve Windows-specific subprocess/job checks with explicit platform applicability; never launch a real worker, heartbeat, model, account or emulator in portable tests.

Only after coverage is included, teach selection about these explicitly owned script paths through the existing ownership schema. Its current unknown-owner branch precedes resource ownership, so adding a YAML group alone is insufficient. Unknown skill Python must continue to fall back conservatively. Do not exempt all of `.agents/` or copy the implementation into a second package.

**Acceptance:** changing each known script selects and runs its owning tests; a controlled callback/cleanup defect is caught by the selected test; an unknown script still takes the conservative path. Report actual selected modules and applicable test cases, not 92 as a guaranteed runtime count. Update the manual skill command to use the same runner. The final selector/inventory change legitimately needs its infrastructure gate.

### F2 — P2: Several live tools omit the runtime's cleanup boundary

**Locations:** [world-route preview](../../../tools/preview_world_map_search_route.py), lines 97–139; [selector discovery](../../../tools/discover_selector_registry.py), lines 175–276; [building inspection](../../../tools/inspect_building_upgrade_entries.py), lines 126–226; [YOLO prototype live branch](../../../tools/prototype_yolo.py), lines 77–105. Existing ownership is in [ConnectedAccountRuntime / ConnectedAutomationRuntime](../../../pnc_automation/app/automation/engine/script_runner.py), lines 110–183.

These tools acquire a connected runtime or runner without entering its context manager or closing it on completion/failure. The existing runtime owns session/operation-lease cleanup and measurement finalization. Logging shutdown alone does not close it. A command's process exit may eventually end process ownership, but it does not execute the explicit cleanup contract; invocation in a surviving interpreter also retains resources.

The actual preview function was exercised with fake application/connected services. A successful preview returned 0 without calling `close`; an optional movement failure also omitted cleanup. Its current test doubles lack a cleanup contract, so the tests cannot detect this omission. The other three sites are source-confirmed omissions, not separately live-reproduced leaks.

**Cause:** standalone tools manually manage lifecycle despite already having a canonical context-managed runtime.

**Related defect in the existing owner:** `ConnectedAutomationRuntime.__exit__` forwards to `self.close()`, which calls `runtime.close()` with its default success outcome. The inner `ConnectedAccountRuntime.__exit__` correctly forwards an error outcome. A second mocked probe confirmed that the same raised operation exception records `error` through the inner context and `success` through the outer bundle. The exception still propagates; the defect is false success in run-level performance evidence. Reusing the bundle should include fixing this outcome propagation at its existing owner.

**Smallest clean fix:** use the existing runtime/runner context manager across all dependent work, including acquisition, capture, optional movement, report generation and exceptional exits. Use the established error-preserving cleanup helper where a context manager does not cover the needed lifetime. Preserve configured keep-warm/instance policy and any outer reservation; cleanup is not permission to shut down an instance. Keep global logging shutdown as its separate existing boundary.

**Acceptance:** contract-aware fakes assert exactly one cleanup on success, preflight failure and execution/report failure; execution plus cleanup errors are both retained. Both context layers record an error outcome for a failed body and success for a successful body. Verify returned discovery records are materialized before closing their owner. Reuse the runtime lifecycle tests; do not add another lease manager, destructor workaround or CLI framework. A short inventory of direct runtime factories can find the remaining concrete omissions without a repository-wide test matrix.

### F3 — P2: Invalid preview arguments reach live setup and navigation before rejection

**Locations:** [preview entry](../../../tools/preview_world_map_search_route.py), lines 92–107; explicit-origin validation at lines 199–204 and boundary validation at lines 209–226.

`_build_request(arguments)` runs after building the connected runtime and proving the World-map preflight. An invocation with `--origin explicit_coordinate --radius 10` but no coordinates therefore connects and requests navigation before raising its argument error. A missing boundary or incomplete rectangle has the same ordering problem. Positive head/tail validation also occurs downstream in the service.

The mocked reproduction recorded `connect → preflight_navigation → SelectorResolutionError`. No real config or device was used. This consumes a scarce live setup opportunity for a locally invalid request and makes ordinary argument mistakes look like live-workflow interruptions.

**Smallest clean fix:** construct/validate the typed request and presentation/execution limits immediately after argument parsing, before application construction or connection. Keep current-viewport facts and genuine current-state qualification after connection; do not pretend every request can resolve without an observation. Preserve existing typed validators rather than duplicating their rules in argparse callbacks.

**Acceptance:** incomplete origin, boundary and invalid preview limits fail with zero application/connection/navigation calls; a valid request retains its existing behavior. This correction can ship with F2's preview lifecycle change, but has its own behavioral assertion.

### F4 — P2 modularity candidate: World-search planning is coupled to live execution composition

**Locations:** [world-search module](../../../pnc_automation/app/pnc/navigation/world_map_search.py), imports at lines 38–72, request/result values at lines 890/927, service dependencies at lines 2549–2572 and planning/preview at lines 2574–2694; [planning tests](../../../tests/unit/app/pnc/navigation/test_world_search_planning.py), lines 15–45.

Request values, plan resolution, report rendering, movement/navigation, viewport analysis and search execution share one module. Even deterministic planning tests construct `WorldMapSearchService(screen_flows=...)`. That service requires a concrete screen-flow dependency and constructs movement/analyzer defaults even when its caller only needs a route.

There are already good pure owners: [coordinate domain](../../../pnc_automation/app/pnc/navigation/world_map_coordinate_domain.py), [traversal](../../../pnc_automation/app/pnc/navigation/world_map_traversal.py), [sweep](../../../pnc_automation/app/pnc/navigation/world_map_sweep.py) and overview projection. They should be reused. The remaining issue is the request-to-plan boundary and shared values living with concrete orchestration, not an absence of route algorithms.

Static body-change probes selected 164/411 modules for `world_map_search.py` with 133 reverse-import test consumers, and 166/411 for traversal. Those are dependency observations, not estimates of removable tests. Traversal legitimately feeds search; moving code cannot erase actual integration dependencies.

**Smallest clean pilot:** extract the cohesive request/result contracts and deterministic request-to-plan calculation into one neutral owner outside any eager runtime facade. Accept the actual immutable planning facts needed by the current contract, such as the relevant surface/coordinate data and explicit supported movement capabilities. Reuse the existing traversal/sweep algorithms. Keep observation acquisition, current-state qualification, movement capability execution and input provenance in `WorldMapSearchService`; delegate its existing public planning methods to the new owner.

Migrate one planning test cohort and preview formatting to this boundary. Preserve all existing origin, stride, sweep, movement-choice and execution-start semantics. Keep required public re-exports as the same objects; do not introduce a second planner or hide imports from selection. Offline preview from a saved/explicit planning context may then become possible, but is not a reason to invent a new evidence format or claim a current-viewport plan without its required facts.

**Acceptance:** the planning cohort can exercise the same meaningful assertions without constructing a screen-flow planner, executor, session, logger or analyzer; the new owner's import closure excludes concrete observation/composition services. Existing service integration tests prove delegation parity. Measure actual ownership/import change; stop expansion if the extraction only relocates code. Runtime gains and selection reduction remain unproved.

### F5 — P2: Mandatory porting guidance still demands a redundant full gate

**Location:** [CORE_WORKFLOW_PORTING.md](../../../instructions/CORE_WORKFLOW_PORTING.md), line 244, tells callers to run “the required final full suite” after focused checks. [AGENTS.md](../../../AGENTS.md), lines 69–70, and [write-code](../../../.agents/skills/write-code/SKILL.md), lines 33–35, require one final affected gate and explicitly reject an extra local full run without a concrete reason.

The porting guide is mandatory reading for workflow migrations, so the conflicting imperative creates a plausible repeated full-test requirement. It appears in operative lifecycle guidance, separately from the clearly dated historical test results. This review proves contradictory instructions, not how many extra runs they have caused.

**Cause:** validation policy is restated in feature/workflow guides instead of referring to its canonical owner.

**Smallest clean fix:** replace the imperative with a reference to the repository's current validation rule and retain any genuinely feature-specific checks. Keep historical commands/results labeled as history. Audit active skill references for the same specific policy contradiction; do not rewrite every old plan or delete real live acceptance requirements.

**Acceptance:** an implementer following either the porting guide or write-code reaches the same final gate, with owning/downstream checks, legitimate full fallback and applicable live proof preserved. Documentation/link checks suffice; no tests of wording or new full run.

## Proposed execution packages

The [separate agent-ready plans](independent-improvements-20260930/README.md) now define the executable scope for these additional findings. They exclude everything already added to V44 Q1–Q6, including selector-discovery cleanup under Q4. Findings above retain their reviewed source evidence; the narrower package boundaries below govern future assignments.

The October 1 [GPT-6 Pro review and Codex audit](independent-improvements-20260930/PRO_REVIEW_AND_CODEX_AUDIT_20261001.md) further tightened headless/native test separation, script/helper recall, failed-construction outcomes and the pure World-search test boundary. Those revisions are incorporated in the linked plans; the original probes and counts above remain historical evidence at their stated baseline.

| Package | Deliverable / owner | Validation and dependency |
|---|---|---|
| **N1 — Make agent-tool tests first-class** | F1; test-infrastructure owner with skill-runtime owner. Establish inventory before narrowing selection. | Existing skill tests run offline through the runner; selector/ownership/fault-recall tests; one final affected infrastructure gate. No game live test. |
| **N2 — Correct tool entry and lifetime** | F2's independent remainder + F3; runtime/tool owner. Preview, building inspection, YOLO live acquisition and the connected bundle's error outcome. Selector discovery remains V Q4-owned. | Extend the three owning tool modules and existing runtime cleanup suites with offline fakes. A live check is needed only for a material acquisition, input or host-cleanup semantic change not proved by the existing boundary contract. |
| **N3 — Isolate world planning** | F4; world-search owner. One neutral value/planning slice, after agreeing the current request/plan semantics. | Existing planning/domain/traversal/sweep tests, service delegation and meaningful import-boundary checks; final affected gate including declaration/import consumers. No new live tour for behavior-equivalent extraction. |
| **N4 — Reconcile validation instructions** | F5; repository workflow owner. Small independent documentation change. | Link/read-through and whitespace checks; no runtime test. |

N1 and N2 have concrete reproducible defects and can be implemented independently in owned checkouts. N4 is a small parallel correction. N3 is a bounded architecture pilot, not a prerequisite for those fixes or a full world-search rewrite. Its value is independently testable planning and clearer ownership, not a promised speed percentage.

Coordinate overlapping symbols before implementation: V Q4 owns selector discovery; N2 owns the separately demonstrated bundle-outcome defect unless another owner has already fixed it. N1 and V Q2 share selection infrastructure but own different mappings. N2 and N3 share only the preview-limit validation/delegation seam. The linked pack defines their serial integration points without making unrelated packages wait for an entire epic. Do not change frozen candidates, wake paused PW, start workers or reallocate M's host capacity from this review. These are proposed packages, not dispatched assignments.

## Verification and evidence limits

- **Passed:** static inventory/ownership probes using the existing selector with identical old/new source snapshots. They selected 411 application modules and excluded all four skill-local test modules for each named skill-script scenario.
- **Passed reproduction:** three runs of the actual preview function with fake application/runtime services: successful preview, invalid explicit origin and movement failure. These exposed the reported defects; they are not passing production acceptance tests.
- **Passed reproduction:** actual inner/outer runtime context code with fake session/performance writer exposed the outer bundle's false-success outcome on an operation exception.
- **Passed:** static world-search dependency probes. Counts establish coupling only; imports under type checking are conservatively included by the graph and are not claimed as runtime-loaded modules.
- **Inspected:** source, relevant callers/fakes, canonical runner, CI, architecture guards, write-code/devin skill instructions and mandatory porting guidance.
- **Skipped:** application suites, benchmarks, actual worker launch, external service calls, ADB and live game actions. They are unnecessary to substantiate this scoped review; proposed fixes still need their owning checks.

Reproduction JSON is local ignored evidence: [skill selection](C:/Users/lebel/pnc/.local-data/worktrees/repo-velocity-review-20260930/.local-data/non-v44-review/skill-test-selection.json), [preview lifecycle/order](C:/Users/lebel/pnc/.local-data/worktrees/repo-velocity-review-20260930/.local-data/non-v44-review/preview-lifecycle-probe.json), [bundle failure outcome](C:/Users/lebel/pnc/.local-data/worktrees/repo-velocity-review-20260930/.local-data/non-v44-review/bundle-failure-outcome.json), [world-search coupling](C:/Users/lebel/pnc/.local-data/worktrees/repo-velocity-review-20260930/.local-data/non-v44-review/world-search-coupling.json). Those links are host-local; the tracked source links and method above are the portable evidence.

No claim is made that these are all repository issues, that every selected test is unnecessary, or that a speedup has been measured. The next useful evidence is the smallest implementation slice and its preserved behavior, not another broad audit.
