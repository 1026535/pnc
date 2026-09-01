---
name: review-plan-live
description: Review implementation plans against requirements, repository state, saved artifacts, and bounded live evidence; identify contradicted or unproven assumptions and produce a traceable readiness verdict. Use when asked to review, validate, challenge, or live-check a plan or its assumptions. Do not use for an ordinary code-only review or to create a new plan from scratch.
---

# Review Plan Against Live Evidence

## Outcome

Determine whether a plan is correct enough to implement and whether its runtime slices are proven enough to promote. Do not equate a plausible design, passing unit tests, one screenshot, or one successful target with complete validation.

## Workflow

1. Establish the review authority: the plan, user decisions, requirements, current code/config, tests, artifacts, and target runtime. Preserve explicit user facts as stakeholder-confirmed inputs; do not silently turn them into hypotheses to retest.
2. Extract atomic claims from the plan. Include requirements, architecture ownership, selectors, screen transitions, target applicability, timing/reset behavior, mutation limits, recovery behavior, acceptance criteria, and promotion gates.
3. Build the matrix in [references/assumption-evidence-matrix.md](references/assumption-evidence-matrix.md). Give every material claim a stable ID, source location, consequence if false, required evidence method, target, status, and evidence path. No blank material rows.
4. Inspect repository evidence before live work. Read the relevant implementation, configs, tests, prior plans, screenshots, observation/OCR sidecars, logs, and run summaries. Check that cited tests would fail for the stated defect and that artifacts prove the claimed state or transition.
5. Identify only the live questions whose answers could change architecture, selectors, state transitions, safety policy, applicability, or promotion. Reuse adequate current artifacts; do not repeat live actions merely to accumulate screenshots.
6. For PNC/BlueStacks live questions, read and follow [../test-bluestacks-live/SKILL.md](../test-bluestacks-live/SKILL.md) and [../create-plan/references/live-evidence.md](../create-plan/references/live-evidence.md). Use the canonical configured runtime, verify the exact instance/account/castle, capture a typed baseline, take one bounded safe action at a time, capture the result, and stop when the question is answered.
7. Stop at mutation boundaries unless the user has explicitly authorized the exact action, target, and budget. Planning or review permission alone never authorizes building, claiming, purchasing, spending, marching, gathering, attacking, changing formation, switching accounts/castles, or other state changes.
8. Reconcile evidence with the plan. A contradiction becomes a finding and a plan correction; it is not averaged away by supporting evidence elsewhere. An unknown or unclassified runtime state interrupts that target and remains unresolved until classified.
9. Issue two distinct verdicts:
   - `implementation_ready`: the design and non-mutating assumptions are sufficiently established to begin the named slices.
   - `promotion_ready`: every required offline and live target cell has passed or has an explicitly approved applicability skip, with no unresolved safety-critical assumption.
10. Update the plan only when requested. Preserve the findings and evidence matrix in the reviewed plan or a companion review document, and do not erase failed attempts or unresolved assumptions.

## Review Rules

- Findings come first, ordered by severity, with plan location, claim, evidence, impact, and correction direction.
- Distinguish `observed`, `repository-proven`, `stakeholder-confirmed`, `inferred`, and `unknown`. State the provenance next to the claim.
- A screenshot proves one screen state. A transition requires a typed baseline, named action, typed post-state, and artifacts from the same bounded trace.
- Process exit success is not proof of the UI postcondition.
- One castle or instance is not a proxy for another named target. Every applicable runtime slice needs a target-matrix result: `passed`, `applicability_skip`, or `blocked`.
- Validate the riskiest or architecture-changing assumption before polishing lower-impact details.
- Keep canaries small and attributable. Do not overlap live experiments when one could contaminate another's result.
- Treat time-dependent evidence explicitly. Record timezone, reset boundary, sample date, and whether the claim is known policy or an observed occurrence.
- When geometry supplies click coordinates and OCR supplies meaning, verify that OCR does not silently become the coordinate source.

## Output Contract

Return or save:

1. findings ordered by severity;
2. the assumption/evidence matrix;
3. bounded live traces and artifact paths;
4. target-by-slice validation results;
5. separate implementation and promotion verdicts;
6. exact unresolved questions, mutation authorizations, or future temporal conditions; and
7. commands run with pass, fail, or skip outcomes.

If no findings remain, say so and name residual evidence limits. Do not call a plan validated when material rows are `unproven`, `contradicted`, `live_blocked`, or at an unauthorized mutation boundary.

## Conditional Routing

- When the request includes rewriting or extending the plan after review, also read [../create-plan/SKILL.md](../create-plan/SKILL.md).
- When the request compares completed implementation against the plan, also read [../review-code/SKILL.md](../review-code/SKILL.md).
- When a live proof would spend resources or mutate game state, do not use `write-code-live` unless the user separately provides exact authorization.
