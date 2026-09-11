# Porting a workflow to the replacement core

This guide describes the bounded path for moving one workflow onto the reviewed navigation core. It applies to the shared runtime in `pnc_automation/app/automation/engine/`, the typed PNC observations, and the application and CLI entrypoints. The current implementation is a read-only boundary. A workflow that can change resources is rejected before it observes the device.

## Canonical owners

| Responsibility | Owner | Contract |
| --- | --- | --- |
| Screenshot capture and independent typed perception | `pnc_automation/app/automation/engine/core_runtime.py:CoreRuntime.observe` and `pnc_automation/app/pnc/vision/navigation_perception.py:NavigationPerception` | One fresh persisted screenshot is parsed. Content is optional and cannot create or replace screen controls. Capture metadata is recorded before parsing so a parser failure keeps its artifact evidence. |
| Connected runtime composition | `build_core_runtime` | Builds exactly one `ConnectedAccountRuntime`, uses its existing screenshot service and observed action executor, and does not navigate while constructing the graph. |
| Reviewed routing and completion | `pnc_automation/app/automation/engine/navigation_core.py:NavigationCore` and `reviewed_navigation_edges` | Current-frame visual evidence authorizes a single action. Completion requires fresh observed destination frames. Unknown screens, unresolved popups, stale frames, and unexpected destinations stop the route. The connected `ObservedActionExecutor` may clear each newly observed safe popup through its explicit selector before routing continues. |
| Known popup recovery | `CoreRuntime.observe` and `ObservedActionExecutor.recover_interruption_if_required` | Core observations pass through the canonical bounded recovery path. OCR-owned reconnect and Valiant Conquest modals, VIP reset, and generic X popups with an explicit safe selector may be dismissed once per visual fingerprint. Task-owned dialogs, unknown screens, missing selectors, and repeated fingerprints remain fail-closed; Android Back is never inferred. |
| Workflow effect and lifecycle | `pnc_automation/app/automation/engine/core_workflow.py` | `WorkflowSpec` validates known entry/exit screens and a `WorkflowEffect`. `CoreWorkflowRunner` allows `READ_ONLY`, owns entry, execution, and exit, and reports success only after exit is confirmed. |
| Workflow access | `WorkflowContext` | Exposes only reviewed `navigate` and fresh expected-screen `observe_content`. It has no raw executor, claim, swipe, selector-tap, or transition API. |
| Typed Daily Quest conversion | `pnc_automation/app/automation/daily_maintenance/coordinator.py:daily_viewport_from_observation` | Converts the canonical typed observation. Do not reimplement row parsing or claim semantics in a replacement workflow. |
| Application and CLI wiring | `ApplicationRunner.run_daily_quest_status` and `pnc_automation.app.entrypoints.cli` | The application performs explicit active-castle identity preflight before constructing workflow execution. The `daily-quest-status` command emits the typed result as structured JSON. |
| Mutation authorization | `daily_maintenance/authorization.py:DailyMutationAuthorizer`, `daily_maintenance/coordinator.py:ForbiddenDailyMutationExecutor`, `pnc_automation/app/pnc/persistence/daily_run_journal_store.py:DailyRunJournalStore` | These are the existing approval, executor, and journal owners for future resource-changing work. Do not add a second approval flag or a parallel journal. |

## Porting sequence

1. Inventory the existing workflow’s canonical parser, typed result, screen controls, navigation edges, tests, authorizer, executor, and journal. Record whether every step is read-only or resource-changing. Reuse the existing parser and result model where they exist.

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

   A resource-changing spec is intentionally rejected by `CoreWorkflowRunner` before navigation or capture. A future mutation port must first define how the existing exact-budget authorizer, mutation executor, and journal are bridged into the constrained lifecycle.

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

5. Integrate through `build_core_runtime` and the application runner. Factory construction connects the configured emulator and creates the artifact directory, but must not navigate or run a workflow. `CoreRuntime.preflight_active_castle_identity` explicitly foregrounds the configured app, passively settles loading within `NavigationPolicy`, navigates to Manage Characters, and requires fresh, unblocked content with exact `current_castle_evidence`. It never selects a castle. The current parser can verify only a visibly selected row in the captured viewport. If that row is outside the initial viewport, a separate bounded read-only roster setup may be needed before the status workflow; there is no automated roster search in this port. Return Home before running the workflow. Identity details are not written to the sanitized JSONL trace.

6. Add deterministic offline tests before a device run. Cover factory composition, typed content preservation, loading settle, unknown and popup stop, stale and late captures, parser failure artifact retention, mutation rejection before capture, workflow success and empty/unknown content, exit failure without replay, explicit recovery, CLI JSON, and application preflight ordering. Use typed observations and fake clocks; do not use BlueStacks, ADB, credentials, or private configuration in ordinary tests.

