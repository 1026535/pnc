# Review: `completed PNC_ACCOUNT_NAVIGATION_SUBPLAN.md` (`dac26f6e893b2b867efb36eaea9eb6caef2d7b5a`)

## Findings

### 1. High: `LoginTask` can succeed on the wrong account, and the new roster check cannot reliably catch it

Affected code:
- `pnc_automation/automation/tasks/login_task.py:42-43`
- `pnc_automation/automation/tasks/login_task.py:90-110`
- `pnc_automation/vision/observation_builder.py:189-199`

Why this is a problem:
- `plan()` no-ops immediately when the run is already on `PNC_HOME_CITY` or `PNC_CASTLE_SELECTION`.
- `verify()` then returns success for those screens whenever `current_pnc_account_id` is `None`, which is the normal case for home-city observations.
- The fallback roster mismatch check is also ineffective during normal runs because `ObservationService.observe()` syncs the just-observed castle roster into the cache before `LoginTask.verify()` reads `context.castle_roster`.
- That means a wrong-account castle roster can be written under the configured `pnc_account_id`, then immediately pass the new verification path.

Impact:
- A session that is already inside the wrong P&C account can pass the `login` step.
- The wrong roster can be persisted into `config/castles.yaml` for the configured account, which then corrupts later castle-selection decisions.

Clean fix:
- Do not treat `PNC_HOME_CITY` or `PNC_CASTLE_SELECTION` as a verified login success unless the configured account has been proven by explicit evidence.
- Thread an immutable pre-observation roster snapshot into `LoginTask.verify()` instead of reading the lazily refreshed cache after `observe()`.
- Gate roster syncing so it only writes when the observed account has already been verified, or when the observation itself carries trustworthy account ownership evidence.

### 2. High: Off-screen castle scrolling assumes canonical roster order, but the cache does not preserve canonical order

Affected code:
- `pnc_automation/pnc/screen_flows.py:190-250`
- `pnc_automation/config/castle_roster_store.py:36-60`

Why this is a problem:
- `_plan_castle_roster_scroll()` uses list indexes inside `castle_roster.castles` to decide whether to swipe up or down.
- `CastleRosterStore.sync()` does not store a true roster ordering. It merges castles into a dict and preserves first-seen insertion order.
- If the roster is discovered from partial windows out of order, the persisted order becomes whatever was seen first, not the real in-game order.

Example failure mode:
- Observe `[C, D]` first, then later observe `[A, B]`.
- The cached roster becomes `[C, D, A, B]`.
- From a visible `[A, B]` window, targeting `D` now looks like "target is above the window", so the planner swipes the wrong direction.

Impact:
- `select_castle` can scroll the wrong way, oscillate, or raise false "should be visible" errors.
- The more the runtime learns partial roster windows, the more likely the cached order drifts away from reality.

Clean fix:
- Only use off-screen directional scrolling when the roster order was captured from a deterministic full scan.
- Persist explicit ordering metadata instead of relying on dict insertion order.
- If ordering cannot be trusted, fail fast and trigger a known-anchor rescan instead of guessing a direction.

### 3. Medium: Wrong-account intermediate states consume the single retry instead of using the existing replan path

Affected code:
- `pnc_automation/automation/tasks/login_task.py:90-114`
- `pnc_automation/automation/tasks/login_task.py:117-155`
- `pnc_automation/automation/runner.py:48-49`
- `pnc_automation/automation/runner.py:194-196`

Why this is a problem:
- `LoginTask.verify()` returns `failure(retryable=True)` as soon as `after.current_pnc_account_id` mismatches.
- That happens even on `PNC_ACCOUNT_SWITCH` and `PNC_LOGIN`, which are both states that `LoginTask.plan()` already knows how to recover from.
- The runner only allows one retry per step, so recoverable wrong-account transitions spend the retry budget before the task finishes the correction flow.

Concrete example:
- `PNC_LOADING` resolves to `PNC_ACCOUNT_SWITCH` with the wrong remembered account.
- The task reports a retryable failure instead of replanning into `_plan_account_switch()`.
- After tapping `change account`, the next `PNC_LOGIN` can still expose the old remembered username, and the task fails again before it gets another chance to input the configured credentials.

Impact:
- Real bootstrap flows can abort even though the task has the logic needed to recover.

Clean fix:
- Treat wrong-account `PNC_ACCOUNT_SWITCH` and `PNC_LOGIN` states as `TaskResult.replan(...)`, not retryable failures.
- Reserve hard failures for terminal mismatches after the corrective branch has already been attempted.

### 4. Low: The commit checked in a live runtime cache with real account data

Affected files:
- `config/castles.yaml:1-9`
- `config/castles.example.yaml:1-10`
- `.gitignore:18-19`

Why this is a problem:
- `config/castles.example.yaml` documents `config/castles.yaml` as the runtime-generated cache.
- This commit replaces the placeholder/empty state with live account data, including a real email address and live castle identities.
- Unlike `config/accounts.yaml`, the runtime cache is not ignored.

Impact:
- The repository now contains user-specific runtime state and personally identifying data.
- Every live roster update can create noisy source-control diffs.
- Future runs on another machine can accidentally inherit stale local cache state from this commit.

Clean fix:
- Revert `config/castles.yaml` to a sanitized placeholder or empty cache.
- Either ignore `config/castles.yaml` like `config/accounts.yaml`, or stop treating it as a runtime-generated file and manage it as a deliberately authored fixture instead.
- If a tracked example is still needed, keep that in `config/castles.example.yaml` only.

## Validation Performed

- Ran `py -3 -m unittest discover -s tests` and the current automated suite passed (`81` tests, `3` skipped).
- Confirmed the first finding with a local reproduction: a wrong castle roster synced under the configured `pnc_account_id` causes `LoginTask.verify()` to return success.
- Confirmed the second finding with a local reproduction: partial roster syncs preserve first-seen insertion order rather than true roster order.
