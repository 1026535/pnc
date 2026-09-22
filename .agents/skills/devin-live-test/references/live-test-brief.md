# Live-test assignment

Use this structure for one complete live-testing handoff. Include only relevant fields, but keep every authority or mutation boundary that applies.

```text
Outcome and acceptance:
Give the coordinator's live-test batch record path and its case IDs. List the live
boundaries to validate and one observable postcondition for each. State when the
assignment is complete and which failure, if any, makes later checks unsafe or
meaningless. Finish all other authorized checks before handback.

Target and authority:
Repository/worktree and one clean integration commit containing the bundle of changes;
give its exact SHA and included commits. Authorized account/castle or the canonical
configured-testing-instance default; allowed live role; declared instance bundle;
authorized switching; permitted mutations; and stable ending screen. When the plan
or series declares a persistent long reservation, name its scope, the renewal
checkpoints, and whether this assignment owns its terminal release; transport the
receipt to the worker without printing its contents. If spending may occur, give
the exact action, target, resource type, maximum amount or attempts, precondition,
success signal, and budget stop condition from the request or approved plan. The
configured live role and canonical lease remain authoritative.

Known evidence and non-goals:
Relevant implementation refs, known passing offline checks, reusable saved evidence,
and decisions already settled by the lead. Prohibited actions, unrelated workflows,
and any choice that genuinely requires user input. Do not edit repository content or
Git state.

Execution ownership:
Read AGENTS.md and .agents/skills/test-bluestacks-live/SKILL.md before ADB access.
Choose the smallest supported tests, application entry points, or authored workflows
that prove all assigned postconditions. Verify the clean candidate SHA and production
import root before execution. Run the smallest missing offline preflight. Prefer one
in-process task lease across dependent checks; when existing checks require separate
processes, run sequential phases and acquire and release each process's own canonical
task lease before its ADB access. Under a declared long reservation, carry its receipt,
renew at meaningful checkpoints, and defer to active foreign reservations. Validate
castle identity on initial instance takeover, authorized castle change, or instance
replacement, then reuse that proof while
continuity holds; verify the current screen and baseline, perform routine bounded
diagnosis, and continue safe independent checks after a failure. Keep raw live evidence
under the canonical configured artifact root. Do not send intermediate updates or ask
the lead to choose routine test, navigation, retry, or evidence details.

Completion and user blockers:
Complete every safe authorized check and package failed, blocked, and not-run results.
For an unrelated popup, try canonical bounded recovery, then use a fresh screenshot
and an unambiguous on-screen dismissal control (including a visible X) for a manual
tap under the same lease and authority if canonical recovery fails. Reobserve and
resume the batch when preconditions hold. Record the popup failure, recovery action,
artifact, and follow-up owner even if the feature case later passes. When an unrelated
lease, popup, or entry failure still prevents a feature case, classify the observed
boundary and report that feature case as not_run; do not infer its behavior.
For an unrelated castle-identity or BlueStacks instance-management failure, the
worker should attempt the smallest evidence-backed correction through existing
identity, status, or readiness entry points. Host-management mutation requires
explicit assignment scope and the role, idle-lease, and `read_only` boundaries.
Revalidate identity and readiness before
resuming the assigned tests. Record the incident even if recovered. Do not spend the
assignment fixing unrelated code or investigating the host without a bound; leave
dependent cases not_run and give the lead a separate defect follow-up if the
precondition cannot be restored promptly.
Do not return NEEDS_LEAD. Return BLOCKED only when a concrete user intervention is
required, such as new authorization, credentials, an account action, an unresolved
target choice, or a resource-budget decision. Finish every other safe check and
consolidate all known required user actions into one terminal BLOCKED handoff. Treat
transport or tool failure without a user remedy as FAILED. Restore the requested stable
screen when supported, apply cleanup, and release every task lease. Release a declared
long reservation only when this assignment owns its terminal semantic scope; an
inherited plan or series reservation remains held for its owner.

Packaged result:
Before handback, verify the candidate SHA, clean tree, and import root still match;
write evidence.json in DEVIN_IMPLEMENT_TURN_DIR using the contract below. Verify that
every assigned check has a result, every cited artifact exists and belongs to this
run, actual mutations and spending are recorded, and cleanup plus every lease release
are explicit. Return a compact READY_FOR_REVIEW / BLOCKED / FAILED handoff
containing only the overall result, evidence.json path, and required user actions
when blocked. Do not paste logs, duplicate per-check evidence, or request routine
intermediate review.
```

## Curated evidence contract

Write one `evidence.json` that lets the lead evaluate assignment completeness without scanning the run directory, raw artifact tree, logs, or conversation:

```json
{
  "schema_version": 2,
  "assignment": "short stable assignment label",
  "verdict": "READY_FOR_REVIEW",
  "candidate": {
    "git_head": "exact tested integration commit SHA",
    "source_root": "absolute production import root",
    "worktree_clean_before_after": true
  },
  "target": {
    "account_id": "resolved account identifier",
    "castle": "resolved castle or active castle",
    "live_role": "resolved configured role",
    "instance": "resolved instance display name"
  },
  "entry_points": ["exact commands or workflows used"],
  "checks": [
    {
      "id": "brief check identifier",
      "verdict": "passed",
      "expected": "observable postcondition",
      "observed": "what the live run established",
      "attempts": 1,
      "artifacts": [
        {
          "path": "absolute canonical artifact path",
          "kind": "screenshot",
          "proves": "specific fact established by this artifact"
        }
      ],
      "uncertainty": null
    }
  ],
  "interruptions": [
    {
      "observed_at": "timestamp with offset",
      "category": "popup, castle_identity, or instance_management",
      "check_id": "affected brief check identifier",
      "boundary": "observed failure before recovery",
      "artifact": "absolute canonical artifact path",
      "recovery": "action attempted and observed result",
      "outcome": "effect on assigned checks",
      "follow_up_owner": "owner or unknown"
    }
  ],
  "actual_mutations": [],
  "spending": {
    "authorized": "none",
    "actual": "none"
  },
  "final_screen": "observed stable ending screen",
  "cleanup": "cleanup action and preserved pre-existing state",
  "lease_released": true,
  "worktree_unchanged": true,
  "required_user_actions": [],
  "unresolved": []
}
```

Use `passed`, `failed`, `blocked`, or `not_run` for each check and explain every non-passing result in `uncertainty`, including whether the stopping boundary was environment/lease, unrelated entry or popup, feature behavior, safety/authority, or inconclusive evidence. Put every castle-identity, popup, and BlueStacks instance-management failure in `interruptions`, including one recovered before the affected check passed; use an empty array when none occurred. A broken canonical popup handler remains a follow-up even when manual dismissal lets the feature case pass. Reserve `blocked` for a check requiring user intervention; use `not_run` when another failed check made it unsafe or meaningless. `lease_released` means all sequential phases released their leases; describe those phases in `cleanup` when more than one process ran. `required_user_actions` must be non-empty only when the overall verdict is `BLOCKED`. Select only artifacts needed for acceptance and do not copy them into the Devin run directory. The handoff references this manifest rather than asking the lead to infer results from directory listings or full logs.

For a resumed turn, send only the user-resolved blocker, changed authority or budget, newly authorized attempt when applicable, and affected checks. Reuse the same run directory and session; do not replay completed checks or broaden the assignment implicitly.
