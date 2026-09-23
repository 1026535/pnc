---
name: manage-source-control
description: Establish Git checkout ownership before tracked edits, and manage requested branches, worktrees, commits, synchronization, integration, pushes, or cleanup while preserving user work.
---

# Manage Source Control

Perform only the Git operations needed for the requested delivery outcome.

## Authority And Safety

- Treat branch creation, commit, push, rebase, merge, target-branch update, branch deletion, and worktree removal as distinct actions. Do not infer authorization for later actions from an earlier one.
- Before modifying tracked files, inspect `git status --short --branch`, the current operation, upstream, and relevant worktrees. This applies to source, tests, config, fixtures, documentation, and plans.
- Preserve unrelated or unknown changes. Do not stash, reset, abort, commit, or move work owned by another task.
- Never force-push a default or protected branch. Use `--force-with-lease` on a rewritten private feature branch only when authorized and after verifying the expected remote tip.
- Prefix branches and worktrees created through this skill with `devin/` (for example `devin/workshop-submit-gates`) so Devin-authored work is distinguishable from `codex/` branches; where other repository docs prescribe a `codex/` prefix, `devin/` takes precedence for Devin-executed operations.

## Start Or Continue Work

1. Identify checkout ownership, the target branch, and the remote. Fetch when remote freshness matters, such as starting from the latest base, synchronizing, or landing.
2. Reuse an existing task-owned worktree when its changes belong to the task. Do not begin tracked edits in a shared or default-branch checkout. If unrelated changes, a conflict, an interrupted operation, or unclear ownership is present, create an isolated `devin/` branch and worktree from the requested base.
3. Keep commits coherent and stage only task-owned source, config, tests, plans, or fixtures.
4. Inspect generated and ignored output before staging; keep runtime products under `.local-data/` and test-selection evidence under `.test-impact/`.

Read-only review and ignored or local-only artifact work need no branch, worktree, commit, or remote backup. Tracked edits require an owned checkout; commit and push remain separately authorized actions.

## Synchronize Or Integrate

Before a rebase, merge, cherry-pick, or landing operation:

1. Fetch the relevant refs and inspect the merge base, unique commits, meaningful diffs, and overlapping paths.
2. Prefer rebase for a private feature branch and merge for shared history. Do not perform both against the same target without a concrete intervening change.
3. Resolve conflicts by requirements, canonical ownership, and tests; never choose a whole side solely to clear markers.
4. Run validation proportional to the combined change. A clean Git operation is not behavioral proof.
5. If landing or pushing, fetch once more immediately before the update. If the target moved, repeat only the affected integration analysis and validation.

Prefer fast-forward landing when the repository permits it. Push only the exact validated commit and never pull through unrelated uncommitted changes.

## Cleanup And Recovery

Delete branches or worktrees only when requested or clearly included in the delivery workflow. Verify the exact path/ref, ownership, and recoverability first.

After transferring task changes to another checkout, inspect and report residual edits in the source checkout. Remove them only when cleanup is authorized and the content is proven preserved by an immutable commit.

Use operation-specific abort commands only for operations started by the current task. Use reflog and immutable commit IDs for diagnosis; ask before discarding work or rewriting published history.

## Report

Summarize the branch/worktree used, base and final commit IDs when relevant, operations performed, validation, remote state, task-owned uncommitted paths, and anything intentionally retained. Omit exhaustive topology when no integration occurred.
