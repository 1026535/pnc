# Porting a workflow to the replacement core

This guide describes the bounded path for moving one workflow onto the reviewed navigation core. It applies to the shared runtime in `pnc_automation/app/automation/engine/`, the typed PNC observations, and the application and CLI entrypoints. The core permits read-only and non-spending state-change workflows; resource-changing workflows are rejected before they observe the device.

## Canonical owners

| Responsibility | Owner | Contract |
| --- | --- | --- |
| Screenshot capture and independent typed perception | `pnc_automation/app/automation/engine/core_runtime.py:CoreRuntime.observe` and `pnc_automation/app/pnc/vision/navigation_perception.py:NavigationPerception` | One fresh persisted screenshot is parsed. Content is optional and cannot create or replace screen controls. Capture metadata is recorded before parsing so a parser failure keeps its artifact evidence. |
| Connected runtime composition | `build_core_runtime` | Builds exactly one `ConnectedAccountRuntime`, uses its existing screenshot service and observed action executor, and does not navigate while constructing the graph. |
| Reviewed routing and completion | `pnc_automation/app/automation/engine/navigation_core.py:NavigationCore` and `reviewed_navigation_edges` | Current-frame visual evidence authorizes a single action. Completion requires fresh observed destination frames. Unknown screens, unresolved popups, stale frames, and unexpected destinations stop the route. The connected `ObservedActionExecutor` may clear each newly observed safe popup through its explicit selector before routing continues. |
| Known popup recovery | `CoreRuntime.observe` and `ObservedActionExecutor.recover_interruption_if_required` | Core observations pass through the canonical bounded recovery path. OCR-owned reconnect and Valiant Conquest modals, VIP reset, and generic X popups with an explicit safe selector may be dismissed once per visual fingerprint. Task-owned dialogs, unknown screens, missing selectors, and repeated fingerprints remain fail-closed; Android Back is never inferred. |
| Workflow effect and lifecycle | `pnc_automation/app/automation/engine/core_workflow.py` | `WorkflowSpec` validates known entry/exit screens and a `WorkflowEffect`. `CoreWorkflowRunner` allows `READ_ONLY` and `NONSPENDING_STATE_CHANGE`, owns entry, execution, and exit, and reports success only after exit is confirmed. |
| Workflow access | `WorkflowContext` | Exposes only reviewed `navigate` and fresh expected-screen `observe_content`. It has no raw executor, claim, swipe, selector-tap, or transition API. |
| Typed Daily Quest conversion | `pnc_automation/app/automation/daily_maintenance/coordinator.py:daily_viewport_from_observation` | Converts the canonical typed observation. Do not reimplement row parsing or claim semantics in a replacement workflow. |
| Application and direct API wiring | `ApplicationRunner.run_daily_quest_status`, `ApplicationRunner.run_collect_mail`, `ApplicationRunner.run_collect_kingdom_chat`, and `pnc_automation.app.entrypoints.api` | Direct application and Python API calls validate before connection, perform explicit active-castle identity preflight, hold the configured account reservation for the complete operation, and return typed core results. The `daily-quest-status` CLI remains the structured JSON example; typed collect-mail and Kingdom Chat are direct Python ports. |
| Mutation authorization | `daily_maintenance/authorization.py:DailyMutationAuthorizer`, `daily_maintenance/coordinator.py:ForbiddenDailyMutationExecutor`, `pnc_automation/app/pnc/persistence/daily_run_journal_store.py:DailyRunJournalStore` | These are the existing approval, executor, and journal owners for future resource-changing work. Do not add a second approval flag or a parallel journal. |

## Porting sequence

1. Inventory the existing workflowâ€™s canonical parser, typed result, screen controls, navigation edges, tests, authorizer, executor, and journal. Record whether every step is read-only, a non-spending state change, or resource-changing. Reuse the existing parser and result model where they exist.

