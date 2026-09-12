# Replacement core remaining-issues implementation review

Review target: `46e80f8f2c2a3c1067b269bda4901c2d07a3708c`

Plan: `reviewed_plans/PNC_REPLACEMENT_CORE_REMAINING_ISSUES_PLAN.md`

Reviewed with repository evidence, deterministic fixture replay, the complete offline suite, and bounded live observations on the exclusively reserved `mega_old_acc` BlueStacks instance. The configured role inventory was inspected without changing configuration: `serious_stuff` currently carries `live_testing`, while the production Daily Quest entry point requires `daily_canary`. `mega_old_acc` was therefore used as the current role-eligible, free live target. This substitution is evidence about the implementation, but it does not satisfy the plan's exact `serious_stuff` matrix rows.

## Findings

### [P1] Navigation perception removes the safe popup selector before recovery can use it

`NavigationPerception.build` obtains typed interruption evidence and controls from `detect_interruption`, but line 56 replaces the observation controls with an empty mapping whenever `interrupted` or `blocked` is true. The new `CoreRuntime.observe` integration then asks `ObservedActionExecutor` to recover that observation. The executor correctly refuses because `PNC_POPUP_CLOSE_BUTTON` is absent.

This failed on a live Savannah offer, one of the explicitly supported promotional popups. Deterministic replay of the captured frame produced:

- detector evidence: `PNC_POPUP / ocr_promotional_offer_popup`
- detector control: `PNC_POPUP_CLOSE_BUTTON`
- final `NavigationPerception` observation: `PNC_POPUP`, blocked, zero controls

Both the production Daily status path and explicit `recover_to_home` stopped with `SelectorResolutionError: Transient popup has no explicit safe close selector; Android Back is forbidden.` No dismissal, navigation retry, castle switch, or resource-changing action was sent.

Fix direction: on an interruption, expose only the interruption detector's explicitly safe controls, scaled into the captured-frame coordinate space. Continue excluding background-screen controls and task-owned controls. Add an end-to-end regression from `NavigationPerception` through `CoreRuntime.observe` and `ObservedActionExecutor` using a real promotional fixture. The existing positive tests call `_build_visual_popup_close_additions` directly, so they cannot catch this ownership loss.

Relevant code:

- `pnc_automation/app/pnc/vision/navigation_perception.py:46-58`
- `pnc_automation/app/automation/engine/core_runtime.py:69-80`
- `pnc_automation/app/automation/engine/observed_action_executor.py:465-470`

Live evidence:

- Daily trace: `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T031953Z_49246b9c_core_trace.jsonl`
- Daily source frame: `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T031954Z_core_20260912T031953Z_49246b9c_0001_preflight_settle_0.png`
- Recovery trace: `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T032122Z_3c3c4c84_core_trace.jsonl`
- Recovery source frame: `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T032123Z_core_20260912T032122Z_3c3c4c84_0001_core_route_source.png`

### [P1] The opt-in recovery smoke does not enforce the smoke-test role

`tests/test_live_core_workflow_smoke.py` accepts an arbitrary account ID and calls `build_core_runtime` without `required_role=LiveAutomationRole.SMOKE_TEST`. Because the runtime only validates a role when one is supplied, this smoke can send navigation and popup-close taps on an account that was not authorized for acceptance smoke, including a `read_only` account. The test also never closes its runtime, leaving cleanup to process exit.

Fix direction: require `SMOKE_TEST` in `build_core_runtime`, register `core_runtime.close` with class cleanup immediately after construction, and document that the smoke target must be the current account carrying that role. If the intended proof is instead a `daily_canary` production probe, give it a separate entry point and explicit role rather than letting one environment variable bypass role ownership.

Relevant code:

- `tests/test_live_core_workflow_smoke.py:38-51`
- `pnc_automation/app/automation/engine/script_runner.py:296-306`

### [P2] The plan's exact live target no longer satisfies the production role gate

The plan hard-codes `serious_stuff`, but `ApplicationRunner.run_daily_quest_status` now requires `LiveAutomationRole.DAILY_CANARY`. Current host configuration assigns that role to `mega_old_acc`, while `serious_stuff` carries `live_testing`. The exact planned Daily command therefore cannot reach its proof under the current authority model. This is plan/config drift rather than a reason to weaken the role gate.

Fix direction: update the reviewed matrix to identify targets by required role and record the concrete account selected at execution time, or explicitly reassign the role through the repository's normal configuration process before rerunning. Do not remove the production role check.

