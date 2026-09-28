# Home-city building endpoints

**Build:** [PNC 5.0.203 / 233](../PROVENANCE.md). **Evidence:** client source verified and selectively compared with September 14, 2026 live captures. No direct game-service call was made.

Scope: the client-side window selected after a Home-city building object is opened. These mappings identify candidate UI destinations; they do not prove that a building exists, is unlocked, or is safe to mutate on a current account.

## Client route owner

Source: `scenes/cityscene/vo/buildtabledata.lua`, `BuildTableData:OpenBuildWin`, `BuildTableData:_OpenBuildWinImpl`, and `BuildTableData:BuildTypeIdToWinPrefabType`; identifiers come from `scenes/cityscene/types/buildidtype.lua`.

`_OpenBuildWinImpl` is the common dispatcher for a selected building DTO. Relevant verified branches include:

| Client building type | Client destination | Automation implication |
| --- | --- | --- |
| `WALLID` (1002) | `CitywallSend.RequireGetCityWallInfo(buildDto)` before the Wall UI | A current Wall destination must be observed after the response; the object tap alone is not success. |
| `WATCHTOWERID` (1006) | `TOWER_WIN` | Qualify the Watchtower window and its own Back edge. |
| `CONSTRUCTIONID` (1008) | `EQUIP_ENTER_WIN` | This is the Blacksmith-family endpoint, not the construction-slot menu. |
| `FAIRID` (1009) | `FAIR_WIN` | This is the Market-family endpoint. |
| `EMBASSYID` (1010) | `EMBASSY_WIN` | This is the Alliance Hall endpoint. |
| `WARID` (1011) | `WAR_HALL_WIN` | This corresponds to the live-qualified Hall of War screen. |
| `CAMP_BUBING`, `CAMP_QIBING`, `CAMP_GONGBING`, `CAMP_CHEBING` (1020-1023) | `CAMP_PANEL` | The four barracks share a prefab family but still require exact Home identity and typed screen ownership. |
| `TRAP` (1025) | `TROP_WIN` | This is the Trap Workshop endpoint. |
| `BANK` (5001) | `TREASURE_CAVE_WIN` | Bank requires a new current Treasure Cave screen identity before catalog promotion. |
| `REMAINS` (5003) | `DRAGON_CAVE_MAIN_WIN` | Dragondom Conquest requires a new current Dragon Cave screen identity before catalog promotion. |
| `MINE_HOLE` (5009) | `MineWarData:sendOpenMineMainWin()` | Pit is a mine-war/Rare Earth entry and is not an upgradeable building. |
| `ARENA_BUILD` (5010) | `ARENA_ENTER_HUB` | The live destination is the Versus Center with Arena selected. |
| `BUILD_ENTER_15` (5015) | `WATER_FLOWER_WIN` | This corresponds to the Sacred Tree-family window. |

Prefab declarations are corroborated by `uis/winsprefabtype.lua`; window identifiers are in `uis/wintype.lua`. `uis/arenaactivity/arenaenterhubwin.lua:StartWindow` returns `WinType.ARENA_ENTER_HUB`. `uis/treasurecave/treasurecavewin.lua:StartWindow` returns `WinType.TREASURE_CAVE_WIN`, and `uis/dragoncave/view/dragoncavemainwin.lua:StartWindow` returns `WinType.DRAGON_CAVE_MAIN_WIN`.

## Live correspondence

- **Live observed, 2026-09-14:** Hall of War opened to the typed Hall of War layout and returned through its measured Back control.
- **Live observed, 2026-09-14:** Sacred Tree opened to the typed Sacred Tree layout and returned through its measured Back control.
- **Live observed, 2026-09-14:** Arena opened to a screen titled `Versus Center` with the `Arena` tab selected, matching `ARENA_ENTER_HUB`. A second live capture group independently reproduced that screen and consumed its measured Back control to Home; that group's later roster scan did not rediscover the active row, so it is visual/return evidence rather than a fresh full identity acceptance.
- **Live observed, 2026-09-14:** Blacksmith was reacquired from Home and opened to the Blacksmith gear hub, matching `EQUIP_ENTER_WIN`. The destination exposes Blacksmith's own Upgrade and gear-category controls. A later independent run was blocked before route acquisition by an unqualified VIP daily-reset foreground modal, so Blacksmith's return edge remains unaccepted.
- **Live observed, 2026-09-14:** Pit was published as `home_city_object_id=pit` with `upgradeable=false`. Its action point remained outside the reviewed HUD-safe band, so no Pit tap was sent.