2. Gather game-first route evidence when a required edge is absent or its return screen is conditional. Evidence must show the visible source control, one reviewed action, fresh completion frames, and the actual return destination. Do not infer a route from a coordinate, a remembered camera position, or a legacy fallback.

3. Define a validated `WorkflowSpec`. Use known `ScreenType` values for entry and exit and an explicit `WorkflowEffect`:

   ```python
   spec = WorkflowSpec(
       name="daily_quest_status",
       entry_screen=ScreenType.PNC_HOME_CITY,
       exit_screen=ScreenType.PNC_HOME_CITY,
       effect=WorkflowEffect.READ_ONLY,
   )
   ```

   A resource-changing spec is intentionally rejected by `CoreWorkflowRunner` before navigation or capture. A non-spending state change may use `WorkflowEffect.NONSPENDING_STATE_CHANGE`; resource-changing work must first define how the existing exact-budget authorizer, mutation executor, and journal are bridged into the constrained lifecycle.

4. Implement the workflow body through `WorkflowContext`. Navigate to the content screen, call `observe_content(expected_screen=...)` once the destination is confirmed, and pass that observation to the canonical typed converter. The context requires a fresh capture newer than the last navigation observation and rejects an unresolved blocking popup. Known safe popups are handled at the connected runtime observation boundary before the workflow sees them. Do not expose the raw runtime or actuator to the workflow.

   The current Daily status implementation is the minimal pattern:

   ```python
   @dataclass(frozen=True, slots=True)
   class DailyQuestStatusWorkflow(CoreWorkflow[DailyQuestStatusResult]):
       _spec = WorkflowSpec(
           name="daily_quest_status",
           entry_screen=ScreenType.PNC_HOME_CITY,
           exit_screen=ScreenType.PNC_HOME_CITY,
           effect=WorkflowEffect.READ_ONLY,
       )

       @property
       def spec(self) -> WorkflowSpec:
           return self._spec

       def execute(self, context: WorkflowContext) -> DailyQuestStatusResult:
           context.navigate(ScreenType.PNC_QUEST_DAILY)
           observation = context.observe_content(expected_screen=ScreenType.PNC_QUEST_DAILY)
           viewport = daily_viewport_from_observation(observation)
           if not viewport.rows and not viewport.unknown_titles:
               raise TaskVerificationError(
                   "No recognized rows or unknown titles were visible.",
                   artifact_path=viewport.artifact_path,
               )
           return DailyQuestStatusResult(
               viewport=viewport,
               captured_at=observation.captured_at,
               coverage="visible_viewport",
           )
   ```

5. Integrate through `build_core_runtime` and the application runner. Factory construction connects the configured emulator and creates the artifact directory, but must not navigate or run a workflow. `CoreRuntime.preflight_active_castle_identity` explicitly foregrounds the configured app, passively settles loading within `NavigationPolicy`, navigates to Manage Characters, and requires fresh, unblocked content with exact `current_castle_evidence`. When the selected row is outside the initial viewport, it rewinds toward the start and scans the roster with bounded swipes. Repeated viewport signatures stop each direction. It never taps or selects a castle row. Return Home before running the workflow. Identity details are not written to the sanitized JSONL trace.

6. Add deterministic offline tests before a device run. Cover factory composition, typed content preservation, loading settle, unknown and popup stop, stale and late captures, parser failure artifact retention, mutation rejection before capture, workflow success and empty/unknown content, exit failure without replay, explicit recovery, CLI JSON, and application preflight ordering. Use typed observations and fake clocks; do not use BlueStacks, ADB, credentials, or private configuration in ordinary tests.

7. Reserve exclusive use of the configured BlueStacks instance for the bounded proof, including other agents and tasks. Keep its currently active castle. Let the shared preflight perform its bounded nonselecting roster scan when the selected row is outside the initial viewport. Leave each workflow body free of roster scrolling. Use the exact non-spending command with configured arguments:

   ```powershell
   py -m pnc_automation.app.entrypoints.cli daily-quest-status --config <config-path> --account <account-id>
   ```

   The proof may foreground the configured app and navigate through reviewed controls. The status workflow must not scroll, claim, switch castles, or spend resources. A route that sees an unknown screen, unresolved popup, stale capture, or competing source frame must stop and preserve its evidence.

