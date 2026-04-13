# PNC Automation AGENTS Guidelines

## Coding
- Make minimal, well-reasoned changes. Avoid duplicating existing code or logic.
- When new requirements arrive, do not patch a now-wrong design with more code. Re-evaluate the design and refactor so the result stays minimal, DRY, and easy to maintain.
- Prefer using existing, authoritative interfaces instead of reimplementing behavior.
- Prioritize clarity, documentation, and maintainability;
- Avoid duplicating logic / re-hardcoding logic at ALL COST.
- Always first make sure everything makes sense and that you have a very deep understanding of the intricacies of the context. Take time to analyze the codebase and current architecture. Take time to make sure we have a very clean and logical solution, with DRY code and a clean architecture, that integrates well with the current designs.
- Throw on unexpected conditions: do not silently swallow exceptions or ignore unexpected inputs—prefer throwing or asserting so issues surface during development and testing.

## General Architecture Requirements
1. Single canonical implementation per concept.
2. No duplicated logic (DRY).
3. Open-Closed extension model.
4. Fail-fast validation for invalid content.
5. Minimal boilerplate and complexity.
6. Strong types are preferred

## Documentation Requirements
- Add concise Python docstrings for every class and function we add or modify, including private helpers when they contain meaningful logic.
- Keep documentation high value and concise: explain responsibility, important interactions/ownership, non-obvious behavior, invariants, and relevant limitations.
- Add brief in-code comments for complex logic when the intent or constraint would not be obvious from the code and docstrings alone.
- Do not write comments that only restate the signature.

## Non-negotiables (MUST)
- MUST avoid duplicating logic: no “same concept, different place” helpers.
- MUST refactor when requirements shift responsibilities (ownership changes).
- MUST delete obsolete code after refactors; do not keep parallel APIs.
- MUST fail fast on unexpected conditions; do not silently swallow invalid states.
- MUST prefer porting everything to the current format and never add support for old legacy code/serializations; update authored config, scripts, and persisted data as needed so all data uses the latest schema.

## Project Overview
- Work happens in **pnc** only.

## Coding Style
- Python code targets Python 3.13+ and should follow PEP 8 with 4 spaces, type hints, and clear module boundaries.
- Keep imports at the top of the file, grouped standard library first, then third-party packages, then local `pnc_automation` imports.
- Favor idiomatic Python and the standard library first; introduce third-party dependencies only when they provide clear value and are compatible with `pyproject.toml`.
- Prefer dataclasses, enums, and typed domain models over ad hoc dictionaries, tuples, or hard-coded strings when representing stable concepts.
- Keep functions and methods concise, focused, and readable; prefer early returns and compact conditional logic for simple cases.
- Favor comprehensions, decorators, lambdas, functional tools, assignment expressions, and structural pattern matching when they keep the code readable; avoid them when they obscure intent.
- Handle `None` explicitly with guard clauses, early returns, or exceptions.
- Do not implement heuristics that guess or probe for multiple field, attribute, or key names. Use the precise intended symbol name or a well-defined interface.
- Use `pathlib.Path` for filesystem paths and the existing storage/artifact helpers when they already model the concept.

## Development Tips
- Runtime package code lives under `pnc_automation/`; tests live under `tests/`; live/manual tools live under `tools/`; authored automation YAML lives under `scripts/`; user configuration examples live under `config/`.
- Treat `config/*.example.yaml` as documented templates. Do not overwrite real local config files such as `config/accounts.yaml` or `config/castle_targets.yaml` unless the task explicitly asks for it.
- Screenshot, OCR, navigation, and live-run evidence is generated under `artifacts/` and temporary test directories. Use it for debugging, but do not treat fresh generated output as source code.
- Reuse the existing application runner, script runner, observation, selector, navigation, and storage abstractions instead of adding parallel entry points.
- BlueStacks/ADB behavior belongs behind the existing emulator/session/client interfaces so offline tests can keep using fakes.
- If unrelated workspace changes already exist, continue the requested task and do not stop for those changes; never revert unrelated files unless the user explicitly asks.

