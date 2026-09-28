---
name: pnc-building-upgrade-requirements
description: Answer Puzzles & Conquest building-upgrade requirement questions — costs, prerequisite gates, base/upgrade times, Castle ability gates, and what the upgrade UI actually displays — from recovered 5.0.203 APK evidence, read-only and build-scoped.
---

# PNC building-upgrade requirements

Evidence-backed lookup method for "what does upgrading building X to level Y require" questions. Everything below is verified against the recovered 5.0.203 (versionCode 233) client. Treat every claim as build-scoped; never present it as current live data.

## Evidence base

- Method conventions and evidence labels (`user-confirmed`, `repository-proven`, `artifact-observed`, `live-observed`, `inferred`, `unknown`): `.agents/skills/pnc-game-knowledge/SKILL.md`.
- Evidence map (accepted root, builds, index locations): `.agents/skills/pnc-game-knowledge/references/evidence-map.md`.
- Accepted build: `com.global.tmslg` 5.0.203, versionCode 233, `arm64-v8a`; acquired 2026-09-12, re-verified 2026-09-27.
- Recovered evidence root (machine-local, ignored, **read-only**): `C:\Users\lebel\pnc\.local-data\apk-exploration`. It is not part of the Git worktree and may be absent on other machines. If the root or a needed artifact is missing, report it inaccessible — do not roam elsewhere and do not substitute another build.
- Recovered Lua TextAssets (`assets/resourcesdata/luascript/**`, including every `GameData/basedb_*/...bytes` base-data asset) are stored XOR-encoded byte-by-byte with `0x2C`. Decoding yields UTF-8 Lua source. Decode **in memory only** — never write a decoded copy into the repo or evidence tree.
- Never conclude a base-data table is absent because grepping decoded Lua sources finds nothing: the `basedb` assets are opaque to text search until decoded. Resolve them through the inventory instead.

## The `BuildingUpgrade` asset

Inventory record in `<root>/lua-search/inventory.json` (top-level JSON array; resolve by `name`, never by a remembered offset):

```json
{
  "name": "BuildingUpgrade",
  "chunk": "assets/ABAsset.pkglzma_18",
  "offset": 9107651,
  "size": 303385,
  "sha256": "6d98058d29ff94f4097fd659fb3eeb6070ef7f62caa636418102135a3dc61272",
  "saved": "6d98058d29ff94f4097fd659fb3eeb6070ef7f62caa636418102135a3dc61272.bin"
}
```

`saved` is the file name under `lua-search/`. Always re-hash the file and compare to `sha256` — reuse a prior decode only if the hash still matches; chunk/offset/size can drift between snapshots.

### Decoded layout (verified for this record)

```lua
local __rt_1 = {count=1,id=12027001,type=9}          -- leaf shared sub-tables (~160 of them)
...
local __rt = createtable and createtable( 390, 0 ) or {}
__rt[1] = {count=-480,id=13005001,type=9}            -- composite shared sub-tables
__rt[2] = {...}
...
local BuildingUpgrade =
{["1"]={...},["2"]={...}, ..., ["1082"]={...}}       -- 1082 rows, keyed by STRING row id
local __default_values = {ability=144,ability2=150000,buildingIcon="ico_bubingying",buildingId=1001,cost=__rt[390],formulaId=1,id=1,level=1,mailId=0,preconditions=__rt_88,removeTime=1500,suitTipType=5,time=3000,upReward=__rt_73,upReward2=0,upgradeTips=""}
do
  local base = { __index = __default_values }
  for k, v in pairs( BuildingUpgrade ) do setmetatable( v, base ) end
end
local basedata = { data = BuildingUpgrade, len = 1082, key = "id", isNeedTransform = false, first = 1, excelName = "J建筑系统" }
return basedata
```

Consequences:

