---
name: manage-source-control
description: Manage Git feature branches and integration safely. Use when starting an endeavor from the latest base-branch head, creating or syncing branches and worktrees, rebasing, merging, cherry-picking, resolving conflicts, pushing, cleaning merged branches, or recovering an interrupted Git operation.
---

# Manage Source Control

Keep each endeavor isolated, begin from the current remote base, understand both sides of an integration before changing history, and preserve user work throughout.

The preferred lifecycle is:

1. Fetch the target branch and create a feature branch from its exact remote-tracking tip.
2. Commit coherent task changes on the feature branch and, when publishing is part of the request, push that feature branch to the remote before integration.
3. Fetch again, synchronize the feature branch with the newest target tip, and validate the resulting feature tree.
4. Fetch immediately before landing, integrate the feature into a clean target worktree with a fast-forward-only merge when possible, and push the target branch without force.

Use either rebase or merge to synchronize the feature with the target for a given change, not both redundantly. Rebase a private feature for the clean linear history; merge the target into a shared feature when preserving published history matters. A later target merge is appropriate only when the target moved after the rebase or a separate target changeset requires semantic integration.

`origin/main` (or `origin/master`) is a remote-tracking ref, not a working tree, and cannot be dirty. "Dirty main" means that a local checkout of `main` has uncommitted changes. A clean local target checkout is the desired steady state, but it must never be achieved by discarding, stashing, or hijacking work owned by another task. Never treat local changes as part of the remote branch or silently include them in a feature.

## Establish The Repository State

1. Read the applicable repository instructions and identify the requested outcome, target branch, remote, and whether push, merge, history rewrite, or branch deletion is authorized.
2. Fetch the relevant remote, then resolve its default branch from the remote HEAD unless the user or repository names another base. Do not assume `main`, and do not treat a stale local base branch as current.
3. Inspect `git status --short --branch`, the current branch and upstream, `git worktree list`, and the active operation reported by Git. Do not start a rebase, merge, cherry-pick, or branch switch inside a worktree that contains unrelated changes, unresolved conflicts, or another interrupted Git operation.
4. If a local `main`/`master` checkout is dirty, classify each change as task-owned, unrelated, or unknown before doing anything with it. Preserve unrelated or unknown changes exactly; do not stash, discard, reset, abort, reformat, or commit them under the current task. If task-owned changes are present, account for them explicitly and migrate them only when their ownership and intended feature scope are clear. Use a clean existing worktree or create an isolated one from the fetched remote base for all current-task writes.
5. Do not "clean" a target checkout by pulling, rebasing, merging, or committing through its uncommitted changes. If target work is needed, create a clean integration worktree from the fetched remote ref and leave the dirty checkout untouched.

## Start A New Endeavor

1. Fetch immediately before branching and record the full remote-base commit.
2. Create a new `codex/` feature branch from that exact remote-tracking commit, not from whichever branch happens to be checked out. Use a concise purpose-based suffix and verify that the branch name and worktree path are unused.
3. Use an isolated worktree when the current checkout is dirty, conflicted, running another Git operation, or owned by another active task. Keep one writer per worktree.
4. Make only coherent task commits on the feature branch. Before staging, inspect `git status --short --ignored` and verify that generated local data, secrets, and unrelated edits are excluded.
5. When publishing is authorized, push the feature branch to the remote at the first complete reviewable checkpoint and again after synchronization. This provides a reviewable/backup ref and allows CI or another reviewer to inspect the exact branch. Never push a dirty or partially staged worktree as if it were complete.
6. Report the feature branch, base ref, base commit, worktree, upstream relationship, and whether the remote feature ref is private or shared.

## Understand Divergence Before Integration

Fetch again, compute the merge base, and inspect both changesets before rebasing or merging. At minimum, examine:

- the commits unique to each side with a left/right or graph log;
- the three-dot feature diff from the merge base;
- the target-only diff from the same merge base;
- overlapping files, renamed or deleted files, generated artifacts, tests, plans, schemas, and canonical ownership boundaries; and
- equivalent changes that already landed under different commits.