8. Require final Home evidence. A successful result is emitted only after the runner confirms the declared exit screen. A failure at exit propagates without an automatic retry or `finally` navigation. Recovery is a separate explicit call to `CoreWorkflowRunner.recover_to_home`; it uses the reviewed graph, allows the connected safe-popup recovery boundary to clear known interruptions, and stops on unknown or unresolved popup states.

9. Migrate production callers only after offline parity and the bounded proof are complete. Then remove the obsolete duplicate capture/perception/construction path for that caller. Keep unrelated legacy daily maintenance unchanged until each workflow has its own reviewed port and evidence.

## Current boundary

The direct `open-building` CLI and Python entry points use the replacement core. Authored scripts with `TaskId.OPEN_BUILDING` still need their binding migrated to the typed script dispatcher.

`DailyQuestStatusWorkflow` reports one `visible_viewport` from the fresh Daily screen. It does not scroll, claim, acknowledge, select a castle, infer unseen rows, or claim full-screen coverage. It fails when both recognized rows and unknown titles are absent. Known safe popup recovery belongs to the connected runtime and shared observed-action executor; the workflow has no generic popup dismissal policy. Navigation does not retry a tap, replay a failed workflow, or use the legacy observer as a fallback. A task-owned dialog or popup without an explicit safe selector still stops the route.

Active-castle preflight recognizes the selected row through exact Manage Characters evidence. It searches a long roster with bounded swipes in both directions and stops on repeated viewport signatures without tapping a castle row.

## Migration status

The full workflow migration is incomplete. A direct API port does not migrate an authored YAML task with the same name. The integrated direct ports below retain that distinction.

| Workflow or boundary | Current status |
| --- | --- |
| Daily Quest status | Implemented as the reference typed workflow; this reads status, not Daily maintenance execution. |
| Open-building | Integrated direct CLI/Python port; authored task dispatch remains legacy. |
| Collect-mail | Direct Python port and typed authored `TaskId.COLLECT_MAIL` dispatch share `CollectMailWorkflow`. |
| Kingdom Chat collection | Integrated direct Python port and typed authored `TaskId.COLLECT_KINGDOM_CHAT` dispatch. |
| Authored scripts | `TaskId.COLLECT_KINGDOM_CHAT` and `TaskId.COLLECT_MAIL` use the typed core dispatcher; other registered `TaskId`/YAML steps remain on legacy dispatch. |
| Bootstrap and roster workflows | Roster refresh has a typed direct Python API; its authored task remains legacy. Login and castle selection remain unported. Core preflight reuses foreground/bootstrap behavior; safe popup recovery belongs to the canonical runtime. Neither is an empty workflow to recreate. |
| Chat and mail sending | Need typed input/send operations and explicit authorization for the actual message and destination before live sending. |
| Resource-changing workflows | Construction, upgrade, research, gathering, campaign actions, and Daily maintenance execution still need reviewed typed operations and the existing authorizer/executor/journal bridge. Live spending needs an exact action, target, and budget. |

## Typed Kingdom Chat port

`CollectKingdomChatWorkflow` is the typed direct Python port for one Kingdom Chat heartbeat. Its `WorkflowSpec` uses `PNC_HOME_CITY` for both entry and exit and `WorkflowEffect.NONSPENDING_STATE_CHANGE`: opening the chat may update in-game read state, while the canonical `ChatArchiveStore` writes the local archive. The workflow enters Chat through the reviewed Home shortcut, captures content with the Chat transcript observation scope, and leaves final Home confirmation to `CoreWorkflowRunner`.