- The map key `["1001"]` is the **row `id`, not the building id**. Rows for one building share `buildingId` but have distinct `id`/`level`.
- Row fields that are absent resolve through `__default_values` via `__index`. Castle rows omit `buildingId` and inherit `1001`; a row that omits `preconditions`, `cost`, `time`, `suitTipType`, `upgradeTips`, etc. silently inherits the default (`preconditions=__rt_88`, `cost=__rt[390]`, `suitTipType=5`, `time=3000`, `upgradeTips=""`). Note the inherited value is itself often an `__rt` alias — merge defaults **and expand the inherited alias** before reporting (`find_row`'s `resolved_fields` does both), and mark which values came from defaults.
- `__rt_N` / `__rt[N]` tokens inside a row (or inside another `__rt` entry) are shared references — expand them before quoting.

## Lookup method

1. **Ground the build.** Read the evidence map; confirm the accepted root and build (5.0.203 / 233). State them in the answer.
2. **Resolve the asset dynamically.** Load `lua-search/inventory.json`, select the record with `name == "BuildingUpgrade"`, and verify `sha256` of `lua-search/<saved>` matches. Cite chunk/offset/size from the record actually used.
3. **Decode in memory.** XOR every byte with `0x2C`, decode as UTF-8.
4. **Build the reference table.** Parse `local __rt_N = {...}` leaf decls, `__rt[N] = {...}` composite entries, and `local __default_values = {...}`.
5. **Select the row by (buildingId, target level), never by map key.**
   - `BuildingData:GetBuildingUpgrade(buildId, curLevel)` passes `level = curLevel + 1` — the *target* level — to `getSingleBaseDataByAttr("BuildingUpgrade", {buildingId=..., level=...})` (`datas/buildingdata.lua:847-855`).
   - `BuildingData:GetBuildingUpgrade2(buildId, level)` passes the level as-is (`buildingdata.lua:858-865`).
   - `getSingleBaseDataByAttr` iterates `data.data` and requires every filter key to match; because rows carry the `__default_values` metatable, `v.buildingId` resolves to `1001` on Castle rows even though the literal omits it.
   - So "requirements for Castle 40→41" = the row with `buildingId==1001, level==41` — row `id` 1001 in this build (the id collision is coincidence, not semantics).
   - Missing row → `CheckBuildPreconditionIsPass` returns `false` (nil-safe fail), i.e. the level does not exist in this build (`buildingdata.lua:623-627`).
6. **Extract fields with defaults merged and refs expanded** (`id`, `level`, `buildingId`, `cost`, `preconditions`, `time`, `removeTime`, `suitTipType`, `ability`, `ability2`, `buildingIcon`, `upReward`, `upReward2`, `soulStoneReward`, `upgradeTips`, `formulaId`, `mailId`) — use `find_row`'s `resolved_fields`, where every value is already the real number/string/table with `__rt` aliases expanded.
7. **Map type codes** through `gameplay-lua/reward/type/rewardtype.lua`: `1` food, `2` wood, `3` stone, `4` mine/iron, `5` gold, `6` crystal, `9` item, `10` player EXP, `11` power, `12` energy, `16` spirit (see the file for the rest). For `type=9` entries the sibling `id` is the **Item base-table id** — resolve names/icons through the `Item` asset in the same inventory; do not invent names. Negative `count` = cost consumed; positive = reward granted.
8. **Classify every requirement** as hard gate / advisory / runtime state (below).
9. **Cross-check the UI** if the question is about what is displayed.
10. **Answer with the contract** at the end.

### Reusable read-only recipe

```python
import hashlib, json, pathlib, re

ROOT = pathlib.Path(r"C:\Users\lebel\pnc\.local-data\apk-exploration")  # evidence-map.md

def lua_block(s: str, i: int):
    """Return (text, end_index) for the {...} literal starting at s[i]."""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return s[i:j + 1], j + 1
        elif c == '"':                       # skip quoted strings ({, }, " inside)
            j += 1
            while s[j] != '"': j += 2 if s[j] == "\\" else 1
        j += 1
    raise ValueError("unbalanced braces")

def load_asset(name: str):
    inv = json.loads((ROOT / "lua-search/inventory.json").read_text("utf-8"))
    rec = next(r for r in inv if r.get("name") == name)
    blob = (ROOT / "lua-search" / rec["saved"]).read_bytes()
    assert hashlib.sha256(blob).hexdigest() == rec["sha256"], "stale/moved asset"
    return rec, bytes(b ^ 0x2C for b in blob).decode("utf-8")

def build_refs(src: str):
    refs = {}
    for m in re.finditer(r"local (__rt_\d+) = ", src):
        refs[m.group(1)], _ = lua_block(src, src.index("{", m.end()))
    for m in re.finditer(r"__rt\[(\d+)\] = ", src):
        refs[f"__rt[{m.group(1)}]"], _ = lua_block(src, src.index("{", m.end()))
    m = re.search(r"local __default_values = ", src)
    refs["__default_values"], _ = lua_block(src, src.index("{", m.end()))
    return refs

def fields(row: str):
    """Top-level key -> raw value of a {...} literal: numbers, "strings",
    __rt aliases, or whole nested {...} tables (kept verbatim, not collapsed)."""
    s = row.strip()
    if s.startswith("{"):
        s = s[1:-1]                                # drop the outer braces
    out, i = {}, 0
    while i < len(s):
        m = re.match(r"(\w+)\s*=", s[i:])
        if not m:                                  # separator or positional value
            if s[i] == "{":
                _, i = lua_block(s, i)
            elif s[i] == '"':
                j = i + 1
                while s[j] != '"': j += 2 if s[j] == "\\" else 1
                i = j + 1
            else:
                i += 1
            continue
        j = i + m.end()
        if s[j] == "{":
            val, j = lua_block(s, j)
        elif s[j] == '"':
            k = j + 1
            while s[k] != '"': k += 2 if s[k] == "\\" else 1
            val, j = s[j:k + 1], k + 1
        else:
            m2 = re.match(r"[^,}]+", s[j:])
            val, j = m2.group(0).strip(), j + m2.end()
        out[m.group(1)] = val
        i = j
    return out

def expand(text: str, refs):
    def sub(m):
        t = m.group(0)
        return expand(refs[t], refs) if t in refs else t
    return re.sub(r"__rt_\d+|__rt\[\d+\]", sub, text)

def find_row(src: str, building_id: int, level: int):
    """Return (row_id, expanded_row, resolved_fields) for (buildingId, target level).

    resolved_fields = __default_values merged under the row's own fields, with
    every __rt alias expanded to its actual table text — so an inherited
    table-valued default (e.g. cost=__rt[390]) reports the real table, not an
    alias the caller cannot resolve."""
    m = re.search(r"local BuildingUpgrade\s*=\s*", src)
    body, _ = lua_block(src, src.index("{", m.end()))
    refs = build_refs(src)
    defaults = fields(refs["__default_values"])
    for rm in re.finditer(r'\["(\d+)"\]=\{', body):
        row, _ = lua_block(body, rm.end() - 1)
        f = {**defaults, **fields(row)}                  # literal fields win over defaults
        if int(f.get("buildingId", -1)) == building_id and int(f.get("level", -1)) == level:
            resolved = {k: expand(v, refs) for k, v in f.items()}
            return rm.group(1), expand(row, refs), resolved
    return None
```

`find_row(src, 1001, 41)` resolves the Castle 40→41 row. `resolved_fields` is self-contained: every value is the actual number, string, or expanded table — row `915` (1027→35) omits `cost` yet reports the expanded `__rt[390]` list `{{count=-21408579,type=2},{count=-6325057,type=4},{count=-3160932,type=5}}` rather than an alias. The same `load_asset` + decode + `lua_block` helpers work for any `name` in the inventory (`Item`, `Building`, `TargetDesc`, `BuildBufferClient`, ...).

## Precondition semantics (hard gates)

`BuildingData:CheckBuildPreconditionIsPass(targetLevel, buildTypeId)` — `datas/buildingdata.lua:623-639`:

```lua
local buildUpGrade = BuildingData:GetBuildingUpgrade2(buildTypeId, targetLevel)
if buildUpGrade == nil then return false end
local isPass = BuildingData:ParseTaskTargetBySrc(preconditionStr)   -- ANDs TaskParserBase:CheckIsOpen per record
if buildTypeId == 1001 then                                        -- CASTLE
    if BuildingData:GetBuildLevelForId(buildTypeId) >= 40 then
        isPass = BuildingData.CurBuildingAbility >= preconditionStr[1].goalValue
    end
end
```

`preconditions` is a **list** of records `{target=T, ...}`; every record must pass (`TaskParserBase:CheckIsOpen`, `task/parser/taskparserbase.lua:131-206`):

- `buildingId` key present → `BuildingData:GetBuildLevelForId(buildingId) >= level` (another building must be at least that level). `techId` → `CollegeData:GetTechLevelBytechId >= level`.
- `target=4101` (`TaskParserType.Task_Parser_Type_4101`, `task/parser/taskparsertype.lua:10`) = building-level condition; `GetCurrentValue` = `GetBuildLevelForId(buildingId)`, `GetInformationNeedValue` = `level`. `8101` = tech level. `GetConditonType` maps `4101→BUILDING_ID`, `8101→TECH_ID` (`taskparserbase.lua:260-266`).
- Other handled targets: `42601` VIP level, `1007103` War God level, `36108`/`1013103`/`1014101`/`1023101` equip-star counts, `1001101` hero count at level, `1508101` finished-task count, `1113101` minigame pass count, `15602` union leader.
- **Unrecognized `target` values pass trivially** (no branch matches → `return true`). `target=4120` is not a `TaskParserType` and has no `CheckIsOpen` branch — do not describe it as a parser-level check.

### Castle ability gate (`target=4120`, Castle ≥ 40)

For `buildTypeId == 1001` (`BuildIdType.CASTLEID`, `scenes/cityscene/types/buildidtype.lua:7`) and current Castle level ≥ 40, `CheckBuildPreconditionIsPass` **replaces** the parsed result with `BuildingData.CurBuildingAbility >= preconditions[1].goalValue` — the account's current building-ability total, set from the server `abilitys["BUILDING"]` entry (`buildingdata.lua:1347-1355`). Only `preconditions[1].goalValue` is compared. This is the authoritative gate for high-level Castle rows; in the panel it renders as the ability condition bar ("building power" style icon `ico_jianzhuzhanli_40`, label from `CastleBuild.txt:title5`, showing `CurBuildingAbility / goalValue`, red when short) — `uis/building/sub/upinfo_conditionitem.lua:105-131`. `CurBuildingAbility` is runtime/server data; the `goalValue` is static.

Precondition display text comes from the `TargetDesc` base table (`taskparserbase.lua:20`, `getBaseDataLONoLog("TargetDesc", target)`) — resolve it through the same inventory/decode method if the wording matters.

## Advisory and runtime state (not static gates)

- **`suitTipType`** = advisory gear hint only. When `> 0` the panel may show a suit-tip bar comparing the player's worn-equipment stars to `suitTipType` (tip types 1 low-star / 2 owned-not-worn / 3 not owned, `uis/building/buildingupgradewin.lua:225-279`, `sub/upinfo_suittipitem.lua`), and it is **hidden** when the player already has enough resources (`buildingupgradewin.lua:296-311`). It never gates the upgrade button.
- **Resource sufficiency** = runtime check: `BuildingUpgradeWin:CheckResIsEnough` compares buff-adjusted `needCount` vs owned (`buildingupgradewin.lua:592-620`). A player can satisfy every static precondition and still be short on cost.
- **Queue state** = runtime blocker: `BuildingData:GetIdelCoolStatusType(needTime)` returns `1` free / `2`,`4` full / `5` queue-3 gift / `3` queue-gift prompt (`buildingdata.lua:1015-1051`); `OnUpgradeHandler` blocks with `Building.txt:buildingQueueIsFull` on `2`/`4` and diverts to queue-gift flows on `3`/`5` (`buildingupgradewin.lua:683-700`). Condition bars also render queue-full rows when `coolStatus` ∈ {2,4,5} (`buildingupgradewin.lua:432-451`, `sub/upinfo_conditionitem.lua:142-186`). `CheckBuildingIsUpgradeing` / `CheckBuildIsInQueue` reflect the building's own queue status (`buildingdata.lua:605-620`, `939-944`). Static data can never prove queue availability — report it as runtime-dependent unless live evidence exists.
- **Rewards/unlocks are not requirements.** `upReward`, `upReward2`, `soulStoneReward` (positive `count` = granted on completion) and `upgradeTips` describe what the upgrade yields — see the preview distinction below.

## What the UI actually displays

Requirements panel (the one that lists needs): `BuildingUpgradeWin` — `WinType.BUILDING_UPGRADE`, prefab `WinsPreFabType.BUILDING_UPGRADE = "UI/UIModules/Building/BuildingUpgradeWin.prefab"` (`uis/winsprefabtype.lua:556`), script `uis/building/buildingupgradewin.lua`.

Open path: building detail `BuildingTopItem.OnBtnMainHandler` → `UpgradeItemTable:OpenItems(buildDto)` → `BuildingUpgradeWin:OpenItems` → `UpdatePanel` (`uis/building/buildingtopitem.lua:650-668`; the Castle detail opens this same generic panel — `buildingtopitem.lua:663-665` adjusts panel position for `buildingId==1001`).

`UpdatePanel` (`buildingupgradewin.lua:190-363`) renders, in order:

1. **Time bar**: `allTime = GetBuildingUpgradeTotalTime` (raw `row.time`), `realTime = GetBuildingUpgradeRealTime` = `GameBuffManager:GetBuildTime(allTime)` then `WarGodData.AddRealTimeBySkill1(realTime)` (`buildingupgradewin.lua:194-202`). `sub/upinfo_timeitem.lua` displays `ms/1000` as `HH:MM:SS`.
2. **Condition bars**: queue-full bars (runtime) + one bar per parsed precondition (`GetConditionBarList`, `:432-466`). Conditions with `srcData.buildingId` show building-level text + go button; without `buildingId` (the 4120/ability rows) they render the ability bar above.
3. **Suit tip** (advisory, may be suppressed).
4. **Cost bars**: `GetResourceBarList(buildUpGrade.cost)` → `LuaRewardManager:GetRewardByString` → per-entry adapter (`CurrencyAdapter` for resources, `GoodsRewardAdapter` for `type=9` items — `id` → `itemId`, `count` → `actualCount`; `reward/adapter/goodsrewardadapter.lua:22-33`). `sub/upinfo_resourceitem.lua:84-132` shows `hasCount / needCount` where `needCount` is **buff-adjusted** (`GetUpgradeBuildCost` for resources, `GetItemConsume` for items), green when discounted below base, red + go-button when insufficient.
5. **Buff preview bars**: `BuildingUpgradeBuffData.GetUpgradeBuffViewInfoList(buildingId, fromLv, toLv)` (`scenes/cityscene/vo/buildingupgradebuffdata.lua:8-53`) — data-table-driven (`BuildBufferClient` filtered by `buildingIds`), can surface `BuildingUpgrade` row fields like `ability` deltas plus `soulStoneReward`.
6. **Instant-upgrade cost**: `GetCreateCrystall` = `BuildRewardData:NeedCrystalCreate(buildingId, level+1)` (`:587-589`).

Button state (`:334-361`): red when `CheckBuildPreconditionIsPass(level+1, buildingId)` fails, or when pass but `coolStatus` ∈ {2,4,5} or resources short. Click flow `OnUpgradeHandler` (`:629-721`): precondition → resource check → queue status → `BuildingSend.UpgradeBuilding(id, 0)`; Castle at `CASTLE_LVUP_NOTICE - 1` gets a confirmation first. Instant path `OnNowUpgradeHandler` (`:723+`) additionally checks item `13005004` for buildings ≥ 40 before `DoneFastUpgrade`.

**Distinguish from the post-upgrade preview**: `castleuppreview.lua` (`WinsPreFabType.CASTLE_UP_PREVIEW`, `winsprefabtype.lua:44`) is the celebration/unlock window shown *after* a Castle upgrade completes. `AddUpUnLock` (`castleuppreview.lua:138+`) reads the `BuildingUpgrade` row for `{buildingId=1001, level=GetCastLevel()}` and resolves `upgradeTips` rows into a reward/unlock grid. Rewards shown there (`upReward`, unlock tips) are consequences of the finished upgrade — never quote them as requirements.

### Buff transforms (raw vs displayed)

Always label whether a number is the raw table value or the buffed display value:

- `GameBuffManager:GetBuildTime` (`managers/gamebuffmanager.lua:897-907`): building-speed % + flat + building-time modifiers, `math.ceil`, clamp ≥ 0.
- `GameBuffManager:GetUpgradeBuildCost` (`:978-984`): per-resource upgrade-cost discounts, `ceil`, clamp ≥ 0.
- `GameBuffManager:GetItemConsume` (`:1332-1337`): per-item consumption modifiers, `ceil`, clamp ≥ 0.
- `WarGodData.AddRealTimeBySkill1` (`datas/wargoddata.lua:1010+`): additional time adjustment applied in `UpdatePanel`.

## Calibration example (5.0.203 only — not live values)

Castle `buildingId=1001`, 40→41, row `["1001"]`, raw text:

```lua
["1001"]={ability=15720000,ability2=2796253,buildingIcon="ico_chengbao",cost={{count=-489455092,type=1},{count=-198524904,type=2},{count=-58814324,type=4},{count=-29377436,type=5},__rt_8,__rt_9,__rt_10},id=1001,level=41,preconditions={{goalValue=62869520,target=4120}},removeTime=54320630000,suitTipType=7,time=108641260000,upReward=__rt_11}
```

with `__rt_8={count=-75000,id=13005001,type=9}`, `__rt_9={count=-6000,id=13005002,type=9}`, `__rt_10={count=-100,id=13005004,type=9}`, `__rt_11={count=8966043,type=10}`.

Resolved: food 489,455,092; wood 198,524,904; mine 58,814,324; gold 29,377,436; items `13005001` ×75,000, `13005002` ×6,000, `13005004` ×100; gate `CurBuildingAbility >= 62,869,520` (target 4120 — Castle override, parser returns true vacuously); base time `108,641,260,000` ms ≈ 1257 d 10 h 7 m 40 s *before* buffs; `removeTime` `54,320,630,000` ms; `suitTipType=7` (advisory); `upReward` 8,966,043 player EXP (reward, not a requirement). `buildingId` is inherited from `__default_values`.

## Answer contract

Every building-upgrade-requirement answer must state:

- **Question/target**: building id + name (resolve via `Building` asset / `BuildingData:GetBuildNameByBuildTypeId`; `buildingdata.lua:885-902`), current level, target level.
- **Evidence**: accepted build (5.0.203/233), evidence root, inventory record (chunk/offset/size/sha256/saved), and the source files + line ranges actually consulted.
- **Selected row**: row `id`, `buildingId`, `level`, and one-line proof it is the right row (matched `buildingId`/`level`, which fields came from `__default_values`).
- **Raw requirements**: resource costs by `RewardType`, item costs by item `id` (name only if resolved from `Item`), precondition records (target/goalValue/buildingId/level), base `time`, `removeTime` when relevant.
- **Gate classification**: per requirement — hard static gate (which check), Castle ability override (`CurBuildingAbility` vs `goalValue`), advisory (`suitTipType`), or runtime (resource sufficiency, queue `coolStatus`).
- **UI/buff caveats**: which numbers the panel buffs (`GetBuildTime`/`GetUpgradeBuildCost`/`GetItemConsume`/`AddRealTimeBySkill1`), and that preview-window rewards/unlocks (`upReward`, `upgradeTips`, `soulStoneReward`, `castleuppreview.lua`) are not requirements.
- **Confidence/evidence labels** per claim (`repository-proven` for the static data; `unknown`/`runtime` for queue or player state).
- **Unresolved**: name the gap and the smallest observation/artifact that would close it (e.g., a `TargetDesc` decode for display text, or a live screenshot for the rendered value).

## Boundaries

- Read-only research. Do not mutate game state, spend resources, run live upgrades, or touch ADB/emulator/accounts. Live validation requires separate explicit authorization and a non-spending scope (or exact action/target/budget via `write-code-live`).
- Never write decoded assets to disk, modify package/evidence files, or copy generated output into Git.
- Do not claim universal or current-live behavior: all data is the 5.0.203/233 snapshot.
- Never guess missing mappings, item names, or requirement values — report `unknown` plus the minimal artifact needed.
- Do not read or transmit secrets, credentials, account data, or ignored configuration files.
