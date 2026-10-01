# N2 — Close standalone tool runtimes and reject invalid input early

Prepared September 30, 2026 against `868157f5897e89e2b6090c0009ecc9a835eaf3e2`. Independent runtime/tools assignment; [pack scope and integration](README.md). Covers the additional remainder of [F2 and F3](../REPOSITORY_VELOCITY_AND_MODULARITY_REVIEW_20260930.md#f2--p2-several-live-tools-omit-the-runtimes-cleanup-boundary).

Revised October 1 after [GPT-6 Pro review and Codex audit](PRO_REVIEW_AND_CODEX_AUDIT_20261001.md) against `a841f7425f2d3658c59b8b9b6f00c6b3410d3b56`.

## Outcome and evidence

Standalone tools must release the connected runtime once their work ends, retain execution and cleanup failures, and record failed operations as failures. Invalid route-preview arguments must be rejected before application construction, runtime acquisition or navigation.

The actual [preview tool](../../../../tools/preview_world_map_search_route.py) was probed with fake services: successful preview and failed movement both omit cleanup; an incomplete explicit origin reaches connection and preflight navigation before rejection. [Building inspection](../../../../tools/inspect_building_upgrade_entries.py) and the live branch of [YOLO prototype](../../../../tools/prototype_yolo.py) have source-confirmed cleanup omissions. In [the connected runtime owner](../../../../pnc_automation/app/automation/engine/script_runner.py), the inner context records an exception as `error`, but the outer bundle calls `close()` with the default success outcome. An actual-class probe with fake session/performance services reproduced this false-success record.

`tools/discover_selector_registry.py` was also identified in the review, but **its cleanup and tests remain V44 Q4's responsibility**. This package does not redesign discovery, receipts, case results, navigation or game actions.

## Owned source and boundaries

- `ConnectedAccountRuntime` / `ConnectedAutomationRuntime` lifecycle methods and the specific exception-cleanup callback in `ScriptRunner._build_automation_runner_from_services`, all in `pnc_automation/app/automation/engine/script_runner.py`, plus their runtime/performance regressions. No service wiring or observation-field migration.
- `tools/preview_world_map_search_route.py`, `tools/inspect_building_upgrade_entries.py`, and the live acquisition branch of `tools/prototype_yolo.py`; their focused tool tests.
- The existing head/tail limit check in `world_map_search.py:preview_route`, only as needed to expose one module-level pure validation function used by both the CLI and direct service callers. N3 may move its implementation while preserving a required alias; no preview-options framework or request-schema redesign.

Keep runtime acquisition arguments, required roles, preflight behavior, report schema and configured keep-warm/cleanup policy. Closing the task runtime must not release an outer reservation or introduce host shutdown. YOLO model evaluation, Home-building route qualification and World-map movement semantics stay with their existing owners.

## Deliverables

1. **Correct the two demonstrated error-outcome paths.** Add deterministic regressions for a failed bundle body and runner construction after connected services exist. The outer context currently uses default-success close; `_build_automation_runner_from_services` also passes `connected_runtime.close` without an error outcome from its exception handler. Delegate exception-aware bundle cleanup to the existing inner lifecycle or forward the outcome, and pass `outcome="error"` through the existing factory cleanup callback. The factory already owns partial-acquisition cleanup: do not wrap it in another close attempt. Preserve no-argument `close()` for normal callers and avoid closing the shared session through both `runner` and `runtime`. Normal completion records success; body/construction failures record error; their cleanup failures remain visible alongside the active error.
2. **Make preview input validation precede acquisition.** Build the typed request immediately after parsing, reusing its current origin/boundary/domain validators. Make positive head/tail validation callable without constructing `WorldMapSearchService` and reuse it at both entry points. Preserve current `execute_first <= 0` no-execution semantics unless the eventual assignment explicitly changes that contract. Viewport coordinates, current screen and available movement capabilities still require connected observation; do not fabricate them offline.
3. **Use one explicit lifetime in each named tool.** Wrap all dependent preflight, capture, optional movement and report materialization in the canonical bundle context. For building inspection, prefer the existing `build_connected_runtime_bundle(...).runner` composition with identical acquisition arguments; the current runner-only context does not itself preserve both body and cleanup failures. This avoids expanding the task into M's `AutomationRunner` implementation. Retain separate logging shutdown. Close acquired owners on early return and exceptional exit; a factory that fails before returning remains responsible for its own partial acquisition.
4. **Upgrade the fakes at the affected boundaries.** The existing preview tests use `SimpleNamespace` objects without a lifetime contract. Give tool tests realistic context/cleanup behavior; use the real connected classes with fake session/performance services for lifecycle assertions. Add focused inspection/YOLO entry tests if no owner exists at assignment time. Fake inference, filesystem outputs and live services as appropriate; do not load a real model or invoke ADB.

## Verification and acceptance

Use [preview regressions](../../../../tests/unit/tools/test_preview_world_map_search_route.py), [connected composition tests](../../../../tests/integration/script_runner/test_script_runner.py), and [workflow lifecycle contracts](../../../../tests/contract/entrypoints/test_core_workflow_lifecycle.py) where their existing contracts apply. Keep new tool coverage limited to the three changed entry points.

| Boundary | Observable acceptance |
|---|---|
| Invalid request before acquisition | Missing explicit coordinates, incomplete boundary and nonpositive head/tail fail with zero application, connection and navigation calls. Valid requests retain preview output and optional movement behavior. |
| Acquired tool lifetime | Normal return, preflight failure, execution failure and report failure release the one acquired owner; no second close through an alias. Exercise representative failures at their actual owning boundaries, not every combination in every tool. |
| Error evidence | Inner and outer contexts distinguish success/error; a runner-construction failure after acquisition also records error and closes once. Body-plus-cleanup and construction-plus-cleanup failures retain both exceptions; final sink failure still fails the command. |
| Ownership | Configured cleanup policy and outer reservation ownership are unchanged; materialized results do not require a closed owner. |

Run the named owning modules or their smallest runner group after each coherent slice. Run `py tools/run_tests.py affected --base origin/main --explain` once on the finished candidate and `git diff --check`; retain import-visible lifecycle consumers.

The intended changes are provable with deterministic acquisition/lifetime fakes. They do not require a new live run. If implementation reveals a material change to actual host cleanup or navigation rather than merely invoking the existing contract, record that expansion and validate its specific boundary through the canonical live workflow: one configured non-Main testing target, current identity and valid lease before entry, one already-needed tool invocation, and observable lease release with the configured instance state preserved. Retain trace/cleanup evidence, stop on unverifiable identity or cleanup, and leave that acceptance pending rather than repeating unchanged actions. Do not invent a multi-tool live tour for this plan.

## Dependencies and handback

N2 is one assignment because input ordering and lifetime touch the same preview entry point. It does not depend on N3's architectural extraction. Coordinate only the preview-limit seam with N3: land or transfer the accepted pure validator before N3 integrates `preview_route` delegation. N3 leaves the CLI files with N2.

Check current ownership of the two connected classes and the named factory exception handler against V Q4 and runtime changes before editing. Reuse a landed equivalent fix; do not duplicate Q4's discovery migration or alter M/PW behavior. Report each tool's cleanup proof, zero-acquisition argument regressions, body/construction outcome parity and any material live-proof gap separately. Source fixes and publication follow the later assignment, not this planning document.
