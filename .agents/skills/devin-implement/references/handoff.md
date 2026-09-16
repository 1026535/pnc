# Worker handoff

Adapt this brief to the package. A fresh Devin session has filesystem/CLI access, but does not inherit the lead's conversation or Codex-only tools. Use paths accessible from its assigned worktree. The launcher supplies worker-role restrictions.

Include only fields relevant to this assignment. Specify concrete edits or a bounded evidence question and the point at which the worker should return. Reference established rules and decisions once; do not copy the full plan or restate the launcher restrictions.

```text
Outcome and acceptance:
Concrete implementation result or evidence question, essential edge cases,
non-goals, and package handback boundary.

Starting state and ownership:
Exact repository/worktree, branch, baseline SHA, owned components/files, existing
changes to preserve, dependencies, integration destination, and commit ownership.

Authority and decisions:
Agreed intent/plan, canonical owners, entry points, resolved approach/interfaces,
migration boundaries, and relevant reference paths. Ordinary worker discretion
and decisions reserved for the lead.
Name the ledger's writer when one is shared.

Validation:
Selected checks or contract-based scope, reusable passing evidence, and ownership.
Identify lead-only tools and reserved resources that affect this package.
Read focused file ranges and summarize machine-readable test results. Leave large
logs, observations, exports, and screenshots on disk; cite exact evidence paths.

Escalation:
Return for lead reasoning if evidence challenges the approach, a material
decision arises, or repeated attempts yield no useful new evidence. Report the
exact failure, relevant changes, attempted remedies/results, and decision needed.
Distinguish observed facts from preliminary hypotheses. Routine repairs remain
within the package; do not redesign the solution or exhaust speculative fixes.

Compact handback:
READY_FOR_REVIEW / NEEDS_LEAD / BLOCKED / FAILED.
Result, commit/ref and pending changes (including new files), material decisions,
checks/results/durations with evidence paths, and unresolved work or risks.
Verify cited artifacts exist and correspond to the reported run/ref; label
hypotheses and limitations explicitly. Summarize results rather than pasting logs
or narrating the investigation. Do not create a periodic progress/context file.
READY_FOR_REVIEW describes this package, not necessarily the entire feature.
NEEDS_LEAD returns an unresolved reasoning question; BLOCKED identifies a missing
resource or external dependency. Preserve partial work on either handback.
Confirm owned tests/processes finished or identify external work by exact run ID.
Include required repository notices and proposed ledger entries for its writer.
```

For related follow-ups and corrections, send only the current ref/changes, new decisions or finding IDs with evidence, concrete requested work, and affected checks. Reuse the same session and request a delta handoff. Do not replay unchanged instructions or ask the worker to rediscover the lead's analysis.