`WorkflowContext.select_chat_channel(ChatChannel.WORLD)` validates the enum and delegates to `NavigationCore`. The core reacquires a fresh unblocked Chat frame, skips the tap when Kingdom is already active, or requires the current-frame template-backed Kingdom tab, taps once, and accepts completion only after bounded fresh Chat frames confirm the requested active channel. The workflow uses the canonical `visible_player_chat_entries` and `visible_unsupported_chat_entries` projections before persisting through `ChatArchiveStore`; unsupported transcript shapes fail closed before archive writes.

`ApplicationRunner.run_collect_kingdom_chat` performs archive availability and exact active-castle preflight before constructing the workflow, then closes its one connected runtime on every outcome. The direct `AutomationApi.collect_kingdom_chat` and module helper hold or reuse the canonical scoped account reservation for the complete call and return the typed core result. Authored `TaskId.COLLECT_KINGDOM_CHAT` YAML steps use the typed `ScriptRunner` core dispatch boundary and retain the typed result, with no fallback adapter or replay. The migration table lists the other completed bindings.

The September 12 live proof on `serious_stuff` archived five visible player messages and confirmed final Home. Its trace is `artifacts/2026-09-12/serious_stuff/20260912T054101Z_9deb03aa_core_trace.jsonl`; final Home is `20260912T054325Z_core_20260912T054101Z_9deb03aa_0039_core_10_after_1.png` in the same directory. The canonical process-scoped instance lease remained held across implementation and dependent probes. No message was sent and no castle was selected.

The first attempt exposed an oversized Home shortcut template: its center at y=840 hit the quest tracker. The corrected crop isolates the Chat icon and centers at (26,869) on the 540Ã—960 fixture. Preserve the original failed trace `20260912T053222Z_124b53df_core_trace.jsonl`; it explains the regression fixture and does not prove a legacy registry misclick.

The shared Chat selector passed from both Home and World Map in `artifacts/replacement_core/kingdom_chat_selectors/20260912T054642Z_serious_stuff_navigation_validation.yaml`. A subsequent core Back action proved the conditional return: World-origin Chat returns to World Map, while Home-origin Chat returns Home. The source and destination are `20260912T054655Z_core_20260912T054650Z_e37b4dc7_0002_core_1_source.png` and `20260912T054700Z_core_20260912T054650Z_e37b4dc7_0003_core_1_after_0.png`. The reviewed Back edge now accepts either observed parent and replans toward the requested destination. This does not add a World-to-Chat core entry edge; that still needs current-frame core control evidence.

The corrected live rerun confirmed Chat â†’ World Map â†’ Home, then Home â†’ Chat, Alliance selection, Kingdom selection, and final Home. Its trace is `artifacts/2026-09-12/serious_stuff/20260912T055048Z_341e9d87_core_trace.jsonl`; final Home is `20260912T055210Z_core_20260912T055048Z_341e9d87_0023_core_6_after_1.png` in the same directory. The compact outcome is `artifacts/replacement_core/kingdom_chat_tabs_result.json`. Both selector cases passed again in `kingdom_chat_selectors/20260912T055035Z_serious_stuff_navigation_validation.yaml` while preparing that conditional-return proof.

The live helpers ran inside one Python process holding the canonical outer lease, through `AutomationApi.collect_kingdom_chat`, `tools/validate_navigation_selectors.py:main` with `--account serious_stuff --selector PNC_CHAT_SHORTCUT`, and the typed `WorkflowContext` channel operations. Reloading the corrected navigation module preserved the original lease-manager instance and reservation; no competing process acquired the emulator between probes. The game was already running and remained open at Home.

Validation for this Chat branch:

- `py -m unittest tests.test_navigation_core tests.test_core_runtime`: passed, 59 tests after the conditional-return correction.
- `py -m unittest tests.test_visual_screen_recognizer`: passed, 15 tests after the shortcut correction.
- `py -m unittest discover -s tests`: passed, 1,270 tests with 22 configured/opt-in skips. Final output: `artifacts/replacement_core/kingdom_chat_final_tests.log`.
- `git diff --check`: passed.
- Direct API, shared selector, and typed channel live proofs on `serious_stuff`: passed as recorded above. The two earlier failures were reproducible navigation defects, corrected with offline regressions and live reruns.

