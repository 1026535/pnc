# Cavalry Barracks primary panel

Artifact-observed on September 30, 2026 during the live turn021 target-only
navigation run. The helper entered Cavalry slot 6 at native action `(222,668)`
from source frame0039; endpoint frame0040 and final frame0041 visibly show the
Cavalry Barracks panel, yet both classified `UNKNOWN` because the family had no
visual profile. The guard correctly refused the Back action. Sources:
`tests/data/screen_recognition/building_routes/cavalry_barracks_native_20260930.png`
(frame0040, `20260930T024932Z_core_20260930T024749Z_d8c919d3_0040_cavalry_slot6_endpoint_endpoint_07.png`)
and correlated frame0041 `..._final_screen_08.png`, manifest group
`2026-09-30/devin-live-test_v44-4-integrated-turn021/d8c919d3`. Native frames are
RGBA 900x1600; installed build was not recorded.

The panel shows the explicit `Cavalry Barracks` title, the family-specific line
"Where Cavalry units are trained. Upgrade to unlock more advanced units.", the
cavalry building illustration and a top-left Back arrow.

**Repository-proven:** the `building_cavalry_barracks` visual profile requires
both the building-illustration and description anchors; the measured
`PNC_BACK_BUTTON_TOP_LEFT` is the only published control. The title band is
deliberately not an identity anchor: frame0041 carries transient
training-completion particles over the title (the frame0040 title template
scores 0.736 there, rivals reach 0.64), while the illustration (0.999) and
description (0.9999) stay stable. Frame0041 is a same-session correlated
validation, not an independent holdout. Older August captures named for Cavalry
are Home-city acquisition frames, not panel fixtures.

**Mutation caution, Lua-evidenced:** frame0040 carries a `Horseman training
completed` poptip, and recovered 5.0.203 Lua (`CampMainPanel.OpenWins/ShowWin ->
CampData:BuildFinish -> RequireRecruitFinish`) indicates a completed nonempty
queue auto-collects on panel open; no collection count is proven. This profile
is passive endpoint/Back perception only — it grants no entry, training,
collection, upgrade or spending authority, and further military body entry stays
held pending a state guard/authority reconciliation.

**Not yet proven:** a live typed Back return after recognition on the final
candidate, an independent-session appearance holdout, and any Siege Factory
panel remain unqualified.
