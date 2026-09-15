# Live Failure Handling

## Classification

Classify the observed boundary without guessing its cause:

- `SAFETY / AUTHORIZATION`: identity, protected action, permission, strict limit, or uncertain consequential result prevents safe continuation.
- `ENVIRONMENT`: lease, ADB, emulator, host, or config prevents execution.
- `NAVIGATION / PREFLIGHT`: the declared feature-entry precondition cannot be established.
- `FEATURE`: feature-owned behavior fails after a valid precondition.
- `EVIDENCE / ORACLE`: observations cannot determine the result.

Store full run evidence under `.local-data/`. Use an existing task note or a category summary for unresolved cross-task problems. Record one row per distinct actionable symptom within a category, not per event and not one row for unrelated problems:

```text
Category | Symptom and boundary | Evidence/occurrences |
Owner and scope impact | Disposition or next check
```

Repeated occurrences update that symptom. Do not add event IDs, a database, dashboard, or runtime instrumentation solely for this policy. Promote a reproducible, recurring, high-impact, or independently actionable symptom to a separate handoff when durable ownership is useful.

Immediately preserve evidence and decide whether continuation is safe. Before retrying, identify the relevant code, state, or diagnosis that changed; never replay an uncertain mutation to discover whether it succeeded. At the end of exploration or a checkpoint, disposition material symptoms as fix in scope, hand off, continue from an equivalent precondition, or block affected work. Reconcile them with acceptance claims before completion.

## Manual Preconditions

An unrelated navigation or preflight defect may be handed off separately. Manual setup can establish an equivalent feature-entry precondition when it does not perform the feature action, bypass its guards, or fabricate its result. After intervention, freshly verify the relevant identity, screen/tab, selection, resource state, and runtime initialization.

If the production feature action and postcondition pass from that state, report feature-action acceptance separately from the failed upstream route and unattended readiness. If automated arrival belongs to the feature contract, manual setup cannot complete that contract.