## Integrated port validation — September 12

The mail, Kingdom Chat, and open-building ports were combined with `origin/main` at `0542c7b`, preserving the canonical domain models, entrypoint-owned task registry, and modular test layout. Open-building now defaults to the `live_testing` role and uses the same scoped direct-API account reservation as mail and Chat. Root review found no remaining actionable integration issues.

`py tools/run_tests.py full` passed: 1,438 total tests, 1,434 passed and four skipped. Focused application/workflow checks and `git diff --check HEAD` also passed. New port tests live under `tests/contract/entrypoints/` and `tests/integration/workflows/`; deleted monolithic test modules were not restored.

The integrated direct APIs were then exercised sequentially on `serious_stuff` under one continuously held process lease. No castle was selected, no message was sent, and no resource was spent. Each complete sequence confirmed Home before the next sequence began:

| Proof | Observed result | Evidence under `artifacts/replacement_core/` |
| --- | --- | --- |
| Collect-mail, player mailbox, limit one | Player mailbox explicitly unavailable; zero messages processed; Home confirmed. This confirms the unavailable-mailbox path, not a fresh thread-read proof. | `integrated_collect_mail_result.json`; trace `20260912T061614Z_f73f61b9_core_trace.jsonl` |
| Kingdom Chat | Five visible player rows; zero duplicate archive additions; Home confirmed. | `integrated_collect_kingdom_chat_result.json`; trace `20260912T061917Z_e145fa4c_core_trace.jsonl` |
| Open-building, Institute | Exact Institute endpoint confirmed, followed by explicit core recovery to Home while the outer reservation stayed held. | `integrated_open_building_result.json`; workflow trace `20260912T062131Z_c9b89d25_core_trace.jsonl`; recovery trace `20260912T062329Z_a26c4ea6_core_trace.jsonl` |

Traces and screenshots are under `artifacts/2026-09-12/serious_stuff/`. The final handoff image is `20260912T062347Z_core_20260912T062329Z_a26c4ea6_0004_core_1_after_1.png`. The local proof helper is `artifacts/replacement_core/integrated_ports_live.py:run_integrated_port_proof`, invoked once per named workflow inside the retained lease process. The instance was already running and remains open at Home. Coding workers were offline throughout; the lease covered preparation, workflow execution, and dependent recovery.

## Historical issues resolved

Earlier Daily validation recorded a visible cavalry Go control that OCR classified as `unknown_action` and a City HUD sparkle that was mistaken for a popup close control. The canonical parser and popup ownership fixes now have deterministic regressions and final role-selected validation. The original evidence and limits remain in the [replacement-core validation ledger](../reviewed_plans/PNC_CORE_PORTING_VALIDATION.md); those historical observations do not describe the current Daily result.

The replacement runner supports `WorkflowEffect.READ_ONLY` and `WorkflowEffect.NONSPENDING_STATE_CHANGE`. Collect-mail uses the latter because opening unread mail may update read state and archive persistence writes local files, while it spends no in-game resources. Resource-changing work remains behind the existing Daily authorizer, executor, and journal contracts. Adding a boolean acknowledgement, direct executor access, or a second journal would bypass the intended boundary and is not a valid port.

Direct Python entry points for collect-mail and Kingdom Chat route through their dedicated `ApplicationRunner` methods and return typed core results. Their direct API calls use the canonical account reservation scope. Authored mail and Kingdom Chat steps use `CoreScriptDispatcher` and the same canonical workflows. Each binding validates its own typed parameters and archive dependency before connection; mail does not require Chat storage and Chat does not require mail storage. Typed dispatch has no legacy fallback or replay.

## Typed roster refresh and phase cleanup

