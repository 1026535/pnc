# Resource Bag rows and single Use

## Evidence and limits

The inspected client source is PNC **5.0.203 / version code 233** from the
recovered gameplay Lua cache; see [provenance](../PROVENANCE.md). The September
13 live session later displayed Settings footer `5.2.77 5.0.204.235`. Source
behavior supports the observed list model but is not an exact current-build or
server guarantee. No direct game-service request was made.

## List and action handlers

**Client source verified:** paths below are relative to the recovered gameplay
Lua root.

- `uis/bag/bagpanel.lua`, `BagPanel:UpdatePanel`, builds the selected page from
  `ItemData.GetPageItemsInfo`, copies its rows into `allDataAry`, and supplies
  that list to `BagPanelSV:SetDataList`. `datas/itemdata.lua`,
  `ItemData.GetPageItemsInfo`, combines stored items for the requested types
  and sorts them with `ItemSortHandler`. This describes client-held page data;
  it does not establish what automation has observed.
- `uis/bag/bagpanelsvitem.lua`, `BagPanelSVItem:SetData`, binds a row's name,
  item count, description, icon and controls to its current `GridData`.
  `OnUseOnceItem` calls `GamePublicManager.UseItem` with quantity **1** for
  eligible item data. `OnUseMoreItem` is a separate handler that selects a
  bulk-use flow by item type. The single-use call is an input intention, not
  proof that stock decreased or a Daily requirement completed.
- `uis/common/customgrid/luacustomgrid.lua`, `LuaCustomGrid:OnValueChanged`,
  computes the viewport from the scroll panel's height and `clipOffset`.
  A cell can be set up when its interval only partly intersects the viewport;
  it need not be fully visible. `RecycleCell` and `SetupCell` pool and reuse
  cells as the scroll position changes. `OnStoppedMoving` and `OnMomentumMove`
  refresh this calculation. `OnDragFinished` is empty, so this handler supplies
  no whole-card snapping guarantee.

`BagPanel` configures a cell size of 154 in the client UI's coordinate system.
Do not treat that value as screenshot pixels: serialized panel geometry and its
current scaling were not established. The older `uis/bag/bagitem.lua` renderer
has a different sizing contract; the inspected caller uses `BagPanelSVItem`.

## Saved-frame findings

**Live observed, September 13:** the canonical Resource scan on the exactly
verified K157 / NPC 2 castle encountered partial cards at both viewport edges.
It returned unknown inventory and Home without selecting a pack, writing a
mutation intent or issuing Use. This is consistent with the source's partial
cell visibility, not evidence of a complete inventory.

**Offline checked:** real RapidOCR through both production observation paths
agreed on the three final scroll frames. Taller fragments were UNREADABLE with
missing title/count evidence. An additional geometry replay found omitted
60-pixel and 66-pixel fragments below the detector's 120-pixel minimum at
900 by 1600. All three frames yielded zero CLIPPED rows. A full inventory cannot
be inferred from that publication.

Artifacts are under the integration candidate's ignored
`.local-data/artifacts/core_resume/`. The original frames and OCR replay are in
`manual_update_20260913T214455Z/`; `resource_edge_geometry.json` records the
additional geometry check. Exact filenames, target, results and cleanup are in
the [validation ledger](../../../reviewed_plans/PNC_CORE_PORTING_VALIDATION.md#published-checkpoint-and-resource-edge-investigation).

## Automation implications

Recognition must retain visible edge fragments and distinguish clipping from
unreadable interior content through both observation paths. Scrolling can
reframe a card, but source code supplies neither its missing live title/count
nor a guarantee that a particular gesture reveals it completely. Once those
facts are published, the canonical scanner can own bounded traversal and
complete-inventory proof. Keep unknown rows unresolved in the meantime.

Recycled cells reinforce the existing exact item fingerprint and fresh
single-Use action reacquisition requirement. Preserve the canonical journal,
one-stock-decrement receipt and full Daily survey; neither a button handler's
quantity argument nor a closed window replaces those observations.
