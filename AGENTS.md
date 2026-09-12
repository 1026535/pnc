# PNC Automation Agent Guide

## Scope And Priorities

- Limit edits to this `pnc` repository unless the user explicitly requests another location. Reading required skills and external documentation is allowed.
- Let the user's requested outcome and explicit constraints define the task. Make reasonable assumptions for reversible, in-scope decisions; ask only when a choice would materially change behavior, the live target, resource spending, or a destructive action.
- Explicit user instructions take precedence over skill guidelines. If a skill causes work to pause, remain unfinished, or diverge from the request, identify the exact skill instruction and explain its effect.
- For action requests, continue through implementation and appropriate verification. Stop at a plan only when the user asks for planning or the applicable planning skill requires a reviewable plan before implementation.
- Preserve unrelated user changes. Never expand a task merely because adjacent cleanup is possible.

## Working Method

1. Inspect the smallest relevant set of code, tests, configs, scripts, artifacts, and prior plans needed to understand ownership and behavior.
2. Research current external behavior when it can affect correctness, especially OpenAI/Codex, BlueStacks, Android/ADB, library APIs, platform behavior, or security. Prefer primary or official sources and cite sources that materially shape the result.
3. For non-trivial work, state or keep a compact plan with explicit acceptance checks. Save a plan document only when requested or required by the planning workflow.
4. Implement in small, coherent slices. After a risky slice, run the narrowest check that can expose the likely failure before continuing.
5. Treat validation as an engineering loop: inspect failure evidence, classify the cause, fix the implementation or fixture, and rerun the bounded proof. Stop only on a confirmed postcondition or a precise authorization, user-input, or external-state blocker.
6. Report the outcome, changed files, validation commands and results, and any remaining risk or blocked live command.

## Architecture And Implementation

- Keep one canonical owner for each concept. Do not duplicate predicates, parsers, formatters, selectors, workflows, or config schemas.
- Reuse the existing application runner, script runner, observation, selector, navigation, storage, BlueStacks, ADB, and artifact abstractions.
- Prefer typed models, dataclasses, enums, and explicit interfaces over ad hoc dictionaries or string conventions.
- Reject invalid configuration, malformed artifacts, and unsupported content with actionable errors. For transient emulator or screen state, use bounded waits or existing recovery paths, then fail with captured evidence.
- When requirements change, migrate callers to the canonical interface and remove obsolete paths. Keep compatibility behavior only when the task requires it, and test the compatibility contract.
- Keep changes focused. Do not combine feature work with unrelated refactors.

## Python Style

- Target Python 3.13+ and follow PEP 8 with 4-space indentation and type hints.
- Keep imports at the top, grouped as standard library, third-party, then local `pnc_automation` imports.
- Prefer `pathlib.Path` for filesystem paths.
- Keep functions focused and names explicit. Use comprehensions, pattern matching, decorators, or functional tools only when they improve clarity.
- Handle `None` and error cases explicitly. Do not guess among multiple possible field, attribute, or key names; use the defined interface.
- Add concise docstrings to public APIs and to helpers whose contract or reasoning is not obvious. Avoid docstring churn in unrelated code.
- Add comments only for non-obvious intent, invariants, or constraints.

## Repository Map

- Runtime package: `pnc_automation/`
- Offline tests and fakes: `tests/`
- Live and manual tools: `tools/`
- Authored automation YAML: `scripts/`
- Script authoring guide: `scripts/README.md`
- Config templates: `config/*.example.yaml`
- Runtime evidence: `artifacts/`
- Reviewed plans and implementation reviews: `reviewed_plans/`
- Local workflow skills: `.agents/skills/`
- Shared browser/session instructions: `instructions/`
- Legacy prompt references: `prompts/`
- Package metadata and Python requirement: `pyproject.toml`

## Config And Secrets

- Treat `config/*.example.yaml` as the documented templates.
- `config/accounts.yaml`, `config/castles.yaml`, `config/daily_maintenance.yaml`, and `tests/data/local_fixture_artifacts.json` are local files. Do not modify them unless the user explicitly requests it.
- `config/castle_targets.yaml` is tracked authored config. Change it only when the task requires target-catalog changes.
- Never echo or paste credentials, tokens, account secrets, or sensitive local config values into prompts, patches, commands, logs, artifacts, or final responses. Redact such values if they already appear in captured output.
- Use typed loaders and existing validation helpers. Validate `castle_targets.yaml` against `accounts.yaml`, `castles.yaml`, and relevant live BlueStacks roster evidence when target identities change.

## Offline Testing

