---
name: write-code
description: Implement production code changes, bug fixes, refactors, tests, scripts, and repo modifications. Use when the user asks Codex to write code, implement a plan, address review findings, fix bugs, add features, refactor architecture, update tests, or make changes in a codebase while preserving correctness, maintainability, iterative validation, and live testing for functional runtime behavior.
---

# Write Code

## Overview

Make small, coherent code changes that improve long-term code health. Ground decisions in current authoritative documentation when external APIs, libraries, security practices, or platform behavior matter; otherwise prefer local architecture and tests.

## Workflow

1. Understand the request and current system before editing. Read the relevant files, nearby tests, authored plans, configs, and existing abstractions.
2. Research current best practice when the change touches external libraries, platform APIs, security, testing frameworks, or runtime behavior. Prefer primary documentation and cite sources in the final response when research shaped the implementation.
3. Choose the smallest design that fully solves the problem. Keep changes scoped, but refactor when the existing design would otherwise force duplication or parallel behavior.
4. Implement through the repository's canonical interfaces. Do not add alternate entry points, legacy schema support, duplicate parsers, duplicate formatters, or hard-coded copies of existing rules.
5. Validate inputs and invariants explicitly. Fail fast on unexpected states instead of silently swallowing invalid content.
6. Add or update focused tests beside the behavior. Use deterministic offline tests first; use live or integration checks when the changed boundary requires them.
7. For functionality that affects live runtime behavior, selectors, navigation, screen classification, ADB/emulator integration, or authored live workflows, use the live-development loop below. A live failure is normally engineering feedback, not the end of the task: inspect its evidence, patch the implementation or fixture, rerun the smallest relevant proof, and continue until the slice is confirmed or a named external blocker remains.
8. Run the narrowest useful validation first, then the repo-required suite for the risk level. Fix failures by reading the assertion, traceback, screenshots, logs, or artifacts before changing code.
9. Summarize what changed, what was verified, and any remaining risk.

## Code Quality Rules

- Keep changes reviewable and cohesive. If the request implies many independent concerns, separate them by deliverable or phase.
- Optimize for readability, maintainability, and correctness before cleverness.
- Prefer strong types, dataclasses, enums, existing domain models, and precise interfaces over ad hoc dictionaries or string conventions.
- Prefer deleting obsolete paths after migration over preserving compatibility shims.
- Keep comments and docstrings high value: explain responsibility, invariants, ownership, and non-obvious constraints.
- Treat security as part of coding, not a later phase: validate inputs, avoid unsafe defaults, keep secrets out of logs, and preserve least privilege.

## PNC Defaults

- Python targets Python 3.13+, `unittest`, `pathlib.Path`, type hints, and existing `pnc_automation` abstractions.
- Reuse the runner, script runner, observation, selector, navigation, storage, emulator, and ADB interfaces instead of adding parallel mechanics.
- For pure code changes, run `python -m unittest discover -s tests` before finishing when feasible.
- For narrow changes, run targeted tests first, then the full offline suite after the focused behavior passes.
- For functional PNC changes that depend on live game or emulator behavior, use the `test-bluestacks-live` skill and the smallest relevant opt-in live smoke path. If no BlueStacks instance is open, let the canonical runtime launch the configured instance before validating.
- Preserve unrelated user changes in the working tree.

## Live-development loop

For a live-dependent slice, track a concrete feature proof rather than treating a
smoke command as a one-shot check:

1. Define the precondition, one observable success condition, postcondition, artifact,
   and safe recovery path. For mutating work, also record the exact authorized budget.
2. Implement the smallest runnable slice and run its focused offline tests.
3. Run one bounded live probe through the canonical runtime. Capture baseline and
   post-action evidence, even when the probe fails.
4. Classify the result:
   - `confirmed`: the expected postcondition is observed; add the evidence to the
     feature result and continue to the next slice or final validation.
   - `applicability_skip`: the approved target-specific condition is observed and
     recorded; do not generalize it to other targets.
   - `engineering_failure`: selector, parser, navigation, timing, or reconciliation
     behavior is wrong or incomplete. Inspect artifacts, patch code/tests, rerun
     focused offline tests, and return to step 3.
   - `user_input_required`: identity, authorization, ambiguous game state, missing
     target choice, or an unresolved product rule prevents a safe next action. Ask
     one precise question and pause that slice.
   - `external_blocker`: the configured emulator, app, account, or required game
     state cannot be made available within the bounded workflow. Preserve the exact
     command, state, and artifact path; do not claim confirmation.
5. After each engineering iteration, update the deterministic regression test or
   fixture when the live evidence exposed a reproducible case. Do not repeat a
   mutation merely to obtain more evidence; repeat only a safe read-only probe or a
   separately authorized bounded mutation.
6. Finish only when the feature's success condition is confirmed, an approved skip is
   recorded, or a precise user-input/external-blocker disposition is handed off.

The live loop is bounded by the slice's action budget and observation/recovery budget,
not by an arbitrary single attempt. "Stop after the first failed live test" is not a
completion rule; "stop after repeated identical evidence without a meaningful code or
state change" is a valid diagnostic boundary.

## Quality Gate

Before finishing, confirm:

- Exactly one canonical implementation exists for each concept touched.
- No duplicated predicates, parsers, formatters, command paths, or test fixtures were introduced.
- Obsolete APIs and persisted formats were removed or migrated.
- Tests cover the changed behavior and likely regressions.
- Live/runtime functionality was exercised incrementally and in a final pass, or the final answer states the exact blocker and remaining command.
- The final answer names any validation that could not be run.
