# Resource tile labels and markers

## Provenance and scope

Inspected 2026-09-13 in the recovered PNC 5.0.203 / version code 233 client. Paths below are relative to `.local-data/apk-exploration/gameplay-lua/`; see [provenance](../PROVENANCE.md). These are client rendering predicates, not live server-state verification.

## Client source verified

- `scenes/worldmapext/module/namelabel/wmresourcenamelabel.lua`, `WMResourceNameLabel:Init`: hides the resource name and name background, uses `tubiao.png` for the level background, and positions the status node above the resource.
- Same file, `WMResourceNameLabel:SetData`: obtains level text from the resource configuration. When `tonumber(content.playerId) > 0`, enables the status node and chooses `pic_wofangzhanling.png` for the current player, `pic_youfangzhanling.png` for the same positive alliance ID or season-alliance ID, otherwise `pic_difangzhanling.png`. With no positive player ID it hides the status node.
- `scenes/worldmapext/module/tileitem/wmresourcetile.lua`, `WMResourceTile:ShowBuilding`: resource artwork is selected through `MapConfig.ResourceConfig[resourceConfig.type].ResImg`. `CheckProtect` separately enables a protection effect when `content.locked == 1`.
- `scenes/worldmapext/module/wmtilebasecontainer.lua`, `Init`, `ShowArrow`, `UpdateArrow`, and `HideArrow`: initializes `arrow.png` and attaches the displayed arrow to `MapData.WorldFocusTilePosX/Y`. Initialization can show it when `WorldMapManager.ShowSelect` is true. This is evidence of a focus/selection arrow, not evidence that every arrow denotes a march.

## Offline checked

The local comparison is saved at `.local-data/tile-recognition-evaluation/REPORT.md`, with original paths, model hashes, inference output, and benchmark scripts. It includes resource detection on v18 held-out images, OCR of manually localized level badges and three unoccupied popups, and exploratory matching of visible red/cyan banners. No new live action or march was performed.

## Automation implications and uncertainty

- Detect resource artwork independently of occupancy, protection, and focus markers. Map resource names are hidden by this renderer, so OCR cannot generally identify their type from map text.
- Search around and above an artwork box for status banners; the artwork box may exclude the top of the banner.
- Keep missing or obscured marker observations distinct from confirmed unoccupied state. Rendering predicates do not prove a screenshot was fully visible or its state is current.
- Preserve separate self/friendly/other occupancy states if the sprite-to-observed-artwork mapping is verified. This inspection did not independently match every extracted sprite to a screenshot color.
- Incoming-march semantics and marker-to-destination association remain unverified. A temporal capture showing the relevant transition is needed; selection and tutorial arrows are confounders.
- Tiny map levels need a separately validated badge localization and recognition path. Lowering OCR confidence based on a small hand-cropped sample is not sufficient validation.
