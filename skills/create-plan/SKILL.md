---
name: create-plan
description: Create rigorous implementation plans, architecture plans, migration plans, project plans, subplans, and planning documents before execution. Use when the user asks Codex to create, draft, review, improve, or save a plan; asks for a roadmap, implementation strategy, phased breakdown, design plan, execution plan, or plan file; or wants a deep planning pass before code or operational work.
---

# Create Plan

## Overview

Create plans that are specific enough to execute, review, and verify. Favor deep context gathering, one canonical design per concept, explicit tradeoffs, clear work breakdown, and concrete validation over generic task lists.

## Workflow

1. Clarify the planning target only when required. Prefer inferring scope from the user's request, repository conventions, issue text, attached artifacts, or referenced documents.
2. Gather context before designing. Inspect relevant code, docs, configs, tests, prompts, schemas, recent plans, and generated evidence. When the user asks to prioritize internet best practice, or when current external APIs, standards, tools, or platform behavior materially affect the plan, research authoritative internet sources first and cite them in the final answer or plan.
3. State the objective in one or two sentences. Include the intended outcome, user-visible behavior, and any hard constraints.
4. Define scope boundaries. List in-scope work, non-goals, assumptions, and known unknowns.
5. Describe the current state. Name the existing architecture, ownership boundaries, canonical interfaces, and pain points the plan must respect or change.
6. Propose the target design. Identify the single canonical implementation for each concept, ownership of responsibilities, data model or API changes, extension points, and fail-fast validation rules.
7. Break the work into deliverable-oriented phases. Each phase must have concrete files or components, dependencies, acceptance criteria, and tests or review checks.
8. Surface risks early. Include migration risks, compatibility risks, live/runtime risks, performance risks, data risks, and test gaps. Pair each risk with a mitigation or validation step.
9. Finish with an execution checklist. Make the next actions ordered, minimal, and unambiguous.

## Planning Principles

- Treat a plan as an implementation artifact, not a brainstorming note.
- Prioritize current authoritative external best practice when it conflicts with an unproven local habit; adapt it to local architecture instead of copying it blindly.
- Decompose by deliverable or capability, then by task. Avoid phases that only describe time order without a completed outcome.
- Prefer architecture that removes duplication instead of adding compatibility shims, legacy support, or parallel code paths.
- Make dependencies explicit: prerequisites, sequencing constraints, shared interfaces, data migrations, and validation dependencies.
- Define done with observable acceptance criteria, not vague confidence.
- Include validation that matches risk: focused tests first, full offline suites for broad code changes, and opt-in live smoke tests when runtime boundaries require them.
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
