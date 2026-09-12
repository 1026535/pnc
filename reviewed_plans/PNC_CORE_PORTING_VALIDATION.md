# Replacement core porting validation ledger

## Authored roster port — September 12, 2026

`TaskId.REFRESH_CASTLE_ROSTER` now dispatches to the existing typed `RefreshCastleRosterWorkflow`. It rejects parameters and explicit castle targets before connection, requires only its canonical roster store, and borrows the script's connected graph. The obsolete legacy task and its dedicated fixtures are removed. The Daily canary identity helper now borrows that graph through `assemble_core_runtime`, requires an exact match to the requested castle, and returns fresh unblocked Home evidence without closing the caller's runtime or performing a mutation. The implementation checkpoint is `4d627b7` on `codex/refresh-castle-roster-script-core-port`, rebased onto main `15845b8`.

The authored current-castle proof passed on `serious_stuff`: `CoreStepRunResult`, success, 12 castles, `full_scan`, and final Home. It wrote `.local-data/artifacts/replacement_core/authored_roster_castles.yaml` and checked that the protected `config/castles.yaml` bytes stayed unchanged. Result: `.local-data/artifacts/replacement_core/authored_roster_port_result.json`. Trace: `artifacts/2026-09-12/serious_stuff/20260912T154337Z_203b9fd9_core_trace.jsonl`. Final Home: `20260912T154919Z_core_20260912T154337Z_203b9fd9_0063_core_18_after_1.png` in that directory.

The canary identity-only proof also passed, using the selected-row evidence from that completed roster preflight as its requested target and independently checking fresh live identity. Result: `.local-data/artifacts/replacement_core/canary_identity_port_result.json`. Trace: `artifacts/2026-09-12/serious_stuff/20260912T154937Z_583f7af5_core_trace.jsonl`. Final Home: `20260912T155102Z_core_20260912T154937Z_583f7af5_0026_core_7_after_1.png`. The helper did not execute a resource-changing canary. The old helper's unmodeled Might Rank, Event Center, and Home-root entry routes are not preserved as a fallback; unsupported states stop at the core guard.

Exact live commands were `run_authored_roster_port_proof()` from `.local-data/artifacts/replacement_core/authored_roster_port_live.py` and `run_canary_identity_port_proof()` from the adjacent `canary_identity_port_live.py`, in the retained lease process. Both used configured `LIVE_TESTING`, `keep_warm`, and `serious_stuff` without selecting a castle, sending messages, claiming, or spending. Coding workers remained offline.

The earlier live-control session was unavailable after context recovery. The new sandboxed process acquired a reservation but could not enumerate BlueStacks; it released that reservation before an approved host-access process acquired the canonical lease. That process held the lease across baseline inspection, preparation, both completed proofs, and cleanup. A first screenshot timed out; subsequent evidence showed the BlueStacks launcher, then a game loading frame. The first authored attempt stopped on UNKNOWN without navigation. After the configured app finished loading and canonical safe-popup recovery produced Home, the completed proofs above ran successfully. Preserve failed trace `20260912T154147Z_7f351a77_core_trace.jsonl` and recovered Home `20260912T154308Z_core_20260912T154254Z_8621108f_0002_core_20260912T154254Z_8621108f_reserved_foreground_diagnostic_interruption_popup_1.png`. The pre-existing instance remains open at Home for the next port.

Validation passed: 61 focused canary/dispatch/roster/script-runner tests, three registry preparation tests, four canary tests after root requested missing/blocked/unknown and exception-propagation coverage, and `git diff --check`. The final command `C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe tools/run_tests.py full` passed 1,497 total tests: 1,492 passed and five skipped in 107.313 seconds. All five skips report unavailable optional local screenshot fixtures; the feature worktree's `.test-impact/results.json` records them. Root review found no remaining actionable issues in this slice. Full tests were run once for the merge gate after focused development checks.

