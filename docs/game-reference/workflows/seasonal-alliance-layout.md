# Seasonal Alliance and Faction layouts

**Source build:** [PNC 5.0.203 / 233](../PROVENANCE.md). **Live build:**
5.2.76 / 5.0.204.235, verified in Settings on September 13, 2026.
Evidence labels below distinguish recovered client behavior from live observation.

## Client source verified

Paths are relative to the ignored recovered `gameplay-lua/` directory.

- `uis/union/unionmain.lua`, `prototype:OpenWins` (lines 152–179), shows the
  seasonal toggle only when `SeasonWarData:GetSeasonUnionStatusFlag()` and
  `SeasonWarData.canJoin` are both true. It also moves the Alliance panel and its
  scroll anchor by 60 client layout units. Those units are not screenshot pixels.
- `datas/seasonwardata.lua`, `GetSeasonUnionStatusFlag` (lines 817–830), requires
  valid season timing data, the configured `SEASONWAR_OPEN_LEVEL` castle threshold,
  and a current time from one day before `playTime` through the group `endTime`.
  `SetSeasonJoinState` (line 492) normalizes a missing `canJoin` value to false.
- `uis/union/unionmain.lua`, `prototype:OnToggleClick2` (lines 673–683), checks the
  seasonal union ID separately. If absent, it restores the Alliance selection and
  displays feedback. A visible Faction tab alone does not prove faction membership.

## Live observed

Capture package, relative to the continuation worktree:
`.local-data/artifacts/capture_gap_exploration/20260913T030954Z/`.

| Capture | Observed state |
|---|---|
| `0112_lost_city_event_entry.png` | Lost City event page; its visible title identifies Golden Sands. |
| `0166_alliance_member_back.png` | Participating K157 castle: Alliance and Faction tabs, with Alliance selected. This was after returning to the normal kingdom. |
| `0193_k290_alliance_without_faction.png` | Existing K290 castle: Alliance page with no tab strip and content positioned higher. |
| `0157` versus `0161` in the package | Leader Manage menu includes impeachment rows; ordinary member Manage has Personal Info and Send at different vertical positions. |
| `0181_alliance_hall_menu.png` | Alliance Hall: empty incoming reinforcement state with Upgrade, Send Back, and Reinforce controls. |
| `0182_alliance_hall_reinforce_members.png` | Hall Reinforce opens a member list whose row actions are Reinforce, unlike the ordinary Manage list. |

The user identified Lost City participation as the reason for the extra Faction tab.
The observed layouts agree with the recovered eligibility gate. The individual
server predicate values were not read, so the exact failed condition on K290 is
not claimed. Event display names may vary by season/localization; do not infer one
universal event name from this sample.

## Automation implications and remaining uncertainty

Recognize the tabbed and compact Alliance layouts independently. Bind fixed-control
geometry and member actions to the current layout, selected tab, role/menu variant,
and frame. Being on the normal World Map does not select the compact layout.
Do not publish a leader-menu Personal Info coordinate for an ordinary member menu,
or a Manage action for the Hall reinforcement list.

These observations establish visible controls and navigation results. They do not
establish reinforcement delivery, resource transport, member removal, or permissions
to perform those actions. No direct client/server API was invoked.