7. Reserve exclusive use of the configured BlueStacks instance for the bounded proof, including other agents and tasks. Keep its currently active castle. If preflight cannot see the selected row, perform the bounded read-only roster setup through existing observed controls when needed; this is ordinary in-scope read-only setup and does not require duplicate permission. Leave the status workflow itself free of roster scrolling. Use the exact non-spending command with configured arguments:

   ```powershell
   py -m pnc_automation.app.entrypoints.cli daily-quest-status --config <config-path> --account <account-id>
   ```

   The proof may foreground the configured app and navigate through reviewed controls. The status workflow must not scroll, claim, switch castles, or spend resources. A route that sees an unknown screen, unresolved popup, stale capture, or competing source frame must stop and preserve its evidence.

8. Require final Home evidence. A successful result is emitted only after the runner confirms the declared exit screen. A failure at exit propagates without an automatic retry or `finally` navigation. Recovery is a separate explicit call to `CoreWorkflowRunner.recover_to_home`; it uses the reviewed graph, allows the connected safe-popup recovery boundary to clear known interruptions, and stops on unknown or unresolved popup states.

9. Migrate production callers only after offline parity and the bounded proof are complete. Then remove the obsolete duplicate capture/perception/construction path for that caller. Keep unrelated legacy daily maintenance unchanged until each workflow has its own reviewed port and evidence.

## Current boundary

The direct `open-building` CLI and Python entry points use the replacement core. Authored scripts with `TaskId.OPEN_BUILDING` remain a legacy compatibility boundary until core script dispatch is available.

`DailyQuestStatusWorkflow` reports one `visible_viewport` from the fresh Daily screen. It does not scroll, claim, acknowledge, select a castle, infer unseen rows, or claim full-screen coverage. It fails when both recognized rows and unknown titles are absent. Known safe popup recovery belongs to the connected runtime and shared observed-action executor; the workflow has no generic popup dismissal policy. Navigation does not retry a tap, replay a failed workflow, or use the legacy observer as a fallback. A task-owned dialog or popup without an explicit safe selector still stops the route.

Active-castle preflight currently sees only the selected row that is visible in the Manage Characters viewport. A separate read-only roster setup may prepare that viewport, but the replacement workflow does not automate roster search or scrolling yet.

## Two remaining issues

### 1. One Daily Quest action was not classified

The `serious_stuff` proof found five visible quest rows. Four were classified as `go`. The fifth row, `Train Cavalry x250`, showed a Go button on screen but was returned as `unknown_action` because OCR did not resolve the button text.

This does not make the read-only status result unsafe: the workflow preserves the uncertainty and never clicks a quest-row action. It does mean consumers cannot yet assume that every visible row has a known action state.

Fix this in the canonical Daily Quest parser or its visual evidence. Do not add a special case to `DailyQuestStatusWorkflow`. The fix is complete when a deterministic screenshot test classifies this row as `go`, the live status command reports all five observed states correctly, and the workflow still treats genuinely unclear buttons as `unknown_action`.

### 2. A City HUD sparkle was mistaken for a popup Close button

After the selector check left the game on Daily Quest, a separate `recover_to_home` proof reached City. Its next confirmation frame contained a sparkle on a right-side HUD icon. The generic upper-right Close-X detector classified that sparkle as `PNC_POPUP`, so navigation stopped before confirming recovery.

The stop was safe: no second tap was sent, and the game remained in City. The false positive still makes recovery unreliable because a normal City animation can look like a blocking popup.

Fix this in the canonical popup detector by requiring stronger popup ownership than an isolated X-shaped patch. Do not weaken `NavigationCore` so it ignores reported interruptions. The fix is complete when the saved City frame is classified as `PNC_HOME_CITY` without a blocking popup, real popup fixtures still block navigation, and a live `recover_to_home` run confirms two fresh City frames.

Until both issues are fixed, report the Daily result with its `unknown_action` value and do not describe the replacement boundary as merge-ready.

The replacement runner currently supports only `WorkflowEffect.READ_ONLY`. Resource-changing work remains behind the existing Daily authorizer, executor, and journal contracts. Adding a boolean acknowledgement, direct executor access, or a second journal would bypass the intended boundary and is not a valid port.

## Acceptance checklist

- [ ] Canonical typed parser and existing tests are identified and reused.
- [ ] Every route edge has reviewed current-frame evidence and a measured return destination.
- [ ] `WorkflowSpec` has known entry/exit screens and the correct explicit effect.
- [ ] Workflow code uses only `WorkflowContext`.
- [ ] Factory construction performs no navigation and builds one connected runtime.
- [ ] Active-castle preflight is explicit, exact-evidence, fresh, unblocked, and never switches castles; selected-row visibility limitations and any separate read-only setup are recorded.
- [ ] Failure tests prove no replay, no action after unknown/popup, and no late success after a time budget.
- [ ] CLI output is structured typed-result JSON with `visible_viewport` coverage where applicable.
- [ ] Bounded proof is non-spending and ends with confirmed Home evidence.
- [ ] Resource-changing ports use the existing exact-budget authorizer, executor, and journal before any implementation is accepted.