The next active implementation is `codex/ensure-game-running-core-port` in `.local-data/worktrees/ensure_game_running`, created from main `15845b8`. It must be synchronized with this roster port before landing. Authored open-building, login, castle selection, sending, resource-changing tasks, and Daily maintenance execution remain incomplete.

## Authored mail port — September 12, 2026

`TaskId.COLLECT_MAIL` now uses typed script dispatch and the existing `CollectMailWorkflow`; its obsolete legacy task is removed. The canonical parser is shared by direct and authored callers. Preconnect validation requires only the archive store used by the selected task, so mail and Chat remain independently available. The feature checkpoint is `2ce100c` on `codex/collect-mail-script-core-port`, based on integrated main `b0ba590`.

The current-castle authored proof on `serious_stuff` returned `CoreStepRunResult`, success, and final Home. Player mail was explicitly unavailable; zero threads were processed or archived. This proves dispatch and the unavailable-mailbox path, not a fresh thread read. The command was `.local-data/artifacts/replacement_core/authored_mail_port_live.py:run_authored_mail_port_proof()` inside the retained process reservation. It used `ApplicationRunner.run`, player mailbox, limit one, archive mode both, only-new false, `LIVE_TESTING`, and `keep_warm`. No castle selection, message sending, claim, or resource spending occurred.

Result: `.local-data/artifacts/replacement_core/authored_mail_port_result.json`. Trace: `artifacts/2026-09-12/serious_stuff/20260912T072001Z_4cc53ea0_core_trace.jsonl`. Final Home: `20260912T072322Z_core_20260912T072001Z_4cc53ea0_0039_core_11_after_1.png` in the trace directory. Runtime evidence followed the existing explicit local artifact configuration; newly authored helper/result files use `.local-data/`.

Validation passed: 45 focused dispatch/parser/workflow/application/registry tests, seven mail workflow tests after root added assertions for archived text and screenshot bytes, 11 architecture/import ownership tests, and `git diff --check`. The final portable gate, `C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe tools/run_tests.py full`, passed 1,493 total tests: 1,489 passed and four expected skips, in 84.476 seconds. Results are in this feature worktree's `.test-impact/results.json`. Root review found no remaining actionable issues in this mail slice.

The next authored roster binding is in `.local-data/worktrees/refresh_castle_roster_script` on `codex/refresh-castle-roster-script-core-port`. Its migration also needs to remove the Daily canary helper's dependency on the legacy roster task by borrowing the existing core preflight, without duplicating scan logic. Authored open-building still needs parity work for offscreen and unbuilt targets before its legacy task can be removed. Other remaining workflows retain the limits recorded below.

## Resumed ports — September 12, 2026

The recovered work now implements direct roster refresh and authored Kingdom Chat dispatch. The candidate includes `origin/main` through `c7dfdd5`, preserving quiescent shutdown, scoped reservations, and generated-output defaults. It combines the roster branch through `93c2f84` and Chat branch through `23be5d0`; both feature checkpoints were pushed before integration. Older checkpoints below remain historical evidence.

Roster refresh passed the corrected live scan on `serious_stuff`: 12 castles, `full_scan`, two top-seek swipes, three scan swipes, and two distinct scan windows. The canonical store wrote `artifacts/replacement_core/roster_port_castles.yaml`. The helper checked that the real `config/castles.yaml` bytes were unchanged. Trace: `artifacts/2026-09-12/serious_stuff/20260912T070027Z_4bf42509_core_trace.jsonl`; final Home: `20260912T070534Z_core_20260912T070027Z_4bf42509_0063_core_18_after_1.png`. The earlier whitespace-gap failure is resolved; the overlap, duplicate, cycle, and exact selected-identity guards remain enabled.

