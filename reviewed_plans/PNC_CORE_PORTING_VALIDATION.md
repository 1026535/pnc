# Replacement core porting validation ledger

This ledger records the bounded evidence for the shared replacement workflow boundary. The authorized `serious_stuff` run below is the final successful Daily Quest status proof; earlier `testing` interruptions remain preserved as superseded safety evidence.

## Contract evidence

| Check | Evidence | Status |
| --- | --- | --- |
| One connected runtime and shared capture/perception graph | `build_core_runtime` composes one `ConnectedAccountRuntime`, `NavigationPerception`, and `NavigationCore`; factory construction does not navigate. | Offline passed |
| Typed content cannot replace screen identity or controls | `NavigationPerception.build(..., include_content=True)` copies typed castle/content fields while retaining independently recognized screen and controls. | Offline passed |
| Read-only effect gate | `CoreWorkflowRunner` rejects `RESOURCE_CHANGING` before navigation or capture. | Offline passed |
| Fresh content boundary | `WorkflowContext.observe_content` requires a post-navigation capture with a newer timestamp, expected screen, and no blocking popup. | Offline passed |
| Passive initial settle | Loading may receive bounded passive observations; initial `UNKNOWN` or popup stops immediately; a capture that arrives after the time budget cannot satisfy stability. | Deterministic offline passed |
| Parser failure evidence | Core runtime records the sanitized capture event before perception, preserving the screenshot basename when parsing raises. | Deterministic offline passed |
| Active identity preflight | Manage Characters content must be fresh relative to navigation completion, unblocked, and backed by exact current-castle evidence; no castle switch is available. | Offline guard passed; serious_stuff live proof passed |
| Lifecycle and exit | Runner owns entry, execute, and exit; exit failure propagates without replay or automatic recovery. | Offline passed |

## Bounded live interruption evidence

The configured live surface showed the known VIP daily reset popup. Independent perception classified it as `PNC_VIP_DAILY_RESET` with `blocking_popup=True` and no actionable controls. The replacement path is expected to stop at that frame; it must not guess a dismissal or continue the workflow.

A separate bounded probe also demonstrated the competing-source guard. More was confirmed, then the next fresh source frame was City because another local probe had closed the menu. The core rejected the changed source before sending another action. The frame was a real City observation rather than a screen-classification error; the stop is the intended fail-closed result.

These are earlier `testing`-target interruptions. They prove stop behavior and remain part of the history, but are superseded for the final verdict by the separately authorized `serious_stuff` run below. The `testing` target was not reused for that result.

## Final proof result

The exact configured non-spending command passed for the authorized alternate target:

```powershell
py -m pnc_automation.app.entrypoints.cli daily-quest-status --config C:/Users/lebel/pnc/config/accounts.yaml --account serious_stuff
```

The command returned `succeeded: true`, `exit_screen: pnc_home_city`, and `coverage: visible_viewport`. It captured five visible rows and no unknown titles. Four rows have `go` state; one remains `unknown_action` because the visible Go control was not resolved by OCR. The result does not claim complete action-state recognition. JSON output: `C:/Users/lebel/pnc/artifacts/replacement_core/core_port_serious_live_final.log`.

Active identity was verified without castle selection. The selected checkmark was outside the initial Manage Characters viewport, so a separate bounded read-only roster setup used one roster scroll through the existing observed-control setup before the status command. The replacement workflow itself did not search, scroll, or switch castles. This limitation is recorded for future preflight work: only a visibly selected row is currently available to the preflight parser, and there is no automated roster search.

The first `serious_stuff` preflight stopped closed because no selected entry was visible in its initial viewport (`C:/Users/lebel/pnc/artifacts/2026-09-11/serious_stuff/20260911T010814Z_c6543519_core_trace.jsonl`). The separate roster setup trace (`C:/Users/lebel/pnc/artifacts/2026-09-11/serious_stuff/20260911T011018Z_9274103a_core_trace.jsonl`) records the bounded read-only preparation that made the selected row visible. Both are preserved as superseded preconditions for the authorized final run, not as evidence that the replacement workflow searched the roster.

Evidence includes the Daily frame `20260911T011203Z_core_20260911T011055Z_01b698af_0020_workflow_content.png`, final Home frame `20260911T011217Z_core_20260911T011055Z_01b698af_0024_core_5_after_1.png`, and trace `C:/Users/lebel/pnc/artifacts/2026-09-11/serious_stuff/20260911T011055Z_01b698af_core_trace.jsonl`. The selector validator also passed for `PNC_BOTTOM_NAV_QUEST` with one pass, zero failures, and zero skips; report: `C:/Users/lebel/pnc/artifacts/replacement_core/core_port_selectors/20260911T011301Z_serious_stuff_navigation_validation.yaml`.

The separate explicit `recover_to_home` follow-up after the selector tool left Daily **failed closed**: its first City frame was followed by a false-positive `PNC_POPUP` classification on a HUD sparkle, with detector evidence `visual_upper_right_close_x`. No additional tap was sent and the game was visibly left in City. Trace: `C:/Users/lebel/pnc/artifacts/2026-09-11/serious_stuff/20260911T011349Z_39a36a1a_core_trace.jsonl`; frame: `20260911T011403Z_core_20260911T011349Z_39a36a1a_0004_core_1_after_1.png`. This separate recovery failure does not invalidate the earlier production workflow result or selector check, and the live boundaries should not be treated as fully clean or merge-ready.

