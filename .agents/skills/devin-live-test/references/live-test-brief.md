# Live-test assignment

Use this structure for one complete live-testing handoff. Include only relevant fields, but keep every authority or mutation boundary that applies.

```text
Outcome and acceptance:
List the live boundaries to validate and one observable postcondition for each. State
when the assignment is complete and which failure, if any, makes later checks unsafe or
meaningless. Finish all other authorized checks before handback.

Target and authority:
Repository/worktree and baseline SHA. Authorized account/castle or the canonical
configured-testing-instance default; allowed live role; declared instance bundle;
authorized switching; permitted mutations; and stable ending screen. If spending may
occur, give the exact action, target, resource type, maximum amount or attempts,
precondition, success signal, and budget stop condition from the request or approved
plan. The configured live role and canonical lease remain authoritative.

Known evidence and non-goals:
Relevant implementation refs, known passing offline checks, reusable saved evidence,
and decisions already settled by the lead. Prohibited actions, unrelated workflows,
and any choice that genuinely requires user input. Do not edit repository content or
Git state.

Execution ownership:
Read AGENTS.md and .agents/skills/test-bluestacks-live/SKILL.md before ADB access.
Choose the smallest supported tests, application entry points, or authored workflows
that prove all assigned postconditions. Run the smallest missing offline preflight,
acquire one canonical reservation for the declared bundle, verify fresh identity and
baseline state, execute dependent checks under that lease, perform routine bounded
diagnosis, and continue safe independent checks after a failure. Keep raw live evidence
under the canonical configured artifact root. Do not send intermediate updates or ask
the lead to choose routine test, navigation, retry, or evidence details.

Completion and user blockers:
Complete every safe authorized check and package failed, blocked, and not-run results.
Do not return NEEDS_LEAD. Return BLOCKED only when a concrete user intervention is
required, such as new authorization, credentials, an account action, an unresolved
target choice, or a resource-budget decision. Finish every other safe check and
consolidate all known required user actions into one terminal BLOCKED handoff. Treat
transport or tool failure without a user remedy as FAILED. Restore the requested stable
screen when supported, apply cleanup, and release the lease.

Packaged result:
Before handback, write evidence.json in DEVIN_IMPLEMENT_TURN_DIR using the contract
below. Verify that every assigned check has a result, every cited artifact exists and
belongs to this run, actual mutations and spending are recorded, and cleanup plus lease
release are explicit. Return a compact READY_FOR_REVIEW / BLOCKED / FAILED handoff
containing only the overall result, evidence.json path, and required user actions
when blocked. Do not paste logs, duplicate per-check evidence, or request routine
intermediate review.
```

## Curated evidence contract

Write one `evidence.json` that lets the lead evaluate assignment completeness without scanning the run directory, raw artifact tree, logs, or conversation:

```json
{
  "schema_version": 1,
  "assignment": "short stable assignment label",
  "verdict": "READY_FOR_REVIEW",
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

Use `passed`, `failed`, `blocked`, or `not_run` for each check and explain every non-passing result in `uncertainty`. Reserve `blocked` for a check requiring user intervention; use `not_run` when another failed check made it unsafe or meaningless. `required_user_actions` must be non-empty only when the overall verdict is `BLOCKED`. Select only artifacts needed for acceptance and do not copy them into the Devin run directory. The handoff references this manifest rather than asking the lead to infer results from directory listings or full logs.

For a resumed turn, send only the user-resolved blocker, changed authority or budget, newly authorized attempt when applicable, and affected checks. Reuse the same run directory and session; do not replay completed checks or broaden the assignment implicitly.
