# PNC Daily Castle Maintenance Automation — Implementation and Live-Promotion Plan

## Context

PNC needs a low-touch daily-maintenance runner that executes at 02:00 America/Toronto across selected castles. One BlueStacks instance maps to one account, one account may contain several castles, instances may run in parallel, and castles within an instance run sequentially. The first production scope is deliberately limited to two targets:

| Account | Castle | Role |
|---|---|---|
| `mega_old_acc` | `[NGF] NPC 2` | higher-level canary and broad feature coverage |
| `serious_stuff` | `[NAX] free cookies` | serious target and lower-progression applicability coverage |

The current worktree contains an uncommitted building-upgrade-only routine, one-feature live-smoke harness, and scheduler wrapper. Building upgrades are explicitly excluded from daily maintenance, and the current wrapper targets stale castles. These files are inputs to migrate, not behavior to preserve.

This plan is based on the live evidence gathered during the planning sessions through 2026-08-31. It does not authorize new game mutations during implementation beyond the narrowly enabled opt-in live smoke being run at that time. Every mutation must be the minimum action needed to prove one slice.

The rollout follows small-change/canary principles: deterministic tests first, one narrow live behavior at a time, NPC 2 first, then free cookies, and no promotion into the unattended routine until both target dispositions are recorded. This follows [Google SRE canary guidance](https://sre.google/workbook/canarying-releases/). ADB target verification and screenshot capture follow the [Android ADB documentation](https://developer.android.com/tools/adb). Windows schedule semantics follow Microsoft's documentation for [logon types](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype), [task settings](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings), and [multiple-instance policy](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-multipleinstances).

## Goals

- Run only the selected castles every day at 02:00 local Toronto time, including daylight-saving transitions.
- Use normalized screen geometry for all clicks. OCR may classify text and validate meaning but must never provide click coordinates.
- Discover and process Daily Quest rows despite scrolling, row reordering, completed rows moving to the bottom, and `Go` changing to `Claim` or disappearing after claim.
- Close startup interruptions through a freshly detected visual X when available, then require a typed Home screen.
- Execute all enabled daily capabilities with strict no-premium/no-adjacent-action policies.
- Continue other instances when one fails; checkpoint and recover an interrupted castle without repeating completed mutating work.
- Interrupt interactive runs immediately on genuinely unknown runtime states. In unattended runs, perform bounded instance-local recovery and preserve clarification evidence.
- Develop and live-test incrementally. Every runtime-affecting slice must be tested on both planned targets or produce a proven typed applicability skip.

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

- Capture and observation geometry is transformed to the current ADB device input size through the canonical action executor. All normalized taps pass through that path.
- OCR supplies task titles, amounts, button semantics, and screen evidence only. It does not return the coordinate clicked.
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

- `UNKNOWN` during an interactive live smoke pauses immediately and requests user classification with the latest screenshot, observation/OCR sidecars, account, castle, and attempted transition.
- `UNKNOWN` during unattended execution checkpoints the current task and its progress, restarts only that BlueStacks instance, returns to typed Home, reopens Daily Quest, and retries the unfinished task up to three times.
- Completed task IDs and mutation receipts are journaled before advancing. Recovery never repeats a completed purchase, summon, battle, wish, claim, donation, enhancement, or march.
- After three unknown-state recoveries, stop that instance, mark the castle `pending_clarification`, and preserve evidence. Continue the other instance.
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

The planning evidence questions are answered by current artifacts except for explicitly stated promotion gates.

| Question | Disposition | Evidence or gate |
|---|---|---|
| Verify free cookies identity | `artifact_answered` | `artifacts/2026-08-30/serious_stuff/20260830T205813Z_daily_plan_serious_identity_confirm.png` |
| Verify NPC 2 identity | `artifact_answered` | `artifacts/2026-08-28/mega_old_acc/20260828T202628Z_daily_plan_npc2_identity_post_action_1.png` |
| Arena `Go` Home highlight and formation | `artifact_answered` | `artifacts/2026-08-31/serious_stuff/20260831T164834Z_daily_plan_serious_arena_go_normalized_post_action_1.png`; `artifacts/2026-08-31/serious_stuff/20260831T165233Z_daily_plan_serious_after_elemental_intro_day2_post_action_1.png` |
| Campaign map/stage route | `artifact_answered` | `artifacts/2026-08-31/serious_stuff/20260831T153132Z_daily_plan_serious_ch10_node3_guarded_post_action_1.png` |
| Gathering formation and full troop-list scan | `artifact_answered` | `artifacts/2026-08-31/serious_stuff/20260831T171853Z_daily_plan_serious_food_gather_formation_post_action_1.png`; `artifacts/2026-08-31/serious_stuff/20260831T175928Z_daily_plan_serious_gather_troop_list_scan2_post_action_1.png` |
| Startup promotional X variants | `artifact_answered` | Savannah: `artifacts/2026-08-31/serious_stuff/20260831T121544Z_daily_plan_serious_after_publisher_splash.png`; Valiant Conquest: `artifacts/2026-08-28/testing/20260828T173500Z_ensure_game_running_post_action_1.png` |
| Lost Land route and return | `artifact_answered` | `artifacts/2026-08-29/mega_old_acc/20260829T011446Z_daily_plan_npc2_lost_land_open_post_action_1.png`; `artifacts/2026-08-29/mega_old_acc/20260829T011658Z_daily_plan_npc2_lost_land_visual_back_post_action_1.png` |
| Alliance Gift entry | `artifact_answered` | `artifacts/2026-08-31/mega_old_acc/20260831T224908Z_daily_plan_npc2_home_before_lostland_quest.png` |
| Praise, Saurgil, enhancements, wishes, trials, and shops destinations | `artifact_answered` | Existing labeled 2026-08-29/30 NPC 2 artifacts listed in the implementation issue/session record. Preserve them as fixtures or local fixture references. |
| Farm output-boost UI | `live_blocked` | The atlas false-positive opened Talent (`artifacts/2026-08-30/mega_old_acc/20260830T152907Z_open_building_post_action_1.png`). Repair Farm selection and observe the actual boost UI before implementing its mutating step. |
| VIP Login popup behavior | `mutation_boundary` | Sample opportunistically during the seven-night startup audit. Runtime uses X; if Confirm appears, verify once that it reaches the same typed postcondition. |
| NPC 2 Arena variability | `live_blocked` promotion gate | The qualifying consecutive streak began 2026-09-01 and is 1/7. Entry 1 showed the Elemental Intro and the expected unset-Formation gate without changing/saving formation or entering an attempt. The weekly Formation reset is known to occur Monday 00:00 UTC; this audit does not test it because Formation remains intentionally unset and the game asks on every visit until saved. A guarded daily helper now types Intro, Formation, and Ranking, permits only normalized-geometry entry/confirm/back taps, rejects unknown destinations and duplicate dates, and has no Save/Challenge/attempt action. Its read-only live selector check passed on NPC 2. Six entries remain through 2026-09-07; see `reviewed_plans/PNC_HERO_ARENA_SEVEN_ENTRY_AUDIT.md`. Free-cookies evidence is supporting only. |

## Target Design

### Canonical ownership

1. `DailyMaintenanceCoordinator` owns one castle's Daily Quest lifecycle: enter Daily, scan rows, claim completed rows, select enabled work, call the canonical capability executor, reopen Daily, checkpoint, and finish.
2. `DailyQuestCatalog` owns exact title aliases and maps them to `DailyQuestId`, policy category, and capability `TaskId`. It is the only semantic parser for Daily rows.
3. `TaskExecutor` is extracted from the current `ScriptRunner` step loop so the coordinator and authored scripts execute the same registered `AutomationTask`. There is no second action loop.
4. Each capability has one canonical task implementation. Extend and reuse `CampaignTask` and `GatheringTask`; do not add daily-specific copies. New capabilities use focused task classes registered once.
5. `DailyRunJournalStore` owns durable per-date, per-account, per-castle checkpoints and mutation receipts. The coordinator never infers completion from in-memory state after restart.
6. `BootstrapInterruptionRecovery` owns generic startup visual-X discovery. Task implementations may use only typed workflow-specific close/back selectors.
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
- `DailyTaskCheckpoint`: date, target, current task, per-task progress, completed task IDs, mutation receipts, recovery count, and last typed screen.
- `DailyTargetOutcome`: success, typed skip, failed, pending clarification, and artifact references.

Create `config/daily_maintenance.example.yaml` and local `config/daily_maintenance.yaml`. The local file is keyed by account ID and castle alias and contains only the two selected targets. It configures campaign mode/target, Trial Shop policy, wish policy, boost cap, and feature enablement. It does not duplicate account, instance, kingdom, or castle identity fields. Those remain referenced from canonical account/castle-target config.

Fail loading before launching BlueStacks when:

- an account or castle alias is missing or ambiguous;
- a fixed campaign target is incomplete;
- an excluded capability is enabled;
- a premium cap is negative or exceeds the locked maximum;
- a shop policy names a forbidden item;
- the same physical castle is selected twice; or
- an unattended target lacks an exact live-verified identity.

### Quest scanning and execution

The coordinator uses a bounded top-to-bottom sweep:

1. reach typed Home;
2. open Quest, explicitly select Daily Quest, and require `PNC_QUEST_DAILY`;
3. observe twice and compare row geometry;
4. process all visible Claim rows first, journaling each claim;
5. classify visible Go/Requirement/completed rows;
6. execute one enabled actionable row, then return to typed Home and reopen Daily;
7. scroll by normalized geometry, require two stable observations, and continue until a repeated viewport fingerprint or bottom marker proves exhaustion;
8. rescan once for claims created by completed work; and
9. exit with gold back and require Home.

Completed rows moving to the bottom is expected. Row ordering is never a task identity. Each click reselects by task ID plus fresh current-frame geometry.

### Runtime concurrency and recovery

- The top-level runner groups targets by BlueStacks instance.
- Instance workers run concurrently with isolated sessions, journals, logs, and artifact namespaces.
- Castle targets inside one instance run in configured order and never overlap.
- An instance worker failure cannot cancel the other worker.
- A process-level lock prevents two nightly wrappers from overlapping.
- The journal uses atomic replace and is written before a mutating task is marked complete.
- Restart recovery validates account and castle identity before resuming.

### Scheduling

Use Windows Task Scheduler as the external trigger. Register one task disabled with:

- daily local trigger at 02:00; Windows handles America/Toronto DST using the machine's local timezone;
- password/background logon as explicitly selected by the user;
- `StartWhenAvailable = false` so missed runs are skipped;
- `WakeToRun = false` so sleeping/off computers are not awakened;
- `MultipleInstancesPolicy = IgnoreNew` so runs never overlap;
- explicit repository working directory and `py` invocation through the canonical PowerShell wrapper;
- bounded execution time and propagated nonzero exit code;
- no credentials written to repository files or logs; and
- task `Enabled = false` until final promotion.

Background logon is a high-risk compatibility boundary because BlueStacks is GUI software. Prove that a password-logon scheduled invocation can launch/foreground both configured instances, establish ADB, capture typed Home, and write artifacts while the interactive session is not relied upon. If that smoke fails, do not silently change logon mode; leave the task disabled and report the exact blocker.

## Implementation Phases

Every numbered slice below is independently mergeable and promotable. For each slice: run focused offline tests, run the full suite when shared runtime code changes, run one-feature NPC 2 live smoke, then run the same smoke on free cookies. Stop that target on `UNKNOWN`, ambiguous geometry, forbidden adjacent action, or unverified postcondition. Do not add the slice to `daily_castle_maintenance.yaml` before its target matrix is complete.

### Phase 0 — Preserve evidence and establish exact targets

1. Inventory the dirty worktree and preserve user changes.
2. Convert safe, representative Daily, bootstrap, Arena, campaign, gather, and destination screenshots into committed deterministic fixtures when size and privacy allow; otherwise document them in `tests/data/local_fixture_artifacts.example.json` and require explicit local fixture configuration.
3. Refresh the live roster through the canonical read-only roster path for NPC 2 and free cookies. Propose the exact `castle_targets.yaml` alias changes for user review; do not overwrite the real file without explicit authorization.
4. Add `daily_maintenance.example.yaml`, its typed loader, and cross-config validation. Add only the two selected local target entries after authorization.
5. Replace stale README examples and wrapper target lists only after exact aliases validate.

Acceptance: both target identities resolve uniquely; stale `testing` targets cannot enter the nightly wrapper; malformed policies fail before emulator launch.

### Phase 1 — Typed observation, bootstrap, and Daily row model

1. Add missing `ScreenType` and `UiElementId` values for all expected workflow states listed below.
2. Update observation requests, OCR capability routing, enrichment, classifier evidence, screen contracts, and selectors together; no enum-only additions.
3. Implement visual-X candidate detection for bootstrap popup regions. The detector returns normalized geometry and a visual fingerprint, not an OCR location.
4. Implement `PNC_QUEST_MAIN` and `PNC_QUEST_DAILY` as distinct typed screens and parse Daily rows/actions/progress.
5. Implement stable scrolling and viewport exhaustion.

Required typed states: publisher splash, black loading, Hero Showdown white loading, Home, Main Quest, Daily Quest, Infirmary, Rally Attack, Campaign global map, campaign chapter map, campaign stage detail, Hero Showdown ranking, Hero Formation, Hero Championship, Resource Shop, resource-search overlay, gather node, gather formation/march confirm, Talent, Alliance Shop, Trial exchange/Trial Shop, Rare Earth Shop, Enhance Gem, Enhance Saurgem, Enhance Gear, Summon Saurgil, Land of Trial floor, Lost Land, Alliance Gift, and BlueStacks Store/My Games.

Acceptance: all known planning artifacts classify to their expected typed state; Daily rows are stable across scrolls; Savannah and Valiant X positions are detected from geometry; no task workflow can call generic-X recovery.

### Phase 2 — Coordinator, claiming, exclusions, journal, and unknown recovery

1. Extract the canonical `TaskExecutor` from `ScriptRunner` and preserve existing authored-task behavior through tests.
2. Implement `DailyMaintenanceCoordinator`, catalog, policy filtering, claim sweep, Daily reopen/return behavior, and no-chest invariant.
3. Implement the durable run journal and idempotent mutation receipts.
4. Implement interactive pause and unattended three-restart instance-local recovery.
5. Test two instance workers in parallel and castles sequentially inside an instance using fakes before live execution.

Acceptance: excluded rows are never executed but can be claimed; completed rows moving downward do not duplicate work; a simulated process restart resumes the unfinished task only; one instance failure does not stop the other.

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

Implemented audit foundation: the Versus Center Hero Showdown entry, optional Elemental Intro, Hero Formation gate, and normal Ranking destination now have typed classifier/enrichment contracts. `tools/run_hero_arena_audit_entry.py` reuses those contracts to collect entries 2–7 while deliberately stopping before Arena mutation behavior is implemented.

Acceptance: all three free attempts are bounded and journaled; no paid/refresh action is reachable; the seven-consecutive-NPC2-entry audit reaches 7/7 before unattended promotion.

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

1. Replace the building-upgrade routine with one coordinator step and remove obsolete multi-castle daily wrappers or parallel schemas.
2. Keep the live smoke harness feature-only; require explicit account and castle alias instead of defaulting to `testing`.
3. Add a target-matrix runner that invokes one feature smoke on NPC 2, then free cookies, preserving separate results. It may run instances in parallel only after the NPC 2 canary passes; mutating smokes remain one castle at a time per instance.
4. Compose only promoted capabilities into the unattended routine. Unsupported or blocked slices remain disabled in typed config and appear in the report.
5. Implement the production wrapper with process lock, per-instance parallel workers, per-castle sequential execution, summary exit code, and artifact paths.
6. Add a Task Scheduler registration script that is idempotent, secret-safe, and disabled by default.
7. Validate the manual wrapper, disabled task definition, password/background launch, no-overlap behavior, missed-trigger policy, and a forced nonzero child exit.

Acceptance: the composed routine cannot include an unpromoted capability; only NPC 2 and free cookies resolve; the disabled task definition exactly matches the locked schedule policy.

## Slice-by-Slice Live Validation Matrix

Every row is required after its implementation. `Pass/skip` means the live test must end as either an observed success or a typed `applicability_skip` with the named predicate; it never means “not run.” Every smoke captures baseline, pre-mutation, post-mutation, final Home/Daily state, observation/OCR sidecars, logs, and a run summary.

| Slice | NPC 2 (`mega_old_acc`) | free cookies (`serious_stuff`) | Promotion gate |
|---|---|---|---|
| Bootstrap and generic startup X | Pass typed startup-to-Home; sample popup if present | Pass typed startup-to-Home; sample popup if present | Savannah/Valiant fixtures pass; unknown popup stops |
| Daily screen and full scroll | Pass full scan, no mutation | Pass full scan, no mutation | No expected screen is `UNKNOWN`; two-frame geometry stability |
| Claims/exclusions | Claim one eligible row or typed no-claim skip | Same | No chest tap; excluded Go never tapped |
| Journal/restart | Inject safe interruption before mutation and resume | Same | Completed receipt is not replayed |
| Resource item | Use one smallest item or typed no-item skip | Same | No bulk/orange Use |
| Hero Hall | Five free singles across cooldown/resume or typed unavailable skip | Same | No 10x/paid action |
| Hero upgrade | Three upgrades and exact reset or typed precondition skip | Same | Ends level 70 |
| Praise | One top-rank praise or already-praised skip | Same | Daily progress verified |
| Saurgil | One free summon or no-free-summon skip | Same | No paid 10x |
| Wishes | Execute bounded configured wishes or typed unavailable skip | Same | Diamond total obeys policy |
| Trial Shop | Execute NPC 2 configured policy or typed inventory/currency skip | Execute free-cookies configured policy or typed skip | No refresh; canonical Trial naming |
| Rare Earth Shop | Buy one 1-star Saurgem Essence or typed skip | Same | Exactly one purchase |
| Alliance Shop | One 1-min speedup, else one 1-star gear, else typed skip | Same | No refresh/gem/5-min+ purchase |
| Enhance Gem | One lowest-star material or typed no-material skip | Same | No Auto Select |
| Enhance Saurgem | Purchase receipt then one enhancement or typed skip | Same | Dependency and exactly one material |
| Enhance Gear | One enhancement or typed no-material skip | Same | No Auto Select |
| Donations | One bounded resource-only donation sequence or typed max/unavailable skip | Same | No diamonds |
| Alliance Gifts | Open/remove eligible gifts or typed empty-list skip | Same | Full-list exhaustion and no Open remains |
| Arena | One feature smoke plus remaining six audit entries to reach 7/7 | One feature smoke; intro/formation variant if presented | Three free attempts max; no refresh/buy |
| Campaign fixed/progress mode | Run configured mode once or natural-AP/locked typed skip | Run configured mode once or typed progression skip | Result and Daily progress verified; no Blitz |
| Land of Trial | One Attack or no-unlocked-row skip | Same | Win/loss typed and bounded |
| Lost Land | One Challenge or locked/unavailable skip | Same | Exactly five preselected; Daily row advances |
| Food gathering | One cavalry-only march or no-cavalry/no-slot skip | Expected no-cavalry skip from full scan | No hero/Quick Select; capacity verified |
| Wood gathering | Same | Same | Same |
| Iron gathering | Same | Same | Same |
| Gold gathering | Same | Same | Same |
| Alliance mine | One cavalry-only march or typed unavailable skip | Same | Same formation invariant |
| Farm boost | Reach typed boost UI, then one bounded boost or typed no-item/cap skip | Same | Talent regression passes; post-boost timer |
| Lumber/Iron/Gold boost | One bounded boost per independently promoted building slice or typed skip | Same | Item first; diamond cap 200 |
| Multi-instance wrapper | Run NPC 2 worker with synthetic safe/no-op capability | Run free-cookies worker concurrently | Isolation and separate summaries |
| Scheduled background launch | Typed Home capture through disabled-task manual run | Typed Home capture in same wrapper | Password logon proven, no overlap/catch-up |

For true feature unavailability, use an explicit `unittest.skip*` reason or a successful typed runtime skip; Python's [skip semantics](https://docs.python.org/3/library/unittest.html#skipping-tests-and-expected-failures) do not justify leaving a target untested.

## Offline Validation Plan

For each slice, run the narrowest relevant module first. Add or extend tests for:

- policy parsing and cross-config validation;
- row-title normalization, progress/action parsing, duplicate/unknown rows, completed-row reordering, stable geometry, and scroll exhaustion;
- capture-to-input normalization across supported screen sizes;
- bootstrap X detection with Savannah/Valiant variants and false-positive rejection outside bootstrap;
- all typed screen classifiers and selector contracts from saved screenshots;
- no OCR coordinate flow into `TapAction`;
- task policy prohibitions and exact mutation count;
- journal atomicity, receipts, restart retry cap, and no replay;
- per-instance parallelism and per-instance castle serialization;
- target-matrix completeness; blank/not-tested cells fail;
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
py tools/validate_navigation_selectors.py
```

Screenshot-backed tests skip clearly only when local-only fixtures are intentionally not configured. A live failure that reveals a stable visual defect gets a deterministic regression fixture before the next live retry.

## Live Smoke Contract and Commands

Keep `tests/test_live_daily_task_smoke.py` as the canonical one-feature harness, but require all of:

- `PNC_RUN_LIVE_DAILY_TASK_SMOKE=1`;
- explicit `PNC_LIVE_SMOKE_ACCOUNT`;
- explicit `PNC_LIVE_DAILY_TASK_SMOKE_CASTLE_REF`;
- explicit `PNC_LIVE_DAILY_TASK_SMOKE_SCRIPT`; and
- explicit mutation acknowledgement for smokes that spend, battle, claim, donate, enhance, wish, summon, or dispatch.

Example shape after exact aliases exist:

```powershell
$env:PNC_RUN_LIVE_DAILY_TASK_SMOKE="1"
$env:PNC_LIVE_SMOKE_ACCOUNT="mega_old_acc"
$env:PNC_LIVE_DAILY_TASK_SMOKE_CASTLE_REF="npc_2"
$env:PNC_LIVE_DAILY_TASK_SMOKE_SCRIPT="scripts/smoke/daily/<feature>.yaml"
py -m unittest tests.test_live_daily_task_smoke

$env:PNC_LIVE_SMOKE_ACCOUNT="serious_stuff"
$env:PNC_LIVE_DAILY_TASK_SMOKE_CASTLE_REF="free_cookies"
py -m unittest tests.test_live_daily_task_smoke
```

The implementation must not assume these alias strings until the refreshed roster and local config confirm them. The smoke verifies ADB reaches the resolved instance, observes exact castle identity, and aborts before task action if identity differs.

## Promotion Gates

A capability may enter `scripts/routines/daily_castle_maintenance.yaml` only when:

1. focused offline tests pass;
2. the full offline suite passes after shared-runtime changes;
3. selector validation passes when selectors/navigation changed;
4. NPC 2 live smoke passes or records an approved typed applicability skip;
5. free cookies live smoke passes or records an approved typed applicability skip;
6. all known screens in that workflow are typed;
7. no forbidden adjacent action occurred;
8. artifacts and mutation receipt were inspected; and
9. every live-discovered bug has an offline regression test where practical.

Additional global gates before the disabled scheduled task is considered ready:

- NPC 2 Arena audit is 7/7 consecutive entries. The current 2026-09-01 through 2026-09-07 streak is 1/7; six remain.
- Farm output-boost UI is observed and typed on the repaired route.
- Exact NPC 2 and free-cookies castle aliases are refreshed and reviewed.
- The complete target matrix has no blank or `blocked` cell for an enabled capability.
- A composed manual run completes both instances with castles sequential per instance.
- Password/background Task Scheduler execution reaches typed Home and writes artifacts for both workers.
- No-catch-up and no-overlap settings are inspected from the registered disabled task.
- Scheduler remains disabled until the user explicitly promotes it.

## Data, Config, and Migration Notes

- Preserve the user's dirty worktree. Reconcile overlapping files rather than reverting them.
- Replace the current building-only daily routine; do not retain it as a compatibility path.
- Remove the deleted/obsolete `multi_castle_daily_maintenance.yaml` path and document one canonical routine plus invocation-time target binding.
- Update the live-smoke default away from building upgrade; require explicit feature and target.
- Rename Tower Shop symbols, config values, selectors, artifacts labels where authored, and tests to Trial Shop. Do not add an alias.
- Migrate Campaign and Gathering policy schemas in one step with strict validation. Authored scripts using obsolete fields must be updated; no dual parser.
- Store run journals and summaries under `artifacts/<date>/<account>/<castle>/daily-maintenance/`; do not store secrets.
- Keep real `accounts.yaml`, `castles.yaml`, `castle_targets.yaml`, and new local daily config out of plan-generated overwrites. Changes require exact diff review.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Game adds a new startup popup | Generic visual-X search is bootstrap-only, freshly fingerprinted, one-tap, and followed by typed Home validation; no X means bounded failure. |
| OCR misreads a task title | Two stable observations, exact alias catalog, one semantic reread, then skip/report. OCR never controls coordinates. |
| Dynamic rows move after completion | Reopen/rescan Daily after each task and reselect by semantic ID plus fresh geometry. |
| Retry duplicates a purchase or battle | Durable mutation receipts and task progress are written before advancing; restart resumes unfinished work only. |
| Low-level castle lacks a feature | Typed applicability predicate and live skip on free cookies; no blind substitute action. |
| Background Task Scheduler cannot drive BlueStacks | Treat password-logon launch as a hard disabled-task promotion gate; do not change selected policy silently. |
| Parallel instances cross-wire ADB or artifacts | Resolve configured endpoints per account, verify identity before action, isolate sessions/journals/artifact roots, and never hard-code ports. |
| Premium currency is spent unexpectedly | Typed caps/prohibitions, selector allowlists, exact mutation count, and pre-mutation observation. |
| Campaign/gathering implementation diverges from direct tasks | Extract/reuse canonical executor and extend existing task ownership; remove old behavior rather than wrap it. |
| Week-long UI variability is not sampled | Keep Arena 7-entry and startup-popup audit as explicit global promotion gates with dated evidence. |

## Open Questions

No design question blocks implementation. The following are evidence/configuration gates, not choices to guess:

- Exact refreshed kingdom and alias records for NPC 2 and free cookies.
- The remaining six NPC 2 Arena audit entries due on 2026-09-02 through 2026-09-07 America/Toronto.
- Farm's actual boost UI after selector repair.
- VIP Login/Daily Reset popup occurrence during the audit window.
- Whether password/background Task Scheduler execution can operate BlueStacks on this Windows installation.

If any of these produces an unknown screen during an interactive smoke, pause and ask for classification as required. During unattended validation, use the bounded three-restart policy and preserve pending-clarification evidence.

## Execution Checklist

- [ ] Reconcile the dirty worktree and preserve current user changes.
- [ ] Establish deterministic/live fixture manifest from planning artifacts.
- [ ] Refresh and review exact NPC 2/free-cookies target aliases.
- [ ] Implement and validate typed daily config.
- [ ] Implement Phase 1 classification, bootstrap-X, and stable Daily scan.
- [ ] Implement Phase 2 coordinator, journal, and unknown recovery.
- [ ] Promote each Phase 3 capability individually through both target cells.
- [ ] Complete the NPC 2 Arena audit and promote Arena.
- [ ] Promote Campaign, Land of Trial, and Lost Land independently.
- [ ] Promote each resource gathering type and alliance mine independently.
- [ ] Repair Farm and promote each building boost independently.
- [ ] Compose only promoted tasks into the canonical routine.
- [ ] Validate full offline suite and selector tooling.
- [ ] Run the composed two-instance manual smoke.
- [ ] Register and inspect the disabled 02:00 Task Scheduler task.
- [ ] Prove password/background launch, no overlap, no catch-up, exit propagation, and artifacts.
- [ ] Present the final matrix and blockers; enable scheduling only on explicit user instruction.
