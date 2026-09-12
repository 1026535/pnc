---
name: create-plan
description: Create or improve repository-grounded implementation, architecture, migration, and execution plans. Use for plans, roadmaps, phased strategies, or saved planning documents when no ChatGPT Pro consultation is requested; use create-plan-with-chatgpt-pro when the user requests Pro input. In PNC, gather required bounded live evidence when material runtime evidence is unavailable.
---

# Create Plan

## Overview

Create plans that are specific enough to execute, review, and verify. Favor deep context gathering, one canonical design per concept, explicit tradeoffs, clear work breakdown, and concrete validation over generic task lists.

## Workflow

1. Clarify the planning target only when required. Prefer inferring scope from the user's request, repository conventions, issue text, attached artifacts, or referenced documents.
2. Gather context before designing. Inspect relevant code, docs, configs, tests, prompts, schemas, recent plans, and generated evidence. When the user asks to prioritize internet best practice, or when current external APIs, standards, tools, or platform behavior materially affect the plan, research authoritative internet sources first and cite them in the final answer or plan.
3. Apply the live-evidence gate before designing. Use repository artifacts first. When a current UI state, selector, navigation path, or emulator behavior is material and no adequate current artifact exists, live evidence is required: use the bounded workflow in [references/live-evidence.md](references/live-evidence.md) before finalizing the target design. A planning-only request is not a reason to skip safe observation. Do not defer required evidence into the plan as a future phase unless a bounded live attempt was made and hit a recorded stop condition. Do not make the user provide a screenshot when the configured runtime can safely capture the required evidence.
4. State the objective in one or two sentences. Include the intended outcome, user-visible behavior, and any hard constraints.
5. Define scope boundaries. List in-scope work, non-goals, assumptions, and known unknowns.
6. Describe the current state. Name the existing architecture, ownership boundaries, canonical interfaces, and pain points the plan must respect or change.
7. Propose the target design. Identify the single canonical implementation for each concept, ownership of responsibilities, data model or API changes, extension points, and fail-fast validation rules.
8. Break the work into deliverable-oriented phases. Each phase must have concrete files or components, dependencies, acceptance criteria, and tests or review checks. For runtime-affecting work, read [references/implementation-live-validation.md](references/implementation-live-validation.md) and attach a narrow offline-then-live validation gate to every implementation slice.
9. Surface risks early. Include migration risks, compatibility risks, live/runtime risks, performance risks, data risks, and test gaps. Pair each risk with a mitigation or validation step.
10. Finish with an execution checklist. Make the next actions ordered, minimal, and unambiguous.

## Live Evidence For Planning

Treat live evidence as a planning input. Before drafting the target design, identify the current-runtime questions whose answers could change selectors, state transitions, architecture, or validation.

When a material question is not answered by current repository artifacts, read and follow [references/live-evidence.md](references/live-evidence.md) completely and use the `test-bluestacks-live` workflow. That reference is the canonical owner of target resolution, observation budgets, allowed actions, stop conditions, evidence classifications, and reporting requirements.

A planning request authorizes bounded read-only observation within scope, but never a state-changing game action solely to obtain evidence. Gather evidence up to the mutation boundary and report the remaining unknown instead of guessing. A plan that merely postpones required evidence without the bounded attempt and disposition required by the reference fails this skill.

## Planning Principles

- Treat a plan as an implementation artifact, not a brainstorming note.
- Prioritize current authoritative external best practice when it conflicts with an unproven local habit; adapt it to local architecture instead of copying it blindly.
- Decompose by deliverable or capability, then by task. Avoid phases that only describe time order without a completed outcome.
- Prefer architecture that removes duplication instead of adding compatibility shims, legacy support, or parallel code paths.
- Make dependencies explicit: prerequisites, sequencing constraints, shared interfaces, data migrations, and validation dependencies.
- Define done with observable acceptance criteria, not vague confidence.
- Include validation that matches risk: focused tests first, full offline suites for broad code changes, and opt-in live smoke tests when runtime boundaries require them.
- Keep live-affecting slices small and promote them incrementally. Do not batch several unproven runtime behaviors behind one final smoke test.
- When the plan names live instances or castles, require a disposition for every planned target after every applicable live-affecting slice: `passed`, `applicability_skip`, or `blocked`. A missing matrix cell is not a pass.
- Treat live screenshots and observations as evidence, not as a substitute for understanding the code or a license for unbounded experimentation. Label each important claim as observed, inferred, or unknown.
- Keep the plan lean. Expand only where ambiguity, risk, or architecture warrants detail.

## Output Contract

When the user asks for a saved plan, create or update a Markdown file in the requested location. If no location is given, follow repository conventions for plans; otherwise use a clear name near related planning documents and avoid overwriting unrelated work.

For substantial implementation plans, use this structure:

- Title
- Context
- Goals
- Non-Goals
- Current State
- Target Design
- Implementation Phases
- Slice-by-Slice Live Validation Matrix
- Data, Config, and Migration Notes
- Validation Plan
- Risks and Mitigations
- Open Questions
- Execution Checklist

For smaller requests, provide the same information in a compact form and skip sections that would be empty.

## Quality Gate

Before finalizing a plan, confirm:

- The plan has one canonical implementation per concept.
- No duplicated predicates, parsers, formatters, workflows, or compatibility layers are proposed.
- Obsolete code paths and serialized formats are removed or migrated rather than preserved.
- Invalid inputs and unexpected states fail fast.
- Each phase has clear dependencies and acceptance criteria.
- Validation covers the changed behavior, architectural risk, and likely regressions.
- Every runtime-affecting slice identifies its mutation boundary, smallest offline test, exact opt-in live entry point, expected pre/post state, artifacts, recovery path, and stopping conditions.
- Every named live instance/castle has an explicit outcome for every applicable slice; skips name the unmet applicability condition and blockers name the remaining command or evidence needed.
- A slice cannot be promoted into an unattended routine until its offline checks and required target matrix pass. The next slice may be developed, but it must not hide or bypass a failed promotion gate.
- Every material current-UI evidence question is answered by an adequate repository artifact, an observed bounded live trace, or a documented failed live attempt with a precise stop condition.
- Required live evidence was not postponed into an implementation phase merely because the request was planning-only or the final action would be state-changing.
- Any live evidence has a target, baseline, bounded action trace, post-action artifact, and explicit stop or failure reason.
- The plan distinguishes live observations from inferences and unresolved unknowns, and preserves artifact paths without exposing secrets.
