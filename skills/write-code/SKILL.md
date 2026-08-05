---
name: write-code
description: Implement production code changes, bug fixes, refactors, tests, scripts, and repo modifications. Use when the user asks Codex to write code, implement a plan, address review findings, fix bugs, add features, refactor architecture, update tests, or make changes in a codebase while preserving correctness, maintainability, and validation.
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
6. Add or update focused tests beside the behavior. Use deterministic offline tests first; use live or integration checks only when the changed boundary requires them.
7. Run the narrowest useful validation first, then the repo-required suite for the risk level. Fix failures by reading the assertion and traceback before changing code.
8. Summarize what changed, what was verified, and any remaining risk.

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
- Preserve unrelated user changes in the working tree.

## Quality Gate

Before finishing, confirm:

- Exactly one canonical implementation exists for each concept touched.
- No duplicated predicates, parsers, formatters, command paths, or test fixtures were introduced.
- Obsolete APIs and persisted formats were removed or migrated.
- Tests cover the changed behavior and likely regressions.
- The final answer names any validation that could not be run.
