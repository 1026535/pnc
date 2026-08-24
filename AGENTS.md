# PNC Automation Agent Guide

## Mission

Work only in this `pnc` repository. Treat each task as done only when the requested behavior is implemented, verified at the right level, and explained clearly. For feature requests, do not stop at a plan unless the user explicitly asks for planning only.

## Operating Workflow

1. Understand the task and current architecture before editing. Read the relevant code, tests, configs, scripts, prompts, artifacts, and prior plans.
2. Use internet research when current external behavior matters, especially for OpenAI/Codex, BlueStacks, Android/ADB, test strategy, library APIs, security, or platform-specific behavior. Prefer official docs and cite sources in the final answer when they shaped the work.
3. For non-trivial work, make a compact implementation plan internally or in the conversation, then execute it. Save a Markdown plan only when the user asks for a plan document or the task is too large to complete safely in one pass.
4. Implement in small, coherent slices. After each risky or live-relevant slice, run the smallest useful validation before continuing.
5. Before saying "done", run the required offline tests and, for live/runtime changes, the smallest relevant live validation path. If live validation cannot run, state the exact blocker and command that remains.

## Architecture Rules

- Keep one canonical implementation per concept.
- Avoid duplicated logic, predicates, parsers, formatters, selectors, workflow steps, and config schemas.
- Prefer refactoring ownership when requirements shift instead of adding compatibility shims or parallel APIs.
- Fail fast on invalid configuration, unexpected screen state, malformed artifacts, or unsupported content.
- Prefer precise typed models, dataclasses, enums, and well-defined interfaces over ad hoc dictionaries or string conventions.
- Reuse existing application runner, script runner, observation, selector, navigation, storage, BlueStacks, ADB, and artifact abstractions.
- Delete obsolete code paths after migrations. Do not preserve legacy serializations unless the user explicitly asks and the plan explains why.

## Coding Style

- Python targets 3.13+ and follows PEP 8 with 4-space indentation and type hints.
- Keep imports at the top, grouped standard library, third-party, then local `pnc_automation` imports.
- Prefer `pathlib.Path` for filesystem paths.
- Keep functions focused and readable. Use comprehensions, pattern matching, decorators, or functional tools only when they improve clarity.
- Handle `None` explicitly with guard clauses, early returns, or exceptions.
- Do not guess among multiple possible field, attribute, or key names. Use the precise intended symbol or a defined interface.
- Add concise docstrings for every class or function you add or modify, including private helpers with meaningful logic.
- Add comments only for non-obvious intent, invariants, or constraints.

## Repository Map

- Runtime package code: `pnc_automation/`
- Offline tests and fakes: `tests/`
- Live/manual tools: `tools/`
- Authored automation YAML: `scripts/`
- Reusable run script guidance: `scripts/README.md`
- User config examples: `config/*.example.yaml`
- Real local config: `config/accounts.yaml`, `config/castles.yaml`, `config/castle_targets.yaml`
- Runtime evidence: `artifacts/`
- Reviewed plans and implementation reviews: `reviewed_plans/`
- Local workflow skills: `skills/`
- Prompt templates: `prompts/`

## Config And Secrets

- Treat `config/*.example.yaml` as documented templates.
- Do not overwrite real local config files unless the user explicitly asks.
- Do not paste credentials, tokens, or account secrets into final answers.
- When validating configs, prefer typed loaders and existing validation helpers over string parsing.
- For `castle_targets.yaml`, validate against `accounts.yaml`, `castles.yaml`, and, when relevant, live BlueStacks roster evidence.

## Testing Strategy

- Tests use Python `unittest`. On this Windows workspace, prefer `py` when the `python` alias is unavailable.
- Full offline suite: `py -m unittest discover -s tests`.
- Targeted tests: `py -m unittest tests.test_world_map_search` or `py -m unittest tests.test_flows_and_tasks.SomeTestClass.test_specific_case`.
- Keep normal tests offline/headless. They must not require BlueStacks, ADB, live game state, network access, or credentials.
- Use saved screenshots, authored YAML, fake sessions, and explicit fixtures for deterministic integration-style coverage.
- When a live screenshot exposes a bug, add a regression test. Prefer a committed deterministic fixture when safe and reasonably sized; otherwise use `tests/data/local_fixture_artifacts.json` copied from the example.
- Screenshot-backed tests must skip clearly when local-only fixtures are not configured.
- Test shape should follow risk: many fast unit tests, fewer integration tests, and a narrow set of high-value live smoke tests for real emulator behavior.