- Tests use `unittest`. On Windows, use `py` when the `python` alias is unavailable.
- Start with the smallest relevant command, such as `py -m unittest tests.test_world_map_search` or a specific test method.
- Run `py -m unittest discover -s tests` for cross-cutting changes, shared interfaces, config schemas, authored workflows, test infrastructure, or any change whose regression surface is broader than the targeted tests. For a genuinely isolated low-risk change, targeted validation may be sufficient; explain that choice in the final response.
- Keep ordinary tests offline and headless. They must not require BlueStacks, ADB, live game state, network access, or credentials.
- Use saved screenshots, authored YAML, fake sessions, and explicit fixtures for deterministic integration coverage.
- When live evidence exposes a bug, add a deterministic regression test when safe and reasonably sized. Otherwise use the local fixture mechanism based on `tests/data/local_fixture_artifacts.example.json`.
- Screenshot-backed tests must skip clearly when local-only fixtures are not configured.
- Do not add tests for documentation-only edits or reversible formatting changes that have no behavioral contract.

## Validation By Change Type

- Documentation or skill-only changes: run the relevant validator when one exists; otherwise run `git diff --check`.
- Selector or navigation changes: run targeted offline tests and `py tools/validate_navigation_selectors.py`. Run registry discovery or update tools only when the task requires regenerating selector data.
- World-map movement calibration changes: run relevant offline tests, then `py tools/run_world_map_movement_calibration.py` or the opt-in live calibration smoke when live access is available.
- Runtime, selector, screen-classification, navigation, ADB/emulator, and authored live-workflow changes require the smallest relevant live proof when a configured BlueStacks target is available.
- Once required checks pass, broaden or repeat them only when the change, a failure, or an unresolved risk justifies it.

## Live BlueStacks Validation

Use `.agents/skills/test-bluestacks-live` for live validation. Available opt-in smoke flags are:

- Account navigation and shared spatial surface: `PNC_RUN_LIVE_SMOKE=1`
- Chat workflow: `PNC_RUN_LIVE_CHAT_SMOKE=1`
- Daily-task workflow: `PNC_RUN_LIVE_DAILY_TASK_SMOKE=1`
- Home-city atlas and building navigation: `PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE=1`
- World-map movement calibration: `PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION=1`

Before and during a live run:

- Confirm the account, castle target, and BlueStacks display name in `config/`. Let the canonical runtime launch the configured instance when needed and verify ADB connectivity through the resolved instance.
- Use configured `adb_path` and `bluestacks_config_path`; never hard-code ports or device IDs.
- If no live target is named, use the currently active castle on the configured `testing` instance. Do not select or switch castles unless the user names a castle and authorizes that navigation.
- Preserve castle inventories for every configured account independently of live execution eligibility. `accounts[].live_roles` is the authority and assignments may be reassigned; names such as `testing`/`smoke_test`, `serious_stuff`/`live_testing`, `mega_old_acc`/`daily_canary`, and `main`/`read_only` describe the current roster examples, not immutable workflow rules. Validate the intended role before constructing a live runtime.
- Every PNC process must acquire the canonical process-scoped lease for each BlueStacks display name before connecting through ADB. Keep the reservation across preparation, all dependent work, and cleanup. Acquisition waits are bounded. Multi-instance work must declare the complete bundle up front so the lease manager can acquire it in canonical order without hold-and-wait deadlocks.
- Multi-step live workflows must use one scoped reservation for their entire sequence: `with api.use_account(...)` for one prepared account, or `with api.reserve_accounts((...))` when several accounts/instances are involved. One-shot direct calls may use an isolated lease, but do not release and reacquire between dependent steps. The active API scope rejects calls for accounts outside its declared bundle.
- The host-management CLI reads only host bindings, roles, metadata, and memory policy; it must remain usable without credentials or castle files. It reloads valid host authority on every monitor sample and again under lease before destructive mutation. Pending recovery intent and cooldown are durable, with at most 3 launch attempts per pass and 9 persisted attempts total; role or identity revocation blocks pending launches.
- Run `py -m pnc_automation.bluestacks_management monitor --watch` under host supervision when automatic leak recovery is desired. It uses working set, repeated samples, durable intent, and a cooldown; it may restart only an idle instance after acquiring its canonical lease. It skips busy instances and must never auto-restart an account carrying `read_only`. Watch mode continues monitoring peers after per-instance failures, while fatal host/configuration failures exit nonzero and are emitted through the bounded rotating state log without raw secrets.
- Register the Windows supervisor with `tools/register_bluestacks_memory_monitor_task.ps1`. Its action must run the resolved windowless Python interpreter directly, not a PowerShell or `py` launcher wrapper: stopping a wrapper task can leave the actual monitor orphaned.
- Run `py -m pnc_automation.bluestacks_management restart-open --require-maintenance-window --include-read-only` only for the explicit 01:55 America/Toronto open-instance maintenance boundary. The legacy Python tool paths remain compatibility shims.
- The daily 01:55 America/Toronto maintenance boundary may restart every configured instance that is open at its initial snapshot, including an open `main`. It must acquire that complete open-instance bundle before stopping anything and must leave configured closed instances closed.
- Default to read-only or non-spending proof. Any live validation that can spend in-game resources requires the exact action, target, and budget from the current request or a user-approved execution plan and must use `.agents/skills/write-code-live`. Do not request duplicate confirmation when those details are complete.
- Start with the smallest smoke path that proves the risky boundary. Use observation-based waits and existing runner/navigation abstractions.
- On failure, inspect screenshots, OCR JSON, logs, and observation artifacts under `artifacts/` before changing code. Preserve relevant artifact paths in the final response.

