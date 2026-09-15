# Live Testing Phases

## Evidence Readiness

Before live-dependent design or implementation, identify the feature boundary, preconditions, distinct use cases, controls, transitions, and observable outcomes. Explore live by default unless inspected saved evidence and relevant deterministic checks demonstrably support every material assumption in the applicable context.

Establish provenance and applicable screen, language, viewport, progression, runtime, transition, and postcondition coverage. A passing fixture proves compatibility with that fixture, not current game behavior by itself. Do not use a universal expiration interval; invalidate evidence when a relevant UI or production contract changes or newer evidence contradicts it.

Record only:

```text
Readiness: READY_SAVED | READY_LIVE | BLOCKED
Scope and distinct use cases: <boundary and behaviors>
Evidence and applicability: <artifacts/tests and why they apply>
Remaining material gaps: <none or required observation>
```

Block only work dependent on an unresolved material fact.

## Exploration

When readiness is not established, retain one live session across the connected questions needed for implementation. It may cover several screens, transitions, timing observations, and ordinary gameplay actions; do not impose a one-tap or one-screenshot limit. Stop when the questions are answered, progress ceases, or a safety/authorization boundary is reached.

For resource-consuming actions, follow [write-code-live](../../write-code-live/SKILL.md). Its exploration mode permits non-premium, non-protected in-game resources without a numeric per-action budget and treats diamonds as non-premium; strict actions retain cumulative limits.

## Development Checkpoints

Implement coherent behavioral batches while their assumptions remain supported. Use focused offline checks within a batch; do not checkpoint by line, file, edit, commit, or elapsed-time count.

Run one consolidated checkpoint when:

- the current coherent batch is complete and its changed live boundary is runnable;
- the next dependent batch would rely on that unproven boundary;
- a new material assumption appears;
- relevant evidence becomes inapplicable or contradicted;
- live evidence is required to diagnose a contract mismatch;
- related pending questions can be answered efficiently together; or
- the candidate is ready for acceptance.

Collect the affected questions, retain one lease, and exercise their smallest distinct production paths after focused offline checks. Do not interrupt the current batch merely because a helper, selector, or partial route became runnable; stop early only for safety, a contradicted material assumption, or a dependency that cannot progress without live evidence. A passing checkpoint remains usable until later code or evidence invalidates it. Declare whether the checkpoint is exploratory or an acceptance canary before execution; exploration cannot be relabeled afterward as strict acceptance.

## Acceptance

Final acceptance covers every distinct feature-owned use case. A use case is distinct when it has materially different transitions, state decisions, interactions, mutations, or success/refusal outcomes. Use one representative target unless the contract or observed variation requires more.

Acceptance canaries require explicit action, target, resource, attempt, and retry limits. A prior checkpoint can satisfy an acceptance case only when it already met those conditions, observed the required production postcondition, and was not invalidated by later changes.

After a feature defect, preserve evidence, add an offline regression when practical, fix offline, and rerun the affected case. Rerun other passing cases only when the fix could plausibly affect them.
