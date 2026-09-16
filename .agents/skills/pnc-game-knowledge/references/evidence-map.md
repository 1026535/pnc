# PNC APK evidence map — build 5.0.203

All paths below are relative to `.local-data/apk-exploration/` under the repository root. Evidence was acquired 2026-09-12 from the `157_farm` instance (`live_testing` role) and analyzed entirely offline.

## Verified build facts

- Package `com.global.tmslg`, versionName `5.0.203`, versionCode 233, `arm64-v8a`, minSdk 24, targetSdk 35 (`package-info.json`, `apk-checksums.json`).
- Unity `2022.3.62f1` per asset-bundle headers. IL2CPP: `libil2cpp.so` + `global-metadata.dat` (metadata version 31). SLua: `libslua.so` plus generated bindings.
- Three splits (`base.apk`, `split-1.apk`, `split-2.apk`; 651,819,057 bytes total) with SHA-256s in `apk-checksums.json`; per-split TextAsset inventories in `base-inventory.json`, `split-1-inventory.json`, `split-2-inventory.json`.

## Canonical reports — read these first

- `REPORT.md` — acquisition scope, verified findings, feasibility assessment.
- `LUA_FINDINGS.md` — Lua payload location, encoding, and the verified request example.
- `SIMPLE_INSTR_TRACE.md` — native send path, outgoing packet layout, checksum reconstruction.

## Recovered Lua tree: `gameplay-lua/` (6,276 files)

Encoding: `assets/resourcesdata/luascript/**` TextAssets XOR every byte with `0x2C` produce UTF-8 Lua source (not bytecode). The gameplay bundle starts at byte offset 25,935,458 inside the LZMA-decompressed `assets/ABAsset.pkglzma_16` entry of `split-1.apk`. `gameplay-lua-index.json` maps every original asset path to its exported file, size, and SHA-256. `reproduced-gameplay-lua/` is an independent reproduction used for verification.

- `commands/<feature>/` — request wrappers, per-feature command enums, response-handler registration via `CommandCenter:LuaRegisterHandler`. 300+ feature modules (`building`, `battle`, `arenaactivity`, `beast`, `auctionhouse`, …).
- `commands/destination.lua` — module/destination IDs (`Destination.BUILDING = 4`, …).
- `uis/<feature>/` — screen and view logic; user actions call into `commands/` (example: `uis/building/buildingupgradewin.lua`).
- `managers/`, `datas/` — client-side managers and per-feature data models (`buildingdata.lua`, `chatdata.lua`, …).
- `server/` (`jufeng/`, `serverinclude.lua`) — server-facing protocol layer; `handler/slgwar/` — war-battle response handlers; `task/` — quest-task parsing (`tasktargetparser.lua`, `taskutil.lua`). `scenes/`, `reward/`, `guides/`, `utils/`, `platform/`, `classutil/` — support code.
- Entry points and glue: `gameluamain.lua`, `gameeventtype.lua`, `winclientevent.lua`, `scenename.lua`, `analyticstype.lua`, `audioeventtype.lua`.

## Other indexes

- `lua-search/inventory.json` — 20,959 TextAsset records across all 22 `ABAsset.pkglzma_*` chunks: `{chunk, offset, name, size, header, sha256}`. Raw payloads are stored as `lua-search/<sha256>.bin`; hex header `4b45592c4368696e6573650d` = `KEY,Chinese` localization table.
- `text-assets.json` — the 460 chunk-0 TextAssets (all localization tables); samples in `textasset-*.bin`.
- `type-markers.json`, `lua-literals.json` — metadata marker lists used to locate the Lua storage.
- `bundle-manifest.json` — parsed `ABAsset` manifest.

## Native / protocol evidence

