# Live Evidence For Planning

Use this reference for plans whose design depends materially on current BlueStacks, UI, selector, navigation, timing, or emulator facts.

## Readiness Gate

Identify the feature boundary, preconditions, distinct use cases, controls, transitions, and observable outcomes. Explore live before fixing dependent design decisions unless inspected saved evidence and relevant deterministic checks demonstrably support every material assumption in the applicable context.

Judge evidence by provenance, applicable screen/language/viewport/progression/runtime conditions, production-path coverage, transitions and postconditions, and newer contradictions. A fixture pass does not establish current game behavior by itself. Do not use a universal expiration interval.

Record `READY_SAVED`, `READY_LIVE`, or `BLOCKED`, the evidence and why it applies, and remaining material gaps. Block only dependent design; continue independent evidence-supported planning.

## Exploration

- Resolve the target from config. If no castle is named, use the active castle on the configured `testing` instance; do not switch castles.
- Follow [test-bluestacks-live](../../test-bluestacks-live/SKILL.md) and use the canonical runtime.
- Keep one scoped session across the connected implementation questions rather than limiting exploration to one action or screenshot.
- For resource-consuming exploration, use the authorization modes in [write-code-live](../../write-code-live/SKILL.md); do not invent per-action ordinary-resource budgets in a plan.

## Observation

1. Capture a typed baseline with relevant screenshot and observation data.
2. Exercise the related screens, transitions, and in-scope actions needed to answer the material questions.
3. Capture post-action states and stop when the questions are supported or further actions cease to produce useful evidence.
4. Return through the existing safe-root flow when useful and supported.

Do not launch BlueStacks merely to reconfirm stable repository facts, gather extra screenshots, or test interchangeable targets. Avoid raw coordinate taps when a typed selector or navigation abstraction exists.

## Stop

Stop and preserve the latest useful artifact when identity cannot be verified, ADB cannot recover within its configured bound, the next action would be blind or cross an unauthorized/protected boundary, an unexpected consequential result is uncertain, or attempts repeat unchanged evidence.

## Plan Evidence

Record the target, questions, baseline, actions, observed results, artifact paths, and stop reason. Label material conclusions as observed, repository-proven, inferred, or unknown.

A failed exploration session may leave independent parts implementation-ready. Keep a gap as a blocker only when the missing evidence is necessary for safe dependent implementation or a claimed acceptance decision.
