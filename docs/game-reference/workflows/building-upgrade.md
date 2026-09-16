# Normal building upgrade

**Build:** [PNC 5.0.203 / 233](../PROVENANCE.md). **Evidence:** client source verified; automation correspondence inspected. No live upgrade performed for this reference.

Scope: normal upgrade initiation and its response handler. Instant completion, purchases, resource-item use, construction, and cancellation are separate paths; the existence of their code does not authorize their execution.

All Lua paths below are relative to the recovered `gameplay-lua/` source root. Symbols are primary anchors; line numbers refer to the recorded extraction.

## UI decisions before sending

Source: `uis/building/buildingupgradewin.lua`, `OnUpgradeHandler` at line 629 and `CheckResIsEnough` at line 592.

1. Checks prerequisites for the target level through `BuildingData:CheckBuildPreconditionIsPass`.
2. Checks resource costs. The cost check applies `GameBuffManager:GetItemConsume` to item costs and `GetUpgradeBuildCost` to other resources. Insufficient resources divert to `ItemData:ResFaseUse` and return without the normal-upgrade send.
3. Checks the available building queue through `GetIdelCoolStatusType(realTime)`. Observed branches: 2/4 show queue-full feedback; 3 opens a queue gift UI; 5 opens a third-queue gift UI. These are branch observations, not a complete definition of queue eligibility.
4. For the configured castle-level notice threshold, opens confirmation and sends from its callback. Otherwise closes the window and calls `BuildingSend.UpgradeBuilding(self.buildDto.id, 0)` at line 717.

**Implications:** base resource tables alone do not establish the displayed payable cost; modifiers matter. Queue-full and gift/purchase prompts are distinct from an accepted upgrade. A window can close before server acceptance, so closing it is not success evidence. The threshold is configured through `GameRuleType.CASTLE_LVUP_NOTICE`; do not invent a fixed level from this handler.

## Request and identity

Source: `commands/building/buildingcommand.lua`, `BuildingSend.UpgradeBuilding` at line 326; `commands/destination.lua` at line 18.

| Item | Verified value/meaning |
|---|---|
| Destination | `Destination.BUILDING = 4` |
| Command | `BuildingCmd.UPGRADE_BUILDING = 4` |
| Payload | `id`, `queueId` |
| UI caller | Passes `buildDto.id` and queueId `0` |
| Bridge options | clientData nil, showLoading true, duration 0 |

`id` comes from the selected building DTO; it is not established as interchangeable with `buildingId` (type/catalog identity) or `positionId`. The observed zero queue argument is not proof of which physical queue the server selects. Transport and local-context semantics belong to [the shared request path](../REQUEST_PATH.md).

## Response and state updates

Source: `commands/building/buildingcommand.lua`, `command.UpgradeBuilding` at line 744, registered at line 1327.

The handler gates processing through `command:FlyErrorCode(result.result, true)`. On that branch it consumes `result.content`, `result.queue`, `result.buildingDto`, and `result.coolQueueDto`; updates building and queue data; and dispatches building/UI events. It has a branch for a response building level older than the current local level. Do not infer numeric success/error codes solely from this call or remove the branch based on a simple happy-path reading.

The `UPGRADE_BUILDING` event is dispatched by both normal-upgrade and fast-upgrade handlers (normal at line 771, fast handler later in the same file). Its name alone does not prove that construction finished. Normal initiation and completed level advancement require different observations.

`BuildingSend.GetBuildingInfo` at line 285 is a source entry point for the building snapshot request (command 1), not a tool agents may silently execute. Its handler `command.GetBuildingInfo` at line 630 updates building, queue, cooldown, and area data. It is useful for understanding state ownership; no direct invocation was validated.

## Correspondence with this repository

| Owner | Existing behavior / relevant inspection |
|---|---|
| [building_upgrade_task.py](../../../pnc_automation/app/automation/tasks/building_upgrade_task.py) | `_verify_started_upgrade_at_home_city`: active-build observation, queue inspection, then target-level fallback. `_verify_started_upgrade_from_build_queue`: timer proof or level-verification follow-up. `_home_city_pending_target_level_increased`: compares the selected pending target with its baseline. |
| [building_workflow_support.py](../../../pnc_automation/app/automation/tasks/building_workflow_support.py) | Shared queue/timer observation helpers; use the canonical owner rather than duplicate UI interpretation. |
| [confirmation tests](../../../tests/unit/app/automation/tasks/test_building_upgrade_confirmation.py) | Final confirmation behavior |
| [completion tests](../../../tests/unit/app/automation/tasks/test_building_upgrade_completion.py) | Upgrade success observations |
| [active queue tests](../../../tests/unit/app/automation/tasks/test_building_upgrade_active_queue.py) | Existing construction/queue behavior |
| [prerequisite tests](../../../tests/unit/app/automation/tasks/test_building_upgrade_prerequisites.py) | Dependency handling |

The existing timer/level checks address the distinction between a UI click and an observed outcome. This correspondence is not a full code review or proof that every timer belongs to the requested target. When changing these paths, preserve target identity and a pre-action baseline, distinguish a pre-existing queue from the newly requested operation, and verify initiation versus completion according to the task contract.

The original source inventory made no production changes. The recognition continuation below adds a captured regression; it does not implement upgrade navigation or spending.

## Prerequisite Go versus equipment Go — September 13, 2026

