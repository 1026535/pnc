# Epic Coordinator Ledger

Keep one ledger in the primary checkout at `.local-data/<epic-id>/coordinator-ledger.md`. This ignored local record survives task handoffs without becoming another tracked status system. If a suitable epic status file already exists, make it the canonical ledger and link it; do not create a competing copy. Keep detailed plans, live batches, manifests, and raw evidence at their existing paths and reference them here.

```markdown
# <epic ID> coordinator ledger

Updated: <UTC timestamp>
State: <active | paused | blocked | complete | closed>
Primary checkout: <absolute repository path>

## Authorized scope
- Scope and explicit exclusions: <...>
- Authority source and exact live/spending limits: <request/approved plan reference; ...>
- Pause/close conditions: <...>

## Acceptance
- Current acceptance revision: <revision ID/date and authoritative criteria reference>
- Amendments: <append-only entries; do not rewrite prior scope or denominator>
- Accepted outcomes and pending requirements: <stable case/plan IDs and linked evidence>

## Critical path
- Current blocker: <stable ID and evidence, or none>
- Dependent work held: <plan/case IDs that cannot advance, or none>
- Why coordinator checkpoint is warranted: <expected reduction in blocked time, or none>

## Ownership and next action
- Current owner: <Codex task/thread, Devin session/run directory/turn, or named person/system>
- Next action: <one concrete action>
- Trigger and prerequisites: <what event enables it; candidate, authority, or dependency>
- Last reconciliation: <UTC timestamp and worker/process/batch/lease sources checked>

## Candidate and validation references
- Candidate: <repository/worktree, branch, exact SHA or direct-source fingerprint, production import root>
- Live batch: <stable path and case IDs, or none>
- Evidence manifest/handoff: <paths and worker turn IDs, or none>
- Incidents: <stable IDs and report paths, or none>

## Active and completed work
| Item | State | Owner | Candidate | Worker run and turn | Batch/evidence | Next action |
|---|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... | ... |

## Resource ownership
- Active process/monitor: <identity and state, or none>
- Task lease: <target and owning process, or released/not acquired>
- Long reservation: <scope, terminal owner, renewal/release state; never include receipt contents>

## Transition log
| UTC | Event | Prior owner/state | New owner/state | Candidate/references | Decision or evidence |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |
```

Update the ledger before dispatch and whenever ownership or scope changes. A resumed coordinator reads it first, then verifies its claims against worker handoffs, active local processes, the candidate tree, the live-test batch, monitor registration, and current lease/reservation state. Reconcile contradictions before dispatch. A callback arriving after pause or closure can update the historical result, but cannot change state back to active or authorize another attempt. Record a scope amendment as a new acceptance revision while preserving the old criteria and denominator.
