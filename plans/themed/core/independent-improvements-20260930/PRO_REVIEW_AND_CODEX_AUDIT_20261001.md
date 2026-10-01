# Pro review and Codex audit of N1–N4

October 1, 2026. Consultation status: **complete**. The user requested ChatGPT Pro review, application of findings, publication to `origin/main`, and model recommendations. This record covers the planning documents; it does not accept an implementation or authorize a new live run.

## Provenance and scope

- Repository: [1026535/pnc](https://github.com/1026535/pnc). Exact review baseline: [`a841f7425f2d3658c59b8b9b6f00c6b3410d3b56`](https://github.com/1026535/pnc/commit/a841f7425f2d3658c59b8b9b6f00c6b3410d3b56), verified through GitHub API and fetched `origin/main`. The task-owned branch `codex/repo-velocity-review-20260930` was fast-forwarded to it before consultation; the plan pack and source review were the only unpublished documents.
- Workflow: [create-plan-with-chatgpt-pro](../../../../.agents/skills/create-plan-with-chatgpt-pro/SKILL.md), [consult-chatgpt-pro](../../../../.agents/skills/consult-chatgpt-pro/SKILL.md), and a local [plan review](../../../../.agents/skills/review-plan-live/SKILL.md). The existing PNC Project was reused. Chat mode and the visible **6 Pro** model were verified before one submission; GitHub was attached last and used read-only.
- [Completed consultation](https://chatgpt.com/g/g-p-6aa2bcd61ce08191a499c5b6f2b67eb5-pnc-bot/c/6abecb4a-c6c8-83ea-8bfb-6b1a956b6ba3). The browser converted the pasted 19,958-character review message into `Pasted text(1).txt`. It contained the index's scope/integration rules and all material design/acceptance excerpts from the four unpublished plans, plus the exact baseline and review questions. Repeated links/boilerplate were omitted. No repository archive, secrets, configuration values, raw logs or Drive upload were sent.
- Pro explicitly confirmed reading the packet and fetching the exact commit, distinguished supplied historical probes from its source inspection, and returned findings and dispositions for all four plans. It did not inspect the local checkout, omitted Markdown boilerplate or raw ignored probe files. The chat remains the consultation deliverable.

The earlier inventory/selection counts in the source review are pinned to `868157f5897e89e2b6090c0009ecc9a835eaf3e2`. A fresh local static inventory at the review baseline contains 413 portable modules; this is not a test-run result. Landed Q1–Q3 and Q4 boundary changes do not make the whole V44 harness complete or transfer its remaining scope into these plans.

## Findings and local disposition

| Finding | Codex verification and resulting plan change |
|---|---|
| **High: N1's visible-console assertion is not headless.** | Accepted. `test_devin_worker.py:420` sets `console=True`; `devin_worker.py:558` requests `CREATE_NEW_CONSOLE`, despite its synthetic CLI. N1 now separates opt-in native attachment proof from portable flag/log assertions and retains meaningful headless child/job checks. Windows applicability alone is insufficient on Windows CI. The assertion map must distinguish native proof left unexecuted from a portable pass. |
| **Medium: N2 omits the failed-construction success outcome.** | Accepted. `script_runner.py:728` catches runner assembly failure and closes an acquired runtime without forwarding `outcome="error"`. Cleanup is already owned there. N2 adds that exact callback and real-class/fake-dependency regression, preserving both construction and cleanup errors without another close attempt or runner redesign. |
| **Medium: N1 needs known-but-unmodeled fallback and late-import proof.** | Accepted. `planner.py` distinguishes early unknown ownership from later `graph.uncertain` fallback; exact resource ownership must not disable the latter. The supervisor-death fixture imports `windows_job` during test execution. N1 now checks mapped-unmodeled fallback and late imports after scoped import cleanup. |
| **Medium: N3's listed modules contain mixed pure/runtime assertions.** | Accepted. `test_world_search_route_edges.py:36` constructs a coordinate mover, while `WorldMapSearchFixtures.setUp` constructs flows and configures logging. N3 now migrates actual pure assertions to value fixtures and moves the preserved direct-movement assertion to the existing mover test area. The matcher/value closure remains bounded and excludes unrelated execution classes. |

Additional local refinement to N1: `python_graph.py` marks a generic file loader uncertain, and `planner.py` includes its consumers for every Python change. A small synthetic graph probe reproduced that behavior. The four existing production skill scripts are not themselves graph-uncertain at the reviewed baseline, but their canonical path names have no direct static consumers. N1 therefore prefers scoped ordinary imports plus exact script/helper ownership, explicitly includes `windows_job.py`, and adds an unrelated-change negative control. No general dynamic-import analyzer or global fallback exemption is proposed.

Other conclusions retained:

- N2/N3 need only one small head/tail validation function and serial integration of that hunk. No preview-options framework or wait for all of N2 is necessary.
- N3 must preserve the existing `FULL_MAP` entry exception in `_movement_tool_allowed_for_step`: supported nonlocal entry may be outside ordinary `allowed_tools`. The existing full-map route-edge regression already proves the intended first-step contract; migrate it rather than invent another movement policy.
- N4 remains a two-sentence/reference task. The porting guide explicitly requires full; the planning reference ambiguously permits it for final integration. The revised plan describes that difference accurately and preserves real live obligations and historical results.
- All four address additional repository work outside the V44 additions. Shared source hunks require coordination; they do not require holding V/M/PW epics. Selector-discovery cleanup remains V Q4-owned.

## Verdict and model judgment

Pro's initial dispositions were **revise N1, revise N2, revise N3, accept N4**. The actionable findings above were verified locally and incorporated. Codex considers the revised packages **implementation-ready within their stated boundaries**. Runtime promotion is unassessed: implementation and its required tests remain future work.

No actionable Pro finding was rejected. Two scope clarifications matter: current known skill scripts are not already dynamically uncertain; the new fallback regression protects a changed unmodeled source. The mixed N3 tests should be split by behavior; their presence does not justify extracting movement execution.

Pro judged N1/N2 suitable for a strong coding model, N3's boundary suitable for flagship reasoning, and N4 suitable for a lightweight model. The [index's concrete recommendations](README.md#suggested-implementation-models) use models exposed by the current Codex host. Codex chooses Astra for N1 as a single owner of the coupled migration/selector work; Sol plus targeted flagship review is also reasonable, but adds an ownership handoff. These are workload judgments, not measured model or repository speedups.

## Verification and limits

**Passed:** GitHub commit verification; source/symbol checks for all four findings; static inventory/import-graph probes; final local-link, Markdown structure and whitespace checks for the revised documentation. No current emulator fact was needed to review these plans.

**Skipped as inapplicable to these document changes:** application/worker suites, fault injection into production, native-console execution, benchmarks, external worker launch, ADB and live game actions. The execution plans name their future acceptance checks; this review does not claim those checks passed.

Material remaining work is implementation and its scoped proof. No unresolved user decision prevents assigning the plans. At eventual integration, recheck the exact shared symbols and retain all independently landed V44 ownership changes.
