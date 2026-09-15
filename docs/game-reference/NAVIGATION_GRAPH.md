# Client Navigation Graph

Offline reference for how Puzzles & Conquest menus connect: which screen opens
which, how scenes switch, and what "back" actually does.

Everything below is **client-source-verified** against the recovered Lua of
build `com.global.tmslg` 5.0.203 (code 233) described in
[PROVENANCE.md](PROVENANCE.md), unless a line is explicitly marked as inferred.
This is a *static* graph: it records the call sites that exist in the source, not
a recording of a live session. See [Limitations](#limitations).

Do not confuse this with `reviewed_navigation_edges()` in
`pnc_automation/app/automation/engine/navigation_core.py`. That is the small,
live-observed, selector-backed edge set the automation runtime actually drives.
This document is the much broader source-derived superset used for consultation.

## Regenerating

```bash
py tools/build_client_navigation_graph.py \
  --source .local-data/apk-exploration/gameplay-lua \
  --output .local-data/apk-exploration/navigation-graph.json
```

The recovered Lua root and the generated JSON both live under ignored
`.local-data/`; neither is committed. Recover the Lua with the UnityPy procedure
in [PROVENANCE.md](PROVENANCE.md) first.

Coverage reported by the current run:

| Metric | Count |
| --- | --- |
| Lua modules scanned | 6,276 |
| Registered windows (`WinsPreFabType`) | 1,965 |
| Windows resolved to an implementing Lua module | 1,598 |
| Window call-site edges (open + close) | 5,326 |
| Scene load edges | 105 |
| Targets referenced but never registered | 63 |
| `OpenWin` call sites with a non-constant target | 147 |

## Architecture

Navigation happens on two independent levels.

**Scenes** are Unity scenes swapped through
`GameLevelManager:LoadLevel(SceneName.X, ...)`. Only one is loaded at a time, so
a scene load tears down whatever was on screen. The names are declared in
`scenename.lua` (24 of them).

**Windows** are UI prefabs stacked *inside* the current scene through
`WinsManager.instance:OpenWin(WinsPreFabType.X, LayerManager.instance.<LAYER>, param)`.
`WinsPreFabType` (`uis/winsprefabtype.lua`) maps a symbolic window name to a
prefab path; the Lua module implementing a window is normally the file named
after that prefab, which is how this graph links a window to the edges it emits.

Windows are placed on a named layer, and the layer determines stacking and how
bulk-close behaves:

| Layer | `OpenWin` sites | Role |
| --- | --- | --- |
| `UI` | 3,289 | Ordinary full-screen/menu windows. The main navigable layer. |
| `TOP_UI` | 512 | Modals and sub-dialogs drawn above `UI`. |
| `TIPS` | 139 | Tooltips, confirmations, flyouts. |
| `EFFECT` | 25 | Reward/fly animations (e.g. `COMMON_FLY_REWARD_WIN`). |
| `MENU` | 21 | Persistent scene chrome — notably the `MAIN` HUD. |
| `SCENE` | 21 | Scene-bound overlays. |
| `LOADING` / `HUD` | 6 | Loading covers and a couple of wall-defence panels. |

`UI` and `TOP_UI` are the two layers treated as "the menu stack":
`WinsOpenManager:CloseUIWinList()` closes exactly those two and reports whether
anything was open.

## Back and close semantics

There is **no central back stack**. Back is a broadcast that each visible window
may claim, and the return destination is a callback the *opener* installed.

The Android back key resolves through `GameLuaMain` (`gameluamain.lua`). A chain
of interceptors runs first for active mini-games and battles (card PvP,
adventure sim, water-sort, insect farm, …); each either consumes the press or
falls through to:

```lua
GameLuaMain.OnBackWinList = function()
    WinsOpenManager:BackUIWinList();
    if (not WinsOpenManager.hasBackUIWinList) then
        PlatFormUtil.showExitDailog();
    end
    WinsOpenManager.hasBackUIWinList = false;
end
```

`WinsOpenManager:BackUIWinList()` broadcasts one event to every window:

```lua
WinsManager.instance:updateAllWin(GameEventType.BACK_TO_LAST_WIN, nil);
```

Windows built on `CommonFullScreenWin` (`uis/common/commonwin/commonfullscreenwin.lua`)
handle it in `GUpdateWins`: if the window is alive, active and shown, it sets the
global `WinsOpenManager.hasBackUIWinList = true` and calls `BackToLastWindow()`,
which closes itself and invokes the opener's callback:

```lua
function CommonFullScreenWin:BackToLastWindow(openParam)
    self.isBack = true;
    local state = self.isdestroy or false
    WinsManager.instance:CloseWin(self.winName, state, {back = true, reOpenParam = openParam});
    if self.backHandler ~= nil then
        self.backHandler(self.parameterback)
    end
end
```

Three consequences worth remembering when consulting this graph:

- **A parent edge only exists if the opener created one.** `backHandler` is set
  per call site via `SetBackHandler(callback, parameter)` (only 6 call sites in
  the whole client) or by passing `param.back` into `ShowWin`. Most windows
  therefore just close on back and reveal whatever was underneath, rather than
  re-opening a specific parent.
- **Back is claimed by any eligible window, not by the topmost one.** The
  broadcast reaches every window; `hasBackUIWinList` only records that *someone*
  handled it.
- **If nothing claims it, the game offers to quit** (`showExitDailog`). That is
  the observable signal that the UI stack is empty and you are at a scene root.

## Scene graph

`CITY_SCENE` (`CityScene/CityScene.unity`) and `WORLD_MAP`
(`WorldMap/WorldMapScene.unity`) are the two hubs. Every other scene is a
special-purpose battle/event scene that returns to the city.

| Scene | `LoadLevel` call sites |
| --- | --- |
| `CITY_SCENE` | 76 |
| `WORLD_MAP` | 17 |
| `TD_BATTLE_COPY_SCENE` | 3 |
| `ALLIANCE_PARTY_SCENE`, `ANSWER_SCENE`, `COPY_BATTLE_SCENE`, `COPY_PLAY_SCENE`, `GUIDE_WORLD_MAP`, `ICE_WAR_SCENE`, `OVERLORD_WAR_SCENE`, `RANCH_SCENE`, `UNION_WAR_SCENE` | 1 each |

The 76 `CITY_SCENE` loads are the "return home" edge, reached from the world
map, every event scene, the guide system, and each free-queue shortcut in
`uis/main/queue/*`.

### The city ↔ world toggle

Both directions are the same HUD button, in `MainBottomPanel:OnCityBtn`
(`uis/main/mainbottompanel.lua:601`):

```lua
if (self.isShowCityBtn) then
    GameLevelManager:LoadLevel(SceneName.CITY_SCENE, nil, nil, false, nil, nil);
else
    if (WinsManager.instance:isWindowShowing(WinsPreFabType.SERVER_LIST_VIEW)) then
        WinsManager.instance:CloseWin(WinsPreFabType.SERVER_LIST_VIEW, false);
    else
        WMEnterMapHandler:EnterMapAndForMyCastle()
    end
end
```

Going *to* the world map is therefore never a direct `LoadLevel` from the HUD —
it routes through `WMEnterMapHandler` (`scenes/worldmapext/handler/wmentermaphandler.lua`),
which gates on the tutorial (`GuideData.CheckCanEnterWorld()`) and castle state
(`self:CheckCastle()`) before loading `WORLD_MAP` centred on the player's castle.
Earlier guards in `OnCityBtn` divert the press entirely: in the mine-war zone
(`COPYZONESMAP_SIMPLE`) it closes the mine windows or shows a flyword and
triggers tutorial `56_0`; inside a puzzle dungeon it shows a flyword and
triggers `561_0`; during ice war it sends `IcewarSend.RequireLeft()`. None of
those reach a scene load.

`WMEnterMapHandler` is the canonical entry point for every world-map jump:
`EnterAssignMap`, `EnterMyMapAndMoveMap`, `EnterRoleMapAndMoveMap`,
`EnterWorldMapAndMoveMap`, `EnterMapAndMoveMap`, `EnterMapAndFocusInfo`,
`EnterMapAndForMyCastle`, `EnterOrMoveMapAndForMyCastle`, `EnterMapAndFocusArmy`,
`EnterBanquetMap`.

## Home city HUD (`MAIN`)

`CityScene` opens `WinsPreFabType.MAIN` on the `MENU` layer in both `scene:Init`
and `scene:ReEnter` (`scenes/cityscene/cityscene.lua`), so the HUD survives
window navigation and is re-created on every return to the city. It is split
into panels, each owning part of the navigation surface.

### Bottom bar — `uis/main/mainbottompanel.lua`

| Handler | Opens |
| --- | --- |
| `OnTaskBtn` | `TASK_WIN` |
| `OnMailBtn` | `MAIL_TYPE_LIST_WIN` |
| `OnPackBtn` | `BAG_WIN` |
| `OnHeroBtn` | `HERO_MAIN_WIN` |
| `OnGoldenEggIconBtn` | `CHAT_WIN` |
| `OnCityBtn` | city ↔ world scene toggle (above) |
| `OnUnionBtn` | `UnionData:OpenUnion()` (dynamic — see limitations) |

### Left bar — `uis/main/mainleftbottompanel.lua`

`OnMapBtn` is a dispatcher: it opens one of `DRAGON_ISLAND_MAP_WIN`,
`WILD_WAR_MAP_WIN`, `BONE_MAP_WIN`, `OverLORD_WAR_MAP_WIN`,
`DRAGON_ISLAND_LEAGUE_MAP_WIN`, `SEASONWAR_MAP_WIN` or `RESOURCE_MAP_WIN`
depending on the active event.

| Handler | Opens |
| --- | --- |
| `OnTowerBtn` | `RESOURCE_SEARCH_WIN` (also loads `CITY_SCENE` first when on the world map) |
| `OnInformationBtn` | `INFORMATION_WIN` |
| `OnChapterTaskBtnClick` | `CHAPTER_TASK_WIN` |
| `OnNewPrivateChatHandler` | `PRIVATE_CHAT_LIST_WIN`, `MAIL_LIST_WIN` |
| `OnFriendChatIconHandler` | `FRIEND_CHAT_LIST_WIN` |
| `OnSeasonActBtnBgClick` | `SEASONWAR_PASS_WIN` |
| `OnWarGodTaskBtnHandler` | `WAR_GOD_TASK_MAIN_WIN` |

### More menu — `uis/main/mainmoreitem.lua`

A single `onClick` switch over the menu entry id:

| Opens |
| --- |
| `SETTING_WIN` |
| `LOCAL_SERVER_RANK` |
| `CHAR_SETTING_WIN` |
| `FRIEND_MEMBER_WIN` |
| `WonderfulInformationWin` (`OnBtnSecretaryClick`) |

### Right side — gifts, shop, events

`uis/main/mainrighttoppanel.lua` and `mainrighttopbuttonitem.lua` drive the
monetisation/event rail: `NEW_GIFT_WIN`, `WEEK_CARDS_WIN`,
`FAST_GIFT_NORMAL_WIN`, `BUILDING_QUEUE_GIFT_WIN`, `BUY_GIFT_WIN`,
`WELFARE_CENTER_WIN`, `WELFARE_CENTER_GIFT_WIN`, `CHOOSE_GIFT_WIN`,
`MULT_FIRST_PAY_WIN`, `KING_RETURN_WIN`, `SVIP_VIEW`, `DAILY_CHARGE_VIEW`,
`TRANSFER_AREA_WIN`, `FIRST_CHARGE_ACT_WIN`, `ACT_LORD_GIFT_BOX_WIN`,
`MAIN_RIGHT_GIFT_WIN`. `mainrightcenterpanel.lua:OnTIZHIBtnClick` opens
`COPY_PLAY_MAIN_WIN`.

### World-map HUD — `uis/main/mainfindpanel.lua`

| Handler | Opens |
| --- | --- |
| `OnFavoriteBtn` | `WORLD_MAP_BOOKMARK_WIN` |
| `OnFindBoxBtn` | `WORLD_MAP_SEARCH_WIN` |
| `OnKingWarTransferBtnlick` | `WORLD_MAP_RANDOM_TRANSFER_WIN` |
| `DragonInvadeBtnlick` | `DRAGON_INVADE_MONSTER_COORD_WIN` |

`uis/main/activityenter.lua:OnBtnAGuoWan` opens `ACTIVITY_CENTER`, the hub whose
`uis/activity/activitycenteritem.lua` fans out to 72 event windows — the single
largest branch point in the client.

## City scene: buildings

Tapping a building goes through `BuildTableData:_OpenBuildWinImpl`
(`scenes/cityscene/vo/buildtabledata.lua`), a switch on `BuildIdType`:

| Building (`BuildIdType`) | Opens |
| --- | --- |
| `CASTLEID` | `CASTLE_BUILD_WIN` |
| `WALLID` | *no window* — sends `CitywallSend.RequireGetCityWallInfo`, server-driven |
| `CAMPID` | `TRAININGCAMP_BUILD_WIN` |
| `INFIRMARYID` | `INFIRMARY_WIN2` |
| `CELLARID` | `CELLAR_WIN` |
| `WATCHTOWERID` | `TOWER_WIN` |
| `COLLEGEID` | `COLLEGE_PANEL` |
| `CONSTRUCTIONID` | `EQUIP_ENTER_WIN` |
| `FAIRID` | `FAIR_WIN` |
| `EMBASSYID` | `EMBASSY_WIN` |
| `WARID` | `WAR_HALL_WIN` |
| `MERCHANTMANID` | `ACTIVITY_SHOP_POOL_WIN` (merchant-ship shop id) |
| `MANORID`, `FARMID`, `LOGGINGID`, `PITID`, `SOUL_MINE` | `RES_BUILD_WIN` |
| `CAMP_BUBING`, `CAMP_QIBING`, `CAMP_GONGBING`, `CAMP_CHEBING` | `CAMP_PANEL` |
| `TREVI_FOUNTAIN` | `TREVI_FOUNTAIN_WIN` |
| `TRAP` | `TROP_WIN` |
| `BANK` | `TREASURE_CAVE_WIN` |
| `REMAINS` | `DRAGON_CAVE_MAIN_WIN` |
| `PUB` | `Pub_Main_View` |
| `MINE_HOLE` | *no window* — `MineWarData:sendOpenMineMainWin()`, server-driven |
| `ARENA_BUILD` | `ARENA_ENTER_HUB` |
| `BUILD_ENTER_15` | `WATER_FLOWER_WIN` |
| `VALKYRIE`, `TREASURE` | empty branch — tap does nothing |

`BuildingMenuBarData:MenuOptionById` (`scenes/cityscene/vo/buildingmenubardata.lua`)
handles the radial menu that some buildings show instead, and resolves newer UI
variants at runtime (`CASTLE_BUILD_MSG_NEW_WIN` vs `CASTLE_BUILD_MSG_WIN`,
`WALL_MSG_WIN_NEWUI` vs `WALL_MSG_WIN`, `INFIRMARY_WIN` vs `INFIRMARY_WIN2`,
`Pub_Main_View1` vs `Pub_Main_View`). Individual
`scenes/cityscene/buildings/items/builditem_*.lua` files override the tap for
specific buildings — e.g. `builditem_1029` → `TANK_MAIN_WIN`, `builditem_5001` →
`AUCTION_HOUSE_WIN`, `builditem_5014` → `InsectFarmMainWin`, and
`emptybuildingitem.lua` → `SELECT_CREATE_BUILDING`.

## Querying the generated graph

`navigation-graph.json` holds the full edge list; the tables above are only the
hubs. Its shape:

- `scenes` — `SceneName` → Unity scene path.
- `windows[]` — `{name, prefab, module, group, declared_in}`.
- `window_edges[]` — `{source_module, source_group, source_windows, function,
  line, kind, target, layer}`, one entry per call site. `kind` is one of
  `OpenWin`, `RealyOpenWin`, `ShowWin` (traversal) or `CloseWin`,
  `RealyCloseWin`, `HideWin` (dismissal).
- `scene_edges[]` — the same shape for `LoadLevel` call sites.
- `group_graph` — call sites aggregated to `uis/<area>` groups, with `opens` and
  `closes` target groups ordered by frequency. Use this for an overview; use
  `window_edges` when you need the exact file and line.

What opens a given window:

```bash
py - <<'PY'
import json
from pathlib import Path
graph = json.loads(Path(".local-data/apk-exploration/navigation-graph.json").read_text())
for edge in graph["window_edges"]:
    if edge["target"] == "BAG_WIN" and edge["kind"] == "OpenWin":
        print(f'{edge["source_module"]}:{edge["line"]} {edge["function"]}')
PY
```

Swap the condition to `edge["source_module"].startswith("uis/mail")` to list
everything an area opens instead.

## Limitations

Read these before treating an edge as a user-visible transition.

- **A call site is not a menu link.** The 5,326 edges include modals, tooltips,
  reward popups, speed-up prompts and internal/conditional UI alongside real
  navigation. Most are guarded by conditions this static pass does not evaluate.
- **147 `OpenWin` call sites have a non-constant target** and are absent from the
  graph. Two patterns dominate: table lookup (`WinsPreFabType[otherwintype]` in
  `datas/activitydata.lua`) and name concatenation
  (`WinsPreFabType["LOGIN_ACTIVITY_REWARD_WIN_" .. lo.windowId]`). Event and
  turntable windows are systematically under-represented as a result. Indirect
  entry points that wrap navigation in a data-layer call — `UnionData:OpenUnion()`,
  `MineWarData:sendOpenMineMainWin()` — are likewise invisible.
- **63 referenced window names are never registered**, e.g. `BUILDING_UP_WIN`
  (opened at `scenes/cityscene/vo/buildingmenubardata.lua:802`) and
  `ACTIVITY_LIMIT_CENTER_WIN`. `WinsPreFabType.X` resolves to `nil` for these, so
  the call sites appear to be dead paths left behind by removed content —
  *inferred*, not proven, since prefabs could in principle be registered natively.
- **One window is rebound at runtime**: `KING_SET_OPENLEVEL_PANEL` is assigned
  two different prefabs conditionally in `datas/transferapplydata.lua:194-196`.
  `declared_in` on each window records every declaring module.
- **Window-to-module resolution is name-based.** A window is linked to the Lua
  file matching its prefab basename, and only when that match is unambiguous;
  367 of 1,965 windows resolve to no module, so edges are attributed to the
  *emitting* module rather than always to a named source window.
- **Scene edges are call sites, not reachability.** 76 modules can load
  `CITY_SCENE`; that does not mean 76 distinct user-facing routes.
- **Build-locked.** Everything here describes 5.0.203. Window names and menu
  layout change between releases; re-run the generator against a fresh
  extraction rather than trusting this document for a newer client.