## Live BlueStacks Validation

Live smoke tests are opt-in modules named `tests/test_live_*_smoke.py`.

- Shared account navigation and spatial surface: `PNC_RUN_LIVE_SMOKE=1`
- Chat workflow: `PNC_RUN_LIVE_CHAT_SMOKE=1`
- Home-city atlas/building navigation: `PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE=1`
- World-map movement calibration: `PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION=1`

Before live validation:

- Confirm the requested account, castle target, and BlueStacks display name exist in `config/`.
- Let the canonical runtime launch the configured BlueStacks instance when it is not already running.
- Verify ADB reaches the resolved instance before continuing.
- Use the configured `adb_path` and `bluestacks_config_path`; do not hard-code ports or device ids.
- If no live target is specified, use the currently active castle on the configured `testing` BlueStacks instance. Do not select or switch castles unless the user explicitly names a castle and authorizes that navigation.

During live validation:

- Start with the smallest smoke path that proves the risky boundary.
- Use observation-based waits and existing runner/navigation abstractions.
- Inspect generated screenshots, OCR JSON, logs, and observation artifacts under `artifacts/` before changing code after a live failure.
- Preserve artifact paths in the final answer when they explain a result or failure.
- Treat live validation as required for completion when a configured BlueStacks account is available and the change touches live runtime behavior, selectors, screen classification, navigation, ADB/emulator integration, or authored live workflows.

## Validation Requirements

- Pure code changes: run `py -m unittest discover -s tests` before finishing.
- Narrow changes: run the most relevant targeted test first, then the full offline suite.
- Selector or navigation changes: run relevant offline tests and consider `py tools/validate_navigation_selectors.py`, `py tools/update_selector_registry.py`, `py tools/discover_selector_registry.py`, or `tools/run_selector_discovery_workflow.bat`.
- World-map movement calibration changes: run relevant offline tests, then use `py tools/run_world_map_movement_calibration.py` or the live calibration smoke flag when live access is available.
- Skill-only or documentation-only changes: run the relevant validator when one exists; otherwise run `git diff --check`.
- Always report commands run and whether they passed, failed, or were skipped.

## Planning, Review, And Skills

- Use `skills/create-plan` for substantial implementation plans.
- Use `skills/write-code` for implementation-heavy work.
- Use `skills/review-code` for review requests or commit/diff audits.
- Use `skills/test-bluestacks-live` for live BlueStacks validation.
- Treat `prompts/` as legacy/local inspiration, not as a reason to skip current best practice.
- For reviews, findings come first, ordered by severity, with file and line references. If no issues are found, say so and name remaining risk.

## Working Tree Safety

- The working tree may already be dirty. Never revert or overwrite user changes unless explicitly asked.
- If unrelated changes exist, ignore them. If they affect the requested task, work with them and mention the interaction.
- Do not use destructive commands such as `git reset --hard` or `git checkout --` unless the user clearly requests that operation.
- Clean only generated evidence needed for reruns. Never remove authored config, scripts, reviewed plans, or user work as test cleanup.

## Done Checklist

Before final response:

- Confirm the implementation matches the requested behavior, not only the plan.
- Confirm exactly one canonical implementation exists for each concept touched.
- Confirm no duplicated predicates, parsers, formatters, selectors, workflows, or config schemas were introduced.
- Confirm obsolete code paths/interfaces were removed or migrated.
- Confirm naming reflects ownership.
- Confirm offline validation passed or explain failures.
- Confirm live validation passed for live/runtime changes, or state the exact blocker and remaining command.
- Summarize changed files and important artifacts without exposing secrets.
