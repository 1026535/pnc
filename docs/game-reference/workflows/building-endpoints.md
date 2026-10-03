# Home-city building endpoints

**Build:** [PNC 5.0.203 / 233](../PROVENANCE.md). **Evidence:** client source verified and selectively compared with September 14, 2026 live captures. No direct game-service call was made.

Scope: the client-side window selected after a Home-city building object is opened. These mappings identify candidate UI destinations; they do not prove that a building exists, is unlocked, or is safe to mutate on a current account.

## Client route owner

Source: `scenes/cityscene/vo/buildtabledata.lua`, `BuildTableData:OpenBuildWin`, `BuildTableData:_OpenBuildWinImpl`, and `BuildTableData:BuildTypeIdToWinPrefabType`; identifiers come from `scenes/cityscene/types/buildidtype.lua`.

`_OpenBuildWinImpl` is the common dispatcher for a selected building DTO. Relevant verified branches include:

| Client building type | Client destination | Automation implication |
| --- | --- | --- |
| `WALLID` (1002) | `CitywallSend.RequireGetCityWallInfo(buildDto)` before the Wall UI | A current Wall destination must be observed after the response; the object tap alone is not success. |
| `WATCHTOWERID` (1006) | `TOWER_WIN` | Qualify the Watchtower window and its own Back edge. |
| `CONSTRUCTIONID` (1008) | `EQUIP_ENTER_WIN` | This is the Blacksmith-family endpoint, not the construction-slot menu. |
| `FAIRID` (1009) | `FAIR_WIN` | This is the Market-family endpoint. |
| `EMBASSYID` (1010) | `EMBASSY_WIN` | This is the Alliance Hall endpoint. |
| `WARID` (1011) | `WAR_HALL_WIN` | This corresponds to the live-qualified Hall of War screen. |
| `CAMP_BUBING`, `CAMP_QIBING`, `CAMP_GONGBING`, `CAMP_CHEBING` (1020-1023) | `CAMP_PANEL` | The four barracks share a prefab family but still require exact Home identity and typed screen ownership. |
| `TRAP` (1025) | `TROP_WIN` | This is the Trap Workshop endpoint. |
| `BANK` (5001) | `TREASURE_CAVE_WIN` | Bank requires a new current Treasure Cave screen identity before catalog promotion. |
| `REMAINS` (5003) | `DRAGON_CAVE_MAIN_WIN` | Dragondom Conquest requires a new current Dragon Cave screen identity before catalog promotion. |
| `MINE_HOLE` (5009) | `MineWarData:sendOpenMineMainWin()` | Pit is a mine-war/Rare Earth entry and is not an upgradeable building. |
| `ARENA_BUILD` (5010) | `ARENA_ENTER_HUB` | The live destination is the Versus Center with Arena selected. |
| `BUILD_ENTER_15` (5015) | `WATER_FLOWER_WIN` | This corresponds to the Sacred Tree-family window. |

Prefab declarations are corroborated by `uis/winsprefabtype.lua`; window identifiers are in `uis/wintype.lua`. `uis/arenaactivity/arenaenterhubwin.lua:StartWindow` returns `WinType.ARENA_ENTER_HUB`. `uis/treasurecave/treasurecavewin.lua:StartWindow` returns `WinType.TREASURE_CAVE_WIN`, and `uis/dragoncave/view/dragoncavemainwin.lua:StartWindow` returns `WinType.DRAGON_CAVE_MAIN_WIN`.

## Live correspondence

