---
name: review-code
description: Perform rigorous code reviews of diffs, commits, branches, implementations, review documents, and proposed changes. Use when the user asks Codex to review code, inspect a commit, find bugs, identify inconsistencies, assess test coverage, evaluate architecture, produce a review document, or verify whether an implementation fully addresses a plan.
---

# Review Code

## Overview

Review for defects that matter: correctness, architecture, maintainability, security, test coverage, and behavioral regressions. Prioritize findings that would change the code, and keep style-only remarks out unless they obscure correctness or maintainability.

## Workflow

1. Establish the review scope. Identify the commit, diff, branch, files, plan, review doc, or stated requirement being reviewed.
2. Read the changed code and enough surrounding context to understand ownership, invariants, callers, tests, and data flow.
3. Research current best practice when the diff depends on external APIs, platform behavior, security rules, or test frameworks. Prefer primary sources and cite them if they influence a finding.
4. Check the implementation against the requirement or plan. Look for missing phases, partial migrations, stale compatibility paths, and mismatched ownership.
5. Inspect tests. Verify that tests would fail for the bug they claim to catch, cover edge cases, and use deterministic offline fakes unless live coverage is explicitly needed.
6. Run tests or static checks when appropriate and feasible. Read failures before inferring causes.
7. Report findings first, ordered by severity, with file and line references. Include only actionable issues supported by evidence.

## Review Checklist

- Correctness: Does the code do what the caller, user, plan, or contract requires for normal and edge cases?
- Architecture: Is there one canonical implementation per concept, with responsibilities in the right owner?
- Simplicity: Is the design smaller, clearer, or more direct than plausible alternatives?
- Duplication: Are predicates, parsers, selectors, formatters, schemas, workflows, and validation rules defined once?
- Tests: Are new and existing tests targeted, deterministic, meaningful, and aligned with the risk?
- Security and robustness: Are inputs validated, errors surfaced, credentials protected, and external calls bounded?
- Maintainability: Are names, types, docstrings, and comments useful without restating the code?
- Migration: Are obsolete formats, paths, or APIs removed instead of carried forward in parallel?

## Output Contract

Lead with findings. For each finding include:

- Severity: critical, high, medium, or low.
- Location: file and line.
- Problem: the concrete bug, risk, missing requirement, or regression.
- Fix direction: the cleanest way to address it without duplicating logic.

If no issues are found, say so clearly and mention residual test gaps or assumptions. When asked to produce a review document, create a Markdown file in the requested location or follow repository conventions for reviewed plans.

## PNC Defaults

- Treat `prompts/ReviewPlan.txt` as the local review style: find bugs, inconsistencies, missing parts, duplication, simplification opportunities, and direct improvements.
- For implementation-plan reviews, verify every plan phase and validation requirement was actually completed.
- For PNC runtime changes, check offline tests first and call out the relevant opt-in live smoke flag only when live validation is needed.
