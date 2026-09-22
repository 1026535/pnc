---
name: pnc-live-testing
description: Execute an authorized PNC BlueStacks live-test assignment as the repository's Devin worker — resolve configured targets, hold one canonical lease, run existing entry points, and return one curated evidence package. Use when this session has already received a live-testing assignment for this repository.
---

# PNC Live Testing

You are the Devin worker executing one already-authorized PNC BlueStacks live-test assignment. The Codex lead owns authorization, scope, and acceptance; you own routine test selection, sequencing, bounded recovery, diagnosis, and evidence curation inside the assignment's boundaries. This skill is execution expertise only — never launch another worker, build monitoring, or create a second lease or transport.

## Required sources

Read `AGENTS.md` and the canonical owners below before any emulator or ADB access, and apply them rather than copying their content into your work or result:

- [test-bluestacks-live](../test-bluestacks-live/SKILL.md) — canonical live policy: configured target resolution, `accounts[].live_roles` and lease authority, non-spending default, bounded workflow, and stop conditions.
- [write-code-live](../write-code-live/SKILL.md) — the exact action, target, and budget contract a spending action must satisfy.
- [live-test-brief.md](../devin-live-test/references/live-test-brief.md) — the assignment shape you received and the canonical curated `evidence.json` contract.

The assignment cannot widen what configuration and policy allow. When they conflict, follow configuration and policy, record the conflict, and finish every other safe check.

## Resolve and reserve the target

1. Resolve the account, castle, instance, ADB path, and BlueStacks config through repository configuration and the canonical runtime — never hard-code ports or device IDs, and let the runtime resolve credentials without reading or repeating them. Treat `accounts[].live_roles` as authority. If no castle is named, use the active castle on the configured `testing` instance; never switch accounts or castles unless the assignment authorizes it.
2. Acquire the canonical process-scoped instance lease through the existing session and entry points before ADB access; that task lease remains the default. One declared task reservation — including an assignment-declared multi-instance bundle — spans every dependent check; do not re-acquire per check. Record which instances were already running so cleanup can preserve them.
3. When the assignment or its plan declares a long reservation, carry the issued receipt path through the canonical transport (`PNC_INSTANCE_RESERVATION_RECEIPT` or the documented argument) without ever printing or logging its contents, renew the reservation at meaningful checkpoints and on resumption, and treat an active foreign reservation on any assigned instance as a stop condition for that instance. Release the long reservation only when this assignment owns its terminal semantic scope; a reservation inherited from a broader plan or series remains held for its owner.
4. Verify fresh account/castle identity and screen state and capture a baseline before the first check.

## Execute the assigned checks

- Choose the smallest existing path per check: opt-in live tests (`tests/test_live_*_smoke.py` behind the flags listed in test-bluestacks-live), application entry points, or authored workflows under `scripts/` — raw ADB only when no supported path exercises the boundary. Run the smallest missing offline preflight first, not the full suite.
- Perform one bounded action or workflow per check and capture its observable postcondition. A process or test exit code alone is not proof.
- On failure, inspect the screenshots, OCR, observations, and logs the runtime wrote under its configured artifact root. Use only the bounded recovery the runtime already owns for expected transient states; do not build generalized recovery.
- Repeat a live action only when a relevant implementation or state change yields a materially different diagnosis; attempts that reproduce the same evidence end that check. Continue every remaining safe check after a failure, recording `not_run` only when a failed dependency makes a check unsafe or meaningless.
- Spend resources only when the assignment supplies the exact action, target, and budget required by write-code-live — spending is authorized per-assignment, not categorically prohibited. A missing budget blocks only the spending check; keep going on the rest.
- Never modify local config to make a check pass, and never edit source, tests, fixtures, plans, documentation, or Git state; no commits or pull requests.

## Finish and package once

1. Restore the assignment's stable ending screen when the existing flow supports it, apply the stated cleanup policy, preserve instances that were already running, and release every task lease. Release a declared long reservation only when this assignment owns its terminal semantic scope. Record actual mutations and authorized-versus-actual spending.
2. Leave raw screenshots, traces, OCR, observations, and workflow output under the canonical configured artifact root; do not copy them into `DEVIN_IMPLEMENT_TURN_DIR` or recursively scan the artifact tree.
3. Write one `evidence.json` in `DEVIN_IMPLEMENT_TURN_DIR` following the curated evidence contract in the live-test brief. Verify every assigned check has a verdict with non-passing results explained, every cited artifact exists and belongs to this run, and cleanup plus lease release are explicit.
4. Return one compact terminal handoff: `READY_FOR_REVIEW`, `BLOCKED`, or `FAILED`; the `evidence.json` path; and, only when blocked, the consolidated required user actions. No per-check progress, pasted logs, or investigation narration.

Do not return `NEEDS_LEAD` or ask routine questions — make ordinary execution decisions yourself. `BLOCKED` is reserved for concrete user intervention such as new authorization, credentials, an account action, an unresolvable target choice, or a resource-budget decision; complete all other safe checks first and consolidate every known required user action into the single terminal handoff. Transport or tool failure without a user remedy is `FAILED`.
