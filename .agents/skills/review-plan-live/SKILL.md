---
name: review-plan-live
description: Review an implementation plan against repository evidence and, when needed, bounded live BlueStacks evidence. Use when asked to validate, challenge, or live-check a plan; do not use for ordinary code review or initial plan creation.
---

# Review Plan Against Live Evidence

Determine whether the plan is sound enough to implement and whether any claimed live readiness is supported.

## Workflow

1. Establish the plan, requirements, user decisions, and intended implementation or promotion decision.
2. Inspect the relevant code, tests, config, artifacts, and prior results before considering live work.
3. Identify consequential claims whose failure would change architecture, safety, acceptance, or likely behavior. Do not inventory cosmetic details or remote theoretical cases.
4. Use [references/assumption-evidence-matrix.md](references/assumption-evidence-matrix.md) only when several consequential claims need traceability. A short review can use ordinary findings.
5. Reuse adequate evidence. Run one bounded live observation only when a material current-runtime question remains; follow [../test-bluestacks-live/SKILL.md](../test-bluestacks-live/SKILL.md).
6. Reconcile contradictions and issue the readiness verdict.

## Review Standard

- Prioritize correctness, unsafe mutation, canonical ownership, likely regressions, and missing acceptance evidence.
- Preserve explicit user facts unless repository or live evidence materially contradicts them.
- A screenshot proves visible state, not an unobserved transition. A green test proves a claim only when the test exercises it.
- Do not demand every target be tested. Require multiple targets only when the contract names them, configuration differs materially, or evidence shows target-dependent behavior.
- Do not repeat live work to accumulate confidence after the decision is adequately supported.
- Stop before any state-changing action unless the exact action, target, and budget are authorized.

## Verdicts

Report:

- `implementation_ready`: whether the design can be implemented responsibly;
- `promotion_ready`: whether the plan's claimed live deployment or unattended-use gate is supported, when that question is in scope; and
- material limitations or next evidence needed.

Use `passed`, `applicability_skip`, or `blocked` target results only when a target matrix is actually warranted.

## Output

Lead with actionable findings ordered by severity and plan location. Include the supporting repository or live evidence, the correction direction, the verdicts, and commands run. If no findings remain, say so and name only material evidence limits.

When asked to update the plan, also follow [../create-plan/SKILL.md](../create-plan/SKILL.md). For implementation review, use [../review-code/SKILL.md](../review-code/SKILL.md).