Relevant code:

- `pnc_automation/app/entrypoints/app.py:122-134`
- `reviewed_plans/PNC_REPLACEMENT_CORE_REMAINING_ISSUES_PLAN.md:134-174`

### [P2] A newly launched instance produces an immediate UNKNOWN failure before the game renders

The selected instance was stopped. The canonical resolver launched it, but the first Daily and recovery observations captured a completely black frame and immediately failed as `UNKNOWN`. A later bounded attempt reached the Savannah offer, proving that the first failure was startup timing. The current preflight policy intentionally stops on the first `UNKNOWN`, so a closed-but-launchable instance cannot reliably be used without an external wait or a recognizer-supported startup state.

Fix direction: keep the fail-closed behavior for arbitrary unknown screens, but make the resolver/foregrounding boundary wait for a responsive rendered game frame before handing control to replacement-core preflight, or classify the verified black startup interval as a bounded launch state. Cover the cold-launch boundary separately from navigation recovery.

Evidence:

- Initial Daily trace: `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T031724Z_707842d6_core_trace.jsonl`
- Initial recovery trace: `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T031728Z_667abf29_core_trace.jsonl`
- Black recovery frame: `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T031730Z_core_20260912T031728Z_667abf29_0001_core_route_source.png`

## Assumption and evidence matrix

| ID | Assumption or acceptance claim | Evidence class | Disposition | Evidence |
| --- | --- | --- | --- | --- |
| DQ-01 | Missing Go OCR can be recovered from clear blue button geometry | `repo_answered` | Passed | Daily fixture positive, negative, and OCR-precedence tests pass. |
| POP-01 | City HUD sparkle no longer becomes a generic popup | `repo_answered` | Passed offline | Direct `NavigationPerception` City regression retains Home controls and remains unblocked. |
| POP-02 | Two different real generic popup layouts retain measured Close controls | `repo_answered` | Passed only at helper boundary | Both sanitized fixtures pass `_build_visual_popup_close_additions`; no positive fixture traverses `NavigationPerception`. |
| REC-01 | Known popups can be closed by the replacement runtime | `live_observed` | Contradicted | Live Savannah offer loses its safe selector before executor recovery; both bounded paths stop. |
| LIVE-01 | Daily status passes on the exact planned `serious_stuff` target | `live_required` | Blocked by role drift | Production path requires `daily_canary`; current target carries `live_testing`. |
| LIVE-02 | Daily status passes on a current role-eligible free target | `live_observed` | Blocked | `mega_old_acc` reached a supported offer and stopped on REC-01 before Daily content. |
| LIVE-03 | Explicit recovery yields two fresh unblocked Home frames | `live_observed` | Failed | Recovery stopped at the supported offer; no tap was sent and no Home frame was claimed. |
| LIVE-04 | A stopped free instance can be launched and immediately reviewed | `live_observed` | Blocked on first attempt | First post-launch frames were black/UNKNOWN; a later bounded observation reached rendered game state. |
| SAFE-01 | Live recovery smoke enforces authorized target ownership | `repo_answered` | Contradicted | The smoke supplies no `required_role` and does not close its runtime. |

## Validation

- Passed: `py -m unittest tests.test_daily_quest_vision tests.test_capture_and_vision tests.test_navigation_core tests.test_core_runtime tests.test_core_workflow tests.test_popup_recovery tests.test_automation_framework` — 258 tests, 2 expected skips.
- Passed: `py -m unittest discover -s tests` — 1,161 tests, 19 expected skips.
- Passed: `git diff --check 6d2a289..HEAD`.
- Not counted: invoking `py tools/validate_navigation_selectors.py` without its required account argument printed usage and performed no validation. The earlier ledger contains a passed pre-fix selector report; it does not prove the new interruption-to-recovery boundary.
- Live safety: all attempts used the canonical account reservation. No resource-changing action, castle selection, generic Android Back, unsafe popup dismissal, or repeated navigation tap occurred.

## Verdict

`implementation_ready: false`

The Daily visual fallback and popup-surface filter are credible in isolation, but the newly integrated popup recovery cannot receive the selector that perception already detected. The live smoke also bypasses required role ownership.

`promotion_ready: false`

Neither required live row passed. Promotion requires fixing REC-01 and the smoke role/lifecycle issue, reconciling the matrix target with current roles, then rerunning Daily status and explicit Home recovery under one exclusive lease with the required final artifacts.