- **Live observed, 2026-09-14:** Hall of War opened to the typed Hall of War layout and returned through its measured Back control.
- **Live observed, 2026-09-14:** Sacred Tree opened to the typed Sacred Tree layout and returned through its measured Back control.
- **Live observed, 2026-09-14:** Arena opened to a screen titled `Versus Center` with the `Arena` tab selected, matching `ARENA_ENTER_HUB`. A second live capture group independently reproduced that screen and consumed its measured Back control to Home; that group's later roster scan did not rediscover the active row, so it is visual/return evidence rather than a fresh full identity acceptance.
- **Live observed, 2026-09-14:** Blacksmith was reacquired from Home and opened to the Blacksmith gear hub, matching `EQUIP_ENTER_WIN`. The destination exposes Blacksmith's own Upgrade and gear-category controls. A later independent run was blocked before route acquisition by an unqualified VIP daily-reset foreground modal, so Blacksmith's return edge remains unaccepted.
- **Live observed, 2026-09-14:** Pit was published as `home_city_object_id=pit` with `upgradeable=false`. Its action point remained outside the reviewed HUD-safe band, so no Pit tap was sent.

## Remaining uncertainty

The recovered source does not prove current downloaded-script overrides, server unlock rules, current text/layout, or return behavior. Bank and Dragondom remain unpromoted until independent live captures establish their current screen identities and measured return controls. Blacksmith remains without a reviewed return until a second exact live group can run after the generic VIP foreground identity is qualified. Shared-prefab branches do not collapse exact building identity or authorize upgrade actions.

## V44 capture constraints — source recheck September 28, 2026

These findings are **repository-proven for the recovered 5.0.203 / 233 client,
high confidence**. They were rechecked offline against the accepted APK evidence
root; they are not new observations of the installed game. The live correspondence
and uncertainty above describe the September 14 checkpoint. Later V44 route
acceptance is recorded in the coordinator's revision-bound evidence ledger.

### Asset identity and occupied slots

`scenes/cityscene/buildpositionitem.lua:64-82` obtains the current building DTO
for a position before selecting its visible building. `LoadBuildingSkin` at
lines 108-122 resolves the type through
`scenes/cityscene/types/cityresourcepath.lua:GetBuildPrefabPath`, which maps to
`Scenes/CityScene/builds_F/<type>.prefab`. The lookup establishes a useful semantic
asset binding; it does not establish the current occupant from slot eligibility.
The position table's inherited defaults must be applied when reading its rows.

Use the extracted layout to plan relative movement and prefab identities to
organize capture groups. Neither supplies current native body pixels, an interior
tap region, visual availability, nor proof that all level/skin variants look
equivalent. New body bindings still need a native source view and a distinct
holdout; automatic input retains the shared current-frame body/slot contract.

### Warehouse body entry

`buildings/items/builditem_1005.lua:OnMouseClick` delegates to
`buildings/components/buildclickcomponent.lua:ClickHandler`. With a current DTO,
that component calls `BuildTableData:OpenBuildWin`; the `CELLARID` branch in
`vo/buildtabledata.lua:153-154` opens `CELLAR_WIN`. This is a candidate Warehouse
entry chain. Native body identity, current destination layout and return still
require observation before a new automatic acquisition is accepted.

### Bank can have an intermediate Home menu

`buildings/items/builditem_5001.lua:OnMouseClick` checks unlock conditions first.
Below the auction-house opening level it directly calls the Bank dispatcher.
Otherwise a body click toggles the on-city menu; `Btn1` calls the Bank dispatcher
and `Btn2` opens `AUCTION_HOUSE_WIN`. The Bank dispatcher maps to
`TREASURE_CAVE_WIN` in `vo/buildtabledata.lua:198-199`.

A Home frame immediately after the body tap therefore need not mean that the
tap failed. Capture the intermediate menu when present, positively identify the
visible Bank entry control, then observe the actual destination and return.
Do not infer a production screen identity, button coordinates or current unlock
level from these symbols. Do not enter the auction branch to qualify Bank.

### Resource body taps may collect before opening

The body handlers for client types 1015, 1016, 1017 and 1019 first check
`GetHasResPop()`. When true they call `OnNormalResourcePopClick(buildDto.id)` and
return before the ordinary building-window dispatcher. For example,
`buildings/items/builditem_1016.lua:136-152` contains this branch. These types map
to Gold Mine, Farm, Lumber Camp and Iron Mine in the canonical slot catalog.
Moon Well (1027) has the same collection branch with an additional capacity check
at `builditem_1027.lua:136-156`.

