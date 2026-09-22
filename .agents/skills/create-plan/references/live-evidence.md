# Live Evidence For Planning

Use this reference only when a current BlueStacks fact could materially change a plan and deterministic tests, fixtures, or saved UI/runtime artifacts cannot answer it.

## Before Running

- Define the single decision and why offline evidence is insufficient.
- Resolve the target from config. A specific castle named in the request or plan authorizes switching to that castle within the selected, role-authorized account and instance. If no castle is named, observe the active castle on the configured `testing` instance; do not switch. A named castle does not authorize switching accounts or instances.
- Follow [test-bluestacks-live](../../test-bluestacks-live/SKILL.md) and use the canonical runtime.
- Set a small action/time budget appropriate to the question. A budget is a ceiling, not a quota.
- Keep the observation non-spending. Stop before any state-changing action that lacks exact authorization.

## Observation

1. Capture a typed baseline with the relevant screenshot and observation data.
2. Use one safe existing navigation or inspection action.
3. Capture the post-action state and decide whether it answers the question.
4. Stop when the decision is supported. Continue only when the next bounded observation is likely to resolve a material ambiguity.
5. Return through the existing safe-root flow when useful and supported.

Do not launch BlueStacks merely to reconfirm stable repository facts, gather extra screenshots, or test interchangeable targets. Avoid raw coordinate taps when a typed selector or navigation abstraction exists.

## Stop

Stop and preserve the latest useful artifact when identity cannot be verified, ADB cannot become responsive within its configured bound, the screen or selector is ambiguous, the next step crosses a mutation boundary, the budget is exhausted, or the same result repeats without new evidence.

## Plan Evidence

Record the target, question, baseline, action, observed result, artifact paths, and stop reason. Label material conclusions as observed, repository-proven, inferred, or unknown.

A failed bounded attempt may leave a plan implementation-ready when the unresolved fact does not affect the design. Keep it as a blocker only when the missing evidence is necessary for safe implementation or the claimed promotion decision.
