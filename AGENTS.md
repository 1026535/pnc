# PNC Automation Agent Guide

## Scope And Priorities

- Limit edits to this repository unless the user requests another location.
- Let the requested outcome and explicit constraints define the task. Make reasonable assumptions for reversible decisions; ask only when a choice materially changes behavior, authorization, live targets, spending, or destructive actions.
- Explicit user instructions take precedence over skill guidelines. If a skill blocks or redirects the work, identify the exact instruction and explain its effect.
- Complete action requests through implementation and proportionate verification. Stop at a plan only for planning requests.
- Preserve unrelated user changes and avoid adjacent cleanup.

## Proportionality

- Preserve correctness, DRY ownership, and SOLID boundaries. YAGNI limits speculative capability; it does not justify duplicated knowledge, mixed responsibilities, or brittle coupling.
- Choose the smallest maintainable design that solves the current requirement. “Smallest” means the least machinery consistent with DRY and SOLID, not the fewest files, types, or lines. Do not add abstractions, configuration, compatibility layers, recovery systems, or extension points for hypothetical future needs.
- Optimize for normal behavior, explicit contracts, observed failures, and likely regressions.
- Handle a rare case in code or tests only when an explicit contract requires it, it has been observed, or credible likelihood and impact justify its implementation and maintenance cost. Mere possibility or cheapness is not enough. Otherwise note the residual risk without expanding the implementation.
- Judge safeguards by realistic likelihood, impact, and cost. Do not add checks, retries, recovery paths, test matrices, or live runs whose expected protection is negligible; retain controls for credible high-impact or irreversible harm.
- Run the smallest validation that can disprove the change. Once required checks pass, stop unless a failure, broad dependency, or unresolved material risk justifies more.

## Working Method

1. Inspect only the code, tests, configs, artifacts, and plans needed to understand the affected behavior and owner.
2. Research current external behavior only when it can change the answer. Prefer official or primary sources and cite sources that materially shape the result.
3. Keep plans compact and acceptance-focused. Save a plan only when requested or required by the planning workflow.
4. Implement small, coherent changes through existing interfaces. After a risky slice, run the narrowest relevant check.
5. Inspect actual failure evidence before changing code. Iterate while new evidence or a meaningful fix exists; stop repeated attempts that reproduce the same result without changing the diagnosis.
6. Report the outcome, changed files, validation results, and any material remaining risk or blocker.

## Architecture And Python

- Keep one canonical owner per concept. Reuse existing runner, observation, selector, navigation, storage, emulator, ADB, and artifact abstractions.
- Prefer typed models and explicit interfaces over ad hoc dictionaries or string conventions. Reject invalid inputs with actionable errors.
- Use bounded recovery for expected transient emulator states. Do not build generalized recovery for unobserved states.
- Migrate callers and remove obsolete paths when requirements change. Keep compatibility only when required.
- Target Python 3.13+, PEP 8, type hints, grouped top-level imports, and `pathlib.Path`.
- Keep functions focused. Add docstrings to public APIs and non-obvious helpers; add comments only for intent or invariants.

## Repository Map

- Runtime: `pnc_automation/`
- Tests: `tests/`; testing guide: `tests/README.md`
- Live/manual tools: `tools/`
- Authored workflows: `scripts/`; guide: `scripts/README.md`
- Config templates and authored config: `config/`
- Runtime evidence and reports: `.local-data/` (ignored)
- Test-selection evidence: `.test-impact/` (ignored)
- Plans: `plans/`
- Skills: `.agents/skills/`; shared instructions: `instructions/`

## Game Behavior Evidence

- Establish game behavior from user-confirmed facts, deterministic tests and fixtures, saved UI/runtime artifacts, and, when necessary, one bounded observation through the existing live workflow.
- Distinguish user-confirmed, repository-proven, artifact-observed, live-observed, inferred, and unknown findings. Resolve material conflicts with current UI observations.
- Add or correct a scoped workflow note when the task establishes reusable behavior. Include artifact or workflow provenance, the observation date and build when available, confidence, automation implications, and remaining uncertainty.
- Keep generated screenshots, observations, logs, and indexes under ignored `.local-data/`. If evidence is absent, reproduce it through the supported UI workflow or report the gap; absence alone does not authorize live access, account changes, or resource spending.

## Local Data, Config, And Secrets

- Put generated screenshots, logs, archives, reports, timing data, and selector output under `.local-data/`. Keep `.test-impact/` for test-selection scratch and CI evidence.
- Keep authored fixtures and package data tracked, including `tests/data/`, `pnc_automation/**/data/`, examples, plans, and selector catalogs.
- Treat `config/*.example.yaml` as sanitized templates containing synthetic values only.
- All other `config/*.yaml` and `config/*.yml` files are ignored local configuration. Do not modify them or `tests/data/local_fixture_artifacts.json` unless requested.
- Never expose credentials, tokens, account secrets, or sensitive config values. Redact them from captured output.

