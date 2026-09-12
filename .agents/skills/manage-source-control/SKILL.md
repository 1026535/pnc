---
name: manage-source-control
description: Manage Git branches, worktrees, synchronization, integration, conflicts, pushes, or cleanup while preserving user work. Use only when the request includes source-control operations.
---

# Manage Source Control

Perform only the Git operations needed for the requested delivery outcome.

## Authority And Safety

- Treat branch creation, commit, push, rebase, merge, target-branch update, branch deletion, and worktree removal as distinct actions. Do not infer authorization for later actions from an earlier one.
- Inspect `git status --short --branch`, the current operation, upstream, and relevant worktrees before writing.
- Preserve unrelated or unknown changes. Do not stash, reset, abort, commit, or move work owned by another task.
- Never force-push a default or protected branch. Use `--force-with-lease` on a rewritten private feature branch only when authorized and after verifying the expected remote tip.

## Start Or Continue Work

1. Identify the target branch and remote. Fetch when remote freshness matters, such as starting from the latest base, synchronizing, or landing.
2. Use the existing clean task branch when appropriate. Create an isolated `codex/` branch and worktree from the requested base when the current checkout is dirty, conflicted, interrupted, or owned by other work.
3. Keep commits coherent and stage only task-owned source, config, tests, plans, or fixtures.
4. Inspect generated and ignored output before staging; keep runtime products under `.local-data/` and test-selection evidence under `.test-impact/`.

Do not create a branch, worktree, commit, or remote backup merely as ceremony when the request only needs a local edit or review.

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

Use operation-specific abort commands only for operations started by the current task. Use reflog and immutable commit IDs for diagnosis; ask before discarding work or rewriting published history.

## Report

Summarize the branch/worktree used, base and final commit IDs when relevant, operations performed, validation, remote state, and anything intentionally retained. Omit exhaustive topology when no integration occurred.
