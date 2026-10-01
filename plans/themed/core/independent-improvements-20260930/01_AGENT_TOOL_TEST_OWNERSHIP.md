# N1 — Put agent-tool coverage into the canonical test workflow

Prepared September 30, 2026 against `868157f5897e89e2b6090c0009ecc9a835eaf3e2`. Independent test-infrastructure assignment; [pack scope and integration](README.md). Source finding: [F1](../REPOSITORY_VELOCITY_AND_MODULARITY_REVIEW_20260930.md#f1--p2-worker-infrastructure-changes-run-the-wrong-test-inventory).

Revised October 1 after [GPT-6 Pro review and Codex audit](PRO_REVIEW_AND_CODEX_AUDIT_20261001.md) against `a841f7425f2d3658c59b8b9b6f00c6b3410d3b56`. Historical counts below retain their original baseline.

## Outcome and evidence

A change to a known worker/monitor/consultation script must execute its actual offline tests through the repository runner and CI. Unrelated application tests must no longer substitute for missing worker coverage.

[Inventory](../../../../tools/test_selection/models.py) only admits the four portable tiers under `tests/`. Four modules under skills contain 92 statically counted test methods outside that inventory. At the baseline, changes to the worker, monitor and consultation scripts each select all 411 portable modules and none of those skill tests. These are reproducible static inventory/selection findings, not a claim that the excluded tests pass or fail. The [planner](../../../../tools/test_selection/planner.py) checks unknown Python ownership before applying explicit resource owners, so a YAML-only change cannot solve this.

V44 Q2 owns Home screenshots and packaged camera assets. This package owns executable skill infrastructure, an additional coverage gap that Q2 does not address.

## Owned source

- Migrate the portable coverage from `.agents/skills/devin-implement/scripts/test_devin_{worker,monitor,acp}.py` and `.agents/skills/devin-game-knowledge/scripts/test_consult_game_knowledge.py` into a proposed `tests/unit/tools/agent_runtime/` package. Retain the actual visible-console attachment assertion in an explicitly opt-in native test outside the four portable tiers, sharing the needed fixture support.
- Add only needed reusable test support under `tests/support/agent_runtime/`, using [the repository path helper](../../../../tests/support/paths.py) to load the real bundled scripts. Keep production scripts at their current skill paths.
- Change [planner](../../../../tools/test_selection/planner.py), [ownership rules](../../../../tests/selection_rules.yaml), relevant `tests/unit/test_selection/` regressions, and [test guidance](../../../../tests/README.md) for these explicit owners. Change inventory code only if the migration reveals an actual requirement; ordinary tests in the proposed package already satisfy its layout.
- Update the active test command in [worker keepalive guidance](../../../../.agents/skills/devin-implement/references/keepalive.md). Other skill command references may change only when they point to the moved tests. Historical dated results remain historical.

The worker implementations, transport behavior, automations, `.github/workflows/tests.yml` job topology, Home resource rules and live-testing policy are not redesign targets. Inspect CI to prove inclusion; do not add a second competing test job merely to bypass the canonical inventory.

## Deliverables

1. **Inventory migration with assertions accounted for.** Migrate the four modules' portable assertions, adapt script imports, and remove superseded test copies. `test_visible_console_preserves_both_logs` currently launches a synthetic CLI with `console=True`, which still creates a real Windows console. Split its concerns: portable checks cover console-mode selection and Unicode stdout/stderr through deterministic boundaries; retain actual console attachment proof in the opt-in native case. A Windows-only skip does not make that case headless on Windows CI. The default group must never actually request `CREATE_NEW_CONSOLE`. Keep meaningful headless child-process/job cleanup checks. `test_devin_acp.py` imports `TimedResult` from a peer test; replace that coupling with shared support only if still needed under the canonical runner. Keep an old-to-new assertion map that explicitly marks native proof unexecuted by the default gate; 92 statically counted methods is not a required runtime pass count.
2. **Reliable, offline loading without global selection.** Load the actual packaged implementation without copying it or depending on the shell's working directory. Prefer ordinary literal imports inside a scoped test-support import path, with explicit script ownership below. A generic `spec_from_file_location` loader is marked uncertain by the current graph; its test consumers are then selected for every Python change. Do not introduce that new global dependency or weaken dynamic-import fallback to hide it. Restore temporary `sys.path`/`sys.modules` state and keep patches bound to the intended module objects. Preserve the existing worker-code tests with synthetic CLI subprocesses: running the implementation against those fixtures is intended; invoking real Devin/model services, app-tool bridges, live heartbeats or emulators is not. Make Windows-only job/console applicability explicit without skipping unrelated portable assertions. Verify the fake boundaries before executing migrated tests.
3. **Explicit selection ownership.** Audit each moved module's production-script imports, including `devin_worker.py` consumed by ACP/monitor and `windows_job.py` consumed by the worker and job-lifetime fixtures. Add exact known-script/helper mappings using the existing validated resource-group schema; the proposed `unit.tools.agent_runtime` group is sufficient unless evidence justifies finer grouping. Allow those explicit owners through the unknown-Python branch without weakening missing-source, parse, infrastructure or unknown-path fallback. A recognized owner must not suppress the later `unmodeled changed source` fallback. Do not exempt all `.agents/` Python or introduce a second selector. If a chosen loader still requires graph support, establish a separately justified finite dependency contract before widening the selector; do not silently accept globally selected worker tests as the completed velocity fix.
4. **One documented route.** Replace active manual discovery instructions with the canonical runner group. Demonstrate that inventory and the existing CI shard union contain the migrated modules. The old skill-local test commands must not silently become the only way to exercise the code.

## Verification and acceptance

During migration run `py tools/run_tests.py group unit.tools.agent_runtime`; after selection changes run `py tools/run_tests.py group unit.test_selection` and the relevant `test_harness` checks. These commands are planned verification, not results from this document.

Add focused selection regressions for a known modeled script, a shared helper's real consumers, a directly changed migrated test, an unknown skill script, a mixed known-plus-unknown change, and a mapped script changed to contain unmodeled dynamic loading. The last case must still full-fallback. Include an unrelated, already-owned Python edit as a negative control: the new worker group must not be selected solely by loader uncertainty. A change to an actually unmodeled loader may legitimately remain broad. Retain architecture/API/static consumers as applicable. Use the existing fault-recall approach to show that a controlled callback or cleanup regression is detected by the selected owning test; keep the injected defect out of the final candidate.

Exercise a representative late sibling import as well as initial collection. The existing supervisor-death case imports `windows_job` inside its test method; adapt that access so scoped import cleanup does not break later execution. Verify default collection/execution does not open a console, and account separately for the retained opt-in native assertion. No native-console run is required to prove the portable migration.

On the finished candidate run `py tools/run_tests.py affected --base origin/main --explain` once and `git diff --check`. Selector infrastructure may legitimately trigger full fallback for this implementation. The desired smaller selection concerns **subsequent known-script changes**, not hiding the infrastructure gate for this migration. No live smoke or timing benchmark is required.

Done means the applicable portable assertions from all four modules are in canonical inventory and CI, native-only proof is explicitly accounted for, known modeled script changes retain their owners, unknown or unmodeled changes still fail closed, late imports work without persistent import-state pollution, and active documentation points to the same test route. Report selection counts as observed; do not promise a percentage speedup.

## Dependencies and agent handback

Prepare the test migration independently of V Q2. Before editing/integrating shared rule and regression hunks, compare current Q2 changes and retain its Home ownership behavior. Serialize that integration only; this task has no dependency on V44 route completion, M acceptance or PW resumption.

Hand back the assertion migration map, exact known-script ownership map, representative selection/fault-recall results, applicable platform skips, and the candidate's final gate. A passing application suite without the four migrated modules is not acceptance.
