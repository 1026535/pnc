# N3 — Separate deterministic World-search planning from live orchestration

Prepared September 30, 2026 against `868157f5897e89e2b6090c0009ecc9a835eaf3e2`. Independent world-search architecture pilot; [pack scope and integration](README.md). Source finding: [F4](../REPOSITORY_VELOCITY_AND_MODULARITY_REVIEW_20260930.md#f4--p2-modularity-candidate-world-search-planning-is-coupled-to-live-execution-composition).

Revised October 1 after [GPT-6 Pro review and Codex audit](PRO_REVIEW_AND_CODEX_AUDIT_20261001.md) against `a841f7425f2d3658c59b8b9b6f00c6b3410d3b56`.

## Outcome and evidence

The existing request-to-plan calculation and preview formatting should be testable without constructing a screen-flow planner, movement executor, session, logger or viewport analyzer. Preserve search behavior and expose one canonical planning owner; do not create another route algorithm.

[WorldMapSearchService](../../../../pnc_automation/app/pnc/navigation/world_map_search.py) requires `screen_flows` and instantiates movement/analyzer defaults even for deterministic `resolve_plan` / `preview_route` calls. Request/result values share that module with navigation, observations, enrichment and execution. [Planning tests](../../../../tests/unit/app/pnc/navigation/test_world_search_planning.py) therefore construct the service to exercise pure work.

Static baseline probes selected 164/411 modules for a hypothetical `world_map_search.py` body change and 166/411 for traversal. Those are dependency observations, not removable-test counts or predicted savings. This pilot succeeds through independent ownership and testability; a smaller selected set is secondary and must preserve actual consumers.

V44 Q3 isolates Home-camera values. This plan addresses the separate World-search request/planning boundary; it does not change Home models, common publication or current live discovery.

## Owned source

- The cohesive planning contracts, `resolve_plan`, preview formatting and their pure helpers currently in `pnc_automation/app/pnc/navigation/world_map_search.py`.
- Proposed neutral sibling modules for World-search contracts and planning under `pnc_automation/app/pnc/navigation/`, provided their entire parent/import closure remains free of concrete runtime composition. Use the minimum cohesive split established by the import audit.
- The pure assertions in `tests/unit/app/pnc/navigation/test_world_search_{planning,plan_rejection,preview,route_edges}.py`, necessary `tests/support/pnc/world_search/` value fixtures, focused service-delegation and import-boundary assertions. `route_edges` also contains `test_coordinate_mover_fails_when_direct_target_is_outside_domain`; move that preserved runtime assertion to the existing coordinate-mover test area rather than bringing the mover into the pure cohort.

Keep [coordinate-domain](../../../../pnc_automation/app/pnc/navigation/world_map_coordinate_domain.py), [traversal](../../../../pnc_automation/app/pnc/navigation/world_map_traversal.py), [sweep](../../../../pnc_automation/app/pnc/navigation/world_map_sweep.py) and overview-projection algorithms canonical. Do not edit N2's CLI files, runtime factories, selector rules, feature ledgers, match-3 or PW implementation. Existing search execution, movement/provenance, checkpoint analysis and survey persistence stay in their runtime owners.

## Deliverables

1. **Close the contract/import audit before moving code.** Trace `WorldMapSearchRequest`, `WorldMapResolvedSearchPlan` and their origin, boundary, pattern, movement, matcher and sweep dependencies. The request canonicalizes its matcher in `__post_init__`; copying only its dataclass or leaving a back-import into the orchestration module would not create a neutral contract. Include required pure matcher/value dependencies cohesively, preserve type identity, and inspect package initializers. The inspected matchers operate on queries, sightings, observations and pure helpers; they do not by themselves require moving the concrete castle inspector, movers, execution profiles or analysis queues. If a further dependency does require unrelated execution extraction, report the specific edge and defer that expansion.
2. **Extract one request-to-plan owner.** Reuse the existing route, execution-plan and sweep builders. Accept the current immutable surface facts required for origin/start resolution and explicit supported movement capabilities. Have the service acquire/qualify the observation and gather capabilities through the existing navigator support checks, then delegate. Do not move session/navigation acquisition into the planner or infer support from an invented default.
3. **Preserve semantic decisions once.** Keep current/self-territory/explicit/corner origins, coordinate normalization, bounds, stride, sweep policy, allowed-tool order, non-local first-step preference and execution-start coordinate behavior. In particular, existing `FULL_MAP` entry may use a supported nonlocal tool outside ordinary `allowed_tools`; do not prefilter the capability snapshot by that ordinary preference list. Preserve the existing full-map entry regression rather than adding a competing rule. Move shared movement-choice logic once if planning and execution consume it; runtime still qualifies support/current state at its existing boundary. A plan is not authorization to replay an input.
4. **Move pure preview formatting and migrate actual pure assertions.** Format from the resolved plan while preserving the preview schema/errors, and consume N2's small head/tail function after that hunk is available. Keep public service methods as delegates and required legacy imports as same-object aliases. Replace pure tests' inheritance from `WorldMapSearchFixtures`: its setup constructs `ScreenFlowPlanner`, configures logging and creates a temporary directory. Use minimal value fixtures for the pure cohort. Keep runtime/workflow fixtures with their existing users and move the one direct-movement rejection assertion to its runtime owner. Remove superseded duplicate planning code.

## Verification and acceptance

Migrate existing assertions before adding new ones. The core acceptance is the same planning/preview/rejection behavior through the new owner without runtime construction. Include the already-supported movement ordering and current-viewport execution-start distinction; these are easy to lose in a superficial extraction.

Run the migrated pure cohort, the receiving coordinate-mover module and relevant existing traversal/sweep owner checks. Preserve `test_full_map_row_sweep_prepends_non_local_entry_intent_from_far_current_viewport` from `route_edges`, including its coordinate-jump first step. Retain a small service-delegation check with real planning values so tests cannot pass while the service still uses old logic. Relevant downstream suites live under `tests/integration/workflows/test_world_search_*`; use the final affected gate to retain real execution consumers rather than manually rerunning every module.

Add a focused import-boundary check that imports the new owner in a fresh interpreter and establishes that concrete `screen_flows`, observation composition and analysis services are not loaded through it. Preserve public alias identity. Do not claim that static type-only references are runtime loads, or remove legitimate static consumer selection to manufacture savings.

Record the same-method before/after import closure and selected modules for a planning-only hypothetical change. No timed full-suite benchmark is needed. On the finished candidate run `py tools/run_tests.py affected --base origin/main --explain` once, including declaration/import consumers, then `git diff --check`. New production modules may legitimately trigger full fallback during the migration.

No live proof is needed for a behavior-equivalent pure extraction. If parity exposes a desired navigation or movement behavior change, leave it as a separately described defect; do not hide it inside this pilot or substitute mock parity for its eventual live acceptance.

## Completion and dependencies

Done means one neutral canonical planning owner, preserved public semantics/type identity, a migrated meaningful cohort with no runtime construction, proven service delegation, and no second algorithm or fabricated observation facts. A file move with the same concrete import closure does not satisfy the plan.

Planning extraction can proceed independently of N1/N4 and V/M/PW features. N2 owns the CLI fixes and preview-limit validation seam; integrate that seam before the final preview delegation and preserve its zero-acquisition regressions. Do not edit the CLI to create a second offline-preview format or expand scope into a new public command.

Hand back the dependency audit, old-to-new ownership map, parity/import results, unchanged runtime boundaries and actual selection observations. Stop further modularization when this boundary is established; no repository-wide model migration is part of acceptance.
