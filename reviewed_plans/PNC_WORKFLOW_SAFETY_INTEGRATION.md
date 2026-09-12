# Workflow safety integration

## Provenance

This bounded transfer follows `reviewed_plans/audit_followups_2026_09_12/01_workflow_safety.md` from the audit handoff in `C:/Users/lebel/.codex/worktrees/a032/pnc`. The source implementation diff was inspected read-only and its changes were applied selectively against the current owners in this worktree.

## Integrated invariants

- `AutomationSession` rejects reentry before replacing its reservation or context token, and an implicit call through another `AutomationApi` is rejected before dispatch.
- Daily claim reconciliation commits only when the post-action row states are nonempty and recognized (`Go`, `Completed`, or `Requirement`).
- Daily mutation scans process each stable viewport once and retain unknown-title evidence from the final viewport.
- World-map corner snapping uses one helper that filters snapped coordinates after parity correction, keeping row-major, row, and column samples inside requested bounds.

Focused offline unittest modules for these four owners passed in the resulting worktree. No live run, configuration access, commit, or push was performed for this transfer.