Source inspected offline in the same recorded build: `uis/building/sub/upinfo_conditionitem.lua`, `UpInfo_ConditionItem:SetPrevBuildingInfo` (line 83) and `OnButtonClickHandler` (line 189); `uis/building/buildingupgradewin.lua`, `GetConditionBarList` (line 432); and `uis/building/sub/upinfo_suittipitem.lua`, `UpInfo_SuitTipItem.OnGotoJumpHandler` (line 96). Confidence: verified packaged client behavior, corroborated by the saved Institute upgrade capture `capture_gap_exploration/20260913T030954Z/0055_institute_upgrade_blocked_settled.png`.

A satisfied building prerequisite hides both its error icon and button. An unmet building prerequisite displays a red description, error icon, and Go button. Queue-condition rows use the same component but have separate Speed/Free/Help behavior. The equipment suggestion uses a different component: its Go opens gift window 1013 for tip type 3, or the Lord window otherwise. Thus the visible word Go alone cannot establish a prerequisite action.

Automation implication: the captured Institute profile owns only the measured Go aligned with `Castle: Lv.23`; removing that control must suppress the unmet-prerequisite fact/action even when the lower Builder Set Go survives. The normal and instant Upgrade labels turn red when prerequisites fail (`buildingupgradewin.lua`, line 334); neither button is qualified by this profile. `tests/integration/vision/test_institute_prerequisite_captured.py` checks this distinction through both publication paths. Source and pixels establish these UI distinctions, not server eligibility, purchase success, or authorization to invoke the handlers.

## Primary-panel Upgrade versus upgrade-panel Upgrade — September 16, 2026

Evidence: saved captures `tests/data/screen_recognition/building_variants/farm_level_one_detail.png` (Farm primary stats panel), `farm_upgrade_available.png` (Farm upgrade detail), `institute_upgrade_blocked.png` (Institute upgrade detail), and `building_routes/blacksmith_reference_20260914.png` (named primary); corroborated by packaged client source `uis/building/buildingtopitem.lua:OnBtnMainHandler` (normal status activates the internal UpgradeItem) and `uis/building/buildingupgradewin.lua:OnUpgradeHandler`. Confidence: artifact-observed plus source-corroborated; no live tap performed.

The primary stats panel's Upgrade opens the building's internal upgrade detail; it is a navigation entry and never spends. The upgrade detail's own ordinary Upgrade is the mutation surface. Observation publishes these as two distinct controls: `PNC_BUILDING_DETAILS_UPGRADE_BUTTON` (entry, primary phase only) and `PNC_BUILDING_UPGRADE_BUTTON` (mutation, proved UPGRADE phase only). Both phases require positive owned evidence — upgrade section headers or the accepted upgrade-detail layout, the primary-only `Overall Hourly Output` stats label on the shared detail, or at least two measured Institute category controls — and a frame whose phase stays unproved advertises neither generic control. Named primaries keep their own entry selectors (`PNC_<X>_UPGRADE_BUTTON`) while their phase is unproved; a proved UPGRADE frame never advertises an entry selector.

Automation implication: the replacement navigation opens the internal upgrade detail through `NavigationCore.open_building_upgrade_detail` — at most one phase-owned entry tap, then a fresh CLEAR same-building UPGRADE detail is required (same ScreenType alone is insufficient). CoreDailyMutation requires the matching, fresh, CLEAR, typed UPGRADE phase plus the measured ordinary Upgrade before spending; a primary menu button cannot satisfy that boundary. The blocked Institute detail proves UPGRADE phase but publishes no mutation surface — its red Upgrade is ineligible, so only the row-owned prerequisite Go is actionable there.

Unsupported separate layouts: named-primary upgrade-detail surfaces other than Institute (`institute_upgrade_detail`) and the Farm generic detail (`building_detail_farm`) are not yet qualified — their destinations keep phase unproved and stop before any entry tap. Captured confirmation/speedup states beyond the already-qualified shield warning remain unsupported; premium Upgrade Now bounds are read-only facts, not actions.

## Lead live qualification — September 16, 2026

Source: canonical core runtime `20260916T143209Z_04a4d567`, configured `mega_old_acc` active castle, native900×1600 captures under the V16 checkout's `.local-data/devin-v16/live_accepted_candidate/`. Confidence: live-observed; build identifier unavailable. The non-spending route returned Home after Institute PRIMARY → UPGRADE → PRIMARY and after Build Queue inspection. Final Home frame0049 was captured14:34:47UTC; the lease was released and the existing instance preserved.

The Institute's upgrade panel showed22/45, CastleLv23 with a distinct measured prerequisite Go, original4d08:36:48 versus actual2d17:10:46, premium19,761, and four material rows. OCR can damage one amount's comma grouping: preserve the readable half and leave the damaged amount unknown. Resource identities from those icons remain unqualified. No Upgrade, Upgrade Now, Go, Activate or purchase action was used.

Back from the internal upgrade panel returns the Institute's primary panel, with the same ScreenType. `close_building_upgrade_detail` proves the same-building PRIMARY phase before the existing Home route proceeds; `WorkflowContext.navigate` performs this close for an observed Institute upgrade panel. Other buildings' internal return layouts still need their own evidence. Build Queue's first slot was idle and second slot inactive; the existing producer proves the first-slot idle fact. Its close is a measured task-owned control, so automatic transient-popup recovery must not dismiss this inspection surface.

The prerequisite target text may remain a descriptive fact when its measured Go is absent. Its absence suppresses prerequisite actionability; neither OCR Go nor the lower equipment Go can replace that row's control.

## Still unverified

Server-side prerequisites and spending rules; complete cost formulas; all queue-status meanings; response timing across live states; downloaded script overrides; and direct-call authentication/acceptance. Extend this note when scoped work establishes those facts, with dated evidence rather than assumed coverage.
