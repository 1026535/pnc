---
name: review-code
description: Review code, diffs, commits, branches, or completed implementations for actionable defects and meaningful test gaps. Use for explicit review requests; do not use as a separate ceremony for ordinary implementation self-checks.
---

# Review Code

Find issues that would justify changing the code.

## Workflow

1. Establish the requirement and exact diff, commit, branch, or implementation in scope.
2. Read the changed code plus enough callers, tests, config, and ownership context to understand its behavior.
3. Check correctness, security, data integrity, canonical ownership, migration completeness, and likely regressions.
4. Inspect whether tests exercise the changed contract and would fail for the suspected defect.
5. Run the smallest relevant static or test command when it materially improves confidence. Use the repository's affected selection for broader changes; do not run the full suite by habit.
6. Report findings first, ordered by severity.

## Review Bar

- Include only evidence-backed, actionable issues.
- Prioritize normal behavior, explicit contracts, observed failures, and high-impact safety cases.
- Report a rare edge case only when it is plausible in this system and its impact justifies implementation complexity. Do not invent defensive machinery for remote, low-impact possibilities.
- Treat DRY ownership and SOLID boundaries as maintainability requirements. Do not call necessary separation or deduplication overengineering merely because it adds structure.
- Flag duplication or overdesign when it creates competing ownership, unnecessary APIs, or maintenance cost.
- Omit style preferences unless they obscure correctness or maintainability.
- Do not require tests that mirror implementation, assert wording, or cover negligible-risk branches.
- Judge added safeguards and requested validation by realistic likelihood, impact, and execution cost; flag resource-heavy protection with negligible expected value.
- Live validation is relevant only when the reviewed behavior depends on the emulator or current UI boundary.

## Output

For each finding include severity, file and line, the concrete problem, impact, and the smallest clean fix. If there are no findings, say so and mention only material residual risk or untested boundaries.

Use `prompts/ReviewPlan.txt` as optional local style context, not as a mandatory extra review pass.
