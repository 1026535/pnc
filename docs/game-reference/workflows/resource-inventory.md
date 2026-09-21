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

**Offline checked:** real RapidOCR through both production observation paths on
the retained September 13 scroll frames now publishes five COMPLETE interior
rows and two unresolved CLIPPED edge rows per frame. The retained fragments
include the previously omitted 60-pixel bottom band and 66-pixel top band, plus
the 146-pixel and 141-pixel edge cards previously labelled unreadable. Clipped
rows carry measured card bounds but no title, item identity, quantity or action.
Complete first/last rows in `bag.png` and `bag_current_testing.png` remain
outside the normalized edge insets.

**Offline checked, September 16 (V09 shell slice):** the shared Bag layout owner
(`pnc_automation/app/pnc/vision/bag_layout.py`) now measures one gold selected
subtab container in the five-slot band and publishes it as the typed
`Observation.active_bag_tab` (`BagTab` in `pnc_automation/app/pnc/domain/bag.py`).
Saved Resource, Speedup and Treasure captures each measure their own selection;
absent or ambiguous gold containers publish no tab. The same body/card-band
geometry returns identical card bounds on all three tabs. Measured
selected/unselected template controls for the Resource, Speedup and Treasure
buttons publish on every Bag frame; Military and Misc. selectors remain
unsupported. Resource rows and the Resource body OCR read stay gated to a
positively measured Resource selection; the Speedup and Treasure captures
publish `active_bag_tab` with no Resource rows, actions or body reads, and no
tab state carries across frames. `NavigationCore.select_bag_tab` /
`WorkflowContext.select_bag_tab` tap one measured subtab control once and
require a fresh frame with the requested typed tab; already-selected frames
no-op. On `bag.png` the fifth card's `10K Food (Safe)` row, previously
unreadable under the shared body read, now resolves `food:10000:safe` (owned
873) through one bounded per-card title/owned-column retry that only runs when
the body read leaves a complete card unresolved. These are offline replay
results on saved captures; the live proof below additionally validates navigation.

Portable fixtures are tracked under `tests/data/screen_recognition/bag_variants/`
with reviewed row and provenance entries in `manual_annotations.json`. The
original frames and OCR replay remain under the integration candidate's ignored
`.local-data/artifacts/core_resume/manual_update_20260913T214455Z/`;
`resource_edge_geometry.json` records the pre-repair geometry check. Exact
filenames, target, results and cleanup are in the [validation ledger](../../../plans/completed/core/PNC_CORE_PORTING_VALIDATION.md#published-checkpoint-and-resource-edge-investigation).

## Live confirmation — September 16

The lead reviewed the integrated V09 candidate, corrected ambiguous source-tab
selection to stop before input, and then ran the core route on the explicitly
authorized `mega_old_acc` daily-canary instance. Its active castle was verified
without selection. Home → Bag → Speedup → Treasure → Resource → one scroll →
Home passed. Speedup/Treasure had their correct typed selection and no Resource
rows; returning to Resource restored six current rows. The scrolled viewport
contained five complete Wood/Iron rows and two clipped edge fragments with no
item facts or actions. No item was consumed and the pre-existing instance was
left at Home after releasing the process lease.

Provenance: the V09 checkout's ignored `.local-data/devin-v09/live_ready/`
contains `result.json`, `trace.jsonl` and per-step observations. Runtime
`20260916T055657Z_a7e1320c` captured `0039_resource_scroll_settled.png` and final
Home `0043_core_12_after_1.png`. Confidence is high for this supported layout and
route. Military/Misc. controls and non-Resource item semantics remain with
V10–12; no full inventory or spending qualification is implied.

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