## Open issues and acceptance checks

### Daily action-state OCR gap

- **Observed:** `Train Cavalry x250` visibly had a Go button but produced `unknown_action`. The other four visible rows produced `go`.
- **Impact:** status reporting is honest but incomplete for one visible row. No action was sent.
- **Owner:** the canonical Daily Quest parser and its visual/OCR tests.
- **Done when:** the saved Daily frame classifies the cavalry row as `go`, unclear buttons still remain `unknown_action`, and a new live status run reports the expected five states.
- **Evidence:** `C:/Users/lebel/pnc/artifacts/2026-09-11/serious_stuff/20260911T011203Z_core_20260911T011055Z_01b698af_0020_workflow_content.png`.

### Popup false positive on City

- **Observed:** an animated HUD sparkle matched the generic upper-right Close-X detector after recovery had already reached City.
- **Impact:** the core stopped safely, but it could not confirm the recovery result.
- **Owner:** the canonical popup detector. Navigation should continue trusting its interruption result.
- **Done when:** the saved City frame is recognized as unblocked, real popup fixtures remain blocked, and a live recovery confirms two fresh City observations.
- **Evidence:** `C:/Users/lebel/pnc/artifacts/2026-09-11/serious_stuff/20260911T011403Z_core_20260911T011349Z_39a36a1a_0004_core_1_after_1.png` and `C:/Users/lebel/pnc/artifacts/2026-09-11/serious_stuff/20260911T011349Z_39a36a1a_core_trace.jsonl`.

These issues block a merge-readiness claim. They do not invalidate the successful read-only Daily content capture and Home return recorded above.

## Validation commands and disposition (2026-09-11 UTC)

- **Passed:** `py -m unittest discover -s tests` on the final code: 1,056 tests in 253.996 seconds, 18 expected skips, no failures. Log: `C:/Users/lebel/pnc/artifacts/replacement_core/core_port_full_tests_final.log`.
- **Passed:** `py -m unittest tests.test_core_runtime tests.test_core_workflow`: 18 tests after the final preflight guards and fake-clock cases.
- **Passed:** `git diff --check`.
- **Superseded failures:** early focused tests contained list/tuple and fake-constructor mistakes; an initial full-suite run read incomplete new test helpers while the worker was editing. These fixture issues are fixed and covered by the final full-suite pass.
- **Passed expected-stop proof:** `py -m pnc_automation.app.entrypoints.cli daily-quest-status --config C:/Users/lebel/pnc/config/accounts.yaml --account testing` stopped on the VIP reset popup before any navigation action. Trace: `C:/Users/lebel/pnc/artifacts/2026-09-11/testing/20260911T003230Z_88805c3a_core_trace.jsonl`. Baseline: `C:/Users/lebel/pnc/artifacts/2026-09-11/testing/20260911T001942Z_core_porting_baseline.png`.
- **Separate setup:** one freshly verified VIP Close action was sent through the existing executor, outside the replacement workflow. Source evidence: `C:/Users/lebel/pnc/artifacts/2026-09-11/testing/20260911T003306Z_core_port_vip_close_source.png`. This does not add popup recovery to the replacement core.
- **Blocked normal proof:** the same production command stopped before its next tap because a competing navigation probe changed More back to City. Trace: `C:/Users/lebel/pnc/artifacts/2026-09-11/testing/20260911T003328Z_02b89a31_core_trace.jsonl`; changed-source frame: `C:/Users/lebel/pnc/artifacts/2026-09-11/testing/20260911T003434Z_core_20260911T003328Z_02b89a31_0007_core_2_source.png`. Concurrent `visual_20260911T003359Z_2f587734` captures in the same testing artifact directory establish overlapping device use. Reserve exclusive access before rerunning the production command above.
- **Superseded alternate-target history:** the earlier `testing` expected-stop and competing-probe records above remain valid safety evidence, but they are superseded for the final status verdict by the authorized `serious_stuff` run. The first `serious_stuff` identity attempt also stopped when its selected row was outside the visible viewport; a separate one-scroll read-only roster setup then made the row visible without castle selection.
- **Passed final status proof:** `py -m pnc_automation.app.entrypoints.cli daily-quest-status --config C:/Users/lebel/pnc/config/accounts.yaml --account serious_stuff` returned success, five visible rows, no unknown titles, and final `pnc_home_city`. Four row states are `go`; one is `unknown_action` because visible Go OCR was unresolved. This is an explicit uncertainty, not a complete action-state claim. Result: `C:/Users/lebel/pnc/artifacts/replacement_core/core_port_serious_live_final.log`.
- **Passed selector check:** `py tools/validate_navigation_selectors.py --config C:/Users/lebel/pnc/config/accounts.yaml --account serious_stuff --selector PNC_BOTTOM_NAV_QUEST --output-dir C:/Users/lebel/pnc/artifacts/replacement_core/core_port_selectors`; one passed, zero failed, zero skipped. Report: `C:/Users/lebel/pnc/artifacts/replacement_core/core_port_selectors/20260911T011301Z_serious_stuff_navigation_validation.yaml`.

The live emulator was already running and the configured game was foregrounded. Its ADB connection was resolved through the configured runtime and verified responsive. The separate roster setup used one read-only scroll and no castle selection; the final status command sent no resource-changing action. The Daily content extraction and Home return are confirmed for the authorized `serious_stuff` run. The separate recovery proof after the selector tool failed closed on the popup false positive described above; no additional taps were sent.