## Remaining uncertainty

The recovered source does not prove current downloaded-script overrides, server unlock rules, current text/layout, or return behavior. Bank and Dragondom remain unpromoted until independent live captures establish their current screen identities and measured return controls. Blacksmith remains without a reviewed return until a second exact live group can run after the generic VIP foreground identity is qualified. Shared-prefab branches do not collapse exact building identity or authorize upgrade actions.

## V44 capture constraints — source recheck September 28, 2026

These findings are **repository-proven for the recovered 5.0.203 / 233 client,
high confidence**. They were rechecked offline against the accepted APK evidence
root; they are not new observations of the installed game. The live correspondence
and uncertainty above describe the September 14 checkpoint. Later V44 route
acceptance is recorded in the coordinator's revision-bound evidence ledger.

### Asset identity and occupied slots

`scenes/cityscene/buildpositionitem.lua:64-82` obtains the current building DTO
for a position before selecting its visible building. `LoadBuildingSkin` at
lines 108-122 resolves the type through
`scenes/cityscene/types/cityresourcepath.lua:GetBuildPrefabPath`, which maps to
`Scenes/CityScene/builds_F/<type>.prefab`. The lookup establishes a useful semantic
asset binding; it does not establish the current occupant from slot eligibility.
The position table's inherited defaults must be applied when reading its rows.

Use the extracted layout to plan relative movement and prefab identities to
organize capture groups. Neither supplies current native body pixels, an interior
tap region, visual availability, nor proof that all level/skin variants look
equivalent. New body bindings still need a native source view and a distinct
holdout; automatic input retains the shared current-frame body/slot contract.

### Warehouse body entry

`buildings/items/builditem_1005.lua:OnMouseClick` delegates to
`buildings/components/buildclickcomponent.lua:ClickHandler`. With a current DTO,
that component calls `BuildTableData:OpenBuildWin`; the `CELLARID` branch in
`vo/buildtabledata.lua:153-154` opens `CELLAR_WIN`. This is a candidate Warehouse
entry chain. Native body identity, current destination layout and return still
require observation before a new automatic acquisition is accepted.

### Bank can have an intermediate Home menu

`buildings/items/builditem_5001.lua:OnMouseClick` checks unlock conditions first.
Below the auction-house opening level it directly calls the Bank dispatcher.
Otherwise a body click toggles the on-city menu; `Btn1` calls the Bank dispatcher
and `Btn2` opens `AUCTION_HOUSE_WIN`. The Bank dispatcher maps to
`TREASURE_CAVE_WIN` in `vo/buildtabledata.lua:198-199`.

A Home frame immediately after the body tap therefore need not mean that the
tap failed. Capture the intermediate menu when present, positively identify the
visible Bank entry control, then observe the actual destination and return.
Do not infer a production screen identity, button coordinates or current unlock
level from these symbols. Do not enter the auction branch to qualify Bank.

### Resource body taps may collect before opening

The body handlers for client types 1015, 1016, 1017 and 1019 first check
`GetHasResPop()`. When true they call `OnNormalResourcePopClick(buildDto.id)` and
return before the ordinary building-window dispatcher. For example,
`buildings/items/builditem_1016.lua:136-152` contains this branch. These types map
to Gold Mine, Farm, Lumber Camp and Iron Mine in the canonical slot catalog.
Moon Well (1027) has the same collection branch with an additional capacity check
at `builditem_1027.lua:136-156`.

Choosing a body point away from the bubble does not by itself make these taps
non-claiming. Under a no-claim live assignment, capture the body passively and
qualify a current non-collecting entry state before tapping. A visible harvest
state leaves that entry case pending unless collection is separately authorized;
it is neither unavailable nor a passed route. This source rule does not authorize
collecting, upgrading or spending to create a test precondition.
