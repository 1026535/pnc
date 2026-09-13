# Neutral gathering: identity, shield, and army counts

**Source build:** [5.0.203 / 233](../PROVENANCE.md). **Live build:**
5.2.76 / 5.0.204.235, September 13, 2026. Source paths below are relative to
the ignored recovered `gameplay-lua/` directory.

## Client source verified

`handler/slgwar/handler/slgwarcolhandler.lua:SlgWarColHandler:FightStartClickHandler`
(lines 319–349) re-reads the target tile before ordinary collection. A positive
occupier player ID belonging to another union, or two unaffiliated players, takes
the shield-check path. An unoccupied tile (`playerId=0`) takes `SendRequest`
with `hasEnemy=false`. Alliance and seasonal-alliance resource collection have
separate branches; this note does not qualify them.

`commands/resource/resourcecommand.lua:command.GoingForCollect` (line 357)
resets the client shield only when `clientData.hasEnemy` is true, then updates
own-army/map state on the accepted-response branch. These client predicates do not
replace server acceptance or a live postcondition. No direct request was executed.

`scenes/worldmap/data/maparmydata.lua:GetSelfArmyLimit` (line 979) reads the
castle-level army limit and applies `GameBuffManager:GetTeamAmount`.
`GetSelfArmyNum` (line 988) counts own armies except `BLACK_MINE_TAKE_HEAP`.
`uis/camp/campdatawin.lua:CampDataWin:UpdatePanel` (lines 73–76) displays those
busy/total army values. They are distinct from selected troops / troop capacity,
five formation hero slots, resource carrying capacity, and a boolean collecting queue.

## Live observed

Package relative to the continuation worktree:
`.local-data/artifacts/capture_gap_exploration/20260913T030954Z/`.

- Frames 0139/0146: unoccupied Farm level 6, K157 X231 Y479, and a formation of
  1,000 Buffalo Catapults without heroes. Displayed carrying capacity: 31,279 food;
  travel time: 47 seconds. The troop-capacity denominator is not a march-slot count.
- Frames 0148/0150/0152: one dispatch, destination-bound march, then active Gathering
  with 1,000 troops and the same Farm's coordinates/resource/remaining time.
- Frame 0215: resulting Gathering Report for the exact Farm, displaying 31.2K food.
  That rounded text does not independently establish an exact integer amount.
- Frame 0221: the eight-hour shield applied before leaving Lost City remained active
  after collection, with 07:10:48 remaining. No hostile action was performed.

## Automation implications and uncertainty

Bind tile identity and occupancy to fresh evidence; a neutral tile may become
occupied between observation and dispatch. Preserve exact destination association
for the active receipt and distinguish dispatch from completed return.

The live formation does not expose the army-limit inputs. A subsequent fresh-lease
probe (`20260913T051219Z`) found that the visible barracks information button opens
level unlocks, not the recovered `CAMP_DATA` statistics page. Its current entry route
remains unidentified. Do not publish available march slots from troop capacity or
carry historical counts into the current frame. A captured statistics producer
would still require an explicit consumer contract for navigation and freshness.
