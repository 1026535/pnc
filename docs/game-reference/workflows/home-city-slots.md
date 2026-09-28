# Home-city slot eligibility and geometry coverage

**Build:** [PNC 5.0.203 / 233](../PROVENANCE.md). **Evidence:** decoded `BuildingPosition`, `Building` and `BuildingSystem` tables (XOR `0x2c` payload under `assets/ABAsset.pkglzma_18`, bundle offset 9107651; `BuildingPosition` raw SHA256 `81538538b0a9e118da2d0f48cf802cada4dde2bf64f55f25c94fed5ab0e56574`), the recovered city dispatcher, build-menu icon tables, the September 2026 live route audit, and the lead-reviewed parent-composed scene-transform extraction plus label-fit calibration of 2026-09-22 (`lead-review-v44-calibration016-20260922`; scene bundle `b4c0a3c4…`, prefab bundle `136cdf0f…`). Geometry publication is offline checked 2026-09-22; no live validation accompanied it.

Scope: static client eligibility for the 54 ordinary Home-city build slots and 15 declared system scene nodes. Eligibility is not occupancy, presence, or permission to move buildings. Canonical owner: `pnc_automation/app/pnc/domain/home_city_slots.py`.

## Slot inventory

The table declares **54 ordinary slots: 16 single-type and 38 multi-type**. Slot indices are scene handles (`BuildingPosition/<slot>/<typeId>` node paths), never coordinates.

| Slots | Client eligibility | Automation implication |
| --- | --- | --- |
| 1 / 2 | `1001` Castle / `1002` Wall | Single-type; calibrated pivot plus retained nominal catalog hint. |
| 3 / 4 | `1005` Warehouse / `1006` Watchtower | Single-type; calibrated pivot plus retained nominal catalog hint. |
| 5–8 | `1020`–`1023` Infantry/Cavalry/Ranged barracks, Siege Factory | Single-type; separate slot identities despite similar artwork. |
| 9 / 10 | `1007` Institute / `1025` Trap Workshop | Single-type; calibrated pivot plus retained nominal catalog hint. |
| 11–13 | each allows `1010` Alliance Hall, `1008` Blacksmith, `1009` Market | Multi-type; occupancy is per-account runtime evidence. Blacksmith artwork is not bound to one coordinate. |
| 14 / 15 | `1011` Hall of War / `1024` Goddess Statue | Single-type; calibrated pivot plus retained nominal catalog hint. |
| 16 | `1026` VALKYRIE | Dispatcher branch is empty; semantically unbound with calibrated pivot. |
| 17–51 | each allows `1016` Farm, `1017` Lumber Camp, `1027` Moon Well, `1003` Recruiting Center, `1004` Infirmary, `1019` Iron Mine, `1015` Gold Mine (table default) | Multi-type; per-slot occupancy must be observed, never inferred from the index. |
| 47–51 | default seven-type set plus `cost` unlock `12031001` (100 / 500 / 5000 / 10000 / 10000) | Locked small slots stay `locked`/`unknown` until observed. |
| 52 | `1028` HERO_RUNE plus `cost` unlock `12031001` ×100 | Semantically unbound type with calibrated pivot; no semantic object. |
| 53 / 54 | `1029` SEASON_TECH / `1030` WARGOD_MECHA | Semantically unbound types with calibrated pivots; availability and appearance unknown. |

`initPosition` flags: slots 1–8, 16, 52. `initPosition`/`cost` flags do not establish current occupancy or availability.

## System nodes