Choosing a body point away from the bubble does not by itself make these taps
non-claiming. The September 30 [standing live resource policy](../../../.agents/skills/test-bluestacks-live/SKILL.md#standing-game-resource-authority)
authorizes collection and feature-needed spending on non-Main instances. A harvest
state is not an authority blocker: observe collection, then continue the intended
entry from fresh evidence. Collection alone is not a passed route. Only an explicit
no-claim/read-only case or protected Main requires a positive non-collecting state.

### Resource collection scope and non-collecting entry — September 29 recheck

`citybuildinfotopitem.lua:145-163` resolves the tapped building's type, enumerates
every building of that type, includes each ID for which
`GainData:CheckResCanPopTip` is true, and calls `GainSend.RequireTake(bidList)`.
`commands/gain/gaincommand.lua:91-104` sends those IDs together in the `TAKE`
request. Consequently, a body tap on one exact slot can collect multiple
same-type buildings. An exact `HomeCitySlotSelector` constrains acquisition; it
does not constrain the client's collection scope.

The source-supported non-collecting body path is conditional. When the collection
branch is inactive, `BuildClickComponent:ClickHandler` at lines 17-21 dispatches
the selected DTO through `BuildTableData:OpenBuildWin`. The five resource branches
in `vo/buildtabledata.lua:174-183` open `RES_BUILD_WIN`, whose title is derived
from the selected building type (`uis/resbuild/resbuildwin.lua:98-108`).
`buildresourcepoptipcomponent.lua:105-177` sets `hasResPop` from current resource
state, except while a build-free or build-help popup has priority. These are
client-state conditions, not qualified visual controls. The harvest threshold
depends on elapsed production time and buffs (`datas/gaindata.lua:103-134`), so
the non-collecting state must remain current at dispatch. Absence of a visible
bubble in a cropped, occluded or transient frame does not prove the collection
branch is inactive. Moon Well's capacity branch is likewise not a qualified
visual precondition; do not create or assume a full-capacity state to bypass it.

No separate non-collecting resource entry control was established by the
inspected Home body handlers and dispatcher. The current shared `open_building`
contract taps one positively measured body; it has no typed resource-entry state
or reviewed `RES_BUILD_WIN` endpoint/return for these types. The Farm upgrade and
construction detail fixtures qualify different phases, not this primary window.
The remaining route evidence is an unoccluded native Home body, observed entry
effects, its primary window, independently measured Back and fresh Home return.
On non-Main instances, the standing authority permits collection, including the
same-type scope above. If the first tap collects instead of opening, reobserve and
use the next justified entry action; do not blindly replay or count collection as
arrival. A non-collecting precondition is needed only for an explicitly restricted
case or protected Main. Missing endpoint support remains implementation/evidence work.

### Military body and endpoint prerequisites — September 29 recheck

The recovered body handlers for types 1020-1022
(`builditem_1020.lua:129-150`, `builditem_1021.lua:129-149`,
`builditem_1022.lua:129-149`) and Siege 1023 (`builditem_1023.lua:102-110`)
delegate to `BuildClickComponent` after package/tutorial guards. They do not
execute the resource collection branch. The common dispatcher opens `CAMP_PANEL`
with the selected DTO (`vo/buildtabledata.lua:184-191`); Hall 1011 opens
`WAR_HALL_WIN` at lines 165-166. This proves the packaged entry chain, not the
current native appearance or return.

The September 29 route-contract candidate has distinct Infantry/Ranged primary
identities and measured Back controls, alongside the existing Hall identity/Back
contract. Public `NavigationCore.open_building` still requires a fresh measured
Home body and exact requested slot, then observes the exact primary destination;
canonical Home return separately requires its current template Back control.
Cavalry and Siege have semantic primary screen mappings but no qualified native
endpoint/Back contract in this candidate, so both public entry methods refuse
them before observation or input. Body qualification alone cannot promote those
routes. Their next prerequisite is a native primary-panel capture with visible
family identity and Back, plus an independent capture/return group; labels or the
shared prefab do not authorize copying a sibling's identity or Back geometry.

**Entry-effect correction, September 30:** Live021 Cavalry entry showed a
completed-training poptip and a completion banner in the opened panel. The
recovered 5.0.203 `CAMP_PANEL` path calls `CampData:BuildFinish`; an ended
nonempty queue can then send `RequireRecruitFinish`. The installed build and
exact resulting troop delta remain unknown. The four barracks, five resource
buildings, and Trap Workshop therefore declare possible automatic collection
as `NONSPENDING_STATE_CHANGE` for an ordinary entry workflow. A direct
navigation call defaults to `READ_ONLY`, and an enabled read-only probe rejects
those body taps. On authorized non-Main test instances incidental collection is
allowed, but the effect classification alone supplies no missing body,
destination, or return route. Passive body location and a measured return from
an already-open panel remain separate. Provenance:
`.local-data/devin-vision-pipeline/v44-military-entry-auto-collection-20260930.md`
and the reviewed live021 Cavalry incident.

## Measured body evidence — September 29, 2026

The V44-4 sepia-taleggio package measured two Home-city bodies from the
2026-09-29 driver-correction sessions (157_farm castle, normalized zoom
0.739-0.75, 900x1600 frames). Each binding pairs a native source frame with an
independent holdout; scores and projection errors come from the production
localizer and matcher.

### Warehouse — ordinary slot 3 body qualified

`warehouse_body` is authored from frame 0047 (camera translation (-777,55),
zoom ~0.739) and reproduces on independent holdout frame 0084
(translation (-389,-427), zoom 0.75, sidebar-cleared crop) at score ~0.956,
projection error ~3.9. The measured body is bound to `HomeCitySlotSelector(3)`;
slot 3 is Warehouse-only, so the same appearance across castles is a correct
slot-3 observation, not a false positive. The body also requalified on the
pan_07, mega_castle, northeast_holdout, and zoom_rung saved views. This feeds
Warehouse's existing shared route through `PNC_WAREHOUSE`; destination and
return remain the reviewed contract described above — the body evidence does
not re-prove live entry.

### Bank — fixed sys_1/5001 body qualified for perception only

`bank_body` is authored from frame 0022 (camera translation (-24,45), zoom 0.75)
and reproduces on independent survey frame 0092 (translation (-152,-21)) at
score ~0.972, projection error ~1.3. The crop covers the golden facade and blue
roof and deliberately excludes the floating `!` badge pointer and the
nameplate. On both views the measured action point lands below the conservative
HUD-safe tap band, so this evidence is perception/discovery only: it lets
shared observation report the Bank body but authorizes no tap, and
`open_building`/`open_visible_building` still refuse the unsupported route
because no `PNC_BANK` destination, entry menu, or return edge is modeled. The
intermediate Home menu behavior above stays the governing uncertainty.

### Military barracks — ordinary slots 5-8 body candidates

The V44-4 military body package measured four fixed single-type slots from the
same 2026-09-29 f1171ffa attempt1 session used for the Bank crop. All four
crops are authored from baseline frame 0022 (camera translation (-24,45),
zoom 0.75), with corresponding body regions visually measured on the independent
0092 survey view (translation (-152,-21), zoom 0.75). Native source/holdout
matching remains pending serialized validation:

- `infantry_barracks_body` (slot 5, client 1020): white facade between the red
  columns, native (415,625,83,78) on 0022 and (287,559,83,78) on 0092; also
  visually measured on the 2026-09-22 zoom-1.0 f0 baseline at (53,995,111,104). The
  crop excludes the floating coin bubble and pennant above, the gold `Z`
  marker and level badge at the right, and the nameplate below. Action point
  (450,666) on 0022 sits on the interior parapet.
- `cavalry_barracks_body` (slot 6, client 1021): blue awning and tower under
  the radar dome, (252,690,100,42) on 0022 and (124,624,100,42) on 0092; the
  `Cavalry Barracks` nameplate corroborates on 0092. The crop excludes the
  `Z` marker grazing the upper-right and the statue/nameplate below. Action
  point (308,722) on 0022 sits on the awning.
- `ranged_barracks_body` (slot 7, client 1022): gong, towers and platform
  band, (390,800,120,34) on 0022 and (262,734,120,34) on 0092. The crop
  excludes the `6` badge above, the red `0` badges and `Z` marker at the
  right, and the nameplate below. On the zoom-1.0 f0 baseline the predicted
  band lies under the chapter banner and must stay an occlusion no-match.
  Action point (445,818) on 0022 sits on the platform step.
- `siege_factory_body` (slot 8, client 1023): factory front wall between the
  blue-topped towers, (212,806,72,84) on 0022 and (84,740,72,84) on 0092.
  The crop excludes the `Z` marker at the upper-right and the cavalry
  nameplate above. On 0092 the projected action point (117,789) lands inside
  that view's left-HUD exclusion band — a view-specific limitation, not a
  target defect. Action point (245,855) on 0022 sits on the interior front
  wall.

Every action point was visually checked on both saved views against floating
training-completion bubbles, help/status bubbles, gold/`Z` markers, level
badges, nameplates and nearby area controls; all four sit on clear current
body pixels. Packaged click routing prioritizes area/button colliders over
bodies, so a body match or slot pivot alone does not prove the selected
point opens the panel — destination qualification remains a live gate, and
no military tap is authorized by this evidence.

### Hall of War — slot 14 pending native capture

Slot 14 (client type 1011, `WARID`) is a fixed single-type slot with a
calibrated pivot, but no saved frame shows the body unclipped: on 0022 the
Hall of War remains cut at the left viewport edge (~x0-95), exposing the
dome, the golden winged statue and a clipped `...of War` nameplate — enough
to corroborate identity, not enough to author a crop. The catalog therefore
carries no Hall of War target. The minimal missing capture is one native
Home view at zoom 0.75-1.0 with the Hall14 body fully inside the frame and
free of floating bubbles/area controls, its camera translation recorded, plus
one independent holdout pose; a readable `Hall of War` nameplate or a paired
endpoint/tap receipt supplies identity.

### Moon Well — multi-slot ordinary body qualified for perception only

`moon_well_body` (client 1027) is authored from the authorized 2026-09-30
ef03789c turn020 frame 0029 (camera translation (-637,-421), zoom 0.75) and
reproduces on the same-session translated holdout frame 0030 (translation
(-882,-413), zoom ~0.742). The crop covers the rocky mound, green crystals
and blue-roofed hut, excluding the floating gem-collect bubble, the yellow
flag and level badge at the right edge, and the `Moon Well` nameplate below.

Under the production localizer, the slot-17 body publishes on 0029 at
(625,1110,122,60) score ~0.994, projection error 0.35, action point (690,1140).
On 0030 the same-tier art publishes at four eligible ordinary slots — 17 at
(372,1110,120,59) score .9383 perr 10.8, 18 at (531,1016,120,59) score .9455
perr 10.7, 19 at (525,1195,120,59) score .9425 perr 9.6, and 20 at
(679,1109,120,59) score .9241 perr 9.8 — each corroborated by a readable
`Moon Well` nameplate. The multi-body view stays a candidates claim: the
singular matcher refuses an ambiguous slot. All five observed action points
(y 1046-1225) sit below the conservative HUD-safe tap band (y <= 928), so
this evidence is perception/discovery only — it lets shared observation
report Moon Well bodies at specific slots but authorizes no tap, and the
remaining body/endpoint/return evidence above still governs route acceptance.
Non-Main collection authority is supplied by the standing September 30 policy.

### Farm — body pending a clean translated holdout (retained gap)

Farm (client 1016) has one clean native source measurement — turn020 frame
0053 (translation (-351,-410), zoom ~0.739) publishes the slot-22 body at
(539,1309,67,38) score ~0.987, projection error ~0.8, action (566,1327) —
but every translated view fails the projection gate: frame 0038
(translation (-364,-422), zoom 0.75) raw-matches the same-tier body at
(538,1309,68,38) score ~0.983, yet the hit lands ~14 frame px above the
slot-22 prediction versus the reviewed 12 px bound, while sibling slots
score under 0.5. The other authorized views occlude the farm district under
the quest strip or the private-chat band, and frames 0047/0052 share 0038's
pose (a static duplicate, not a translated holdout). The catalog therefore
carries no Farm target. The minimal missing capture is one native Home view
at a pose distinct from (-351,-410) with the farm body inside the frame,
clear of the quest strip, collect bubbles, and chat band, where the measured
body agrees with its slot projection within the reviewed bound.

## Watchtower entry behavior — October 3, 2026

Repository-proven in recovered APK **5.0.203 / versionCode 233**, high
confidence for that build; current installed-client equivalence is unknown and
menu geometry, endpoint recognition and return still require native
qualification. `scenes/cityscene/buildings/items/builditem_1006.lua:146-163`
toggles an on-city menu; `Btn1` opens `TOWER_WIN`.
`uis/tower/towerwin.lua:92-115` requests tower information — a read query, not
a resource claim or spending. Body recognition alone cannot prove panel entry:
qualify the current menu control, panel and measured return; never derive a
click coordinate from the Lua button name.

Offline camera evidence: the slot-4 stone-shaft body registers on the authored
0047 source view (frame (387,311,63,89) score .9897 perr 6.72, action
(423,373)) and the translated 0050 holdout (frame (141,314,64,90) score .9143
perr 5.80, action (178,377)) under the shared .90/12px gates, and both action
points sit inside the HUD-safe band. Those measurements qualify the body for
the bounded developmental batch: it authorizes the qualified body tap plus a
measured selected-building chip control precisely to establish the endpoint
and a measured return, bound to one body witness and its continuous input
receipts. The chip is an exploratory on-city control whose immediate raw
follow-up is recorded as truth — no panel or upgrade claim, and the old Lua
`Btn1` identity stays unasserted.

October 3 correction: the chip's measurement owner is the canonical
`PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP` template selector — an opaque 78x62
RGBA crop (alpha 255 everywhere) of the green arrow/circle plus Upgrade
caption, qualified offline on the live007 native 900x1600 frame (bounds
(624,474,78,62), score 1.0, center (663,505)) and reproduced on the
translated holdout (bounds (624,496,78,62),
score .8811, center (663,527)) under the .85 whole-frame gate; both unselected
source views stay unmatched. The frozen control case now declares
`measurement_selector_id`, so the runner measures the chip from the current
frame's own provenanced template element through the annotation exchange's
selector proof — the earlier tester-attested bounds (622,945,80,110) pointed
at an unrelated city wall and are withdrawn. The selector supplies the
control's current native geometry only; it asserts no destination. Menu
entry, collider routing and return remain unproved until that batch runs;
production route promotion stays gated on the resulting endpoint/return
proof. Source-level Close/Remove behavior
does not qualify a current Back control. No new live action was performed for
this note. Provenance: recovered Lua evidence via the September 30
ordinary-building consultation and the corrected Watchtower registration on
`codex/v44-retained-routes-20261002`.

**Live008 developmental outcome, October 3:** the bounded native-chip
checkpoint ran the frozen body and chip cases on `157_farm` under run
`v44-watchtower-native-chip-20261003`. A fresh slot-4 body witness
authorized the body tap at (676,383) (receipt `in-0014`), and the current
frame's canonical chip element measured and tapped the chip at (678,518)
(receipt `in-0015`). The immediate raw follow-up is a full-screen Watch
Tower panel, consistent with the `TOWER_WIN` mapping above; installed-client
equivalence stays unproved, and the panel had no qualified visual profile at
that time. The developmental body/chip witness is therefore accepted;
the production open/return route — qualified body, fresh canonical chip,
`PNC_WATCHTOWER`/`building_watchtower` endpoint and a measured
`PNC_BACK_BUTTON_TOP_LEFT` return to guarded Home — remains pending its own
frozen acceptance run. Two unrelated delivery/host incidents are recorded
under the canonical incident collection; no game resource was spent.
Provenance: curated run evidence SHA-256
`1e731848d0be0dab92cd346675f73e6798c7b59cec886cbcd947ad6b76eb2f27` and
`.local-data/devin-vision-pipeline/V44_WATCHTOWER_LIVE008_REVIEW_20261003.json`.

**Live009 production attempt, October 3:** the first frozen production
open/return run (run `v44-watchtower-production-20261003`, candidate
`9d54a864`) FAILED at `route_opening`. Observed: the body tap dispatched at
(670,371) (`in-0014`) and the chip tap dispatched at (670,543) (`in-0015`)
from the source34 frame whose canonical match was (633,511,78,62) score
~0.8933, but no Watchtower panel and no Back receipt followed; the chip
remains visible on frames 35 and 42, so an earlier claim that it visibly
dismissed is withdrawn. The match itself moved upward 15 px between frames
34 and 35, and the caption-inclusive template center (672,542) sits below
the visible button; the dispatched point differed from that same-frame
center by only [-2,+1], so large jitter is not established. Inferred: low
point placement and animated displacement are supported miss risks.
Unknown: the exact click-time hitbox and final cause. The resolved
candidate correction keeps one asset/threshold — the canonical selector's
authored `click.point_ratio` [0.5, 0.35] resolves (672,533) inside each
current match — after 46x44 circle and 31x33 inner-arrow subcrops both
failed visible42 at the unchanged .85 gate and were rejected. The live
miss is not claimed fixed; the corrected open/return still requires its
own frozen final-candidate proof. Provenance:
`.local-data/devin-vision-pipeline/V44_WATCHTOWER_LIVE009_REVIEW_20261003.json`
and correction commit on `codex/v44-retained-routes-20261002`; two run
incidents are recorded under the canonical incident collection.

**Live010 production attempt, October 3:** the corrected-point
production open/return run (run `v44-watchtower-button-point-20261003`,
candidate `843d6039`) FAILED before chip dispatch. Observed: one body
send (`in-0014` at (686,365)) and zero chip/Back sends. Chip-source34
visibly shows the Upgrade chip yet the unchanged 78x62/.85 matcher
scores only ~0.7959 at (649,507,78,62), below the gate, so no qualified
element authorized a tap. The later final35 of the same selected
building and same input chain qualifies unchanged at (649,474,78,62)
score ~0.8634, which resolves the [0.5, 0.35] action point (688,496).
Inferred: rendering/animation variability can temporarily hold the
floating chip under the gate, and a fresh passive frame can reacquire it
without new input. Unknown: the exact pixel/opacity cause, and the
corrected point's live effectiveness remains untested. The resolved
candidate correction uses the existing bounded passive Home observation
allowance after the single body send: each fresh capture rechecks newer
timestamp, session/epoch, the original body-to-chip input chain,
normalized endpoint/calibration, Home guard and the same operation
deadline. Only a missing match may wait; a present foreign element,
interrupted chain or exhausted allowance/deadline still stops
immediately before dependent input, ending `NO_QUALIFIED_ROUTE` with no
chip sent. The circle/caption and content-glyph alpha-mask matcher
experiments failed existing saved views and were rejected; asset,
threshold, point_ratio, jitter and deadline owners stay unchanged.
Production open/return is still unproved and requires its own frozen
final-candidate run. Provenance:
`.local-data/devin-vision-pipeline/V44_WATCHTOWER_LIVE010_REVIEW_20261003.json`,
run evidence SHA-256
`304fc0f6e1cf9d1e8a5475b70417236678749f9c6333d0688967ae58768eed7a`, and
correction commit on `codex/v44-retained-routes-20261002`; two run
incidents are recorded under the canonical incident collection.

**Live011 production attempt, October 3:** the passive-reacquisition
production open/return run (run `v44-watchtower-chip-settle-20261003`,
candidate `a88236a8`) FAILED before any body, chip or Back input.
Observed: the route spent only six camera wheels and one 1,0 pan, then
refused. Camera localization passed on the last observation (native
frame 34, zoom .75, translation (-551,43), groups
garden_terrace/institute_structure/plaza_low), and the canonical shaft
template scored .90357 — above the unchanged .90 floor — but its
projection residual measured 12.414709 reference px, just beyond the
target's prior 12-px envelope, so no slot-4 body published. Native
frames 33 and 35 stay unqualified: frame 33's best saved hits score
.8875 below the floor and .9218 at a 14.65-px residual, and frame 35
scores .89966 below the floor. A Military
Expedition widget is observed on the frame; no causal role is
established. Inferred: the floating Watchtower shaft can drift a few
tenths of a pixel beyond the authored 12-px bound while remaining the
same visible body — rendering-level variability, like the chip's
live010 excursion. The resolved correction widens only the Watchtower
envelope 12 -> 13, the smallest whole-pixel bound containing the
observed residual; the .90 score floor, shaft template, reference
geometry, slot-4 identity, action geometry, HUD constraints,
provenance gates and the passive chip correction stay unchanged. All
four previously qualified source/holdout/live009/live010 body views
still match under the calibrated envelope on saved replay, and
native33/35 remain unqualified. Unknown: the precise pixel-level
cause of the floating displacement. The production open/return route
remains unproved and requires its own frozen final-candidate run.
Provenance:
`.local-data/devin-vision-pipeline/V44_WATCHTOWER_LIVE011_REVIEW_20261003.json`,
saved-frame replay
`.local-data/devin-vision-pipeline/watchtower-live011-saved-diagnosis.json`,
and correction commit on `codex/v44-retained-routes-20261002`.

**Live012 production acceptance, October 3:** run
`v44-watchtower-body-envelope-20261003` on clean `197469ba` opened the
qualified `PNC_WATCHTOWER` / `building_watchtower` panel and returned
through its measured Back control to guarded Home. The lead independently
checked the original evidence hash, all 16 input receipt chains, the
native endpoint and return images, candidate identity and cleanup. One
route attempt used six camera wheels, one pan, one qualified body tap,
one current-frame chip tap and one Back tap; no resource action occurred.
The chip match scored .864921 at (627,484,78,62), with current-match
intent (666,506) and actual receipt point (665,507). This establishes the
observed production open/return route, not an upgrade or other panel action.

The successful body frame's projection residual was 6.294839 pixels and
also qualified with the earlier 12-pixel envelope. Contrary to the worker's
causal attribution, this live run did not exercise the 13-pixel edge; its
specific calibration is proved by the saved live011 frame and deterministic
boundary tests. The chip qualified on the first post-body capture, so
bounded passive reacquisition was likewise unneeded here; its delayed-frame,
input-chain, deadline and exhaustion mechanics retain their offline proof.
Neither the exact cause of the live009 miss nor whole-V44 completion is
inferred. Original offline gate: 4,058 passed / 7 skipped on `197469ba`.
Provenance:
`.local-data/devin-vision-pipeline/V44_WATCHTOWER_LIVE012_REVIEW_20261003.json`,
original live evidence SHA-256
`62ae66b97dd8540da340fe2769b8f5033bf8ba2e8030eb4eb1bfdce05f9bd57f`.
