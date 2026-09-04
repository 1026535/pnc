# PNC Daily Castle Maintenance Automation — Implementation and Live-Promotion Plan

## Context

PNC needs a low-touch daily-maintenance runner that executes at 02:00 America/Toronto across selected castles. One BlueStacks instance maps to one account, one account may contain several castles, instances may run in parallel, and castles within an instance run sequentially. The first production scope is deliberately limited to two targets:

| Account | Castle | Role |
|---|---|---|
| `mega_old_acc` | `[NGF] NPC 2` | higher-level canary and broad feature coverage |
| `serious_stuff` | `[NAX] free cookies` | serious target and lower-progression applicability coverage |

The working tree was clean at the 2026-09-02 review. The committed building-upgrade-only routine, one-feature live-smoke harness, and scheduler wrapper remain migration inputs, not behavior to preserve. Building upgrades are explicitly excluded from daily maintenance, and the current wrapper still targets stale castles.

This plan is based on repository evidence and bounded live evidence gathered through 2026-09-01. It does not authorize new game mutations. Every mutating smoke requires an acknowledgement bound to the exact account, castle, capability, local date, maximum action count, and premium-currency budget.

The rollout follows small-change/canary principles: deterministic tests first, one narrow live behavior at a time, and one successful live canary per distinct behavior variant. Repeating the same live behavior on every castle is not a promotion requirement. Target-specific policies that execute different code paths, such as the two Campaign modes or distinct Trial Shop policies, remain separate variants and each receives one live canary. This follows [Google SRE canary guidance](https://sre.google/workbook/canarying-releases/). ADB target verification and screenshot capture follow the [Android ADB documentation](https://developer.android.com/tools/adb). Windows schedule semantics follow Microsoft's documentation for [logon types](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype), [task settings](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings), and [multiple-instance policy](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-multipleinstances).

## Reviewed Decisions — 2026-09-02

- Diamonds are allowed only where the capability-specific policy below explicitly permits them. The governing invariant is no unbudgeted premium spend, not a blanket no-premium rule.
- Efficiency takes priority over repeated verification. Use one fresh pre-action observation and one post-action observation for normal mutations; use two stable frames only for dynamic click geometry or after a scroll.
- Unknown screens and OCR failures use a short, non-cyclic recovery ladder. They do not immediately fail the whole castle, but they also never cause blind mutation replay.
- One live canary is sufficient for each distinct behavior variant. Convert its evidence into deterministic offline coverage and run the focused tests after adding the regression.
- Exact castle identity is resolved once per castle-selection/session boundary and cached. Capabilities do not reopen Lord Info or Manage Char merely to re-prove the same identity.
- Scheduled full-roster discovery is a separate follow-up plan because it has its own cadence, process-lock, cache-freshness, config-write, and failure semantics. Daily maintenance consumes that canonical cache.

### Review resolution matrix

| Review ID | Resolution applied to this plan | Remaining interview point |
|---|---|---|
| `JOURNAL-01` | Per-operation prepared/dispatched/reconciled/committed intents; one reconciliation; no cyclic recovery | Exact ambiguity report/operator workflow |
| `PREMIUM-01` | Corrected blanket no-premium wording; diamonds follow capability caps | Mutation-acknowledgement representation |
| `GEOM-01` | Vision materializes normalized geometry once; executor receives final ADB pixels unchanged | None |
| `POPUP-01` | Migrate existing runner/popup APIs; remove generic task-time recovery and Android-Back fallback | None |
| `TRACE-01` | Downgraded static screenshots, added exact paths, required fixture manifest and same-trace evidence | Exact local fixtures selected in Phase 0 |
| `SKIP-01` | Closed runtime skip reasons; `unittest.skip*` is not live evidence; one canary per behavior variant | None |
| `EXEC-01` | Extract from `AutomationRunner`, not `ScriptRunner`; coordinator is not recursively executed as a task | Whether routine YAML remains a manifest |
| `IDENTITY-01` | Roster freshness plus one identity resolution per castle-selection/session boundary | Refresh cadence/cache age in separate plan |
| `VALIDATOR-01` | Removed live selector validation from offline commands; added explicit account/selector example | None |
| `SCHED-01` | Added Windows timezone validation, offset-free boundary, DST expectations, and shared run-date/reset ID | Exact PNC daily-reset boundary |

## Goals

- Run only the selected castles every day at 02:00 local Toronto time, including daylight-saving transitions.
- Use normalized screen geometry for all clicks. OCR may classify text and validate meaning but must never provide click coordinates.
- Discover and process Daily Quest rows despite scrolling, row reordering, completed rows moving to the bottom, and `Go` changing to `Claim` or disappearing after claim.
- Close startup interruptions through a freshly detected visual X when available, then require a typed Home screen.
- Execute all enabled daily capabilities with strict premium-budget and no-adjacent-action policies.
- Continue other instances when one fails; checkpoint and recover an interrupted castle without repeating completed mutating work.
- Apply the short reread/safe-root recovery ladder before interrupting an interactive run or skipping one unattended capability; preserve clarification evidence without entering a restart loop or failing unrelated work.
- Develop and live-test incrementally. Every distinct runtime behavior variant receives one positive live canary; target-specific applicability and configuration remain explicit without duplicating an identical live mutation on every castle.

## Non-Goals

- No building upgrade, research/technology upgrade, troop training, Hell Fortress, stamina consumption, pack purchase, Hero Curio crafting, or Alliance Help execution.
- No Daily reward-chest claims.
- No automation for any castle other than NPC 2 and free cookies until explicitly added.
- No OCR-derived tap points and no broad removal of OCR from semantic classification.
- No generic X dismissal inside a task workflow. Generic visual-X recovery exists only during bootstrap.
- No scheduler enablement as part of implementation. Registration is disabled; enabling is a separate promotion decision after all gates pass.
- No catch-up run if the computer was asleep or off at 02:00.
- No work on the black-capture `157_farm` instance.

## Locked Runtime Policies

### Geometry, classification, and navigation

- ADB `screencap` pixels and `adb input tap` use the same device coordinate space in the current runtime. Authored selector geometry remains normalized, then the observation/vision layer materializes it exactly once against the current ADB screenshot dimensions. `ActionExecutor` receives final device pixels and must not rescale them again.
- Dynamic visual geometry is detected in screenshot pixels and passed through unchanged. Every tappable element records coordinate provenance (`normalized_selector`, `visual_geometry`, or another explicit non-OCR source) so tests can reject a second conversion.
- OCR supplies task titles, amounts, button semantics, and screen evidence only. It never supplies the coordinate clicked and never causes a geometry conversion.
- Before clicking a dynamic row or popup X, re-observe the current frame, re-resolve its visual fingerprint, and click that fresh geometry. Never reuse a coordinate from an earlier screenshot. This prevents the observed Farm-to-Talent and Talent-to-Chat stale-coordinate failures.
- Daily row taps require two consecutive observations with equivalent row geometry after every scroll.
- Enter Quest and explicitly select the Daily Quest tab every time. Main Quest and Daily Quest remain separate typed screens.
- Exit Daily Quest with the in-game gold back control, never Android Back.
- A Daily `Go` action may route directly, return Home and pan/highlight a building, or land on an intermediate screen. Every handler validates its typed destination rather than assuming `Go` succeeded.

### Bootstrap interruptions

- Bootstrap recognizes publisher splash, black winged-sword loading, Hero Showdown white loading, Android Home, the BlueStacks Store/My Games surface, typed promotional popups, and Home.
- On an interrupting startup popup, search the current screenshot for an X candidate in the allowed popup regions, re-observe the same fingerprint immediately before tapping it, tap once, and require typed Home or another typed bootstrap state afterward.
- Savannah Sale and Valiant Conquest are known distinct visual-X examples. VIP Login/Daily Reset remains an optional variant to sample when it appears. If a popup has no confident X, or post-dismissal state is not typed, stop; do not guess.
- The BlueStacks Store is recovered by foregrounding the configured PNC package, then requiring a typed game destination.
- No generic-X routine runs after a task workflow begins. Expected dialogs define their own typed close/back selector.

### Unknown states and checkpointing

- `UNKNOWN` or an OCR-only miss first gets one immediate broad re-observation. OCR semantic failure gets one stable reread. These are rereads, not task retries, and share one fixed recovery budget.
- If the state is still unknown before any mutation, attempt the canonical safe-root path once. When Home is recovered, record a typed `runtime_unknown_skip` for that capability and continue the castle instead of restarting the instance or failing the entire run.
- Restart only that BlueStacks instance at most once per castle run when safe-root recovery is unavailable or the app is unhealthy. A `(castle, capability, recovery_stage)` key may be consumed once; the coordinator rejects repeated or cyclic recovery transitions.
- Interactive smoke tests use the same short recovery ladder before asking for classification. They do not pause on the first noisy OCR frame.
- Every individual mutating action persists a prepared intent before dispatch. After the action, one fresh observation reconciles the expected postcondition and commits the receipt. On restart, a prepared or dispatched intent is reconciled once: commit it if the postcondition is visible, retry it only when the original precondition is still positively proven, and otherwise mark only that capability `pending_clarification` without replay.
- Multi-action capabilities journal each sub-operation separately, including each Hero Hall single, Arena attempt, gift open, donation, enhancement, purchase, wish, claim, and march.
- A pending-clarification capability does not block unrelated capabilities when the runtime is back at typed Home. If safe Home cannot be recovered, stop that castle and continue the other instance.
- Expected workflow screens must be typed by promotion. A genuinely novel state may follow the unknown policy; a known screen returning `UNKNOWN` is a defect and blocks that slice.

## Daily Quest Catalog and Policy

The runtime catalog is semantic and data-driven: normalized title aliases map to one `DailyQuestId`. A row absent because it is already completed/claimed is not an error. An unrecognized title is skipped, reported, and preserved as evidence; OCR semantic failure gets one stable reread, then the same skip/report outcome.

### Enabled

| Daily capability | Locked behavior |
|---|---|
| Claim completed rows | Claim every completed-unclaimed Daily row, including rows whose underlying task is excluded. Never claim Daily chests. Claimed rows have no `Go`. |
| Hero Arena 3x | Run up to three free Hero Showdown attempts; no refresh or purchases. Select the weakest foreign-kingdom candidate. |
| Use resource item | In Bag/Resource choose globally smallest owned numeric amount; ties Food, Wood, Iron, Gold. Tap blue `Use` once, never orange bulk-use. Resource Shop is back-only. |
| Hero Hall 5x | Perform five single free recruitments as cooldowns allow. Campaign may run while waiting. Never use 10x or paid actions. |
| Upgrade Hero 3x | Use the first fully visible level-70 hero, only if free reset is available; perform three upgrades and restore exactly level 70. |
| Campaign natural AP | Per-castle `fixed_stage` or `progress_then_farm`; preserve saved lineup, Challenge once, Auto battle, never Blitz, and verify result. |
| Gather Food/Wood/Iron/Gold | Search highest available full unoccupied node with enough resources. Use cavalry only, T1 first then higher available tiers ascending until the smallest sufficient capacity; no heroes and no Quick Select. |
| Gather alliance mine | Same cavalry-only formation policy where the Daily row and mine are eligible. |
| Resource-building output boost | Use an owned boost item first; diamond fallback is allowed only up to 200. Farm selector must be repaired and boost UI typed before promotion. |
| Trial Shop | Apply the configured per-castle policy: main-policy castle buys up to 99 maximum affordable 60-minute speedups; farm-policy castle buys one 1-star Gem Essence. No refresh. The canonical name is Trial Shop; remove Tower Shop naming without an alias. |
| Rare Earth Shop | Buy exactly one 1-star Saurgem Essence before Saurgem enhancement. |
| Alliance Shop | Buy exactly one 1-minute speedup if present; otherwise one 1-star gear item from Treasure; otherwise skip. No refresh, gems, or speedups of five minutes or more. |
| Praise | Open typed Might Rank and tap the top-rank thumbs-up once. |
| Summon Saurgil | Use free `Summon 1x` only; never paid 10x. |
| Enhance Gem | Select a suitable lowest-star equipped item and one lowest-star material; no Auto Select; confirm once. |
| Enhance Saurgem | Complete the Rare Earth purchase first, then use one lowest-star material; no Auto Select; confirm once. |
| Enhance Gear | Use the first fully visible lowest `+` item and one lowest-star material; no Auto Select; confirm once. |
| Wishes | Exhaust free resource wishes. Diamonds may be used only for the missing wishes needed to reach 50 total, according to the per-castle policy. |
| Land of Trial | Select first unlocked row with an explicit Trial button, Attack once; win or loss counts. |
| Lost Land | Open current stage, trust exactly five game-preselected strongest heroes and save only if required, Challenge once. Daily-row progress is authoritative. |
| Alliance donations | Prefer non-max HOT technology in Economy, then Military, then Alliance Skill; resource-only, never diamonds. |
| Alliance Gift | Open all eligible gifts across the full list, claim the grand pack only when explicitly available, then `Remove All` claimed entries and verify no `Open` remains. |

### Excluded or deferred

| Daily row | Disposition |
|---|---|
| Upgrade building | Excluded; claim if already completed by the user. |
| Upgrade tech/research | Excluded; claim if already completed. |
| Train Infantry/Cavalry/Ranged/Siege | Excluded; claim if already completed. |
| Defeat Hell Fortress | Excluded. |
| Consume 20/80 Stamina | Excluded. |
| Buy any pack | Excluded. |
| Craft Hero Curio | Excluded as progression/manual work. |
| Help allies / Alliance Help | Deferred until explicitly designed and live-validated. |
| Unknown future Daily row | Stable reread once, then skip/report; never infer a handler from similar text. |

## Current State

- `scripts/routines/daily_castle_maintenance.yaml` currently performs only `building_upgrade`, directly contradicting the locked exclusions.
- `tools/run_daily_maintenance.ps1` currently invokes `testing` castles and a generic serious `main` alias, not NPC 2 and free cookies.
- `tests/test_live_daily_task_smoke.py` correctly limits a smoke to one feature but defaults to the excluded building-upgrade smoke and only one account.
- `TaskId` exposes only building, research, gathering, and campaign among the relevant capabilities.
- `GatheringTask` selects visible world-map nodes and dispatches the default formation; it has no resource search, full/unoccupied checks, capacity calculation, or cavalry-only tier selection.
- `CampaignTask` stops at battle preparation and has no per-castle progression/farm model, natural-AP guard, battle/result handling, or safe return to Daily Quest.
- `GatheringPolicy` and `CampaignPolicy` are too small for the locked behavior.
- `ScreenType.PNC_QUEST_DAILY` exists, but live Daily screenshots have classified as `UNKNOWN` because observation requests/enrichment/selectors do not consistently supply its evidence.
- Many destination screens observed during planning are not yet represented end to end through `ScreenType`, `UiElementId`, observation enrichment, selector registry, and navigation contracts.
- `config/castle_targets.yaml` is stale relative to the two live identities. Exact kingdom/name/alias data must be refreshed and reviewed before a scheduled run.
- No PNC Windows scheduled task is currently registered.

## Live-Evidence Disposition

Current artifacts establish useful static layouts, but a screenshot is not a transition trace and Lord Info name/alliance text is not an exact kingdom/name identity. The rows below distinguish static evidence from remaining implementation or promotion proof.

| Question | Disposition | Evidence or gate |
|---|---|---|
| Verify free cookies visible name/alliance | `artifact_answered` | `artifacts/2026-08-30/serious_stuff/20260830T205813Z_daily_plan_serious_identity_confirm.png`; exact kingdom/name identity remains a roster-refresh gate. |
| Verify NPC 2 exact identity | `artifact_answered` | `artifacts/2026-09-01/mega_old_acc/20260901T133805Z_arena_audit_20260901_baseline.png` shows `K157 / NPC 2 / level 22`; the older Lord Info artifact proves only the visible name/alliance. |
| Arena `Go` Home highlight and formation layouts | `artifact_answered` | `artifacts/2026-08-31/serious_stuff/20260831T164834Z_daily_plan_serious_arena_go_normalized_post_action_1.png`; `artifacts/2026-08-31/serious_stuff/20260831T165233Z_daily_plan_serious_after_elemental_intro_day2_post_action_1.png`. Preserve the same-trace September 1 audit summary for the typed Intro/Formation/back transition. |
| Campaign stage-detail layout | `artifact_answered` | `artifacts/2026-08-31/serious_stuff/20260831T153132Z_daily_plan_serious_ch10_node3_guarded_post_action_1.png` currently classifies as generic `PNC_POPUP`; it does not prove battle/result handling. |
| Gathering formation and troop-list layouts | `artifact_answered` | `artifacts/2026-08-31/serious_stuff/20260831T171853Z_daily_plan_serious_food_gather_formation_post_action_1.png`; `artifacts/2026-08-31/serious_stuff/20260831T175928Z_daily_plan_serious_gather_troop_list_scan2_post_action_1.png`; dispatch remains a mutation boundary. |
| Startup promotional X layouts | `artifact_answered` | Savannah baseline and Home result: `artifacts/2026-08-31/serious_stuff/20260831T121544Z_daily_plan_serious_after_publisher_splash.png`, `artifacts/2026-08-31/serious_stuff/20260831T121656Z_daily_plan_serious_after_savannah_popup_recovery.png`; Valiant baseline: `artifacts/2026-08-28/testing/20260828T173500Z_ensure_game_running_post_action_1.png`. Valiant still needs a deterministic fixture rather than a claimed transition. |
| Lost Land static route screens | `artifact_answered` | `artifacts/2026-08-29/mega_old_acc/20260829T011446Z_daily_plan_npc2_lost_land_open_post_action_1.png`; `artifacts/2026-08-29/mega_old_acc/20260829T011658Z_daily_plan_npc2_lost_land_visual_back_post_action_1.png`; mutation/result remains unproven. |
| Alliance Gift layout | `artifact_answered` | `artifacts/2026-08-31/mega_old_acc/20260831T224908Z_daily_plan_npc2_home_before_lostland_quest.png` currently classifies `UNKNOWN`; use it as the classifier fixture. |
| Praise, Saurgil, enhancements, wishes, trials, and shop layouts | `artifact_answered` | Phase 0 must create a checked-in or local-fixture manifest with exact 2026-08-29/30 NPC 2 screenshot and OCR-sidecar paths. No external session record is accepted as evidence. |
| Farm output-boost UI | `live_blocked` | The atlas false-positive opened Talent (`artifacts/2026-08-30/mega_old_acc/20260830T152907Z_open_building_post_action_1.png`). Repair Farm selection and observe the actual boost UI before implementing its mutating step. |
| VIP Login popup behavior | `mutation_boundary` | Sample opportunistically when it naturally appears. Runtime uses X; if Confirm appears, verify once that it reaches the same typed postcondition. Repeated nightly sampling is not required. |
| NPC 2 Arena variability | `artifact_answered`, not a promotion gate | The 2026-09-01 guarded entry typed Intro and Formation and returned without Save/Challenge/attempt. The optional seven-entry audit may continue for operational knowledge, but the user-approved promotion rule is one positive live canary per distinct Arena behavior variant. See `reviewed_plans/PNC_HERO_ARENA_SEVEN_ENTRY_AUDIT.md`. |

## Target Design

### Canonical ownership

1. `DailyMaintenanceCoordinator` owns one castle's Daily Quest lifecycle: enter Daily, scan rows, claim completed rows, select enabled work, call the canonical capability executor, reopen Daily, checkpoint, and finish.
2. `DailyQuestCatalog` owns exact title aliases and maps them to `DailyQuestId`, policy category, and capability `TaskId`. It is the only semantic parser for Daily rows.
3. `TaskExecutor` is extracted from `AutomationRunner._execute_step_loop`, which currently owns the canonical plan-act-observe-verify loop. `ScriptRunner` remains runtime wiring only. The coordinator and authored scripts call the same session-scoped executor; there is no second action loop and no task recursively invoking another runner.
4. Each capability has one canonical task implementation. Extend and reuse `CampaignTask` and `GatheringTask`; do not add daily-specific copies. New capabilities use focused task classes registered once.
5. `DailyRunJournalStore` owns durable per-reset, per-account, per-castle checkpoints, prepared mutation intents, reconciliation outcomes, and committed receipts. The coordinator never infers completion from in-memory state after restart.
6. The existing `PopupRecoveryTask`, `AutomationRunner._ensure_no_blocking_popup`, and `ScreenFlowPlanner.close_blocking_popup` are migrated rather than bypassed. Generic visual-X discovery is owned only by bootstrap/`ensure_game_running`; the unconditional runner-level popup hook and generic Android-Back fallback are removed. Known cross-workflow blockers use typed selectors, while task dialogs remain task-owned.
7. `DailyMaintenanceConfigLoader` owns the one typed schema for per-castle policy and validates references against accounts, castles, and castle targets.

### Typed interfaces and configuration

Add these canonical models; exact module placement follows existing domain/config ownership rather than creating a new parallel package:

- `DailyQuestId`: all enabled, excluded, deferred, and known claim-only row identities.
- `DailyQuestDisposition`: `enabled`, `excluded_claim_only`, `deferred_claim_only`.
- `DailyQuestRowState`: `go`, `claim`, `completed`, `requirement`, `unknown_action`.
- `DailyQuestRow`: ID, normalized title, progress, action state, stable normalized row geometry, and observation fingerprint.
- `DailyCapabilityPolicy`: enabled flag and task-specific typed policy.
- `CampaignExecutionMode`: `fixed_stage` or `progress_then_farm`.
- `CampaignTarget`: chapter and node; required and prevalidated for `fixed_stage`, configured fallback for `progress_then_farm`.
- `CavalryGatheringPolicy`: resource kind, highest search level, full-resource requirement, unoccupied requirement, required amount, no-hero invariant, and tier order fixed to T1 through highest available.
- Typed shop, wishes, boost, Arena, enhancement, donation, and gift policies with explicit premium caps/prohibitions.
- `MutationIntentState`: `prepared`, `dispatched`, `reconciled`, or `committed`, keyed per individual mutating sub-operation.
- `DailyTaskCheckpoint`: Toronto maintenance date, game-reset identifier, target, current task, per-task progress, completed task IDs, mutation intents/receipts, consumed recovery stages, and last typed screen.
- `DailyApplicabilitySkipReason`: a closed enum for genuine feature, inventory, currency, progression, march-slot, and policy inapplicability. OCR failure and an untested path are not applicability skips.
- `DailyTargetOutcome`: success, typed applicability skip, runtime-unknown skip, failed, pending clarification, and artifact references.
- `CastleRosterFreshness`: scan timestamp, account, ordering proof, roster fingerprint, and source artifact summary. It is written by the canonical roster-refresh workflow and consumed without reopening Manage Char for every capability.

Create `config/daily_maintenance.example.yaml` and local `config/daily_maintenance.yaml`. The local file is keyed by account ID and castle alias and contains only the two selected targets. It configures campaign mode/target, Trial Shop policy, wish policy, boost cap, and feature enablement. It does not duplicate account, instance, kingdom, or castle identity fields. Those remain referenced from canonical account/castle-target config. Live identity is resolved once when the session selects a castle, cached for all capabilities on that castle, and invalidated only by a castle switch, app/account reset, roster-fingerprint change, or contradictory observation.

Fail loading before launching BlueStacks when:

- an account or castle alias is missing or ambiguous;
- a fixed campaign target is incomplete;
- an excluded capability is enabled;
- a premium cap is negative or exceeds the locked maximum;
- a shop policy names a forbidden item;
- the same physical castle is selected twice; or
- an unattended target is absent from the latest accepted full-scan roster, the roster fingerprint conflicts with `castle_targets.yaml`, or the configured freshness limit has expired. Expiry blocks a castle switch but does not force each capability to repeat live identity navigation.

### Quest scanning and execution

The coordinator uses a bounded top-to-bottom sweep:

1. reach typed Home;
2. open Quest, explicitly select Daily Quest, and require `PNC_QUEST_DAILY`;
3. observe twice and compare row geometry;
4. process all visible Claim rows first, journaling each claim;
5. classify visible Go/Requirement/completed rows;
6. execute one enabled actionable row, then return to typed Home and reopen Daily;
7. scroll by normalized geometry, require two stable observations, and continue until a bottom marker or a confirmed bottom bounce proves exhaustion. An unchanged viewport on the first swipe is classified as `scroll_not_applied`, gets one adjusted retry, and never proves bottom by itself;
8. rescan once for claims created by completed work; and
9. exit with gold back and require Home.

Completed rows moving to the bottom is expected. Row ordering is never a task identity. Each click reselects by task ID plus fresh current-frame geometry.

### Runtime concurrency and recovery

- The top-level runner groups targets by BlueStacks instance.
- Instance workers run concurrently with isolated sessions, journals, logs, and artifact namespaces.
- Castle targets inside one instance run in configured order and never overlap.
- An instance worker failure cannot cancel the other worker.
- A process-level lock prevents two nightly wrappers from overlapping.
- The journal uses atomic replace. It writes a prepared intent before each individual mutation and a committed receipt after one postcondition reconciliation.
- Restart recovery validates account and castle identity before resuming.
- Identity validation happens once per connected castle-selection boundary, then the exact identity is held in session state. Tasks reuse it without reopening Lord Info or Manage Char.

### Scheduling

Use Windows Task Scheduler as the external trigger. Register one task disabled with:

- registration-time and run-time validation that Windows reports `Eastern Standard Time`, the Windows timezone corresponding to America/Toronto on this machine;
- an offset-free local `StartBoundary` at 02:00 so Windows applies the machine's DST rules; an explicit numeric UTC offset is rejected;
- an explicit spring-forward acceptance rule: if 02:00 does not exist, the task may run at the earliest available local time (normally 03:00); this is not treated as an asleep/off catch-up run. The fall-back day must produce one run only;
- password/background logon as explicitly selected by the user;
- `StartWhenAvailable = false` so missed runs are skipped;
- `WakeToRun = false` so sleeping/off computers are not awakened;
- `MultipleInstancesPolicy = IgnoreNew` so runs never overlap;
- explicit repository working directory and `py` invocation through the canonical PowerShell wrapper;
- bounded execution time and propagated nonzero exit code;
- no credentials written to repository files or logs; and
- task `Enabled = false` until final promotion.

Background logon is a high-risk compatibility boundary because BlueStacks is GUI software. Prove that a password-logon scheduled invocation can launch/foreground both configured instances, establish ADB, capture typed Home, and write artifacts while the interactive session is not relied upon. If that smoke fails, do not silently change logon mode; leave the task disabled and report the exact blocker.

The wrapper computes one `maintenance_date` in America/Toronto and one game-reset identifier at startup and passes both to every worker. The exact PNC daily-reset boundary remains an interview decision; the implementation must not infer it independently in each task.

## Implementation Phases

Every numbered slice below is independently mergeable and promotable. For each slice: run focused offline tests, run the full suite when shared runtime code changes, then run one positive live canary for that distinct behavior variant. NPC 2 is preferred when applicable; use free cookies when it is the only applicable target or when its configured policy is a distinct code path. Convert the live result or defect into a deterministic fixture/test and rerun the focused module. Do not duplicate an identical live mutation merely to cover the second castle. Stop mutation on an ambiguous postcondition; pre-mutation OCR or unknown noise uses the bounded recovery ladder before producing a runtime skip.

### Phase 0 — Preserve evidence and establish exact targets

1. Record the clean/dirty worktree state at implementation start and preserve any user changes that appear later.
2. Convert safe, representative Daily, bootstrap, Arena, campaign, gather, and destination screenshots into committed deterministic fixtures when size and privacy allow; otherwise document them in `tests/data/local_fixture_artifacts.example.json` and require explicit local fixture configuration.
3. Run the canonical `refresh_castle_roster` workflow once for each account, record `CastleRosterFreshness`, and propose the exact `castle_targets.yaml` alias changes for user review; do not overwrite the real target file without explicit authorization.
4. Add `daily_maintenance.example.yaml`, its typed loader, and cross-config validation. Add only the two selected local target entries after authorization.
5. Replace stale README examples and wrapper target lists only after exact aliases validate.

Acceptance: both target identities resolve uniquely; stale `testing` targets cannot enter the nightly wrapper; malformed policies fail before emulator launch.

Follow-up boundary: extract scheduled roster discovery, freshness policy, shared locking, and reviewed alias reconciliation into a separate `PNC_SCHEDULED_CASTLE_ROSTER_REFRESH_PLAN.md`. Daily maintenance consumes its cache contract but does not implement a second roster scanner or auto-rewrite authored target aliases.

### Phase 1 — Typed observation, bootstrap, and Daily row model

1. Add missing `ScreenType` and `UiElementId` values for all expected workflow states listed below.
2. Update observation requests, OCR capability routing, enrichment, classifier evidence, screen contracts, and selectors together; no enum-only additions.
3. Implement visual-X candidate detection for bootstrap popup regions. The detector returns current screenshot pixels, coordinate provenance, and a visual fingerprint, not an OCR location. Normalized authored regions are materialized once in vision; `ActionExecutor` never converts them again.
4. Implement `PNC_QUEST_MAIN` and `PNC_QUEST_DAILY` as distinct typed screens and parse Daily rows/actions/progress.
5. Implement stable scrolling and viewport exhaustion with a distinct one-retry `scroll_not_applied` state; a first repeated fingerprint is not sufficient bottom evidence.
6. Remove the unconditional generic popup-recovery call from `AutomationRunner._execute_step_loop`; migrate typed cross-workflow blockers into one typed recovery owner and keep generic visual-X detection inside bootstrap only.

Required typed states: publisher splash, black loading, Hero Showdown white loading, Home, Main Quest, Daily Quest, Infirmary, Rally Attack, Campaign global map, campaign chapter map, campaign stage detail, Hero Showdown ranking, Hero Formation, Hero Championship, Resource Shop, resource-search overlay, gather node, gather formation/march confirm, Talent, Alliance Shop, Trial exchange/Trial Shop, Rare Earth Shop, Enhance Gem, Enhance Saurgem, Enhance Gear, Summon Saurgil, Land of Trial floor, Lost Land, Alliance Gift, and BlueStacks Store/My Games.

Acceptance: all known planning artifacts classify to their expected typed state; Daily rows are stable across scrolls; Savannah and Valiant X positions are detected from geometry; every click has one coordinate provenance and one materialization; no task workflow can call generic-X recovery or generic Android-Back popup fallback.

### Phase 2 — Coordinator, claiming, exclusions, journal, and unknown recovery

1. Extract the canonical `TaskExecutor` from `AutomationRunner._execute_step_loop`, leave `ScriptRunner` as runtime wiring, and preserve existing authored-task behavior through tests. The coordinator is an application-level orchestration service that calls this executor; it is not a registered task running recursively inside the same executor.
2. Implement `DailyMaintenanceCoordinator`, catalog, policy filtering, claim sweep, Daily reopen/return behavior, and no-chest invariant.
3. Implement the durable intent/reconciliation journal and per-sub-operation mutation receipts. Add crash injection before dispatch, after dispatch, after observation, and before commit.
4. Implement the one-reread/one-safe-root/at-most-one-instance-restart recovery ladder with consumed-stage keys and runtime-unknown capability skips.
5. Test two instance workers in parallel and castles sequentially inside an instance using fakes before live execution.

Acceptance: excluded rows are never executed but can be claimed; completed rows moving downward do not duplicate work; crash injection never blindly repeats an ambiguous mutation; OCR/unknown noise does not cause a retry cycle or fail unrelated work; one instance failure does not stop the other.

### Phase 3 — One capability per incremental slice

Implement the following in order. Each line is a separate implementation/live-promotion slice and uses one feature-only smoke YAML generated or authored against the canonical task:

1. Resource item use.
2. Hero Hall five free singles, including cooldown checkpoint/resume.
3. Hero upgrade three times and exact level-70 restoration.
4. Praise.
5. Free Saurgil summon.
6. Wishes.
7. Trial Shop.
8. Rare Earth Shop.
9. Alliance Shop.
10. Gem enhancement.
11. Saurgem enhancement, with Rare Earth dependency receipt.
12. Gear enhancement.
13. Alliance donations.
14. Alliance Gifts.

For each purchase/use/enhancement slice, encode forbidden adjacent controls in the policy and verify both selection and resulting inventory/progress state. Do not treat closing the screen as proof of mutation.

### Phase 4 — Arena

1. Use Daily `Go`; accept direct Versus Center or Home with Arena highlight.
2. Reuse the canonical home-city atlas/pan to find Arena. Fix selectors rather than adding ad hoc coordinates.
3. Select Hero Showdown specifically. Hero Championship is a typed wrong mode: gold back, then reselect Hero Showdown.
4. Treat ranking-screen Challenge as navigation to candidates, not a battle.
5. Handle optional Elemental Fluctuation Intro; Confirm and X share the same typed postcondition.
6. If first-time defense formation appears, require exactly five game-preselected heroes and save once; otherwise stop.
7. Select the weakest foreign-kingdom candidate, use at most three free attempts, never refresh or buy.
8. Verify each result, return by gold controls to Home, reopen Daily, and validate row progress.

Implemented audit foundation: the Versus Center Hero Showdown entry, optional Elemental Intro, Hero Formation gate, and normal Ranking destination now have typed classifier/enrichment contracts. `tools/run_hero_arena_audit_entry.py` remains an optional operational-observation tool and deliberately stops before Arena mutation behavior.

Acceptance: one authorized positive Arena live canary observes the configured free-attempt path, journals each attempted battle separately, and proves that no paid/refresh action is reachable. The seven-entry audit is informative, not a promotion gate.

### Phase 5 — Campaign, Land of Trial, and Lost Land

Campaign:

1. Expand `CampaignPolicy` to the per-castle execution model.
2. Type global map, chapter map, stage detail, battle prep, active battle, victory/defeat, and AP-insufficient states.
3. `progress_then_farm` selects the highest actionable chapter and highest gold/unlocked node, rediscovering after a win; when blocked it farms the configured fallback.
4. `fixed_stage` validates and selects its configured unlocked chapter/node.
5. Require sufficient natural AP, preserve the existing lineup, Challenge once, enable Auto, never Blitz, and verify result.
6. Return through gold controls to typed Home and reopen Daily.

Land of Trial and Lost Land are separate slices after Campaign:

- Land of Trial chooses the first unlocked explicit Trial row and attacks once; win or loss counts.
- Lost Land opens the current stage, trusts exactly five preselected strongest heroes, saves only if required, challenges once, and accepts completion only when the Daily row advances.

### Phase 6 — Gathering

1. Extend `GatheringPolicy` and `GatheringTask`; remove the current visible-node/default-formation behavior rather than retaining it as a fallback.
2. From Daily `Go`, type World Map and explicitly open resource search.
3. Select resource category, highest available level, full resources only, then Confirm.
4. Verify node is unoccupied and has enough resources. Observe after each tap because one/two-tap behavior varies.
5. On formation, clear heroes, scan the entire troop list, and select cavalry only: T1 first, then available tiers ascending, stopping at the smallest sufficient capacity. Never use Quick Select.
6. If the full scan finds no cavalry, gold-back out, record a typed applicability skip, and continue the castle.
7. Dispatch one march only after capacity is sufficient, then verify march slot decrease or world-map march evidence.
8. Implement alliance-mine gathering as its own later slice using the same canonical cavalry formation builder.

Known target expectations: free cookies currently has only T4 Champion Infantry and should produce a proved no-cavalry applicability skip; NPC 2 has shown T8 Dragon Paladin and should perform the one minimum dispatch when the task is actionable.

### Phase 7 — Resource-building output boost

1. Repair the Farm atlas selector using the captured Talent false-positive as an offline regression.
2. Type resource-building and boost UI states for Farm, Lumber, Iron, and Gold.
3. Prefer an owned item. If none is usable and policy allows it, spend at most 200 diamonds.
4. Re-observe immediately before Use/Buy and verify the active boost/timer after one action.
5. Close a Talent modal only through its typed X if encountered outside a Talent workflow; never use a stale point.

The Farm route must reach and type the real boost UI read-only before any boost mutation is authorized for that target.

### Phase 8 — Composition, scheduling, and reporting

1. Replace the building-upgrade routine with one application-level coordinator entrypoint and remove obsolete multi-castle daily wrappers or parallel schemas. Do not implement the coordinator as a task that recursively invokes the task runner.
2. Keep the live smoke harness feature-only; require explicit account and castle alias instead of defaulting to `testing`.
3. Add a capability-validation runner that invokes one positive live canary per distinct behavior variant and preserves the selected target, result, and evidence. It does not repeat the same variant on the second castle. Normal production still records per-target outcomes and keeps mutations one castle at a time per instance.
4. Compose only promoted capabilities into the unattended routine. Unsupported or blocked slices remain disabled in typed config and appear in the report.
5. Implement the production wrapper with process lock, per-instance parallel workers, per-castle sequential execution, summary exit code, and artifact paths.
6. Add a Task Scheduler registration script that is idempotent, secret-safe, and disabled by default.
7. Validate the manual wrapper, disabled task definition, password/background launch, no-overlap behavior, missed-trigger policy, and a forced nonzero child exit.

Acceptance: the composed routine cannot include an unpromoted capability; only NPC 2 and free cookies resolve; the disabled task definition exactly matches the locked schedule policy.

## Slice-by-Slice Live Validation Matrix

Each row requires one positive live canary per distinct behavior variant, not one mutation per castle. The selected canary target is recorded in the run summary. Both production targets still require valid typed configuration, a fresh roster-cache match, offline policy coverage, and a normal per-run outcome, but the second castle does not duplicate an identical pre-promotion mutation. Every canary captures baseline, pre-mutation, post-mutation, final Home/Daily state, observation/OCR sidecars, logs, and a run summary.

| Slice | Required single live canary or variant | Other-target deployment guard | Promotion gate |
|---|---|---|---|
| Bootstrap and generic startup X | One typed startup-to-Home trace when a supported popup is present | Savannah/Valiant deterministic fixtures and typed unknown recovery | Generic recovery is unreachable after bootstrap |
| Daily screen and full scroll | One complete read-only sweep | Offline target-resolution and row fixtures | Two-frame dynamic geometry; failed swipe is not bottom |
| Claims/exclusions | One eligible claim | Policy fixtures for both target configs | No chest tap; excluded `Go` never tapped |
| Journal/restart | Offline crash injection plus one live reconciliation observation if an interruption naturally occurs | Same journal state machine for every target | No blind replay; no recovery cycle |
| Resource item | One smallest-item use | Typed inventory/no-item outcome at runtime | No bulk/orange Use |
| Hero Hall | One five-single cooldown/resume path | Typed unavailable outcome at runtime | No 10x/paid action |
| Hero upgrade | One three-upgrade and exact-reset path | Typed precondition outcome at runtime | Ends level 70 |
| Praise | One top-rank praise | Typed already-praised outcome | Daily progress verified |
| Saurgil | One free summon | Typed no-free-summon outcome | No paid 10x |
| Wishes | One configured wish-policy variant | Each materially different diamond policy is its own variant | Diamond total obeys the exact policy budget |
| Trial Shop | One live canary for each distinct main/farm purchase policy | Other castles sharing that policy use offline/config coverage | No refresh; canonical Trial naming |
| Rare Earth Shop | One exact purchase | Typed inventory/currency outcome | Exactly one purchase |
| Alliance Shop | One priority-chain purchase | Typed inventory/currency outcome | No refresh/gem/5-min+ purchase |
| Enhance Gem/Saurgem/Gear | One canary per distinct enhancement UI/receipt dependency | Typed no-material outcome | No Auto Select; one material |
| Donations | One bounded resource-only sequence | Typed max/unavailable outcome | No diamonds |
| Alliance Gifts | One full-list exhaustion | Typed empty-list outcome | No `Open` remains |
| Arena | One positive Hero Showdown feature smoke | Target config and typed intro/formation handling | Three free attempts max; no refresh/buy; seven-day audit optional |
| Campaign | One canary for `fixed_stage` and one for `progress_then_farm` | Castles sharing a mode use offline/config coverage | Result and Daily progress verified; no Blitz |
| Land of Trial | One Attack | Typed no-unlocked-row outcome | Win/loss typed and bounded |
| Lost Land | One Challenge | Typed locked/unavailable outcome | Exactly five preselected; Daily row advances |
| Resource gathering | One cavalry-only resource march proves the shared formation builder | Resource-category selectors use fixtures; no-cavalry remains a typed runtime outcome | No hero/Quick Select; capacity verified |
| Alliance mine | One separate alliance-mine march canary | Typed unavailable outcome | Shared cavalry formation invariant |
| Resource-building boost | One item-first/diamond-capped boost mutation after every building route has a read-only fixture | Other building routes use classifier/selector fixtures | Talent regression passes; post-boost timer; diamond cap 200 |
| Multi-instance wrapper | One concurrent synthetic safe/no-op run across both workers | Both target identities come from the fresh cache | Isolation and separate summaries |
| Scheduled background launch | One disabled-task manual run captures typed Home for both workers | No repeated per-capability identity navigation | Password logon proven; no overlap; DST policy inspected |

`unittest.skip*` is never live evidence. A live applicability outcome is a successful structured runtime result with a closed `DailyApplicabilitySkipReason`, current target identity, and artifact path. OCR failure uses `runtime_unknown_skip`, not `applicability_skip`.

## Offline Validation Plan

For each slice, run the narrowest relevant module first. Add or extend tests for:

- policy parsing and cross-config validation;
- row-title normalization, progress/action parsing, duplicate/unknown rows, completed-row reordering, stable geometry, and scroll exhaustion;
- exactly-once geometry materialization across supported screenshot sizes, including tests that fail on double scaling and prove `ActionExecutor` receives final ADB pixels;
- bootstrap X detection with Savannah/Valiant variants and false-positive rejection outside bootstrap;
- all typed screen classifiers and selector contracts from saved screenshots;
- no OCR coordinate flow into `TapAction`;
- task policy prohibitions and exact mutation count;
- journal atomicity, prepared/dispatched/reconciled/committed transitions, crash injection at every boundary, consumed recovery stages, and no blind replay;
- one-reread/one-safe-root/one-instance-restart recovery without cycles; OCR and unknown failures skip only the affected capability when Home is recoverable;
- per-instance parallelism and per-instance castle serialization;
- live-canary record completeness per distinct behavior variant and both-target configuration/applicability coverage;
- scheduler XML/PowerShell settings, quoting, working directory, disabled default, `StartWhenAvailable=false`, `WakeToRun=false`, and `IgnoreNew`;
- stale/missing castle aliases failing before launch; and
- the Talent false-positive Farm regression.

Commands, adjusted to the final module names:

```powershell
py -m unittest tests.test_daily_maintenance_config
py -m unittest tests.test_daily_quest_catalog tests.test_daily_maintenance_coordinator
py -m unittest tests.test_daily_capability_tasks
py -m unittest tests.test_capture_and_vision tests.test_screen_classifier tests.test_selectors
py -m unittest tests.test_runtime_castle_targeting tests.test_script_runner
py -m unittest tests.test_daily_scheduler
py -m unittest discover -s tests
```

Screenshot-backed tests skip clearly only when local-only fixtures are intentionally not configured. A live result or stable visual defect becomes a deterministic regression fixture/test, and the focused module is rerun before promotion. Do not repeat a successful live mutation after its fixture-backed offline test passes.

`tools/validate_navigation_selectors.py` is a live validator, not an offline command. Run it only after selector/navigation changes, with one explicit account and only the selectors changed by the slice. Example shape:

```powershell
py tools/validate_navigation_selectors.py --account mega_old_acc --selector PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY
```

Do not invoke the tool with its broad all-selector default as part of this plan. The selected validation target and navigation actions must remain read-only and bounded.

## Live Smoke Contract and Commands

Keep `tests/test_live_daily_task_smoke.py` as the canonical one-feature harness, but require all of:

- `PNC_RUN_LIVE_DAILY_TASK_SMOKE=1`;
- explicit `PNC_LIVE_SMOKE_ACCOUNT`;
- explicit `PNC_LIVE_DAILY_TASK_SMOKE_CASTLE_REF`;
- explicit `PNC_LIVE_DAILY_TASK_SMOKE_SCRIPT`; and
- a structured mutation acknowledgement for smokes that spend, battle, claim, donate, enhance, wish, summon, or dispatch. It must match the account, castle alias, capability, America/Toronto date, maximum mutation count, and maximum diamond spend declared by the smoke policy. A stale or broader acknowledgement fails before ADB connection.

Example shape after exact aliases exist:

```powershell
$env:PNC_RUN_LIVE_DAILY_TASK_SMOKE="1"
$env:PNC_LIVE_SMOKE_ACCOUNT="mega_old_acc"
$env:PNC_LIVE_DAILY_TASK_SMOKE_CASTLE_REF="npc_2"
$env:PNC_LIVE_DAILY_TASK_SMOKE_SCRIPT="scripts/smoke/daily/<feature>.yaml"
py -m unittest tests.test_live_daily_task_smoke
```

Run a second command only when it exercises a materially different configured behavior variant; change the explicit account, castle, script, and acknowledgement together. The implementation must not assume these alias strings until the refreshed roster and local config confirm them. The smoke verifies ADB reaches the resolved instance, resolves exact castle identity once at the castle-selection boundary, and aborts before task action if identity differs. It does not reopen identity screens between capability steps.

## Promotion Gates

A capability may enter the coordinator's enabled capability set only when:

1. focused offline tests pass;
2. the full offline suite passes after shared-runtime changes;
3. selector validation passes when selectors/navigation changed;
4. one positive live canary passes for each distinct behavior variant, on NPC 2 by default or free cookies when appropriate;
5. both target configurations and cached identities validate offline, while target-specific runtime inapplicability uses a structured `DailyApplicabilitySkipReason` during normal execution rather than a duplicate promotion smoke;
6. all known screens in that workflow are typed;
7. no forbidden adjacent action occurred;
8. artifacts and the per-operation mutation receipt were inspected;
9. the successful live result or any live-discovered bug was converted into deterministic offline coverage and the focused test module passed afterward; and
10. the capability recovery graph has no cycle and cannot consume the same recovery stage twice.

Additional global gates before the disabled scheduled task is considered ready:

- Farm output-boost UI is observed and typed on the repaired route.
- Exact NPC 2 and free-cookies castle aliases are refreshed and reviewed against a timestamped full-scan roster.
- The distinct-variant live-canary matrix has no blank or `blocked` required canary, and both production target configs pass offline validation.
- A composed manual run completes both instances with castles sequential per instance.
- Password/background Task Scheduler execution reaches typed Home and writes artifacts for both workers.
- No-catch-up and no-overlap settings are inspected from the registered disabled task.
- The registered task uses an offset-free 02:00 boundary, validates Windows `Eastern Standard Time`, and records the expected spring-forward/fall-back behavior.
- Scheduler remains disabled until the user explicitly promotes it.

## Data, Config, and Migration Notes

- Preserve the user's working tree regardless of whether it is clean or dirty at implementation start. Reconcile overlapping files rather than reverting them.
- Replace the current building-only daily routine with the canonical daily-maintenance application entrypoint; do not retain it as a compatibility path or add a coordinator task that recursively invokes the task runner.
- Remove the deleted/obsolete `multi_castle_daily_maintenance.yaml` path and document one canonical coordinator entrypoint plus invocation-time target binding. If the existing routine YAML is retained as a manifest, it is not a second executor.
- Update the live-smoke default away from building upgrade; require explicit feature and target.
- Rename Tower Shop symbols, config values, selectors, artifacts labels where authored, and tests to Trial Shop. Do not add an alias.
- Migrate Campaign and Gathering policy schemas in one step with strict validation. Authored scripts using obsolete fields must be updated; no dual parser.
- Store run journals and summaries under `artifacts/<date>/<account>/<castle>/daily-maintenance/`; do not store secrets.
- Keep real `accounts.yaml`, `castles.yaml`, `castle_targets.yaml`, and new local daily config out of plan-generated overwrites. Changes require exact diff review.
- The existing `refresh_castle_roster` task remains the only full-scan roster implementation. A separate scheduled-roster-refresh plan adds timestamps/fingerprints, scheduling, locking, and alias-diff proposals; it may update `castles.yaml` but must never invent or silently rewrite authored `castle_targets.yaml` aliases.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Game adds a new startup popup | Generic visual-X search is bootstrap-only, freshly fingerprinted, one-tap, and followed by typed Home validation; no X means bounded failure. |
| OCR misreads a task title | Two stable observations, exact alias catalog, one semantic reread, then skip/report. OCR never controls coordinates. |
| Dynamic rows move after completion | Reopen/rescan Daily after each task and reselect by semantic ID plus fresh geometry. |
| Retry duplicates a purchase or battle | Persist a per-operation intent before dispatch, reconcile once after an interruption, retry only from a positively proven original precondition, and otherwise mark that capability pending clarification. |
| Low-level castle lacks a feature | Closed typed applicability reason during normal execution; no blind substitute action and no duplicate pre-promotion smoke solely for the second castle. |
| Background Task Scheduler cannot drive BlueStacks | Treat password-logon launch as a hard disabled-task promotion gate; do not change selected policy silently. |
| Parallel instances cross-wire ADB or artifacts | Resolve configured endpoints per account, verify identity before action, isolate sessions/journals/artifact roots, and never hard-code ports. |
| Premium currency is spent unexpectedly | Typed caps/prohibitions, selector allowlists, exact mutation count, and pre-mutation observation. |
| Campaign/gathering implementation diverges from direct tasks | Extract/reuse canonical executor and extend existing task ownership; remove old behavior rather than wrap it. |
| UI variability appears after a single canary | Preserve typed unknown recovery, deterministic fixtures for observed variants, and normal production artifacts; the optional Arena audit is operational evidence rather than a promotion gate. |
| OCR or unknown recovery loops | Consume each recovery stage once per castle/capability, prefer capability skip after safe-root recovery, and allow at most one instance restart per castle run. |
| Coordinate double conversion | Materialize normalized geometry once in vision, carry provenance, and test that `ActionExecutor` receives final ADB pixels unchanged. |
| Roster verification slows every capability | Refresh the canonical roster cache out of band, validate once per castle-selection/session boundary, and reuse cached identity until an explicit invalidation event. |

## Open Questions

The 2026-09-02 review resolved premium spending, coordinate ownership, live-canary count, and per-capability identity reuse. The following items are reserved for the requested interview refinement:

- Exact PNC daily-reset boundary and the canonical `game_reset_id` calculation used beside the Toronto maintenance date.
- Mutation-acknowledgement representation and operator workflow, while retaining exact account/castle/capability/date/count/diamond binding.
- Scheduled roster-refresh cadence, maximum accepted cache age, and whether it shares the maintenance task or uses a separate disabled Task Scheduler registration. The architecture recommendation is a separate follow-up plan sharing the same process lock.
- Whether the application-level coordinator replaces the routine YAML entirely or the YAML remains a non-executable manifest. It must not become a recursively executing `AutomationTask`.
- Exact refreshed kingdom and alias records for NPC 2 and free cookies.
- Farm's actual boost UI after selector repair.
- VIP Login/Daily Reset popup occurrence when naturally encountered.
- Whether password/background Task Scheduler execution can operate BlueStacks on this Windows installation.

If one of these produces an unknown screen, use the bounded recovery ladder first. Ask for classification only after the broad reread and safe-root attempt fail; never enter a restart loop.

## Execution Checklist

- [ ] Record the worktree state and preserve current user changes.
- [ ] Establish deterministic/live fixture manifest from planning artifacts.
- [ ] Refresh the canonical roster once per account, persist freshness metadata, and review exact NPC 2/free-cookies target aliases.
- [ ] Create the separate scheduled castle-roster-refresh plan; do not duplicate its scanner in daily maintenance.
- [ ] Implement and validate typed daily config.
- [ ] Implement Phase 1 classification, bootstrap-X, and stable Daily scan.
- [ ] Implement Phase 2 coordinator, journal, and unknown recovery.
- [ ] Promote each Phase 3 behavior variant through one positive live canary plus both-target offline/config validation.
- [ ] Run one positive Arena canary and promote Arena; keep the seven-entry audit optional.
- [ ] Promote Campaign, Land of Trial, and Lost Land independently.
- [ ] Promote each resource gathering type and alliance mine independently.
- [ ] Repair Farm and promote each building boost independently.
- [ ] Compose only promoted tasks into the canonical coordinator entrypoint.
- [ ] Validate full offline suite and selector tooling.
- [ ] Run the composed two-instance manual smoke.
- [ ] Register and inspect the disabled 02:00 Task Scheduler task.
- [ ] Prove password/background launch, no overlap, no catch-up, exit propagation, and artifacts.
- [ ] Present the distinct-variant canary matrix, both-target config outcomes, and blockers; enable scheduling only on explicit user instruction.