## Offline Validation

- Use the repository runner instead of raw discovery; raw `unittest discover` can bypass portable inventory and resource rules.
- During development, run the smallest relevant module or component group after a meaningful change. Do not rerun a passing check for unchanged code.
- For an ordinary source change with broader consumers, run `py tools/run_tests.py affected --base origin/main --explain` once on the finished candidate. Add `--dry-run` only when selection or fallback needs inspection. Reuse a worker's passing result for the same candidate and scope instead of running it again.
- Let `affected` expand to full for shared contracts, test infrastructure, unknown ownership, or other fail-closed cases. Do not follow a passing full fallback with a separate local `full`. CI owns the merge-candidate check; run local `full` only for an explicit request or a concrete risk the selector cannot cover.
- Keep task worktrees free of unrelated untracked files; an unknown file can make `affected` select the full suite. Preserve unknown files rather than deleting them to change test selection.
- Use `measure` commands only for requested timing, coverage, or scheduled dependency-learning work.
- Keep portable tests offline and headless. Add deterministic tests for changed behavior and likely regressions; do not test implementation wording, reversible formatting, or speculative low-impact edge cases.
- Documentation or skill-only changes need the relevant validator, if any, plus `git diff --check`; they do not require unit or live tests.

## Live BlueStacks Validation

Use `.agents/skills/test-bluestacks-live` when the request or changed behavior depends on ADB, emulator state, live UI timing, selectors, navigation, or a real workflow transition.

- Prefer saved evidence and offline tests. Run one smallest relevant live smoke; do not run every flag, castle, or instance unless the contract or observed variability requires it.
- Resolve targets from config, treat `accounts[].live_roles` as authority, and use configured ADB paths and instance resolution.
- Acquire the canonical process-scoped lease before ADB access. Hold one scoped reservation across dependent steps; declare multi-instance bundles up front. The outer phase owns cleanup and preserves pre-existing instances by default.
- If no castle is named, use the active castle on the configured `testing` instance. Never switch accounts or castles without explicit authorization.
- Default to non-spending proof. Resource spending requires the exact action, target, and budget from the request or an approved plan and must use `.agents/skills/write-code-live`.
- Inspect `.local-data/artifacts/` after a failure. Repeat a live action only after a relevant implementation or state change, and never repeat an irreversible action outside its authorized budget.

Opt-in flags:

- Shared navigation/spatial: `PNC_RUN_LIVE_SMOKE=1`
- Chat: `PNC_RUN_LIVE_CHAT_SMOKE=1`
- Daily task: `PNC_RUN_LIVE_DAILY_TASK_SMOKE=1`
- Home-city map: `PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE=1`
- World-map calibration: `PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION=1`

## Skill Routing

Read the applicable `SKILL.md` completely before its workflow.

- Use the plan, review, implementation, live-test, browser, and source-control skills only when their descriptions match the request.
- `create-plan-with-chatgpt-pro` may route to `consult-chatgpt-pro`; direct Pro consultation otherwise requires an explicit request.
- `implement-with-luna-global` is explicit-only.
- Use `devin-implement` for requested Devin implementation delegation and `devin-game-knowledge` for bounded consultation. When the user delegates live testing to Devin, use `devin-live-test` for all applicable live execution, including follow-up validation; the lead reviews its curated evidence and owns acceptance. `test-bluestacks-live` remains the canonical live policy.
- Before porting a workflow to the replacement navigation core, read `instructions/CORE_WORKFLOW_PORTING.md`.

## Review And Source Control

- Reviews lead with actionable findings ordered by severity and file/line. Prioritize correctness, security, data loss, behavior, ownership, and meaningful test gaps; omit theoretical or style-only findings that would not justify a change.
- Use `.agents/skills/manage-source-control` before tracked edits and for branch, worktree, commit, synchronization, integration, push, or cleanup operations.
- Before modifying tracked files, including documentation and plans, confirm the checkout is task-owned. Reuse its worktree when existing changes belong to the task; do not edit a shared or default-branch checkout. If ownership is unclear or unrelated work is present, use an isolated `codex/` worktree before editing.
- Preserve unrelated changes. Do not use destructive Git/filesystem commands without explicit authorization and verified targets.
- Keep generated output out of Git. Before staging, use `git status --short --ignored` and inspect unexpected paths with `git check-ignore -v`.

## Completion

Finish when the requested behavior is implemented and the smallest sufficient checks pass. For modifying tasks, inspect final status and report task-owned uncommitted paths plus commit and push state; a commit in another checkout does not make the original clean. Report commands as passed, failed, or skipped. For a required live check that cannot run, give the exact blocker and remaining command. Mention only material residual risks and never expose secrets.
