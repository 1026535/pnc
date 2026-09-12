---
name: manage-source-control
description: Manage Git feature branches and integration safely. Use when starting an endeavor from the latest base-branch head, creating or syncing branches and worktrees, rebasing, merging, cherry-picking, resolving conflicts, pushing, cleaning merged branches, or recovering an interrupted Git operation.
---

# Manage Source Control

Keep each endeavor isolated, begin from the current remote base, understand both sides of an integration before changing history, and preserve user work throughout.

## Establish The Repository State

1. Read the applicable repository instructions and identify the requested outcome, target branch, remote, and whether push, merge, history rewrite, or branch deletion is authorized.
2. Fetch the relevant remote, then resolve its default branch from the remote HEAD unless the user or repository names another base. Do not assume `main`, and do not treat a stale local base branch as current.
3. Inspect `git status --short --branch`, the current branch and upstream, `git worktree list`, and the active operation reported by Git. Do not start a rebase, merge, cherry-pick, or branch switch inside a worktree that contains unrelated changes, unresolved conflicts, or another interrupted Git operation.
4. Preserve such a worktree exactly as found. Use a clean existing worktree or create an isolated one from the fetched remote base. Never stash, discard, reset, abort, or move another task's changes merely to make the current operation convenient.

## Start A New Endeavor

1. Fetch immediately before branching and record the full remote-base commit.
2. Create a new `codex/` feature branch from that exact remote-tracking commit, not from whichever branch happens to be checked out. Use a concise purpose-based suffix and verify that the branch name and worktree path are unused.
3. Use an isolated worktree when the current checkout is dirty, conflicted, running another Git operation, or owned by another active task. Keep one writer per worktree.
4. Report the feature branch, base ref, base commit, worktree, and upstream relationship. Do not push merely to establish a branch unless the request includes publishing it.

## Understand Divergence Before Integration

Fetch again, compute the merge base, and inspect both changesets before rebasing or merging. At minimum, examine:

- the commits unique to each side with a left/right or graph log;
- the three-dot feature diff from the merge base;
- the target-only diff from the same merge base;
- overlapping files, renamed or deleted files, generated artifacts, tests, plans, schemas, and canonical ownership boundaries; and
- equivalent changes that already landed under different commits.

Summarize what each side intended. Classify overlaps as independent, compatible, superseding, duplicated, or contradictory. Do not choose an integration strategy or conflict resolution from filenames or conflict markers alone.

## Synchronize The Feature Branch

1. Prefer rebasing a local or private feature branch onto the latest remote base so the eventual integration is linear and tests exercise the current target.
2. Treat a published or shared branch as shared history. Rebase it only when the user explicitly authorizes rewriting that branch and the remote tip is verified unchanged. Otherwise merge the latest base into the feature branch.
3. Require a clean feature worktree before synchronization. During conflicts, inspect the common ancestor and both stages, relevant commits, callers, tests, and repository plans. Resolve the combined intended behavior with one canonical owner; never accept `ours` or `theirs` wholesale without semantic evidence.
4. After every conflict batch, verify that no conflict markers or unmerged index entries remain, then continue the operation and inspect the resulting diff. If intent cannot be established safely, stop with the exact conflicting decisions instead of guessing.
5. If an operation started for this task cannot continue safely, use its matching abort command to return that isolated worktree to its recorded pre-operation state. Never abort an operation that predated the task, and never use `reset --hard` or destructive checkout as recovery.

## Review And Validate The Integrated Result

Treat a clean Git operation as insufficient proof. Review the full feature diff against the updated base, run validation proportional to the combined change, and inspect failures before proceeding. Recheck that neither side's behavior, migration, tests, documentation, or generated-source contract was silently lost.

Immediately before landing, fetch the target again. If its remote tip moved, repeat divergence analysis, synchronization, review, and affected validation against the new tip.

## Generated Local Data

Keep generated run products out of Git and separate from authored repository data:

- Use the repository-root `.local-data/` directory, created on demand and
  ignored by Git, for local runtime artifacts, chat/mail archives, reports,
  timing CSVs, selector discovery/validation output, screenshots, logs, state,
  coverage, and similar generated data.
- Keep `.test-impact/` for test-selection scratch and CI evidence. It is also
  ignored and must not be staged.
- Treat `tests/data/`, package `**/data/` directories, example configuration,
  selector catalogs, and reviewed plans as authored inputs unless the task
  explicitly changes them. Do not solve output pollution with a global
  `*.csv` or `*.json` ignore rule.
- Before staging, inspect `git status --short --ignored` and verify unexpected
  output with `git check-ignore -v <path>`. If a generated file is already
  tracked, preserve it by moving it into the matching `.local-data/` location,
  stage the old path's removal, and update the producing command's default.
  Never delete a generated result just to clean the worktree.

## Land And Publish

Follow repository protections and the user's requested delivery path:

- Prefer a pull request when branch protection, required review, CI, or repository policy expects one.
- For an authorized direct integration of a rebased branch, update a clean target worktree to the exact remote tip and use a fast-forward-only merge.
- Create a merge commit only when the repository or user wants an explicit integration boundary; inspect and validate the resulting tree before push.
- Never force-push a protected or default branch. Use `--force-with-lease` on a rewritten feature branch only with explicit authorization and only after verifying the expected remote tip.
- Treat pushing, merging a pull request, deleting a branch, and removing a worktree as distinct external or destructive actions. Perform only the actions included in the request.

After publishing, fetch and verify the remote ref or merged commit. Report the final branch topology, commits landed, validation, any retained worktrees or branches, and any remaining divergence.

## Cleanup And Recovery

Do not delete branches or worktrees as routine cleanup. When deletion is requested, verify the exact path and ref, confirm that the branch is merged or otherwise recoverable, check that no worktree or active task owns it, and distinguish local deletion from remote deletion.

Use `git reflog`, merge-base analysis, and immutable commit IDs for diagnosis and recovery planning. Ask before any recovery that would rewrite published history or discard commits or files.