Summarize what each side intended. Classify overlaps as independent, compatible, superseding, duplicated, or contradictory. Do not choose an integration strategy or conflict resolution from filenames or conflict markers alone.

## Synchronize The Feature Branch

1. After the feature checkpoint is pushed, fetch again and record the current target tip and remote feature tip. Inspect the merge base, commits unique to each side, the three-dot feature diff, target-only diff, and overlapping paths before changing history.
2. For a private feature branch whose remote tip contains only this task's published history, prefer `git rebase <remote>/<target>` for a linear tree. Because rebase rewrites the already-pushed feature ref, update it only with an explicit expected-value `--force-with-lease` after verifying that no other work was added. Do not use `--force`.
3. If the feature ref is shared, another agent's commits are present, or rewriting is not authorized, preserve its history by merging the latest remote target into the feature branch. Resolve overlaps by intent, ownership, tests, and plans - not by choosing one side wholesale.
4. Do not rebase and then immediately merge the same target into the feature merely to "be safe." If the target advances after the rebase, repeat the fetch/divergence check and synchronize once more; merge only when the shared-history rule or a distinct target changeset requires it.
5. Require a clean feature worktree before synchronization. During conflicts, inspect the common ancestor and all stages, relevant commits, callers, tests, and repository plans. After every conflict batch, verify that no conflict markers or unmerged index entries remain, inspect the combined diff, run affected validation, and push the synchronized feature ref.
6. If an operation started for this task cannot continue safely, use its matching abort command to return that isolated worktree to its recorded pre-operation state. Never abort an operation that predated the task, and never use `reset --hard` or destructive checkout as recovery.

## Review And Validate The Integrated Result

Treat a clean Git operation as insufficient proof. Review the full feature diff against the updated base, run validation proportional to the combined change, and inspect failures before proceeding. Recheck that neither side's behavior, migration, tests, documentation, or generated-source contract was silently lost.

Immediately before landing, fetch the target and feature refs again. If either remote tip moved, repeat divergence analysis, synchronization, review, and affected validation against the new tips. Never land from a stale `origin/main`/`origin/master` ref.

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
- For an authorized direct integration, update a clean target worktree to the exact remote target tip, merge the synchronized remote feature with `git merge --ff-only` when it is a descendant, and inspect the resulting tree before pushing the target.
- Create a merge commit only when the repository or user wants an explicit integration boundary; inspect and validate the resulting tree before push.
- Never force-push a protected or default branch. Use `--force-with-lease` on a rewritten feature branch only with explicit authorization and only after verifying the expected remote tip.
- Push the exact validated target commit with a non-force update. If the target rejects because it advanced, stop and repeat the final fetch, divergence analysis, synchronization, and validation; do not pull into a dirty local target checkout.
- Treat committing, pushing a feature branch, merging a pull request, pushing the target, deleting a branch, and removing a worktree as distinct external or destructive actions. Perform only the actions included in the request.

After publishing, fetch and verify the remote ref or merged commit. Report the final branch topology, commits landed, validation, any retained worktrees or branches, and any remaining divergence.

## Cleanup And Recovery

Do not delete branches or worktrees as routine cleanup. When deletion is requested, verify the exact path and ref, confirm that the branch is merged or otherwise recoverable, check that no worktree or active task owns it, and distinguish local deletion from remote deletion.

Use `git reflog`, merge-base analysis, and immutable commit IDs for diagnosis and recovery planning. Ask before any recovery that would rewrite published history or discard commits or files.

The workflow follows Git's documented topic-branch/rebase model, `--ff-only` refusal behavior, `--force-with-lease` protection for rewritten refs, and linked-worktree isolation. Consult the [Git rebase](https://git-scm.com/docs/git-rebase), [git-merge](https://git-scm.com/docs/git-merge), [git-push](https://git-scm.com/docs/git-push), and [git-worktree](https://git-scm.com/docs/git-worktree) documentation when a repository-specific policy conflicts with these defaults. For protected repositories, follow the host's branch-protection and required-review rules.
