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

1. Inventory the existing workflow’s canonical parser, typed result, screen controls, navigation edges, tests, authorizer, executor, and journal. Record whether every step is read-only, a non-spending state change, or resource-changing. Reuse the existing parser and result model where they exist.

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

`DailyQuestStatusWorkflow` reports one `visible_viewport` from the fresh Daily screen. It does not scroll, claim, acknowledge, select a castle, infer unseen rows, or claim full-screen coverage. It fails when both recognized rows and unknown titles are absent. Known safe popup recovery belongs to the connected runtime and shared observed-action executor; the workflow has no generic popup dismissal policy. Navigation does not retry a tap, replay a failed workflow, or use the legacy observer as a fallback. A task-owned dialog or popup without an explicit safe selector still stops the route.

Active-castle preflight recognizes the selected row through exact Manage Characters evidence. It searches a long roster with bounded swipes in both directions and stops on repeated viewport signatures without tapping a castle row.

## Typed Kingdom Chat port

`CollectKingdomChatWorkflow` is the typed direct Python port for one Kingdom Chat heartbeat. Its `WorkflowSpec` uses `PNC_HOME_CITY` for both entry and exit and `WorkflowEffect.NONSPENDING_STATE_CHANGE`: opening the chat may update in-game read state, while the canonical `ChatArchiveStore` writes the local archive. The workflow enters Chat through the reviewed Home shortcut, captures content with the Chat transcript observation scope, and leaves final Home confirmation to `CoreWorkflowRunner`.

`WorkflowContext.select_chat_channel(ChatChannel.WORLD)` validates the enum and delegates to `NavigationCore`. The core reacquires a fresh unblocked Chat frame, skips the tap when Kingdom is already active, or requires the current-frame template-backed Kingdom tab, taps once, and accepts completion only after bounded fresh Chat frames confirm the requested active channel. The workflow uses the canonical `visible_player_chat_entries` and `visible_unsupported_chat_entries` projections before persisting through `ChatArchiveStore`; unsupported transcript shapes fail closed before archive writes.

`ApplicationRunner.run_collect_kingdom_chat` performs archive availability and exact active-castle preflight before constructing the workflow, then closes its one connected runtime on every outcome. The direct `AutomationApi.collect_kingdom_chat` and module helper hold or reuse the canonical scoped account reservation for the complete call and return the typed core result. Authored `TaskId.COLLECT_KINGDOM_CHAT` YAML steps remain on the legacy `ScriptRunner` dispatch boundary until typed script dispatch is implemented; no adapter routes those steps through `CoreWorkflowRunner`.

## Historical issues resolved

Earlier Daily validation recorded a visible cavalry Go control that OCR classified as `unknown_action` and a City HUD sparkle that was mistaken for a popup close control. The canonical parser and popup ownership fixes now have deterministic regressions and final role-selected validation. The original evidence and limits remain in the [replacement-core validation ledger](../reviewed_plans/PNC_CORE_PORTING_VALIDATION.md); those historical observations do not describe the current Daily result. The new Kingdom Chat port still requires its own bounded live proof.

The replacement runner supports `WorkflowEffect.READ_ONLY` and `WorkflowEffect.NONSPENDING_STATE_CHANGE`. Collect-mail uses the latter because opening unread mail may update read state and archive persistence writes local files, while it spends no in-game resources. Resource-changing work remains behind the existing Daily authorizer, executor, and journal contracts. Adding a boolean acknowledgement, direct executor access, or a second journal would bypass the intended boundary and is not a valid port.

Direct Python entry points for collect-mail and Kingdom Chat route through their dedicated `ApplicationRunner` methods and return typed core results. Their direct API calls use the canonical account reservation scope. Authored `TaskId.COLLECT_MAIL` and `TaskId.COLLECT_KINGDOM_CHAT` script steps remain on the legacy `ScriptRunner` dispatch path until typed script dispatch is implemented; do not add adapters that route those steps through `CoreWorkflowRunner`.

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
