# N4 — Remove contradictory final-test instructions

Prepared September 30, 2026 against `868157f5897e89e2b6090c0009ecc9a835eaf3e2`. Independent documentation assignment; [pack scope and integration](README.md). Source finding: [F5](../REPOSITORY_VELOCITY_AND_MODULARITY_REVIEW_20260930.md#f5--p2-mandatory-porting-guidance-still-demands-a-redundant-full-gate).

Accepted with a wording clarification in the October 1 [GPT-6 Pro review and Codex audit](PRO_REVIEW_AND_CODEX_AUDIT_20261001.md), against `a841f7425f2d3658c59b8b9b6f00c6b3410d3b56`.

## Outcome and evidence

An engineer following mandatory workflow-porting guidance should reach the same final validation decision as an engineer following the repository's implementation skill. The change removes a concrete source of redundant work without weakening feature or live acceptance.

[CORE_WORKFLOW_PORTING.md](../../../../instructions/CORE_WORKFLOW_PORTING.md), line 244 at the baseline, instructs a final full suite after focused checks. That imperative occurs in active lifecycle guidance, not the dated historical validation section. [AGENTS.md](../../../../AGENTS.md) and [write-code](../../../../.agents/skills/write-code/SKILL.md) instead require one final affected gate where appropriate and accept its full fallback without a second full run. The contradiction is source-proven; its frequency and elapsed-time cost are unknown.

An adjacent active [planning reference](../../../../.agents/skills/create-plan/references/implementation-live-validation.md), line 17, broadly permits full validation for final integration; this is ambiguous permission, not the porting guide's explicit full-suite requirement. Align that sentence with the canonical decision rule so new plans do not recreate the conflict. This is policy-reference consistency, separate from V44 Q5's live development/acceptance phase amendment.

## Owned edits

Change only the operative validation sentence/link in `instructions/CORE_WORKFLOW_PORTING.md` and the corresponding offline-test sentence in `.agents/skills/create-plan/references/implementation-live-validation.md`. Treat `AGENTS.md`, `tests/README.md` and `write-code/SKILL.md` as read-only authorities unless a future user assignment separately requests changing policy.

Keep concrete feature checks, required live postconditions, reservations, error-preserving cleanup and source-freeze rules. Preserve the porting guide's historical `full` results and dated commands as history. Do not rewrite old plans, all skill prose, CI, test-selection code, or live spending/target policy.

## Deliverables

1. Read the current canonical offline-validation rule and confirm the conflicting sentences still exist. If another accepted change already corrected one, retain it and close that portion without another edit.
2. Replace the porting imperative with a short relative link to the current repository validation owner. Convey the decision: focused checks during development, one final affected gate for a source change with downstream consumers, legitimate full fallback retained, and a separate local full run only for an explicit request or a concrete uncovered risk. Prefer a reference over copying the complete policy.
3. Align the planning reference's sentence with the same owner while keeping its live-proof requirements. Read the linked active instructions together to ensure neither instructs the reader to run full again merely because integration is final. This is a bounded read-through, not an audit of every historical plan.

## Acceptance and validation

The guide, implementation skill and planning reference must lead to the same result in three representative cases: a documentation-only edit needs documentation checks; an ordinary source change needs its owning checks and final affected selection; an infrastructure change may legitimately use the affected full fallback without an additional local full run. A material live boundary still requires its applicable live proof.

Check edited Markdown links and `git diff --check`, and inspect the two small diffs. No unit, full, live or benchmark run is required, and no test should assert policy wording.

## Assignment and handback

This package can complete independently of N1/N2/N3 and all three feature epics. Before editing, check whether a live-policy/workflow owner has changes to the same paragraphs; integrate the narrow sentence corrections without taking over that owner's phase changes.

Hand back the two diffs, canonical links, and passed documentation checks. Do not claim measured runtime savings or alter any coordinator's queues. No new validator, scheduler, skill or approval step is needed.