Authored Kingdom Chat passed through `ApplicationRunner.run` using generated YAML with one current-castle `collect_kingdom_chat` step. The result was `CoreStepRunResult`, `success`, and final `pnc_home_city`. Trace: `artifacts/2026-09-12/serious_stuff/20260912T070604Z_fa61a59e_core_trace.jsonl`; final Home: `20260912T071116Z_core_20260912T070604Z_fa61a59e_0046_core_12_after_1.png`. Result: `artifacts/replacement_core/authored_chat_port_result.json`. This proves the typed authored dispatch path; it does not claim live validation of switching to another castle.

One process held the canonical `serious_stuff` reservation across both proofs and their preparation. Coding workers remained offline. The configured game returned to Home between workflows, no castle was selected, no message was sent, and no resource was spent. The earlier launcher/UNKNOWN interruption was superseded by a fresh confirmed Home observation before these proofs. The pre-existing instance stayed open with `keep_warm` cleanup.

Focused integration validation passed 69 tests. The final `tools/run_tests.py full` gate passed: 1,490 total tests, 1,486 passed and four expected skips, in 146.614 seconds. Results are in the integration worktree's `.test-impact/results.json`. `git diff --check` passed, and root review found no remaining actionable issues in these two slices. The Windows `py` launcher was unavailable after the sandbox profile changed; the gate used `C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe tools/run_tests.py full` instead.

Remaining caller migration: authored mail, open-building, and roster task IDs still need their typed bindings. Authored mail is being implemented separately on `codex/collect-mail-script-core-port`; its unlanded work must not be confused with the already integrated direct mail workflow. Login, castle selection, sending, resource-changing tasks, and Daily maintenance execution remain outside these completed slices.

## Recovery checkpoint — September 12, 2026

This checkpoint was reconstructed from fetched `origin/main` at `76c486f`, the current task registry, application entrypoints, branch ancestry, and preserved worktree diffs after a reported loss of conversation context. Earlier sections below are chronological evidence; their old blockers and limitations are superseded where this checkpoint or the final role-selected evidence says otherwise.

### Already merged: reuse these implementations

| Capability | Canonical code and status |
| --- | --- |
| Shared replacement core | `core_runtime.py`, `navigation_core.py`, `core_workflow.py`, and `NavigationPerception` are on main. Active-castle preflight now includes a bounded nonselecting roster search; the older limitation requiring manual roster positioning no longer describes the code. |
| Daily Quest status | `DailyQuestStatusWorkflow` and its application/CLI entrypoint are on main. This reads status; it does not port Daily maintenance execution. |
| Collect-mail | `CollectMailWorkflow` and the direct Python API are on main. |
| Kingdom Chat collection | `CollectKingdomChatWorkflow` and the direct Python API are on main. |
| Open-building | `OpenBuildingWorkflow`, direct Python API, and dedicated CLI are on main. |
| Instance ownership | Canonical process leases, scoped account reservations, and the later quiescent-shutdown change `76c486f` are on main. Preserve the outer phase's cleanup policy when integrating subsequent ports. |

Git ancestry confirms that the tips of `codex/pnc-replacement-core`, `codex/pnc-replacement-core-remaining-issues`, `codex/collect-mail-core-port`, `codex/collect-kingdom-chat-core-port`, and `codex/open-building-core-port` are contained in main. Their retained worktrees are not evidence of unmerged work. The direct ports were integrated through `3a251ca`, `dcd4a07`, and `68e7349`; their final combined evidence is recorded in `instructions/CORE_WORKFLOW_PORTING.md`.

### Work in progress: preserve before resuming

| Branch and worktree under `artifacts/replacement_core/ports/` | Verified state |
| --- | --- |
| `codex/refresh-castle-roster-core-port` / `refresh_castle_roster` | Two local commits through `f6bf51a` implement typed roster refresh and migrate its tests. An uncommitted correction normalizes OCR spelling only for scan identity, with exact kingdom matching. The first live scan rejected a false gap caused by whitespace variation and wrote no roster. This port is not on main and is not live-complete. |
| `codex/kingdom-chat-heartbeat-core-port` / `kingdom_chat_heartbeat` | Uncommitted typed script-dispatch work builds on the existing direct Chat workflow. It is a caller migration, not a second Chat workflow. The work includes registry metadata, a dispatcher over the existing connected runtime, and legacy task removal. Tests and integration review remain unfinished. |
| `codex/campaign-core-port` / `campaign` | Branch tip is an existing main ancestor and contains no unique port commit. The branch name does not prove implementation. |

