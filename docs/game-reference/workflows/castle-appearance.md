# Castle skins and ambience

## Evidence scope

Client-source findings below refer to packaged PNC **5.0.203 / code 233**;
see [provenance](../PROVENANCE.md). Downloaded updates may differ. Source paths
are relative to `.local-data/apk-exploration/gameplay-lua/`. The bounded source
report and dated screenshots are in `.local-data/skin-tab-exploration/`.

## Verified client behavior

- **Client source verified:** `uis/castleappearance/castleappearancestart.lua`,
  `StartWindow`, `ResetModel`, and `setSelectId` maintain separate castle and
  atmosphere preview layers. The tabs include Castle, Atmosphere, Nameplate,
  March, and MarchTail. Ambience adds visual effects to the selected castle.
- **Client source verified:** `CastleAppearanceStart:OnItemClick` changes the
  selected preview ID and redraws. Castle selection also records a local seen
  flag. It does not itself send an equip/activation command. Activation and use
  are distinct operations in `commands/castlesurface/castlesurfacecommand.lua`
  and `commands/castleatmosphere/castleatmospherecommand.lua`; do not press their
  controls during a preview-only collection.
- **Client source verified:** `scenes/cityscene/vo/buildingmenubardata.lua`,
  `BUTTON_PIFU`, `Get1001Btns`, and `OnMenuBtnClick` define the appearance icon
  `ioc_hxcd_gengbianwaiguan`, gate it by `BUY_CASTLE_SURFACE`, and open the
  appearance window through the surface-list request.
- **Client source verified:** `datas/castlesurfacedata.lua`, `ShowTipsForHasItem`,
  `CheckHasActItemForAll`, and `CheckhasActItemForSingle` derive this entry's red
  dot from usable castle-surface items, excluding default and permanent skins.
  The dot is optional; its predicate is more specific than merely a new catalog
  skin existing. These functions do not scan atmosphere items.

## Rendering and dataset implications

- **Client source verified:** `CastleAppearanceStart:ChangeCurCastlePic` loads
  static or animated sprites via UI CastlePic resource paths. It is not a shared
  3-D model loader. `datas/castleappearancedata.lua`, `CreateUIAtmospherParams`,
  loads a separate AtmospherePic animation.
- **Client source verified:** `scenes/worldmap/sub/worldmaptileitem.lua`,
  `AddBuilding`, and `scenes/worldmapext/module/tileitem/wmcastletile.lua`,
  `AddBuilding` / `ChangeBuildSprite`, use the same logical skin icon keys.
  `scenes/worldmap/manager/worldmapprefabmanager.lua` loads world sprite resources
  from `Scenes/WorldMap/sprites/`, a different root from preview resources.
- **Client source verified:** `WorldMapTileItem:CheckCastleAtmosphere` creates
  an extra sprite attached to the castle building container. `AtmosphereFrameHandler`
  and `AtmosphereTimeHandler` show and hide it with randomized delays; ambience
  appearance can vary between frames of the same castle.
- **Inference:** catalog previews can supplement missing skin appearances, but
  identical physical assets/resolution between preview and map have not been
  established. Logical icon reuse alone does not prove identical pixels.

For a world-map detector, keep skins in the `castle` class and record skin and
ambience IDs/names as source metadata. Treat ambience as appearance variation,
not another castle or a new object class by default. Collect examples with and
without effects. Prefer stable castle artwork for boxes; review ambiguous effect
boundaries before changing existing annotations. Preserve independent real-map
evaluation when trialing preview-derived training data.

## Live evidence and uncertainty

User screenshots show the entry icon and Castle/Ambience tabs; the user identifies
ambience as extra particles. The September 13 probe uses the canonical lease on
`157_farm`, without account/castle switching or resource spending. Consult its
`live_state.json` and screenshot sequence for completed UI postconditions.
The probe opened the catalog through an entry without a red dot, previewed
Kraken Tentacle, then selected Titan's Shadow in Ambience. The latter visibly
overlaid a translucent octopus on the same castle. No Activate control was
pressed. It returned to Home and released the account lease; the instance was
left running. Screenshots `kraken_preview.png`, `ambience_preview.png`, and
`final_home.png` record these postconditions.
The live loading screen shows resource version **5.2.76** and app version prefix
**5.0.204**, newer than the extracted package. No source claim above is silently
promoted to a verified rule of that newer build.
