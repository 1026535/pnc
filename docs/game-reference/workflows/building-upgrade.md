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

No production changes or new tests were made for this note. Use the repository test runner for future implementation changes, and the existing live workflow only when offline evidence cannot establish the changed boundary.

## Still unverified

Server-side prerequisites and spending rules; complete cost formulas; all queue-status meanings; response timing across live states; downloaded script overrides; and direct-call authentication/acceptance. Extend this note when scoped work establishes those facts, with dated evidence rather than assumed coverage.
