# Home city layout

## Evidence

Extracted offline 2026-09-23 from the packaged **5.0.203 / version code 233** client bundles. Source scene: `split-1.apk` → `assets/ABAsset.pkglzma_14` → UnityFS bundle at offset `17844917` (`BuildingPosition` root, 218 GameObjects). Re-extract with `.local-data/apk-exploration/dump_prefab2.py 14 17844917`; the saved hierarchy is `home_city_scene.json`. All coordinates below are scene world units (8 units per background tile; y decreases downward).

## Structure

- `CityMoveArea` — 60×60 world-unit BoxCollider centered `(11.56, -19.18)`: the pannable city region.
- `Frontground` — 5×4 tile grid, 8-world-unit tiles (`1_1` at (0,0) through `5_4` at (24,-32)).
- `BuildingPosition` — **54 numbered slot markers**, each a building anchor point. A slot holds either a fixed `buildingId` or an `areaId` zone per the `BuildingPosition` base-data table (TextAsset, chunk 18 offset 9107651, XOR `0x2C` Lua; `datas/buildingdata.lua:824-1520` consumes it).
- `area_2`–`area_8` — unlockable district click zones carrying `CityClickType`; `area_next_button`/`area_open_button` sit off-map at x=−50.
- `Main Camera` at `(19.82, -17.0, -100)` with `UICamera` + `BackgroundMoveForCamera` — orthographic projection; world→screen needs one calibration point (ortho size + pan offset) before slot coords yield pixels.
- `Farmers/farmer1-10`, `NewbieArmys/army*` — ambient walkers with `CityPathPointList` paths; not interactables.

## Slot anchors (world units)

Fixed `initPosition` buildings per the base table: slot 1 → `1001` (15.43, −5.09), 2 → `1002` (22.47, −17.15), 3 → `1005` (20.40, −10.34), 4 → `1006` (21.34, −5.96), 5 → `1020` (12.35, −9.42), 16 → `1026` (25.02, −7.37). Slots 11–13 accept `1010|1008|1009`; slots 17+ are `areaId` zones (17–20 → area 2, 21–26 → area 3, 27–31 → area 4, 32–36 → area 5, 37–41 → area 6, 42–46 → area 7, 47+ → area 8 with escalating `cost` unlocks).

## Automation implications

- Slot markers are **points**, not hit-boxes — tap targets should still derive from the rendered building, but the markers are the canonical screen-order and distance reference: adjacent slots are ~1–3 units; a center-screen tap that misses a building by <1 unit can be snapped to the nearest slot.
- Distance estimates are linear in world units under ortho projection; once a live frame fixes the unit↔pixel scale and pan origin, all 54 slots map deterministically.
- District unlock (`area_*` `CityClickType` zones + `cost` entries) explains why later areas appear empty — they are unlock-gated content, not missing buildings.
- Confidence: client-source + extracted-scene verified (5.0.203 packaged assets). Screen-space mapping and slot→building visual extents remain unverified until calibrated against a live frame.
