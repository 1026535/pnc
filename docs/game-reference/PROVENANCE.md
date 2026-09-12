# Evidence provenance and reproduction

## Recorded build

Inspected 2026-09-12: package `com.global.tmslg`, version **5.0.203**, version code **233**, ARM64, Unity **2022.3.62f1**, IL2CPP metadata version **31**, SLua. APKs were copied from the user-selected `157_farm` instance under the canonical lease. The baseline screenshot was black, so the investigation did not establish active castle identity or live gameplay behavior.

All subsequent extraction and native tracing were offline. Keep that distinction when citing these findings. Downloaded updates can override packaged scripts; these hashes identify the package evidence, not necessarily the code active in a later session.

### APK SHA-256

Local filenames identify copies, not original split names:

| File | Bytes | SHA-256 |
|---|---|---|
| `base.apk` | 28903845 | `bf78cfb95b2e01297515bcc507ab0f52714b3a6785ade678e62112a483d346b1` |
| `split-1.apk` | 586463643 | `5c5276f03b2b838442d371932c34c7f858b9d09fbf86610f9ffa7340d838b730` |
| `split-2.apk` | 36451569 | `c5d3de945877b426c047cf8656d1794f2ca4e2768a1bd401f7830f203ec66076` |

All three ZIP CRC checks passed. `base.apk` contains `assets/bin/Data/Managed/Metadata/global-metadata.dat`; `split-2.apk` contains `lib/arm64-v8a/libil2cpp.so` and `libslua.so`.

### Source anchors

Hashes are over decoded bytes, preserving original line endings. Paths are relative to the recovered Lua root.

| File | SHA-256 |
|---|---|
| `gameluamain.lua` | `666c670bad0959db7d8b678562ca5c47aee870b04e2e1f5ac178e65f0d3b8833` |
| `commands/destination.lua` | `55f25e62572d37402826462a629741edf2305f232c270b3cb0d94115307c50f4` |
| `commands/building/buildingcommand.lua` | `3d48a35240d64452fdeed98258a8c0016d715b3416ce09bc480f443ffb051c68` |
| `datas/buildingdata.lua` | `828021ad17132e719047ac752b1f6985205616305ab1fe3b000fe8d1a3e909fa` |
| `uis/building/buildingupgradewin.lua` | `ccd2cb7f85395faa2a218c871d0d6c24bbc9d50bf503361e5532566c4a29ce85` |

## Local evidence layout

Everything below is under ignored `.local-data/apk-exploration/` and may be missing in another worktree or machine:

| Artifact | Purpose |
|---|---|
| `gameplay-lua/` | 6,276 decoded files, original asset-relative structure |
| `gameplay-lua-index.json` | Original asset paths, exported paths, byte lengths, hashes |
| `lua-search/inventory.json` | 20,959 TextAsset records across 22 scanned chunks; not all are gameplay implementation |
| `il2cppdumper/dump.cs`, `script.json` | Native metadata declarations and address mappings |
| `native-trace/` | Annotated ARM64 instructions and checksum comparison results |
| `REPORT.md`, `LUA_FINDINGS.md`, `SIMPLE_INSTR_TRACE.md` | Original exploration reports |

Original scratch scripts are also present locally, but the steps below do not require those scripts. Do not commit the APKs, extracted source, analysis dependencies, or bulk inventories. The tracked notes remain readable without them; source-dependent claims cannot be freshly verified until the evidence is available.

## Reproduce the Lua extraction offline

Use the exact asset APK hash above to reproduce this build. Place that copy at `.local-data/apk-exploration/split-1.apk`. If acquiring a new copy from an instance is necessary, follow the existing live skill and lease/target rules; this document itself is not live-action authorization.

Use Python 3.13+ with UnityPy 1.25.3 in an isolated analysis environment. For example, from the repository root:

```powershell
py -3.13 -m venv .local-data/game-reference-venv
& .local-data/game-reference-venv/Scripts/python.exe -m pip install UnityPy==1.25.3
```

Save the following as an ignored scratch script and run it with that environment. It reads the known chunk and bundle location, checks the input hash, preserves binary round trips, and writes a new output directory so an earlier extraction is not overwritten.

```python
import hashlib
import json
import lzma
import struct
import zipfile
from pathlib import Path

import UnityPy

root = Path('.local-data/apk-exploration').resolve()
apk = root / 'split-1.apk'
expected = '5c5276f03b2b838442d371932c34c7f858b9d09fbf86610f9ffa7340d838b730'
with apk.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected
with zipfile.ZipFile(apk) as archive:
    chunk = lzma.decompress(archive.read('assets/ABAsset.pkglzma_16'))
start = 25935458
assert chunk[start:start + 8] == b'UnityFS\0'
cursor = start + 12
for _ in range(2):
    cursor = chunk.index(b'\0', cursor) + 1
size = struct.unpack_from('>Q', chunk, cursor)[0]
assert 0 < size <= len(chunk) - start
environment = UnityPy.load(chunk[start:start + size])
output = root / 'reproduced-gameplay-lua'
output.mkdir()  # Use a fresh directory for each reproduction.
records = []
prefix = 'assets/resourcesdata/luascript/'
for asset_path, reference in environment.container.items():
    if reference.type.name != 'TextAsset':
        continue
    assert asset_path.startswith(prefix)
    relative = Path(asset_path.removeprefix(prefix)).with_suffix('.lua')
    destination = (output / relative).resolve()
    assert destination.is_relative_to(output)
    encoded = reference.deref_parse_as_object().m_Script.encode(
        'utf-8', 'surrogateescape'
    )
    decoded = bytes(value ^ 0x2C for value in encoded)
    decoded.decode('utf-8-sig')
    assert bytes(value ^ 0x2C for value in decoded) == encoded
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(decoded)
    records.append({
        'asset': asset_path, 'file': relative.as_posix(),
        'size': len(decoded), 'sha256': hashlib.sha256(decoded).hexdigest(),
    })
assert len(records) == 6276
records.sort(key=lambda record: record['file'])
(output / 'index.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
```

This locates one verified gameplay bundle, not arbitrary future builds. For a new build, rediscover the bundle instead of changing the input hash and assuming the offset or encoding is unchanged. UTF-8, hash, and round-trip checks prove extraction consistency, not Lua runtime correctness.

## Reproduce native evidence when needed

Extract the two files named above from the hash-matched base and ARM64 APKs. Run [IL2CppDumper 6.7.46](https://github.com/Perfare/Il2CppDumper/releases/tag/v6.7.46) on `libil2cpp.so` and `global-metadata.dat` in an ignored analysis directory. Disable `RequireAnyKey` for unattended use. Inspect the actual output location; the original run placed files beside the dumper despite the supplied output argument.

The observed registration RVAs were `0x26E7528` and `0x27CA5C0`. The tool printed a possible-protection warning before completing; method addresses were then verified through ELF load segments and coherent ARM64 instructions. Use [the shared path's anchors](REQUEST_PATH.md) with a native disassembler. Metadata declarations alone do not establish method behavior.

The original trace used Capstone 5.0.9, pyelftools 0.33, and Unicorn 2.1.4 for bounded checksum emulation. Repeating native analysis is unnecessary for a workflow whose Lua behavior and existing notes already resolve the task.