The decoded `BuildingSystem` table has **15 entries** (5001–5012, 5014–5016), addressed as `sys_<typeId-5000>/<typeId>` scene nodes with per-type required castle levels (1–24). Declared type `5013` (`TOWER_DEFEND`) is absent from the table and stays unresolved. Bound nodes: 5001 Bank, 5003 Dragondom Conquest, 5008 Hero Hall, 5009 Pit, 5010 Arena, 5015 Sacred Tree, 5016 Illusory Beast Manor; the rest stay unbound pending endpoint evidence. The extracted scene ships **16 `sys_1`–`sys_16` markers**; all 16 publish calibrated geometry through `home_city_system_markers()`, including `sys_13` (extracted but undeclared, so it stays unbound). `sys_16`/`5016` BEAST_MANOR binds to `HomeCityObjectId.ILLUSORY_BEAST_MANOR` through the archived scene marker plus the reviewed 2026-09-21 PW destination evidence (verified tap (511,722) -> `PNC_ILLUSORY_BEAST_MANOR`).

## Semantic binding coverage

29 of the 42 reviewed client `BuildIdType` records bind to a canonical `HomeCityObjectId` through dispatcher, build-menu icon, live-verified, or reviewed PW destination evidence. (The 54 count is the `BuildingPosition` *slot* table, not the type table.) Unbound records (1026, 1028–1030, 5002, 5004–5007, 5011–5014) publish no semantic object rather than guessing one; `9999` is a wall-hide flag, not a building, and is intentionally absent.

## Geometry coverage and gaps

- **Calibrated pivots:** all 54 ordinary slots and all 16 `sys_*` markers publish `atlas_coordinate` with evidence `cityscene_pivot_calibration_20260922`, packaged in `pnc_automation/app/pnc/data/home_city/scene_geometry.json`. Each pivot maps the extracted parent-composed world position through the lead-reviewed fit `atlas_x = k·wx + tx`, `atlas_y = −k·wy + ty` (k `108.24698772671348`, tx `−681.4851210137155`, ty `−180.35407805478746`) at zoom 1.0; recorded uncertainty is 6 reference px (leave-one-out max 3.6155 px across the seven measured anchors Castle/Infantry/Institute/Wall/Ranged/Siege/Bank). Pivots are slot placement markers — candidate *search* geometry, never nameplate points, tap authorization, body targets, routes, or occupancy.
- **Measured extent:** calibrated pivots span x `−332.2803..2357.2244`, y `370.6231..3724.9806`, published via `home_city_scene_calibration().extent`. This disproves completeness of the old inferred 2800×3200 rectangle as geometry coverage; it is a measured geometry extent only — not a camera boundary, clamp, or reachability claim. `HomeCityMapCoordinate` therefore accepts signed integers and rejects only malformed/non-integer values.
- **Inferred hints:** the 12 single-type slots whose bound object owns a reviewed `HomeCityMapAtlas` coordinate (slots 1–10, 14, 15) keep it as `inferred_atlas_coordinate` with source `catalog_map_coordinate:<object_id>` — a nominal search anchor, never verified action geometry, and distinct from the calibrated pivot.
- **Occupancy:** unknown for every multi-type slot. The future runtime producer must bind its records to current account/castle identity and frame evidence before navigation consumes them.

## Automation implications

- Navigation may act only on qualified body matches or slot geometry with named calibration evidence; inferred catalog hints may seed a search region but must never authorize a tap. A calibrated pivot may seed a search/pan; it still cannot authorize a tap without live camera and body proof.
- Multi-type eligibility is variable occupancy, not player relocation: occupants (Alliance Hall, Blacksmith, Market on slots 11–13; resource/utility types on 17–51) vary per castle, so their artwork cannot establish camera position without a verified slot binding. It may corroborate independent fixed-landmark localization. Movable occupants (Blacksmith, Alliance Hall) and the repeated Moon Well stay excluded from geometry calibration.
- A slot's calibrated pivot says nothing about current occupancy; absence of a match is never proof a slot is empty or absent.

## Remaining uncertainty

Downloaded-script overrides, server unlock state, and per-account occupancy are unverified. Native cross-zoom Home captures were not located in the reviewed corpus, so measured-zoom acceptance rests on synthetic transform checks plus the single-scale live landmark corpus until a live phase qualifies the supported zoom interval.
