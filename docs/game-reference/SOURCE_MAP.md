# Source discovery

All paths in the tables below are relative to `.local-data/apk-exploration/gameplay-lua/`. That ignored directory may be absent in another checkout. See [provenance and reproduction](PROVENANCE.md). Availability is not a claim that a subsystem has been behaviorally validated.

## Structure across the recovered client

| Path | Where to begin |
|---|---|
| `gameluamain.lua` | Initialization and shared Lua entry point |
| `commands/destination.lua` | Destination identifiers; follow the matching command module |
| `commands/` | Request wrappers, command identifiers, response registration, nested DTO definitions |
| `datas/` | Client state, derived values, and data access functions |
| `uis/` | UI handlers and local action checks |
| `scenes/` | City, map, battle, and other scene behavior |
| `server/` | Connection/login helpers; not yet traced into a complete handshake |
| `managers/`, `handler/` | Shared coordination and handlers |
| `reward/` | Reward processing and resource updates |
| `guides/`, `task/` | Tutorial and task behavior |
| `utils/`, `classutil/`, `platform/` | Utilities, class support, and platform integration |

The complete per-file discovery index is `.local-data/apk-exploration/gameplay-lua-index.json`: original asset path, exported path, size, and SHA-256. The wider TextAsset inventory is `lua-search/inventory.json`; it includes configuration/localization and must not be treated as gameplay code coverage.

## Common automation starting points

| Question | Source entry points | Detailed status |
|---|---|---|
| Normal building upgrade | `uis/building/buildingupgradewin.lua`, `commands/building/buildingcommand.lua`, `datas/buildingdata.lua` | [Scoped reference](workflows/building-upgrade.md) |
| Building queues | `datas/queuedata.lua`, `datas/queuetype.lua`, `commands/building/buildingdto/playerbuildingqueuedto.lua` | Source available; follow the affected queue operation |
| Research | `commands/collegetech/collegetechcommand.lua`, `datas/collegedata.lua` | Source available |
| Chat | `commands/chat/chatcommand.lua`, `commands/privatechatcmd/privatechatcommand.lua` | Source available |
| Mail | `commands/mailx/mailxcommand.lua`, `datas/maildata.lua` | Source available |
| Login/session | `server/jufeng/gameloginmanager.lua`, `datas/logindata.lua` | Source available; no handshake validation |
| Other workflows/events | Search `commands/`, then the matching `uis/` and `datas/` callers | Source available where present; no blanket validation |

## Bounded searches

Run from the repository root; PowerShell examples:

```powershell
$gameSource = '.local-data/apk-exploration/gameplay-lua'
rg --files "$gameSource/commands"
rg --files $gameSource | rg 'college|mail|building|queue'
rg -n 'BuildingSend.UpgradeBuilding|command.UpgradeBuilding' "$gameSource/commands/building"
rg -n 'SimpleInstrSend|LuaRegisterHandler' "$gameSource/commands/collegetech"
```

Inspect the function body and callers before writing a behavioral claim. Search names reflect client naming, which may differ from UI labels (research uses `collegetech`, for example). Avoid dumping whole login modules or broad string tables into output; they are unnecessary for most tasks and may contain sensitive integration values.