## Testing
- Tests live under `tests/` and use Python's standard `unittest` runner. Keep normal tests offline/headless: they must not require BlueStacks, ADB, live game state, network access, or credentials unless they are explicitly opt-in live smoke tests.
- Run the full offline suite with `python -m unittest discover -s tests`.
- Run targeted tests with module or class paths, for example `python -m unittest tests.test_world_map_search` or `python -m unittest tests.test_flows_and_tasks.SomeTestClass.test_specific_case`.
- The package requires Python 3.13+ per `pyproject.toml`. If imports fail in a fresh environment, install the package dependencies before testing.
- `tests/__init__.py` redirects temporary files into `.tmp_test_workspace`; treat `.tmp_test_workspace/`, `.tmp_test_artifacts/`, and `artifacts/` as generated test/runtime output unless the task specifically concerns persisted evidence.
- Prefer adding focused unit coverage beside the related behavior in the existing `tests/test_*.py` module. Reuse shared builders and fakes from `tests/test_support.py` instead of inventing parallel fixtures.
- Keep integration-style coverage deterministic by using saved screenshots, authored YAML, fake sessions, and explicit fixtures. Do not make ordinary tests depend on live emulator timing or the current account state.

### Live smoke tests
- Live smoke tests are opt-in `unittest` modules named `tests/test_live_*_smoke.py`; they are skipped unless their environment flag is set.
- The shared account-navigation and spatial-surface smoke tests use `PNC_RUN_LIVE_SMOKE=1`, with optional `PNC_LIVE_SMOKE_CONFIG`, `PNC_LIVE_SMOKE_ACCOUNT`, and `PNC_LIVE_SMOKE_SCRIPT`.
- The chat workflow smoke test uses `PNC_RUN_LIVE_CHAT_SMOKE=1`, with optional `PNC_LIVE_CHAT_CONFIG`, `PNC_LIVE_CHAT_ACCOUNT`, and `PNC_LIVE_CHAT_BASELINE_SECONDS`.
- The home-city atlas smoke test uses `PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE=1`, with optional `PNC_LIVE_SMOKE_CONFIG`, `PNC_LIVE_HOME_CITY_MAP_SMOKE_ACCOUNTS`, `PNC_LIVE_HOME_CITY_MAP_SMOKE_SEED`, and `PNC_LIVE_HOME_CITY_MAP_SMOKE_TARGETS`.
- The world-map movement calibration smoke test uses `PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION=1`, with optional `PNC_LIVE_WORLD_MAP_MOVEMENT_CONFIG` and `PNC_LIVE_WORLD_MAP_MOVEMENT_ACCOUNT`.
- If no other live target is proposed, use the BlueStacks instance/account configured for `testing` with the PNC account/castle `pine cobaye 1`.
- Before running any live smoke test, verify BlueStacks is running, ADB can reach the configured instance, and the requested account/castle configuration exists under `config/`.

### Validation workflow (required)
- For pure code changes, run `python -m unittest discover -s tests` before finishing.
- For narrow changes, run the most relevant targeted test first, then run the full offline suite once the focused failure is fixed.
- For changes touching live runtime boundaries, selectors, screen classification, navigation, or ADB/emulator integration, run the full offline suite and call out which live smoke flag should be used for optional manual validation.
- For selector-registry or navigation-selector changes, include the relevant offline tests and consider the live tools only when real-device evidence is needed: `python tools/validate_navigation_selectors.py`, `python tools/update_selector_registry.py`, `python tools/discover_selector_registry.py`, or `tools/run_selector_discovery_workflow.bat`.
- For world-map movement calibration changes, run the relevant offline tests first, then use `python tools/run_world_map_movement_calibration.py` or the live calibration smoke flag when a live account is available.

### Test failure handling
- Read the failing assertion and traceback first; most tests are ordinary `unittest` failures and should not need a custom log parser.
- If a live smoke test fails, inspect the generated observation artifacts and screenshots under `artifacts/` for the run label before changing code.
- If a test writes stale generated evidence or temporary files, clean only the generated output needed for the rerun. Never remove authored config, scripts, reviewed plans, or user changes as part of test cleanup.

## DRY enforcement checklist (required)

Before you finish:
- Confirm there is exactly one canonical implementation per concept.
- Confirm there are no duplicated predicates/formatters/parsers.
- Confirm obsolete code paths/interfaces were removed.
- Confirm naming reflects ownership (policy vs consumer).