Both active port worktrees were based on `68e7349` when this checkpoint was taken and must incorporate `76c486f` before landing. That change overlaps the core runtime, script runner, application/API facade, lease finalization, and cleanup ownership. Do not overwrite it with an older port version or hot-reload an obsolete native lease manager into current runtime code.

The current default task registry on main still registers all 16 legacy task classes. In particular, authored `TaskId.COLLECT_MAIL`, `COLLECT_KINGDOM_CHAT`, and `OPEN_BUILDING` steps still use the legacy script runner despite their direct APIs being ported. Login, castle selection, roster refresh, sending, construction, upgrade, research, gathering, and campaign have not acquired typed production script dispatch on main. Bootstrap and popup recovery already have shared owners; do not manufacture empty ports for catalog entries or duplicate those owners.

### Live ownership and validation state

The user-selected target remains `serious_stuff`, with no castle switching or resource spending. Coding workers remain offline. Hold one canonical lease across preparation, all dependent operations, and cleanup; an idle coding worker must not independently manipulate the screen.

The failed roster trace is `artifacts/2026-09-12/serious_stuff/20260912T062708Z_ac521393_core_trace.jsonl`. The source window `20260912T062946Z_core_20260912T062708Z_ac521393_0050_core_14_castle_roster_scroll_after_1.png` and next window `20260912T063007Z_core_20260912T062708Z_ac521393_0053_core_15_castle_roster_scroll_after_1.png` visibly overlap. Offline parsing reproduced `gimme cookies` versus `gimmecookies`. The correction must reuse `normalize_ocr_text`, retain the overlap/cycle guards, and rerun the bounded proof before any full-scan result is accepted. The proof directs `CastleRosterStore` to an artifact file; actual `config/castles.yaml` is protected.

An explicit recovery confirmed Home at `20260912T063348Z_core_20260912T063329Z_a6d9b70b_0007_core_2_after_1.png`. The prior lease process subsequently ended. A new process acquired the canonical lease, but its read-only baseline at `20260912T064259Z_core_20260912T064259Z_90f747a8_0001_new_series_baseline.png` showed a black Android frame and was classified UNKNOWN. No navigation followed that observation. Recheck runtime and foreground state under the held lease before resuming; do not assume the older Home frame is still current. Process and terminal IDs are ephemeral and must be verified from the active session.

Use focused tests or `py tools/run_tests.py affected --base origin/main --explain` during corrections. The earlier roster full run had 1,454 total tests: 1,450 passed and four skipped, but preceded the live OCR finding. It does not validate the uncommitted correction. Run the required final full suite only after live feedback is resolved and the candidate is synchronized and reviewed for merging. Documentation-only checkpoint edits require `git diff --check`, not another test run.

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

Both defects now have deterministic offline regressions. The Daily parser recognizes a
visually clear blue Go button only after known OCR states, and the generic-X fallback
requires popup-surface ownership after recognized popup handling. The sanitized City
frame remains unblocked Home, while two sanitized real popup layouts retain measured
close controls. Fresh live acceptance remains blocked by concurrent control of the
configured emulator, so these fixes are not yet promoted to a live-passed verdict.

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

## Remaining-issues implementation validation

