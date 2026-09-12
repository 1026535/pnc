---
name: create-plan
description: Create or improve repository-grounded implementation, architecture, migration, or execution plans. Use for requested plans, roadmaps, phased strategies, or saved planning documents; use create-plan-with-chatgpt-pro when Pro input is requested.
---

# Create Plan

Create a plan that another engineer can execute and verify without prescribing work the task does not need.

## Workflow

1. Infer the objective and scope from the request and repository. Ask only when a missing choice would materially change the design.
2. Inspect the current owner, callers, tests, config, relevant plans, and recent evidence. Research external behavior only when it affects the design.
3. Describe the current state and the smallest target design that satisfies the requirement.
4. Break work into deliverables with concrete acceptance checks and dependencies.
5. Match validation to risk: focused or affected offline tests for ordinary slices, full validation only for broad integration, and live proof only for behavior that depends on current emulator state.
6. State material assumptions, tradeoffs, migration needs, and unresolved decisions.

## Proportional Planning

- Preserve DRY ownership and SOLID boundaries. YAGNI rejects speculative capability, not the structure needed to avoid duplication, mixed responsibilities, or brittle coupling.
- Prefer existing interfaces and one canonical owner. Choose the least machinery that remains maintainable, not merely the fewest components.
- Do not add extension points, compatibility paths, generalized recovery, or configuration for hypothetical future requirements.
- Plan for the normal path, explicit contracts, observed failures, and likely regressions.
- Include a rare edge case only when an explicit contract requires it, it has been observed, or credible likelihood and impact justify its ongoing complexity. Mere possibility or cheapness is not enough; otherwise record it as a residual risk.
- Keep phases independently useful. Do not create a phase, matrix, checklist, or proof step solely to make the plan look comprehensive.
- Judge safeguards by realistic likelihood, impact, and cost. Do not prescribe tests that merely mirror implementation, repeat sufficient proof, or consume live resources for negligible expected protection.

## Live Evidence

Use repository artifacts first. Read [references/live-evidence.md](references/live-evidence.md) only when an unresolved current UI, selector, navigation, or emulator fact could materially change the plan and existing evidence is insufficient.

Planning does not automatically require launching BlueStacks. When live evidence is justified, use one bounded, non-spending observation targeted at the decision. Stop at any mutation boundary. Read [references/implementation-live-validation.md](references/implementation-live-validation.md) only when the plan actually changes a live runtime boundary.

Use multi-target matrices only when the feature contract names multiple targets or repository evidence shows meaningful target-specific variation. Do not require identical proof across interchangeable targets.

## Output

For a small plan, return objective, design, steps, validation, and material risks. For a substantial plan, add current state, scope/non-goals, migration, and open decisions. Skip empty sections.

When the user requests a saved plan, write it to the requested location or the repository's plan directory without overwriting unrelated work.

## Quality Check

Before finishing, confirm that:

- the design solves the requested outcome through one canonical path;
- each step has a useful deliverable and observable acceptance check;
- validation is sufficient but not repetitive;
- live work is included only where offline evidence cannot prove the behavior; and
- material unknowns are explicit without expanding minor possibilities into design requirements.