`RefreshCastleRosterWorkflow` performs a bounded Home-to-Home scan without selecting a castle. It requires two unchanged scroll outcomes at each end, ordered overlap between advancing windows, and exact selected-castle evidence matching preflight. Gaps, duplicates, cycles, exhausted budgets, or changed identities stop before persistence. Scan matching uses the exact kingdom and canonical `normalize_ocr_text` name; it preserves observed names and gives observed levels priority over cached hints.

The canonical `CastleRosterStore.replace_full_scan` owns persistence and preserves other accounts. The September 12 live proof found 12 castles across two distinct scan windows, with two top-seek swipes and three scan swipes. It wrote an artifact roster and confirmed Home without changing the protected castle configuration. Evidence: `artifacts/replacement_core/roster_port_result.json`, trace `artifacts/2026-09-12/serious_stuff/20260912T070027Z_4bf42509_core_trace.jsonl`, and final Home frame `20260912T070534Z_core_20260912T070027Z_4bf42509_0063_core_18_after_1.png` in the same trace directory.

Mail, Chat, open-building, and roster direct entrypoints inherit the outer reservation's `session_cleanup_policy`. They use the canonical `close_preserving_error` boundary to retain both execution and cleanup failures. Authored dispatch borrows the connected graph; only the outer script runner closes it. Use focused tests during development, then the required final full suite on the reviewed integration candidate.

The authored Chat proof used one current-castle YAML step through `ApplicationRunner.run` and returned `CoreStepRunResult` with success and final Home. Its trace is `artifacts/2026-09-12/serious_stuff/20260912T070604Z_fa61a59e_core_trace.jsonl`; final Home is `20260912T071116Z_core_20260912T070604Z_fa61a59e_0046_core_12_after_1.png`. The same exclusive process reservation covered preparation and both completed proofs. No castle selection, message sending, or resource spending occurred. The integrated roster/Chat candidate passed 69 focused tests and the final portable gate: 1,490 total, 1,486 passed, four expected skips. Exact commands and recovery history are in the validation ledger.

## Authored mail proof

One current-castle `collect_mail` YAML step passed on `serious_stuff` with player mailbox, limit one, `archive_mode: both`, and `only_new: false`. It returned `CoreStepRunResult`, success, and final Home. The mailbox was explicitly unavailable, so zero threads were processed or archived. This is an unavailable-mailbox proof, not a fresh thread-read claim. Offline workflow coverage checks empty mailboxes, deduplication, exact active-castle preflight, and persisted text and screenshot bytes.

The helper is `.local-data/artifacts/replacement_core/authored_mail_port_live.py`; its compact result is `authored_mail_port_result.json` beside it. The configured runtime trace is `artifacts/2026-09-12/serious_stuff/20260912T072001Z_4cc53ea0_core_trace.jsonl`, with final Home frame `20260912T072322Z_core_20260912T072001Z_4cc53ea0_0039_core_11_after_1.png`. The existing outer process reservation remained held through preparation, collection, and cleanup. No castle selection, message sending, claim, or resource spending occurred.

## Acceptance checklist

- [ ] Canonical typed parser and existing tests are identified and reused.
- [ ] Every route edge has reviewed current-frame evidence and a measured return destination.
- [ ] `WorkflowSpec` has known entry/exit screens and the correct explicit effect.
- [ ] Workflow code uses only `WorkflowContext`.
- [ ] Factory construction performs no navigation and builds one connected runtime.
- [ ] Active-castle preflight is explicit, exact-evidence, fresh, unblocked, scans only through bounded roster swipes, and never switches castles.
- [ ] Failure tests prove no replay, no action after unknown/popup, and no late success after a time budget.
- [ ] CLI output is structured typed-result JSON with `visible_viewport` coverage where applicable.
- [ ] Bounded proof is non-spending and ends with confirmed Home evidence.
- [ ] Resource-changing ports use the existing exact-budget authorizer, executor, and journal before any implementation is accepted.