- `il2cppdumper/dump.cs`, `il2cppdumper/script.json` — IL2CPP metadata declarations: signatures and fields only, no method bodies.
- `native-trace/` — annotated ARM64 listings per function (`GameFrameWork.*.asm`); `write.txt` (addresses `0x17E1730`–`0x17E1864`) is the `WriteToSocket` source evidence, alongside `sendmsg.txt`, `dispatch.txt`, `encoding.txt`, `transport.txt`, `table-conversion.txt`; `checksum-verification.json` records the checksum emulation results; `send-loop.txt` covers the final socket send.
- Tooling: `disassemble.py` (Capstone/pyelftools), `verify_checksum.py` (Unicorn), `scan_lua.py`, `verify_lua.py`, `check_reproduced.py`.

## Verified send path: `LuaManager.SimpleInstrSend`

Bridge signature:

```csharp
void SimpleInstrSend(short moduleId, short cmd, LuaTable data,
                     object clientData, bool showLoading, int duration)
```

Chain: `LuaManager.SimpleInstrSend` (`0x17AC41C`) → `LuaSamePropertyObjectUtil.CopyLuaTableToObj` → `AppFrame.SimpleInstrSend` → `Instruction` → `AppFrame.SendInstruction` → `SocketConnection.SendMsg` → `SocketConnection.WriteToSocket` → `SocketThread` queue → `Socket.Send` (`0x17E64E8`).

- `moduleId`/`cmd` become `Request.dest`/`cmd` — 32-bit fields on the wire. `data` is serialized as UTF-8 JSON. `clientData`, `showLoading`, `duration` stay client-side in `SocketClientVO` and are not serialized.
- Frame (all 32-bit fields big-endian): magic `0x91201314` | length `N + 21` | checksum over bytes ≥ offset 12 | request seq | dest | cmd | literal `0x00` byte | payload count `N` | JSON payload — total `N + 29`.
- Checksum: FNV variant — basis `0x811C9DC5`, prime `0x01000193`, signed-byte XOR per byte, then `h += h<<13; h ^= h>>7; h += h<<3; h ^= h>>17; h += h<<5` with wrapping 32-bit arithmetic and arithmetic (sign-preserving) right shifts. Reproduced by `verify_checksum.py` against CPU emulation of the original routine on four synthetic inputs. Do not substitute a stock FNV.
- No encryption or compression step appears between the serializer and `Socket.Send` on this traced path in this build.
- `AppFrame.SendSocketInstruction` is a receiver-dictionary dispatch, not the outgoing hop.

## Verified request example

`uis/building/buildingupgradewin.lua:717` calls `BuildingSend.UpgradeBuilding(id, 0)` → `commands/building/buildingcommand.lua:326` builds `{id, queueId}` → `SimpleInstrSend` at `:334` with `Destination.BUILDING = 4` (`destination.lua:18`), `BuildingCmd.UPGRADE_BUILDING = 4` (`:58`); response handlers are registered in the `LuaRegisterHandler` block starting at `:1322`. Non-spending investigation candidate: `BuildingSend.GetBuildingInfo` at `:285` (dest 4, `BuildingCmd.GET_BUILDING_INFO = 1` at `:19`, empty server-parameter table; sends at `:302`).

## Known gaps

- No authenticated standalone client; connection setup, login/session handshake, receive-frame parsing, and response correlation are not yet traced.
- `SocketJsonVO` is a lead, not proof that every payload is plain JSON; optional per-request sender handlers can transform the payload before `SendMsg`.
- Downloaded updates and server-driven config may override packaged behavior.

## Investigation recipes

- "What happens when the user taps X" → find the view under `uis/<feature>/`, follow its `*Send.*` call into `commands/<feature>/`, record dest/cmd, the param table, and the response-handler line.
- "Which module/cmd does feature F use" → `commands/<feature>/` plus `commands/destination.lua`.
- "How is a response handled" → look for the handler registration near the end of the command file.
- "Is field F sent to the server" → only keys in the `data` table passed to `SimpleInstrSend` are serialized; `clientData`/`showLoading`/`duration` never leave the client.
- Asset missing from `gameplay-lua/` → look up its name in `lua-search/inventory.json` and read `lua-search/<sha256>.bin`; if still absent, report the gap instead of guessing.
