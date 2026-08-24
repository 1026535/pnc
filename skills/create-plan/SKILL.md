---
name: create-plan
description: Create rigorous implementation plans, architecture plans, migration plans, project plans, subplans, and planning documents before execution, requiring bounded live-evidence gathering from a configured BlueStacks instance when material screenshots or current runtime UI state are not already evidenced. Use when the user asks Codex to create, draft, review, improve, or save a plan; asks for a roadmap, implementation strategy, phased breakdown, design plan, execution plan, or plan file; or wants a deep planning pass before code or operational work.
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
8. Break the work into deliverable-oriented phases. Each phase must have concrete files or components, dependencies, acceptance criteria, and tests or review checks.
9. Surface risks early. Include migration risks, compatibility risks, live/runtime risks, performance risks, data risks, and test gaps. Pair each risk with a mitigation or validation step.
10. Finish with an execution checklist. Make the next actions ordered, minimal, and unambiguous.

## Live Evidence For Planning

Treat live evidence as a planning input, not merely an implementation-phase recommendation. Before drafting the target design, write down the specific evidence questions whose answers could change selectors, state transitions, architecture, or validation. If any question is material and repository evidence cannot answer it, perform the bounded live workflow now.

The fact that the final behavior is state-changing does not justify skipping all live inspection. Navigate safely up to the last read-only screen, capture the available controls and classifications, then stop before the mutating action. Mark the unobserved transition `unknown` and name the authorization needed to cross it. Skip the whole live workflow only when adequate current artifacts already answer the evidence questions or a precondition/stop condition prevents a safe attempt.

When live evidence is needed, use the `test-bluestacks-live` workflow and the repository's canonical runtime abstractions. Resolve the requested account and BlueStacks display name from configuration; if the user gives no live target, use whichever castle is currently active on the configured `testing` instance, verify its identity through observation, and do not select or switch castles. If the user explicitly names a castle, resolve and verify it before any castle navigation. If the configured instance is closed, allow `BlueStacksInstanceResolver` to launch it and wait for the configured ADB endpoint. Do not hard-code an emulator port, device ID, or executable path.

Gather evidence in bounded, reversible increments. Capture a baseline observation, perform at most one existing navigation action, capture the post-action observation and artifacts, and decide whether the evidence is sufficient before continuing. Prefer `ScreenFlowPlanner`, selector-based `ActionRequest` objects, `ObservationService`, and existing live smoke/discovery tools over raw coordinate clicks or ad hoc ADB commands. Read [references/live-evidence.md](references/live-evidence.md) for the safety budget, allowed actions, stop conditions, and evidence reporting contract.

Never perform a state-changing game action solely to obtain planning evidence. Without explicit user authorization, do not build, research, collect, claim, send mail or chat, march, gather, attack, purchase, spend resources, switch accounts, log out, or change authored configuration. If the requested evidence requires one of those actions, stop and record the exact unknown or ask for authorization rather than guessing.

If live evidence was required but could not be gathered, include the attempted target, command or canonical entry point, reached state, artifact paths if any, exact stop condition, and the design decisions that remain provisional. A plan that only says “gather live evidence later” without an attempted bounded run fails this skill.

## Planning Principles

- Treat a plan as an implementation artifact, not a brainstorming note.
- Prioritize current authoritative external best practice when it conflicts with an unproven local habit; adapt it to local architecture instead of copying it blindly.
- Decompose by deliverable or capability, then by task. Avoid phases that only describe time order without a completed outcome.
- Prefer architecture that removes duplication instead of adding compatibility shims, legacy support, or parallel code paths.
- Make dependencies explicit: prerequisites, sequencing constraints, shared interfaces, data migrations, and validation dependencies.
- Define done with observable acceptance criteria, not vague confidence.
- Include validation that matches risk: focused tests first, full offline suites for broad code changes, and opt-in live smoke tests when runtime boundaries require them.
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
- Every material current-UI evidence question is answered by an adequate repository artifact, an observed bounded live trace, or a documented failed live attempt with a precise stop condition.
- Required live evidence was not postponed into an implementation phase merely because the request was planning-only or the final action would be state-changing.
- Any live evidence has a target, baseline, bounded action trace, post-action artifact, and explicit stop or failure reason.
- The plan distinguishes live observations from inferences and unresolved unknowns, and preserves artifact paths without exposing secrets.
