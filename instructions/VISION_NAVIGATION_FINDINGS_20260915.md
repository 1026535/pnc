# Home and menu navigation evidence — 2026-09-15

## Captured behavior

The non-spending survey used the configured `testing` instance, its active castle,
game 5.2.80 in English, at 900 × 1600. Reference images and decoded-image hashes
are in `tests/data/screen_recognition/manifest.json` (capture group
`2026-09-15/vision_live_tour_20260915`). Original captures, observations, and the
survey report are under ignored `.local-data/reports/vision_live_tour_20260915`.

- **Campaign:** opening its Home building reached the Chapter 6 map. The user
  confirmed the bottom-right portal returns Home; the bottom-left castle icon
  was the wrong instruction. `campaign_map_chapter_6.png` qualifies this map
  appearance and its portal, not chapter selection, formation, or battle.
- **Tower of Trial:** a current-frame body tap opened Trial Challenge directly.
  `trial_challenge.png` qualifies its category-list identity and top-left return.
  The canonical building destination is therefore `PNC_TRIAL_CHALLENGE`.
  Home target acquisition remains dependent on observed building evidence.
- **Bag:** the Arena Surprise Chest magnifier opened its contents without using
  the chest. `bag_arena_chest_preview.png` qualifies only this preview appearance.
  `PNC_BAG_CHEST_PREVIEW` is task-owned: normal observation preserves it; an
  explicit measured gold-X transition returns to Bag. Missing controls and
  unrelated interruptions retain their existing guard behavior.

These are high-confidence observations of the captured views, not qualification
of all chapters, trial cards, chests, skins, or research nodes. No trial, battle,
item use, research, account switch, or castle switch was performed.

## Home map facts and design implication

The user confirmed that Home positions and dimensions change little; Christmas
skins change appearances without moving buildings. Dragondom and Lost City
Headquarters occupy fixed event slots that can be empty. Sauroi Lair retains
its position while its tutorial appearance changes. These variants were not
captured in this survey; their exact build and appearance coverage remain unknown.

Reuse the existing city atlas and navigation owner. Prefer visual localization
of the camera, fresh visibility/occupancy checks, and destination confirmation.
Separate fixed location from present/empty/unknown state and tutorial appearance.
Do not infer occupancy from an atlas coordinate or label confidence.

The measured Home pan moved an Institute patch by (-468, -931) pixels, much more
than the requested drag. Reobserve actual displacement after each pan. Offline
OpenCV patch matching and ORB translation consensus agreed on that shift.
Shared HUD artwork produced false camera matches until excluded. These small
same-session experiments support this direction but do not prove seasonal
robustness or supply a production Home detector.

## Fix validation

Focused navigation and vision tests cover the captured identities, measured
returns, absent-close rejection, task-owned recovery, and interruption priority.
Fresh live return evidence is recorded separately in the ignored report directory
`.local-data/reports/vision_navigation_fix_20260915`.

Trial Challenge → Home, Chapter 6 Campaign → Home via its bottom-right portal,
and chest preview → Bag → Home passed live on the same active testing castle.
The first Campaign confirmation failed because its selected-node ring pulses;
cropping the title anchor to exclude that ring fixed recognition on the captured
settled frames and the subsequent live return. The pulse regression is retained
as `campaign_map_chapter_6_pulse.png` in the manifest's validation split.

427 focused tests passed (249 navigation, 122 vision, 56 engine). The broader
affected and vision integration runs were stopped at the user's request to
limit work before the planned vision port; they are not passing full-suite proof.
No further detector, content-parser, or Home-atlas implementation is part of this fix.