## Local Skills

Read the applicable `SKILL.md` completely before taking the actions it governs.

- `.agents/skills/create-plan`: substantial plans and roadmaps.
- `.agents/skills/review-plan-live`: plan audits that require repository and bounded live evidence.
- `.agents/skills/write-code`: production implementation, fixes, refactors, tests, and scripts.
- `.agents/skills/review-code`: code, diff, commit, branch, or implementation reviews.
- `.agents/skills/test-bluestacks-live`: live emulator validation and diagnosis.
- `.agents/skills/write-code-live`: implementation with bounded in-game resource spending authorized by the current request or a user-approved execution plan.
- `.agents/skills/control-in-app-browser`: browser automation through the selected browser surface.
- `.agents/skills/consult-chatgpt-pro`: explicit or planning-required, repository-grounded consultation with ChatGPT Pro.
- `.agents/skills/implement-with-luna-global`: explicit delegation of substantial implementation to Luna workers.
- `.agents/skills/manage-source-control`: feature branches, worktrees, rebases, merges, conflict resolution, pushes, and branch cleanup.

Treat `prompts/` as legacy inspiration, not as a substitute for the applicable skill or current best practice. If a skill creates a blocker or conflicts with the requested outcome, identify the exact instruction and explain the impact instead of silently changing scope.

## Replacement Workflow Ports

Before adding or migrating a workflow onto the replacement navigation core, read [`instructions/CORE_WORKFLOW_PORTING.md`](instructions/CORE_WORKFLOW_PORTING.md). It defines the canonical runtime, typed parser, effect gate, constrained context, offline checks, bounded non-spending proof, final Home evidence, and the existing authorizer/executor/journal boundary for future resource-changing work.

## Code Review Rules

- Lead with actionable findings ordered by severity, with file and line references and the cleanest fix direction.
- Review correctness, ownership, duplication, migration completeness, test quality, security, and behavioral regressions. Omit style-only findings unless they obscure correctness or maintainability.
- If no findings remain, say so and identify residual test gaps or assumptions.

## Source Control Workflow

Use `.agents/skills/manage-source-control` for new feature branches, branch synchronization, rebases, merges, cherry-picks, conflict resolution, pushes to a base branch, and branch or worktree cleanup.

- Start every new endeavor from the freshly fetched remote target-branch head. When the current checkout contains unrelated changes, conflicts, or an interrupted Git operation, preserve it and create an isolated `codex/` feature worktree from that remote commit.
- Before integrating, inspect the merge base and commits and diffs unique to both the feature and target branches. Resolve overlaps according to the intent, tests, and canonical ownership of both changesets; never select one side wholesale merely to clear conflicts.
- Prefer rebasing a local or private feature branch onto the latest target. Do not rewrite a published or shared branch without explicit authorization; merge the target into it when shared history must be preserved.
- Review and validate the combined result, fetch the target again immediately before landing, and repeat synchronization if it moved. Never force-push the default or a protected branch.

## Working Tree Safety

- Inspect the working tree before editing. Do not revert, overwrite, or reformat unrelated user changes.
- If existing changes overlap the task, preserve them and work with the resulting state; mention the interaction in the final response.
- Do not use destructive Git or filesystem commands unless the user clearly requests the operation and the exact target has been verified.
- Clean only generated evidence needed for reruns. Never remove authored config, scripts, reviewed plans, or user work as test cleanup.

## Completion Criteria

Before finishing, confirm that the requested behavior is implemented, the architecture has one canonical path per touched concept, obsolete paths were migrated or intentionally retained, and verification matches the actual risk. Report every validation command as passed, failed, or skipped. For required live validation that cannot run, state the exact blocker and the command that remains. Do not expose secrets in the handoff.
