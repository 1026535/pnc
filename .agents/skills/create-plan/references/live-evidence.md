# Live Evidence Acquisition

Use this reference only when a plan needs current BlueStacks UI or runtime evidence that repository artifacts cannot establish.

## Preconditions

1. Use the `test-bluestacks-live` skill and the existing PNC runtime. Do not invent a second emulator-control path.
2. Resolve the account and BlueStacks display name from `config/`. If no castle target is specified, use whichever castle is currently active on the `testing` instance; observe and record its identity, but do not select or switch castles. If a castle is explicitly specified, resolve and verify that target before navigating.
3. Let `BlueStacksInstanceResolver` launch the configured instance when it is closed. Wait for `BlueStacksSession.connect()` and `ensure_responsive()` to succeed.
4. Keep ADB local and use the configured `adb_path`, host, and port. Never print credentials, tokens, or unrelated device data.
5. Define the evidence question before acting, for example: "Which screen follows opening the Institute?" or "Is this selector visible on the current home-city screen?"
6. Treat a planning-only request as authorization for safe, read-only observation within the requested scope. It is not authorization for a state-changing action.

## Mandatory Evidence Gate

Before finalizing a plan, classify each material current-runtime question as one of:

- `artifact_answered`: a current repository artifact directly answers it;
- `live_observed`: a bounded live trace answers it;
- `live_blocked`: a bounded live attempt reached a named stop condition; or
- `mutation_boundary`: safe navigation reached the last read-only state, but answering the remainder requires explicit authorization for a state-changing action.

Do not classify a question as future implementation work merely because live setup has a cost. If the plan's selectors, transitions, or success criteria depend on it, attempt the bounded workflow now. When the terminal action is forbidden, gather evidence up to the mutation boundary and preserve that screen instead of skipping live inspection entirely.

## Bounded Observation Loop

Use one target and one evidence question per run. The default budget is at most 8 navigation transitions and 10 minutes, whichever comes first. Stop as soon as the evidence question is answered; do not spend the budget searching for extra screenshots.

1. Capture a labeled baseline with `ObservationService`, including the screenshot and normal observation sidecars under `artifacts/`.
2. Check the typed screen classification, popup state, account/castle identity, and visible selectors before choosing an action.
3. Choose one safe, existing navigation action from `ScreenFlowPlanner`, an existing selector registry entry, or an approved live discovery/smoke helper. Set `observe_after=True` where supported.
4. Execute only that action, then capture a labeled post-action observation. Inspect the screenshot, OCR/observation data, and logs before deciding on another transition.
5. Record the transition as `baseline -> action -> observed result -> artifact paths`. Mark the result as observed, inferred, or unknown.
6. If the evidence is sufficient, stop. If the screen is unexpected, the action has no verifiable post-observation, or the action would become state-changing, stop and report the blocker.
7. When possible, unwind through the canonical safe-root flow and capture a final observation. Do not force recovery with blind taps.

## Allowed And Forbidden Actions

Allowed without additional authorization: launch or foreground the configured app, dismiss a recognized blocking popup, open a read-only menu or screen, scroll to inspect visible content, press Back, and return to the canonical safe root. These actions are still bounded by the transition budget and must be observed after execution.

Forbidden without explicit user authorization: building, researching, collecting or claiming rewards, sending mail or chat, marching, gathering, attacking, purchasing, spending resources, changing account or castle, logging in or out, resetting app data, deleting anything, or changing authored configuration. Do not use raw coordinate taps when a typed selector or navigation abstraction exists.

## Stop Conditions

Stop immediately and preserve the latest artifacts when:

- the requested account, castle, instance, or app cannot be verified;
- ADB is disconnected, the instance cannot become responsive, or the app is not the expected package;
- screen classification is unknown, a popup is unrecognized, or a selector is ambiguous;
- a proposed action could mutate game or account state;
- the action budget or time budget is exhausted; or
- the same transition fails twice without new evidence.

Do not retry a failed click blindly. Inspect the latest screenshot, OCR, observation, and logs, then either choose a canonical recovery action or stop.

## Plan Evidence Contract

Include a compact evidence table in the plan or planning response with:

- target account, castle, BlueStacks display name, and whether the instance was already running or launched;
- baseline and post-action screen classifications;
- each action and observed result;
- screenshot, OCR, observation, and log artifact paths;
- claims labeled `observed`, `inferred`, or `unknown`; and
- the final stop reason, including any blocker or authorization needed.

Also list each original evidence question and its `artifact_answered`, `live_observed`, `live_blocked`, or `mutation_boundary` disposition. A plan cannot pass the evidence contract when a material question is merely deferred without a live attempt.

Do not embed secrets or treat a screenshot as proof of behavior that was not actually observed. Convert live-discovered defects into deterministic regression fixtures or tests when practical.
