# Independent repository improvements outside the V44 additions

September 30, 2026. Planning baseline: `868157f5897e89e2b6090c0009ecc9a835eaf3e2`. These are four separately assignable plans for the additional findings in the [repository review](../REPOSITORY_VELOCITY_AND_MODULARITY_REVIEW_20260930.md). They are **outside the quality work already added to V44**, and have independent acceptance. They do not extend the V, match-3 M, or Pet Workshop PW feature queues.

Status: revised after [GPT-6 Pro consultation and Codex audit](PRO_REVIEW_AND_CODEX_AUDIT_20261001.md) on October 1 against `a841f7425f2d3658c59b8b9b6f00c6b3410d3b56`; prepared for the user's requested publication. Implementation and agent assignment remain pending. Historical counts describe the original baseline above. At assignment, compare the named symbols with current main and active owners; an already-landed fix satisfies that portion instead of triggering another implementation.

## Packages

| Plan | Additional problem and repository benefit | Priority / assignment |
|---|---|---|
| [N1 — Agent-tool test ownership](01_AGENT_TOOL_TEST_OWNERSHIP.md) | Four skill-local test modules are absent from the normal inventory, while worker changes select the entire application suite. Migrate headless coverage, retain native-console proof separately, then select known owners accurately. | High coverage priority; one test-infrastructure agent. |
| [N2 — Tool lifecycle and early validation](02_TOOL_LIFECYCLE_AND_PREFLIGHT.md) | Three standalone tools omit explicit cleanup; the connected bundle records failed operations as successful; invalid preview requests reach navigation. Correct these concrete defects through existing owners. | Independent implementation priority; one runtime/tools agent. |
| [N3 — World-search planning boundary](03_WORLD_SEARCH_PLANNING_BOUNDARY.md) | Deterministic route planning requires live-service composition. Make the existing planning behavior independently usable and testable. | Bounded architecture pilot; one world-search agent. |
| [N4 — Validation policy consistency](04_VALIDATION_POLICY_CONSISTENCY.md) | Mandatory porting guidance still demands a final full suite despite the canonical affected-test policy. Remove the conflicting operative instruction. | Small immediate documentation task; one workflow agent. |

F1 maps to N1; F2's independently owned remainder and F3 map to N2; F4 maps to N3; F5 maps to N4. F2/F3 stay together because both change the preview entry point. N1/N2 have demonstrated defects; N3 has demonstrated coupling but no measured speedup. N4 proves an instruction conflict, not a measured count of wasted runs.

## Work deliberately left with V44

The [V coordinator's Q1–Q6 sequence](../../vision/modules/v44/V44_QUALITY_REVIEW_AND_SEQUENCE.md) owns common observation publication, Home fixture/asset ownership, neutral Home-camera values, tracked live cases/results and discovery controls, the developmental live cohort, and evidence/current-view consolidation. None is reissued here.

In particular, **selector-discovery cleanup stays in Q4**. The original review identified `tools/discover_selector_registry.py` alongside other omissions, but N2 excludes that tool and its tests. Likewise, N1 does not redo Q2's Home resource map, N3 does not move Home-camera contracts, and N4 does not amend Q5's live-worker phase policy. No new generic live harness, scheduler, result database, vision route or game feature is proposed.

## Source ownership and integration

Separate agents can prepare and implement the packages in separate task-owned worktrees. Independence of purpose does not eliminate shared source files:

| Shared surface | Exact integration rule |
|---|---|
| N1 / V Q2: `tests/selection_rules.yaml`, selector regression modules, `tests/README.md` | N1 owns known skill-script mappings and inventory; Q2 owns Home screenshots/assets. Rebase and integrate these hunks serially with both recall expectations preserved. Neither package waits for all of V44. |
| N2 / V Q4 and runtime consumers: `script_runner.py` | N2 owns connected-runtime context/close methods plus the error-outcome callback in `_build_automation_runner_from_services`, with body/construction regressions. Q4 owns discovery/case composition. Check exact symbol ownership; share a landed equivalent fix. No observation, match-3 or PW wiring changes. |
| N2 / N3: preview-limit validation in `world_map_search.py` | N2 owns moving the current pure limit check ahead of live acquisition. N3 preserves that owner while extracting planning/formatting. Integrate N2's small validation seam before N3's preview delegation; N3 can develop the planning boundary independently. |
| N4 / active workflow edits: porting guide and one planning reference | Change only the validation-policy sentences and links. Preserve feature instructions, historical results and live-phase rules. |

N2 owns the three named CLI files; N3 does not edit them. N3 does not edit selector rules or runtime composition. N4 does not rewrite `AGENTS.md` or the implementation skill. No plan requires a V/M/PW feature hold. Heavy test capacity is resolved at execution time under the existing allocation; this document does not reserve CPU, instances or workers.

## Common execution and handback

Each linked plan is an agent brief with source scope, deliverables, tests and completion criteria. Read the applicable repository skills at assignment; establish checkout ownership before edits. Start from then-current main, preserve unrelated work, and resolve only actual symbol overlap. A shared-file conflict calls for serial integration of that slice, not expanding another epic's scope.

Use focused checks during development, then the existing affected gate once on a finished source candidate with downstream consumers. Keep a legitimate full fallback; do not follow it with another local full run. Documentation-only work needs links/read-through and `git diff --check`. No package needs a benchmark, real worker launch or a new live tour to establish its planned acceptance.

Hand back the exact candidate and diff, completed acceptance criteria, commands/results, selected-test evidence where relevant, and remaining material gaps. Keep generated evidence under ignored `.local-data/` or `.test-impact/`. Report any task-owned uncommitted paths and commit/push state. The user's publication request covers these planning documents; implementation commits, pushes and agent dispatch follow their later assignment.

## Suggested implementation models

These are task-specific recommendations using models exposed by the current Codex host on October 1, 2026, not measured PNC performance rankings. They follow the general [OpenAI model-selection guidance](https://developers.openai.com/api/docs/guides/latest-model) while respecting this host's available model IDs; a model mentioned in API documentation is not automatically available here.

| Plan | Model / reasoning effort | Reason |
|---|---|---|
| N1 | `gpt-6-astra` / `high` | Test-inventory migration and selector recall interact with imports, shared helpers and platform-specific process tests. Strong reasoning is useful at that infrastructure boundary. |
| N2 | `gpt-6-sol` / `high` | Concrete, bounded defects with existing cleanup owners and deterministic regressions. A strong general coding model should handle the implementation and error-path checks. |
| N3 | `gpt-6-astra` / `xhigh` | The contract/import closure and behavior-preserving split require the most architectural judgment of the four packages. |
| N4 | `gpt-6-luna` / `medium` | Two small policy-reference corrections with explicit scope and documentation-only acceptance. |

These choices do not dispatch agents or change any existing task's model. Escalate a specific unresolved design problem rather than assigning the largest model and effort to every mechanical follow-up.
