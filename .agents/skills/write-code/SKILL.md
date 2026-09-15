---
name: write-code
description: Implement scoped production code changes, fixes, refactors, tests, or scripts. Use for repository implementation work; use write-code-live only when validation may spend authorized in-game resources.
---

# Write Code

Implement the requested behavior through the smallest maintainable change and verify it in proportion to risk.

## Workflow

1. Read the affected owner, callers, tests, config, and any approved plan.
2. Establish PNC game behavior from user-confirmed facts, deterministic tests and fixtures, and saved or live UI/runtime evidence. Research official external documentation only when it can change the implementation.
3. Choose the simplest design that fully satisfies the request. Reuse canonical interfaces and refactor only when needed to avoid real duplication or conflicting ownership.
4. Implement a larger, coherent slice and add focused tests for changed behavior or likely regressions before running the test command.
5. Apply the scope-based validation policy below after the larger slice is complete.
6. For behavior that depends on live PNC or emulator state, follow the live section below.
7. Report the result, validation, and material remaining risk.

## Design Boundaries

- Preserve DRY ownership and SOLID boundaries. YAGNI limits speculative features and infrastructure; it does not excuse duplicated knowledge, mixed responsibilities, or brittle coupling.
- Do not add abstractions, alternate entry points, compatibility layers, configuration, or recovery paths for speculative future use.
- Handle normal behavior, explicit contracts, observed defects, and plausible high-impact failures.
- Cover a rare case only when explicitly required, observed, or justified by credible likelihood and material impact. Mere possibility or cheapness is not enough; otherwise keep the design simple and document the residual risk.
- Prefer typed domain models and actionable validation errors.
- Preserve unrelated changes and keep secrets out of output.

## Validation

Follow the repository runner and [`AGENTS.md`](../../AGENTS.md)'s Offline Validation policy. It owns module-only tests for low-level scoped fixes, Coverage.py-backed affected selection for higher-level multi-module fixes, and the pre-final-review/pre-push full-suite gates. Stop and report rather than accepting a full-suite fallback during development.
- Do not add or run redundant checks, exhaustive matrices, or live proofs when their realistic likelihood-and-impact reduction does not justify their cost.
- Do not repeat passing checks without a new change or risk.
- Do not add tests for implementation wording, reversible formatting, or remote low-impact branches.

## Live-Dependent Changes

Use [test-bluestacks-live](../test-bluestacks-live/SKILL.md) only when offline evidence cannot prove the changed boundary.

1. Define one observable precondition and success condition.
2. Run the scope-appropriate offline tests from Validation; do not run the full suite merely because a live probe follows.
3. Execute the smallest non-spending live probe through the canonical runtime and preserve the relevant artifacts.
4. If it fails, inspect the evidence, make a meaningful fix, and rerun that proof. Stop repeated attempts with unchanged evidence.
5. Convert a reproducible live defect into an offline regression when practical.

A live check is not required for documentation, internal refactors, or behavior fully proven below the emulator boundary. Use [write-code-live](../write-code-live/SKILL.md) when proof may spend resources.

## Completion

Finish when the requested behavior and likely regressions are covered by the smallest sufficient checks. State any required validation that was blocked; do not replace a missing live proof with unrelated extra offline testing.
