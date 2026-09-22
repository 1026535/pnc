# Live-Test Batch Record

The coordinator creates one QA-style record under `.local-data/live-test-batches/<batch>.md` when related live-dependent changes are ready for a checkpoint or acceptance. Use the same record for direct execution or a delegated live-test brief. It is a test specification before execution and a result ledger afterward; raw screenshots and traces stay in the configured artifact root.

```markdown
# <batch name>

Purpose and gate: <development checkpoint or acceptance; what cannot advance without proof>
Candidate: <worktree and exact tested tip SHA; included commits; clean tree for delegated
  acceptance, or source fingerprint for a direct uncommitted development checkpoint>
Offline evidence: <focused commands and results; saved artifact provenance if reused>
Target and authority: <configured account/active castle/instance, live role, allowed switching,
  mutations and exact spending budget if applicable; no secrets>
Lease and cleanup: <declared bundle, one execution owner, initial instance state,
  long-reservation scope/terminal owner if declared, stable ending screen,
  preservation decision; never include a reservation receipt>

| ID | Behavior and production entry | Preconditions and dependencies | Action | Observable pass condition | Result | Evidence / next step |
|---|---|---|---|---|---|---|
| C1 | ... | ... | ... | ... | pending | ... |

Interruptions: <one entry per castle-identity, popup, or instance-management failure,
  including recovered failures: timestamp, category, target, case, observed boundary,
  artifact, recovery attempted and result, affected case disposition, follow-up owner>
Execution: <entry points/commands, candidate actually loaded and production import root,
  instance identity and continuity proof, initial screen, lease acquisition and release
  for each execution process>
Disposition: <which cases pass, remain pending, or need an owned fix; next attempt trigger>
```

Use `pending`, `passed`, or `failed` per case. For a non-passing case, name the observed stopping boundary: environment/lease, unrelated entry or popup, feature behavior, safety/authority, or inconclusive evidence. Record the artifact and a concrete next attempt trigger. Log castle-identity, popup, and BlueStacks instance-management failures in `Interruptions` even when recovered and the case later passes. Keep a broken canonical popup handler as a separate follow-up after manual dismissal. A feature case whose valid precondition could not be established remains pending; a failed feature action after that precondition is established is failed. A delegated manifest's `not_run` maps to pending when live proof is still required. An equivalent manually established precondition can prove the feature action only when it does not bypass a feature-owned entry route; record those as separate cases if both matter.

Bind each result to the candidate actually exercised. A clean integration tip can cover a bundle of commits, but it proves the combined tree rather than every intermediate commit. For delegated acceptance, use that clean tip and reconcile it with the manifest's candidate SHA and import root. If later source changes can affect a passing case, mark that case pending again; retain unaffected proof. Finish other safe independent cases after a failure. The coordinator reconciles the record with the acceptance gate and, for delegated runs, the curated `evidence.json`; it does not scan raw artifacts when the package is complete.
