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