- **Passed:** `py -m unittest tests.test_daily_quest_vision`: 8 tests, no failures.
- **Passed:** `py -m unittest tests.test_capture_and_vision tests.test_navigation_core tests.test_core_runtime tests.test_core_workflow tests.test_popup_recovery`: 193 tests, 2 expected local-fixture skips, no failures.
- **Passed:** `py -m unittest discover -s tests`: 1,064 tests, 19 expected skips, no failures, after rebasing onto the latest `origin/main`. The additional skip is the explicitly opt-in live recovery smoke.
- **Passed:** `py -m unittest tests.test_live_core_workflow_smoke`: 1 expected opt-in skip with live execution disabled.
- **Passed:** `git diff --check`.
- **Blocked by concurrent emulator control:** the fresh selector validation report `C:/Users/lebel/pnc/artifacts/replacement_core/core_port_selectors/20260911T202732Z_serious_stuff_navigation_validation.yaml` recorded a Home-to-VIP-to-Home sequence instead of a Quest destination. During the following Daily proof, independently generated `navigation_validation_30` through `navigation_validation_38` artifacts continued appearing for the same instance. The Daily command stopped on its changed-source guard before a workflow action. No resource-changing action or castle selection occurred.
- **Required rerun with exclusive instance access:** the Daily status command and `PNC_RUN_LIVE_SMOKE=1` recovery smoke from the remaining-issues plan. Neither live matrix row is marked passed from the contended session.

The live emulator was already running and the configured game was foregrounded. Its ADB connection was resolved through the configured runtime and verified responsive. The separate roster setup used one read-only scroll and no castle selection; the final status command sent no resource-changing action. The Daily content extraction and Home return are confirmed for the authorized `serious_stuff` run. The separate recovery proof after the selector tool failed closed on the popup false positive described above; no additional taps were sent.

## Final role-selected evidence (2026-09-12)

The final bounded proofs used the current live roles under the exclusive canonical lease. The `daily_canary` role resolved to `mega_old_acc`; preparation verified `ensure_game_running` and login. The preparation controller then raised a reporting-only `AttributeError` while reading an absent `RunResult.succeeded` field, but the subsequent Daily workflow result itself reported `succeeded=true`, `exit_screen=PNC_HOME_CITY`, `coverage=visible_viewport`, five visible rows all classified as `go`, and `unknown_title_count=0`. The Daily content artifact is `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T044036Z_core_20260912T043911Z_8821a7f21_0021_workflow_content.png`; the final Home frame is `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T044057Z_core_20260912T043911Z_821a7f21_0025_core_5_after_1.png`; the trace is `C:/Users/lebel/pnc/artifacts/2026-09-12/mega_old_acc/20260912T043911Z_821a7f21_core_trace.jsonl`.

Selector validation was first attempted against `mega_old_acc` and correctly failed its role gate because that validator requires the current `live_testing` role. It was rerun against `serious_stuff`, the current `live_testing` account, and passed with one pass, zero failures, and zero skips. The report is `C:/Users/lebel/pnc/artifacts/replacement_core/core_port_selectors/20260912T044200Z_serious_stuff_navigation_validation.yaml`.

The explicit recovery smoke ran on `testing`, the current `SMOKE_TEST` account, and passed one test in 14.994 seconds. Its source frame is `C:/Users/lebel/pnc/artifacts/2026-09-12/testing/20260912T044211Z_core_20260912T044207Z_b0ced5b8_0001_core_route_source.png`; its final recovery frame is `C:/Users/lebel/pnc/artifacts/2026-09-12/testing/20260912T044218Z_core_20260912T044207Z_b0ced5b8_0002_live_recovery_follow_up.png`; its trace is `C:/Users/lebel/pnc/artifacts/2026-09-12/testing/20260912T044207Z_b0ced5b8_core_trace.jsonl`.

The focused offline validation covering the affected navigation, perception, popup, runtime, live-smoke wiring, and Daily paths completed with 234 tests passing and 3 expected skips. The full offline suite completed with 1,207 tests passing and 22 expected skips. No live proof spent resources, switched castles, or used an unsafe popup action.

The initial Savannah live failure and the deterministic semantic popup identity guard remain part of the engineering evidence. Savannah did not reappear during this final live run, so these results do not claim live reappearance or live dismissal of that popup family after the guard was added.
